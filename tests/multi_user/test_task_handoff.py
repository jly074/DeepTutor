"""Synthetic same-backend handoff receipts, no external channel or accounts."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json

from deeptutor.services.task_board import TaskBoardStore, get_task_board_store
from deeptutor.services.task_detail import TaskDetail
from deeptutor.services.task_handoff import ImportHandoff, TaskHandoff
from tests.multi_user.test_task_board import client as client
from tests.multi_user.test_task_board import headers
from tests.multi_user.test_task_detail import api_path, create_task, seed_sources


def export(client, task, **kw):
    response = client.post(
        api_path(task) + "/handoff-export", headers=headers(), json={"consent": True, **kw}
    )
    assert response.status_code == 200, response.text
    return response.json()


def receive(client, task, summary, confirm=True, **kw):
    return client.post(
        api_path(task) + "/handoff-import",
        headers=headers(),
        json={"summary": summary, "confirm": confirm},
        **kw,
    )


def test_minimal_privacy_preview_confirmation_and_retry(client, as_user):
    task, _ = create_task(client)
    base = api_path(task)
    before = client.get(base + "/detail", headers=headers()).json()
    summary = export(client, task)
    assert summary["task_id"] == task and summary["status"] == "todo"
    assert summary["next_step"] == "" and summary["reference_ids"] == []
    assert "Synthetic coursework" not in json.dumps(summary)
    assert set(summary) == {
        "format",
        "id",
        "issuer",
        "task_id",
        "version",
        "status",
        "issued_at",
        "expires_at",
        "next_step",
        "reference_ids",
    }
    assert receive(client, task, summary, False).json()["accepted_at"] is None
    assert client.get(base + "/handoffs", headers=headers()).json()["items"] == []
    first = receive(client, task, summary).json()
    assert first["accepted_at"] and first == receive(client, task, summary).json()
    assert client.get(base + "/detail", headers=headers()).json() == before
    # A separate service/SQLite connection sees the same accepted receipt.
    with as_user("alice"):
        service = TaskHandoff(TaskDetail(TaskBoardStore(get_task_board_store().path), ""))
        assert service.receive(task, ImportHandoff(summary=summary, confirm=True)) == first
    assert len(client.get(base + "/handoffs", headers=headers()).json()["items"]) == 1


def test_reviewed_next_step_and_pinned_refs_roundtrip(client, as_user):
    task, _ = create_task(client)
    seed_sources(as_user)
    base = api_path(task)
    choice = client.get(base + "/evidence-choices", headers=headers()).json()["sources"][0]
    detail = client.post(
        base + "/evidence",
        headers=headers(),
        json={k: v for k, v in choice.items() if k != "label"},
    ).json()
    ref = detail["links"][0]["id"]
    summary = export(client, task, next_step="Review synthetic result", reference_ids=[ref, ref])
    assert summary["reference_ids"] == [ref]
    assert receive(client, task, summary).json()["summary"] == summary
    assert "snapshot" not in json.dumps(summary) and "label" not in summary
    assert (
        client.post(
            base + "/handoff-export",
            headers=headers(),
            json={"consent": True, "reference_ids": [ref + 100]},
        ).status_code
        == 409
    )


def test_tamper_unknown_issuer_other_task_account_and_workspace_rejected(client, as_user):
    task, _ = create_task(client)
    summary = export(client, task)
    for key, value in [
        ("status", "done"),
        ("issuer", "foreign"),
        ("next_step", "changed"),
        ("id", "unknown"),
    ]:
        response = receive(client, task, {**summary, key: value})
        assert (
            response.status_code == 409
            and response.json()["detail"]["code"] == "handoff_unverified"
        )
    assert (
        client.post(api_path(task) + "/handoff-import", json={"summary": summary}).status_code
        == 401
    )
    assert (
        client.post(
            api_path(task) + "/handoff-import", headers=headers("bob"), json={"summary": summary}
        ).status_code
        == 404
    )
    other = client.post(
        "/api/task-board/cards", headers=headers(), json={"title": "Synthetic second"}
    ).json()["cards"][-1]["id"]
    if other == task:
        other = next(
            c["id"]
            for c in client.get("/api/task-board", headers=headers()).json()["cards"]
            if c["id"] != task
        )
    assert receive(client, other, summary).status_code == 409
    from deeptutor.services.workspace import get_content_workspace_service

    with as_user("alice"):
        workspace = get_content_workspace_service().create_workspace("Synthetic workspace")[
            "workspace_id"
        ]
    client.patch(api_path(task), headers=headers(), json={"workspace_id": workspace})
    assert receive(client, task, summary).status_code == 404
    assert receive(client, task, summary, params={"dt_workspace": workspace}).status_code == 409


def test_stale_status_and_evidence_block_preview_and_apply(client, as_user):
    task, _ = create_task(client)
    summary = export(client, task)
    assert receive(client, task, summary, False).status_code == 200
    client.patch(api_path(task), headers=headers(), json={"status": "doing"})
    assert receive(client, task, summary).json()["detail"]["code"] == "handoff_stale"
    summary = export(client, task)
    seed_sources(as_user)
    choice = client.get(api_path(task) + "/evidence-choices", headers=headers()).json()["sources"][
        0
    ]
    client.post(
        api_path(task) + "/evidence",
        headers=headers(),
        json={k: v for k, v in choice.items() if k != "label"},
    )
    assert receive(client, task, summary, False).json()["detail"]["code"] == "handoff_stale"
    assert (
        client.get(api_path(task) + "/detail", headers=headers()).json()["task"]["status"]
        == "doing"
    )


def test_expiry_concurrent_retry_and_storage_failure(client, as_user, monkeypatch):
    task, _ = create_task(client)
    summary = export(client, task)
    with as_user("alice"):
        service = TaskHandoff(TaskDetail(get_task_board_store(), ""))
        request = ImportHandoff(summary=summary, confirm=True)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: service.receive(task, request), range(8)))
        assert all(r == results[0] for r in results)
        assert len(service.history(task)["items"]) == 1
        expired = {
            **summary,
            "expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        }
        with service.connection(task) as (conn, _):
            conn.execute(
                "UPDATE task_handoffs SET payload=? WHERE id=?",
                (json.dumps(expired), summary["id"]),
            )
    assert receive(client, task, expired).json()["detail"]["code"] == "handoff_expired"
    import sqlite3

    def fail(*args):
        raise sqlite3.OperationalError("synthetic private diagnostic")

    monkeypatch.setattr(TaskHandoff, "history", fail)
    response = client.get(api_path(task) + "/handoffs", headers=headers())
    assert response.status_code == 409 and "private diagnostic" not in response.text


def test_reject_missing_consent_unknown_fields_and_oversized_text(client):
    task, _ = create_task(client)
    base = api_path(task)
    for body in (
        {},
        {"consent": False},
        {"consent": True, "account_id": "bob"},
        {"consent": True, "next_step": "x" * 501},
    ):
        assert (
            client.post(base + "/handoff-export", headers=headers(), json=body).status_code == 422
        )
    summary = export(client, task)
    assert receive(client, task, {**summary, "raw_document": "not permitted"}).status_code == 422
    client.patch(base, headers=headers(), json={"archived": True})
    assert (
        client.post(base + "/handoff-export", headers=headers(), json={"consent": True}).status_code
        == 409
    )


def test_failed_acceptance_rolls_back_and_safe_retry_records_once(client, as_user):
    task, _ = create_task(client)
    summary = export(client, task)
    with as_user("alice"):
        service = TaskHandoff(TaskDetail(get_task_board_store(), ""))
        with service.connection(task) as (conn, _):
            conn.execute(
                "CREATE TRIGGER synthetic_failure BEFORE UPDATE ON task_handoffs BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END"
            )
    response = receive(client, task, summary)
    assert response.status_code == 409
    assert client.get(api_path(task) + "/handoffs", headers=headers()).json()["items"] == []
    with as_user("alice"):
        with service.connection(task) as (conn, _):
            conn.execute("DROP TRIGGER synthetic_failure")
    assert receive(client, task, summary).status_code == 200
    assert len(client.get(api_path(task) + "/handoffs", headers=headers()).json()["items"]) == 1

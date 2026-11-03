"""Synthetic task evidence: persistent links, explicit deadlines, no provider requests."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3

import pytest

from deeptutor.services.announcement_inbox import (
    AnnouncementInbox,
    ConvertAnnouncement,
    ReceiveAnnouncement,
)
from deeptutor.services.drive_source.service import get_drive_sources
from deeptutor.services.notion_source.service import get_notion_sources
from deeptutor.services.task_board import TaskBoardStore, UpdateCard, get_task_board_store
from deeptutor.services.task_detail import AdoptDeadline, InboxError, TaskDetail
from tests.multi_user.test_task_board import client as client
from tests.multi_user.test_task_board import headers


def receipt(**changes):
    return {
        "title": "Synthetic coursework",
        "body": "Synthetic source only",
        "source_label": "Synthetic announcements",
        "source_key": "notice-1",
        "simulated": True,
        "consent": True,
        **changes,
    }


def create_task(client, **changes):
    row = client.post("/api/task-board/inbox", headers=headers(), json=receipt(**changes)).json()[
        "item"
    ]
    linked = client.post(
        "/api/task-board/inbox/" + row["id"] + "/task", headers=headers(), json={"revision": 1}
    ).json()
    return linked["task_id"], row


def api_path(task):
    return "/api/task-board/cards/" + task


def seed_sources(as_user):
    with as_user("alice"):
        drive = get_drive_sources("demo")
        file = asyncio.run(drive.listing("demo-course"))[0]
        asyncio.run(drive.select("demo-course", file.id))
        notion = get_notion_sources("demo")
        row = asyncio.run(notion.preview(["title", "mastery", "status"]))["rows"][0]
        asyncio.run(notion.import_row(row.page_id, ["title", "mastery", "status"], row.fingerprint))


def test_evidence_links_pin_source_version_and_reload_without_inferred_deadline(client, as_user):
    task, announcement = create_task(client)
    seed_sources(as_user)
    base = api_path(task)
    detail = client.get(base + "/detail", headers=headers()).json()
    assert detail["task"]["due_date"] is None
    assert detail["announcements"][0]["id"] == announcement["id"]
    assert "confirm_deadline" in [s["code"] for s in detail["next_steps"]]
    choices = client.get(base + "/evidence-choices", headers=headers()).json()
    assert (
        choices["slack"] == "no_verified_automatic_intake"
        and choices["matching"] == "manual_selection_only"
    )
    assert len(choices["sources"]) == 2
    for choice in choices["sources"]:
        body = {k: v for k, v in choice.items() if k != "label"}
        one = client.post(base + "/evidence", headers=headers(), json=body)
        two = client.post(base + "/evidence", headers=headers(), json=body)
        assert one.status_code == 200 and one.json() == two.json()
    detail = client.get(base + "/detail", headers=headers()).json()
    assert len(detail["links"]) == 2 and all(link["open_url"] is None for link in detail["links"])
    assert all(link["snapshot"]["available"] is False for link in detail["links"])
    notion = next(link for link in detail["links"] if link["provider"] == "notion")
    assert notion["snapshot"]["metadata"]["fields"]["mastery"]["value"] == 42
    assert detail["task"]["status"] == "todo"
    with as_user("alice"):
        store = get_task_board_store()
        assert TaskDetail(TaskBoardStore(store.path), "").read(task)["links"] == detail["links"]


def test_deadline_correction_preserves_old_values_and_retry_never_creates_second_task(client):
    task, original = create_task(client, due_date="2026-12-10")
    base = api_path(task)
    correction = client.post(
        "/api/task-board/inbox",
        headers=headers(),
        json=receipt(
            source_key="notice-1-v2", body="Synthetic corrected deadline", due_date="2026-12-12"
        ),
    ).json()["item"]
    card = client.get(base + "/detail", headers=headers()).json()["task"]
    body = {
        "confirm": True,
        "announcement_id": correction["id"],
        "announcement_revision": 1,
        "expected_updated_at": card["updated_at"],
    }
    assert (
        client.post(
            base + "/deadline-source",
            headers=headers(),
            json={k: v for k, v in body.items() if k != "confirm"},
        ).status_code
        == 422
    )
    first = client.post(base + "/deadline-source", headers=headers(), json=body)
    second = client.post(base + "/deadline-source", headers=headers(), json=body)
    assert first.status_code == 200 and first.json() == second.json()
    data = first.json()
    assert data["task"]["due_date"] == "2026-12-12"
    assert [(h["old_date"], h["new_date"]) for h in data["deadline_history"]] == [
        (None, "2026-12-10"),
        ("2026-12-10", "2026-12-12"),
    ]
    assert data["deadline_history"][1]["basis"]["announcement_id"] == correction["id"]
    assert [a["due_date"] for a in data["announcements"]] == ["2026-12-10", "2026-12-12"]
    # Re-receive both original and correction, then convert: all point to the same task.
    for payload in (
        receipt(due_date="2026-12-10"),
        receipt(
            source_key="notice-1-v2", body="Synthetic corrected deadline", due_date="2026-12-12"
        ),
    ):
        again = client.post("/api/task-board/inbox", headers=headers(), json=payload).json()["item"]
        assert again["task_id"] == task
        assert (
            client.post(
                "/api/task-board/inbox/" + again["id"] + "/task",
                headers=headers(),
                json={"revision": 1},
            ).json()["task_id"]
            == task
        )
    assert len(client.get("/api/task-board", headers=headers()).json()["cards"]) == 1


def test_stale_correction_blocked_and_direct_edits_preserve_history(client):
    task, _ = create_task(client, due_date="2026-12-10")
    base = api_path(task)
    correction = client.post(
        "/api/task-board/inbox", headers=headers(), json=receipt(source_key="no-confirmed-date")
    ).json()["item"]
    old = client.get(base + "/detail", headers=headers()).json()["task"]
    body = {
        "confirm": True,
        "announcement_id": correction["id"],
        "announcement_revision": 1,
        "expected_updated_at": old["updated_at"],
    }
    client.patch(base, headers=headers(), json={"due_date": "2026-12-11"})
    assert client.post(base + "/deadline-source", headers=headers(), json=body).status_code == 409
    data = client.get(base + "/detail", headers=headers()).json()
    assert data["deadline_history"][-1]["basis"]["kind"] == "manual_task_edit"
    assert data["deadline_history"][-1]["old_date"] == "2026-12-10"
    body["expected_updated_at"] = data["task"]["updated_at"]
    data = client.post(base + "/deadline-source", headers=headers(), json=body).json()
    assert (
        data["task"]["due_date"] is None
        and data["deadline_history"][-1]["old_date"] == "2026-12-11"
    )
    assert "confirm_deadline" in [s["code"] for s in data["next_steps"]]


def test_foreign_accounts_and_sources_rejected(client, as_user):
    task, _ = create_task(client)
    seed_sources(as_user)
    base = api_path(task)
    assert client.get(base + "/detail").status_code == 401
    assert client.get(base + "/detail", headers=headers("bob")).status_code == 404
    choice = client.get(base + "/evidence-choices", headers=headers()).json()["sources"][0]
    bob = client.post(
        "/api/task-board/cards", headers=headers("bob"), json={"title": "Synthetic other task"}
    ).json()["cards"][0]
    body = {k: v for k, v in choice.items() if k != "label"}
    assert (
        client.post(
            api_path(bob["id"]) + "/evidence", headers=headers("bob"), json=body
        ).status_code
        == 404
    )
    assert (
        client.post(
            base + "/evidence", headers=headers(), json={**body, "account_id": "bob"}
        ).status_code
        == 422
    )


def test_new_notion_snapshot_does_not_silently_change_task_progress(client, as_user):
    task, _ = create_task(client)
    seed_sources(as_user)
    base = api_path(task)
    choice = next(
        s
        for s in client.get(base + "/evidence-choices", headers=headers()).json()["sources"]
        if s["provider"] == "notion"
    )
    body = {k: v for k, v in choice.items() if k != "label"}
    client.post(base + "/evidence", headers=headers(), json=body)
    with as_user("alice"):
        service = get_notion_sources("demo")
        original = service.client.page

        async def changed(*args):
            row = await original(*args)
            row["properties"]["Mastery"]["number"] = 73
            row["last_edited_time"] = "2026-01-02T00:00:00.000Z"
            return row

        service.client.page = changed
        row = asyncio.run(service.preview(["title", "mastery", "status"]))["rows"][0]
        asyncio.run(
            service.import_row(row.page_id, ["title", "mastery", "status"], row.fingerprint)
        )
    assert (
        client.get(base + "/detail", headers=headers()).json()["links"][0]["snapshot"]["metadata"][
            "fields"
        ]["mastery"]["value"]
        == 42
    )
    assert client.post(base + "/evidence", headers=headers(), json=body).status_code == 409
    fresh = next(
        s
        for s in client.get(base + "/evidence-choices", headers=headers()).json()["sources"]
        if s["provider"] == "notion"
    )
    data = client.post(
        base + "/evidence", headers=headers(), json={k: v for k, v in fresh.items() if k != "label"}
    ).json()
    assert (
        len(data["links"]) == 1
        and data["links"][0]["snapshot"]["metadata"]["fields"]["mastery"]["value"] == 73
    )
    with as_user("alice"):
        with sqlite3.connect(get_task_board_store().path) as conn:
            values = [
                json.loads(r[0])["metadata"]["fields"]["mastery"]["value"]
                for r in conn.execute("SELECT snapshot FROM task_source_links ORDER BY seq")
            ]
        assert values == [42, 73]


def test_deadline_transaction_rollback_and_concurrent_retries(tmp_path, monkeypatch):
    store = TaskBoardStore(tmp_path / "board.sqlite")
    inbox = AnnouncementInbox(store, "")
    first = inbox.receive(ReceiveAnnouncement(**receipt(due_date="2026-12-10")))["item"]
    task = inbox.convert(first["id"], ConvertAnnouncement(revision=1))["task_id"]
    second = inbox.receive(ReceiveAnnouncement(**receipt(source_key="v2", due_date="2026-12-12")))[
        "item"
    ]
    service = TaskDetail(store, "")
    card = service.read(task)["task"]
    change = AdoptDeadline(
        confirm=True,
        announcement_id=second["id"],
        announcement_revision=1,
        expected_updated_at=card.updated_at,
    )
    original = store._changed

    def fail(_):
        raise sqlite3.OperationalError("synthetic failure")

    monkeypatch.setattr(store, "_changed", fail)
    with pytest.raises(sqlite3.Error):
        service.adopt(task, change)
    assert service.read(task)["task"].due_date == "2026-12-10"
    assert len(service.read(task)["deadline_history"]) == 1
    monkeypatch.setattr(store, "_changed", original)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: service.adopt(task, change), range(8)))
    assert all(r["task"].due_date == "2026-12-12" for r in results)
    assert len(service.read(task)["deadline_history"]) == 2 and len(store.read().cards) == 1


def test_moving_task_does_not_expose_old_workspace_evidence(client, as_user):
    from deeptutor.services.workspace import get_content_workspace_service

    task, _ = create_task(client)
    seed_sources(as_user)
    base = api_path(task)
    source = client.get(base + "/evidence-choices", headers=headers()).json()["sources"][0]
    client.post(
        base + "/evidence",
        headers=headers(),
        json={k: v for k, v in source.items() if k != "label"},
    )
    with as_user("alice"):
        workspace = get_content_workspace_service().create_workspace("Synthetic other")[
            "workspace_id"
        ]
    client.patch(base, headers=headers(), json={"workspace_id": workspace})
    assert client.get(base + "/detail", headers=headers()).status_code == 404
    data = client.get(
        base + "/detail", headers=headers(), params={"dt_workspace": workspace}
    ).json()
    assert data["announcements"] == [] and data["links"] == [] and data["deadline_history"] == []

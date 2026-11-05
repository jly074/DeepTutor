"""Synthetic inventory checks: no remote account, scheduler or notification actions."""

import sqlite3

from deeptutor.services.automation_readiness import readiness
from deeptutor.services.task_board import get_task_board_store
from tests.multi_user.test_task_board import client as client
from tests.multi_user.test_task_board import headers

PATH = "/api/task-board/automation-readiness"


def test_inventory_never_claims_cutover_and_does_not_change_tasks(client):
    task = client.post(
        "/api/task-board/cards",
        headers=headers(),
        json={"title": "Synthetic private task", "note": "must not appear"},
    ).json()["cards"][0]
    client.patch("/api/task-board/cards/" + task["id"], headers=headers(), json={"status": "doing"})
    before = client.get("/api/task-board", headers=headers()).json()
    response = client.get(PATH, headers=headers())
    assert response.status_code == 200
    data = response.json()
    assert data["local_tasks"]["counts"] == {"todo": 0, "doing": 1, "done": 0, "archived": 0}
    assert data["external_sources_checked"] == [] and data["read_only"] is True
    assert data["notification_policy"] == "no_activation_no_delivery"
    assert {r["id"] for r in data["rows"]} == {"morning", "evening", "weekly", "slack", "tasks"}
    for row in data["rows"]:
        assert row["cutover_ready"] is False and row["v2_state"] == "unverified"
        assert row["sole_writer"] == "unconfirmed" and row["external_connection"] == "unverified"
        assert row["validation_scope"] == "synthetic_only"
        assert "legacy_schedule_state" in row["gaps"] and "rollback" in row["gaps"]
    assert task["id"] not in response.text and "must not appear" not in response.text
    assert client.get("/api/task-board", headers=headers()).json() == before
    assert client.post(PATH, headers=headers(), json={"activate": True}).status_code == 405


def test_account_workspace_isolation_and_archived_counts(client, as_user):
    from deeptutor.services.workspace import get_content_workspace_service

    assert client.get(PATH).status_code == 401
    task = client.post(
        "/api/task-board/cards", headers=headers(), json={"title": "Synthetic"}
    ).json()["cards"][0]
    with as_user("alice"):
        workspace = get_content_workspace_service().create_workspace("Synthetic separate")[
            "workspace_id"
        ]
    client.patch(
        "/api/task-board/cards/" + task["id"],
        headers=headers(),
        json={"workspace_id": workspace, "archived": True},
    )
    assert sum(client.get(PATH, headers=headers()).json()["local_tasks"]["counts"].values()) == 0
    scoped = client.get(PATH, headers=headers(), params={"dt_workspace": workspace}).json()
    assert scoped["local_tasks"]["counts"] == {"todo": 0, "doing": 0, "done": 0, "archived": 1}
    assert (
        sum(client.get(PATH, headers=headers("bob")).json()["local_tasks"]["counts"].values()) == 0
    )
    assert (
        client.get(PATH, headers=headers("bob"), params={"dt_workspace": workspace}).status_code
        == 404
    )


def test_storage_failure_keeps_checklist_but_never_claims_zero(client, monkeypatch):
    from deeptutor.services.task_board import TaskBoardStore

    def fail(_):
        raise sqlite3.OperationalError("private synthetic path")

    monkeypatch.setattr(TaskBoardStore, "read", fail)
    response = client.get(PATH, headers=headers())
    assert response.status_code == 200 and "private synthetic path" not in response.text
    assert response.json()["local_tasks"]["state"] == "unavailable"
    assert response.json()["local_tasks"]["counts"] is None
    assert len(response.json()["rows"]) == 5


def test_separate_store_reload_returns_same_scoped_inventory(client, as_user):
    from deeptutor.services.task_board import TaskBoardStore

    client.post("/api/task-board/cards", headers=headers(), json={"title": "Synthetic persistent"})
    before = client.get(PATH, headers=headers()).json()
    before.pop("observed_at")
    with as_user("alice"):
        reloaded = readiness(TaskBoardStore(get_task_board_store().path).read, "")
    reloaded.pop("observed_at")
    assert before == reloaded

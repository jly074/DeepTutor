"""Synthetic manual intake; authenticated real local API and atomic persistence."""

from concurrent.futures import ThreadPoolExecutor
import sqlite3

from pydantic import ValidationError
import pytest

from deeptutor.services.announcement_inbox import (
    AnnouncementInbox,
    ConvertAnnouncement,
    InboxError,
    ReceiveAnnouncement,
    ReviewAnnouncement,
)
from deeptutor.services.task_board import CreateCard, TaskBoardStore, UpdateCard
from tests.multi_user.test_task_board import client as client
from tests.multi_user.test_task_board import headers


def payload(**changes):
    return {
        "title": "Synthetic announcement",
        "body": "Original synthetic body",
        "source_label": "Synthetic course",
        "source_key": "announcement-1",
        "simulated": True,
        "consent": True,
        **changes,
    }


def test_http_scope_dedup_conflict_conversion_and_reload(client):
    path = "/api/task-board/inbox"
    assert client.get(path).status_code == 401
    result = client.post(path, headers=headers(), json=payload()).json()
    row = result["item"]
    assert result["duplicate"] is False and row["task_id"] is None
    assert client.get("/api/task-board", headers=headers()).json()["cards"] == []
    repeated = client.post(path, headers=headers(), json=payload()).json()
    assert repeated["duplicate"] and repeated["item"] == row
    assert client.post(path, headers=headers(), json=payload(body="Changed")).status_code == 409
    assert client.post(path, headers=headers(), json=payload(account_id="bob")).status_code == 422
    assert client.get(path, headers=headers("bob")).json()["items"] == []
    assert (
        client.patch(
            path + "/" + row["id"], headers=headers("bob"), json={"revision": 1, "reviewed": True}
        ).status_code
        == 404
    )
    review = client.patch(
        path + "/" + row["id"], headers=headers(), json={"revision": 1, "reviewed": True}
    ).json()
    assert review["reviewed"] and review["revision"] == 2
    assert (
        client.patch(
            path + "/" + row["id"], headers=headers(), json={"revision": 1, "reviewed": False}
        ).status_code
        == 409
    )
    first = client.post(
        path + "/" + row["id"] + "/task", headers=headers(), json={"revision": 2}
    ).json()
    second = client.post(
        path + "/" + row["id"] + "/task", headers=headers(), json={"revision": 2}
    ).json()
    assert first["task_id"] == second["task_id"] and first["task"]["status"] == "todo"
    board = client.get("/api/task-board", headers=headers()).json()
    assert len(board["cards"]) == 1
    card = board["cards"][0]
    assert card["title"].startswith("[Synthetic] ") and card["due_date"] is None
    assert "Original synthetic body" not in card["note"]
    assert row["id"] in card["note"]
    client.patch("/api/task-board/cards/" + card["id"], headers=headers(), json={"status": "doing"})
    listed = client.get(path, headers=headers()).json()
    assert listed["slack_connected"] is False and listed["items"][0]["task"]["status"] == "doing"


def test_workspace_and_mode_isolation_and_existing_board(tmp_path):
    store = TaskBoardStore(tmp_path / "tasks.sqlite")
    old = store.create(CreateCard(title="Existing"), "a").cards[0]
    a, b = AnnouncementInbox(store, "a"), AnnouncementInbox(store, "b")
    row = a.receive(ReceiveAnnouncement(**payload()))["item"]
    assert b.list()["items"] == []
    with pytest.raises(InboxError, match="not_found"):
        b.convert(row["id"], ConvertAnnouncement(revision=1))
    other = b.receive(ReceiveAnnouncement(**payload()))["item"]
    live = a.receive(ReceiveAnnouncement(**payload(simulated=False)))["item"]
    assert len({row["id"], other["id"], live["id"]}) == 3
    assert store.read().cards == [old]
    restored = AnnouncementInbox(TaskBoardStore(store.path), "a")
    assert len(restored.list()["items"]) == 2


def test_concurrent_receive_and_convert_are_atomic(tmp_path):
    path = tmp_path / "tasks.sqlite"
    inbox = AnnouncementInbox(TaskBoardStore(path), "")
    inbox.list()  # initialize the shared schema before concurrent workers

    def receive(_):
        return inbox.receive(ReceiveAnnouncement(**payload()))["item"]

    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(receive, range(12)))
    assert len({r["id"] for r in rows}) == 1

    def convert(_):
        return inbox.convert(rows[0]["id"], ConvertAnnouncement(revision=1))

    with ThreadPoolExecutor(max_workers=6) as pool:
        converted = list(pool.map(convert, range(12)))
    assert len({r["task_id"] for r in converted}) == 1
    assert len(inbox.board.read().cards) == 1


def test_conversion_rollback_does_not_leave_orphan_task(tmp_path, monkeypatch):
    store = TaskBoardStore(tmp_path / "tasks.sqlite")
    inbox = AnnouncementInbox(store, "")
    row = inbox.receive(ReceiveAnnouncement(**payload()))["item"]

    def fail(_):
        raise sqlite3.OperationalError("synthetic failure")

    monkeypatch.setattr(store, "_changed", fail)
    with pytest.raises(sqlite3.Error):
        inbox.convert(row["id"], ConvertAnnouncement(revision=1))
    assert store.read().cards == [] and inbox.list()["items"][0]["task_id"] is None


def test_moved_task_does_not_leak_or_recreate(tmp_path):
    store = TaskBoardStore(tmp_path / "tasks.sqlite")
    inbox = AnnouncementInbox(store, "a")
    row = inbox.receive(ReceiveAnnouncement(**payload()))["item"]
    linked = inbox.convert(row["id"], ConvertAnnouncement(revision=1))
    store.update(linked["task_id"], UpdateCard(workspace_id="b"), workspace_id="a")
    retried = inbox.convert(row["id"], ConvertAnnouncement(revision=1))
    assert retried["task"] is None and retried["task_id"] == linked["task_id"]
    assert len(store.read().cards) == 1


def test_bounded_pagination_and_explicit_date(tmp_path):
    inbox = AnnouncementInbox(TaskBoardStore(tmp_path / "tasks.sqlite"), "")
    for n in range(52):
        inbox.receive(ReceiveAnnouncement(**payload(source_key=str(n), due_date="2026-12-02")))
    first = inbox.list()
    second = inbox.list(first["next_cursor"])
    assert len(first["items"]) == 50 and len(second["items"]) == 2 and second["next_cursor"] is None
    assert not {r["id"] for r in first["items"]} & {r["id"] for r in second["items"]}
    row = first["items"][0]
    inbox.convert(row["id"], ConvertAnnouncement(revision=1))
    assert inbox.board.read().cards[0].due_date == "2026-12-02"


@pytest.mark.parametrize(
    "change",
    [
        {"source_url": "javascript:alert(1)"},
        {"source_url": "https://u:password@example.test/a"},
        {"source_url": "file:///tmp/a"},
        {"due_date": "2026-02-30"},
        {"consent": False},
        {"source_key": " "},
        {"title": "x" * 149},
    ],
)
def test_invalid_input(change):
    with pytest.raises(ValidationError):
        ReceiveAnnouncement(**payload(**change))


def test_http_workspace_filter_cannot_be_bypassed(client, as_user):
    from deeptutor.services.workspace import get_content_workspace_service

    with as_user("alice"):
        a = get_content_workspace_service().create_workspace("Synthetic A")["workspace_id"]
        b = get_content_workspace_service().create_workspace("Synthetic B")["workspace_id"]
    path = "/api/task-board/inbox"
    row = client.post(path, headers=headers(), params={"dt_workspace": a}, json=payload()).json()[
        "item"
    ]
    assert client.get(path, headers=headers(), params={"dt_workspace": b}).json()["items"] == []
    for workspace in ("", b):
        assert (
            client.post(
                path + "/" + row["id"] + "/task",
                headers=headers(),
                params={"dt_workspace": workspace},
                json={"revision": 1},
            ).status_code
            == 404
        )
    assert (
        client.get(path, headers=headers(), params={"dt_workspace": a}).json()["items"][0][
            "task_id"
        ]
        is None
    )

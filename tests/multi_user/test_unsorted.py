"""Synthetic-only intake, originals and scoped manual classification."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import sqlite3

import pytest

from deeptutor.services.storage.file_library import FileLibraryStore
from deeptutor.services.task_board import TaskBoardStore
from deeptutor.services.unsorted import CollectBatch, Unsorted
from tests.multi_user.test_task_board import client as client
from tests.multi_user.test_task_board import headers


def upload(client, files, **data):
    return client.post(
        "/api/task-board/intake/batch",
        headers=headers(),
        data={"consent": "true", "data_class": "synthetic", **data},
        files=[("files", (name, content, "application/octet-stream")) for name, content in files],
    )


def listed(client):
    return client.get("/api/task-board/intake/items", headers=headers()).json()["items"]


def test_batch_originals_retry_explicit_versions_and_no_name_inference(client):
    first = upload(client, [("中文.txt", b"synthetic A"), ("b.txt", b"synthetic B")]).json()[
        "results"
    ]
    assert all(r["ok"] for r in first)
    a = first[0]["item"]
    assert a["status"] == "pending" and a["category"] == ""
    again = upload(client, [("中文.txt", b"synthetic A")]).json()["results"][0]
    assert again["duplicate"] and again["item"]["id"] == a["id"]
    same_name = upload(client, [("中文.txt", b"synthetic independent")]).json()["results"][0][
        "item"
    ]
    assert same_name["source_id"] != a["source_id"]
    version = upload(
        client, [("中文-v2.txt", b"synthetic revised")], source_id=a["source_id"]
    ).json()["results"][0]["item"]
    assert version["source_id"] == a["source_id"] and version["sha256"] != a["sha256"]
    for item, content in [(a, b"synthetic A"), (version, b"synthetic revised")]:
        r = client.get("/api/task-board/intake/original/" + item["id"], headers=headers())
        assert r.content == content and hashlib.sha256(r.content).hexdigest() == item["sha256"]
        assert r.headers["content-disposition"].startswith("attachment;")
        assert r.headers["cache-control"] == "no-store"
    assert len(listed(client)) == 4


def test_partial_failure_validation_and_missing_consent(client):
    assert upload(client, [("a", b"a")], consent="false").status_code == 403
    assert listed(client) == []
    results = upload(
        client, [("safe.txt", b"synthetic"), ("../bad.txt", b"bad"), ("empty", b"")]
    ).json()["results"]
    assert [r["ok"] for r in results] == [True, False, False]
    assert results[1]["code"] == "invalid_filename" and results[2]["code"] == "file_size"
    assert upload(client, [(str(i), b"x") for i in range(11)]).status_code == 422
    assert not upload(client, [("huge", b"x" * (5 * 1024 * 1024 + 1))]).json()["results"][0]["ok"]
    assert len(listed(client)) == 1


def test_collect_atomic_stale_retry_and_manual_correction(client, as_user):
    items = [r["item"] for r in upload(client, [("a", b"a"), ("b", b"b")]).json()["results"]]
    body = {
        "items": [{"id": i["id"], "revision": 1, "category": "Synthetic chapter"} for i in items]
    }
    stale = {"items": [body["items"][0], {**body["items"][1], "revision": 99}]}
    assert (
        client.post("/api/task-board/intake/collect", headers=headers(), json=stale).status_code
        == 409
    )
    assert all(i["status"] == "pending" for i in listed(client))
    one = client.post("/api/task-board/intake/collect", headers=headers(), json=body).json()
    assert client.post("/api/task-board/intake/collect", headers=headers(), json=body).json() == one
    assert all(i["status"] == "collected" for i in listed(client))
    correction = {
        "items": [{"id": items[0]["id"], "revision": 2, "category": "Corrected synthetic chapter"}]
    }
    assert (
        client.post(
            "/api/task-board/intake/collect", headers=headers(), json=correction
        ).status_code
        == 200
    )
    with as_user("alice"):
        from deeptutor.services.task_board import get_task_board_store

        with sqlite3.connect(get_task_board_store().path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM intake_history").fetchone()[0] == 3


def test_registration_failure_keeps_original_and_retry_recovers(client, monkeypatch):
    original = Unsorted.register

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("synthetic failure")

    monkeypatch.setattr(Unsorted, "register", fail)
    failed = upload(client, [("retry.txt", b"synthetic retry")]).json()["results"][0]
    assert not failed["ok"] and failed["code"] == "storage_unavailable"
    assert listed(client) == []
    monkeypatch.setattr(Unsorted, "register", original)
    item = upload(client, [("retry.txt", b"synthetic retry")]).json()["results"][0]["item"]
    assert (
        client.get("/api/task-board/intake/original/" + item["id"], headers=headers()).content
        == b"synthetic retry"
    )
    assert len(listed(client)) == 1


def test_account_workspace_and_forged_target_isolation(client, as_user):
    a = upload(client, [("private-synthetic.txt", b"synthetic")]).json()["results"][0]["item"]
    path = "/api/task-board/intake/original/" + a["id"]
    assert client.get(path).status_code == 401
    assert client.get(path, headers=headers("bob")).status_code == 404
    assert client.get("/api/task-board/intake/items", headers=headers("bob")).json()["items"] == []
    with as_user("alice"):
        from deeptutor.services.workspace import get_content_workspace_service

        workspace = get_content_workspace_service().create_workspace("Synthetic other")[
            "workspace_id"
        ]
    assert (
        client.get(path, headers=headers(), params={"dt_workspace": workspace}).status_code == 404
    )
    r = client.post(
        "/api/task-board/intake/batch",
        headers=headers(),
        params={"dt_workspace": workspace},
        data={"consent": "true", "data_class": "synthetic", "source_id": a["source_id"]},
        files={"files": ("x", b"x")},
    )
    assert r.json()["results"][0]["code"] == "not_found"


def test_parallel_dedup_and_reopen(tmp_path):
    library = FileLibraryStore(tmp_path / "library.db", tmp_path / "files")
    board = TaskBoardStore(tmp_path / "board.db")
    service = Unsorted(board, "workspace-a", library)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda _: asyncio.run(service.receive("same.txt", b"synthetic", "synthetic")),
                range(8),
            )
        )
    assert len({r["item"]["id"] for r in results}) == 1
    reopened = Unsorted(
        TaskBoardStore(board.path),
        "workspace-a",
        FileLibraryStore(tmp_path / "library.db", tmp_path / "files"),
    )
    assert reopened.listing() == service.listing()
    item = reopened.listing()["items"][0]
    assert library.resolve_path(item["library_id"]).read_bytes() == b"synthetic"
    payload = CollectBatch(items=[{"id": item["id"], "revision": 1, "category": "Synthetic"}])
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: reopened.collect(payload), range(8)))
    with sqlite3.connect(board.path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM intake_history").fetchone()[0] == 1


def test_missing_original_blocks_collection_and_download(client, monkeypatch):
    item = upload(client, [("synthetic.txt", b"synthetic")]).json()["results"][0]["item"]
    monkeypatch.setattr(FileLibraryStore, "resolve_path", lambda *_: None)
    assert (
        client.get("/api/task-board/intake/original/" + item["id"], headers=headers()).status_code
        == 409
    )
    response = client.post(
        "/api/task-board/intake/collect",
        headers=headers(),
        json={"items": [{"id": item["id"], "revision": 1, "category": "Synthetic"}]},
    )
    assert response.status_code == 409
    assert listed(client)[0]["status"] == "pending"

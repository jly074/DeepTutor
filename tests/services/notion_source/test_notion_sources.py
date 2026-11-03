"""Synthetic-only Notion transport, local source versions and scope tests."""

import asyncio
from dataclasses import replace
import json
import sqlite3

from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
import httpx
import pytest

from deeptutor.api.routers import notion_sources
from deeptutor.api.routers.auth import _install_request_workspace
from deeptutor.multi_user.models import CurrentUser, UserScope
from deeptutor.multi_user.paths import user_context
from deeptutor.services.notion_source.client import (
    DEMO_PAGE,
    DEMO_SOURCE,
    VERSION,
    DemoNotionClient,
    NotionClient,
    NotionFailure,
)
from deeptutor.services.notion_source.service import NotionSources, get_notion_sources
from deeptutor.services.workspace.context import workspace_context
from tests.services.workspace.test_data_scope import account as account


@pytest.fixture
def api(account):
    async def scoped(request: Request):
        _install_request_workspace(request)

    app = FastAPI(dependencies=[Depends(scoped)])
    app.include_router(notion_sources.router, prefix="/api/notion-sources")
    with TestClient(app) as client:
        yield client


def test_http_opt_in_import_idempotent_reload_and_workspace_isolation(account, api):
    a = account.create_workspace("Synthetic A")["workspace_id"]
    b = account.create_workspace("Synthetic B")["workspace_id"]
    params = {"mode": "demo", "dt_workspace": a}
    assert (
        api.get("/api/notion-sources", params={"dt_workspace": a}).json()["state"]
        == "not_configured"
    )
    assert api.post("/api/notion-sources/schema", params=params, json={}).status_code == 422
    schema = api.post("/api/notion-sources/schema", params=params, json={"consent": True}).json()[
        "properties"
    ]
    assert next(p for p in schema if p["id"] == "formula")["supported"] is False
    body = {"consent": True, "property_ids": ["title", "mastery", "status"]}
    row = api.post("/api/notion-sources/preview", params=params, json=body).json()["rows"][0]
    assert "notes" not in row["fields"] and row["fields"]["mastery"]["value"] == 42
    payload = {
        **body,
        "page_id": row["page_id"],
        "fingerprint": row["fingerprint"],
        "account_id": "forged-user",
    }
    one = api.post("/api/notion-sources/snapshots", params=params, json=payload)
    two = api.post("/api/notion-sources/snapshots", params=params, json=payload)
    assert one.status_code == 200 and one.json() == two.json()
    assert one.json()["available"] is False and one.json()["source_id"] == "notion:" + DEMO_PAGE
    assert one.json()["metadata"]["fields"]["status"]["value"] == "Read, not assessed"
    assert api.get("/api/notion-sources", params=params).json()["sources"] == [one.json()]
    assert (
        api.get("/api/notion-sources", params={"mode": "demo", "dt_workspace": b}).json()["sources"]
        == []
    )
    assert (
        api.get("/api/notion-sources", params={"mode": "live", "dt_workspace": a}).json()["sources"]
        == []
    )
    with workspace_context(a):
        service = get_notion_sources("demo")
        assert service.saved()[0].id == one.json()["id"]
        with sqlite3.connect(service.path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM notion_source_snapshots").fetchone()[0] == 1


def test_changed_source_requires_review_and_keeps_old_versions(account):
    service = get_notion_sources("demo")
    before = asyncio.run(service.preview(["title", "mastery"]))["rows"][0]
    first = asyncio.run(
        service.import_row(before.page_id, ["title", "mastery"], before.fingerprint)
    )
    original = service.client.page

    async def changed(*args):
        row = await original(*args)
        row["last_edited_time"] = "2026-01-02T00:00:00.000Z"
        row["properties"]["Mastery"]["number"] = 73
        return row

    service.client.page = changed
    with pytest.raises(NotionFailure, match="source_changed"):
        asyncio.run(service.import_row(before.page_id, ["title", "mastery"], before.fingerprint))
    fresh = asyncio.run(service.preview(["title", "mastery"]))["rows"][0]
    second = asyncio.run(service.import_row(fresh.page_id, ["title", "mastery"], fresh.fingerprint))
    assert second.id == first.id and second.source_id == first.source_id
    with sqlite3.connect(service.path) as conn:
        rows = conn.execute(
            "SELECT source_json FROM notion_source_snapshots ORDER BY seq"
        ).fetchall()
    assert [json.loads(r[0])["metadata"]["fields"]["mastery"]["value"] for r in rows] == [42, 73]
    assert service.saved()[0].metadata["fields"]["mastery"]["value"] == 73


def test_service_cannot_be_reused_across_account_or_workspace(account, tmp_path):
    service = get_notion_sources("demo")
    other = account.create_workspace("Other")["workspace_id"]
    with workspace_context(other):
        with pytest.raises(NotionFailure, match="access_denied"):
            service.saved()
    user = CurrentUser("other", "other", "user", UserScope("user", "other", tmp_path / "other"))
    with user_context(user):
        with pytest.raises(NotionFailure, match="access_denied"):
            asyncio.run(service.schema())


def test_bound_configuration_and_no_anonymous_access(account, monkeypatch, tmp_path):
    from deeptutor.multi_user.context import get_current_user

    monkeypatch.setenv("DEEPTUTOR_NOTION_OWNER_ID", "someone-else")
    monkeypatch.setenv("DEEPTUTOR_NOTION_WORKSPACE_ID", "")
    monkeypatch.setenv("DEEPTUTOR_NOTION_DATA_SOURCE_ID", DEMO_SOURCE)
    monkeypatch.setenv("DEEPTUTOR_NOTION_READ_TOKEN", "SYNTHETIC_ONLY")
    assert get_notion_sources().state == "not_configured"
    assert get_notion_sources().binding.source == ""
    monkeypatch.setenv("DEEPTUTOR_NOTION_OWNER_ID", get_current_user().scope.user_id)
    assert get_notion_sources().state == "configured_not_verified"
    user = CurrentUser(
        "local-admin", "local", "admin", UserScope("admin", "local-admin", tmp_path / "anon")
    )
    monkeypatch.setenv("DEEPTUTOR_NOTION_OWNER_ID", "local-admin")
    with user_context(user):
        assert get_notion_sources().state == "authentication_required"
        with pytest.raises(NotionFailure):
            asyncio.run(get_notion_sources().schema())


def wire_schema():
    return {
        "object": "data_source",
        "id": DEMO_SOURCE,
        "properties": {
            "Topic": {"id": "title", "type": "title"},
            "Mastery": {"id": "mastery", "type": "number"},
            "SecretNotes": {"id": "notes", "type": "rich_text"},
        },
    }


def live_service(account, handler):
    demo = get_notion_sources("demo")
    return NotionSources(
        demo.path,
        replace(demo.binding, simulated=False),
        NotionClient("SYNTHETIC_ONLY_TOKEN", DEMO_SOURCE, httpx.MockTransport(handler)),
    )


def test_real_adapter_uses_only_fixed_read_endpoints_and_selected_ids(account):
    record = asyncio.run(DemoNotionClient().page(DEMO_PAGE, ["title", "mastery"]))
    calls = []

    def handler(req):
        calls.append(req)
        assert req.headers["Notion-Version"] == VERSION
        assert req.headers["Authorization"] == "Bearer SYNTHETIC_ONLY_TOKEN"
        assert req.url.host == "api.notion.com"
        if req.method == "GET":
            assert req.url.path == "/v1/data_sources/" + DEMO_SOURCE
            return httpx.Response(200, json=wire_schema())
        assert req.method == "POST" and req.url.path == "/v1/data_sources/" + DEMO_SOURCE + "/query"
        assert req.url.params.get_list("filter_properties") == ["title", "mastery"]
        assert json.loads(req.content)["page_size"] == 25
        return httpx.Response(
            200,
            json={"object": "list", "results": [record], "has_more": False, "next_cursor": None},
        )

    service = live_service(account, handler)
    row = asyncio.run(service.preview(["title", "mastery"]))["rows"][0]
    result = asyncio.run(service.import_row(row.page_id, ["title", "mastery"], row.fingerprint))
    assert result.metadata["simulated"] is False  # transport is doubled, adapter is live
    assert result.metadata["fields"]["mastery"]["value"] == 42
    assert len(calls) == 4
    with pytest.raises(NotionFailure):
        asyncio.run(service.client._read("PATCH", "pages/" + DEMO_PAGE))
    assert len(calls) == 4


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "needs_authorization"),
        (403, "access_denied"),
        (404, "missing_or_unshared"),
        (429, "rate_limited"),
        (500, "unavailable"),
        (302, "unavailable"),
    ],
)
def test_provider_errors_redacted_and_not_retried(account, status, code):
    calls = []
    service = live_service(
        account,
        lambda req: calls.append(req) or httpx.Response(status, text="SYNTHETIC_PRIVATE_ERROR"),
    )
    with pytest.raises(NotionFailure, match=code) as error:
        asyncio.run(service.schema())
    assert "PRIVATE" not in str(error.value) and len(calls) == 1
    assert service.saved() == []


def test_timeout_safe(account):
    def handler(req):
        raise httpx.ReadTimeout("SYNTHETIC_PRIVATE_ERROR")

    with pytest.raises(NotionFailure, match="timeout"):
        asyncio.run(live_service(account, handler).schema())


@pytest.mark.parametrize(
    "selected", [[], ["mastery"], ["title", "formula"], ["title", "unknown"], ["title", "title"]]
)
def test_invalid_field_selection_rejected(account, selected):
    with pytest.raises(NotionFailure):
        asyncio.run(get_notion_sources("demo").preview(selected))


def test_truncated_property_blocks_import_without_mastery_guess(account):
    service = get_notion_sources("demo")
    original = service.client.page

    async def partial(*args):
        row = await original(*args)
        row["properties"]["Topic"]["title"] = [{"plain_text": "x"}] * 25
        return row

    service.client.page = partial
    row = asyncio.run(service.preview(["title"]))["rows"][0]
    assert row.issues == ["title"]
    with pytest.raises(NotionFailure, match="incomplete_properties"):
        asyncio.run(service.import_row(row.page_id, ["title"], row.fingerprint))
    assert service.saved() == []


@pytest.mark.parametrize(
    "change",
    [
        {"has_more": True, "next_cursor": None},
        {"has_more": True, "next_cursor": "same"},
        {"request_status": {"type": "incomplete"}},
    ],
)
def test_incomplete_or_repeated_cursor_is_not_presented_as_complete(account, change):
    service = get_notion_sources("demo")

    async def query(*args):
        return {"object": "list", "results": [], "has_more": False, "next_cursor": None, **change}

    service.client.query = query
    with pytest.raises(NotionFailure):
        asyncio.run(service.preview(["title"], "same"))


def test_foreign_parent_and_disappeared_rows_do_not_erase_snapshots(account):
    service = get_notion_sources("demo")
    row = asyncio.run(service.preview(["title"]))["rows"][0]
    saved = asyncio.run(service.import_row(row.page_id, ["title"], row.fingerprint))

    async def missing(*args):
        return {"object": "list", "results": [], "has_more": False, "next_cursor": None}

    service.client.query = missing
    with pytest.raises(NotionFailure, match="row_moved_or_missing"):
        asyncio.run(service.import_row(row.page_id, ["title"], row.fingerprint))
    assert service.saved()[0].id == saved.id


def test_untrusted_source_id_cannot_change_fixed_host():
    with pytest.raises(NotionFailure):
        NotionClient("SYNTHETIC", "https://evil.example/id")


def test_foreign_parent_is_rejected(account):
    service = get_notion_sources("demo")
    original = service.client.page

    async def foreign(*args):
        row = await original(*args)
        row["parent"]["data_source_id"] = "33333333-3333-4333-8333-333333333333"
        return row

    service.client.page = foreign
    with pytest.raises(NotionFailure):
        asyncio.run(service.preview(["title"]))
    assert service.saved() == []


def test_cursor_forwarded_and_missing_property_blocks_import(account):
    service = get_notion_sources("demo")
    original = service.client.page

    async def query(selected, cursor):
        assert cursor == "opaque-next"
        row = await original(DEMO_PAGE, selected)
        row["properties"].pop("Mastery")
        return {"object": "list", "results": [row], "has_more": False, "next_cursor": None}

    service.client.query = query
    row = asyncio.run(service.preview(["title", "mastery"], "opaque-next"))["rows"][0]
    assert row.issues == ["mastery"]
    with pytest.raises(NotionFailure, match="incomplete_properties"):
        asyncio.run(
            service.import_row(row.page_id, ["title", "mastery"], row.fingerprint, "opaque-next")
        )

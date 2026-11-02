"""Synthetic-only metadata transport, scope and durable-reference acceptance."""

import asyncio
from dataclasses import replace
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
import httpx
import pytest

from deeptutor.api.routers import drive_sources
from deeptutor.api.routers.auth import _install_request_workspace
from deeptutor.learning.topic_materials import build_topic_materials
from deeptutor.multi_user.models import CurrentUser, UserScope
from deeptutor.multi_user.paths import user_context
from deeptutor.services.drive_source.client import (
    FOLDER,
    SHORTCUT,
    DemoDriveClient,
    DriveFailure,
    DriveFile,
    DrivePage,
    GoogleDriveClient,
)
from deeptutor.services.drive_source.service import DriveSources, get_drive_sources
from deeptutor.services.workspace.context import workspace_context
from tests.services.workspace.test_data_scope import account as account


@pytest.fixture
def client(account):
    async def select(request: Request):
        _install_request_workspace(request)

    app = FastAPI(dependencies=[Depends(select)])
    app.include_router(drive_sources.router, prefix="/api/drive-sources")
    with TestClient(app) as client:
        yield client


def test_http_demo_save_reload_workspace_boundaries_and_live_disconnected(account, client):
    a = account.create_workspace("A")["workspace_id"]
    b = account.create_workspace("B")["workspace_id"]
    base = "/api/drive-sources"
    headers = {"X-DeepTutor-Workspace": a}
    real = client.get(base, headers=headers).json()
    assert real == {
        "state": "not_connected",
        "simulated": False,
        "allowed_folders": [],
        "sources": [],
    }
    listed = client.get(base + "/files?mode=demo&folder_id=demo-course", headers=headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == ["demo-file-2", "demo-file-1"]
    body = {"folder_id": "demo-course", "file_id": "demo-file-1"}
    first = client.post(base + "/sources?mode=demo", headers=headers, json=body)
    again = client.post(base + "/sources?mode=demo", headers=headers, json=body)
    assert first.status_code == again.status_code == 200
    assert first.json()["id"] == again.json()["id"]
    saved = client.get(base + "?mode=demo", headers=headers).json()["sources"]
    assert len(saved) == 1 and saved[0]["available"] is False
    assert saved[0]["metadata"]["simulated"] is True
    assert (
        client.get(base + "?mode=demo", headers={"X-DeepTutor-Workspace": b}).json()["sources"]
        == []
    )
    assert client.get(base, headers=headers).json()["sources"] == []
    assert client.get(base, headers={"X-DeepTutor-Workspace": "ws_missing"}).status_code == 404
    assert client.get(base + f"?dt_workspace={b}", headers=headers).status_code == 400
    with workspace_context(a):
        reopened = get_drive_sources("demo")
        assert reopened.saved()[0].id == first.json()["id"]
        # Even an incorrectly marked available reference cannot reach a reader.
        source = reopened.saved()[0].model_copy(update={"available": True})
        materials = build_topic_materials([source])
        assert materials.source_index() == {}
        assert not materials.materials[0].readable


def test_account_isolation_and_captured_service_cannot_cross_scope(account, tmp_path):
    service = get_drive_sources("demo")
    asyncio.run(service.select("demo-course", "demo-file-1"))
    other = CurrentUser("other", "other", "user", UserScope("user", "other", tmp_path / "other"))
    with user_context(other):
        assert get_drive_sources("demo").saved() == []
        with pytest.raises(DriveFailure, match="access_denied"):
            service.saved()
    wid = account.create_workspace("Other scope")["workspace_id"]
    with workspace_context(wid), pytest.raises(DriveFailure, match="access_denied"):
        service.saved()


@pytest.mark.parametrize(
    "folder", ["x' or trashed=true", "../other", "https://evil.test", "a/b", "", "x" * 201]
)
def test_malicious_folder_rejected_without_client_calls(account, folder):
    class NoCalls:
        async def list_page(self, *args):
            pytest.fail("No request allowed")

    service = get_drive_sources("demo")
    service.client = NoCalls()
    with pytest.raises(DriveFailure, match="invalid_folder"):
        asyncio.run(service.listing(folder))


def test_allowlist_and_no_forged_selection(account, client):
    assert client.get("/api/drive-sources/files?mode=demo&folder_id=other").status_code == 403
    response = client.post(
        "/api/drive-sources/sources?mode=demo",
        json={"folder_id": "demo-course", "file_id": "not-listed"},
    )
    assert response.status_code == 404
    assert client.get("/api/drive-sources?mode=demo").json()["sources"] == []
    assert client.get("/api/drive-sources?mode=invalid").status_code == 422


def test_transport_exact_readonly_request_and_pagination(account):
    calls = []

    async def handler(request):
        calls.append(request)
        assert request.method == "GET"
        assert str(request.url).startswith("https://www.googleapis.com/drive/v3/files?")
        assert request.url.params["q"] == "'demo-course' in parents and trashed = false"
        assert "alt" not in request.url.params
        assert (
            request.url.params["fields"]
            == "nextPageToken,incompleteSearch,files(id,name,mimeType,parents,trashed,modifiedTime,version)"
        )
        page = await DemoDriveClient().list_page(
            "demo-course", request.url.params.get("pageToken", "")
        )
        # Real API tokens are opaque; demo's token verifies forwarding only.
        return httpx.Response(200, json=page.model_dump())

    service = get_drive_sources("demo")
    service.client = GoogleDriveClient(lambda: "synthetic-test-token", httpx.MockTransport(handler))
    assert len(asyncio.run(service.listing("demo-course"))) == 2
    assert len(calls) == 2
    assert calls[1].url.params["pageToken"] == "demo-page-2"


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "needs_authorization"),
        (403, "access_denied"),
        (404, "not_found"),
        (429, "rate_limited"),
        (500, "unavailable"),
        (302, "unavailable"),
    ],
)
def test_http_failures_are_bounded_redacted_and_do_not_erase_saved(account, status, code):
    service = get_drive_sources("demo")
    asyncio.run(service.select("demo-course", "demo-file-1"))
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="PRIVATE response and synthetic-test-token")

    service.client = GoogleDriveClient(lambda: "synthetic-test-token", httpx.MockTransport(handler))
    with pytest.raises(DriveFailure, match=code) as failure:
        asyncio.run(service.listing("demo-course"))
    assert "PRIVATE" not in str(failure.value)
    assert len(calls) == 1 and len(service.saved()) == 1


def test_timeout_and_no_token_do_not_retry(account):
    def timeout(request):
        raise httpx.ReadTimeout("PRIVATE URL", request=request)

    client = GoogleDriveClient(lambda: "synthetic-test-token", httpx.MockTransport(timeout))
    with pytest.raises(DriveFailure, match="timeout"):
        asyncio.run(client.list_page("demo-course"))
    client = GoogleDriveClient(lambda: None, httpx.MockTransport(lambda r: pytest.fail("no token")))
    with pytest.raises(DriveFailure, match="needs_authorization"):
        asyncio.run(client.list_page("demo-course"))


def test_folder_shortcuts_trashed_outside_items_not_followed(account):
    class Listing:
        async def list_page(self, *args):
            return DrivePage(
                files=[
                    DriveFile(id="folder", name="Folder", mimeType=FOLDER, parents=["demo-course"]),
                    DriveFile(
                        id="link", name="Shortcut", mimeType=SHORTCUT, parents=["demo-course"]
                    ),
                    DriveFile(
                        id="deleted",
                        name="Deleted",
                        mimeType="application/pdf",
                        parents=["demo-course"],
                        trashed=True,
                    ),
                    DriveFile(
                        id="outside",
                        name="Outside",
                        mimeType="application/pdf",
                        parents=["elsewhere"],
                    ),
                ]
            )

    service = get_drive_sources("demo")
    service.client = Listing()
    assert asyncio.run(service.listing("demo-course")) == []


@pytest.mark.parametrize("variant", ["cycle", "limit", "incomplete"])
def test_incomplete_or_unbounded_listing_fails_closed(account, variant):
    class Listing:
        calls = 0

        async def list_page(self, *args):
            self.calls += 1
            return DrivePage(
                nextPageToken="same" if variant == "cycle" else str(self.calls),
                incompleteSearch=variant == "incomplete",
            )

    service = get_drive_sources("demo")
    service.client = Listing()
    with pytest.raises(DriveFailure):
        asyncio.run(service.listing("demo-course"))
    assert service.client.calls <= 5
    assert service.saved() == []


def test_missing_authorization_and_transport_states(account):
    service = get_drive_sources("demo")
    service.connection = replace(service.connection, authorized=False, simulated=False)
    assert service.state == "needs_authorization"
    with pytest.raises(DriveFailure, match="needs_authorization"):
        asyncio.run(service.listing("demo-course"))
    service.connection = replace(service.connection, authorized=True)
    service.client = None
    assert service.state == "blocked"


@pytest.mark.parametrize(
    "method,path,expected",
    [
        ("GET", "/api/drive-sources", "reading"),
        ("GET", "/api/drive-sources/files", "reading"),
        ("POST", "/api/drive-sources/sources", "reading"),
        ("POST", "/api/drive-sources/login", ""),
        ("DELETE", "/api/drive-sources/sources", ""),
    ],
)
def test_only_metadata_routes_are_learner_surfaces(method, path, expected):
    from deeptutor.api.routers.auth import _learning_surface_for_path

    assert _learning_surface_for_path(path, method, route_path=path) == expected


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "needs_authorization"),
        (403, "access_denied"),
        (404, "not_found"),
        (429, "rate_limited"),
    ],
)
def test_api_errors_do_not_return_provider_payload(account, client, monkeypatch, status, code):
    service = get_drive_sources("demo")
    service.client = GoogleDriveClient(
        lambda: "synthetic-test-token",
        httpx.MockTransport(
            lambda request: httpx.Response(
                status, text="PRIVATE provider detail synthetic-test-token"
            )
        ),
    )
    monkeypatch.setattr(drive_sources, "get_drive_sources", lambda mode: service)
    response = client.get("/api/drive-sources/files?mode=demo&folder_id=demo-course")
    assert response.status_code == status
    assert response.json() == {
        "detail": {"state": "needs_authorization" if status == 401 else "blocked", "code": code}
    }
    assert "PRIVATE" not in response.text and "synthetic-test-token" not in response.text


def test_same_file_revision_updates_reference_without_duplicate(account):
    service = get_drive_sources("demo")
    first = asyncio.run(service.select("demo-course", "demo-file-1"))

    class Revised:
        async def list_page(self, *args):
            return DrivePage(
                files=[
                    DriveFile(
                        id="demo-file-1",
                        name="Renamed synthetic.pdf",
                        mimeType="application/pdf",
                        parents=["demo-course"],
                        version="3",
                    )
                ]
            )

    service.client = Revised()
    updated = asyncio.run(service.select("demo-course", "demo-file-1"))
    assert updated.id == first.id
    saved = get_drive_sources("demo").saved()
    assert len(saved) == 1 and saved[0].metadata["version"] == "3"
    assert saved[0].label == "Renamed synthetic.pdf"

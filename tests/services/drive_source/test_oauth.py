"""Synthetic Google HTTP transport + crypto double; never contact a real account."""

import asyncio
import base64
import hashlib
import json
import sqlite3
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from deeptutor.services.config import protected_settings
from deeptutor.services.drive_source.client import DriveFailure
from deeptutor.services.drive_source.oauth import SCOPE, TOKEN, DriveOAuth, OAuthConfig, OAuthStore
from tests.services.workspace.test_data_scope import account as account

ORIGIN = "http://127.0.0.1:3784"
NONCE = "synthetic-tab-nonce-" + "a" * 32


@pytest.fixture
def flow(tmp_path, monkeypatch):
    monkeypatch.setattr(protected_settings, "available", lambda: True)
    # This reversal is not encryption: it only verifies envelope/storage plumbing.
    monkeypatch.setattr(protected_settings, "_crypt", lambda data, decrypt=False: data[::-1])
    return DriveOAuth(
        OAuthStore(tmp_path / "oauth.sqlite3", "owner-a", "workspace-a"),
        OAuthConfig(
            "synthetic.apps.googleusercontent.com",
            "SYNTHETIC_CLIENT_SECRET",
            ORIGIN + "/drive-oauth-callback",
        ),
        clock=lambda: 1000,
    )


def response(**changes):
    return {
        "access_token": "SYNTHETIC_ACCESS",
        "token_type": "Bearer",
        "expires_in": 3600,
        "scope": SCOPE,
        **changes,
    }


def authorize(flow, handler=None):
    flow.transport = httpx.MockTransport(
        handler or (lambda req: httpx.Response(200, json=response()))
    )
    result = flow.start("folder-stable-id", NONCE, ORIGIN)
    return result["state"]


def complete(flow, state, **kwargs):
    return asyncio.run(
        flow.complete(
            state,
            kwargs.get("nonce", NONCE),
            "SYNTHETIC_CODE",
            kwargs.get("error", ""),
            kwargs.get("origin", ORIGIN),
        )
    )


def test_pkce_online_only_encrypted_restart_and_redacted_status(flow):
    sent = []
    state = authorize(
        flow,
        lambda req: (
            sent.append(req)
            or httpx.Response(200, json=response(refresh_token="DO_NOT_STORE_REFRESH"))
        ),
    )
    pending = flow.store.read()["pending"]
    # A second start supersedes the first and exposes no secret in its URL.
    start = flow.start("folder-stable-id", NONCE, ORIGIN)
    query = parse_qs(urlsplit(start["authorization_url"]).query)
    verifier = flow.store.read()["pending"]["verifier"]
    assert query["code_challenge"] == [
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    ]
    assert query["scope"] == [SCOPE] and query["access_type"] == ["online"]
    assert "client_secret" not in query and "code_verifier" not in query
    with pytest.raises(DriveFailure):
        complete(flow, state)
    assert complete(flow, start["state"])["state"] == "connected"
    assert str(sent[0].url) == TOKEN
    assert parse_qs(sent[0].content.decode())["code_verifier"] == [verifier]
    reopened = DriveOAuth(
        OAuthStore(flow.store.path, "owner-a", "workspace-a"), flow.settings, clock=lambda: 1000
    )
    assert reopened.token() == "SYNTHETIC_ACCESS"
    assert "SYNTHETIC_ACCESS" not in json.dumps(reopened.status())
    assert "refresh_token" not in reopened.store.read()
    assert b"SYNTHETIC_ACCESS" not in flow.store.path.read_bytes()
    assert pending["verifier"].encode() not in flow.store.path.read_bytes()


@pytest.mark.parametrize(
    "change", ["state", "nonce", "origin", "expired", "workspace", "owner", "config"]
)
def test_callback_binding_blocks_before_network(flow, change):
    calls = []
    state = authorize(flow, lambda req: calls.append(req))
    kwargs = {}
    if change == "state":
        state = "wrong"
    if change == "nonce":
        kwargs["nonce"] = "b" * 64
    if change == "origin":
        kwargs["origin"] = "https://untrusted.example"
    if change == "expired":
        flow.clock = lambda: 2000
    if change == "workspace":
        flow.store.workspace = "workspace-b"
    if change == "owner":
        flow.store.owner = "owner-b"
    if change == "config":
        flow.settings.client_id = "other.apps.googleusercontent.com"
    with pytest.raises(DriveFailure):
        complete(flow, state, **kwargs)
    assert calls == []


def test_replay_and_denied_consent_never_exchange(flow):
    calls = []
    state = authorize(flow, lambda req: calls.append(req))
    with pytest.raises(DriveFailure, match="consent_denied"):
        complete(flow, state, error="access_denied")
    with pytest.raises(DriveFailure, match="invalid_callback"):
        complete(flow, state)
    assert calls == [] and flow.token() is None


def test_concurrent_callback_exchanges_once(flow):
    calls = []
    state = authorize(flow, lambda req: calls.append(req) or httpx.Response(200, json=response()))

    async def run():
        return await asyncio.gather(
            *(flow.complete(state, NONCE, "synthetic-code", "", ORIGIN) for _ in range(2)),
            return_exceptions=True,
        )

    result = asyncio.run(run())
    assert len(calls) == 1
    assert sum(isinstance(x, DriveFailure) for x in result) == 1


def test_disconnect_during_exchange_cannot_resurrect_authorization(flow):
    def handler(req):
        flow.disconnect(ORIGIN)
        return httpx.Response(200, json=response())

    state = authorize(flow, handler)
    with pytest.raises(DriveFailure, match="superseded_authorization"):
        complete(flow, state)
    assert flow.token() is None


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 302])
def test_exchange_failure_safe_and_not_retried(flow, status):
    calls = []
    state = authorize(
        flow, lambda req: calls.append(req) or httpx.Response(status, text="SYNTHETIC_SECRET_ERROR")
    )
    with pytest.raises(DriveFailure) as e:
        complete(flow, state)
    assert "SECRET" not in str(e.value) and len(calls) == 1 and flow.token() is None
    with pytest.raises(DriveFailure):
        complete(flow, state)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"scope": ""},
        {"scope": SCOPE + " https://www.googleapis.com/auth/drive"},
        {"expires_in": True},
        {"expires_in": 0},
        {"access_token": ""},
        {"token_type": "mac"},
    ],
)
def test_bad_token_response_not_saved(flow, change):
    state = authorize(flow, lambda req: httpx.Response(200, json=response(**change)))
    with pytest.raises(DriveFailure):
        complete(flow, state)
    assert flow.token() is None


def test_timeout_consumed_safe(flow):
    def handler(req):
        raise httpx.ReadTimeout("SYNTHETIC_SECRET_ERROR")

    state = authorize(flow, handler)
    with pytest.raises(DriveFailure, match="exchange_failed"):
        complete(flow, state)
    assert not flow.store.read().get("pending")


def test_expiry_and_forget_local(flow):
    complete(flow, authorize(flow))
    flow.clock = lambda: 5000
    assert flow.status()["state"] == "needs_authorization" and flow.token() is None
    flow.disconnect(ORIGIN)
    assert flow.store.read() == {}


def test_unconfigured_and_unsupported_never_write(flow, monkeypatch):
    flow.settings = OAuthConfig()
    assert flow.status()["state"] == "not_configured"
    with pytest.raises(DriveFailure):
        flow.start("id", NONCE, ORIGIN)
    assert not flow.store.path.exists()
    flow.settings = OAuthConfig(
        "synthetic.apps.googleusercontent.com", "synthetic", ORIGIN + "/drive-oauth-callback"
    )
    monkeypatch.setattr(protected_settings, "available", lambda: False)
    assert flow.status()["state"] == "storage_unavailable"
    with pytest.raises(DriveFailure):
        flow.start("id", NONCE, ORIGIN)
    assert not flow.store.path.exists()


@pytest.mark.parametrize(
    "uri",
    [
        "http://evil.example/drive-oauth-callback",
        "https://good.example/wrong",
        "https://good.example/drive-oauth-callback?next=evil",
        "https://user:pass@good.example/drive-oauth-callback",
        "http://[bad",
    ],
)
def test_invalid_redirect_config_rejected(uri):
    assert not OAuthConfig("synthetic.apps.googleusercontent.com", "synthetic", uri).valid


def test_folder_injection_rejected(flow):
    with pytest.raises(DriveFailure):
        flow.start("x' or trashed=true", NONCE, ORIGIN)
    assert not flow.store.path.exists()


def test_swapping_encrypted_rows_cannot_cross_owner_workspace(flow):
    flow.start("id", NONCE, ORIGIN)
    with sqlite3.connect(flow.store.path) as c:
        c.execute("UPDATE drive_oauth SET owner='owner-b'")
    flow.store.owner = "owner-b"
    with pytest.raises(DriveFailure, match="storage_unavailable"):
        flow.store.read()


def test_encryption_failure_never_falls_back(flow, monkeypatch):
    flow.start("id", NONCE, ORIGIN)
    before = flow.store.path.read_bytes()

    def fail(*a, **kw):
        raise protected_settings.ProtectionError("safe")

    monkeypatch.setattr(protected_settings, "_crypt", fail)
    with pytest.raises(DriveFailure):
        flow.store.write({"access_token": "SYNTHETIC"})
    assert flow.store.path.read_bytes() == before


def test_http_oauth_to_live_reference_persistence(account, monkeypatch):
    from fastapi import Depends, FastAPI, Request
    from fastapi.testclient import TestClient

    from deeptutor.api.routers import drive_sources
    from deeptutor.api.routers.auth import _install_request_workspace
    from deeptutor.services.drive_source import client as drive_client
    from deeptutor.services.drive_source import oauth
    from deeptutor.services.drive_source.service import get_drive_sources
    from deeptutor.services.workspace.context import workspace_context

    monkeypatch.setattr(protected_settings, "available", lambda: True)
    monkeypatch.setattr(protected_settings, "_crypt", lambda data, decrypt=False: data[::-1])
    monkeypatch.setattr(
        oauth,
        "config",
        lambda: OAuthConfig(
            "synthetic.apps.googleusercontent.com", "SYNTHETIC", ORIGIN + "/drive-oauth-callback"
        ),
    )
    original = oauth.get_drive_oauth
    calls = []

    def token_http(req):
        calls.append(str(req.url))
        return httpx.Response(200, json=response())

    def factory():
        service = original()
        service.transport = httpx.MockTransport(token_http)
        return service

    monkeypatch.setattr(oauth, "get_drive_oauth", factory)
    original_client = drive_client.GoogleDriveClient

    def metadata(req):
        calls.append(str(req.url))
        assert req.headers["Authorization"] == "Bearer SYNTHETIC_ACCESS"
        return httpx.Response(
            200,
            json={
                "files": [
                    {
                        "id": "file-stable-id",
                        "name": "Synthetic.pdf",
                        "mimeType": "application/pdf",
                        "parents": ["folder-stable-id"],
                    }
                ]
            },
        )

    monkeypatch.setattr(
        drive_client,
        "GoogleDriveClient",
        lambda token, **kwargs: original_client(token, httpx.MockTransport(metadata), **kwargs),
    )

    async def select(request: Request):
        _install_request_workspace(request)

    app = FastAPI(dependencies=[Depends(select)])
    app.include_router(drive_sources.router, prefix="/api/drive-sources")
    a = account.create_workspace("Synthetic A")["workspace_id"]
    b = account.create_workspace("Synthetic B")["workspace_id"]
    with TestClient(app, headers={"Origin": ORIGIN}) as client:
        params = {"dt_workspace": a}
        start = client.post(
            "/api/drive-sources/oauth/start",
            params=params,
            json={
                "folder_id": "folder-stable-id",
                "browser_nonce": NONCE,
                "consent": True,
                "account_id": "forged-account",
            },
        )
        assert start.status_code == 200
        payload = {"state": start.json()["state"], "browser_nonce": NONCE, "code": "SYNTHETIC_CODE"}
        assert (
            client.post(
                "/api/drive-sources/oauth/complete", params={"dt_workspace": b}, json=payload
            ).status_code
            == 400
        )
        assert calls == []
        assert (
            client.post(
                "/api/drive-sources/oauth/complete", params=params, json=payload
            ).status_code
            == 200
        )
        saved = client.post(
            "/api/drive-sources/sources",
            params=params,
            json={"folder_id": "folder-stable-id", "file_id": "file-stable-id"},
        )
        assert saved.status_code == 200 and saved.json()["available"] is False
        assert saved.json()["metadata"]["simulated"] is False  # real adapter, HTTP doubled
        source_id = saved.json()["id"]
        assert (
            client.get("/api/drive-sources", params=params).json()["sources"][0]["id"] == source_id
        )
        assert client.get("/api/drive-sources", params={"dt_workspace": b}).json()["sources"] == []
        count = len(calls)
        assert (
            client.get(
                "/api/drive-sources/files", params={**params, "folder_id": "not-allowed"}
            ).status_code
            == 403
        )
        assert len(calls) == count
        assert client.post("/api/drive-sources/oauth/disconnect", params=params).status_code == 200
        assert (
            client.get("/api/drive-sources", params=params).json()["sources"][0]["id"] == source_id
        )
    with workspace_context(a):
        assert get_drive_sources().saved()[0].id == source_id


def test_provider_401_invalidates_only_the_matching_grant(flow):
    from deeptutor.services.drive_source.client import GoogleDriveClient

    complete(flow, authorize(flow))
    identity = flow.store.read()["connection_id"]
    client = GoogleDriveClient(
        flow.token,
        httpx.MockTransport(lambda r: httpx.Response(401)),
        on_unauthorized=lambda: flow.store.invalidate(identity),
    )
    with pytest.raises(DriveFailure, match="needs_authorization"):
        asyncio.run(client.list_page("folder-stable-id"))
    assert flow.status()["state"] == "needs_authorization"
    complete(flow, authorize(flow))
    flow.store.invalidate(identity)
    assert flow.status()["state"] == "connected"


def test_anonymous_local_mode_cannot_authorize_or_read_tokens(flow):
    complete(flow, authorize(flow))
    flow.authenticated = False
    assert flow.status()["state"] == "authentication_required"
    with pytest.raises(DriveFailure):
        flow.start("id", NONCE, ORIGIN)
    with pytest.raises(DriveFailure):
        flow.token()
    with pytest.raises(DriveFailure):
        flow.disconnect(ORIGIN)


def test_factory_blocks_default_shared_identity(tmp_path, monkeypatch):
    from deeptutor.multi_user.models import CurrentUser, UserScope
    from deeptutor.multi_user.paths import user_context
    from deeptutor.services.drive_source import oauth

    monkeypatch.setattr(
        oauth,
        "config",
        lambda: OAuthConfig(
            "synthetic.apps.googleusercontent.com", "SYNTHETIC", ORIGIN + "/drive-oauth-callback"
        ),
    )
    user = CurrentUser("local-admin", "local", "admin", UserScope("admin", "local-admin", tmp_path))
    with user_context(user):
        service = oauth.get_drive_oauth()
        assert service.status()["state"] == "authentication_required"
        with pytest.raises(DriveFailure):
            service.start("id", NONCE, ORIGIN)
        assert not service.store.path.exists()

"""HTTP routes with synthetic stores and crypto double; no real account access."""

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from deeptutor.api.routers import settings
from deeptutor.services.config import protected_settings as protection
from deeptutor.services.config.model_catalog import ModelCatalogService
from deeptutor.services.config.settings_draft import SettingsDraftService


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "get_current_user", lambda: SimpleNamespace(is_admin=True))
    monkeypatch.setattr(
        settings,
        "get_model_catalog_service",
        lambda: ModelCatalogService.get_instance(tmp_path / "model_catalog.json"),
    )
    monkeypatch.setattr(
        settings,
        "get_settings_draft_service",
        lambda: SettingsDraftService.get_instance(tmp_path / "settings_draft.json"),
    )
    app = FastAPI()
    app.include_router(settings.router, prefix="/api/settings")
    return TestClient(app)


def test_non_admin_cannot_inspect_or_protect_inherited_catalog(client, monkeypatch):
    monkeypatch.setattr(settings, "get_current_user", lambda: SimpleNamespace(is_admin=False))
    assert client.get("/api/settings/credential-storage").status_code == 403
    assert (
        client.post("/api/settings/credential-storage/protect", json={"account_id": "admin"}).status_code == 403
    )


def test_protect_and_reload_status_do_not_expose_values(client, tmp_path, monkeypatch):
    monkeypatch.setattr(protection, "available", lambda: True)
    monkeypatch.setattr(protection, "_crypt", lambda data, decrypt=False: data[::-1])
    (tmp_path / "model_catalog.json").write_text('{"secret":"SYNTHETIC_ONLY"}')
    assert client.get("/api/settings/credential-storage").json()["enabled"] is False
    response = client.post("/api/settings/credential-storage/protect")
    assert response.status_code == 200
    assert client.get("/api/settings/credential-storage").json()["files"]["model_catalog.json"] == "protected"
    assert "SYNTHETIC_ONLY" not in response.text
    assert str(tmp_path) not in response.text


def test_unavailable_protection_is_safe_conflict(client, tmp_path, monkeypatch):
    monkeypatch.setattr(protection, "available", lambda: False)
    response = client.post("/api/settings/credential-storage/protect")
    assert response.status_code == 409
    assert list(tmp_path.iterdir()) == []


def test_mismatched_settings_owner_is_rejected(client, tmp_path, monkeypatch):
    monkeypatch.setattr(
        settings,
        "get_settings_draft_service",
        lambda: SettingsDraftService(tmp_path / "other" / "settings_draft.json"),
    )
    assert client.post("/api/settings/credential-storage/protect").status_code == 409
    assert list(tmp_path.iterdir()) == []

import json
import os
from pathlib import Path

import pytest

from deeptutor.services.config import protected_settings as protection
from deeptutor.services.config.model_catalog import ModelCatalogService
from deeptutor.services.config.settings_draft import SettingsDraftService


@pytest.fixture
def cipher(monkeypatch):
    # A transport double, not a claim that Windows DPAPI was exercised on Linux.
    monkeypatch.setattr(protection, "available", lambda: True)
    monkeypatch.setattr(protection, "_crypt", lambda data, decrypt=False: data[::-1])


def test_enable_protects_both_files_and_future_saves(tmp_path, cipher):
    catalog = ModelCatalogService(tmp_path / "model_catalog.json")
    draft = SettingsDraftService(tmp_path / "settings_draft.json")
    catalog.save({"connections": [], "services": {}})
    draft.save({"catalog": {"synthetic_secret": "SYNTHETIC_CREDENTIAL"}})
    before = (catalog.load(), draft.load())
    result = protection.enable(tmp_path)
    assert result["enabled"] and set(result["files"].values()) == {"protected"}
    assert (catalog.load(), draft.load()) == before
    for path in tmp_path.iterdir():
        assert "SYNTHETIC_CREDENTIAL" not in path.read_text()
    draft.save({"catalog": {"synthetic_secret": "SECOND_SYNTHETIC"}})
    assert "SECOND_SYNTHETIC" not in draft.path.read_text()
    assert draft.load()["catalog"]["synthetic_secret"] == "SECOND_SYNTHETIC"


def test_crypto_failure_preserves_existing_and_never_falls_back(tmp_path, cipher, monkeypatch):
    path = tmp_path / "settings_draft.json"
    draft = SettingsDraftService(path)
    draft.save({"catalog": {"secret": "SYNTHETIC"}})
    protection.enable(tmp_path)
    before = path.read_bytes()

    def fail(*args, **kwargs):
        raise protection.ProtectionError("Safe failure")

    monkeypatch.setattr(protection, "_crypt", fail)
    with pytest.raises(protection.ProtectionError):
        draft.load()
    with pytest.raises(protection.ProtectionError):
        draft.save({"catalog": {}})
    assert path.read_bytes() == before


def test_preflight_failure_does_not_modify_either_file(tmp_path, cipher):
    a, b = (tmp_path / name for name in protection.FILES)
    a.write_text('{"secret":"SYNTHETIC"}')
    b.write_text("not-json")
    with pytest.raises(protection.ProtectionError):
        protection.enable(tmp_path)
    assert a.read_text() == '{"secret":"SYNTHETIC"}'
    assert b.read_text() == "not-json"
    assert not (tmp_path / protection.MARKER).exists()


def test_partial_replace_can_be_retried_without_plaintext_temp(tmp_path, cipher, monkeypatch):
    for name in protection.FILES:
        (tmp_path / name).write_text('{"secret":"SYNTHETIC"}')
    original = protection._atomic
    calls = 0

    def fail_second(path, value):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic interruption")
        return original(path, value)

    monkeypatch.setattr(protection, "_atomic", fail_second)
    with pytest.raises(OSError):
        protection.enable(tmp_path)
    assert not (tmp_path / protection.MARKER).exists()
    assert (
        protection.decode(json.loads((tmp_path / protection.FILES[0]).read_text()))["secret"]
        == "SYNTHETIC"
    )
    monkeypatch.setattr(protection, "_atomic", original)
    assert protection.enable(tmp_path)["enabled"]


def test_missing_marker_does_not_downgrade_encrypted_file(tmp_path, cipher):
    path = tmp_path / "model_catalog.json"
    path.write_text(json.dumps(protection.encode({"secret": "SYNTHETIC"}, path, force=True)))
    assert protection.encode({"secret": "new"}, path)["protected_format"] == protection.FORMAT


def test_unsupported_host_does_not_change_files(tmp_path, monkeypatch):
    monkeypatch.setattr(protection, "available", lambda: False)
    with pytest.raises(protection.ProtectionError):
        protection.enable(tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(os.name != "nt", reason="Real Windows DPAPI requires Windows")
def test_real_windows_dpapi_roundtrip():
    secret = b"SYNTHETIC_ONLY_TEST"
    encrypted = protection._crypt(secret)
    assert secret not in encrypted
    assert protection._crypt(encrypted, decrypt=True) == secret


@pytest.mark.parametrize("name", protection.FILES)
def test_truncated_protected_settings_are_preserved(tmp_path, cipher, name):
    (tmp_path / protection.MARKER).write_text("{}")
    path = tmp_path / name
    path.write_text('{"protected_format":')
    service = (
        ModelCatalogService(path) if name == "model_catalog.json" else SettingsDraftService(path)
    )
    with pytest.raises(protection.ProtectionError):
        service.load()
    assert path.read_text() == '{"protected_format":'

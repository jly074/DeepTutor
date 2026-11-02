"""Fourth-round review fixes: local Git fixtures and controlled supervisor faults."""

import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
from types import SimpleNamespace

import psutil
import pytest

from tests.scripts.test_learning_trial import repos as repos
from tests.scripts.test_learning_trial import trial as trial


@pytest.mark.parametrize("stage", ["start", "deps"])
def test_noop_update_cannot_clear_deps_or_start_failure(trial, repos, tmp_path, monkeypatch, stage):
    _, local = repos
    home = tmp_path / "home"
    trial.configure(local, "trial", home)
    monkeypatch.setattr(trial, "require_tools", lambda: None)
    python = home / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python.parent.mkdir(parents=True)
    python.touch()
    sha = trial.Git(local).run(["rev-parse", "HEAD"]).stdout
    (home / "dependencies.json").write_text(json.dumps({"commit": sha}))

    def fail(*args):
        raise subprocess.CalledProcessError(7, "synthetic")

    monkeypatch.setattr(trial, "execute_supervised", fail)
    monkeypatch.setattr(trial, "execute", fail)
    with pytest.raises(subprocess.CalledProcessError):
        trial.lifecycle(local, stage)
    trial.lifecycle(local, "update")  # no new commits; must only clear update stage
    marker = local / ".git/learning-trial-failure.json"
    assert stage in trial.read_failures(marker)
    with pytest.raises(trial.UpdateError, match=f"Previous {stage}"):
        trial.lifecycle(local, "start")
    monkeypatch.setattr(trial, "execute", lambda *args: None)
    trial.lifecycle(local, "deps")  # mocked installation, genuine state transitions
    assert not marker.exists()
    monkeypatch.setattr(trial, "execute_supervised", lambda *args: None)
    trial.lifecycle(local, "start")


def test_legacy_failure_migrates_without_losing_gate(trial, repos, tmp_path):
    _, local = repos
    trial.configure(local, "trial", tmp_path / "home")
    marker = local / ".git/learning-trial-failure.json"
    marker.write_text('{"action":"start","state":"pending_or_failed"}')
    trial.lifecycle(local, "update")
    assert json.loads(marker.read_text()) == {"stages": {"start": "pending_or_failed"}}


@pytest.fixture
def worker():
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "trial_worker_repair", root / "scripts/learning_trial_worker.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_process(worker, monkeypatch, *, code, cancels=0, cleanup_error=None):
    process = SimpleNamespace(pid=99999999, returncode=code, poll=lambda: code)
    force_seen = []

    def spawn(*args, **kwargs):
        for _ in range(cancels):
            signal.getsignal(signal.SIGINT)(signal.SIGINT, None)
        return SimpleNamespace(process=process)

    def missing(pid):
        raise psutil.NoSuchProcess(pid)

    def cleanup(processes, *, force):
        force_seen.append(force.is_set())
        if cleanup_error:
            raise cleanup_error

    monkeypatch.setattr(worker.launcher, "_spawn", spawn)
    monkeypatch.setattr(worker.launcher, "_terminate_all", cleanup)
    monkeypatch.setattr(psutil, "Process", missing)
    return force_seen


def test_cancel_plus_exit7_keeps_failure(worker, monkeypatch, tmp_path):
    fake_process(worker, monkeypatch, code=7, cancels=1)
    guard = tmp_path / "guard"
    assert worker.supervise([], tmp_path, {}, guard) == 7
    assert not guard.exists()


def test_repeated_cancel_is_130_and_forces_cleanup(worker, monkeypatch, tmp_path):
    seen = fake_process(worker, monkeypatch, code=0, cancels=2)
    guard = tmp_path / "guard"
    assert worker.supervise([], tmp_path, {}, guard) == 130
    assert seen == [True]
    assert not guard.exists()


def test_cleanup_exception_retains_exit7_diagnostics_and_lock(worker, trial, monkeypatch, tmp_path):
    cleanup_error = OSError("synthetic cleanup error")
    fake_process(worker, monkeypatch, code=7, cleanup_error=cleanup_error)
    guard = tmp_path / "learning-trial-cleanup-pending"
    lock = tmp_path / "learning-trial.lock"
    with pytest.raises(worker.SupervisionFailure) as caught:
        with trial.exclusive(lock):
            worker.supervise([], tmp_path, {}, guard)
    assert caught.value.exit_code == 7
    assert caught.value.cleanup_error is cleanup_error
    assert caught.value.__cause__ is cleanup_error
    assert json.loads(guard.read_text())["original_exit"] == 7
    assert json.loads(guard.read_text())["cleanup_error"] == "OSError"
    assert lock.exists()


def test_guard_write_failure_restores_signal_handlers(worker, tmp_path):
    sigs = [getattr(signal, n) for n in ("SIGINT", "SIGTERM", "SIGBREAK") if hasattr(signal, n)]
    before = {sig: signal.getsignal(sig) for sig in sigs}
    with pytest.raises(FileNotFoundError):
        worker.supervise([], tmp_path, {}, tmp_path / "missing" / "guard")
    assert {sig: signal.getsignal(sig) for sig in sigs} == before


def test_primary_and_cleanup_exceptions_both_retained(worker, monkeypatch, tmp_path):
    original = ValueError("synthetic spawn failure")
    cleanup = OSError("synthetic unlink failure")
    guard = tmp_path / "guard"

    def fail_spawn(*args, **kwargs):
        raise original

    old_unlink = Path.unlink

    def fail_unlink(path, *args, **kwargs):
        if path == guard:
            raise cleanup
        return old_unlink(path, *args, **kwargs)

    monkeypatch.setattr(worker.launcher, "_spawn", fail_spawn)
    monkeypatch.setattr(Path, "unlink", fail_unlink)
    with pytest.raises(worker.SupervisionFailure) as caught:
        worker.supervise([], tmp_path, {}, guard)
    assert caught.value.original_error is original
    assert caught.value.cleanup_error is cleanup
    assert caught.value.__cause__ is original
    saved = json.loads(guard.read_text())
    assert saved["original_error"] == "ValueError" and saved["cleanup_error"] == "OSError"

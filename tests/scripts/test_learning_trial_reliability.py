"""Real isolated POSIX processes; Windows argv tested without claiming execution."""

import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import psutil
import pytest

from deeptutor.runtime.npm_command import npm_command
from tests.scripts.test_learning_trial import repos as repos
from tests.scripts.test_learning_trial import trial as trial


def test_windows_npm_uses_node_without_shell(tmp_path, monkeypatch):
    npm = tmp_path / "Node with spaces & symbols" / "npm.cmd"
    cli = npm.parent / "node_modules/npm/bin/npm-cli.js"
    cli.parent.mkdir(parents=True)
    cli.touch()
    monkeypatch.setattr(
        "deeptutor.runtime.npm_command.shutil.which", lambda _: "C:/Node Folder/node.exe"
    )
    args = ("ci", "--prefix", "a & b %PATH% ^ | ; $(echo nope)")
    command = npm_command(str(npm), *args, windows=True)
    assert command == ["C:/Node Folder/node.exe", str(cli), *args]
    assert not any(x.lower().endswith(("cmd.exe", "npm.cmd")) for x in command)


def test_unknown_windows_npm_layout_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr("deeptutor.runtime.npm_command.shutil.which", lambda _: "node.exe")
    with pytest.raises(RuntimeError, match="npm-cli"):
        npm_command(str(tmp_path / "npm.cmd"), "ci", windows=True)


def test_failed_update_blocks_deps_and_start_until_success(trial, repos, tmp_path):
    remote, local = repos
    trial.configure(local, "trial", tmp_path / "home")
    offline = remote.with_name("offline")
    remote.rename(offline)
    with pytest.raises(trial.UpdateError):
        trial.lifecycle(local, "update")
    for action in ("deps", "start"):
        with pytest.raises(trial.UpdateError, match="Previous update"):
            trial.lifecycle(local, action)
    offline.rename(remote)
    trial.lifecycle(local, "update")
    assert not (local / ".git/learning-trial-failure.json").exists()


def test_cleanup_guard_retains_lock(trial, tmp_path):
    lock = tmp_path / "learning-trial.lock"
    with trial.exclusive(lock):
        (tmp_path / "learning-trial-cleanup-pending").write_text("synthetic")
    assert lock.exists()
    with pytest.raises(trial.UpdateError, match="active or stale"):
        with trial.exclusive(lock):
            pytest.fail("must not enter")


def wait_file(path):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if path.exists() and path.read_text():
            return path.read_text()
        time.sleep(0.02)
    pytest.fail(f"missing readiness: {path}")


def alive(pid):
    try:
        p = psutil.Process(pid)
        return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


@pytest.mark.skipif(os.name == "nt", reason="POSIX real process cancellation; Windows pending")
def test_real_cancel_cleans_child_tree_before_unlock(tmp_path):
    root = Path(__file__).resolve().parents[2]
    guard, lock, ready = (
        tmp_path / n for n in ("learning-trial-cleanup-pending", "learning-trial.lock", "child pid")
    )
    child = tmp_path / "child script with spaces.py"
    child.write_text("import time\ntime.sleep(120)\n")
    parent = tmp_path / "parent script.py"
    parent.write_text(
        f"import subprocess,sys,time\nfrom pathlib import Path\np=subprocess.Popen([sys.executable,{str(child)!r}])\nPath({str(ready)!r}).write_text(str(p.pid))\ntime.sleep(120)\n"
    )
    worker = tmp_path / "worker.py"
    worker.write_text(
        f"import sys,os\nfrom pathlib import Path\nsys.path.insert(0,{str(root / 'scripts')!r})\nfrom learning_trial_worker import supervise\nsys.exit(supervise([sys.executable,{str(parent)!r}],Path({str(tmp_path)!r}),dict(os.environ),Path({str(guard)!r})))\n"
    )
    runner = tmp_path / "runner.py"
    runner.write_text(
        f"import sys,os\nfrom pathlib import Path\nsys.path.insert(0,{str(root / 'scripts')!r})\nfrom learning_trial import exclusive,execute_supervised\nwith exclusive(Path({str(lock)!r})):\n    execute_supervised([sys.executable,{str(worker)!r}],Path({str(tmp_path)!r}),dict(os.environ))\n"
    )
    proc = subprocess.Popen([sys.executable, str(runner)], start_new_session=True)
    pid = None
    try:
        pid = int(wait_file(ready))
        assert lock.exists() and guard.exists() and alive(pid)
        os.killpg(proc.pid, signal.SIGINT)
        assert proc.wait(timeout=15) == 0
        assert not alive(pid)
        assert not lock.exists() and not guard.exists()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        if pid and alive(pid):
            psutil.Process(pid).kill()


def test_worker_nonzero_exit_propagates_and_cleans_guard(tmp_path):
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "trial_worker", root / "scripts/learning_trial_worker.py"
    )
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    guard = tmp_path / "guard"
    result = worker.supervise(
        [sys.executable, "-c", "raise SystemExit(7)"], tmp_path, dict(os.environ), guard
    )
    assert result == 7
    assert not guard.exists()


def test_start_subprocess_failure_persists_block(trial, repos, tmp_path, monkeypatch):
    _, local = repos
    home = tmp_path / "home"
    trial.configure(local, "trial", home)
    monkeypatch.setattr(trial, "require_tools", lambda: None)
    python = home / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python.parent.mkdir(parents=True)
    python.touch()
    sha = trial.Git(local).run(["rev-parse", "HEAD"]).stdout
    (home / "dependencies.json").write_text(trial.json.dumps({"commit": sha}))

    def failed(*args):
        raise subprocess.CalledProcessError(7, "synthetic-worker")

    monkeypatch.setattr(trial, "execute_supervised", failed)
    with pytest.raises(subprocess.CalledProcessError):
        trial.lifecycle(local, "start")
    with pytest.raises(trial.UpdateError, match="Previous start"):
        trial.lifecycle(local, "start")


def test_node_exec_preserves_metacharacters_on_local_host(tmp_path, monkeypatch):
    import json
    import shutil

    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    npm = tmp_path / "Node folder with spaces" / "npm.cmd"
    cli = npm.parent / "node_modules/npm/bin/npm-cli.js"
    cli.parent.mkdir(parents=True)
    cli.write_text("console.log(JSON.stringify(process.argv.slice(2)))")
    monkeypatch.setattr("deeptutor.runtime.npm_command.shutil.which", lambda _: node)
    args = ["ci", "a & b %PATH% ^ | ; $(echo nope)"]
    result = subprocess.check_output(npm_command(str(npm), *args, windows=True), text=True)
    assert json.loads(result) == args

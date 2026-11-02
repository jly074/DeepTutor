"""Only disposable local Git repositories; no GitHub or product credentials."""

import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


@pytest.fixture
def trial(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("learning_trial", SCRIPTS / "learning_trial.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(repo, *args):
    return subprocess.check_output(
        ["git", *args], cwd=repo, text=True, stderr=subprocess.PIPE
    ).strip()


def commit(repo, name="next"):
    git(repo, "add", ".")
    git(repo, "commit", "-m", name)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repos(tmp_path, trial, monkeypatch):
    remote = tmp_path / "published"
    remote.mkdir()
    git(remote, "init", "-b", "trial")
    git(remote, "config", "user.name", "Synthetic")
    git(remote, "config", "user.email", "synthetic@example.invalid")
    (remote / "file.txt").write_text("one")
    commit(remote, "initial")
    local = tmp_path / "checkout"
    git(tmp_path, "clone", str(remote), str(local))
    git(local, "config", "user.name", "Synthetic")
    git(local, "config", "user.email", "synthetic@example.invalid")
    monkeypatch.setattr(trial, "SOURCE", str(remote))  # no CLI/environment override exists
    return remote, local


def test_clean_fast_forward_and_version(trial, repos, capsys):
    remote, local = repos
    (remote / "file.txt").write_text("two")
    expected = commit(remote)
    trial.update(trial.Git(local), "trial")
    assert git(local, "rev-parse", "HEAD") == expected
    assert (local / "file.txt").read_text() == "two"
    assert expected in capsys.readouterr().out


@pytest.mark.parametrize("kind", ["tracked", "untracked"])
def test_dirty_preserved_before_fetch(trial, repos, kind):
    _, local = repos
    file = local / ("file.txt" if kind == "tracked" else "personal.txt")
    file.write_text("keep")
    before = git(local, "rev-parse", "HEAD")
    with pytest.raises(trial.UpdateError, match="Tracked/untracked"):
        trial.update(trial.Git(local), "trial")
    assert file.read_text() == "keep"
    assert git(local, "rev-parse", "HEAD") == before
    assert not (local / ".git/FETCH_HEAD").exists()


@pytest.mark.parametrize("diverged", [False, True])
def test_local_only_or_diverged_never_merged(trial, repos, diverged):
    remote, local = repos
    (local / "local.txt").write_text("keep")
    before = commit(local)
    if diverged:
        (remote / "remote.txt").write_text("published")
        commit(remote)
    with pytest.raises(trial.UpdateError, match="Local-only or divergent"):
        trial.update(trial.Git(local), "trial")
    assert git(local, "rev-parse", "HEAD") == before


def test_offline_fetch_does_not_move_head(trial, repos):
    remote, local = repos
    before = git(local, "rev-parse", "HEAD")
    remote.rename(remote.with_name("unavailable"))
    with pytest.raises(trial.UpdateError, match="Git fetch failed"):
        trial.update(trial.Git(local), "trial")
    assert git(local, "rev-parse", "HEAD") == before


def test_no_new_version(trial, repos, capsys):
    _, local = repos
    before = git(local, "rev-parse", "HEAD")
    trial.update(trial.Git(local), "trial")
    assert "Already up to date" in capsys.readouterr().out
    assert git(local, "rev-parse", "HEAD") == before


def test_ignored_file_collision_preserved(trial, repos):
    remote, local = repos
    (local / ".git/info/exclude").write_text("secret.txt\n")
    (local / "secret.txt").write_text("local synthetic secret")
    (remote / "secret.txt").write_text("remote")
    commit(remote)
    before = git(local, "rev-parse", "HEAD")
    with pytest.raises(trial.UpdateError):
        trial.update(trial.Git(local), "trial")
    assert (local / "secret.txt").read_text() == "local synthetic secret"
    assert git(local, "rev-parse", "HEAD") == before


def test_fixed_remote_and_branch(trial, repos):
    _, local = repos
    with pytest.raises(trial.UpdateError, match="Current branch"):
        trial.update(trial.Git(local), "main")
    git(local, "remote", "set-url", "origin", "https://example.invalid/other.git")
    with pytest.raises(trial.UpdateError, match="fixed"):
        trial.update(trial.Git(local), "trial")


def test_setup_preserves_existing_home_and_configuration(trial, repos, tmp_path):
    _, local = repos
    existing = tmp_path / "existing"
    existing.mkdir()
    (existing / "settings.json").write_text("keep")
    with pytest.raises(trial.UpdateError, match="NEW runtime"):
        trial.configure(local, "trial", existing)
    home = tmp_path / "new-home"
    trial.configure(local, "trial", home)
    with pytest.raises(trial.UpdateError, match="already configured"):
        trial.configure(local, "trial", tmp_path / "another")
    assert (existing / "settings.json").read_text() == "keep"
    assert not (tmp_path / "another").exists()


def test_start_needs_matching_dependencies_and_isolated_launcher(
    trial, repos, tmp_path, monkeypatch
):
    _, local = repos
    home = tmp_path / "home"
    trial.configure(local, "trial", home)
    monkeypatch.setattr(trial, "require_tools", lambda: None)
    with pytest.raises(trial.UpdateError, match="Dependencies not verified"):
        trial.lifecycle(local, "start")
    python = home / "venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    python.parent.mkdir(parents=True)
    python.touch()
    (home / "dependencies.json").write_text(
        trial.json.dumps({"commit": git(local, "rev-parse", "HEAD")})
    )
    calls = []
    monkeypatch.setattr(trial, "execute", lambda *args: calls.append(args))
    trial.lifecycle(local, "start")
    command, cwd, env = calls[0]
    assert command[1:] == [local / "scripts/start_web.py", "--home", home / "runtime", "--dev"]
    assert cwd == local and env["DEEPTUTOR_HOME"] == str(home / "runtime")
    (home / "dependencies.json").write_text('{"commit":"old"}')
    with pytest.raises(trial.UpdateError, match="Dependencies not verified"):
        trial.lifecycle(local, "start")
    assert len(calls) == 1


def test_lock_does_not_remove_another_operations_lock(trial, tmp_path):
    lock = tmp_path / "lock"
    with trial.exclusive(lock):
        with pytest.raises(trial.UpdateError, match="active or stale"):
            with trial.exclusive(lock):
                pytest.fail("must not enter")
        assert lock.exists()
    assert not lock.exists()


def test_missing_prerequisite_stops(trial, monkeypatch):
    monkeypatch.setattr(trial.shutil, "which", lambda tool: None)
    with pytest.raises(trial.UpdateError, match="Missing git"):
        trial.require_tools()


def test_failed_dependency_install_invalidates_stamp_preserves_runtime(
    trial, repos, tmp_path, monkeypatch
):
    _, local = repos
    home = tmp_path / "home"
    trial.configure(local, "trial", home)
    runtime = home / "runtime"
    runtime.mkdir()
    (runtime / "settings.json").write_text("synthetic-preserve")
    stamp = home / "dependencies.json"
    stamp.write_text('{"commit":"previous"}')
    monkeypatch.setattr(trial, "require_tools", lambda: None)

    def fail(*args):
        raise subprocess.CalledProcessError(1, "synthetic-install")

    monkeypatch.setattr(trial, "execute", fail)
    with pytest.raises(subprocess.CalledProcessError):
        trial.lifecycle(local, "deps")
    assert not stamp.exists()
    assert (runtime / "settings.json").read_text() == "synthetic-preserve"


def test_update_preserves_separate_runtime(trial, repos, tmp_path):
    remote, local = repos
    home = tmp_path / "home"
    trial.configure(local, "trial", home)
    (home / "runtime").mkdir()
    saved = home / "runtime" / "synthetic-data.json"
    saved.write_text('{"value":42}')
    (remote / "file.txt").write_text("new")
    commit(remote)
    trial.lifecycle(local, "update")
    assert saved.read_text() == '{"value":42}'


def test_missing_published_branch_stops(trial, repos):
    remote, local = repos
    git(remote, "branch", "-m", "renamed")
    before = git(local, "rev-parse", "HEAD")
    with pytest.raises(trial.UpdateError, match="Git fetch failed"):
        trial.update(trial.Git(local), "trial")
    assert git(local, "rev-parse", "HEAD") == before

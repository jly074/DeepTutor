#!/usr/bin/env python
"""Explicit, isolated source-trial lifecycle; never publishes or configures credentials."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from update import Git as ExistingGit
from update import UpdateError, current_branch, dependency_hints

SOURCE = "https://github.com/jly074/DeepTutor.git"


class Git(ExistingGit):
    def run(self, args, **kwargs):
        try:
            return super().run(args, **kwargs)
        except UpdateError:
            raise UpdateError(
                f"Git {args[0]} failed. Check connectivity, published branch, permissions or local conflicts; inspect git status."
            ) from None


def require_tools():
    if not (3, 11) <= sys.version_info[:2] < (3, 15):
        raise UpdateError("Use Python 3.11-3.14 (recommended 3.12).")
    for tool in ("git", "node", "npm"):
        if not shutil.which(tool):
            raise UpdateError(f"Missing {tool}; install prerequisites, then retry.")
    major = int(
        subprocess.check_output([shutil.which("node"), "--version"], text=True)
        .strip()
        .lstrip("v")
        .split(".")[0]
    )
    if major != 22:
        raise UpdateError("Use Node.js 22 LTS for this Windows trial.")


def clean(git):
    if git.run(["status", "--porcelain=v1", "--untracked-files=all"]).stdout:
        raise UpdateError(
            "Tracked/untracked changes found. Preserve them manually; no update performed."
        )


def identity(git, branch):
    git.run(["check-ref-format", "--branch", branch])
    if git.run(["remote", "get-url", "origin"]).stdout != SOURCE:
        raise UpdateError("origin must be the fixed jly074/DeepTutor HTTPS repository.")
    if current_branch(git) != branch:
        raise UpdateError(
            "Current branch differs from the configured trial branch; stop and inspect."
        )
    clean(git)


def paths(repo):
    git = Git(repo)
    directory = Path(git.run(["rev-parse", "--absolute-git-dir"]).stdout)
    return git, directory / "learning-trial.json", directory / "learning-trial.lock"


@contextmanager
def exclusive(path):
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise UpdateError(
            "Trial operation active or stale lock. Stop the trial; inspect lock PID before manually removing it."
        ) from None
    try:
        with os.fdopen(fd, "w") as out:
            out.write(str(os.getpid()))
        yield
    finally:
        path.unlink()


def configure(repo, branch, home):
    git, marker, _ = paths(repo)
    if marker.exists():
        raise UpdateError("Trial already configured; existing configuration is preserved.")
    identity(git, branch)
    home = home.resolve()
    if home == repo or repo in home.parents or home in repo.parents or home.exists():
        raise UpdateError(
            "Choose a NEW runtime directory outside the checkout; existing data is never adopted."
        )
    home.mkdir(parents=True)
    marker.write_text(
        json.dumps({"branch": branch, "home": str(home), "repo": str(repo)}, indent=2),
        encoding="utf-8",
    )
    print(f"Configured branch={branch}; isolated trial home={home}. Next: deps, then start.")


def update(git, branch):
    identity(git, branch)
    old = git.run(["rev-parse", "HEAD"]).stdout
    # Fetch only the explicitly configured branch. No implicit main/upstream choice.
    git.run(["fetch", "--no-tags", "origin", f"refs/heads/{branch}"], timeout=60)
    target = git.run(["rev-parse", "FETCH_HEAD^{commit}"]).stdout
    ahead, behind = map(
        int, git.run(["rev-list", "--left-right", "--count", f"HEAD...{target}"]).stdout.split()
    )
    print(f"Current={old} Published={target} ahead={ahead} behind={behind}")
    if ahead:
        raise UpdateError(
            "Local-only or divergent commits; no merge/reset performed. Ask for review."
        )
    if not behind:
        print("Already up to date. Dependencies and server state are separate.")
        return
    clean(git)
    if git.run(["rev-parse", "HEAD"]).stdout != old:
        raise UpdateError("HEAD changed concurrently; stop and inspect.")
    changed = git.run(["diff", "--name-only", old, target]).stdout.splitlines()
    git.run(["merge", "--ff-only", "--no-overwrite-ignore", target])
    print(f"Updated code to {target}. Server NOT restarted. Run deps, then start.")
    for hint in dependency_hints(changed):
        print(hint)


def environment(home):
    # Do not inherit DEEPTUTOR runtime overrides from another instance.
    # Other OS/tool environment variables are retained; no credentials are configured here.
    env = {k: v for k, v in os.environ.items() if not k.startswith("DEEPTUTOR_")}
    env["DEEPTUTOR_HOME"] = str(home / "runtime")
    return env


def execute(command, cwd, env):
    subprocess.run([str(x) for x in command], cwd=cwd, env=env, check=True)


def lifecycle(repo, action):
    git, marker, _ = paths(repo)
    if not marker.exists():
        raise UpdateError("Run setup with an explicit branch and new home first.")
    config = json.loads(marker.read_text(encoding="utf-8"))
    if config["repo"] != str(repo):
        raise UpdateError("Checkout moved; inspect configuration before continuing.")
    identity(git, config["branch"])
    home = Path(config["home"])
    if not home.is_dir() or home.is_symlink():
        raise UpdateError("Trial home missing or replaced; inspect before continuing.")
    if action == "update":
        update(git, config["branch"])
        return
    sha = git.run(["rev-parse", "HEAD"]).stdout
    print(f"Version={sha}\nBranch={config['branch']}\nTrial data={home / 'runtime'}", flush=True)
    if action == "status":
        print(
            "Local status only; publication is checked by update. No server or dependency change."
        )
        return
    require_tools()
    python = home / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    stamp = home / "dependencies.json"
    env = environment(home)
    if action == "deps":
        if stamp.exists():
            stamp.unlink()  # invalidate success before any partial installation
        if not python.exists():
            execute([sys.executable, "-m", "venv", home / "venv"], repo, env)
        execute([python, "-m", "pip", "install", "-r", "requirements/full.txt"], repo, env)
        execute([python, "-m", "pip", "install", "-e", ".", "--no-deps"], repo, env)
        execute([python, "-m", "pip", "check"], repo, env)
        execute([shutil.which("npm"), "ci", "--legacy-peer-deps"], repo / "web", env)
        stamp.write_text(json.dumps({"commit": sha}), encoding="utf-8")
        print("Dependencies ready for this commit. Next: start.")
    else:
        if (
            not python.exists()
            or not stamp.exists()
            or json.loads(stamp.read_text())["commit"] != sha
        ):
            raise UpdateError("Dependencies not verified for this commit. Run deps first.")
        print(
            "Starting existing development launcher. Read its actual URL; Ctrl+C stops it.",
            flush=True,
        )
        execute(
            [python, repo / "scripts/start_web.py", "--home", home / "runtime", "--dev"], repo, env
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["setup", "status", "update", "deps", "start"])
    parser.add_argument("--branch")
    parser.add_argument("--home", type=Path)
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parent.parent
    try:
        _, _, lock = paths(repo)
        with exclusive(lock):
            if args.action == "setup":
                if not args.branch or not args.home:
                    raise UpdateError("setup requires --branch and --home; neither is inferred.")
                configure(repo, args.branch, args.home)
            else:
                lifecycle(repo, args.action)
        return 0
    except (UpdateError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        # Do not echo subprocess stderr: it may contain credential-bearing URLs.
        print(
            f"BLOCKED: {exc if isinstance(exc, UpdateError) else type(exc).__name__}. No automatic rollback; inspect status before retry.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

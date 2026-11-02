"""Supervise only the trial launcher we spawn, using its existing tree cleanup."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deeptutor.runtime import launcher  # noqa: E402


class SupervisionFailure(RuntimeError):
    def __init__(self, exit_code, original_error, cleanup_error, cancelled):
        self.exit_code = exit_code
        self.original_error = original_error
        self.cleanup_error = cleanup_error
        self.cancelled = cancelled
        super().__init__(
            f"Trial supervision failed: original_exit={exit_code}, "
            f"original_error={type(original_error).__name__ if original_error else None}, "
            f"cleanup_error={type(cleanup_error).__name__ if cleanup_error else None}, "
            f"cancelled={cancelled}; inspect retained guard/lock when cleanup failed."
        )


def supervise(command, cwd, env, guard):
    import psutil

    stop = threading.Event()
    force = threading.Event()

    def cancel(_signum, _frame):
        if stop.is_set():
            force.set()
        stop.set()

    previous = {}
    proc = None
    descendants = {}
    original_error = cleanup_error = None
    original_exit = None
    guard_created = False
    try:
        for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
            sig = getattr(signal, name, None)
            if sig is not None:
                previous[sig] = signal.signal(sig, cancel)
        # Inside the restoration boundary, including filesystem failures.
        guard.write_text(str(os.getpid()), encoding="utf-8")
        guard_created = True
        try:
            proc = launcher._spawn(command, cwd=cwd, env=env, name="trial")
            while proc.process.poll() is None:
                try:
                    for child in psutil.Process(proc.process.pid).children(recursive=True):
                        descendants[child.pid] = child
                except psutil.NoSuchProcess:
                    pass
                if stop.wait(0.05):
                    break
        except Exception as exc:
            original_error = exc
        try:
            if proc is not None:
                original_exit = proc.process.poll()
                try:
                    for child in psutil.Process(proc.process.pid).children(recursive=True):
                        descendants[child.pid] = child
                except psutil.NoSuchProcess:
                    pass
                launcher._terminate_all([proc], force=force)
                alive = []
                for child in descendants.values():
                    try:
                        if child.is_running() and child.status() != psutil.STATUS_ZOMBIE:
                            alive.append(child)
                    except psutil.NoSuchProcess:
                        pass
                if proc.process.poll() is None or alive:
                    raise RuntimeError("Trial cleanup incomplete")
            guard.unlink()
            guard_created = False
        except Exception as exc:
            cleanup_error = exc
        if original_error is not None or cleanup_error is not None:
            failure = SupervisionFailure(
                original_exit, original_error, cleanup_error, stop.is_set()
            )
            if guard_created:
                try:
                    guard.write_text(
                        json.dumps(
                            {
                                "pid": os.getpid(),
                                "original_exit": original_exit,
                                "original_error": type(original_error).__name__
                                if original_error
                                else None,
                                "cleanup_error": type(cleanup_error).__name__
                                if cleanup_error
                                else None,
                                "cancelled": stop.is_set(),
                            }
                        ),
                        encoding="utf-8",
                    )
                except OSError as diagnostic_error:
                    failure.add_note(
                        f"Could not update guard diagnostics: {type(diagnostic_error).__name__}"
                    )
            raise failure from (original_error or cleanup_error)
        if original_exit not in (None, 0):
            return original_exit
        # A failure observed after the initial poll must not become cancellation success.
        final_exit = proc.process.returncode if proc else None
        if final_exit is not None and final_exit > 0:
            return final_exit
        return 130 if stop.is_set() else final_exit
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    # Called by learning_trial.py with fixed positional paths, never shell text.
    guard = Path(sys.argv[1])
    home = Path(sys.argv[2])
    root = Path(__file__).resolve().parent.parent
    raise SystemExit(
        supervise(
            [sys.executable, str(root / "scripts/start_web.py"), "--home", str(home), "--dev"],
            root,
            dict(os.environ),
            guard,
        )
    )

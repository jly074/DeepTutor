"""Supervise only the trial launcher we spawn, using its existing tree cleanup."""

from __future__ import annotations

import os
from pathlib import Path
import signal
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deeptutor.runtime import launcher  # noqa: E402


def supervise(command, cwd, env, guard):
    import psutil

    stop = threading.Event()
    force = threading.Event()

    def cancel(_signum, _frame):
        if stop.is_set():
            force.set()
        stop.set()

    signals = [
        getattr(signal, name) for name in ("SIGINT", "SIGTERM", "SIGBREAK") if hasattr(signal, name)
    ]
    previous = {sig: signal.signal(sig, cancel) for sig in signals}
    proc = None
    descendants = {}
    guard.write_text(str(os.getpid()), encoding="utf-8")
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
        return 0 if stop.is_set() else proc.process.returncode
    finally:
        try:
            if proc is not None:
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
                    raise RuntimeError("Trial cleanup incomplete; lock retained for inspection.")
            guard.unlink()
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

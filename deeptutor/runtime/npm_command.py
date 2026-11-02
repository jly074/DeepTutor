"""Build shell-free npm argv, including the standard Windows Node installation."""

from __future__ import annotations

import os
from pathlib import Path
import shutil


def npm_command(npm: str, *args: str, windows: bool | None = None) -> list[str]:
    if windows is None:
        windows = os.name == "nt"
    if not windows:
        return [npm, *args]
    # Never pass a .cmd shim or user arguments to cmd.exe. Support the official
    # bundled/global npm layout; unknown shim layouts fail instead of using shell.
    cli = Path(npm).parent / "node_modules" / "npm" / "bin" / "npm-cli.js"
    node = shutil.which("node")
    if not node or not cli.is_file():
        raise RuntimeError(
            "Cannot locate Node/npm-cli.js. Install standard Node.js 22 LTS and retry."
        )
    return [node, str(cli), *args]

"""Opt-in Windows user-bound protection for provider catalog and settings drafts.

Only these two stores use this envelope. No plaintext fallback on protected read/write
failure. OS account protection does not replace application authorization.
"""

from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import tempfile

FORMAT = "deeptutor-windows-dpapi-v1"
MARKER = ".windows-protected-settings"
FILES = ("model_catalog.json", "settings_draft.json")


class ProtectionError(RuntimeError):
    pass


def available() -> bool:
    return os.name == "nt"


def _crypt(data: bytes, *, decrypt=False) -> bytes:
    if not available():
        raise ProtectionError("Windows protection is unavailable on this host.")

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    incoming = Blob(len(data), buffer)
    outgoing = Blob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    fn = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    fn.argtypes = [
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(Blob),
    ]
    fn.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    try:
        if not fn(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
            raise ProtectionError(
                "Windows could not protect/unlock settings. Original file preserved."
            )
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        ctypes.memset(buffer, 0, len(data))
        if outgoing.data:
            ctypes.memset(outgoing.data, 0, outgoing.size)
            kernel32.LocalFree(outgoing.data)


def decode(value: dict) -> dict:
    if value.get("protected_format") != FORMAT:
        if "protected_format" in value:
            raise ProtectionError("Unknown protected settings format; file preserved.")
        return value
    try:
        payload = base64.b64decode(value["ciphertext"], validate=True)
        result = json.loads(_crypt(payload, decrypt=True))
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except ProtectionError:
        raise
    except (ValueError, KeyError, TypeError):
        raise ProtectionError("Protected settings are invalid; file preserved.") from None


def encode(value: dict, path: Path, *, force=False) -> dict:
    if not force and not (path.parent / MARKER).exists():
        # A protected file remains protected even if the marker was removed.
        if not path.exists():
            return value
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            raise ProtectionError("Cannot inspect settings protection; file preserved.") from None
        if not isinstance(existing, dict) or "protected_format" not in existing:
            return value
    raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
    return {"protected_format": FORMAT, "ciphertext": base64.b64encode(_crypt(raw)).decode("ascii")}


def state(directory: Path) -> dict:
    files = {}
    for name in FILES:
        path = directory / name
        if not path.exists():
            files[name] = "absent"
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            files[name] = (
                "protected"
                if isinstance(value, dict) and value.get("protected_format") == FORMAT
                else "plaintext"
            )
        except (ValueError, OSError):
            files[name] = "unreadable"
    return {
        "available": available(),
        "enabled": (directory / MARKER).exists(),
        "files": files,
        "scope": "provider_catalog_and_settings_draft",
    }


def _atomic(path: Path, value: dict):
    fd, temporary = tempfile.mkstemp(prefix=".protected-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(value, out)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def enable(directory: Path) -> dict:
    if not available():
        raise ProtectionError("Windows protection is unavailable; do not enter real credentials.")
    directory.mkdir(parents=True, exist_ok=True)
    prepared = []
    # Validate/decrypt/encrypt ALL existing files before replacing any of them.
    for name in FILES:
        path = directory / name
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    raise ValueError()
                plain = decode(raw)
                encrypted = encode(plain, path, force=True)
                if decode(encrypted) != plain:
                    raise ProtectionError("Protection round-trip verification failed.")
                prepared.append((path, encrypted))
            except (ValueError, OSError):
                raise ProtectionError(
                    "Settings cannot be protected; original files preserved."
                ) from None
    # No plaintext backup/temp files. Partial replacement is readable and retryable.
    for path, encrypted in prepared:
        _atomic(path, encrypted)
    _atomic(directory / MARKER, {"version": 1})
    return state(directory)

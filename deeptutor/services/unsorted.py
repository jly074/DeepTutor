"""Workspace intake registry referencing the existing account File Library."""

from contextlib import contextmanager
import hashlib
import json
from pathlib import PurePosixPath, PureWindowsPath
import time
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .announcement_inbox import InboxError


class IntakeItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64)
    revision: int = Field(ge=1)
    category: str = Field(min_length=1, max_length=100)


class CollectBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[IntakeItemUpdate] = Field(min_length=1, max_length=100)


def filename(value):
    if (
        not value
        or len(value) > 200
        or value in {".", ".."}
        or any(ord(c) < 32 for c in value)
        or PurePosixPath(value).name != value
        or PureWindowsPath(value).name != value
        or "/" in value
        or "\\" in value
        or ":" in value
    ):
        raise InboxError("invalid_filename", 422)
    return value


class Unsorted:
    def __init__(self, board, workspace, library):
        self.board, self.workspace, self.library = board, workspace, library

    @contextmanager
    def connection(self):
        conn = self.board._connect()
        try:
            conn.executescript("""CREATE TABLE IF NOT EXISTS intake_sources (
             id TEXT PRIMARY KEY,workspace TEXT NOT NULL,name TEXT NOT NULL);
             CREATE TABLE IF NOT EXISTS intake_versions (
             id TEXT PRIMARY KEY,source_id TEXT NOT NULL,workspace TEXT NOT NULL,
             library_id TEXT NOT NULL,sha256 TEXT NOT NULL,filename TEXT NOT NULL,size_bytes INTEGER NOT NULL,
             data_class TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',category TEXT NOT NULL DEFAULT '',
             revision INTEGER NOT NULL DEFAULT 1,created_at REAL NOT NULL,
             UNIQUE(workspace,source_id,sha256));
             CREATE TABLE IF NOT EXISTS intake_history (
             seq INTEGER PRIMARY KEY AUTOINCREMENT,version_id TEXT NOT NULL,
             old_json TEXT NOT NULL,new_json TEXT NOT NULL,at REAL NOT NULL);""")
            conn.commit()
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                yield conn
        finally:
            conn.close()

    def source(self, conn, identity):
        row = conn.execute(
            "SELECT * FROM intake_sources WHERE id=? AND workspace=?", (identity, self.workspace)
        ).fetchone()
        if row is None:
            raise InboxError("not_found", 404)
        return row

    def row(self, conn, identity):
        row = conn.execute(
            "SELECT * FROM intake_versions WHERE id=? AND workspace=?", (identity, self.workspace)
        ).fetchone()
        if row is None:
            raise InboxError("not_found", 404)
        return row

    def register(self, entry, name, data_class, source_id=None):
        with self.connection() as conn:
            if source_id:
                self.source(conn, source_id)
                previous = conn.execute(
                    "SELECT * FROM intake_versions WHERE workspace=? AND source_id=? AND sha256=?",
                    (self.workspace, source_id, entry["sha256"]),
                ).fetchone()
            else:
                previous = conn.execute(
                    "SELECT * FROM intake_versions WHERE workspace=? AND filename=? AND sha256=? AND data_class=? ORDER BY created_at LIMIT 1",
                    (self.workspace, name, entry["sha256"], data_class),
                ).fetchone()
            if previous:
                return {"item": dict(previous), "duplicate": True}
            if not source_id:
                source_id = str(uuid4())
                conn.execute(
                    "INSERT INTO intake_sources VALUES(?,?,?)", (source_id, self.workspace, name)
                )
            identity = str(uuid4())
            conn.execute(
                "INSERT INTO intake_versions(id,source_id,workspace,library_id,sha256,filename,size_bytes,data_class,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    identity,
                    source_id,
                    self.workspace,
                    entry["id"],
                    entry["sha256"],
                    name,
                    entry["size_bytes"],
                    data_class,
                    time.time(),
                ),
            )
            return {"item": dict(self.row(conn, identity)), "duplicate": False}

    async def receive(self, name, data, data_class, source_id=None):
        name = filename(name)
        if not data or len(data) > 5 * 1024 * 1024:
            raise InboxError("file_size", 422)
        if source_id:
            with self.connection() as conn:
                self.source(conn, source_id)
        entry = await self.library.add_file(
            data=data, filename=name, mime_type="application/octet-stream"
        )
        path = self.library.resolve_path(entry["id"])
        if (
            path is None
            or not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]
        ):
            raise InboxError("original_unavailable", 409)
        return self.register(entry, name, data_class, source_id)

    def listing(self, offset=0):
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM intake_versions WHERE workspace=? ORDER BY created_at DESC,id LIMIT 101 OFFSET ?",
                (self.workspace, offset),
            ).fetchall()
            return {
                "items": [dict(r) for r in rows[:100]],
                "next_offset": offset + 100 if len(rows) > 100 else None,
            }

    def collect(self, payload):
        if len({x.id for x in payload.items}) != len(payload.items):
            raise InboxError("duplicate_selection", 422)
        with self.connection() as conn:
            changes = []
            for item in payload.items:
                row = self.row(conn, item.id)
                category = item.category.strip()
                if not category:
                    raise InboxError("category_required", 422)
                if row["status"] == "collected" and row["category"] == category:
                    continue
                if row["revision"] != item.revision:
                    raise InboxError("stale_revision", 409)
                path = self.library.resolve_path(row["library_id"])
                if path is None or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
                    raise InboxError("original_unavailable", 409)
                changes.append((row, category))
            for row, category in changes:
                conn.execute(
                    "UPDATE intake_versions SET status='collected',category=?,revision=revision+1 WHERE id=?",
                    (category, row["id"]),
                )
                conn.execute(
                    "INSERT INTO intake_history(version_id,old_json,new_json,at) VALUES(?,?,?,?)",
                    (
                        row["id"],
                        json.dumps({"status": row["status"], "category": row["category"]}),
                        json.dumps(
                            {
                                "status": "collected",
                                "category": category,
                                "basis": "manual_confirmation",
                            }
                        ),
                        time.time(),
                    ),
                )
            return {"items": [dict(self.row(conn, x.id)) for x in payload.items]}

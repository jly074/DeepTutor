"""Manual announcement intake attached to the existing account task-board store.

No provider connections, message sending, calendar writes or model calls.
"""

from contextlib import closing, contextmanager
from datetime import datetime, timezone
import hashlib
import json
from typing import Annotated
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from deeptutor.services.task_board import TaskBoardStore, TaskDueDate

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class ReceiveAnnouncement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=148)]
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)]
    source_label: ShortText
    source_key: ShortText
    source_url: str = Field(default="", max_length=2048)
    due_date: TaskDueDate | None = None
    simulated: bool = False
    consent: bool

    @field_validator("consent")
    @classmethod
    def require_consent(cls, value):
        if not value:
            raise ValueError("Explicit host storage consent required")
        return value

    @field_validator("source_url")
    @classmethod
    def safe_url(cls, value):
        if not value:
            return value
        parsed = urlsplit(value)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or any(c.isspace() for c in value)
        ):
            raise ValueError("Use a source HTTP(S) link without credentials")
        return value


class ReviewAnnouncement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    reviewed: bool


class ConvertAnnouncement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)


class InboxError(Exception):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


class AnnouncementInbox:
    def __init__(self, board: TaskBoardStore, workspace: str):
        self.board, self.workspace = board, workspace

    @contextmanager
    def connection(self):
        with closing(self.board._connect()) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS announcement_inbox (
              seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
              workspace TEXT NOT NULL, simulated INTEGER NOT NULL,
              source_label TEXT NOT NULL, source_key TEXT NOT NULL,
              fingerprint TEXT NOT NULL, payload TEXT NOT NULL,
              reviewed INTEGER NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 1,
              task_id TEXT, created_at TEXT NOT NULL,
              UNIQUE(workspace,simulated,source_label,source_key))""")
            conn.commit()
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                yield conn

    def row(self, conn, item_id):
        row = conn.execute(
            "SELECT * FROM announcement_inbox WHERE id=? AND workspace=?", (item_id, self.workspace)
        ).fetchone()
        if row is None:
            raise InboxError("not_found", 404)
        return row

    def render(self, conn, row):
        payload = json.loads(row["payload"])
        task = None
        if row["task_id"]:
            # Moving a task to another workspace must not disclose its new contents.
            card = conn.execute(
                "SELECT id,status,archived FROM cards WHERE id=? AND COALESCE(workspace_id,'')=?",
                (row["task_id"], self.workspace),
            ).fetchone()
            task = dict(card) if card else None
        return {
            **payload,
            "id": row["id"],
            "seq": row["seq"],
            "reviewed": bool(row["reviewed"]),
            "revision": row["revision"],
            "created_at": row["created_at"],
            "task_id": row["task_id"],
            "task": task,
            "receipt_mode": "manual",
        }

    def list(self, before=0):
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM announcement_inbox WHERE workspace=? AND (?=0 OR seq<?) ORDER BY seq DESC LIMIT 51",
                (self.workspace, before, before),
            ).fetchall()
            return {
                "items": [self.render(conn, r) for r in rows[:50]],
                "next_cursor": rows[49]["seq"] if len(rows) > 50 else None,
                "slack_connected": False,
            }

    def receive(self, payload: ReceiveAnnouncement):
        data = payload.model_dump(exclude={"consent"})
        serialized = json.dumps(data, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(serialized.encode()).hexdigest()
        with self.connection() as conn:
            prior = conn.execute(
                "SELECT * FROM announcement_inbox WHERE workspace=? AND simulated=? AND source_label=? AND source_key=?",
                (self.workspace, payload.simulated, payload.source_label, payload.source_key),
            ).fetchone()
            if prior:
                if prior["fingerprint"] != digest:
                    raise InboxError("source_conflict")
                return {"item": self.render(conn, prior), "duplicate": True}
            item_id = uuid4().hex
            conn.execute(
                "INSERT INTO announcement_inbox(id,workspace,simulated,source_label,source_key,fingerprint,payload,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    item_id,
                    self.workspace,
                    payload.simulated,
                    payload.source_label,
                    payload.source_key,
                    digest,
                    serialized,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            return {"item": self.render(conn, self.row(conn, item_id)), "duplicate": False}

    def review(self, item_id, change: ReviewAnnouncement):
        with self.connection() as conn:
            row = self.row(conn, item_id)
            if row["revision"] != change.revision:
                raise InboxError("stale_revision")
            conn.execute(
                "UPDATE announcement_inbox SET reviewed=?,revision=revision+1 WHERE id=?",
                (change.reviewed, item_id),
            )
            return self.render(conn, self.row(conn, item_id))

    def convert(self, item_id, change: ConvertAnnouncement):
        with self.connection() as conn:
            row = self.row(conn, item_id)
            if row["task_id"]:
                # A retry after an uncertain response returns the same task; never recreates it.
                return self.render(conn, row)
            if row["revision"] != change.revision:
                raise InboxError("stale_revision")
            payload = json.loads(row["payload"])
            task_id, now = uuid4().hex, datetime.now(timezone.utc).isoformat()
            title = ("[Synthetic] " if payload["simulated"] else "") + payload["title"]
            conn.execute(
                "INSERT INTO cards(id,title,note,status,archived,created_at,updated_at,workspace_id,due_date) VALUES(?,?,?,'todo',0,?,?,?,?)",
                (
                    task_id,
                    title,
                    "Inbox source: " + item_id,
                    now,
                    now,
                    self.workspace,
                    payload["due_date"],
                ),
            )
            conn.execute(
                "UPDATE announcement_inbox SET task_id=?,revision=revision+1 WHERE id=?",
                (task_id, item_id),
            )
            self.board._changed(conn)
            return self.render(conn, self.row(conn, item_id))

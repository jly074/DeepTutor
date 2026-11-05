"""Reviewed, receipt-verified task summaries; never remote synchronization."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from deeptutor.services.task_detail import InboxError, digest


class ExportHandoff(BaseModel):
    model_config = ConfigDict(extra="forbid")
    consent: Literal[True]
    next_step: str = Field(default="", max_length=500)
    reference_ids: list[int] = Field(default_factory=list, max_length=20)


class HandoffSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["deeptutor-task-handoff-v1"]
    id: str = Field(max_length=36)
    issuer: str = Field(max_length=36)
    task_id: str = Field(max_length=100)
    version: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["todo", "doing", "done"]
    issued_at: str = Field(max_length=40)
    expires_at: str = Field(max_length=40)
    next_step: str = Field(max_length=500)
    reference_ids: list[int] = Field(max_length=20)


class ImportHandoff(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: HandoffSummary
    confirm: bool = False


class TaskHandoff:
    def __init__(self, detail):
        self.detail = detail

    @contextmanager
    def connection(self, task_id):
        with self.detail.connection() as conn:
            card = self.detail.card(conn, task_id)
            conn.execute(
                "CREATE TABLE IF NOT EXISTS task_handoff_issuer (singleton INTEGER PRIMARY KEY CHECK(singleton=1),id TEXT NOT NULL)"
            )
            conn.execute("INSERT OR IGNORE INTO task_handoff_issuer VALUES(1,?)", (str(uuid4()),))
            conn.execute("""CREATE TABLE IF NOT EXISTS task_handoffs (
                id TEXT PRIMARY KEY,task_id TEXT NOT NULL,workspace TEXT NOT NULL,
                payload TEXT NOT NULL,accepted_at TEXT)""")
            yield conn, card

    def version(self, conn, card):
        # Includes private state only in an opaque digest, never in the exported file.
        state = {"task": card.model_dump(mode="json")}
        for table in ("task_source_links", "task_deadline_history", "announcement_inbox"):
            state[table] = [
                dict(row)
                for row in conn.execute(
                    f"SELECT * FROM {table} WHERE task_id=? AND workspace=? ORDER BY seq",
                    (card.id, self.detail.workspace),
                )
            ]
        return digest(state)

    def export(self, task_id, request: ExportHandoff):
        with self.connection(task_id) as (conn, card):
            if card.archived:
                raise InboxError("task_archived")
            references = sorted(set(request.reference_ids))
            valid = {
                row[0]
                for row in conn.execute(
                    "SELECT seq FROM task_source_links WHERE task_id=? AND workspace=?",
                    (task_id, self.detail.workspace),
                )
            }
            if not set(references) <= valid:
                raise InboxError("source_unavailable")
            now = datetime.now(timezone.utc)
            summary = HandoffSummary(
                format="deeptutor-task-handoff-v1",
                id=str(uuid4()),
                issuer=conn.execute("SELECT id FROM task_handoff_issuer").fetchone()[0],
                task_id=task_id,
                version=self.version(conn, card),
                status=card.status,
                issued_at=now.isoformat(),
                expires_at=(now + timedelta(days=7)).isoformat(),
                next_step=request.next_step.strip(),
                reference_ids=references,
            ).model_dump(mode="json")
            conn.execute(
                "INSERT INTO task_handoffs VALUES(?,?,?,?,NULL)",
                (summary["id"], task_id, self.detail.workspace, json.dumps(summary)),
            )
            return summary

    def receive(self, task_id, request: ImportHandoff):
        payload = request.summary.model_dump(mode="json")
        with self.connection(task_id) as (conn, card):
            row = conn.execute(
                "SELECT * FROM task_handoffs WHERE id=? AND task_id=? AND workspace=?",
                (payload["id"], task_id, self.detail.workspace),
            ).fetchone()
            # Matching an account-scoped issued receipt is required; an ID is not authority.
            if row is None or json.loads(row["payload"]) != payload:
                raise InboxError("handoff_unverified")
            if datetime.fromisoformat(payload["expires_at"]) <= datetime.now(timezone.utc):
                raise InboxError("handoff_expired")
            if card.archived or payload["version"] != self.version(conn, card):
                raise InboxError("handoff_stale")
            accepted_at = row["accepted_at"]
            if request.confirm and accepted_at is None:
                accepted_at = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    "UPDATE task_handoffs SET accepted_at=? WHERE id=?",
                    (accepted_at, payload["id"]),
                )
            return {"summary": payload, "verified": True, "accepted_at": accepted_at}

    def history(self, task_id):
        with self.connection(task_id) as (conn, card):
            version = self.version(conn, card)
            rows = conn.execute(
                "SELECT * FROM task_handoffs WHERE task_id=? AND workspace=? AND accepted_at IS NOT NULL ORDER BY accepted_at DESC LIMIT 50",
                (task_id, self.detail.workspace),
            ).fetchall()
            return {
                "items": [
                    {
                        "summary": json.loads(row["payload"]),
                        "accepted_at": row["accepted_at"],
                        "current": json.loads(row["payload"])["version"] == version,
                    }
                    for row in rows
                ]
            }

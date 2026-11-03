"""User-selected evidence for existing tasks. No external requests or guessed matching."""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from deeptutor.services.announcement_inbox import AnnouncementInbox, InboxError
from deeptutor.services.drive_source.service import get_drive_sources
from deeptutor.services.notion_source.service import get_notion_sources
from deeptutor.services.task_board import TaskCard


class LinkEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["drive", "notion"]
    mode: Literal["live", "demo"]
    source_id: str = Field(min_length=1, max_length=200)
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class AdoptDeadline(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: Literal[True]
    announcement_id: str = Field(min_length=1, max_length=200)
    announcement_revision: int = Field(ge=1)
    expected_updated_at: str = Field(min_length=1, max_length=100)


def digest(source):
    return hashlib.sha256(
        json.dumps(source, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


class TaskDetail:
    def __init__(self, board, workspace):
        self.board, self.workspace = board, workspace
        self.inbox = AnnouncementInbox(board, workspace)

    @contextmanager
    def connection(self):
        with self.inbox.connection() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS task_source_links (
              seq INTEGER PRIMARY KEY AUTOINCREMENT,task_id TEXT NOT NULL,workspace TEXT NOT NULL,
              provider TEXT NOT NULL, mode TEXT NOT NULL, source_id TEXT NOT NULL,
              fingerprint TEXT NOT NULL, snapshot TEXT NOT NULL, created_at TEXT NOT NULL,
              UNIQUE(task_id,workspace,provider,mode,source_id,fingerprint))""")
            yield conn

    def card(self, conn, task_id):
        row = conn.execute(
            "SELECT * FROM cards WHERE id=? AND COALESCE(workspace_id,'')=?",
            (task_id, self.workspace),
        ).fetchone()
        if row is None:
            raise InboxError("not_found", 404)
        return TaskCard.model_validate(dict(row))

    @staticmethod
    def candidates(provider, mode):
        service = get_drive_sources(mode) if provider == "drive" else get_notion_sources(mode)
        # saved() is local scoped storage, never a provider query.
        return service.state, service.saved()

    def choices(self, task_id):
        with self.connection() as conn:
            self.card(conn, task_id)
            rows = conn.execute(
                "SELECT * FROM announcement_inbox WHERE workspace=? AND (task_id IS NULL OR task_id=?) ORDER BY seq DESC LIMIT 101",
                (self.workspace, task_id),
            ).fetchall()
            announcements = [self.inbox.render(conn, r) for r in rows[:100]]
        sources, states = [], []
        for provider in ("drive", "notion"):
            for mode in ("live", "demo"):
                try:
                    state, saved = self.candidates(provider, mode)
                    states.append(
                        {
                            "provider": provider,
                            "mode": mode,
                            "state": state,
                            "limited": len(saved) > 100,
                        }
                    )
                    for source in saved[:100]:
                        snap = source.model_dump(mode="json")
                        sources.append(
                            {
                                "provider": provider,
                                "mode": mode,
                                "source_id": source.id,
                                "label": source.label,
                                "fingerprint": digest(snap),
                            }
                        )
                except Exception:
                    # Independent local stores may be unavailable; never expose raw paths/secrets.
                    states.append(
                        {
                            "provider": provider,
                            "mode": mode,
                            "state": "unavailable",
                            "limited": False,
                        }
                    )
        return {
            "announcement_limited": len(rows) > 100,
            "sources": sources,
            "states": states,
            "announcements": announcements,
            "matching": "manual_selection_only",
            "slack": "no_verified_automatic_intake",
        }

    def link(self, task_id, choice: LinkEvidence):
        with self.connection() as conn:
            card = self.card(conn, task_id)
            if card.archived:
                raise InboxError("task_archived")
        _, saved = self.candidates(choice.provider, choice.mode)
        source = next((s for s in saved if s.id == choice.source_id), None)
        if source is None:
            raise InboxError("source_unavailable", 404)
        snapshot = source.model_dump(mode="json")
        if digest(snapshot) != choice.fingerprint:
            raise InboxError("source_changed")
        if bool(source.metadata.get("simulated")) != (choice.mode == "demo"):
            raise InboxError("source_changed")
        with self.connection() as conn:
            if self.card(conn, task_id).archived:
                raise InboxError("task_archived")
            count = conn.execute(
                "SELECT COUNT(*) FROM (SELECT DISTINCT provider,mode,source_id FROM task_source_links WHERE task_id=? AND workspace=?)",
                (task_id, self.workspace),
            ).fetchone()[0]
            existing = conn.execute(
                "SELECT 1 FROM task_source_links WHERE task_id=? AND workspace=? AND provider=? AND mode=? AND source_id=?",
                (task_id, self.workspace, choice.provider, choice.mode, choice.source_id),
            ).fetchone()
            if count >= 20 and not existing:
                raise InboxError("link_limit")
            conn.execute(
                "INSERT OR IGNORE INTO task_source_links(task_id,workspace,provider,mode,source_id,fingerprint,snapshot,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    task_id,
                    self.workspace,
                    choice.provider,
                    choice.mode,
                    source.id,
                    choice.fingerprint,
                    json.dumps(snapshot, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        return self.read(task_id)

    def adopt(self, task_id, change: AdoptDeadline):
        with self.connection() as conn:
            card = self.card(conn, task_id)
            if card.archived:
                raise InboxError("task_archived")
            row = self.inbox.row(conn, change.announcement_id)
            if row["task_id"] not in (None, task_id):
                raise InboxError("already_linked")
            event = "receipt:" + change.announcement_id
            used = conn.execute(
                "SELECT 1 FROM task_deadline_history WHERE task_id=? AND workspace=? AND source_event=?",
                (task_id, self.workspace, event),
            ).fetchone()
            if not used:
                if (
                    card.updated_at != change.expected_updated_at
                    or row["revision"] != change.announcement_revision
                ):
                    raise InboxError("stale_revision")
                payload = json.loads(row["payload"])
                conn.execute(
                    "UPDATE cards SET due_date=?,updated_at=? WHERE id=?",
                    (payload["due_date"], datetime.now(timezone.utc).isoformat(), task_id),
                )
                conn.execute(
                    "UPDATE announcement_inbox SET task_id=?,revision=revision+1 WHERE id=?",
                    (task_id, row["id"]),
                )
                self.board.record_deadline(
                    conn,
                    task_id,
                    self.workspace,
                    card.due_date,
                    payload["due_date"],
                    {
                        "kind": "announcement",
                        "announcement_id": row["id"],
                        "source_label": payload["source_label"],
                        "source_key": payload["source_key"],
                        "source_url": payload["source_url"],
                        "simulated": payload["simulated"],
                    },
                    event,
                )
                self.board._changed(conn)
        return self.read(task_id)

    def read(self, task_id):
        with self.connection() as conn:
            card = self.card(conn, task_id)
            rows = conn.execute(
                "SELECT * FROM announcement_inbox WHERE workspace=? AND task_id=? ORDER BY seq",
                (self.workspace, task_id),
            ).fetchall()
            announcements = [self.inbox.render(conn, r) for r in rows]
            links = []
            rows = conn.execute(
                """SELECT * FROM task_source_links WHERE seq IN (
              SELECT MAX(seq) FROM task_source_links WHERE task_id=? AND workspace=? GROUP BY provider,mode,source_id) ORDER BY seq""",
                (task_id, self.workspace),
            ).fetchall()
            for row in rows:
                snapshot = json.loads(row["snapshot"])
                meta = snapshot["metadata"]
                href = None
                if row["mode"] == "live":
                    if row["provider"] == "drive" and re.fullmatch(
                        r"[A-Za-z0-9_-]{1,200}", str(meta.get("file_id", ""))
                    ):
                        href = "https://drive.google.com/file/d/" + meta["file_id"] + "/view"
                    elif row["provider"] == "notion":
                        try:
                            href = (
                                "https://www.notion.so/" + UUID(meta.get("notion_page_id", "")).hex
                            )
                        except (ValueError, TypeError, AttributeError):
                            pass
                links.append(
                    {
                        "id": row["seq"],
                        "provider": row["provider"],
                        "mode": row["mode"],
                        "snapshot": snapshot,
                        "linked_at": row["created_at"],
                        "open_url": href,
                        "access": "synthetic" if row["mode"] == "demo" else "saved_not_revalidated",
                    }
                )
            history = [
                {**dict(r), "basis": json.loads(r["basis"])}
                for r in conn.execute(
                    "SELECT * FROM task_deadline_history WHERE task_id=? AND workspace=? ORDER BY seq",
                    (task_id, self.workspace),
                )
            ]
        next_steps = []
        if not announcements:
            next_steps.append({"code": "confirm_announcement", "evidence_ids": []})
        if card.due_date is None:
            next_steps.append(
                {"code": "confirm_deadline", "evidence_ids": [a["id"] for a in announcements]}
            )
        elif not history or history[-1]["basis"].get("kind") != "announcement":
            next_steps.append(
                {
                    "code": "verify_manual_deadline",
                    "evidence_ids": [str(history[-1]["seq"])] if history else [],
                }
            )
        drive = [str(link["id"]) for link in links if link["provider"] == "drive"]
        notion = [str(link["id"]) for link in links if link["provider"] == "notion"]
        next_steps.append(
            {
                "code": "open_selected_material" if drive else "select_material",
                "evidence_ids": drive,
            }
        )
        next_steps.append(
            {
                "code": "review_progress_snapshot" if notion else "select_progress",
                "evidence_ids": notion,
            }
        )
        return {
            "task": card,
            "announcements": announcements,
            "links": links,
            "deadline_history": history,
            "next_steps": next_steps,
            "matching": "manual_selection_only",
            "slack": "no_verified_automatic_intake",
        }

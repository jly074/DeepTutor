"""Selected Notion property snapshots in the existing workspace session database.

This ledger stores source versions, not another task/mastery/learning database.
No learning evidence, mastery estimate, task completion or Notion write is produced.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

from deeptutor.core.identities import is_partner_user_id
from deeptutor.learning.models import TopicSource, TopicSourceKind
from deeptutor.multi_user.context import get_current_user
from deeptutor.services.workspace.context import current_workspace_id

from .client import (
    DEMO_SOURCE,
    DemoNotionClient,
    NotionClient,
    NotionFailure,
    notion_id,
    parse_row,
    selected_properties,
)


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True)
class Binding:
    owner: str
    workspace: str
    source: str = ""
    simulated: bool = False
    configured: bool = False


class NotionSources:
    def __init__(self, path: Path, binding: Binding, client=None):
        self.path, self.binding, self.client = path, binding, client

    def scope(self):
        user = get_current_user()
        if (
            self.binding.owner != user.scope.user_id
            or self.binding.workspace != current_workspace_id()
            or is_partner_user_id(user.id)
        ):
            raise NotionFailure("access_denied", 403)

    @property
    def state(self):
        self.scope()
        if not self.binding.simulated and get_current_user().id == "local-admin":
            return "authentication_required"
        if not self.binding.configured:
            return "not_configured"
        return "simulated" if self.binding.simulated else "configured_not_verified"

    def require(self):
        state = self.state
        if state not in ("simulated", "configured_not_verified") or self.client is None:
            raise NotionFailure(state, 409)

    @contextmanager
    def db(self):
        self.scope()
        conn = None
        try:
            conn = sqlite3.connect(self.path, timeout=5)
            conn.execute("""CREATE TABLE IF NOT EXISTS notion_source_snapshots (
              seq INTEGER PRIMARY KEY AUTOINCREMENT,owner TEXT NOT NULL,workspace TEXT NOT NULL,
              mode TEXT NOT NULL,data_source_id TEXT NOT NULL,page_id TEXT NOT NULL,
              fingerprint TEXT NOT NULL,source_json TEXT NOT NULL,imported_at REAL NOT NULL,
              UNIQUE(owner,workspace,mode,data_source_id,page_id,fingerprint))""")
            with conn:
                yield conn
        except sqlite3.Error:
            raise NotionFailure("storage_unavailable", 409) from None
        finally:
            if conn is not None:
                conn.close()

    @property
    def mode(self):
        return "demo" if self.binding.simulated else "live"

    def saved(self):
        self.scope()
        with self.db() as conn:
            rows = conn.execute(
                """SELECT source_json FROM notion_source_snapshots WHERE seq IN (
              SELECT MAX(seq) FROM notion_source_snapshots WHERE owner=? AND workspace=? AND mode=?
              GROUP BY data_source_id,page_id) ORDER BY seq DESC""",
                (self.binding.owner, self.binding.workspace, self.mode),
            ).fetchall()
        return [TopicSource.model_validate_json(row[0]) for row in rows]

    async def schema(self):
        self.require()
        return await self.client.schema()

    async def preview(self, selected, cursor=""):
        self.require()
        chosen = selected_properties(await self.client.schema(), selected)
        raw = await self.client.query(selected, cursor)
        try:
            if raw.get("request_status", {}).get("type") == "incomplete":
                raise NotionFailure("incomplete_query", 409)
            if (
                raw.get("object") != "list"
                or not isinstance(raw.get("results"), list)
                or len(raw["results"]) > 25
            ):
                raise ValueError()
            more = raw["has_more"]
            next_cursor = raw.get("next_cursor")
            if not isinstance(more, bool) or (
                more
                and (
                    not isinstance(next_cursor, str)
                    or not next_cursor
                    or next_cursor == cursor
                    or len(next_cursor) > 2048
                )
            ):
                raise ValueError()
            rows = []
            seen = set()
            for record in raw["results"]:
                row = parse_row(record, self.binding.source, chosen)
                if row.page_id in seen:
                    raise NotionFailure("inconsistent_query", 409)
                seen.add(row.page_id)
                row.fingerprint = fingerprint(
                    {
                        "source": self.binding.source,
                        "selected": sorted(selected),
                        "row": row.model_dump(exclude={"fingerprint"}),
                    }
                )
                rows.append(row)
            return {
                "rows": rows,
                "next_cursor": next_cursor if more else None,
                "has_more": more,
                "simulated": self.binding.simulated,
            }
        except NotionFailure:
            raise
        except (ValueError, TypeError, KeyError, AttributeError):
            raise NotionFailure("invalid_response", 502) from None

    async def import_row(self, page_id, selected, expected, cursor=""):
        # Re-query only the allowed source, never fetch arbitrary page IDs supplied by a client.
        page_id = notion_id(page_id)
        preview = await self.preview(selected, cursor)
        row = next((r for r in preview["rows"] if r.page_id == page_id), None)
        if row is None:
            raise NotionFailure("row_moved_or_missing", 409)
        if row.issues:
            raise NotionFailure("incomplete_properties", 409)
        if row.fingerprint != expected:
            raise NotionFailure("source_changed", 409)
        b = self.binding
        identity = fingerprint([b.owner, b.workspace, self.mode, b.source, row.page_id])
        source = TopicSource(
            id="notion_" + identity,
            kind=TopicSourceKind.FILE,
            source_id="notion:" + row.page_id,
            label=row.title,
            available=False,
            excerpt="",
            metadata={
                "provider": "notion",
                "metadata_only": True,
                "snapshot_only": True,
                "simulated": b.simulated,
                "data_source_id": b.source,
                "notion_page_id": row.page_id,
                "last_edited_time": row.edited_at,
                "fingerprint": row.fingerprint,
                "fields": row.fields,
            },
        )
        with self.db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO notion_source_snapshots(owner,workspace,mode,data_source_id,page_id,fingerprint,source_json,imported_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    b.owner,
                    b.workspace,
                    self.mode,
                    b.source,
                    row.page_id,
                    row.fingerprint,
                    source.model_dump_json(),
                    time.time(),
                ),
            )
            # Repeated import returns the persisted identity/timestamp, not a fabricated new row.
            stored = conn.execute(
                "SELECT source_json FROM notion_source_snapshots WHERE owner=? AND workspace=? AND mode=? AND data_source_id=? AND page_id=? AND fingerprint=?",
                (b.owner, b.workspace, self.mode, b.source, row.page_id, row.fingerprint),
            ).fetchone()
        return TopicSource.model_validate_json(stored[0])


def get_notion_sources(mode="live"):
    from deeptutor.services.session import get_sqlite_session_store

    user = get_current_user()
    workspace = current_workspace_id()
    owner = user.scope.user_id
    if mode == "demo":
        binding = Binding(owner, workspace, DEMO_SOURCE, True, True)
        return NotionSources(get_sqlite_session_store().db_path, binding, DemoNotionClient())
    # No secret setup endpoint: configuration must come from separately approved provisioning.
    # A global connection is never inherited by an arbitrary account or workspace.
    matched = (
        user.id != "local-admin"
        and os.environ.get("DEEPTUTOR_NOTION_OWNER_ID") == owner
        and os.environ.get("DEEPTUTOR_NOTION_WORKSPACE_ID") == workspace
    )
    token = os.environ.get("DEEPTUTOR_NOTION_READ_TOKEN", "") if matched else ""
    source = os.environ.get("DEEPTUTOR_NOTION_DATA_SOURCE_ID", "") if matched else ""
    if source:
        try:
            source = notion_id(source)
        except NotionFailure:
            source = ""
    configured = bool(token and source)
    binding = Binding(owner, workspace, source if configured else "", False, configured)
    return NotionSources(
        get_sqlite_session_store().db_path,
        binding,
        NotionClient(token, source) if configured else None,
    )

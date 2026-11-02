"""Workspace-scoped reference persistence in the existing session database."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from deeptutor.learning.models import TopicSource, TopicSourceKind
from deeptutor.multi_user.context import get_current_user
from deeptutor.services.workspace.context import current_workspace_id

from .client import FOLDER, ID_PATTERN, SHORTCUT, DemoDriveClient, DriveFailure, DriveFile


@dataclass(frozen=True)
class DriveConnection:
    owner: str
    workspace: str
    connection_id: str
    allowed_folders: tuple[str, ...] = ()
    configured: bool = False
    authorized: bool = False
    simulated: bool = False


class DriveSources:
    def __init__(self, db_path: Path, connection: DriveConnection, client=None):
        self.db_path, self.connection, self.client = db_path, connection, client

    def assert_scope(self):
        if (
            self.connection.owner != get_current_user().scope.user_id
            or self.connection.workspace != current_workspace_id()
        ):
            raise DriveFailure("access_denied", 403)

    @property
    def state(self):
        self.assert_scope()
        c = self.connection
        if not c.configured:
            return "not_connected"
        if not c.authorized:
            return "needs_authorization"
        if self.client is None:
            return "blocked"
        return "mock" if c.simulated else "queryable"

    @contextmanager
    def _connect(self):
        self.assert_scope()
        conn = sqlite3.connect(self.db_path)
        conn.execute("""CREATE TABLE IF NOT EXISTS drive_source_refs (
            owner TEXT NOT NULL, workspace TEXT NOT NULL, connection_id TEXT NOT NULL,
            file_id TEXT NOT NULL, source_json TEXT NOT NULL,
            PRIMARY KEY(owner, workspace, connection_id, file_id))""")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def saved(self) -> list[TopicSource]:
        c = self.connection
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT source_json FROM drive_source_refs WHERE owner=? AND workspace=? AND connection_id=? ORDER BY file_id",
                (c.owner, c.workspace, c.connection_id),
            ).fetchall()
        return [TopicSource.model_validate_json(row[0]) for row in rows]

    def _allow(self, folder: str):
        self.assert_scope()
        if not re.fullmatch(ID_PATTERN, folder):
            raise DriveFailure("invalid_folder", 422)
        if folder not in self.connection.allowed_folders:
            raise DriveFailure("access_denied", 403)
        if self.state in ("not_connected", "needs_authorization"):
            raise DriveFailure("needs_authorization", 401)
        if self.state == "blocked":
            raise DriveFailure("unavailable", 503)

    async def listing(self, folder: str) -> list[DriveFile]:
        self._allow(folder)
        files, tokens = {}, set()
        token = ""
        for _ in range(5):
            page = await self.client.list_page(folder, token)
            if page.incompleteSearch:
                raise DriveFailure("incomplete_listing", 409)
            for item in page.files:
                if (
                    folder in item.parents
                    and not item.trashed
                    and item.mimeType not in (FOLDER, SHORTCUT)
                ):
                    files[item.id] = item
            token = page.nextPageToken
            if not token:
                return sorted(files.values(), key=lambda item: (item.name, item.id))
            if token in tokens:
                raise DriveFailure("invalid_response", 502)
            tokens.add(token)
        # Do not present a truncated result as a complete folder listing.
        raise DriveFailure("listing_limit", 409)

    async def select(self, folder: str, file_id: str) -> TopicSource:
        # Never trust a filename, URL or metadata supplied by the browser.
        item = next((item for item in await self.listing(folder) if item.id == file_id), None)
        if item is None:
            raise DriveFailure("not_found", 404)
        c = self.connection
        identity = hashlib.sha256(
            json.dumps([c.owner, c.workspace, c.connection_id, item.id]).encode()
        ).hexdigest()
        source = TopicSource(
            id=f"drive_{identity}",
            kind=TopicSourceKind.FILE,
            source_id=f"drive:{item.id}",
            label=item.name,
            available=False,
            excerpt="",
            metadata={
                "provider": "google_drive",
                "metadata_only": True,
                "simulated": c.simulated,
                "connection_id": c.connection_id,
                "folder_id": folder,
                "file_id": item.id,
                "mime_type": item.mimeType,
                "modified_time": item.modifiedTime,
                "version": item.version,
            },
        )
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO drive_source_refs VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(owner,workspace,connection_id,file_id)
                DO UPDATE SET source_json=excluded.source_json""",
                (c.owner, c.workspace, c.connection_id, item.id, source.model_dump_json()),
            )
        return source


def get_drive_sources(mode: str = "live") -> DriveSources:
    from deeptutor.services.session import get_sqlite_session_store

    demo = mode == "demo"
    connection = DriveConnection(
        owner=get_current_user().scope.user_id,
        workspace=current_workspace_id(),
        connection_id="synthetic-demo" if demo else "google-drive-unconfigured",
        allowed_folders=("demo-course",) if demo else (),
        configured=demo,
        authorized=demo,
        simulated=demo,
    )
    return DriveSources(
        get_sqlite_session_store().db_path, connection, DemoDriveClient() if demo else None
    )

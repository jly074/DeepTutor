"""Bounded read-only Drive transport and a separate synthetic provider."""

from __future__ import annotations

from typing import Callable

import httpx
from pydantic import BaseModel, Field

ID_PATTERN = r"^[A-Za-z0-9_-]{1,200}$"
FOLDER = "application/vnd.google-apps.folder"
SHORTCUT = "application/vnd.google-apps.shortcut"


class DriveFailure(Exception):
    def __init__(self, code: str, status: int = 409):
        self.code, self.status = code, status
        super().__init__(code)


class DriveFile(BaseModel):
    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=255)
    mimeType: str = Field(min_length=1, max_length=128)
    parents: list[str] = Field(default_factory=list, max_length=100)
    trashed: bool = False
    modifiedTime: str = Field(default="", max_length=64)
    version: str = Field(default="", max_length=64)


class DrivePage(BaseModel):
    files: list[DriveFile] = Field(default_factory=list, max_length=100)
    nextPageToken: str = Field(default="", max_length=2048)
    incompleteSearch: bool = False


class GoogleDriveClient:
    """Only files.list metadata; token injection from the owner/workspace OAuth store.

    No content download, write operation, recursive scan or automatic refresh.
    """

    def __init__(self, token: Callable[[], str | None], transport=None, on_unauthorized=None):
        self.token, self.transport = token, transport
        self.on_unauthorized = on_unauthorized

    async def list_page(self, folder: str, page_token: str = "") -> DrivePage:
        # Validate again at the transport boundary, before obtaining a token.
        import re

        if not re.fullmatch(ID_PATTERN, folder):
            raise DriveFailure("invalid_folder", 422)
        token = self.token()
        if not token:
            raise DriveFailure("needs_authorization", 401)
        params = {
            "q": f"'{folder}' in parents and trashed = false",
            "fields": "nextPageToken,incompleteSearch,files(id,name,mimeType,parents,trashed,modifiedTime,version)",
            "pageSize": "100",
            "spaces": "drive",
        }
        if page_token:
            params["pageToken"] = page_token
        try:
            async with httpx.AsyncClient(
                timeout=10, transport=self.transport, follow_redirects=False
            ) as client:
                response = await client.get(
                    "https://www.googleapis.com/drive/v3/files",
                    params=params,
                    headers={"Authorization": f"Bearer {token}"},
                )
        except httpx.TimeoutException:
            raise DriveFailure("timeout", 504) from None
        except httpx.HTTPError:
            raise DriveFailure("unavailable", 503) from None
        errors = {
            401: "needs_authorization",
            403: "access_denied",
            404: "not_found",
            429: "rate_limited",
        }
        if response.status_code == 401 and self.on_unauthorized is not None:
            self.on_unauthorized()
        if response.status_code in errors:
            raise DriveFailure(errors[response.status_code], response.status_code)
        if response.status_code != 200:
            raise DriveFailure("unavailable", 503)
        try:
            return DrivePage.model_validate(response.json())
        except ValueError:
            raise DriveFailure("invalid_response", 502) from None


class DemoDriveClient:
    """No network calls. All names, IDs and dates are synthetic."""

    async def list_page(self, folder: str, page_token: str = "") -> DrivePage:
        if folder != "demo-course" or page_token not in ("", "demo-page-2"):
            raise DriveFailure("access_denied", 403)
        first = DriveFile(
            id="demo-file-1",
            name="Synthetic lesson.pdf",
            mimeType="application/pdf",
            parents=[folder],
            version="1",
            modifiedTime="2026-01-01T00:00:00Z",
        )
        if not page_token:
            return DrivePage(files=[first], nextPageToken="demo-page-2")
        return DrivePage(
            files=[
                first,
                DriveFile(
                    id="demo-file-2",
                    name="Synthetic exercise.pdf",
                    mimeType="application/pdf",
                    parents=[folder],
                    version="2",
                ),
            ]
        )

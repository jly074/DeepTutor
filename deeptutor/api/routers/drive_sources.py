"""Manual metadata-only Drive references and explicit personal OAuth lifecycle."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from deeptutor.learning.models import TopicSource
from deeptutor.services.drive_source.client import ID_PATTERN, DriveFailure, DriveFile
from deeptutor.services.drive_source.service import get_drive_sources

router = APIRouter()
Mode = Literal["live", "demo"]


class DriveOverview(BaseModel):
    state: Literal["not_connected", "needs_authorization", "mock", "queryable", "blocked"]
    simulated: bool
    allowed_folders: list[str]
    sources: list[TopicSource]


class DriveSelection(BaseModel):
    folder_id: str = Field(pattern=ID_PATTERN)
    file_id: str = Field(pattern=ID_PATTERN)


def failure(exc: DriveFailure):
    return HTTPException(
        exc.status,
        detail={
            "state": "needs_authorization" if exc.code == "needs_authorization" else "blocked",
            "code": exc.code,
        },
    )


@router.get("", response_model=DriveOverview)
def overview(mode: Mode = "live"):
    try:
        service = get_drive_sources(mode)
        return DriveOverview(
            state=service.state,
            simulated=service.connection.simulated,
            allowed_folders=list(service.connection.allowed_folders),
            sources=service.saved(),
        )
    except DriveFailure as exc:
        raise failure(exc) from None


@router.get("/files", response_model=list[DriveFile])
async def files(folder_id: str, mode: Mode = "live"):
    try:
        return await get_drive_sources(mode).listing(folder_id)
    except DriveFailure as exc:
        raise failure(exc) from None


@router.post("/sources", response_model=TopicSource)
async def select(payload: DriveSelection, mode: Mode = "live"):
    try:
        return await get_drive_sources(mode).select(payload.folder_id, payload.file_id)
    except DriveFailure as exc:
        raise failure(exc) from None


class OAuthStart(BaseModel):
    folder_id: str = Field(pattern=ID_PATTERN)
    browser_nonce: str = Field(pattern=r"^[A-Za-z0-9_-]{32,200}$")
    consent: Literal[True]


class OAuthComplete(BaseModel):
    state: str = Field(min_length=1, max_length=200)
    browser_nonce: str = Field(min_length=32, max_length=200)
    code: str = Field(default="", max_length=8192)
    error: str = Field(default="", max_length=200)


@router.get("/oauth/status")
def oauth_status():
    from deeptutor.services.drive_source.oauth import get_drive_oauth

    try:
        return get_drive_oauth().status()
    except DriveFailure as exc:
        raise failure(exc) from None


@router.post("/oauth/start")
def oauth_start(payload: OAuthStart, request: Request):
    from deeptutor.services.drive_source.oauth import get_drive_oauth

    try:
        return get_drive_oauth().start(
            payload.folder_id, payload.browser_nonce, request.headers.get("origin", "")
        )
    except DriveFailure as exc:
        raise failure(exc) from None


@router.post("/oauth/complete")
async def oauth_complete(payload: OAuthComplete, request: Request):
    from deeptutor.services.drive_source.oauth import get_drive_oauth

    try:
        return await get_drive_oauth().complete(
            payload.state,
            payload.browser_nonce,
            payload.code,
            payload.error,
            request.headers.get("origin", ""),
        )
    except DriveFailure as exc:
        raise failure(exc) from None


@router.post("/oauth/disconnect")
def oauth_disconnect(request: Request):
    from deeptutor.services.drive_source.oauth import get_drive_oauth

    try:
        return get_drive_oauth().disconnect(request.headers.get("origin", ""))
    except DriveFailure as exc:
        raise failure(exc) from None

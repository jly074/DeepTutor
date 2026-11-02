"""Manual metadata-only Drive reference flow; real login is not configured here."""

from typing import Literal

from fastapi import APIRouter, HTTPException
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

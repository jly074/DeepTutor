"""User-selected Notion property reads and local snapshots; no Notion mutations."""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from deeptutor.services.notion_source.client import NotionFailure
from deeptutor.services.notion_source.service import get_notion_sources

router = APIRouter()
Mode = Literal["live", "demo"]


class ReadConsent(BaseModel):
    consent: Literal[True]


class Preview(ReadConsent):
    property_ids: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(
        min_length=1, max_length=10
    )
    cursor: str = Field(default="", max_length=2048)


class Import(Preview):
    page_id: str = Field(min_length=32, max_length=36)
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


def fail(exc):
    return HTTPException(exc.status, detail={"code": exc.code})


@router.get("")
def overview(mode: Mode = "live"):
    try:
        service = get_notion_sources(mode)
        return {
            "state": service.state,
            "simulated": service.binding.simulated,
            "data_source_id": service.binding.source,
            "sources": service.saved(),
        }
    except NotionFailure as exc:
        raise fail(exc) from None


@router.post("/schema")
async def schema(payload: ReadConsent, mode: Mode = "live"):
    try:
        return {"properties": await get_notion_sources(mode).schema()}
    except NotionFailure as exc:
        raise fail(exc) from None


@router.post("/preview")
async def preview(payload: Preview, mode: Mode = "live"):
    try:
        return await get_notion_sources(mode).preview(payload.property_ids, payload.cursor)
    except NotionFailure as exc:
        raise fail(exc) from None


@router.post("/snapshots")
async def snapshot(payload: Import, mode: Mode = "live"):
    try:
        return await get_notion_sources(mode).import_row(
            payload.page_id, payload.property_ids, payload.fingerprint, payload.cursor
        )
    except NotionFailure as exc:
        raise fail(exc) from None

"""Each workspace's task board, kept in one account store.

The router sits outside request scope installation (see ``auth.py``) so its
event stream never holds a workspace activity lease; it resolves the board's
workspace from the same header/query itself.
"""

from __future__ import annotations

import asyncio

# Manual source intake shares the board's authenticated account and workspace.
import sqlite3
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from deeptutor.services.announcement_inbox import (
    AnnouncementInbox,
    ConvertAnnouncement,
    InboxError,
    ReceiveAnnouncement,
    ReviewAnnouncement,
)
from deeptutor.services.drive_source.client import DriveFailure
from deeptutor.services.notion_source.client import NotionFailure
from deeptutor.services.storage.file_library import get_file_library_store
from deeptutor.services.task_board import (
    CreateCard,
    LinkStatus,
    LinkTasks,
    StatusColors,
    TaskBoard,
    UpdateCard,
    get_task_board_store,
    workspace_board,
)
from deeptutor.services.task_detail import AdoptDeadline, LinkEvidence, TaskDetail
from deeptutor.services.unsorted import CollectBatch, Unsorted
from deeptutor.services.workspace.context import workspace_context
from deeptutor.services.workspace.models import WorkspaceError

router = APIRouter()


def board_workspace(request: Request) -> str:
    raw = request.headers.get("x-deeptutor-workspace") or request.query_params.get("dt_workspace")
    try:
        with workspace_context(raw or "") as scope:
            return scope.workspace_id
    except WorkspaceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("", response_model=TaskBoard)
def get_board(request: Request) -> TaskBoard:
    return workspace_board(get_task_board_store().read(), board_workspace(request))


@router.get("/events")
async def board_events(request: Request):
    # Resolve once before streaming; each connection retains its account identity.
    workspace_id = board_workspace(request)
    store = await asyncio.to_thread(get_task_board_store)

    async def events():
        revision = -1
        heartbeat = 0
        while not await request.is_disconnected():
            current_revision = await asyncio.to_thread(store.revision)
            if current_revision != revision:
                board = workspace_board(await asyncio.to_thread(store.read), workspace_id)
                revision = board.revision
                yield f"id: {revision}\ndata: {board.model_dump_json()}\n\n"
            elif heartbeat % 30 == 0:
                yield ": heartbeat\n\n"
            heartbeat += 1
            await asyncio.sleep(0.5)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            # Next's proxy must flush each event instead of gzip-buffering it.
            "Cache-Control": "no-cache, no-transform",
            "Content-Encoding": "identity",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/cards", response_model=TaskBoard, status_code=201)
def create_card(payload: CreateCard, request: Request) -> TaskBoard:
    workspace_id = board_workspace(request)
    return workspace_board(get_task_board_store().create(payload, workspace_id), workspace_id)


@router.patch("/cards/{card_id}", response_model=TaskBoard)
def update_card(card_id: str, payload: UpdateCard, request: Request) -> TaskBoard:
    workspace_id = board_workspace(request)
    try:
        if "workspace_id" in payload.model_fields_set and payload.workspace_id is not None:
            with workspace_context(payload.workspace_id) as scope:
                payload.workspace_id = scope.workspace_id
                if scope.archived:
                    raise WorkspaceError("Restore this workspace before assigning tasks.")
        return workspace_board(
            get_task_board_store().update(card_id, payload, workspace_id=workspace_id), workspace_id
        )
    except WorkspaceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task card not found.") from exc


@router.put("/colors", response_model=TaskBoard)
def update_colors(payload: StatusColors, request: Request) -> TaskBoard:
    workspace_id = board_workspace(request)
    return workspace_board(get_task_board_store().set_colors(payload), workspace_id)


async def require_session(session_id: str, workspace_id: str, board_workspace_id: str) -> str:
    from deeptutor.services.session import get_session_store

    try:
        with workspace_context(workspace_id) as scope:
            if scope.workspace_id != board_workspace_id:
                raise HTTPException(status_code=404, detail="Conversation not found.")
            if scope.archived:
                raise WorkspaceError("Restore this workspace before changing its conversations.")
            if await get_session_store().get_session(session_id) is None:
                raise HTTPException(status_code=404, detail="Conversation not found.")
            return scope.workspace_id
    except WorkspaceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/sessions/{session_id}", response_model=TaskBoard)
async def link_tasks(session_id: str, payload: LinkTasks, request: Request) -> TaskBoard:
    workspace_id = board_workspace(request)
    payload.workspace_id = await require_session(session_id, payload.workspace_id, workspace_id)
    try:
        board = await asyncio.to_thread(get_task_board_store().link_tasks, session_id, payload)
        return workspace_board(board, workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found or archived.") from exc


@router.patch("/sessions/{session_id}/status", response_model=TaskBoard)
async def link_status(session_id: str, payload: LinkStatus, request: Request) -> TaskBoard:
    workspace_id = board_workspace(request)
    payload.workspace_id = await require_session(session_id, payload.workspace_id, workspace_id)
    board = await asyncio.to_thread(get_task_board_store().link_status, session_id, payload)
    return workspace_board(board, workspace_id)


def inbox_call(request, operation):
    try:
        inbox = AnnouncementInbox(get_task_board_store(), board_workspace(request))
        return operation(inbox)
    except InboxError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code}) from None
    except sqlite3.Error:
        raise HTTPException(409, detail={"code": "storage_unavailable"}) from None


@router.get("/inbox")
def list_inbox(request: Request, before: int = Query(default=0, ge=0, le=9223372036854775807)):
    return inbox_call(request, lambda inbox: inbox.list(before))


@router.post("/inbox")
def receive_announcement(payload: ReceiveAnnouncement, request: Request):
    return inbox_call(request, lambda inbox: inbox.receive(payload))


@router.patch("/inbox/{item_id}")
def review_announcement(item_id: str, payload: ReviewAnnouncement, request: Request):
    return inbox_call(request, lambda inbox: inbox.review(item_id, payload))


@router.post("/inbox/{item_id}/task")
def convert_announcement(item_id: str, payload: ConvertAnnouncement, request: Request):
    return inbox_call(request, lambda inbox: inbox.convert(item_id, payload))


@router.get("/cards/{card_id}/detail")
def task_detail(card_id: str, request: Request):
    return detail_call(request, lambda service: service.read(card_id))


@router.get("/cards/{card_id}/evidence-choices")
def task_evidence_choices(card_id: str, request: Request):
    return detail_call(request, lambda service: service.choices(card_id))


@router.post("/cards/{card_id}/evidence")
def task_link_evidence(card_id: str, payload: LinkEvidence, request: Request):
    return detail_call(request, lambda service: service.link(card_id, payload))


@router.post("/cards/{card_id}/deadline-source")
def task_adopt_deadline(card_id: str, payload: AdoptDeadline, request: Request):
    return detail_call(request, lambda service: service.adopt(card_id, payload))


def detail_call(request, operation):
    try:
        workspace = board_workspace(request)
        with workspace_context(workspace):
            return operation(TaskDetail(get_task_board_store(), workspace))
    except InboxError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code}) from None
    except (DriveFailure, NotionFailure):
        raise HTTPException(409, detail={"code": "source_unavailable"}) from None
    except sqlite3.Error:
        raise HTTPException(409, detail={"code": "storage_unavailable"}) from None


def intake_service(request):
    return Unsorted(get_task_board_store(), board_workspace(request), get_file_library_store())


@router.get("/intake/items")
def intake_items(request: Request, offset: int = Query(default=0, ge=0)):
    try:
        return intake_service(request).listing(offset)
    except (sqlite3.Error, OSError):
        raise HTTPException(409, detail={"code": "storage_unavailable"}) from None


@router.post("/intake/batch")
async def intake_upload(
    request: Request,
    files: list[UploadFile] = File(...),
    consent: bool = Form(False),
    data_class: Literal["synthetic", "approved_non_sensitive"] = Form(...),
    source_id: str | None = Form(None),
):
    try:
        if not consent:
            raise HTTPException(403, detail={"code": "consent_required"})
        if not 1 <= len(files) <= 10 or (source_id and len(files) != 1):
            raise HTTPException(422, detail={"code": "batch_limit"})
        service = intake_service(request)
        results, total = [], 0
        for upload in files:
            try:
                data = await upload.read(5 * 1024 * 1024 + 1)
                total += len(data)
                if total > 20 * 1024 * 1024:
                    raise InboxError("batch_size", 422)
                saved = await service.receive(upload.filename or "", data, data_class, source_id)
                results.append({"filename": upload.filename, "ok": True, **saved})
            except InboxError as exc:
                results.append({"filename": upload.filename, "ok": False, "code": exc.code})
            except (sqlite3.Error, OSError):
                results.append(
                    {"filename": upload.filename, "ok": False, "code": "storage_unavailable"}
                )
        return {"results": results}
    finally:
        for upload in files:
            await upload.close()


@router.post("/intake/collect")
def intake_collect(request: Request, payload: CollectBatch):
    try:
        return intake_service(request).collect(payload)
    except InboxError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code}) from None
    except (sqlite3.Error, OSError):
        raise HTTPException(409, detail={"code": "storage_unavailable"}) from None


@router.get("/intake/original/{version_id}")
def intake_original(request: Request, version_id: str):
    import hashlib

    try:
        service = intake_service(request)
        with service.connection() as conn:
            row = service.row(conn, version_id)
        path = service.library.resolve_path(row["library_id"])
        if path is None or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise InboxError("original_unavailable", 409)
        return FileResponse(
            path,
            filename=row["filename"],
            media_type="application/octet-stream",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )
    except InboxError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code}) from None
    except (sqlite3.Error, OSError):
        raise HTTPException(409, detail={"code": "original_unavailable"}) from None

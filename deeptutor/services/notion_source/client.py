"""Bounded Notion read transport. No search, page blocks, mutation or credential setup."""

from __future__ import annotations

import asyncio
import json
import math
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel, Field

VERSION = "2026-03-11"
SUPPORTED = {
    "title",
    "rich_text",
    "number",
    "select",
    "multi_select",
    "status",
    "date",
    "checkbox",
    "url",
    "relation",
}
DEMO_SOURCE = "11111111-1111-4111-8111-111111111111"
DEMO_PAGE = "22222222-2222-4222-8222-222222222222"


class NotionFailure(Exception):
    def __init__(self, code: str, status: int = 409):
        self.code, self.status = code, status
        super().__init__(code)


def notion_id(value: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise NotionFailure("invalid_id", 422) from None


class Property(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    name: str = Field(max_length=200)
    type: str = Field(max_length=50)
    supported: bool


class Row(BaseModel):
    page_id: str
    edited_at: str
    title: str
    fields: dict[str, Any]
    issues: list[str] = Field(default_factory=list)
    fingerprint: str = ""


def properties(raw: dict, source: str) -> list[Property]:
    try:
        if raw["object"] != "data_source" or notion_id(raw["id"]) != source:
            raise ValueError()
        result = [
            Property(id=p["id"], name=name, type=p["type"], supported=p["type"] in SUPPORTED)
            for name, p in raw["properties"].items()
        ]
        if (
            len(result) > 100
            or len({p.id for p in result}) != len(result)
            or sum(p.type == "title" for p in result) != 1
        ):
            raise ValueError()
        return result
    except (KeyError, TypeError, ValueError, AttributeError):
        raise NotionFailure("invalid_response", 502) from None


def selected_properties(schema: list[Property], selected: list[str]) -> list[Property]:
    if not selected or len(selected) > 10 or len(set(selected)) != len(selected):
        raise NotionFailure("invalid_properties", 422)
    by_id = {p.id: p for p in schema}
    if any(key not in by_id or not by_id[key].supported for key in selected):
        raise NotionFailure("unsupported_property", 422)
    result = [by_id[key] for key in selected]
    if not any(p.type == "title" for p in result):
        raise NotionFailure("title_required", 422)
    return result


def value_of(prop: dict, kind: str):
    value = prop.get(kind)
    if prop.get("type") != kind or prop.get("has_more"):
        raise ValueError()
    if kind in ("title", "rich_text"):
        if not isinstance(value, list) or len(value) >= 25:
            raise ValueError()
        # Mentions/links are kept as returned plain text, never dereferenced.
        result = "".join(item["plain_text"] for item in value)
        if len(result) > 10000:
            raise ValueError()
        return result
    if kind in ("select", "status"):
        return None if value is None else str(value["name"])
    if kind == "multi_select":
        if len(value) > 100:
            raise ValueError()
        return [str(item["name"]) for item in value]
    if kind == "number":
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError()
        return value
    if kind == "checkbox":
        if not isinstance(value, bool):
            raise ValueError()
        return value
    if kind == "date":
        return None if value is None else {k: value.get(k) for k in ("start", "end", "time_zone")}
    if kind == "url":
        if value is not None and (not isinstance(value, str) or len(value) > 2048):
            raise ValueError()
        return value
    if kind == "relation":
        if len(value) >= 25:
            raise ValueError()
        return [notion_id(item["id"]) for item in value]
    raise ValueError()


def parse_row(raw: dict, source: str, selected: list[Property]) -> Row:
    try:
        if raw.get("object") != "page" or raw.get("archived") or raw.get("in_trash"):
            raise NotionFailure("remote_missing", 404)
        if (
            raw["parent"].get("type") != "data_source_id"
            or notion_id(raw["parent"].get("data_source_id")) != source
        ):
            raise NotionFailure("wrong_parent", 403)
        page_id = notion_id(raw["id"])
        edited = raw["last_edited_time"]
        if not isinstance(edited, str) or not edited or len(edited) > 64:
            raise ValueError()
        by_id = {p["id"]: p for p in raw["properties"].values()}
        fields, issues, title = {}, [], ""
        for prop in selected:
            try:
                value = value_of(by_id[prop.id], prop.type)
                if len(json.dumps(value)) > 20000:
                    raise ValueError()
                fields[prop.id] = {"name": prop.name, "type": prop.type, "value": value}
                if prop.type == "title":
                    title = value
            except (KeyError, TypeError, ValueError, AttributeError):
                issues.append(prop.id)
        return Row(page_id=page_id, edited_at=edited, title=title, fields=fields, issues=issues)
    except NotionFailure:
        raise
    except (KeyError, TypeError, ValueError, AttributeError):
        raise NotionFailure("invalid_response", 502) from None


class NotionClient:
    def __init__(self, token: str, source: str, transport=None):
        self.token, self.source, self.transport = token, notion_id(source), transport

    async def _read(self, method, path, selected=(), body=None):
        if not self.token:
            raise NotionFailure("needs_authorization", 401)
        # Only two fixed read operations; POST is the Notion read query.
        allowed = (method == "GET" and path == f"data_sources/{self.source}") or (
            method == "POST" and path == f"data_sources/{self.source}/query"
        )
        if not allowed:
            raise NotionFailure("access_denied", 403)
        try:
            async with (
                asyncio.timeout(20),
                httpx.AsyncClient(
                    timeout=15, transport=self.transport, follow_redirects=False
                ) as client,
            ):
                async with client.stream(
                    method,
                    "https://api.notion.com/v1/" + path,
                    headers={"Authorization": "Bearer " + self.token, "Notion-Version": VERSION},
                    params=[("filter_properties", p) for p in selected],
                    json=body,
                ) as response:
                    errors = {
                        401: "needs_authorization",
                        403: "access_denied",
                        404: "missing_or_unshared",
                        429: "rate_limited",
                    }
                    if response.status_code in errors:
                        raise NotionFailure(errors[response.status_code], response.status_code)
                    if response.status_code != 200:
                        raise NotionFailure("unavailable", 503)
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > 2_000_000:
                            raise NotionFailure("response_limit", 502)
                    result = json.loads(data)
                    if not isinstance(result, dict):
                        raise ValueError()
                    return result
        except (TimeoutError, httpx.TimeoutException):
            raise NotionFailure("timeout", 504) from None
        except httpx.HTTPError:
            raise NotionFailure("unavailable", 503) from None
        except (ValueError, TypeError):
            raise NotionFailure("invalid_response", 502) from None

    async def schema(self):
        return properties(await self._read("GET", f"data_sources/{self.source}"), self.source)

    async def query(self, selected, cursor=""):
        if len(cursor) > 2048:
            raise NotionFailure("invalid_cursor", 422)
        body = {"page_size": 25, "result_type": "page", "is_archived": False}
        if cursor:
            body["start_cursor"] = cursor
        return await self._read("POST", f"data_sources/{self.source}/query", selected, body)


class DemoNotionClient:
    source = DEMO_SOURCE

    async def schema(self):
        return [
            Property(id="title", name="Topic", type="title", supported=True),
            Property(id="mastery", name="Mastery", type="number", supported=True),
            Property(id="status", name="Status", type="status", supported=True),
            Property(id="notes", name="Notes", type="rich_text", supported=True),
            Property(id="formula", name="Derived field", type="formula", supported=False),
        ]

    async def page(self, page_id, selected):
        if notion_id(page_id) != DEMO_PAGE:
            raise NotionFailure("remote_missing", 404)
        fields = {
            "Topic": {
                "id": "title",
                "type": "title",
                "title": [{"plain_text": "Synthetic concept A"}],
            },
            "Mastery": {"id": "mastery", "type": "number", "number": 42},
            "Status": {"id": "status", "type": "status", "status": {"name": "Read, not assessed"}},
            "Notes": {
                "id": "notes",
                "type": "rich_text",
                "rich_text": [{"plain_text": "Synthetic note only"}],
            },
        }
        return {
            "object": "page",
            "id": DEMO_PAGE,
            "parent": {"type": "data_source_id", "data_source_id": self.source},
            "last_edited_time": "2026-01-01T00:00:00.000Z",
            "properties": {name: p for name, p in fields.items() if p["id"] in selected},
        }

    async def query(self, selected, cursor=""):
        if cursor:
            raise NotionFailure("invalid_cursor", 422)
        return {
            "object": "list",
            "results": [await self.page(DEMO_PAGE, selected)],
            "has_more": False,
            "next_cursor": None,
        }

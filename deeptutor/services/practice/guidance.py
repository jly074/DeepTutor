"""Versioned, user-confirmed remediation; no model inference or provider calls."""

import hashlib
import json
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GuidanceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=16, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    version: int = Field(ge=0)
    quality: Literal["unknown", "ready", "missing_image", "disputed"]
    kind: Literal["unknown", "original", "recalled", "adapted", "simulated"]
    note: str = Field(default="", max_length=4000)
    reference: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def require_reference(self):
        if self.note.strip() and not self.reference.strip():
            raise ValueError("A supplementary explanation needs its source reference.")
        return self


def initialize(conn):
    conn.executescript("""CREATE TABLE IF NOT EXISTS practice_guidance (
        entry_id INTEGER PRIMARY KEY REFERENCES notebook_entries(id) ON DELETE CASCADE,
        version INTEGER NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS practice_guidance_changes (
        request_id TEXT PRIMARY KEY, entry_id INTEGER NOT NULL REFERENCES notebook_entries(id) ON DELETE CASCADE,
        payload TEXT NOT NULL, created_at REAL NOT NULL);""")


def config(conn, entry_id):
    row = conn.execute("SELECT * FROM practice_guidance WHERE entry_id=?", (entry_id,)).fetchone()
    return (
        {**json.loads(row["payload"]), "version": row["version"]}
        if row
        else {"version": 0, "quality": "unknown", "kind": "unknown", "note": "", "reference": ""}
    )


def fingerprint(entry):
    return hashlib.sha256(
        json.dumps(
            {
                k: entry[k]
                for k in (
                    "question",
                    "options_json",
                    "correct_answer",
                    "explanation",
                    "source_metadata_json",
                )
            },
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def view(conn, entry, now=None):
    now = time.time() if now is None else now
    setting = config(conn, entry["id"])
    events = [
        {**dict(r), "outcome": json.loads(r["outcome_json"])}
        for r in conn.execute(
            "SELECT * FROM practice_review_events WHERE entry_id=? ORDER BY reviewed_at, rowid",
            (entry["id"],),
        )
    ]
    current = [
        e
        for e in events
        if e["outcome"].get("evidence_fingerprint") == fingerprint(entry)
        and e["outcome"].get("guidance_version") == setting["version"]
        and not e["outcome"].get("self_report")
    ]
    wrong = [e for e in current if e["outcome"].get("correct") is False]
    state = "awaiting_evidence"
    evidence = []
    if setting["quality"] != "ready":
        state = "needs_confirmation"
    elif wrong:
        last = wrong[-1]
        due = last["outcome"]["due_at"]
        evidence = [last["request_id"]]
        later = [
            e for e in current if e["reviewed_at"] >= due and e["outcome"].get("correct") is True
        ]
        if later:
            state = "delayed_retest_correct"
            evidence.append(later[-1]["request_id"])
        else:
            state = "retest_due" if now >= due else "retest_waiting"
    elif current and current[-1]["outcome"].get("correct") is True:
        state = "correct_once"
    return {
        "config": setting,
        "status": state,
        "mastery": "not_established",
        "evidence_ids": evidence,
        "due_at": wrong[-1]["outcome"]["due_at"]
        if wrong and setting["quality"] == "ready"
        else None,
        "attempts": [
            {
                "request_id": e["request_id"],
                "answer": e["answer"],
                "at": e["reviewed_at"],
                "correct": e["outcome"].get("correct"),
                "self_report": e["outcome"].get("self_report", False),
                "current_version": e in current,
                "question_snapshot": e["outcome"].get("question_snapshot"),
            }
            for e in events
        ],
        "saved_explanation": entry["explanation"],
        "model_used": False,
    }


def update(store, entry_id, payload):
    from .storage import ReviewConflict

    with store.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        entry = conn.execute(
            "SELECT n.* FROM notebook_entries n LEFT JOIN sessions s ON s.id=n.session_id WHERE n.id=? AND (n.session_id IS NULL OR s.deleted_at IS NULL)",
            (entry_id,),
        ).fetchone()
        if entry is None:
            raise LookupError("Question not found")
        serialized = payload.model_dump_json()
        previous = conn.execute(
            "SELECT * FROM practice_guidance_changes WHERE request_id=?", (payload.request_id,)
        ).fetchone()
        if previous:
            if previous["entry_id"] != entry_id or previous["payload"] != serialized:
                raise ReviewConflict("Submission ID already used")
            return view(conn, entry)
        current = config(conn, entry_id)
        if current["version"] != payload.version:
            raise ReviewConflict("Guidance changed; reload before saving")
        data = payload.model_dump(exclude={"request_id", "version"})
        conn.execute(
            "INSERT INTO practice_guidance VALUES(?,?,?) ON CONFLICT(entry_id) DO UPDATE SET version=excluded.version,payload=excluded.payload",
            (entry_id, current["version"] + 1, json.dumps(data)),
        )
        conn.execute(
            "INSERT INTO practice_guidance_changes VALUES(?,?,?,?)",
            (payload.request_id, entry_id, serialized, time.time()),
        )
        # Invalidate an open review, including an ungraded question without state yet.
        conn.execute(
            "INSERT OR IGNORE INTO practice_review_state(entry_id,is_mistake,first_wrong_at,due_at) VALUES(?,0,?,?)",
            (entry_id, time.time(), time.time()),
        )
        conn.execute(
            "UPDATE practice_review_state SET version=version+1 WHERE entry_id=?", (entry_id,)
        )
        return view(conn, entry)

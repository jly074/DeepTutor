"""Read-only succession checklist. No scheduler, connector or notification calls."""

from datetime import datetime, timezone
import sqlite3

from deeptutor.services.task_board import workspace_board


def readiness(read_board, workspace):
    """Aggregate scoped local state without interpreting it as external readiness."""
    rows = [
        ("morning", "/kanban", "task-detail.md", ["source_freshness", "briefing", "delivery"]),
        (
            "evening",
            "/learning/unsorted",
            "unsorted-intake.md",
            ["review_evidence", "batch_sync", "delivery"],
        ),
        (
            "weekly",
            "/calendar",
            "calendar-availability.md",
            ["calendar_access", "protected_write", "reconcile"],
        ),
        (
            "slack",
            "/learning/inbox",
            "announcement-inbox.md",
            ["channel_scope", "event_receipt", "corrections"],
        ),
        (
            "tasks",
            "/kanban",
            "task-handoff.md",
            ["legacy_task_mapping", "shared_runtime", "handoff_channel"],
        ),
    ]
    counts = None
    local_state = "available"
    try:
        board = workspace_board(read_board(), workspace)
        counts = {
            state: sum(c.status == state and not c.archived for c in board.cards)
            for state in ("todo", "doing", "done")
        }
        counts["archived"] = sum(c.archived for c in board.cards)
    except (OSError, sqlite3.Error):
        local_state = "unavailable"
    return {
        "schema_version": 1,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "local_tasks": {
            "state": local_state,
            "source": "scoped_local_task_store",
            "counts": counts,
        },
        "external_sources_checked": [],
        "notification_policy": "no_activation_no_delivery",
        "rows": [
            {
                "id": key,
                "route": route,
                "evidence_doc": "docs-for-dev/learning-os/" + doc,
                "inventory_source": "requirements_and_code",
                "v2_state": "unverified",
                "v3_state": "partial_code",
                "validation_scope": "synthetic_only",
                "external_connection": "unverified",
                "sole_writer": "unconfirmed",
                "cutover_ready": False,
                "gaps": gaps + ["legacy_schedule_state", "sole_writer", "rollback"],
            }
            for key, route, doc, gaps in rows
        ],
    }

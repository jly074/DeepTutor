# Read-only automation succession inventory

Baseline `d237e554a8f12557fae461ae3cc9b263a1795ac2`. Validated 2026-11-05 with synthetic data in Linux cloud.

Open Learning > Automation succession checklist (`/learning/readiness`). This slice is a verification checklist, not an automation engine or migration. It does not query or change external accounts, schedule jobs, send messages, or select a writer.

## Evidence and authority

The server returns five responsibility rows derived from requirements and repository inventory. These are **code evidence**, not observed external connections. Related local workflows have synthetic tests; full live responsibility-level acceptance is still missing. Old schedule state, real connection and single writer remain unverified/unconfirmed, with cutover false. Unknown must not be presented as disconnected or disabled. Previously disabled jobs must not be revived merely because a replacement exists.

The only dynamic observation is aggregate counts from the authenticated account's existing task board, filtered by the resolved workspace. Archived cards are separate from active todo/doing/done counts. No task title, note, ID, provider metadata or original document is returned. Counts do not prove migration or mastery. A storage error produces null counts and unavailable state while retaining the checklist; HTTP failure clears prior observations until a successful retry. The timestamp denotes this local read only. Refresh is manual, with no polling.

| Responsibility | Reused local code | Missing acceptance | Future trigger/output |
| --- | --- | --- | --- |
| Morning briefing | Task detail sources, announcement and next-step view | Source freshness, briefing content, authorized delivery and retry | Existing schedule must be identified; reviewed briefing artifact |
| Evening consolidation | Unsorted versions/manual collection, practice evidence | Evidence distinction, approved batch sync/readback, delivery | Existing trigger must be identified; consolidated verified evidence |
| Weekly planning | Local availability/conflict calculation | Real busy intervals, protected fixed events, allowed flexible writes, reconciliation | Existing schedule must be identified; reviewed proposal before any write |
| Slack sensing | Manual announcement inbox and deduplication; channel adapter exists | Exact channel scope, actual receipt, correction handling | Authorized event/source must be verified; traceable receipt |
| Task lifecycle | Local task states and same-backend handoff receipts | Legacy stable ID mapping, shared authenticated runtime, real handoff channel | Explicit task/event scope; same task identity and verified result |

All rows also require old schedule IDs/status/disabled intent, a confirmed single writer and rollback/retry evidence. No inferred deadlines or live readiness percentage.

`services/cron/service.py` contains `CronService.list_jobs` and scheduler logic; this page **does not instantiate or invoke it**. The existence of that code proves neither registration nor delivery. `partners/channels/slack.py` likewise does not prove course intake. Old-system connector visibility and product credentials remain separate.

## Implementation and tests

- `services/automation_readiness.py`: deterministic inventory plus scoped local count aggregation, no new storage.
- `api/routers/task_board.py`: GET-only authenticated endpoint `/automation-readiness`; existing server account/workspace resolution.
- `AutomationReadiness.tsx`, API helper and native learning route/link: source distinctions, gaps, failure/retry and feature navigation. No activation controls.
- Additive generated API contract and locale keys. English fallback for locales other than Chinese; no claim of full translation.

Backend tests cover unknown/cutover invariants, unchanged board revision/state, aggregate privacy, account/workspace isolation, archived counts, unauthorized access, mutation-method rejection and storage failure. UI tests use read-function substitutes; real local API/Chromium separately verifies five rows, GET-only page traffic, unchanged board, reload and retry (503 is explicitly a browser transport substitute). Actual backend process restart preserves task state and checklist/counts, excluding the intentionally changing observed timestamp.

No production schedules, real private records or external credentials are used in tests. No true external connection, physical devices, persistent cloud execution, actual notification delivery or cutover is claimed. No user-reachable preview is configured here. Broad full-suite lint is not claimed.

## Trial and rollback

1. Open Learning > checklist; five responsibilities should show unverified legacy state, unconfirmed writer and no approved cutover.
2. Compare local workspace counts with the task board; refreshing must not change tasks, schedule jobs or send notifications.
3. Reload/restart the same isolated runtime: counts and checklist persist by re-reading the existing board. A simulated transport failure must clear stale observations; retry recovers.

Rollback: revert this feature commit in a clean checkout; no data migration or new table is involved. Keep the task runtime and earlier commits intact. Next useful work is obtaining an authorized, scope-verified old schedule inventory and a concrete read-only comparison for one responsibility; no cutover without separate approval.

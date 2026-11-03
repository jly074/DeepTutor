# Native manual announcement inbox

Implemented 2026-11-03. This replaces the manual receipt/review part of an external
announcement workflow, not Slack's automatic channel monitoring. Slack is not
connected; no external subscription, account connection, message send, calendar
write, model call or background intake was added.

## One usable flow

Learning (native and classic layouts) -> Announcement inbox -> enter source label,
stable announcement ID, title, body, optional source link and explicit date ->
acknowledge host storage boundary -> save -> review -> explicitly create a task.
The existing Kanban/task board receives the same task ID; its status is shown on
inbox refresh. Reviewed does not mean done, assessed or mastered.

The synthetic example fills the form only; it never saves automatically. Example
rows are visibly marked and converted task titles carry `[Synthetic]`. Manual
entries, including text the user chooses to copy from Slack, are always marked
manual, never auto-received. No real Slack content was used in validation.

## Reuse and boundaries

- Reuses authenticated account TaskBoardStore, existing account SQLite file,
  workspace resolution, cards, board revision/event stream and Kanban UI.
- Adds only `announcement_inbox` source rows in that database. Does not build a
  parallel task lifecycle or duplicate task store. Existing board schema unchanged.
- Only explicit conversion inserts a normal `todo` card. Card title and supplied
  date are copied; note contains the inbox ID, not the body or source URL. Existing
  assistant task context can include card titles/notes, disclosed in the UI.
  The receipt/conversion itself never runs a model.
- Source body stays on the application host. Host-storage consent is required;
  a cloud backend is not a local-only privacy boundary. Do not use local-only
  private material on cloud hosts. No indexing/embedding/model pipeline added.
- Source URLs must be HTTP(S), have a host and no URL credentials/whitespace;
  stored links are not fetched. React renders text as text, not raw HTML.
- No inferred deadline: only an explicitly supplied valid calendar day is copied;
  no UTC conversion or Calendar event. Dates remain their source calendar date.

## Identity, retries and conflict behavior

Unique key: `(workspace, simulated, source_label, source_key)` inside the current
account's database. Source label/ID comparison is case-sensitive and whitespace
trimmed. Different IDs/sources retain separate announcements even with identical
text. Renaming a source label changes its key; keep it stable for retries.

The content fingerprint includes all accepted fields except consent. Same key and
same content returns the original row with `duplicate=true`. Same key and changed
content returns HTTP 409 `source_conflict`; nothing is overwritten. For a correction,
the user can create a new revision ID and preserve the original. This first slice
does not automatically reconcile corrected deadlines or link revision histories.

Review writes require the current revision. A stale tab gets 409 and must refresh.
Conversion uses one SQLite `BEGIN IMMEDIATE` transaction for card insertion,
source/task link and board revision. Concurrent/retried conversion returns the
original task ID. If a task is moved to another workspace, only its existing ID
remains; foreign task data is hidden and no replacement task is created. Archived
tasks stay linked. Receipt alone does not mark a source reviewed or create a task.

Lists use 50-row keyset pages with explicit older-page loading. No polling was
added to this page. Existing task-board event streaming remains unchanged.

## Validation and trial

Synthetic tests cover real authenticated local HTTP, account/workspace isolation,
invalid URL/date/consent, dedup/conflicts, stale revisions, concurrent conversion,
transaction rollback, moved-task visibility, bounded pagination, raw text and date
preservation, native board display, and restart persistence.

Commands:
```
python -m pytest tests/multi_user/test_announcement_inbox.py tests/multi_user/test_task_board.py -q
npm --prefix web run test:unit -- tests/announcement-inbox.spec.tsx tests/task-board.spec.tsx tests/task-board-scope.spec.tsx
npm --prefix web run typecheck
npm --prefix web run build
```

Three-step acceptance:
1. Start the current local checkout, open Learning -> Announcement inbox, fill the
   synthetic example. Saving remains disabled until host-storage consent is checked.
2. Save twice: one item remains and duplicate notice appears. Mark reviewed, then
   explicitly create a task: one linked ID appears; Open task board shows the card.
3. Reload or restart the same runtime: the source, review state and linked task
   persist. Change the body while keeping the same source key and retry: conflict
   is shown and original content remains.

Cloud localhost is not a user-accessible preview. Windows actual device acceptance
and real Slack automatic intake remain unverified/unimplemented. This milestone
requires no external credentials. Its code is local until a separately approved push.

Rollback: stop the app and use the previous checkout. The additive inbox table is
ignored by old code; converted cards are ordinary existing-board tasks and remain.
Do not reset/clean or delete runtime. Removing real saved items requires a separate
explicit data action; there is no destructive delete endpoint in this slice.

Next useful step: user device acceptance and review of whether manual receipt is
sufficient. If automatic Slack announcement intake is desired, separately confirm
exact channels, authorization and data boundary. No connector permissions have
been inherited from ChatGPT and no automation has been switched.

Recorded checks for this milestone: 41 Python tests passed; 10 rendered UI tests
passed; TypeScript, targeted ESLint, Ruff, contracts, architecture and locale
checks passed (existing non-blocking i18n audit findings remain). Chromium ran the
actual local API: receipt/retry/review/conversion/reload and existing Kanban display
passed with synthetic data, including fresh mobile viewport. Backend PID
17084 -> 17663 restart retained identical full inbox and board JSON. Full Node
suite: 1332 passed / 2 existing German/Turkish punctuation failures. No full Python
suite or Windows hardware pass is claimed. Detailed logs and screenshots are in
the private review bundle.

Production build also passed, including `/learning/inbox`.

# Read-only calendar availability

Baseline: `2c270aa9b0fa68c47ece2e01f7fe40d14f55f0fb`, clean `work` checkout.
Validation date: 2026-11-05. Task detail remains at its separately committed
milestone; its tests are included in this round's regression. Its actual restart
and failure-recovery evidence remains in the 2026-11-04 private review package.

## User behavior

Expand **Available time and conflicts** on the existing Calendar page. Pick a
date and minimum duration. The first UI slice uses 09:00–18:00 Asia/Taipei.
An explicit read calculates candidate free intervals and overlapping event names.
Occurrence IDs remain available in expandable details. Editing inputs invalidates
the previous result; errors clear it rather than leaving a stale availability claim.

The API is authenticated by the existing Calendar surface and scoped to the current
account. It reuses `CalendarStore.occurrences`, including hidden calendars,
recurrence exceptions and overrides. Workspace learning overlays are not busy
calendar events. No events, reminders, tasks or external calendars are written.
All stored events are protected, regardless of their origin label. Snapshot
revision is displayed; results are not a reservation and require recalculation
after changes. There is no claim of Google Calendar connectivity or complete
real-world busy coverage. An empty local calendar can return a whole-day candidate,
but the UI explicitly warns that this does not establish actual availability.

## Calculation

`GET /api/calendar/availability?day=2026-11-05&duration=30` defaults to Taipei.
The API also accepts `tz`, `start_minute`, `end_minute`; windows stay within one
day. Ambiguous or nonexistent local clock boundaries are rejected. All-day dates
follow the existing calendar's viewed-date convention with an exclusive end.
Time intervals are clipped to the requested window and sorted. A cursor advances
to the maximum occupied end; gaps large enough for the duration are returned.
Touching events are not conflicts. Pairwise intersections retain occurrence IDs
and event names. More than 1,000 occurrences or conflicts fails closed.

No new persistence/schema, dependency, credential or service is introduced.
The frontend defaults are intentionally limited to one daily window; multiple
days, editable working hours, task scheduling and writes remain separate stages.

## Verification

- 95 Python tests passed: availability, calendar service/API/account isolation,
  recurrence editing, task detail, announcement inbox and task board.
- 12 rendered UI tests passed: Calendar, availability, task detail.
- Production build passed. The Node locale regression caught a prohibited dash
  in the new Turkish fallback text; it was replaced with an ASCII hyphen.
- Typecheck, generated contract check, architecture check and new-file lint passed.
- Existing CalendarPage has three `react-hooks/set-state-in-effect` lint errors;
  running ESLint on the baseline via stdin reproduces the same three. They are
  not hidden or described as passing. No unrelated refactor was included.
- Actual local API + Chromium at 390px: two synthetic events remain unchanged;
  overlap 09:30–10:00, candidate free time 11:00–18:00. Zero Calendar mutation
  requests occur during the UI calculation. Fixture creation is isolated test setup.
- Stop backend PID 38916, restart PID 39515 with the same test runtime: event
  snapshots, revision and free intervals remain identical. Test services stopped.

Actual cloud tests do not establish Windows or physical phone acceptance. No
authenticated external preview facility is configured in this environment.
Screenshots and readback evidence can be reviewed remotely, but are not an
interactive app link. A future phone trial requires an authorized authenticated
preview or a separately approved private hosting target. No anonymous tunnel,
push, deployment or real-account access is performed.

## Three-step acceptance and recovery

1. In an isolated synthetic runtime, create fixed sample events 09:00–10:00 and
   09:30–11:00 Taipei on the same day. Existing real data must not be used as fixtures.
2. Calendar → Available time and conflicts → that date → 30 minutes → Calculate.
   Expect one overlap and 11:00–18:00 free. Inspect names and occurrence references.
3. Refresh/restart, calculate again, and compare event counts/revision and times.
   Events are unchanged. A longer duration may yield no fitting interval, not an error.

Rollback: use the baseline checkout with the same preserved runtime or a backup
copy. This change has no migration or event writes to undo. Keep existing local
modifications; do not reset or clean the user's checkout.

Next authorized order remains evidence-based weakness/retest, Unsorted and
cross-device continuation. None is represented as completed by this calendar slice.

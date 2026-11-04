# Task evidence detail

Validated 2026-11-03 against baseline `07442972c99744bb1453d36a86d925bab509e32c`.

The existing Kanban card now links to `/kanban/{taskId}`. The detail screen
shows the task identity, original announcement receipts, deadline provenance,
explicitly selected saved Drive references and Notion snapshots, and deterministic
next steps citing evidence IDs. It does not infer a course, deadline, weakness,
completion or mastery from a title, calendar event or isolated score.

## Storage and boundaries

Reuse the account's existing task-board SQLite database and workspace scoping.
The additive `task_source_links` table pins immutable source snapshots by
task/workspace/provider/mode/source ID/fingerprint. Re-selecting an identical
version is idempotent; selecting a changed saved version requires a fresh digest.
Older versions remain stored. Moving a task does not expose its former workspace's
links, announcements or deadline history in its new workspace.

`task_deadline_history` records old/new dates and the announcement receipt that
justified a change. Adoption requires explicit confirmation and current task and
receipt revisions. The transaction links the correction to the same task, records
history and updates the board revision atomically. Repeated adoption or conversion
does not create another task. Explicitly accepting a receipt with no date clears
the date; the UI warns first. Ordinary task date edits record that no source was
supplied. Existing dates without history remain visibly unverified.

Source choices read only existing local saved references; this page makes no
Google, Notion or Slack API requests. Live links point to canonical provider URLs,
but access and current contents are not revalidated. A saved reference is not
readable source evidence for teaching. Notion properties retain their original values
and timestamps; mastery is not reinterpreted as a test score. Synthetic sources
are labeled separately; their material preview is local example text, not a
downloaded Drive document. Snapshot data is not inserted into model task context.

Slack automatic intake is unverified here. Missing matched announcements do not
mean that the user's Slack account is disconnected. Use manual receipt selection
until a genuine match is established. Choices are bounded to 100 per source mode
and 100 announcements, with visible limit notices; a task allows 20 logical links.

## Validation

- Python regression: 877 passed, 1 skipped (Windows-only credential protection).
- Node regression: 1335 passed. Targeted rendered UI: 12 passed.
- New backend cases cover account/workspace isolation, stale snapshots,
  explicit deadline clearing, concurrent retries, transaction rollback,
  retained snapshot versions and task relocation.
- Real local HTTP + Chromium: create synthetic receipts, convert once, select
  saved sources, confirm a correction, reload, retry duplicate intake and inspect
  desktop/mobile screens. One task and both deadline records remain.
- Stop/restart the isolated backend: full detail and board JSON compare equal.
- Typecheck, targeted ESLint, Ruff, contract generation/check and architecture
  checks pass. Production build result is recorded in the private review evidence.

No real provider authorization, external write, model inference, Windows device
acceptance or production deployment is claimed. The environment's existing
dependency audit findings are not remediated by this feature.

## Three-step trial

1. In Drive sources and Notion sources, save clearly labeled synthetic examples.
   In the announcement inbox, create a synthetic receipt with an explicit date
   and convert it to a task. Save a second receipt with a distinct correction key.
2. Open the task's **Task details** link on Kanban. Explicitly link each saved
   source. Select the correction, inspect old/new dates, check confirmation and
   adopt it. Expect original receipts, raw Notion fields and labeled material link.
3. Refresh and restart the same runtime, then open the task again. Expect preserved
   links and date history. Re-converting either linked receipt returns that task.

Use the existing launcher and preserve the same `DEEPTUTOR_HOME`. Git updates
alone do not install dependencies or restart services. This round is local-only
until separately approved for publishing; a remote clone cannot yet obtain it.

## Recovery and next step

Stop the runtime and back up its complete data directory before changing versions.
Use an independent checkout of the baseline with a copy of the runtime for rollback
testing; do not delete the new additive tables or overwrite current data. Older code
does not display new evidence/history, while current task dates remain changed.
Reverting code does not reverse confirmed date edits; preserve their audit history.

Next: user acceptance on the intended running instance, including manually verified
real source links. Calendar scheduling and automation migration remain separate work.

## Revalidation, 2026-11-04

Baseline `5f8c3eeed9c7dd3145a298e4d1d0411ab2835a96`, clean `work` checkout.
Reproduced an initial-load failure: a failed evidence-choice request hid a
successfully loaded task because the two requests used `Promise.all`. They now
settle independently. The task remains readable, the failure is visible, and
refresh clears stale choices and confirmations before retrying.

Targeted backend regression: 51 passed. Related rendered UI: 13 passed. New
coverage includes 16 concurrent receipts/conversions/source links, partial
provider-store failure without leaking error details, archived-task write
rejection, and choice failure/recovery without implicit writes. Existing cases
still cover deadline nulls/corrections, rollback, stale versions and isolation.

Real local API + Chromium desktop/mobile replay passed in a fresh synthetic
runtime. An injected HTTP 503 verified the UI failure path. Full task detail and
board JSON remained identical after stopping PID 34160 and starting PID 34476
against the same runtime. Both test services were stopped afterward; the earlier
runtime was preserved. The first browser script used an incorrect refresh-button
label; correcting that test locator and replaying in a fresh runtime passed.

The cloud environment reports no remote-preview capability, configured secrets,
outbound identities or VPN. No externally accessible preview URL is established.
Screenshots document the tested UI but are not a live trial. A future phone trial
requires an authenticated preview facility or an explicitly approved private
hosting target; never expose this local-mode runtime through an anonymous tunnel.
No real account connection, deployment, push or expanded permission occurred.

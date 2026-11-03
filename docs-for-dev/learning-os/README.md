> Drive authorization milestone (2026-11-03): [implementation, setup gates and acceptance](drive-oauth.md). Real Google/Windows acceptance is pending.

> Latest security milestone (2026-11-03): [provider storage and integration prerequisites](security-prerequisites.md). Earlier acceptance and patch instructions below are historical.

# Question source handoff — 2026-11-02

Original first-round acceptance snapshot: implemented and locally verified; awaiting user acceptance.
At that snapshot no commit, push, deployment, external account connection, or automation cutover had occurred.
Subsequently committed locally as `a8fb61400`; Drive references followed in `93f952439`.
See [Drive references](drive-sources.md) and [Windows trial/update workflow](windows-trial.md)
for later increments and their separate verification limits. Remote publication remains pending.
Fourth increment: [trial reliability](trial-reliability.md) and [brain/Notion design only](brain-notion-design.md).
This is a public-safe engineering record, not the private product work package.
`/docs/` is ignored by this repository, so this record uses the existing developer handbook.

## Baseline and scope

Baseline: branch `work`, HEAD `f7aed0744c36c5afef16a4261c31ebee1208cac2`, clean
tracked/untracked status. Only root `AGENTS.md` applies; no repository or workspace
`.agents/skills` content was available. Read README, AGENT_SETUP, DEVELOPMENT,
DATA_STORAGE, TESTING and frontend contract instructions. Reused the task checkout.

The one deliverable is explicit original-question source labels across import,
SQLite storage, API, question cards and reload. No inference, model call, file
opening, source verification or private-document ingestion is added.

Pre-change checks: question-bank API 23 passed; existing tooltip UI test 1 passed;
`/` redirected to `/chat`, which returned HTTP 200. An initial production build
succeeded but overlapped editing, so it is not a pristine-build baseline. A separate
final build was run after all frontend changes. No startup repair was needed.

## Feasibility and functionality inventory

Evidence below distinguishes code presence from actual end-to-end verification.

| Area / existing surface | Evidence | Gap / smallest action | Current verification |
| --- | --- | --- | --- |
| Question Bank `/space/questions` | `web/components/space/question-bank`, `api/routers/question_notebook.py`, SQLite `notebook_entries` | Add four explicit labels to existing persistence and card | This round: real import/API/store/browser verified |
| File import preview/commit | `services/practice/importing.py`, `storage.py`, `PracticeImport.tsx` | Carry optional source fields; retain same question from distinct explicit sources | JSON UI flow, CSV parser, retry and legacy tests passed |
| Source materials / Reading / knowledge | `services/workspace`, `api/routers/knowledge*`, `book` | Source version/hash, PDF/image opening, uncertain parsing and local-only routing remain separate work | Code present; real parsing/RAG not tested |
| Tutoring / mastery / journal | `learning`, `api/routers/learning_journal.py`, `services/session` | Separate provenance, original answer and disputed answer; evidence-based mastery acceptance | Code present; no configured model in isolated runtime |
| Task / durable turns | `app`, `services/session/turns`, `services/task_board.py` | Product task acceptance, approval and restart scenarios still needed | Code present; not certified by source tests |
| Memory / rules | `services/memory`, memory tools | Rule correction/deletion and privacy lifecycle acceptance | Not tested |
| Calendar / scheduling | `api/routers/calendar.py`, `services/calendar`, `services/cron` | Google account adapter, fixed-event protection and write reconciliation acceptance | Local code present; no Google Calendar connection tested |
| Slack | `partners/channels/slack.py` | Scoped real account and announcement deduplication acceptance | Adapter present; not connected/tested |
| Drive / Notion / dot | No verified account binding or shared task protocol in this round | Read-only integration plus explicit authority/sync rules | Not connected; existing external-system ability is not v3 evidence |
| Cross-device / shutdown continuity | Web/API/SQLite architecture | Same-account physical device tests and persistent service operation | Desktop/mobile viewport simulation only; no phone/Mac/Windows continuity claim |
| Research / experiment / slides | Existing capability/plugin architecture | Separate output-specific acceptance | Deferred |

Old-system automations and connector state were not inspected or changed. Their
reported historical capabilities are external to this checkout. No external
capability is marked “v3 real-connected”; only the local source workflow is real.

## Behavior and design decisions

- `source_metadata` contains `filename` (display label, max 255 chars), `year`
  (integer 1–9999 or unknown), `pdf_page` (positive 1-based integer or unknown),
  `question_number` (string, max 100 chars; supports `12(b)`). It is user-supplied
  metadata, not proof of an original exam. Do not submit sensitive paths/labels.
- JSON imports use `source_metadata`; CSV/TSV/XLSX use `source_filename`,
  `source_year`, `source_pdf_page`, `source_question_number`. A nested object takes
  precedence. Invalid values block preview commit with a row error.
- No source is inferred from the upload filename. Missing fields render Unknown.
  Existing download templates are unchanged; add the optional columns as needed.
- An additive JSON column reuses `notebook_entries`; no parallel database. The
  migration follows the older origin-table migration and preserves old entries.
- Upsert omission/null preserves source metadata; an explicit object replaces
  it (empty object clears labels). Old clients can resubmit answers safely.
- Import deduplication includes explicitly supplied source labels. Reimporting
  identical source-bearing content is idempotent; different explicit sources are
  retained. Source-less legacy hashes remain unchanged. Adding/changing source
  labels to a previous import creates another record; no fuzzy merging occurs.
- Original question text/options are not translated or reduced by this change.
  The pre-existing importer still performs its existing type/answer normalization;
  this round does not certify every historical question format.
- Chinese source labels are provided in `zh`; other non-English catalogs use
  English fallback strings for these four new labels, preserving locale parity.

## Three-step acceptance

Prerequisites: apply this round's complete patch to the baseline, install the
repository's documented Python and Node dependencies. In two terminals, from the
repository root, use a **new isolated runtime home** (absolute path):

```bash
DEEPTUTOR_HOME=/tmp/deeptutor-source-demo deeptutor serve --host 127.0.0.1 --port 8001
```

```bash
cd web
DEEPTUTOR_API_BASE_URL=http://127.0.0.1:8001 npm run dev -- --hostname 127.0.0.1 --port 3782
```

1. On that same computer, open `http://127.0.0.1:3782/space/questions`, choose
   **Import questions**, select `synthetic-import.json` next to this document,
   review the synthetic question and confirm. Expect `synthetic-upload.pdf`,
   2024, PDF page 3, original number `12(b)`, and all five Chinese options.
2. Refresh, then import the same file again. Expect one copy of that import;
   the source remains visible. Omit `year` in a copy of the fixture: preview and
   import it, then expect Unknown for that separate source's year.
3. Stop only the test backend with Ctrl+C and rerun its exact command with the
   same runtime home. Refresh: source labels and question remain. Narrow the
   browser to phone width and confirm all four labels remain readable.

The running managed instance has loopback frontend 3782/backend 8001 and a separate
synthetic runtime. These are **not user-accessible cloud URLs**. No supported
port-forward/share-preview tool was exposed, so local reproduction is the verified
alternative; no public deployment was attempted. Browser screenshots supplement,
but do not replace, actual SQLite/API persistence checks.

## Verification

Full logs, response JSON, screenshots, browser scripts and complete patch are in
`/workspace/scratch/learning-os-round1/` in the development task; they are not
committed. See `evidence.md` for exact commands/results and remaining limitations.

## Core function lesson: normalize_source

`deeptutor/services/practice/importing.py` adds this small function (about 18 lines).
Its input is an imported row. It chooses the nested source object or four optional
spreadsheet columns, removes empty values, converts numeric spreadsheet strings,
then validates against `QuestionSourceMetadata`. Its output is a plain dictionary
of known labels only. Invalid page/year values raise a validation error that the
existing preview catches and reports against the row; nothing is committed.

The useful concept is **validation at the data boundary**: CSV gives strings, JSON
can give numbers, and the database should see one consistent shape. An absent year
stays absent rather than being guessed from the filename or current date. The API
uses the same model, so import and direct saves agree on valid data.

## Rollback and next work

Save the complete patch and preserve the synthetic runtime first. Stop the test
processes, reverse only this round's patch (review `git apply --reverse --check`
first). Do not reset the checkout or erase runtime directories. The additive source
column can remain; the immediately preceding code ignores it. Returning to the
baseline hides source labels but retains them in SQLite. Downgrades across older
schema-rebuilding migrations are outside this guarantee and need a full backup.
No existing runtime database was migrated for this demo.

Recommended next task: source version/hash and safe original PDF/image navigation,
with missing-file behavior. Then original/AI/recalled/adapted provenance and answer
conflict handling. External integrations remain a later independently authorized
read-only stage; never use this demo to trigger an automation cutover.

## Prepared commit / PR (not submitted)

Commit: `feat(question-bank): persist and display explicit question source labels`

PR: Question imports and notebook saves previously lost original filename, year,
PDF page and question number. Add optional shared validation, additive SQLite
storage, source-aware import deduplication, API contracts and question-card labels.
Old source-less imports retain their IDs, omitted metadata preserves existing
labels, and missing fields display Unknown. Verified synthetic import, reload,
backend restart, legacy migration, invalid values and desktop/mobile rendering.
No real document, provider account, external write or deployment is included.

## Obtain this unpushed change without disturbing local edits

A normal clone does **not** contain this round. Download `complete.patch` from the
handoff attachments. Keep any current working directory and its uncommitted files
intact. From an existing clone that already contains the baseline commit:

```bash
git status --short
git cat-file -e f7aed0744c36c5afef16a4261c31ebee1208cac2^{commit}
git worktree add --detach ../DeepTutor-source-trial f7aed0744c36c5afef16a4261c31ebee1208cac2
```

Choose a new, unused destination; do not reuse an existing directory. If the
baseline object is missing, stop and obtain that exact revision before proceeding.
In the new worktree, use the absolute path to the downloaded patch:

```bash
cd ../DeepTutor-source-trial
patch_file=/absolute/path/to/complete.patch
git rev-parse HEAD
git status --short
git apply --check "$patch_file"
git apply "$patch_file"
git diff --check
git status --short
```

HEAD must match the baseline above and status must be clean **before** applying.
If either check fails, stop; do not use reset, clean, forced checkout or `--reject`.
The original checkout's tracked and untracked changes remain untouched. Install
source dependencies in a dedicated virtual environment for this new worktree,
then follow the three-step acceptance above. Do not commit, push or deploy as part
of this trial. The attachment also includes a SHA-256 manifest for byte integrity.

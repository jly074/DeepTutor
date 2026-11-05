# Unsorted batch original-file intake

Baseline `2bc75bdcabd4afd9f66e69ed04d69c1cb804b029`, clean `work` checkout.
Validated 2026-11-05. This is a file-registration and manual-classification slice,
not Notion batch synchronization or automated lesson completion.

## Reused architecture and user flow

The learning dashboard links to `/learning/unsorted`. Existing account File Library
stores original bytes and deduplicates content by SHA-256. Three additive tables
in the existing account TaskBoard database hold workspace-scoped source identities,
immutable content versions and manual classification history. No parallel database,
parser, model, external integration or new dependency is introduced.

Batch registration requires an explicit server-storage consent and data boundary
(`synthetic` or `approved_non_sensitive`). The UI offers two synthetic text files.
The user's local original is never moved or deleted. The server receives a copy;
this is unsuitable for local-only sensitive documents. Limits: 10 files, nonempty
files up to 5 MiB each, 20 MiB aggregate. Raw bytes are accepted without extraction,
so registration does not prove that a format can be parsed or used for teaching.

Rows start **pending** with unknown classification. Users select rows and enter a
category before batch collection. **Collected** means original registration plus
manual classification, not parsed, indexed, learned or synchronized. Classification
correction preserves an audit record. All requested classifications validate before
the transaction changes any row; stale versions fail rather than partially applying.

## Source identity, retries and versions

Default duplicate identity is workspace + original filename + content hash + data
boundary. Re-uploading it returns the same registration. Different filenames retain
separate references while identical bytes share the existing account library blob.
This is file deduplication, not question/content-semantic deduplication.

Same-name changed bytes create a separate source unless the user explicitly chooses
**Add explicit new version** on an existing source. Explicit versions retain source
ID, receive a new content digest/version row, preserve old originals and begin pending.
No version lineage is guessed from filenames. Concurrent duplicate registrations and
confirmation retries are idempotent under database transactions/unique constraints.

Byte storage and registry writes span existing stores, so a failed registry write
can leave an account-library original without an intake row. This is preserved, not
deleted; retry reuses that blob and creates one row. Individual batch results report
success/duplicate/failure. A batch is not falsely described as all-or-nothing.
An unavailable/corrupt original fails verification and collection/download fails
closed. Re-upload alone does not necessarily repair missing bytes; use the existing
library recovery path. This slice never silently overwrites a corrupt original.

## Security and isolation

Account identity comes from existing authentication. Workspace is validated by the
existing task-board scope resolver. Intake rows, version targets and download routes
require that workspace; cross-account/foreign-workspace IDs do not resolve. The
underlying preexisting File Library is account-owned, not a new per-workspace blob
security boundary. The UI states this distinction rather than promising stricter
isolation than the existing library supports.

Filenames containing path components/control characters are rejected; stored paths
are library-generated. Downloads recheck SHA-256 and use attachment/octet-stream,
no-store and nosniff headers. The frontend downloads through authenticated apiFetch.
No inline HTML execution, archive extraction, OCR, embeddings, model processing,
Notion writes, file moves or deletion are part of this feature.

## Verification and trial

- 122 Python tests: new intake + existing task/inbox/detail and File Library tests.
- New cases cover original hashes, aliases/explicit versions, size/name/consent
  failures, partial batch recovery, atomic stale classification, correction history,
  registration failure after byte storage, unavailable originals, eight parallel
  retries, reopened stores and authenticated account/workspace isolation.
- Four rendered UI tests (intake and existing announcement inbox) cover consent,
  explicit collection and missing-original errors without hiding the registry.
- Real local API + Chromium at 390px: two synthetic files, duplicate replay, manual
  batch collection, explicit new version, refresh and verified original downloads.
- Actual backend stop PID 48834 / restart PID 49866 with the same runtime: complete
  rows and every original download remain identical. Services stopped afterward.

Three-step trial:
1. Learning → Unsorted → choose synthetic examples, review storage consent, register.
2. Select both pending rows, enter a manual synthetic category, collect. Retry upload:
   expect duplicates, not more rows.
3. Explicitly add a changed version to one source. Expect the new version pending,
   previous version collected, both originals downloadable after refresh/restart.

This environment provides no confirmed authenticated external app preview. Screenshots
are evidence, not a live trial link. Physical phone/Windows and real-account acceptance
remain unverified. No push, deployment, credentials or real Notion operations occur.

Rollback uses a separate baseline checkout and runtime backup/copy. Preserve new
registry/history tables and account-library originals; do not reset/clean/delete.
Older code will not display intake records but the existing library retains bytes.
Next stages may add explicitly authorized parsing and batched learning evidence;
none is claimed as delivered by this original-file intake slice.

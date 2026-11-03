# Notion selected-property snapshots

Status: implemented first read-only slice, synthetic validation only (2026-11-03).
Real Notion access and Windows device acceptance remain unverified. No credentials
were created/configured, no account access enabled, and no Notion data changed.

## Reuse and scope

The native `/learning/notion` page is linked from both learning dashboards. It
uses the existing account/workspace request context, session SQLite database and
`TopicSource` model. An additive `notion_source_snapshots` table holds source
versions, not a second task/mastery database. Existing task board, learning journal,
memory/rules and mastery models are unchanged. This implements the incoming source
snapshot step of the brain design, not the full brain or two-way synchronization.

Read flow: local connection status -> explicit host/data-boundary acknowledgement
-> read schema -> select stable property IDs -> preview one page -> select a row
-> re-query the same allowed source and cursor -> compare fingerprint -> save local
snapshot -> reload. Default selection is title only; up to ten explicitly chosen
properties, 25 rows per manual request. No background sync, search, recursive reads,
page bodies, OCR, embedding, model processing or related-page fetches.

Identity is `(owner, workspace, mode, data_source_id, page_id)`. Version uniqueness
adds a SHA-256 fingerprint over selected IDs, raw values/types, source timestamp
and title. Repeated imports are idempotent. Changed sources require new preview;
new versions keep the same local source ID and original Notion page ID. Prior
versions are retained; UI currently shows the latest imported version. Missing or
unshared remote rows do not delete local snapshots. Selecting different fields
creates a new snapshot; it does not erase history. No local deletion UI this slice.

Supported: title/rich text, number, select/status/multi-select, date, checkbox,
URL, and relation IDs only. Formula/rollup/people/files are not supported here.
Potentially truncated properties block import. No unsupported value is guessed.
Actual tracker schema has not been read: Course may be a relation, Mastery may be
a formula, and those types require real schema comparison before migration claims.
Mastery remains an uninterpreted source value, never converted into a score or
LearningEvidence. Sources have `available=false`, `metadata_only=true`, and
`snapshot_only=true`; they are not presented to teaching as readable textbooks.

## Authorization design and remaining approval

This slice supports a separately provisioned internal connection with **Read
content only**, shared only with the intended source database. No insert/update,
comments or user-information capability is needed. Public OAuth page selection is
an alternative for future multi-user onboarding; no OAuth setup UI is implemented
here. Personal access tokens were not chosen because their access follows the
user's broader page permissions. Actual setup requires separate user approval.

The provider reads future-approved process environment only:

- `DEEPTUTOR_NOTION_OWNER_ID`: authenticated application user scope ID.
- `DEEPTUTOR_NOTION_WORKSPACE_ID`: exact application workspace ID (empty general).
- `DEEPTUTOR_NOTION_DATA_SOURCE_ID`: UUID of the original data source, not database
  container ID, display name, linked view or an arbitrary page URL.
- `DEEPTUTOR_NOTION_READ_TOKEN`: injected by an approved secret mechanism, never
  placed in repository files, frontend, chat, shell history or provider forms.

No setup endpoint or token persistence was added. No real values were configured.
Anonymous local-admin and partner identities cannot use a real connection. Other
accounts/workspaces do not inherit the binding. A configuration is only
`configured_not_verified`; successful manual reads establish UI readability.
Unconfigured mode performs no provider request. The application allowlist limits
requests but cannot narrow the token's upstream capability; sharing is therefore
part of future setup verification. Sensitive content must be processed on an
approved local host; a cloud-hosted backend is not a local privacy boundary.

Only `GET https://api.notion.com/v1/data_sources/{bound_id}` and read-only
`POST .../{bound_id}/query` are allowed, pinned to Notion-Version `2026-03-11`.
Selected IDs use `filter_properties`; redirects are disabled, request duration and
response size bounded, cursor length bounded, no automatic retries. 401,403,404,
429,timeout and invalid/incomplete responses become safe error codes, never raw
provider text. Saving re-queries the allowed source instead of fetching an arbitrary
client-supplied page ID. Application request context owns identity; a client
`account_id` cannot select another owner's store.

Official references consulted:
- https://developers.notion.com/guides/get-started/authorization
- https://developers.notion.com/guides/get-started/internal-connections
- https://developers.notion.com/reference/capabilities
- https://developers.notion.com/reference/query-a-data-source
- https://developers.notion.com/reference/retrieve-a-data-source

## Trial and verification

1. Run the existing local application at this checkout. In Learning, open Notion
   and choose the synthetic demonstration. The default real mode reports setup or
   authentication requirements; it does not pretend to be connected.
2. Acknowledge the data boundary, read schema, select Mastery/Status if desired,
   then preview and import Synthetic concept A. Original page UUID and raw values
   appear with a simulation label. Unsupported formula selection is disabled.
3. Refresh, choose the demonstration again, and confirm the same saved ID/values.
   Real and simulated snapshots are separated. Repeated import creates no duplicate.

Python tests use synthetic accounts/SQLite and httpx.MockTransport for the real
adapter; no provider network access. Browser verification uses the actual local
HTTP application with built-in synthetic mode, not a real Notion connection.
Commands/results are recorded in the private review evidence bundle.

Relevant commands:
```
python -m pytest tests/services/notion_source tests/services/drive_source tests/services/workspace -q
npm --prefix web run test:unit -- tests/notion-sources.spec.tsx
npm --prefix web run typecheck
npm --prefix web run build
```

Rollback: stop the application; use the previous checkout with the same runtime.
The new table is additive and previous code ignores it. Do not delete runtime or
reset existing work. Reverting the source commit after review is another option;
keep the source-version ledger unless its deletion is separately requested.

Next: obtain approval for the exact source, hosting/privacy boundary and Read
content connection provisioning; then verify the actual schema and selected reads.
Notion writes, full task/rule/evidence projection, dot synchronization and Slack
remain separate work. No existing Topic or task migration has been claimed.

## Recorded validation at this milestone

- Python Notion + Drive + workspace regression: 222 passed (Notion: 25).
- Rendered Notion + Drive component/callback tests: 10 passed.
- TypeScript, targeted ESLint, Ruff, contracts, architecture, locale parity/audit:
  passed; locale audit still reports existing non-blocking findings.
- Production build: passed, including `/learning/notion`.
- Full Node suite: 1332 passed, 2 failed. Both are existing German/Turkish
  punctuation quality failures already reproduced on the prior baseline; this
  milestone does not claim a green full suite.
- Chromium actual local API, built-in synthetic provider: explicit field reads,
  import, reload, source ID/raw values retained; desktop and fresh 390px mobile
  viewport checked. This is browser emulation, not Windows/mobile hardware testing.
- Backend PID 13190 stopped with SIGTERM, restarted as PID 13499 with the same
  isolated runtime: paired JSON readbacks identical. No provider credentials used.
- Real Notion, actual tracker schema, Windows and device acceptance: not run,
  pending separate authorization/environment. No full Python suite claim.

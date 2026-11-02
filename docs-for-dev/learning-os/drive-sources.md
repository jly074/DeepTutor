# Workspace Drive references — second increment

Verified 2026-11-02. First increment: `a8fb61400f0d5383f19406fcb5eca4e3fa339abc`.
This increment provides a workspace-scoped metadata reference flow. It is not a
production Drive connection, textbook ingestion, or a completed deployment.

## Behavior and boundaries

`/learning/drive?dt_workspace=<workspace-id>` is linked from both learning dashboards.
The default mode is disconnected. The explicit synthetic demonstration uses a local
provider with two pages and a repeated file ID. Refresh is manual. Selecting a file
rechecks its folder membership, then saves a TopicSource in the existing session
SQLite database. Reload preserves references; demo and live connections are distinct.
References have `available=false`, empty excerpts, and `metadata_only=true`.
The material builder rejects Drive references as unreadable even if a caller sets
`available=true`. References are not automatically attached to a particular topic.

The service captures and rechecks account and workspace identity. The persistence
key is `(owner, workspace, connection_id, file_id)`; changes to version/name update
that reference. Folder IDs must match a bounded identifier pattern and a server-side
allowlist. The provider requests direct children only, excludes folders, shortcuts
and trashed files, validates parents, deduplicates IDs, and processes at most five
100-item pages. Incomplete searches, repeated page tokens and pagination limits fail
without presenting partial results. Saving never trusts browser-provided metadata.

The injected Google client only implements GET `/drive/v3/files`, metadata fields,
a ten-second timeout, no redirects and no retries. 401/403/404/429, malformed output,
provider failures and timeout have safe static errors without exposing provider bodies.
No token is read from environment, ChatGPT connectors or stored credentials. The live
factory remains unconfigured. Trusted application code can inject an authorized
connection and token callback in a later increment; no configuration or login UI is
implemented here. States include disconnected, needs authorization, simulated,
queryable and blocked; only disconnected and simulated are presently reachable
through default configuration. Other states are verified with injected test providers.

## Files

- `deeptutor/services/drive_source/`: bounded provider adapters, isolation, persistence.
- `deeptutor/api/routers/drive_sources.py`, server manifest and auth surface map: scoped API.
- `deeptutor/learning/topic_materials.py`: metadata cannot become readable教材.
- `web/lib/drive-sources-api.ts`, panel and learning route: manual reference workflow.
- Both learning dashboards: entry link; ten locale catalogs: matching keys (English fallback except Chinese).
- OpenAPI schema/generated TypeScript: current API contracts.
- Python service tests and `web/tests/drive-sources.spec.tsx`: boundary and UI verification.

## Verification

Commands run from repository root unless noted:

```sh
/workspace/.venvs/deeptutor/bin/python -m pytest tests/services/drive_source tests/multi_user/test_learning_surface_map.py deeptutor/learning/tests/test_topic_materials.py tests/services/workspace/test_account_and_scope_boundaries.py tests/services/workspace/test_http_scope.py -q
# 149 passed
cd web
npx vitest run tests/drive-sources.spec.tsx
# 3 passed
npm run typecheck
npm run lint
npm run architecture:check
npm run i18n:check
npm run contracts:check
DEEPTUTOR_NEXT_DIST_DIR=.next-drive-build npm run build
```

Type checking, contract generation/check, architecture, localization parity and
production build passed. Full lint: zero errors, 58 existing warnings. Targeted
lint and Ruff passed. Browser automation used real frontend/API/SQLite with only
synthetic provider data: explicit demo, manual list, repeated selection, reload,
second-workspace isolation, desktop and fresh 390px mobile viewport. No browser
page errors or browser Google Drive requests occurred. Whole-backend stop/start
and identical persisted response are recorded in the private restart evidence.

Not run: real Google API/OAuth, real accounts/materials, physical device trial,
external preview/deployment, downloads and model processing. These are not claimed.
MockTransport tests validate HTTP request structure and error behavior, not Google
account authorization or Google accepting the request. Browser tests validate the
synthetic path, not an independent live integration.

## Trial (three steps)

1. Start backend and frontend, open Learning → Google Drive sources in a selected
   workspace. Expect Not connected and disabled refresh in real mode.
2. Choose Try synthetic demonstration, then Refresh direct file list. Select Save
   reference on Synthetic lesson.pdf twice. Expect one saved reference, marked
   simulation and metadata-only/unreadable.
3. Reload, select the synthetic demonstration again: the same reference remains.
   Change workspace: it must not appear there. Return to recover the original reference.

Reproducible local startup (use an empty temporary runtime, not personal data):

```sh
DEEPTUTOR_HOME=/tmp/deeptutor-drive-trial deeptutor serve --host 127.0.0.1 --port 8002
# separate terminal, web directory
DEEPTUTOR_API_BASE_URL=http://127.0.0.1:8002 npm run dev -- --hostname 127.0.0.1 --port 3783
```

These are local machine addresses, not publicly accessible cloud preview links.
The cloud verification runtime uses a separate scratch directory. To apply patches
elsewhere, inspect existing work, use an isolated clean worktree at the stated base,
and run `git apply --check` before applying. Do not reset or overwrite local changes.
Rollback should revert this increment after preserving later work; the additive
reference table can remain unused. Do not delete user databases.

## Core function: select

`DriveSources.select(folder, file_id)` first obtains a validated complete direct
listing. It rejects unknown IDs, derives stable identity from account/workspace/
connection/file, constructs an unavailable TopicSource, then parameterizes an SQL
upsert. Inputs never include trusted filenames or content. The output is the saved
reference. This separates *knowing where material exists* from *having read it*.

## Follow-up gate

Before real connection, explicitly approve account, exact folder allowlist, metadata
storage location and read-only permission scope; choose OAuth/client and callback
configuration or approved service-account design. Provision secrets through a secure
runtime mechanism, never chat or repository. Authorization, consent, scope and token
refresh handling require a separate approved implementation and real connection test.
No persistent credentials, external writes, push, merge or deployment occurred.

# Reviewed task handoff summaries

Implemented on the existing task-board/detail path; no new task database or external channel.
Baseline: `535ef97e76709d65807a8bfc731426eb44be61e5`. Validated 2026-11-05 in Linux cloud with synthetic data.

## Behavior and boundary

Open a task detail, prepare a reviewed JSON summary, download it, then select it from another browser session connected to the **same backend, account and workspace**. Verify first; explicitly record second. The canonical task is never created, replaced or marked complete by import. Task ID and status remain the original ones.

Default export contains only format/version, task ID/status, random issuer and receipt IDs, issuance/expiry timestamps and an opaque task/evidence digest. Title, notes, announcement content, filenames, provider IDs, URLs, credentials and source snapshots are not automatically exported. Optional next-step text is user-authored and reviewed (500 characters); it is not model guidance or automatically classified as safe. Optional reference IDs are existing task evidence-link row IDs, not source content or arbitrary external results. IDs can still reveal relationships; review before transferring. Do not enter sensitive text. No file is sent externally by this feature.

The account's existing SQLite task database stores an issuer UUID and exact issued summaries. Import requires an exact matching receipt in the selected task/workspace/account; foreign backends and edited summaries are rejected. This is local receipt verification, **not a public-key signature or proof of a dot/human identity**. Independent installations are not supported. The issuer survives process restarts and database backups.

A transaction checks a digest of the complete current card plus its saved evidence, announcements and deadline history. Any change blocks an old summary, including changes between preview and confirmation. Summaries expire after seven days. Accepted receipts are immutable and deduplicated by receipt ID; retry does not create a task or second receipt. Recent accepted records (maximum 50) are shown; changed versions are marked historical. Core task progress is never overwritten. Import records the handoff only; it does not execute the next step. Retention/cleanup controls are not added in this slice.

## Implementation

- `services/task_handoff.py`: strict schemas, scoped receipt store, transaction-level validation and acceptance.
- `api/routers/task_board.py`: authenticated task routes, server-resolved account/workspace; safe storage error codes.
- `TaskHandoffPanel.tsx`: native task-detail UI, explicit privacy review, exact JSON preview/download, bounded file input (16 KB), server verification then explicit acceptance.
- Existing detail tests updated for the new read-only history endpoint; dedicated handoff tests exercise export/import independently.
- Additive SQLite tables only. Previous code can run with these tables left intact. Revert this commit on a clean checkout if needed; never delete the runtime database to roll back.

## Validation and limits

Python: minimal field allowlist, selected reference roundtrip, auth/account/workspace/task isolation, tampered/unissued/stale/expired rejection, preview without acceptance, concurrent idempotent retry, rollback after simulated SQLite failure and successful retry, archived task and malformed input.
UI tests use HTTP function substitutes. Separate real local API + Chromium run downloads JSON, switches browser contexts (no localStorage transfer), verifies, accepts and reloads. A real backend PID stop/start against the same isolated runtime confirms exact task/detail/history readback and idempotent retry. Synthetic references are tested in backend tests; browser flow uses no selected reference.

No actual dot channel, remote hosting, mobile/Mac/Windows devices, external account, cross-backend import, continuous execution or cross-device network sync was tested. This is a manual same-backend handoff feature. No configured user-accessible preview exists in this environment; localhost is not a public preview URL. External channel/hosting and persistent access require separate authorization.

## Three-step trial

1. In an existing isolated trial runtime, open Task board > Task details. Leave optional fields empty or enter a synthetic next step and select a saved evidence ID. Confirm review, prepare, inspect and download JSON.
2. Open another browser session to the same runtime/account/workspace and task. Select JSON, inspect the verified receipt and record. Reload: exactly one record with the same task ID/status/next step/reference IDs remains.
3. Change task status through the existing board and attempt the old file again: stale error, no overwrite. Export again to continue. A copied or modified file from another backend is rejected.

Next bounded work: user-operated hosted/shared runtime access verification before claiming actual cross-device continuation. Keep external writers and old automations unchanged.

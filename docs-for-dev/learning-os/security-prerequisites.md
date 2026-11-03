# Provider settings protection and integration prerequisites

Status: 2026-11-03, based on b6a0dd58c08a551b896e5a56f87ff0aa40d1447c.
This milestone is local development, not approval to deploy or use real credentials.

## Delivered slice

- Next.js and eslint-config-next: 16.2.3 -> 16.4.4, locked versions.
  Disable new automatic agent-rule generation so development startup does not dirty
  the trial checkout with an untracked AGENTS.md; existing root rules are preserved.
- Native Settings > Providers (`/settings/connections`) displays storage status.
  Windows administrators can explicitly opt in to Windows DPAPI user-bound
  encryption of `model_catalog.json` and `settings_draft.json`.
- Existing unprotected files remain readable. Enabling protection preflights both
  files, encrypts and checks a round trip before replacing files atomically. No
  plaintext backup is created. A partial replacement is readable and retryable;
  the completion marker is written last. Subsequent saves remain encrypted.
- Non-admin callers cannot inspect or convert the inherited administrator catalog.
  Stores must resolve to the same owner directory. API responses contain only status,
  never credentials or paths. Crypto failure does not fall back to plaintext.
- Invalid or empty catalog files now fail closed instead of being overwritten with
  defaults; protected corrupt drafts also fail closed. Keep damaged files for recovery.

Only these two stores are covered. Runtime settings, MCP/OAuth stores, logs, memory,
exports and old backups are NOT converted. Processes under the same OS account can
still decrypt. Linux/macOS report unsupported. This is for a single backend process;
stop other backend writers before conversion (the existing stores use process-local
locks, not cross-process transactions). This does not establish production readiness.

Microsoft documents user-bound DPAPI and its roaming-profile exceptions:
https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata
Next.js security guidance:
https://nextjs.org/blog/nextjs-security-update-october-14-2026

## Verification

Evidence is kept outside Git in the private review package. Commands run from the
repository root unless `web/` is specified; Python uses the dedicated project venv.

| Check | Result |
| --- | --- |
| `python -m pytest tests/services/config tests/services/test_model_catalog.py tests/api/test_credential_storage.py tests/api/test_settings_router.py -q` | 462 passed, 1 Windows-only test skipped, 2 warnings |
| `npm run test:unit -- tests/credential-storage.spec.tsx tests/drive-sources.spec.tsx` (web) | 6 passed |
| `npm run typecheck` (web) | passed |
| `DEEPTUTOR_NEXT_DIST_DIR=.next-day2-build npm run build` (web) | passed, Next.js 16.4.4 |
| targeted ESLint and Ruff | passed |
| contract export, generate and check | passed |
| `npm run i18n:check` (web) | parity and audit passed; existing literal-text suggestions remain |
| Chromium, isolated empty runtime, live local HTTP API | desktop/mobile status, reload, no horizontal overflow, no page errors |
| `npm audit --json` (web) | before: 70, critical 1/high 31; after: 43, critical 0/high 8. Next.js no longer reported. Audit still exits nonzero. |

Tests replace DPAPI with a reversible transport double on Linux; this is NOT an
actual cryptography test. Windows DPAPI remains unverified on a real Windows host.
The browser checks the actual Linux unsupported state, not simulated Windows success.
The unit UI test simulates Windows capability/response and checks explicit consent.
No full repository test suite, Windows UI test, real provider, Google OAuth, Slack,
Notion, migration of private records, or deployment test was run.
Remaining high dependency findings include DOMPurify, undici and Vite plus transitive
build tooling. Applicability and compatible fixes still need review; do not treat
zero critical findings as a complete security assessment.

## Three-step local acceptance

This commit is not yet pushed. An existing Windows checkout will not obtain it until
review and an explicitly approved push to its configured trial branch. Then use the
existing `learning_trial.py update`, `deps`, `start` workflow in windows-trial.md.
Use an isolated synthetic runtime, retain the original runtime and local changes.

1. Open Settings > Providers. Confirm the storage panel appears in the native layout.
   Windows should offer opt-in; Linux/macOS should say protection is unavailable.
2. With synthetic settings only and one backend running, read the binding warning,
   tick consent and enable. The panel should confirm protection. On unsupported
   hosts there must be no enable action. Do not enter real credentials for this test.
3. Restart and reload. Protection should persist and existing synthetic settings
   remain readable. On Windows run the Windows-only DPAPI test as well; preserve any
   failure details without copying credential values into reports.

The development preview uses a cloud-local port and is not a user-accessible URL.
Representative screenshots supplement, but do not replace, backend persistence tests.

## Rollback

Before opting in, previous code can run against unchanged settings. After opting in,
old code cannot read the new envelope: keep the protected runtime and this version
intact; test the old commit only with a separate fresh synthetic runtime. Do not
remove the marker, overwrite the protected files, or copy them between accounts as
an attempted recovery. Explicit plaintext export/recovery is not implemented or
performed. Partial conversion can be retried using this version on the same account.
Do not reset/clean the user's checkout. A later reviewed revert must retain encrypted
reader compatibility if it will use an already-protected runtime.

## Next integration slices (not implemented here)

1. Drive: reuse workspace IDs, TopicSource and the existing fixed-URL read-only client.
   Add per-actor OAuth state, expiry, PKCE and callback validation, a protected token
   store, revocation and an explicit connection UI. Select folders by stable IDs,
   not names; preserve account/workspace scope and the explicit allowlist. Test
   callback replay, denied consent, refresh expiry, disconnect and pagination with
   transport doubles before real consent. Current integration remains metadata-only;
   it cannot teach from undownloaded content.
2. Before real connection, approve OAuth client creation/configuration, redirect URI,
   requested scopes and persistence. `drive.metadata.readonly` is broader than a
   folder; an app allowlist does not narrow Google's grant. `drive.file` with Picker
   does not automatically grant access to every child of a selected folder. Decide
   the intended behavior against Google documentation, not an assumed permission.
   Never borrow ChatGPT connector tokens.
3. Notion: retain stable task/Topic/source IDs and the existing learning stores.
   Knowledge projection fields include Topic, Course, Mastery, Importance, Status,
   Last/Next Review, Weakness, Source and Notes. Mastery is not a single score.
   Preserve preparation/read/assessed/mastery distinctions. Batch synchronization
   only on explicit finish/sync, deduplicate before writing, read back afterwards;
   reconcile uncertain outcomes before retrying. Notion is not a lock. The real
   database schema/IDs and Slack channel mapping remain unverified. Existing records
   must be preserved; no migration or write is authorized by this design.

Drive auth references:
https://developers.google.com/identity/protocols/oauth2/web-server
https://developers.google.com/workspace/drive/api/guides/api-specific-auth

# Round 1 verification evidence

Verified 2026-11-02, approximately 16:36 UTC. Baseline and branch are in README.
Evidence directory (`E` below): `/workspace/scratch/learning-os-round1`.
Python (`P`): `/workspace/.venvs/deeptutor/bin/python` (3.12.14).
Frontend used installed Node 24.19.0; the setup guide recommends Node 22 LTS.
A Node 22 matrix run was not performed. No dependency lock was changed.

Commands from repository root unless marked `web/`:

| Command | Result | Complete log |
| --- | --- | --- |
| `$P -m pytest tests/api/test_question_bank_api.py -q` before edits | 23 passed | `baseline-pytest.log` |
| `npm run test:unit -- tests/question-bank-tooltips.spec.tsx` in web/ before edits | 1 passed | `baseline-vitest.log` |
| `npm run build` in web/ (overlapped editing) | exit 0; not pristine baseline | `baseline-build.log` |
| `$P -m pytest tests/api/test_practice.py tests/api/test_question_bank_api.py tests/api/test_notebook_api_contract.py tests/api/test_book_quiz_attempt_notebook.py tests/tools/test_question_bank_tool.py tests/services/test_notebook_service.py -q` | 121 passed | `pytest-final.log` |
| `npm run test:unit -- tests/question-source.spec.tsx tests/question-bank-tooltips.spec.tsx` in web/ | 3 passed | `vitest-source.log` |
| `npm run typecheck` in web/ | exit 0 | `typecheck-final.log` |
| `npm run lint` in web/ | exit 0, 0 errors, 58 warnings at unchanged code locations | `lint.log` |
| `npm run i18n:check` in web/ | exit 0; parity OK, existing literal-text audit findings | `i18n.log` |
| `npm run architecture:check` in web/ | exit 0, no dependency violations | `architecture.log` |
| `DEEPTUTOR_NEXT_DIST_DIR=.next-learning-os-build npm run build` in web/ | exit 0, compiled and prerendered | `final-build.log` |
| `DEEPTUTOR_HOME=$E/runtime $P scripts/export_frontend_contracts.py --check` | exit 0 | `contracts-check-python.log` |
| `npm run contracts:check` in web/ | exit 0 | `contracts-check-js.log` |
| `$P -m ruff check deeptutor/core/question_source.py deeptutor/services/practice/importing.py deeptutor/services/practice/storage.py deeptutor/api/routers/question_notebook.py deeptutor/services/session/sqlite_store.py tests/api/test_question_bank_api.py tests/api/test_practice.py` | all passed | `ruff-check.log` |
| Same file list with `$P -m ruff format --check` | 7 files already formatted | `ruff-format.log` |
| `node $E/browser-import.cjs` | real UI upload/confirm/reload, repeated import, mobile no horizontal overflow, no JS page errors | `browser-import-final.log` |
| `node $E/browser-restart.cjs` after terminating/restarting only our backend | same imported record after restart; all 4 labels visible at 390px | `browser-restart.log` |
| `git diff --check` | exit 0 | final execution record |

The browser scripts use installed Playwright and a task-local Chromium executable.
They call the running frontend and backend; there is no route mocking. The backend
uses `$E/runtime` and synthetic fixtures only. `live-create.json`, `live-list.json`,
`live-after-restart.json` and `live-after-import.json` capture actual API responses.
`restart-check.log` compares identity, metadata, Chinese text and all five options
before/after a complete backend process restart.

Screenshots: `import-desktop.png`, `source-mobile-viewport.png`, `source-labels.png`.
`import-mobile.png` is an earlier full-page capture affected by the app's nested
scroll container; use the viewport and source-label captures for readable evidence.

## Honest limits and intermediate failures

- Full Python/Vitest/Node/E2E suites were not run; focused source, practice and
  adjacent API/storage regressions were run. Models, RAG, external services,
  deployment, real phones and cross-account/device continuity were not tested.
- Model startup reports no active LLM configured. This does not block source CRUD.
- Ruff was initially absent and was installed in the existing development venv;
  the first format check failed on test formatting and was corrected, then passed.
- Initial browser `networkidle` waited on a long-lived calendar stream. The final
  scripts wait for DOM readiness plus concrete UI/API outcomes. An initial duplicate
  assertion raced UI refresh; SQLite showed one record, and waiting for commit plus
  reload passed. Initial logs remain for review.
- One contracts-check invocation used the repository root instead of web/ and failed
  with missing package.json; rerunning from web/ passed. No code workaround needed.
- Next rewrote next-env.d.ts/tsconfig.json while starting dev; only those generated
  edits were restored to their clean baseline. Build and dev used separate caches
  for final verification. Both initial and final outputs remain, uncommitted.
- Initial contract export created missing non-secret default settings under the
  repository's ignored data directory. Existing settings were not replaced. Later
  export/startup used the isolated runtime. No learner data/credential contents were
  read; no existing runtime database was opened for migration or test fixtures.
- No supported external preview forwarding tool was available. Loopback success
  proves only managed-instance access. Reproduction steps are in README.

## Change map

| File | Purpose |
| --- | --- |
| `deeptutor/core/question_source.py` | Shared validation for four explicit labels |
| `deeptutor/api/routers/question_notebook.py` | Accept/return optional source metadata |
| `deeptutor/services/session/sqlite_store.py` | Additive migration, transactional save, list/detail serialization |
| `deeptutor/services/practice/importing.py` | JSON/CSV/XLSX normalization; explicit-source-aware identity |
| `deeptutor/services/practice/storage.py` | Persist source metadata on confirmed import |
| `tests/api/test_question_bank_api.py` | Restart, legacy migration, partial save, invalid labels, original options |
| `tests/api/test_practice.py` | Import/readback, source-aware dedup, invalid CSV labels |
| `web/lib/notebook-api.ts` | Source metadata types for consumers/saves |
| `web/components/space/question-bank/QuestionCard.tsx` | Mount the source display |
| `web/components/space/question-bank/QuestionSource.tsx` | Four labels and unknown states |
| `web/tests/question-source.spec.tsx` | Known/missing/legacy source rendering |
| `web/contracts/schema/openapi.json`, `web/contracts/generated/api.ts` | Generated backend/frontend contract updates |
| `web/locales/{de,en,fr,ja,pl,pt,tr,uk,vi,zh}/app.json` | Four source-label catalog keys; Chinese localized, other additions English |
| `docs-for-dev/learning-os/README.md` | Public-safe requirements, inventory, decisions, trial, rollback and PR draft |
| `docs-for-dev/learning-os/evidence.md` | Commands, outcomes, limitations and file map |
| `docs-for-dev/learning-os/synthetic-import.json` | Uploadable synthetic UI fixture |
| `docs-for-dev/learning-os/synthetic-question.json` | Synthetic direct-upsert fixture |

The complete patch includes tracked changes **and all new files**; it is saved as
`$E/complete.patch` alongside `final-status.txt` and `diff-stat.txt`. No Git index,
branch reference or commit was changed. This is ready for user trial, not a claim
that the broader product migration or deployment is complete.

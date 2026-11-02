# Round 1 supervisory verification supplement — 2026-11-02

Only tests and handoff documentation changed in this supplement. No product
functionality, commit, push, merge, deployment or second-round work was added.
The original working directory and first-round changes remain intact.

## Added checks

- `test_source_metadata_null_preserves_and_empty_object_clears`: explicit null
  preserves all four labels; `{}` clears them to unknown; same entry ID remains;
  list readback and a reopened SQLite store confirm the cleared result.
- `test_source_less_import_keeps_fixed_baseline_hash`: fixed expected ID for
  `question=2+2=?, A=3, B=4, answer=B` is
  `import:93ac4ed934d25236cbb843baa2fd8669d679ba203ae7a7b3513ffe14408cd238`.
  The clean baseline implementation independently produced this literal; missing,
  empty and null source metadata all preserve it in the new implementation.
- Extended `test_store_migrates_legacy_notebook_review_columns` with a genuinely
  pre-origin schema: session_id NOT NULL, UNIQUE(session_id,turn_id,question_id),
  no origin columns or source_metadata_json. This forces the origin table rebuild.
  All pre-existing row columns compare equal before/after, including ID, Chinese
  five-choice question, answer, image reference, bookmark and timestamps. The
  migrated schema has nullable session_id and origin/source columns; foreign key
  check is empty. New source labels save and survive a second store initialization.
  This covers this explicit schema and the immediately preceding schema, not every
  historical/custom/corrupted database or an arbitrary downgrade/re-upgrade.

## Exact commands and outcomes

Repository: `/workspace/DeepTutor`; Python: `/workspace/.venvs/deeptutor/bin/python`.
Supplement evidence: `/workspace/scratch/learning-os-round1-supplement` (S).

```bash
/workspace/.venvs/deeptutor/bin/python -m pytest tests/api/test_practice.py tests/api/test_question_bank_api.py tests/services/session/test_sqlite_store.py tests/api/test_notebook_api_contract.py tests/api/test_book_quiz_attempt_notebook.py tests/tools/test_question_bank_tool.py tests/services/test_notebook_service.py -q
```

Result: **172 passed in 4.77s** (`pytest.log`). Ruff check and format check passed
for all three modified test files (`ruff-check.log`, `ruff-format.log`). Product
and frontend code did not change, so the previous frontend/build results remain
applicable; these checks were not rerun just for test/document changes.

```bash
/workspace/.venvs/deeptutor/bin/python /workspace/scratch/learning-os-round1-supplement/restart_proof.py
```

The script starts an isolated, previously absent runtime, asserts an empty bank,
saves one synthetic question through HTTP, reads it back, terminates the actual
backend, waits for its exit and verifies its port is closed, then starts a new
backend process using the same runtime and reads the same record through HTTP.
It finally stops the second test process; neither process remains running.

Exact backend start command (same on both starts):

```bash
DEEPTUTOR_HOME=/workspace/scratch/learning-os-round1-supplement/restart-runtime-df6uubed /workspace/.venvs/deeptutor/bin/deeptutor serve --host 127.0.0.1 --port 18081
```

The first actual server PID was **7148**; the stop command was `kill -TERM 7148`.
The second actual server PID was **7165**, subsequently stopped by `kill -TERM 7165`.
Both server logs show application shutdown complete and finished server process;
Popen wait observed exit status -15. The paired evidence confirms entry ID 1,
origin `synthetic:source-demo:v1`, original number `12(b)`, all source labels,
Chinese question, five options and created/updated timestamps are unchanged.
The original question is `【合成資料】下列哪個選項代表五？`; options are A 一, B 二,
C 三, D 四, E 五. Metadata is synthetic-exam.pdf, 2024, PDF page 3, number 12(b).

Raw evidence: `restart_proof.py`, `restart-proof.json`, `restart-proof.log`,
`before.json`, `after.json`, `backend-before.log`, `backend-after.log`.

## Clean baseline patch check

```bash
git worktree add --detach /workspace/scratch/learning-os-round1-supplement/clean-baseline f7aed0744c36c5afef16a4261c31ebee1208cac2
git -C /workspace/scratch/learning-os-round1-supplement/clean-baseline rev-parse HEAD
git -C /workspace/scratch/learning-os-round1-supplement/clean-baseline status --porcelain=v1
git -C /workspace/scratch/learning-os-round1-supplement/clean-baseline apply --check /workspace/scratch/learning-os-round1-supplement/complete.patch
```

Result: exact baseline HEAD, clean status before/after, apply check exit 0.
Only checked applicability; did not apply changes to either checkout. The detached
worktree remains available, without changing the original branch or user files.
`apply-check.json` records argv, working directory, exit codes and output.
`worktree-create.log` captures creation; `baseline-hash.log` captures the original
importer's fixed hash from this unmodified worktree.

## Review package layout

The new complete package supersedes the earlier patch and adds these tests/docs.
Root contains complete.patch, README.md, evidence.md, supplement.md, synthetic
fixtures, final-status.txt and diff-stat.txt. `evidence/round1/` preserves original
logs, screenshots, browser scripts and HTTP responses referred to by the first
handoff; `evidence/supplement/` contains every new raw evidence file named above.
No runtime databases, settings, tokens, installed browsers or node_modules are
packaged. SHA256SUMS covers every payload file in the ZIP, excluding only itself
(self-hashing is not possible); a separate outer ZIP hash is reported at delivery.

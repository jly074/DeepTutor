# Trial lifecycle reliability — fourth increment

Scope: preserve the Windows trial workflow, reuse the existing launcher, and
improve argv handling, owned-process cleanup and failure gating. Windows remains
unverified; this is not deployment or automatic update infrastructure.

## Changes

- `runtime/npm_command.py`: on Windows, resolve the standard npm-cli.js beside
  the npm shim and invoke `[node, npm-cli.js, ...args]`. No cmd.exe, shell=True,
  command-string concatenation, ExecutionPolicy change or arbitrary script URL.
  Unknown installation layouts fail with an actionable message. Both trial deps
  and existing launcher install/build/dev calls use the helper. POSIX argv stays unchanged.
- `scripts/learning_trial_worker.py`: runs under the trial venv and reuses
  `launcher._spawn` and `_terminate_all`. It monitors only the child it creates,
  retains observed descendants, and verifies that observed processes exited.
  Ctrl+C requests cancellation; a repeated signal requests faster cleanup.
- Outer trial process waits for the worker while holding its existing exclusive
  lock. The worker writes `learning-trial-cleanup-pending` in the Git directory
  before spawning; it removes it only after cleanup. An incomplete/aborted cleanup
  retains the guard and lock for manual inspection, rather than allowing an update.
- `learning-trial-failure.json` records a pending/failed action. Failed update blocks
  deps/start until update succeeds. Failed deps/start blocks direct start; recover
  with successful deps (and an update if the code version needs repair).
  Dependencies still receive a success stamp only after all installation commands pass.

The supervisor uses existing bounded termination, not a new general process manager.
It does not kill unrelated processes. It does not claim proof against every possible
unobserved detached child: observed survivors retain the lock; unknown platform behavior
remains a Windows trial gate. Third-party installers run through the existing foreground
subprocess path; their complete cancellation trees are not newly certified here.

## Validation and limits

Tests run in Linux with isolated local Git fixtures and synthetic processes. The real
cancellation test starts an outer lock-holder, worker, parent and child in temporary
paths containing spaces; sends SIGINT to the outer console group; verifies zero exit,
child no longer alive, guard removed and lock released. A real child exit code 7 is
propagated. A separate mocked start failure checks the persistent start block.

Windows command construction is tested with shell metacharacters preserved as a single
argument. The resulting Node/JS argv is also executed on the Linux host to check argument
preservation. This is not a Windows npm installation test. Existing launcher console-flag
unit tests stub argv construction to isolate their original concern.

Selected commands (not a full repository suite):

```sh
python -m pytest tests/scripts/test_learning_trial.py tests/scripts/test_learning_trial_reliability.py tests/scripts/test_update.py tests/scripts/test_start_web.py tests/runtime/test_launcher_shutdown.py tests/runtime/test_launcher.py -v
ruff check scripts/learning_trial.py scripts/learning_trial_worker.py deeptutor/runtime/npm_command.py deeptutor/runtime/launcher.py tests/scripts/test_learning_trial.py tests/scripts/test_learning_trial_reliability.py tests/runtime/test_launcher.py
```

Final result: **96 passed in 7.07s**; Ruff check and git diff whitespace check passed.

No Windows runner, PowerShell or Windows host was available. Windows npm layout,
console signal delivery, process-tree cleanup, real dependency installation and app startup
remain unverified. The first test pass exposed an old Windows-platform mock lacking an npm
installation fixture; that console-only test now stubs npm argv, with separate argv tests.
No real Google/Notion/model credentials or requests were used.

## Three-step Windows trial after approved publication

1. Follow `windows-trial.md` for a new checkout/home, then status and deps. Expect
   the published full SHA, separate runtime and successful dependency stamp.
2. Start and view the synthetic Drive reference page. In another terminal try update:
   expect the active lock to block it. Press Ctrl+C in the start terminal and wait for
   cleanup to finish; verify the trial processes ended before proceeding.
3. Update/deps/start again. Expect no-new-version or a specific new SHA; a failed update
   must block deps/start until update succeeds. Preserve any guard/lock after abnormal
   termination for inspection; do not delete it merely to bypass protection.

Git/data isolation from the previous increment is unchanged. Do not adopt real runtime
or secrets during this trial. Runtime migrations remain application behavior, not a Git
rollback guarantee. To roll back this increment, preserve failed-process evidence and data,
stop owned trial processes, then use a separately reviewed older checkout with compatible
backup data. Do not rewrite the preceding commits or reset/clean local work.

## Separate design deliverable

`brain-notion-design.md` inventories current task, journal, evidence, memory, workspace and
source models and proposes a bounded local projection experiment. It is design only;
no Notion adapter, schema migration, simulation or live connection was implemented.

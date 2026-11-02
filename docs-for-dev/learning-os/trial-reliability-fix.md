# Fourth-increment review repair

This supplements `trial-reliability.md`; it does not add a new product increment.
The brain/Notion design is unchanged.

Failure records now contain independent update/deps/start stage entries. A successful
update, including no-op update, removes only update failure. Successful deps removes
deps and start failures. Direct start remains blocked while any failure is present.
The previous single-action format is migrated conservatively; writes use a temporary
file and atomic replacement. Invalid records still require manual inspection.

Supervisor outcomes no longer turn cancellation into success: observed nonzero child
exit is preserved; otherwise cancellation returns 130. The outer CLI reports the child
exit code without printing command arguments. Clean cancellation releases guard/lock
but leaves the start gate, so run successful deps before starting again. The usual
update → deps → start workflow remains valid; update alone cannot clear this gate.

Cleanup errors produce `SupervisionFailure` with original exit code, original exception,
cleanup exception and cancellation flag. Exceptions remain available as attributes and
chained context; safe diagnostic fields (types, code, flag and supervisor PID) are written
to the retained guard. If diagnostic writing fails, the exception adds a note and the
existing guard remains. No exception messages, commands or credentials go into the guard.
Signal handlers are restored even when initial guard writing fails.

Validation: original selected 96-case coverage plus 8 new parametrized cases:
- start failure → no-op update → start blocked; successful mocked deps recovers;
- deps failure → no-op update → start blocked; successful mocked deps recovers;
- legacy failure format retained across update;
- controlled cancel + exit 7 returns 7;
- controlled repeated cancel sets forced cleanup and returns 130;
- controlled cleanup exception + exit 7 preserves diagnostics and lock;
- actual guard write failure restores signal handlers;
- controlled primary and cleanup exceptions are both retained.

Command:
`python -m pytest tests/scripts/test_learning_trial.py tests/scripts/test_learning_trial_reliability.py tests/scripts/test_learning_trial_repair.py tests/scripts/test_update.py tests/scripts/test_start_web.py tests/runtime/test_launcher_shutdown.py tests/runtime/test_launcher.py -v`

Result: **104 passed in 7.40s**. Ruff and diff checks pass. The existing real Linux
process-tree cancellation test remains included; its outer subprocess now correctly
exits nonzero because worker cancellation is exit 130. Repeated cancellation and cleanup
fault combinations are controlled mocks, not Windows process experiments. Windows still
requires real validation. No guarantee about arbitrary unobserved detached processes is added.

Recovery: preserve diagnostics if guard/lock remain; inspect only owned trial processes
before manual recovery. Do not delete a guard just to bypass it. No changes to runtime data,
remote publication, credentials or prior commits are part of this repair.

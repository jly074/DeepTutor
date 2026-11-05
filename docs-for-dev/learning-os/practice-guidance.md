# Question evidence, supplementary guidance and delayed retest

Baseline `24e68dd058d71c29a89679b5e5b09b5777604c36`; validated 2026-11-05.
Scope: the existing Practice session, not a new tutor application or a global
concept-mastery model. No model/provider calls or new credentials are introduced.

## Behavior and evidence

Practice now shows original source metadata and a guidance panel. The user
explicitly identifies provenance (unknown/original/recalled/adapted/simulated)
and confirms question quality. Unknown is the default. Missing images or disputed
questions return no objective check verdict and reject new practice reviews.
Unknown quality never produces a weakness diagnosis in this panel. Existing
legacy mistake counts are historical labels, not new concept diagnoses.

Supplementary explanations are user-entered and require a source/location. The
existing saved explanation remains available after answer reveal; neither is
advertised as model-generated or independently fact-checked. The quality choice
is a user attestation, not automatic verification of an external image or document.
Original question language, options, answer and provenance are not rewritten.

The existing transactional review ledger and scheduler are reused. A confirmed
objective wrong attempt provides question-specific evidence; saving exits the
current round rather than immediately recycling it. The existing scheduler's
`again` delay is approximately ten minutes. The due queue uses the saved time.
Manual opening before due remains possible, but an early correct attempt is not
counted as a delayed retest. A correct attempt after the most recent wrong
attempt's due time yields `delayed_retest_correct`. Correct once, delayed correct
and self-report never establish long-term mastery. Existing review responses now
return `mastered: false` plus `mastery: not_established`; historical outcomes are
retained unchanged. This slice does not fit or infer a concept-level mastery score.

## Storage and correction

Two additive tables in the existing account/workspace notebook database retain
current guidance and immutable correction requests. No parallel task or learning
database is created. Guidance requests have a unique ID and expected version;
retries are idempotent, reused IDs with changed payloads and stale versions fail.
Confirmation/correction also invalidates an open review's version.

Each new review retains the guidance version and a digest plus snapshot of the
question, options, answer, explanation and source metadata. The original notebook
answer is not overwritten. Current evidence must match the current content digest
and guidance version, and must not be a self-report. Source or guidance corrections
preserve old attempts while excluding them from current diagnosis. Legacy attempts
without these snapshots remain historical rather than being silently upgraded.
New tables use existing foreign-key deletion behavior; no data deletion is performed.

## Validation and limitations

- 35 Python tests: existing practice behavior, complete controlled-time retest
  lifecycle, Chinese five-option/source preservation, missing-image/dispute gates,
  concurrent retry deduplication, correction invalidation, snapshot preservation,
  source-reference validation, self-report exclusion and authenticated account /
  workspace isolation.
- 18 rendered UI tests: existing Practice flows plus cited-note validation and
  exact retry payload preservation after an uncertain response.
- Actual API + Chromium mobile viewport: synthetic source confirmation, cited
  note, wrong answer, deferred save, reload and retained five original options.
- Actual backend restart: PID 45340 stopped; PID 45503 used the same isolated
  runtime; full question/state/guidance JSON remained identical. Test services stop
  afterward and both earlier and final synthetic runtimes remain preserved.
- The delayed-time transition is tested with a controlled clock; no claim of
  a real-time ten-minute user trial, physical phone or Windows validation.
- Typecheck, new-file lint, Ruff, contracts and architecture checks pass. Existing
  PracticeSession has one ref-during-render lint error reproduced from the baseline;
  this is not represented as a clean whole-project lint run.

## Three-step acceptance

1. Open a synthetic question in Practice. Check its original text, all options and
   source fields. Expand source confirmation, mark synthetic/verified, and save a
   supplementary explanation with its source location.
2. Answer incorrectly, reveal the reference, then save and retest later. Reopen:
   expect the saved attempt ID, supplemental guidance, due time and waiting state.
   Flagging the question as missing-image/disputed instead blocks review saves.
3. After the displayed delay, answer correctly. Expect delayed-retest-correct,
   still not long-term mastery. Correcting guidance/source preserves historical
   attempts but requires fresh evidence for the corrected version.

This environment has no confirmed authenticated external preview. Screenshots and
private test artifacts are evidence, not a live app URL. No push/deployment occurred.
For rollback, stop the service and preserve a runtime backup; use a separate
baseline checkout with a copy of data. Keep additive tables and historical records.
Reverting code does not undo any user confirmations already saved.

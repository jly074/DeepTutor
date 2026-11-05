# Integration and dependency security review

Reviewed 2026-11-05 from `98f6313b5e35fd9b0ad0a1ae2175220961095493`, clean `work` branch. All earlier commits preserved. No feature added, push, deployment, schedule activation or external account provisioning.

## Reproducible repair

Production npm audit originally reported 22 affected dependency entries: 14 high, 4 moderate, 4 low, zero critical. Updated only six lockfile nodes, preserving package.json and framework versions:

| Package | Before | After |
| --- | --- | --- |
| DOMPurify | 3.4.0 | 3.4.17 |
| source-map-js | 1.2.1 | 1.2.2 |
| brace-expansion, root | 1.1.14 | 1.1.21 |
| brace-expansion, readdir-glob | 2.1.1 | 2.1.7 |
| brace-expansion, openapi-core (dev) | 2.1.4 | 2.1.7 |
| fflate | 0.8.2 | 0.8.3 |

After installation, `npm audit --omit=dev --json` reports **7 entries: 3 moderate, 4 low, zero high/critical**. The Next.js high entry was inherited through postcss/source-map-js, not a new direct Next advisory. Remaining chains involve uuid (exceljs/mermaid) and KaTeX (math rendering packages). Removing those findings requires compatibility work across major/minor API boundaries; no forced override applied. Audit is advisory matching, not exploit testing or a guarantee of safety. No Python vulnerability audit was performed; pip check confirms dependency consistency only.

## Integration evidence

One isolated synthetic runtime was used for task evidence/deadline corrections, calendar overlap/free-time calculation, practice guidance and delayed retest, Unsorted versioned files, handoff receipts and the succession checklist. Real local HTTP API plus Chromium tested all six native pages. Same-runtime conflict checks cover stale deadline and subsequent explicit correction, stale handoff and fresh idempotent acceptance, review replay/conflicting payload, stale guidance, disputed grading, and stale intake classification.

Actual backend process stop/start preserved task identity/status/history, fixed events and availability, practice content/state/evidence, file versions and original hashes, handoff receipts and checklist counts. Equality excludes only the read timestamp and a time-derived retest waiting/due label; raw before/after evidence is retained. Delayed future transitions are controlled-clock unit tests, not a claimed real multi-day wait. Final production build pages were checked again after dependency updates.

- Functional Python regression: 300 passed.
- Credential/config/security regression: 466 passed, 24 skipped, 2 warnings. One skip needs real Windows DPAPI; 23 need the absent optional fastapi-guard package. No guard package or security setting was enabled.
- Feature UI regression: 33 passed; markdown/math/preview/Mermaid regression: 14 passed.
- Node: 1335 passed; typecheck, contracts, architecture and production build passed.
- Known lint remains: CalendarPage has three set-state-in-effect errors; PracticeSession has one ref-during-render error. Both reproduced against the starting HEAD. This is not a whole-repository lint pass.

## Data and credential boundary

Task, handoff, intake registry and provider references are account/workspace scoped. General FileLibrary blobs remain account scoped; registry isolation is not a new per-workspace blob ACL. Sensitive original materials remain outside these cloud trial tests. Native task/intake/calendar/readiness paths used no real provider requests; Drive/Notion fixtures used explicitly marked demo clients. Existing ChatGPT/dot connectors are not product credentials.

Drive OAuth requests metadata-readonly, online access, bounded fixed Google endpoints, no refresh-token persistence, and owner/workspace-bound protected storage. That protection uses Windows DPAPI; it is not verified on Windows and unavailable on this Linux host. Generic provider settings remain plaintext unless the supported opt-in Windows protection is enabled. Do not treat every credential store as encrypted. Notion live access requires explicitly matched owner/workspace environment configuration and a read token; no token was created or configured. No true Drive/Notion/Slack/Calendar account, physical device, cloud continuity or notification delivery was accepted by this review.

## Program delivery

Evidence archives contain logs/screenshots and synthetic verification, **not an application installer**. The remote review branch was still at `07442972c99744bb1453d36a86d925bab509e32c`; current local features are not obtainable via pull yet. A safe option is an incremental Git bundle against that exact published base, transferred only after explicit approval. Keep it separate from evidence archives; validate bundle hash, prerequisites, target commit and tree before import. Another option is an explicitly approved new remote branch. Neither happens implicitly.

After an approved bundle transfer: clone the named review branch into a new directory; require a clean checkout; verify the bundle; fetch its `work` ref; compare FETCH_HEAD with the accompanying approved SHA; merge only with `--ff-only`. Use the existing `learning_trial.py setup/status/deps/start` workflow with that local branch name and a new data home outside the checkout. Do not run `update` against the older remote while local commits are ahead; it correctly blocks. Dependencies must be installed after code update, and running services restarted separately. No reset, clean, stash, settings overwrite or existing runtime adoption is needed.

No user-reachable cloud preview is configured. A mobile screenshot is evidence, not an interactive mobile application. A phone cannot reach this cloud workspace's localhost. Authenticated hosting or a supported private preview requires a separately approved destination.

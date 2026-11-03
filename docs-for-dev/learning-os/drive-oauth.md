# Drive authorization and metadata references

Status: 2026-11-03. Incremental implementation after 8fa4e3bda. Local development
only; real Google consent and Windows DPAPI still require separate acceptance.

## Behavior and scope

The existing Learning > Drive sources page now has a native authorization panel.
It distinguishes missing administrator configuration, shared anonymous mode,
unavailable secure storage, consent required/expired, connected and operation
failure. It collects a stable folder ID and explicit consent, never a client
secret, authorization code or access token pasted by the user.

Only `https://www.googleapis.com/auth/drive.metadata.readonly` is requested.
Google grants metadata access across Drive: **this is not a folder-scoped Google
grant**. The application allowlist confines queries to the specified folder's
direct files. No recursive scan, shortcut following, content download, OCR,
embedding, model call, external write or background polling. This is a restricted
Google scope; Google consent/testing/verification requirements must be resolved
for the intended account before live use. `drive.file` is not substituted because
it does not provide arbitrary selected-folder child enumeration and permits writes.

The flow requests online access only, accepts an access-token lifetime of at most
one hour, and never saves a refresh token. This does not provide unattended sync.
A fresh grant has a fresh opaque connection ID, so changing Google accounts cannot
silently overwrite references from a prior grant. Saved references from earlier
grants remain visible in the same DeepTutor account/workspace, retaining their own
connection IDs. No Google email/profile scope is requested. Metadata references
remain `available=False`; teaching cannot treat them as downloaded materials.

## Setup gates (not performed by the development agent)

Before real use, explicitly approve and configure:

1. A real DeepTutor account/login. Shared `local-admin` fallback mode is blocked
   from OAuth start, completion and token use. No authentication setting is changed
   automatically. Partners cannot operate another account's OAuth lifecycle.
2. A Google OAuth **Web application** client, consent-screen configuration and the
   chosen metadata scope, using approved account/project access. Add test users or
   satisfy verification requirements as applicable. No app/project was created here.
3. Approved server-only secret provisioning for `DEEPTUTOR_GOOGLE_CLIENT_ID`,
   `DEEPTUTOR_GOOGLE_CLIENT_SECRET`, `DEEPTUTOR_GOOGLE_REDIRECT_URI`. Do not put secret
   values in Git, chat, browser storage or command history. These environment values
   enable the adapter but do not initiate consent or a Google request by themselves.
4. The exact redirect URI must be registered and end in `/drive-oauth-callback`,
   without query/fragment/userinfo. Local example (no secret):
   `http://127.0.0.1:3782/drive-oauth-callback`. Open the app at the same origin/port;
   `localhost` and `127.0.0.1` are not interchangeable. Non-loopback redirects require
   HTTPS. Deployment TLS, reverse-proxy log redaction and access controls still need
   review; no public deployment is included.
5. A Windows backend under the intended OS account. Tokens and pending PKCE data
   use Windows user-bound DPAPI. Linux/macOS remain blocked; there is no plaintext
   fallback. Validate real DPAPI with synthetic values first, before real consent.

An approved user can then enter the folder ID, read the scope/storage warning,
check consent, follow Google, refresh the direct-file list, and save references.
This is a real protocol adapter with mocked acceptance tests, not evidence that a
real account is connected. Model/ChatGPT connector credentials are never reused.

## Security and persistence

- Fixed Google authorization/token/metadata endpoints, verified TLS, bounded
  timeouts, no followed redirects on token/API requests. No callback-supplied URLs.
- Random 256-bit state, independent tab nonce, S256 PKCE, ten-minute expiry; state
  and nonce hashes plus verifier, folder and configuration binding are encrypted.
- OAuth state lives in an account-local SQLite store, keyed by account/workspace.
  Encrypted payloads repeat that binding and reject cross-owner swaps. Browser/body
  account IDs are never used to choose ownership.
- Callback compares state/tab/config/expiry, atomically consumes pending state
  before exchange, and atomically checks its claim before saving. Replay, duplicate
  callback, newer login or local disconnect cannot revive a superseded grant.
- The standalone callback route has no app layout/external assets, uses a strict
  script-hash CSP, no-store/no-referrer headers, and strips the code query before
  returning to the app. Completion is an authenticated POST; PKCE verifier/client
  secret/token never reach browser storage. Short-lived callback code and tab nonce
  are consumed from session storage. Next dev callback access logging is suppressed;
  external proxy logging must be configured separately before deployment.
- Tokens are encrypted before SQLite insertion. Only DPAPI ciphertext enters SQLite
  journals. OS-account peers can still decrypt; this is not OS-level isolation
  between DeepTutor accounts. Process memory and external backups are not covered.
- Provider 401 invalidates only the matching active grant. No refresh/retry occurs.
  Expiry requires explicit consent again; failed exchange consumes state and requires
  a new attempt. Other provider errors are safe statuses without response bodies.
- Local disconnect forgets the active token/pending grant; it does NOT revoke the
  Google-side grant or erase historical ciphertext from backups. Existing references
  and other workspaces remain intact. Google-side revocation is a separate action.

## Verification results

- Relevant Python service, HTTP, authorization-map and settings-protection tests:
  **192 passed, 1 skipped** (real Windows DPAPI).
- Frontend unit/callback tests: **8 passed**. Build, typecheck, targeted ESLint,
  Ruff, generated contracts and i18n checks passed.
- Broader Node suite: **1332 passed, 2 failed**. The two locale punctuation failures
  also fail with the baseline catalog files. No claim of a green full suite.
- Real local browser/API sequence with explicit Google, crypto and actor doubles:
  consent, callback, listing, save, reload, local disconnect and retained references.
  Desktop/mobile have no page errors or horizontal overflow. The final synthetic
  backend was stopped/restarted; paired grant expiry and source IDs are identical.
- Shared Drives, real Google consent, Windows host encryption, real multi-device
  access and production networking are unverified. Use a personal My Drive synthetic
  folder for the first approved live trial.

## Reproducible acceptance

Use synthetic fixtures first. The service test file explicitly replaces DPAPI with
an envelope-plumbing double and Google with `httpx.MockTransport`. The browser
fixture also simulates an authenticated actor and intercepts the Google navigation;
its screenshots are labeled TEST ONLY. No real credentials are needed.

```bash
python -m pytest tests/services/drive_source tests/multi_user/test_learning_surface_map.py tests/multi_user/test_account_presets.py tests/api/test_auth_contextvar.py tests/services/config/test_protected_settings.py -q
npm --prefix web run test:unit -- tests/drive-sources.spec.tsx tests/drive-authorization.spec.tsx tests/drive-callback.spec.ts
npm --prefix web run typecheck
npm --prefix web run contracts:check
npm --prefix web run build
```

The private review package supplies complete logs, the synthetic server/browser
scripts, PID stop/start commands and paired before/after readbacks. Restart testing
must use the same synthetic runtime directory, never the user's real runtime.

Three-step UI acceptance after the reviewed commit is made available:

1. Open Learning > Drive sources. With no client configuration, see an explicit
   setup block and no consent button. With approved configuration but no account,
   see the login requirement; with no Windows storage, see secure-storage blockage.
2. In the isolated synthetic harness, enter a stable folder ID and check consent.
   Complete the intercepted authorization; refresh and select a synthetic file.
   It must remain labeled as a metadata reference unavailable for teaching.
3. Reload and restart the backend: the same IDs/metadata and unexpired grant survive.
   Forget local authorization: saved references remain but querying requires consent.
   Wrong workspace, replay, timeout, denied consent and malicious folder input must
   not send an unauthorized metadata request or store credentials in plaintext.

Real Google consent and real Windows DPAPI are unrun. Full repository Python and
real multi-device/production tests are unrun. Broader Node tests expose existing
German/Turkish punctuation assertions, reproduced against the prior commit; these
are not claimed green. Existing npm dependency advisories from the previous security
milestone remain open. No further dependency upgrade is included here.

## Rollback and next step

Keep runtime and prior commits. Reverting this feature leaves encrypted token rows
in the private store; it does not revoke Google access. If a real grant was ever
created, explicitly forget/revoke it before removing the feature. Do not reset,
clean, delete runtime files or downgrade the earlier protected-settings reader.

The next acceptance gate is approved Windows + Google client setup, followed by a
real consent/read-only synthetic-folder trial. This is separate from authorizing
refresh tokens, background work, content processing, Notion/Slack writes or a push.

References consulted:
- https://developers.google.com/identity/protocols/oauth2/web-server
- https://developers.google.com/identity/protocols/oauth2/native-app
- https://developers.google.com/workspace/drive/api/guides/api-specific-auth

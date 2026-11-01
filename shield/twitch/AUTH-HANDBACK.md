# M3 auth implementation hand-back

Prepared child: `WORKTREE_t3-5c0ce3ee`, branch `t3/5c0ce3ee`,
HEAD `ec1d1f96a1c29ab82109c66f27064f3fd6cb326d`. Final observed branch is
`t3/twitch-auth-hardening`; the branch name changed externally during the session, with
no branch-mutating command from this child. HEAD stayed at the required SHA. Worktree was clean before copying the six
owned Python files from `WORKTREE_t3-3bb00dac`.
Evidence gathered 2026-10-29 PT (2026-10-30 UTC). No commits, staging, pushes, PRs,
worktree creation/removal, subagents, live Twitch/auth calls, personal keyring access, secrets/config
inspection, Mac/GPU/media jobs, or installs. Parent source files were read and copied only.
All test processes ran one at a time at nice 10; no heavy job was needed.

Final local result: **19 test methods pass**, with `ResourceWarning` treated as an error.
All **12 of 12** allowed unittest invocations were used; no TLC invocations.
This is the auth-owned suite, not the repository gate or the parent's full M3 suite.

## Changes and interfaces

- `auth.py:88`: login HTTP requests race the cancel event and the device deadline. Both
  helper tasks are cancelled and awaited on completion, event cancellation, or caller-task
  cancellation. A token response arriving at/after expiry is rejected. The new event-cancel
  regression failed for both initial device and token requests before this fix.
- `auth.py:49`, `auth.py:60`, `auth.py:78`: validate numeric lifetimes without leaking
  overflow/type exceptions; require a list containing exactly the three approved scopes;
  reject non-string bearer type, malformed bodies, and whitespace/control characters in
  credentials. Activation prompts require `https://www.twitch.tv/activate` with no fragment.
- `auth.py:180`: serialize shared-session refresh/validation with an asyncio lock because
  public device-flow refresh tokens are single-use. Concurrent callers share one rotation;
  the following rotation uses the replacement refresh token. Validation requires matching
  client ID, nonempty broadcaster identity, exact scopes, and a positive lifetime. The
  validation lifetime can shorten the cached token deadline.
- `http.py:14`: explicit empty or malformed mock origins fail closed instead of selecting
  the production origin. IPv4 loopback with an explicit valid port is the only mock origin.
  The existing operation allowlist and refusal of redirects remain.
- `http.py:40`: read until EOF or 65,537 bytes before decoding, rather than treating the
  first available stream chunk as a complete response. Limit stays 65,536 bytes; errors
  contain fixed local reasons. Deeply malformed JSON also produces a safe local error.
- `storage.py:18`: writing requires literal `remember=True`; truthy strings/integers no
  longer opt in. Reads enforce the same exact scope shape and sanitize failures. RAM remains
  the default; every storage test injects a Mock backend. No personal OS backend was opened.
- `keys.py` is copied unchanged from the parent, reviewed and covered by the local wire tests.
  `KeyProvider.get_key() -> Secret` and `HelixKeyProvider(session, http)` remain compatible.
  The provider validates through `UserSession.access_token()` before requesting a key.
- `test_http.py:52`: fixtures now construct public `Tokens` rather than calling `_tokens`.
  Both test classes install `network.local_network`; localhost tests exercise real aiohttp
  requests, form encoding, headers, and redirect refusal. The copied network guard lives
  only in ignored `.tmp/m3-auth/network.py`; do not copy it back. No `__init__.py` was needed.

The scope set is exactly `user:read:chat moderator:read:shield_mode channel:read:stream_key`.
No dependency or version was introduced; requirements and other M3 modules are untouched.

## Required caller integration and limits

**Idle hourly validation remains a caller integration requirement.** `access_token()`
validates on first use, at >=3,600 elapsed seconds when called, and after refresh. It does
not own a background timer. The parent's current `EventSubClient.start()` calls it at
startup (`transport.py:127`); `_PolicySocket._build_request_header()` calls it during
subscription requests (`transport.py:26`). There is no periodic idle-session call in that
file. M3 must schedule calls on the owning loop at least hourly, stop the active session
on validation failure, and cancel/await that timer at shutdown. I did not edit transport
or claim that a quiet, long-lived session currently validates autonomously.

The public session identity/client fields are assumed fixed for that session. Create a
new `UserSession` for another broadcaster or client. Session refresh locking is for one
owning asyncio loop; the parent transport already marshals calls to its owner loop.

HTTP/network errors fail the login attempt; there is no automatic connection-timeout retry.
The RFC backoff recommendation would apply if a caller later adds retry behavior.
Live service compatibility, real keyring backend behavior, actual wall-clock hourly
operation, and attended terminal presentation were not exercised. No CLI/root edits,
full gate, media bench, or transport test runs were performed in this child.

## Test seams and why these tests remain

DeviceAuth public login protects polling timing/expiry/cancellation and untrusted OAuth
response decoding; it does not establish live Twitch service behavior. UserSession plus
HelixKeyProvider over localhost protects identity validation, token rotation, and key
release; the fake clock establishes interval math rather than a one-hour real wait.
TwitchHTTP over localhost protects streamed reads, redirect refusal, response bounds and
operation/origin guards; TLS and upstream availability are outside this local test.
TokenStore with a mock OS backend protects explicit opt-in and credential decoding without
writing real account data. These are auth/privacy contracts and behavioral regressions;
no production hook was added solely to expose state to tests.

The baseline owned tests were already green. There is **no claim of red-before-implementation
for the copied baseline** (nor for the parent's broader nine-test report). New fix reds:
`02` leaves HTTP running after cancel; `04` leaks type/overflow errors and accepts malformed
scope/credential/activation fields; `06` accepts empty mock origin and parses a partial
JSON chunk; `08` refreshes three times with the same token; `10` accepts implicit keyring
opt-in/malformed stored scopes/invalid validation claims and ignores validation lifetime.
The HTTP red log includes a localhost server connection-reset traceback after the client
prematurely closed the partial response; final runs have no such error.

## Exact unittest invocations and logs

Each command ran from `WORKTREE_t3-5c0ce3ee`, with output redirected
to the named absolute log. Counts below are unittest **method** counts; a failed method
can report multiple subtest failures/errors. Commands 01 and 02 were followed by `cat`,
so their enclosing shell exit status was 0; the recorded unittest verdicts below, not
that shell status, are the receipts. Commands 03–12 explicitly preserved the Python exit.

01. `Ran 5 tests in 0.052s`; **OK**. [Log](/tmp/agents/irl-shield/m3-auth/01-baseline.log)

```bash
PYTHONPATH="$PWD:$PWD/.tmp/m3-auth" nice -n 10 WORKTREE_t3-3bb00dac/.tmp/m3/py311/bin/python -m unittest discover -s tests/m3 -p 'test_*.py' -v > /tmp/agents/irl-shield/m3-auth/01-baseline.log 2>&1
```

02. `Ran 3 tests in 0.225s`; **FAILED (failures=2)**. [Log](/tmp/agents/irl-shield/m3-auth/02-cancel-red.log)

```bash
PYTHONPATH="$PWD:$PWD/.tmp/m3-auth" nice -n 10 WORKTREE_t3-3bb00dac/.tmp/m3/py311/bin/python -m unittest discover -s tests/m3 -p 'test_auth.py' -v > /tmp/agents/irl-shield/m3-auth/02-cancel-red.log 2>&1
```

03. `Ran 3 tests in 0.026s`; **OK**. [Log](/tmp/agents/irl-shield/m3-auth/03-cancel-green.log)

```bash
PYTHONPATH="$PWD:$PWD/.tmp/m3-auth" nice -n 10 WORKTREE_t3-3bb00dac/.tmp/m3/py311/bin/python -m unittest discover -s tests/m3 -p 'test_auth.py' -v > /tmp/agents/irl-shield/m3-auth/03-cancel-green.log 2>&1
```

04. `Ran 5 tests in 3.057s`; **FAILED (failures=3, errors=6)**. [Log](/tmp/agents/irl-shield/m3-auth/04-malformed-red.log)

```bash
PYTHONPATH="$PWD:$PWD/.tmp/m3-auth" nice -n 10 WORKTREE_t3-3bb00dac/.tmp/m3/py311/bin/python -m unittest discover -s tests/m3 -p 'test_auth.py' -v > /tmp/agents/irl-shield/m3-auth/04-malformed-red.log 2>&1
```

05. `Ran 8 tests in 0.186s`; **OK**. [Log](/tmp/agents/irl-shield/m3-auth/05-malformed-green.log)

```bash
PYTHONPATH="$PWD:$PWD/.tmp/m3-auth" nice -n 10 WORKTREE_t3-3bb00dac/.tmp/m3/py311/bin/python -m unittest discover -s tests/m3 -p 'test_*.py' -v > /tmp/agents/irl-shield/m3-auth/05-malformed-green.log 2>&1
```

06. `Ran 5 tests in 0.122s`; **FAILED (failures=2)**. [Log](/tmp/agents/irl-shield/m3-auth/06-http-red.log)

```bash
PYTHONPATH="$PWD:$PWD/.tmp/m3-auth" nice -n 10 WORKTREE_t3-3bb00dac/.tmp/m3/py311/bin/python -m unittest discover -s tests/m3 -p 'test_http.py' -v > /tmp/agents/irl-shield/m3-auth/06-http-red.log 2>&1
```

07. `Ran 10 tests in 0.414s`; **OK**. [Log](/tmp/agents/irl-shield/m3-auth/07-http-green.log)

```bash
PYTHONPATH="$PWD:$PWD/.tmp/m3-auth" nice -n 10 WORKTREE_t3-3bb00dac/.tmp/m3/py311/bin/python -m unittest discover -s tests/m3 -p 'test_*.py' -v > /tmp/agents/irl-shield/m3-auth/07-http-green.log 2>&1
```

08. `Ran 6 tests in 0.163s`; **FAILED (failures=1)**. [Log](/tmp/agents/irl-shield/m3-auth/08-rotation-red.log)

```bash
PYTHONPATH="$PWD:$PWD/.tmp/m3-auth" nice -n 10 WORKTREE_t3-3bb00dac/.tmp/m3/py311/bin/python -m unittest discover -s tests/m3 -p 'test_http.py' -v > /tmp/agents/irl-shield/m3-auth/08-rotation-red.log 2>&1
```

09. `Ran 13 tests in 0.267s`; **OK**. [Log](/tmp/agents/irl-shield/m3-auth/09-rotation-wire-green.log)

```bash
PYTHONPATH="$PWD:$PWD/.tmp/m3-auth" nice -n 10 WORKTREE_t3-3bb00dac/.tmp/m3/py311/bin/python -m unittest discover -s tests/m3 -p 'test_*.py' -v > /tmp/agents/irl-shield/m3-auth/09-rotation-wire-green.log 2>&1
```

10. `Ran 11 tests in 0.164s`; **FAILED (failures=6, errors=2)**. [Log](/tmp/agents/irl-shield/m3-auth/10-claims-storage-red.log)

```bash
PYTHONPATH="$PWD:$PWD/.tmp/m3-auth" nice -n 10 WORKTREE_t3-3bb00dac/.tmp/m3/py311/bin/python -m unittest discover -s tests/m3 -p 'test_http.py' -v > /tmp/agents/irl-shield/m3-auth/10-claims-storage-red.log 2>&1
```

11. `Ran 16 tests in 0.195s`; **OK**. [Log](/tmp/agents/irl-shield/m3-auth/11-claims-storage-green.log)

```bash
PYTHONPATH="$PWD:$PWD/.tmp/m3-auth" nice -n 10 WORKTREE_t3-3bb00dac/.tmp/m3/py311/bin/python -m unittest discover -s tests/m3 -p 'test_*.py' -v > /tmp/agents/irl-shield/m3-auth/11-claims-storage-green.log 2>&1
```

12. `Ran 19 tests in 0.346s`; **OK**. [Log](/tmp/agents/irl-shield/m3-auth/12-final.log)

```bash
PYTHONPATH="$PWD:$PWD/.tmp/m3-auth" nice -n 10 WORKTREE_t3-3bb00dac/.tmp/m3/py311/bin/python -W error::ResourceWarning -m unittest discover -s tests/m3 -p 'test_*.py' -v > /tmp/agents/irl-shield/m3-auth/12-final.log 2>&1
```

## Final test inventory

- [test_server_interval_and_slow_down_apply_before_every_poll](WORKTREE_t3-5c0ce3ee/tests/m3/test_auth.py:50)
- [test_expiry_denial_and_cancellation_never_continue_polling](WORKTREE_t3-5c0ce3ee/tests/m3/test_auth.py:63)
- [test_cancellation_aborts_inflight_device_and_token_requests](WORKTREE_t3-5c0ce3ee/tests/m3/test_auth.py:83)
- [test_malformed_token_responses_fail_with_safe_local_errors](WORKTREE_t3-5c0ce3ee/tests/m3/test_auth.py:116)
- [test_malformed_device_responses_never_reach_presenter](WORKTREE_t3-5c0ce3ee/tests/m3/test_auth.py:131)
- [test_omitted_interval_defaults_to_five_and_slow_down_accumulates](WORKTREE_t3-5c0ce3ee/tests/m3/test_auth.py:146)
- [test_expiry_during_response_rejects_late_credentials](WORKTREE_t3-5c0ce3ee/tests/m3/test_auth.py:165)
- [test_key_stays_redacted_and_wrong_identity_never_requests_key](WORKTREE_t3-5c0ce3ee/tests/m3/test_http.py:56)
- [test_refresh_rotation_and_hourly_validation](WORKTREE_t3-5c0ce3ee/tests/m3/test_http.py:72)
- [test_keyring_is_explicit_and_mock_only](WORKTREE_t3-5c0ce3ee/tests/m3/test_http.py:85)
- [test_streamed_json_waits_for_complete_bounded_response](WORKTREE_t3-5c0ce3ee/tests/m3/test_http.py:100)
- [test_fixed_origin_redirect_and_response_guards](WORKTREE_t3-5c0ce3ee/tests/m3/test_http.py:125)
- [test_concurrent_access_rotates_refresh_token_once_and_uses_new_token_next](WORKTREE_t3-5c0ce3ee/tests/m3/test_http.py:149)
- [test_device_flow_over_localhost_encodes_exact_scopes_and_poll_timing](WORKTREE_t3-5c0ce3ee/tests/m3/test_http.py:178)
- [test_cancel_event_aborts_localhost_token_response](WORKTREE_t3-5c0ce3ee/tests/m3/test_http.py:219)
- [test_validation_rejects_malformed_claims_before_releasing_a_key](WORKTREE_t3-5c0ce3ee/tests/m3/test_http.py:249)
- [test_validation_lifetime_limits_when_refresh_must_happen](WORKTREE_t3-5c0ce3ee/tests/m3/test_http.py:264)
- [test_keyring_rejects_malformed_scopes_and_sanitizes_read_failures](WORKTREE_t3-5c0ce3ee/tests/m3/test_http.py:277)
- [test_malformed_or_denied_key_response_never_returns_a_key](WORKTREE_t3-5c0ce3ee/tests/m3/test_http.py:293)

## Primary sources

Checked 2026-10-29 PT, public documentation only:

- [Twitch device-code grant flow](https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/#device-code-grant-flow):
  device and token parameters, verification URI, `authorization_pending`/`invalid device code`
  messages, public-client support and single-use refresh-token behavior. The DCF-specific
  section is the source for public device-flow refresh support.
- [Twitch validating tokens](https://dev.twitch.tv/docs/authentication/validate-tokens/#who-must-validate-tokens):
  startup/hourly validation requirement and client/user/scopes/lifetime response fields.
- [Twitch refreshing tokens](https://dev.twitch.tv/docs/authentication/refresh-tokens/#how-to-use-a-refresh-token):
  public clients omit client_secret; retain returned replacement refresh tokens; form encoding.
- [Twitch Get Stream Key](https://dev.twitch.tv/docs/api/reference/#get-stream-key):
  `channel:read:stream_key`, required matching broadcaster/user identity and client ID.
- [Twitch scopes](https://dev.twitch.tv/docs/authentication/scopes/): scope meanings and
  minimum-required-scope policy. Exact requested selection comes from the M3 packet.
- [RFC 8628 §3.5](https://www.rfc-editor.org/rfc/rfc8628.html#section-3.5): poll no earlier
  than server interval (default five), add five seconds for each slow_down, and stop on
  denial/expiry/other terminal errors. Twitch-specific message fields are handled too.

## Files, hashes and process receipts

All deliverable paths below are new/untracked relative to prepared HEAD. This is expected:
`git ls-files --error-unmatch -- <six Python paths>` failed for all six, and nothing was
staged. HEAD remains the required SHA. `git diff --check` exits 0 but cannot examine
untracked files; a separate AST parse and trailing-whitespace check read all six files
successfully. Reviewed parent-relative diffs are in the scratch directory.

- [WORKTREE_t3-5c0ce3ee/shield/twitch/auth.py](WORKTREE_t3-5c0ce3ee/shield/twitch/auth.py)
  - SHA-256: `c2486778d8124cfbf42d62a41f9964328a180b828e0dc19c965c6f6fa4efcacf`
  - Parent at hand-back SHA-256: `bf91c41a7bc96bb5e5e05c8097625acc9d32e1e2de440c2d3b3f50cc0d24cc36`
- [WORKTREE_t3-5c0ce3ee/shield/twitch/http.py](WORKTREE_t3-5c0ce3ee/shield/twitch/http.py)
  - SHA-256: `3e327442e1e0477501d807f5815d283f903fb6dd5ca6d2dfb30cafa9040125e7`
  - Parent at hand-back SHA-256: `ce18e82b130aeb11ece6249966955f04688531356f2a4ce8963528731fe3cde0`
- [WORKTREE_t3-5c0ce3ee/shield/twitch/keys.py](WORKTREE_t3-5c0ce3ee/shield/twitch/keys.py)
  - SHA-256: `889ac382277054c22030c3b384308fde71cec75385eb0ef6bd8f9a32f15040f1`
  - Parent at hand-back SHA-256: `889ac382277054c22030c3b384308fde71cec75385eb0ef6bd8f9a32f15040f1`
- [WORKTREE_t3-5c0ce3ee/shield/twitch/storage.py](WORKTREE_t3-5c0ce3ee/shield/twitch/storage.py)
  - SHA-256: `7a7edcebd9a290c737403fb860bc5427db3584d41418c0282f63f514f0d7bee7`
  - Parent at hand-back SHA-256: `88b1f9b560d05ccc10fa4fecdba37746748aa15c62657cd2e9d7a2a33dfdccee`
- [WORKTREE_t3-5c0ce3ee/tests/m3/test_auth.py](WORKTREE_t3-5c0ce3ee/tests/m3/test_auth.py)
  - SHA-256: `32477eaac94fac49007af22b69e706b73096b9571fb44c4dd79fe82c1c93d6c0`
  - Parent at hand-back SHA-256: `736a0afa0d43117597264c78ecd6d25946838453827ee3681a64a8705885ce04`
- [WORKTREE_t3-5c0ce3ee/tests/m3/test_http.py](WORKTREE_t3-5c0ce3ee/tests/m3/test_http.py)
  - SHA-256: `6da83ecddb5b8debb834f84808a97dc34d53c8541ec423de04b53c731e9da5e7`
  - Parent at hand-back SHA-256: `43f1416d7ef6a92bc92a5bc90ab21f106c2a04c5dc2141dc70ac8c6b1f06bcca`

The hand-back itself is `WORKTREE_t3-5c0ce3ee/shield/twitch/AUTH-HANDBACK.md`. Its hash, plus hashes of
all source files and logs, is in [SHA256SUMS](/tmp/agents/irl-shield/m3-auth/SHA256SUMS).
All logs, parent-relative diffs and [file manifest](/tmp/agents/irl-shield/m3-auth/file-manifest.json) are at
`/tmp/agents/irl-shield/m3-auth`. Runtime guard only: `WORKTREE_t3-5c0ce3ee/.tmp/m3-auth/network.py`.

Each owned test process exited; the final Python exit code was 0. aiohttp runners and
ClientSession objects use async cleanup; task-based fixtures cancel and await their tasks
or release their server handlers in finally blocks. The final warnings-as-errors run
reports no ResourceWarning. No server, timer, or background command was handed off.
[Process inventory](/tmp/agents/irl-shield/m3-auth/processes.json) contains only the existing harness processes
and the receipt shell after the test exit; those were left untouched. No process
arguments or environments were read for the inventory.

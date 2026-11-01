# PR2 round 1: validation error classification

Implementation child for the auth portion of
`claude:r1:transient-validation-failure-latches-revoked`.
Base: `bb6948b9793e1bbb505e84e8042357818ddb9608`.
Checkout: `WORKTREE_t3-6b46f095`.
Branch: `t3/fix-twitch-invalid-token-classification`.
The checkout started clean and remains uncommitted for the parent to audit and copy.

`shield.twitch.auth.InvalidToken` is a public `TwitchError` subclass. Its only
raise site is the HTTP 401 result from `GET /oauth2/validate` inside
`UserSession.access_token()`. It preserves the fixed local message
`authorization validation failed`. HTTP 503 and mismatched identity claims
remain plain `TwitchError`; a dropped HTTP connection remains the sanitized
`Twitch HTTP request failed` error. Validation must succeed before an access
token reaches the key provider. The refresh lock, single-use refresh rotation
in RAM, and exact three approved scopes are unchanged.

The regression extends the existing local HTTP integration fixture in
`tests/m3/test_http.py`. It calls `HelixKeyProvider.get_key()` with a real
public `UserSession`, exercising `access_token()` before any Helix request.
Its four rows are a JSON HTTP 401, JSON HTTP 503, an actual loopback server
connection close, and HTTP 200 with a different user ID. Each asserts the
exact exception class, safe local error text, and that the only wire
requests were validation requests. The existing socket guard permits only
IPv4 loopback. All credentials, claims, and bodies are synthetic. No test-only
production hooks or new dependencies were introduced.

The pre-fix run used exception class names so the missing export could not
mask the behavioral failure. The production auth file was unchanged from
the base during that run. After implementation, the regression imports
`InvalidToken` and compares actual exception classes.

```text
RED: 1 test method, 4 table rows; exit 1
FAIL ... (response='unauthorized')
AssertionError: 'TwitchError' != 'InvalidToken'
Ran 1 test in 0.019s
FAILED (failures=1)

GREEN: test_auth + test_http; exit 0
Ran 20 tests in 0.217s
OK
```

Two test invocations were used out of the four allowed. The green run includes
the existing concurrent refresh rotation, exact device-flow scopes, hourly
validation, malformed claims, key redaction, HTTP guards, and mocked keyring
tests. It has no skips. The personal keyring was never accessed.

Raw receipts are in `/tmp/agents/irl-shield/m3-r1-CHILD/`:

- `red.command.sh` and `green.command.sh`: exact executable commands.
- `red.log`, `red.exit`, `green.log`, `green.exit`: complete output and status.
- `auth.pre-fix.py`, `test_http.red.py`, `red.diff`: pre-fix implementation
  and the regression used for RED.
- `baseline.sha256`, `baseline.status`, `pre-red-hashes.log`: initial hashes
  and status. The auth hash passes before RED; the test hash differs because
  that file already contains the new regression.
- `process-exit.log`: both owned systemd scopes are inactive/dead after the
  synchronous runs, with no surviving tasks.
- `final.sha256`, `final.diff`, `final.status`: final copy/audit receipts.

Both commands use the parent's read-only Python runtime
`WORKTREE_t3-3bb00dac/.tmp/m3/py311/bin/python`,
with this child's checkout as cwd and its root plus `tests/m3` on `PYTHONPATH`.
Bytecode writes are disabled. The execution prefix is:

```sh
XDG_RUNTIME_DIR="/run/user/$(id -u)" \
DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus" \
systemd-run --user --scope --slice=app-t3code-agents.slice \
  --unit=<receipt-specific-unit> -p MemoryMax=2G -p CPUQuota=200% \
  nice -n10 env PYTHONPATH=<child-root>:<child-root>/tests/m3 \
  PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 \
  MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2 <parent-python> \
  -B -W error::ResourceWarning -m unittest -v <tests>
```

No Java was run. No live Twitch calls, login, secrets, configuration dumps,
Mac or GPU work occurred. No processes remain from this child. No staging,
commit, push, PR, or shell worktree creation was performed. Only `auth.py`,
`tests/m3/test_http.py`, and this report were edited in the checkout.

The parent owns transport integration: catch `InvalidToken` for definitive
validation 401 revocation and closure; keep other failures held, retryable,
and eligible for normal reconciliation. This child does not establish that
the full transport finding is fixed. The parent also owns transport RED/GREEN,
the full repository gate, bench decisions, review, and merge. This regression
covers initial validation with normal JSON status responses; live Twitch,
transport retries/revocation, and malformed-body HTTP 401 responses were not
verified here.

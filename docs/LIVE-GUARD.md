# Attended live publication guard

This slice implements CLI selection and session-local live authorization.
Runtime, destination selection and verified TLS forwarding are integrated;
the runtime accepts `twitch_live` and `live_approval` and consumes the approval
before opening a live route. No real Twitch authentication or publication was performed
while developing this slice.

## Publication selection

For `run` and `login --run`:

| Selection | Behavior |
| --- | --- |
| Neither publication flag | Local protected output plus authenticated controls; a stored credential or stream key never enables publication automatically |
| `--twitch-bandwidth-test` | Explicit Twitch bandwidth-test publication; remains the default Twitch publication mode |
| `--twitch-live` | Live publication requires fresh configured broadcaster identity validation and an attended terminal confirmation |
| Both publication flags | Parser error before authentication |

Both flags are available on `login`; without `--run`, login ends without
starting media or acquiring a stream key. `--twitch-live` cannot be combined
with `--mock-origin`, `--local-only`, or `--local-sink`. The synthetic mock
control route continues to use no Twitch publication flag.

Configure `TWITCH_BROADCASTER_LOGIN` alongside `TWITCH_BROADCASTER_ID` and
`TWITCH_CLIENT_ID` through Infisical. Live mode requires a nonempty lowercase
login consisting of ASCII letters, digits or underscores; its exact
confirmation must fit the unchanged 64-byte readline. There is no default login.
Non-live modes do not require this variable.

Owner queue decision 50 still permits the owner's own live sessions only on
the test channel `naie`, during an owner-started, attended session. The owner
keeps `naie` configured and types the unchanged `LIVE naie` confirmation. Other
installers configure their own broadcaster login and matching ID; this does not
authorize an agent to publish or relax attended approval.

## Authorization interface and source

`shield.app.live.authorize_live(session, http)` uses the existing
`UserSession.access_token()` interface after checking login configuration, then
always makes its own fresh `GET /oauth2/validate` request with the access token.
It does not trust the
session's hourly validation cache. The response must have:

- HTTP status 200 and a JSON object;
- a nonempty matching client ID and matching numeric broadcaster ID;
- exactly the existing approved scopes;
- positive finite token lifetime;
- the exact configured `TWITCH_BROADCASTER_LOGIN` (mismatches, case variants
  and a missing response login fail).

After validation, separate read and write handles open `/dev/tty` and both
must report an attended terminal. Separate handles support nonseekable
terminals; buffered `r+` mode does not. The attendee must enter exactly
`LIVE <login>` followed by Enter, using the validated configured login.
For the owner's setup this remains exactly `LIVE naie`. EOF, incomplete input,
whitespace or case differences, missing terminal and terminal I/O errors all deny approval.
Validation must still be unexpired when confirmation finishes. Device-code polling has completed, and EventSub, media and their watchdogs
have not started when the prompt blocks the startup event loop. The prompt
reads synchronously before media startup, with no stdin/environment/file
fallback or persistent confirmation.

Successful authorization returns a RAM-only `LiveApproval`. Its public
constructor refuses issuance, copying/serialization are refused, and
`consume()` succeeds exactly once, including across concurrent consumers.
Reuse throws the same local `LiveModeError` as all other live guard failures.
It names only a syntactically valid configured login, or "broadcaster" when
configuration is absent or invalid; the `naie` setup retains its exact prior
error text. Remote bodies, exception messages and credentials cannot enter
that error. The CLI presents this local reason and retains its existing
generic redaction for unrelated upstream failures.

The response contract and scopes come from `shield/twitch/auth.py`;
fixed-origin HTTP, redirect refusal and bounded responses come from
`shield/twitch/http.py`. No new OAuth scopes, Helix endpoints, dependencies,
models, fixtures from external datasets, or license obligations are introduced.

## Runtime integration

The CLI authorizes live mode before `TwitchControls.prepare()` obtains the
stream key, before MediaMTX starts and before engine creation. It calls the
runtime with:

```python
publish_twitch=(args.twitch_bandwidth_test or args.twitch_live)
twitch_live=args.twitch_live
live_approval=approval  # None for every non-live route
```

The runtime interface adds `twitch_live=False, live_approval=None`.
Before opening any live egress, it requires an actual `LiveApproval` and
consumes it once at startup. Writer reconnects do not consume it again.
A real `run()` regression refuses missing, wrong-type or already-consumed
approvals before any forwarder/output opens; removing runtime consumption
makes that regression fail. [LIVE-EGRESS.md](LIVE-EGRESS.md) records the
integrated route, proof and full-gate scope.

## Functional verification

`tests/integration/test_live_mode.py` owns authorization and CLI wiring;
existing `test_app.py` continues to own login/key/control integration.
The new tests use real `UserSession`, `DeviceAuth`, `TwitchHTTP` and
loopback aiohttp responses. The terminal seam supplies synthetic input,
including one actual OS PTY redirected from `/dev/tty`. CLI wiring tests
route HTTP to loopback and replace only the native media/engine/runtime
execution and OS credential/terminal seams. They do not mock the live
authorization function. One isolated CLI error-rendering test injects a
local error at `execute` to check safe diagnostics.

Tests and their realistic failure modes:

- Parser/validation: both flags accepted individually, simultaneous flags
  refused before execution, and synthetic/local combinations refused.
- Authorization: cached session cannot bypass fresh identity, scopes,
  expiry or HTTP failure; exact attended input is required; expiry during
  confirmation denies; approval cannot be issued directly, copied or reused.
- CLI: default and mock routes do not publish; bandwidth mode stays
  distinct; live authorization precedes key/media; wrong login never gets
  a stream key or starts media; safe local reasons remain visible.

These are new privacy/auth contracts not exercised by the prior app tests.
They use production interfaces and add no test-only production flags or
reset hooks. They do not qualify real Twitch, native media, GPU/detectors,
TLS, runtime approval enforcement, or independent privacy/bench scores.

To reproduce the short functional selection from the checkout, using the
assigned read-only Python 3.11 SDK without package installation or
cross-checkout source overlays:

```sh
scripts/host-lock shared env \
  XDG_RUNTIME_DIR="/run/user/$(id -u)" \
  DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus" \
  systemd-run --user --scope --quiet --slice=app-t3code-agents.slice \
  nice -n 10 env PYTHONDONTWRITEBYTECODE=1 \
  OMP_NUM_THREADS=2 OMP_THREAD_LIMIT=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  NUMEXPR_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2 OPENCV_FOR_THREADS_NUM=1 \
  WORKTREE_t3-7cba93a7/.tmp/integration/venv/bin/python \
  -W error::ResourceWarning - <<'PY'
import sys
import unittest
sys.path[:0] = ['.', 'tests/m3', 'tests/integration']
import cv2
from network import local_network
cv2.setNumThreads(1)
suite = unittest.defaultTestLoader.loadTestsFromNames(['test_live_mode', 'test_app'])
assert suite.countTestCases() == 15
with local_network():
    result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
PY
```

The final run passed 15 tests. The initial parser, authorization and CLI
wiring red logs show missing behavior. A subsequent OS PTY red/green cycle
caught and fixed nonseekable terminal handling. A deliberate mutation
allowing `nale` failed the identity test with `LiveModeError not raised`;
the source was restored byte for byte before the final passing run.

The hand-back directory `out/live-guard/` contains `changes.patch`,
`post-apply-sha256.json`, `handback.json`, the invocation ledger,
red/green logs and mutation evidence. The patch includes all new source,
test and documentation files and is checked against the exact base
`aa2b79e247e1f4ab3179c4f24663c4c05e40db2a`. Nothing was staged, committed,
pushed or published. The conductor runs the full Linux gate after applying
and integrating the runtime changes.

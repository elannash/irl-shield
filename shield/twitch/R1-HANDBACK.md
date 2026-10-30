# PR #2 R1 implementation hand-back

Historical R1 receipt, committed by the conductor as `ea004ec`.
[R2-HANDBACK.md](R2-HANDBACK.md) supersedes its timestamp-ordering and model
release-obligation claims after round 2 review.

**Ready for conductor round 2:** all nine accepted findings have regression
receipts. The final combined functional gate exited 0: **147 tests ran, 146
passed, one macOS-only test skipped**, including **48/48 M3 tests**. Direct TLC
found two real pre-fix counterexamples; the fixed finite model passed six
invariants over **399,992 distinct states**. **23/30 invocations used**: parent
10, auth child 2, policy child 6, model child 5. Seven remain unused.

## Checkout and authority

Actual/requested branch: `elannash/m3-twitch` / `elannash/m3-twitch`.
HEAD and review base: `bb6948b9793e1bbb505e84e8042357818ddb9608`.
Assigned worktree: `/home/elan/.t3/worktrees/irl-shield/t3-3bb00dac`.
First/resume commands verified path, branch, HEAD and status. Original uncommitted
work was preserved. No stage, commit, push, PR mutation or merge was performed.
The conductor owns committing and round 2 of
[PR #2](https://github.com/elannash/irl-shield/pull/2).

Writes remain in `shield/twitch/`, `tests/m3/`, `docs/model/`, ignored `.tmp/`
and owned OS scratch. Common engine/control/transport, root requirements and
root README are unchanged. The underlying `Control`/`engine.hold` seam is unchanged.

## Red/green evidence, one row per accepted finding

Parent receipt root `P` is `/tmp/agents/irl-shield/m3-r1/`.
Auth/policy child receipt root `C` is `/tmp/agents/irl-shield/m3-r1-CHILD/`.
Model receipts `M` are committed-path candidates under `docs/model/evidence/r1/`.
All red receipts remain available; a filename containing `green` does not imply
that intermediate run passed.

| Finding | RED before the relevant fix | GREEN after the fix |
| --- | --- | --- |
| `connect-timeout-kills-upstream-tasks` | `P/01-transport-red.log`: a real >20-second dial timeout killed the upstream watchdog task; liveness assertion failed and its `TimeoutError` is in the log. | `P/06-transport-full-green.log` and final gate: two actual 21-second handshake stalls, one close-triggered and one keepalive-triggered. Reader/watchdog survive; recovery completes and real notification delivery still holds/resumes. Connection errors stay inside capped retry/backoff. |
| `stale-subscriptions-release-hold` | `P/01-transport-red.log`: failed resubscribe left output LIVE instead of HOLD. | Focused run 05, full transport run 06 and final gate verify enabled responses for all three topics, distinct IDs and current session ID. Failed, partial, disabled and foreign-session subscriptions stay HOLD. Retry creates only missing topics; planned handover explicitly carries subscriptions under Twitch's contract. |
| `fault-overwritten-by-stale-welcome` | `C/01-red.log` reproduces both fault/welcome orderings on the old API. `M/stale-welcome.tlc.log` reaches LIVE with a dead socket and no enabled subscriptions; `M/public-replay.log` reproduces this on unmodified base code. | `C/06-final-green.log`, fixed public replay and final gate reject stale welcome/query completions. Required generation/session arguments and unique query-token identity fence the release. |
| `clock-skew-drops-holds` | `C/01-red.log`: authorized chat/Shield holds at +0.2 s and +10 s were rejected. `M/dropped-hold.tlc.log` independently finds a discarded Shield begin when Twitch time is 11 and local time is 10. | Final policy 16-test suite, fixed replay and final gate admit protective events regardless of timestamp alone. Protective ordering clamps at receipt; releases retain strict freshness/order checks with a documented local 30-second forward allowance. |
| `reconciled-unsynchronized-cross-thread` | `C/01-red.log`: real two-thread status/fault overlap fails. `C/03-release-red.log`: reentrant fault during connection release exposed transient LIVE. `C/05-status-red.log`: reentrant Shield begin was overwritten by older inactive status. | Final policy tests and final gate pass. Socket mutations marshal to the owner loop; all public policy calls/read properties use RLock. Rechecks after callbacks and a separate `twitch-reconcile` hold prevent both transient exposure and Shield overwrite. Both release callback positions are exercised with fault/revocation. |
| `holds-dropped-outside-ready-phases` | `C/01-red.log`: subscribing/connecting/disconnected/revoked holds were discarded. Public old/fixed replay also reproduces subscribing chat loss. Additional `P/08-close-and-origin-red.log` exposes loss of an in-flight old-socket hold when recovery resets routing. | Final policy accepts authorized hold/Shield begin in every phase and stale generation. `P/09-close-and-origin-green.log` plus final gate preserve old-read subscription provenance across reset; reconciliation never clears chat/local holds. Releases remain current live READY only. |
| `transient-validation-failure-latches-revoked` | `P/01-transport-red.log`: 503 latched revoked. Auth `C/red.log`: 401 lacked a definitive exception class. `P/04-unreadable401-red.log`: non-JSON 401 was misclassified as transient. | Auth child 20-test pass, parent focused 16-test pass and final gate: only validation HTTP 401 raises `InvalidToken`; unreadable bodies do not change that classification. 503/network/claim failures remain temporary HOLD, retry and recover through normal reconciliation. Definitive idle 401 stays held and closes transport. |
| `model-invariants-hold-by-construction` | Separate pre-fix spec, no mutation flags: direct TLC exits 12 for `NoLIVEWithoutCurrentChannel` and `AuthorizedShieldBeginPersists`, each with an eight-transition path ending at state 9. Actual base Python replay exhibits both unsafe outcomes. | Fixed model exhausts 5,618,817 generated / 399,992 distinct / 0 queued states, depth 39, six invariants. Replay holds on frozen production policy. Independent socket/subscription truth and delivered protective obligations make these checks capable of failing. Report explicitly bounds its claims. |
| `transport-mock-masks-resubscribe-and-timeouts` | Enhanced mock issues unique subscription IDs, fails POSTs and stalls handshakes; it exposed the genuine failures in parent run 01 against unchanged production. | Twelve transport tests pass in the final gate, using pyTwitchAPI sockets, local HTTP/WebSocket fakes and the actual hash-pinned Twitch CLI. The fake can fail a selected topic, return disabled/foreign-session records and delay connects. CLI limitations/facade scope are documented in `PROTOCOL.md`; no live endpoint was used. |

## Implementation and integration

Production changes are `auth.py` (definitive invalid-token classification),
`http.py` (preserve validation 401 before decoding), `events.py` (serialized,
generation/session/token-fenced policy) and `transport.py` (owner-loop dispatch,
verified subscription readiness, safe retry and shutdown). Tests are in
`tests/m3/test_{events,http,transport}.py`; no production test-only reset/export
was added. Private pyTwitchAPI hooks are pinned to 4.5.0 and their removal
condition is recorded in the transport module docstring.

Two additional defects found during this round are fixed with red/green proof.
Run 07's first combined gate found that socket cleanup could cancel its own
unfinished close future. Run 08 reproduced this deterministically and also
exposed an old-socket protective event losing its verified subscription registry.
Run 09 passed both regressions plus the idle-validation cleanup case. Final run
10 includes them. `_closing` now becomes true after actual socket/session close;
the bounded provenance map retains a captured per-socket registry for in-flight
reads. No other session's process was stopped.

Root's launch/key-provider recipe remains in [PROTOCOL.md](PROTOCOL.md). No new
scope or external seam change is needed. Direct policy callers must migrate to
the required generation/session API in [R1-POLICY.md](R1-POLICY.md); there are no
compatibility defaults. Root uses the same engine's named hold seam. A chat
resume clears chat only; reconciliation's internal releases cannot clear chat,
local or an active Shield Mode source. Missing coverage still prevents LIVE.

Exactly the approved scopes remain: `user:read:chat`,
`moderator:read:shield_mode`, `channel:read:stream_key`. Official citations and
access dates, including Get Shield Mode Status, are in `PROTOCOL.md`. No live
login, Twitch HTTP/WebSocket connection, stream key, ingest, publishing,
personal keyring write, Mac, GPU or OCR measurement occurred. Python network
guards allow loopback only in tests. The real CLI runs with synthetic scratch
config and is stopped by the test. No secret values were read or recorded.

## Full invocation ledger and commands

Every suite/TLC ran in `app-t3code-agents.slice`, with `MemoryMax=2G`,
`CPUQuota=200%`, niceness 10. Native Python libraries were capped at two threads;
TLC used one worker, `-Xmx1g -XX:ActiveProcessorCount=2`. No benchmark/performance
lease or GPU work was needed. Static source/hash/diff inspection is not counted
as a test invocation.

| Parent invocation | Receipt basename under P | Result |
| --- | --- | --- |
| 1 | `01-transport-red.log` | 8 tests; 3 failures + 1 error. Genuine liveness/stale-subscription/transient-validation red assertions; planned fake lacked carried IDs. |
| 2 | `02-transport-green.log` | 8 tests; 2 errors. Initial integration exposed planned fixture and old-close/new-generation recovery issues; timeout survival already passed. |
| 3 | `03-transport-focused.log` | 2 tests pass: planned handover/dedup/revocation and transient validation recovery. |
| 4 | `04-unreadable401-red.log` | 1 test fails on malformed-body validation 401. |
| 5 | `05-focused-green.log` | 16 tests pass: HTTP suite, failed/partial resubscription and transient recovery. |
| 6 | `06-transport-full-green.log` | 10 tests pass in 51.496 s, including real timeout boundaries and actual CLI. |
| 7 | `07-combined-gate.log` | 145 tests; 1 cleanup error and 1 expected macOS skip. Not a passing gate. |
| 8 | `08-close-and-origin-red.log` | 2 regressions fail, with 1 cleanup error. |
| 9 | `09-close-and-origin-green.log` | 3 tests pass, including idle-validation shutdown. |
| 10 | `10-combined-gate-final.log` | Exit 0, 147 tests in 75.852 s, 1 expected macOS skip. |

The actual final gate command, run from the assigned worktree, was:

```sh
XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus \
systemd-run --user --scope --unit=m3-r1-combined-gate-final \
  --slice=app-t3code-agents.slice -p MemoryMax=2G -p CPUQuota=200% \
  env OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2 \
  PYTHONPYCACHEPREFIX="$PWD/.tmp/m3-r1/pycache" nice -n 10 \
  .tmp/m3/py311/bin/python -W error::ResourceWarning tests/m3/run_gate.py \
  > /tmp/agents/irl-shield/m3-r1/10-combined-gate-final.log 2>&1
```

All ten historical parent command-execution items were copied from this lane's
T3 activity into `P/parent-command-transcript.txt`, retaining the shell-rendered
quoting and output. It is a receipt, not a runner. Raw logs retain the systemd
unit/invocation IDs and test selections. Auth's exact two
commands are `C/{red,green}.command.sh`; policy's exact six are
`C/run-01-red.sh` through `C/run-06-final-green.sh`. The model's exact five are
in `docs/model/evidence/r1/commands.sh` with resource-limited runner scripts.
Auth and policy used the same scratch directory name; use the distinct named
logs/scripts and each file's final hash, not a shared generic `final.diff`.

Children: auth 2 invocations (one RED, one 20-test GREEN); policy 6 invocations
(RED/GREEN, callback-release RED/GREEN, status-reentry RED/final 16-test GREEN);
model 5 (two real pre-fix failures, one rejected negative-literal config, fixed
pass, combined public replay). The rejected config is included in the 23 total.
The complete final gate ran in the parent; child passes do not substitute for it.

## Model receipts and limits

[REPORT.md](../../docs/model/REPORT.md) maps the model to frozen policy SHA-256
`907a17f84498b08c9c99ba882d85c3f08db8d173517a3a73ba38e16e8c384bdd`.
The two pre-fix raw traces, fixed pass and executable public replay are in
`docs/model/evidence/r1/`. The parent read the models, replay harness, raw
failure states, pass output and cleanup receipts, verified the child's checksum
manifest, then copied only its owned model paths. Parent additions to the
report record reused tool licenses; no checked TLA/config bytes changed.

The model bounds generations to three, query identities to two and protective
deliveries to one per source; local time is fixed, with distinct remote clock
inputs. It models observed faults, queued welcome, independently enabled topics,
status completion and callback release microsteps. It does not prove the full
WebSocket/watchdog, elapsed time to detect a silent loss, payload authorization,
replay-cache eviction, progress/fairness, actual Twitch service or media privacy.
Three invariants use independent environment/obligation facts; three are
structural Control checks. Historical by-construction model results are labeled
historical and do not support the current gate claim.

## Tools, manifests, processes and unfinished work

No dependency, tool, model or dataset was introduced or installed in R1. Existing
`twitchAPI==4.5.0` (MIT), optional `keyring==25.6.0` (MIT), Twitch CLI 1.1.24
(Apache-2.0), TLC distribution 1.7.4 (MIT) and Temurin 25 (GPL v2 with Classpath
Exception) were reused. [LICENSES.md](LICENSES.md) and
[DEPENDENCIES.json](DEPENDENCIES.json) retain transitive license records.
The CLI binary SHA-256 is
`40958ae7aed8a58f58bd9f32dec98cdd326741e5f9c1c6e6da9f7ae1df599240`;
TLC JAR is `936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88`.
`shield/twitch/SHA256SUMS` and `docs/model/SHA256SUMS` identify final owned files;
parent scratch retains `final.diff`, `git-status.txt`, `process-exit.txt` and
`raw-receipts.sha256`. No model weights, dataset, fixture or demo asset changed.

All parent and child test scopes exited; see `P/process-exit.txt`,
`C/process-exit.log`, `C/process-exit.txt` and model
`evidence/r1/process-cleanup.txt`. No process, listener or queued survivor is
retained, so there is no PID/port/stop command to hand off. Final git diff/check
and tracked-file checks are recorded in parent scratch; new R1 files remain
untracked intentionally. All changes are unstaged and uncommitted.

Unfinished: conductor artifact audit, commit and PR #2 round 2 review. Live
authorization/ingest/platform acceptance remain outside tonight's authority.
The macOS-only VideoToolbox test was skipped on Linux; no portability pass is
claimed from that skip. There is no new OCR/bench scorecard because this round
changes the offline Twitch control path, not detection/masking/media output.

Verdict: **nine findings addressed; 146 passed / 1 expected skip; 399,992 fixed
model states; 23/30 invocations; zero owned process survivors; round 2 pending.**

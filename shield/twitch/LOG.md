# M3 implementation ledger

This lane started 2026-10-29 PT in the assigned dedicated worktree
`/home/elan/.t3/worktrees/irl-shield/t3-3bb00dac`. First command was exactly
`pwd`, `git branch --show-current`, `git rev-parse HEAD`, `git status --short`.
It returned isolated path, branch `t3/m3-twitch`, clean status, and HEAD
`ec1d1f96a1c29ab82109c66f27064f3fd6cb326d`. Branch renamed in place with
`git branch -m elannash/m3-twitch`. No worktree was created in the shell.

No staging, commits, pushes, PRs, merges, Mac/media/GPU jobs, live login,
Twitch API/EventSub calls, personal keyring access, secrets reads or external
publishing. Public docs, GitHub tools/source and PyPI dependencies were fetched.
All runtime HTTP/event fixtures and credentials were synthetic. Ordinary Python
imports created ignored bytecode caches; lasting deliverables are confined to
`shield/twitch/`, `tests/m3/`, `docs/model/`. Scratch lives in `.tmp/m3/`,
`.tmp/tools/`, and `/tmp/agents/irl-shield/m3-twitch/`.

## Design and authorization

Loaded codebase-design, tdd, test-review gate, research, full statechart,
diagnosing-bugs source/hypothesis checks, routing Roles/Packets/Conducting/Tool
access, and machine Shell traps. Receipt-audit loaded before child acceptance.
One existing Control/engine.hold seam is used without common code edits.
Tests observe public auth, transport, event-control and key-provider interfaces;
network/time/keyring fixtures sit at external seams. The tests protect authority,
privacy, replay and lifecycle behavior; pixel/design assertions are absent.

Owner/conductor later authorized Ultra/priority worktree children. Auth owns
four auth/key modules and two tests; model children own only docs/model. Parent
owns integration, transport, event policy, final checks and this hand-back.
Auth source and all receipt hashes were read/verified before explicit per-file
copy. A local hook misclassified a bulk Python copy using shutil as worktree
removal and blocked it; explicit cp of the same seven named files succeeded.
No removal was attempted. The original timebox and 48-invocation budget were
not reset by the setting interruption or delegation.

## Test invocation ledger

Parent commands used `<python> -m unittest discover -s tests/m3 ... -v` from
the assigned checkout, with output redirected to the absolute receipt folder.
01–07 used `.tmp/m3/venv/bin/python` (3.14); 08 onward used
`.tmp/m3/py311/bin/python` (3.11.14). 01–12 commands appended `cat`, so a shell
exit of zero did not mean the test passed; verdicts below come from read logs.
Later commands preserve Python's exit. 13 onward explicitly use nice 10.
Full exact commands for children are in their own delivered ledgers.

| Parent invocation | Receipt under `/tmp/agents/irl-shield/m3-twitch/` | Actual result |
| --- | --- | --- |
| 01, auth import red | `01-auth-red.log` | Missing package, one import error; scaffolding receipt only. |
| 02, auth slice | `02-auth-green.log` | 1 method passed; interval/slow_down. |
| 03, event import red | `03-events-red.log` | Missing module, one import error; scaffolding receipt only. |
| 04, combined slices | `04-events-green.log` | 3 methods, 1 failure; tied Shield timestamps correctly retained HOLD, fixture corrected. Filename is historical, not a green claim. |
| 05, replay slice | `05-replay-red.log` | 4 methods, 1 failure; older resume incorrectly cleared newer hold. |
| 06, combined slices | `06-replay-green.log` | 6 methods, 1 failure; newly conservative tied chat timestamp rejected fixture resume. Fixture made newer. |
| 07, auth/events/Helix | `07-http-green.log` | 9 methods passed. |
| 08, real localhost socket | `08-transport.log` | 1 method error; reconnect race. |
| 09, same with phase receipt | `09-reconnect-probe.log` | 1 failure; two sockets existed but phase remained reconnecting. |
| 10, reconnect correction | `10-reconnect-green.log` | 1 method passed. |
| 11, actual CLI + localhost | `11-cli.log` | 2 methods, CLI startup error; pinned CLI rejects chat subscriptions. |
| 12, first TLC helper | `12-tlc.log` | Stopped before verdict; no pass. Nice 10 but not in required cgroup; stopped owned launcher after matching its exact command. All later heavy checks use the slice. |
| 13, idle red + CLI facade | `13-idle-red-cli.log` | 3 methods, 2 errors; no idle timer and mock GET missing client header. |
| 14, timer + CLI | `14-idle-cli.log` | 3 methods, 2 errors; competing shutdown and undrained CLI pipe. Timed-out CLI helper exited when owned server closed. |
| 15, cleanup + drain | `15-cli-probe.log` | 3 methods passed with ResourceWarning promoted to error; actual CLI events/reconnect, idle failure shutdown and chat transport. |
| 16, authority production mutation | `16-role-mutant.log` | Expected failure: moderator `!shield resume` executed. Source restored byte for byte. |
| 17, replay production mutation | `17-replay-mutant.log` | Expected failure: replayed hold executed after clearing cache/floor. Source restored byte for byte. |
| 18, reconciliation red attempt | `18-reconcile-red.log` | Test insertion indentation error; no behavior exercised, counted against budget. Corrected immediately. |
| 19, reconciliation red | `19-reconcile-red.log` | 5 methods, 2 failures + 1 timeout; proves missing status query/recovery. |
| 20, reconciliation implementation | `20-reconcile-green.log` | 28 methods, 27 passed; synthetic status endpoint incorrectly retained active=true after its end event. Fixture updated to false; awaits final gate. |
| 21, reconciliation production mutation | `21-reconcile-mutant.log`, `21-mutation-receipt.json` | Expected two failures: local hold cleared to LIVE and exact TLC active-status path reached PROTECT. Restored byte-for-byte before gate. |
| 22, full portable functional gate | `22-full-functional-gate.log` | Exit 0; 129 discovered, 128 passed, 1 skipped (VideoToolbox requires macOS); 30/30 M3 passed. All portable source parsed. |

The CLI trigger failure was investigated against pinned official source. Its
Shield events and RPC stay local; draining the server's stdout prevents pipe
backpressure. Final actual CLI evidence is `cli-server.log`, containing only
synthetic public IDs and loopback addresses. No production values occur in it.

Auth child used 12 invocations; its final 19-method suite passed. See
[AUTH-HANDBACK.md](AUTH-HANDBACK.md), raw receipts `/tmp/agents/irl-shield/m3-auth/`.
The first model child used 11 invocations (9 TLC and 2 replay harness), not 6:
the statechart helper continued after deliberate invariant failures. Its old
baseline passed 5,312 distinct states, but those receipts predate reconciliation
and are historical only. They remain in the model delivery as evidence.

At parent invocation 20 the total was **43/48**. Three TLC invocations are
reserved for the reconciliation model, one for production clobber mutation,
and one combined full functional gate. The full Python gate combines the repo's
tests, M2 tests and M3 tests in one process, asserts discovery is nonempty,
installs the nonlocal socket guard, and parses Python source. It does not claim
the Linux host can compile Apple Vision; root must run the Mac Swift gate.

Final count: parent 22 + auth child 12 + historical model child 11 + current
reconciliation model child 3 = **48/48**. No further tests were run. The current
model passes eight invariants over 50,920 distinct states (1,139,021 generated),
zero queued, depth 18, on baseline and restored configs. Direct clobber TLC failed
ReconcileReleaseIsolated on two transitions. The final Python gate replayed those
same public calls and retained HOLD; the production mutant failed them first.

Exact final parent commands (from this checkout):

```sh
nice -n 10 .tmp/m3/py311/bin/python .tmp/m3/reconcile_mutation.py
XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus \
  systemd-run --user --scope --unit=irl-shield-m3-final-gate \
  --slice=app-t3code-agents.slice -p CPUQuota=200% \
  env OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  PYTHONPYCACHEPREFIX="$PWD/.tmp/m3/pycache" nice -n 10 \
  .tmp/m3/py311/bin/python -W error::ResourceWarning tests/m3/run_gate.py
```

The mutation helper's applied/restored hashes are in its JSON receipt. The scope
reported LoadState=not-found, ActiveState=inactive, SubState=dead after exit. The
final process inventory found only preexisting harness processes and the receipt
shell/Python itself in this cwd, not a retained test server or worker. Child cleanup
receipts are preserved with their reports. No process is handed off.

## Scope changes and remaining verification

Conductor explicitly moved startup/outage Shield Mode reconciliation into M3.
It uses the approved read scope and existing hold seam. Reconciliation retries
under HOLD, planned handover adds no hold, and snapshots cannot clear newer
events or another source. Missed outage chat has no replay interface; video is
already held during that period. Exact protocol sources and limits are in
[PROTOCOL.md](PROTOCOL.md). No extra OAuth scope was added.

Final status, commands, source hashes, combined gate and model receipts are
recorded in M3-HANDBACK.md when available. OCR/bench scores are not claimed:
M3 changes no detector, rendering, engine scheduling, scorer, common cache or
media egress. Corrected independent OCR grading remains root's responsibility.

## PR #2 review round 1

Conductor committed the milestone as `bb6948b9793e1bbb505e84e8042357818ddb9608`
on `elannash/m3-twitch`, then assigned nine accepted blockers from
`/tmp/claude-1000/agents/twitchcon-hackathon/conductor/pr2-triage-r1.json`.
This round uses the same dedicated worktree and leaves changes unstaged and
uncommitted. New budget: 30 test/TLC invocations; deadline Fri Oct 30 03:00 PT.

Disjoint Ultra children supplied auth classification, policy generation/hold
safety and a nonvacuous model. Parent read the changed code, regression receipts,
raw model failures/pass/replay and manifests before integration. Auth used two
invocations, policy six, model five. Parent used ten, for **23/30 total**.
One model config parse rejection is included. Parent's first full gate failed
with an idle-validation cleanup cancellation; focused red regressions exposed
that shutdown race and an in-flight old-socket hold losing its routing registry.
Both were fixed before the final gate. Intermediate failures remain in the
ledger and are not represented as passing runs.

Final combined gate command and all nine red/green rows are recorded in
[R1-HANDBACK.md](R1-HANDBACK.md). Raw parent receipts:
`/tmp/agents/irl-shield/m3-r1/01-transport-red.log` through
`10-combined-gate-final.log`. Final result: **147 tests ran in 75.852 seconds,
146 passed, one macOS-only VideoToolbox skip; 48/48 M3 passed**, exit 0.
Runs were constrained to 2 GB, 200% CPU, niceness 10 and native workers two.
No common engine/control/bench/root requirements/README edit, new dependency,
new scope, live service request, credentials, keyring, Mac or GPU work occurred.

The replacement model's real pre-fix traces end at state 9 with (a) LIVE after
socket loss and stale reconciliation, and (b) LIVE after discarding an authorized
clock-ahead Shield begin. Actual public Python replay reproduces old RED/fixed
GREEN. Fixed direct TLC exhausts **5,618,817 generated / 399,992 distinct /
0 queued** states, depth 39, six invariants. The report explicitly omits a full
transport/watchdog/progress proof. Historical by-construction evidence remains
labeled historical. Checked policy SHA-256:
`907a17f84498b08c9c99ba882d85c3f08db8d173517a3a73ba38e16e8c384bdd`.
TLC/Java were existing read-only tools with 1 GB heap in the 2 GB scope.

Final artifact hashes and process-exit receipts are in the R1 hand-back and
owned scratch. No process or listener is retained. Conductor audit, commit and
PR #2 round 2 remain pending; no push/merge authority was assumed.

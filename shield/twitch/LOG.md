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

## PR #2 review round 2

Conductor committed R1 as `ea004ecdad9583996d4907cfb0f35ca130a227af` and
assigned three accepted blockers: mixed timestamp domains let a stale release
clear a clock-ahead hold; the model discharged obligations using the policy's
own key; startup revocation left `start()` pending. The same dedicated worktree
and branch were retained. M3 issued no staging, commit, push, PR or merge.

Policy RED on unchanged `ea004ec`: two tests, six assertion/subtest failures.
The prescribed `[started_at, receipt + 30]` clamp passes all 17 policy tests,
including chat/Shield skew 10/29, older/equal release rejection and valid newer
release. Existing unusable timestamp fallback and protective admission remain.
Startup RED reproduced all three terminal routes: validation during subscribe,
validation before reconcile and EventSub revocation while reconcile waits.
All 13 transport tests then passed. The final startup code signals a terminal
outcome, closes transport and raises fixed `TwitchError`, without changing the
meaning of `InvalidToken` or transient-fault retries.

Parent run 05 failed an unchanged root queue timing test; all 50 M3 passed.
Focused run 06 also failed that root test at a different timing assertion,
while startup/auth checks passed. Root confirmed an existing flake, supplied
injected-delay old RED/new GREEN evidence and cherry-picked its test-only
correction as `9c86a70791c4af5e35aab042d6f3f7c2fd114280`. M3 waited for the
explicit pick notice before the final gate. The frozen production/test hashes
were verified unchanged across the pick. Common files were not edited by M3.

One isolated Ultra child updated `docs/model/` only, spending three of five
authorized invocations. The parent audited models, independent obligations,
actual state-17 counterexample, fixed output, public replay, commands, hashes,
licenses and process cleanup before copying. Old direct TLC reached LIVE after
hold raw20/receipt10 and stale release raw19/receipt11, with obligation still
true. Frozen fixed policy passed the six unchanged invariants: **150,289,557
generated / 14,747,184 distinct / 0 queued**, depth44. Actual old/fixed replay
passed, including legitimate newer releases. All bounded assumptions and
omissions are explicit in the report; prior R1 evidence is historical.

Final parent combined gate run 07 on `9c86a70` plus uncommitted M3 fixes:
**149 tests in 76.938s, 148 passed / 1 macOS-only skip, 50/50 M3 passed**, exit0.
This round spent parent7 + model3 =10 invocations; prior23 makes **33/38**,
five unused. The root's separate proof calls are not M3 calls. Exact runners,
all failed/passing logs and cleanup live in `/tmp/agents/irl-shield/m3-r2/`.
Every M3 suite/TLC stayed under the required 2GB scope; TLC heap1GB/workers2.

No new dependency, model weights, dataset, asset, scope, live Twitch, secrets,
personal keyring, Mac or GPU work. All owned scopes/JVMs exited, no survivors.
Final source is frozen; files remain unstaged/uncommitted for conductor audit,
commit and PR #2 round3. [R2-HANDBACK.md](R2-HANDBACK.md) is the current receipt.

## PR #2 review round 3

Conductor committed R2 as `9cb8e812af152833f97adc2ce1cdd4858c5efdf3` and
accepted one P1: the receipt+30 clamp let an older release clear a newer hold.
Same dedicated worktree/branch, no M3 staging/commit/push/PR/merge. The fix
orders finite holds/releases by raw Twitch time; host time is only freshness,
replay accounting and engine hold time. A far-future release stays rejected
with fixed warning `clock-skew`, without payload/identity/credential data.

Parent run01 reproduced the base failure:20 tests/22 assertion+subtest failures.
Run02 found an existing cache-retention assertion failing; receipt accounting
was restored only for the replay cache, with raw ordering separate. Run03
passed20 policy tests. Run04 passed the earlier152-test combined gate, later
superseded. The conductor clarified that an unstamped hold with no history must
fence its first stamped release, and added all-message metadata seeding plus
Helix-active ordering. Run05 reproduced six failures across those contracts.
Run06 passed all55 M3 tests, including four real WebSocket header cases: welcome,
keepalive, reconnect request and candidate handover welcome. Run07 passed154
tests before final source review restored the upstream initial planned-dial
watchdog reset. That run is not the gate for final transport bytes.

An isolated Ultra child used four calls: old config error counted, old raw-order
TLC counterexample at state17, superseded703 candidate TLC pass, superseded703
public replay pass. It returned the final0e90 bootstrap model/replay unexecuted
under its exhausted cap. The parent audited every model, independent obligation,
counterexample, replay, command, license/hash and cleanup receipt before copying
only owned model files. No703 result was claimed for the final revision.

Prior33 + parent7 + child4 exhausted44. The conductor explicitly granted exactly
two final calls, ceiling46, with stop-on-failure. Run08 checked the final model:
**73,263,001 generated /7,380,396 distinct /0queued**, depth43, six unchanged
invariants, exit0,4min59sec. Run09 executed the audited actual old/final replay
and full functional gate in ONE Python process: replay PASS, **154 tests /
153passed /1macOS-only skip**,55/55M3,75.292sec,exit0. Both approved calls passed;
all frozen source, test, TLA/config and replay input hashes matched afterward.
Exact final review usage **46/46**; no further test was run or authorized.

Source freeze: policy0e90e43f52b3bd9444925469baf96b40d29480ecefd22c4eeb5afdd68bb630fd;
transportd991ee39489544eeba61965330761087643beebaa1e5ba91791afb40019d91d8.
No source/test edit followed final freeze. Model header comment alone was
corrected before08; exact checked projection hash8dc2ae824f16cea93e274abdd6f22a717afb45aff167e86b21d0efd753d564f5.
Independent raw evidence has no cap; missing-first anchoring and Helix-active
barriers are explicit. Bounded assumptions/omissions remain in the model report.

No dependency, model weights, dataset, asset, scope, live Twitch, device login,
secret read, personal keyring, Mac, GPU, OCR or performance measurement. All
parent/child scopes and JVMs exited; no process/listener retained. Exact runners,
all receipts and seals live in `/tmp/agents/irl-shield/m3-r3/`; final model raw
receipts are also under `docs/model/evidence/r3/`. Source remains uncommitted
for conductor artifact audit, commit and the last review round.
[R3-HANDBACK.md](R3-HANDBACK.md) is the current hand-back.

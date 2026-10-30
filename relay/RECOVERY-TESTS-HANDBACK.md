# M2 recovery tests: invocation 70 red hand-back

Implemented tests and a test-only fault fixture. The single authorized native
invocation ran against the live parent implementation and produced three
meaningful failures. No production files were changed. No green run, full gate,
soak, bench, quality decode, scorer, OCR, GPU, or model invocation was performed.
Root OCR/Q qualification remains pending.

## Checkout and scope

- CWD: `/home/elan/.t3/worktrees/irl-shield/t3-adf5298f`.
- Branch renamed in place from `t3/adf5298f` to `elannash/m2-recovery-tests`.
- HEAD: `d4a28a99bdda0bc44a685f31cd971babf1263781`, the exact assigned checkpoint.
  Original project base supplied by the packet:
  `ec1d1f96a1c29ab82109c66f27064f3fd6cb326d`.
- First operation verified CWD, branch, HEAD and clean status. This checkout is
  neither `/home/elan/code/irl-shield` nor the parent `t3-ae860af9` checkout.
- Writes: `tests/m2/test_recovery.py`, `tests/m2/recovery_fixture.py`, this
  hand-back, and ignored `.tmp/m2-recovery/` only.
- No stage, commit, push, PR, merge, worktree creation/removal, installation,
  account access, secret lookup, Twitch traffic, parent writes, delegation or
  messages to other agents. New files are intentionally untracked;
  `git ls-files --error-unmatch` confirmed they are not in the index.
- Read local AGENTS, routing Roles/Packets/Conducting/Tool access,
  codebase-design, TDD (including tests/mocking), the standalone test gate,
  diagnosing-bugs Source and hypothesis checks, research Measurements, and the
  parent staged recovery stream/live/runtime interfaces before authoring tests.

## Test gate and public interfaces

1. `test_full_ping_is_valid_then_fragmented_ping_recovers_without_replay`
   protects recovery from the real run-68 fault at public `Egress.write`.
   Existing `test_stream` proves fatal handshake cleanup, not recovery from a
   steady-state network mux stall. Full Ping is the validity control. The
   fragmented condition checks real reconnect, recovery events, ACK accounting,
   monotonically increasing original indices/PTS with honest gaps, no failed
   frame replay, appended generation manifests, and preserved archive bytes.
2. `test_saturated_media_pause_preserves_moderator_hold_across_reconnect`
   protects `RelaySession.tick` batch disposal and its public M3 hold control
   during actual blocked `Egress.write`. Existing `test_live` uses a collecting
   sink and cannot block native output or restart a network writer. Real shared
   MaskingEngine, real DetectorLane/NoOpDetector, renderer and RelaySession are
   used. The fixture's NoOpMotion adapter is only synthetic coverage support.
   Source PTS and `presented_at` use real elapsed/monotonic clocks, independently
   of output ACK count. After recovery, every generation-2 row must be HOLD,
   protected, slate, black, and freshly computed after the moderator hold. A
   final public hold release also checks the temporary egress hold was released.
3. `test_refused_loopback_connection_exhausts_five_reconnects_without_hanging`
   protects public Egress's bounded 5/60 reconnect behavior using a real bound,
   non-listening loopback TCP port. It requires exact terminal code, five
   ordered/reaped generation events, persisted event agreement and no hang.

No production exports, reset hooks, flags, private readiness fields or parser
modules were added or used. The test-only MessageGate comes from the supplied
Codex-family candidate fixture; its sole role is injecting the exact valid
run-68 packet at a server RTMP chunk boundary. The proxy accepts multiple
connections and faults only the first. A replacement connection retires the
old upstream publisher without shortening the first connection's six-second
pause timer. This avoids adding a publisher-collision fault to backpressure.

## Invocation and source identity

One unittest/native invocation, accounting **70**. Start
`2026-10-30T10:20:22Z`, end `2026-10-30T10:20:57Z`; unittest reports
`Ran 3 tests in 35.590s`, `FAILED (failures=3)`, exit **1**, not timeout.

Actual command, executed with CWD
`/home/elan/.t3/worktrees/irl-shield/t3-ae860af9`:

```bash
env PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  TMPDIR=/home/elan/.t3/worktrees/irl-shield/t3-adf5298f/.tmp/m2-recovery/tests-tmp \
  M2_RECOVERY_RECEIPTS=/home/elan/.t3/worktrees/irl-shield/t3-adf5298f/.tmp/m2-recovery/receipts \
  PYTHONPATH=. nice -n 10 timeout --signal=TERM --kill-after=4s 115s \
  /home/elan/code/irl-shield/scripts/host-lock exclusive \
  /home/elan/.t3/worktrees/irl-shield/t3-ae860af9/.tmp/m2/py311/bin/python \
  -m unittest discover \
  -s /home/elan/.t3/worktrees/irl-shield/t3-adf5298f/tests/m2 \
  -p test_recovery.py -v \
  > /home/elan/.t3/worktrees/irl-shield/t3-adf5298f/.tmp/m2-recovery/run70.log 2>&1
```

The Perl canonical host lock was exclusive, without a nested queue lock.
The inherited cgroup is under `app-t3code-agents.slice`; process inspection
confirmed niceness 10 for the runner, MediaMTX and encoding worker. Native work
was sequential, at most one MediaMTX and one libx264 worker, with codec thread
counts already bounded to two. No other session's processes were stopped.

Parent live source SHA-256, identical before and after the run:

```text
relay/stream.py  2616a9057225c77c734949edf55fa623b0c2bfa5c98e7562c6d60a6bc338e482
relay/live.py    c00793f1365d50de378d088d42776bf8334e8df1eae358c945575123f6c3c29b
relay/runtime.py a1836c696faaa11d8a45e0b64e67de67fef9a6ea4054dcfd0e1436a84ec9ce94
```

These are the parent legacy-fatal implementation with diagnostics, not this
worker's checkpoint and not the staged recovery implementation. The staged
`.tmp/m2/recovery/stream.py` read for interface understanding had SHA-256
`09c66da4ed23da5b61e1a1ec4bb753c429c7780a50b9c8c7502d188ad210d254`.

## What the red actually proved

- Full Ping: **90 warmup ACKs, 300 total ACKs**, one network connection,
  complete control delivered, no failure or fixture error.
- Fragmented Ping: **90 warmup ACKs, 93 total ACKs**, the exact csid-2/type-4/
  stream-0/event-6 packet with only its basic-header byte initially delivered.
  Remaining bytes held for six seconds. Failure was exactly
  `EgressError`, `egress-write-timeout`, `operation=network-mux`, active index
  **93**, completed **92**, operation age **5.007520831s**. This matches the
  run-68 mechanism and 300/93 ACK controls. Client-to-server media forwarding
  remained active. The parent run-68 reference is
  `/tmp/agents/irl-shield/m2-relay/68-fragmented-control-red/repro.json`.
- Backpressure: **90 warmup ACKs**, loopback receive buffer **8192 bytes**
  (requested SO_RCVBUF 4096), client-media reads throttled until a real write
  had been in flight **0.251356706s** without an ACK. Only then did the exact
  six-second stop-reading pause begin. Warmup plus saturation took about
  **10.009s**, under 20 seconds. The blocked frame was **LIVE**, index **291**;
  **285** acknowledged baseline rows were LIVE/non-slate. The controller called
  public `session.control.hold(True, source='twitch-chat', reason='moderator')`
  during that blocked write, about **0.000174s** after pause start. The failure
  was exactly `egress-write-timeout`, `network-mux`, active **291**, completed
  **290**, operation age **5.017600206s**. This was actual socket backpressure,
  not an unsaturated six-second buffer test. No controller/proxy error.
- Refused port: real loopback refusal produced legacy `egress-write`,
  `operation=network-startup` in **0.170s**, instead of the required
  `egress-recovery-limit`. It failed at the intended terminal-code assertion,
  not a setup, import, parser, or cleanup error.

The new-connection path, successful recovery, generation-2 hold assertions,
archive preservation, event persistence and actual exhaustion of five retries
remain **unverified until parent green 71**. Legacy code terminated at the first
failure, so it could not exercise those assertions. No green claim is made.

## Receipts, cleanup and dependencies

- [Raw sanitized unittest log](../.tmp/m2-recovery/run70.log)
- [Full/fragmented control receipt](../.tmp/m2-recovery/receipts/test_full_ping_is_valid_then_fragmented_ping_recovers_without_replay.json)
- [Backpressure/hold receipt](../.tmp/m2-recovery/receipts/test_saturated_media_pause_preserves_moderator_hold_across_reconnect.json)
- [Refusal receipt](../.tmp/m2-recovery/receipts/test_refused_loopback_connection_exhausts_five_reconnects_without_hanging.json)
- [Final process/listener cleanup](../.tmp/m2-recovery/cleanup.txt)
- [Inherited cgroup](../.tmp/m2-recovery/cgroup.txt)
- [Uncommitted test-file diff](../.tmp/m2-recovery/tests.diff)

MediaMTX PIDs **4103473**, **4103676**, **4103911** exited **0** via owned
MediaMTX context shutdown/wait. Encoder worker PIDs **4103486**, **4103686**,
**4103896**, **4103921** were reaped by Egress close/failure handling; each
receipt confirms no surviving child and absent `/proc/PID`. Faulty native
workers were stopped by the production Egress process-isolation path, not by
the fixture. Proxy threads and controller were joined. Runner **4103468** and
timeout **4103467** exited. Final read-only `ps` found none of those PIDs;
listener inspection found none of the recorded ports. No retained process or
stop command remains. Only threading.Event is used in fixtures, avoiding the
previous killed-sender multiprocessing.Event lock problem.

Credentials were generated in memory by existing Credentials, passed in
private pipes/stdin, never argv, disk or diagnostics. Before persisting or
printing each diagnostic JSON, all generated user/password values were checked
absent. Only fixed codes/classes and selected numeric telemetry were retained;
no upstream exception text or socket payload was logged.

Existing Python **3.11.14** and PyAV **16.0.1** environment reused read-only.
Existing MediaMTX **v1.21.3**, MIT, verified binary SHA-256
`bfa372a169751bbf6da2ebddcbcd2f7d3ab3dca3cc553022162eda36fe03e73d` reused.
Existing PyAV BSD-3-Clause and its FFmpeg GPL-2.0-or-later/libx264 component
notices, NumPy BSD-3-Clause and OpenCV Apache-2.0 apply, as already recorded in
`relay/README.md`. No new dependency/model/license was introduced. Synthetic
pixels/audio are original CC0 random fixtures, no music/logos/location labels;
they are not privacy-qualified. TemporaryDirectory cleans archives and configs;
only the explicitly selected receipts remain in this checkout's ignored scratch.

## File fingerprints and handoff

```text
tests/m2/test_recovery.py
  9c2687e217e716c9b50a25b87c5e9bd1a399a21a906147f4e13c7cbd76f06155
tests/m2/recovery_fixture.py
  5e75baf9eabfa918aff47c84e55320cf72500291d3ee9f8d8da5a3a52b7854f0
.tmp/m2-recovery/tests.diff (test diff followed by fixture diff, /dev/null baselines)
  cf9cd90559dde22714510f9c94f5c78818f7f56998e10c9439bcfd257422b29e
.tmp/m2-recovery/run70.log
  aa3433d4ad95a3e11a54b58eb8a82dfa634b17d16f2f2a4ec5689e3f4448d3f3
```

Test source was not edited after invocation 70; the files remain untracked as
required. Explicit `git diff --no-index --check /dev/null <file>` found one
cosmetic warning in `recovery_fixture.py:353`: a new blank line at EOF. The
test file and hand-back had no whitespace findings. The fixture is left byte
for byte as run; the parent can trim that final redundant blank when copying.
The parent audits/copies these two test files and activates its production fix
before green **71**, then owns gate **72**, soak **73**, and the remaining retry
reserve through **76**. This worker spent no additional test/native invocation
and stops here within the Fri 08:00 PT / 15:00Z fix timebox.

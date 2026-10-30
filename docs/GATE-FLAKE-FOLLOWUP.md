# Busy-host gate follow-up

This is a test-only follow-up to the completed original 40/40 sweep, based on
`d3ed2abb52604c577c062185a49b82db4c2f324b`. Its separate append-only ledger is
`out/flake-followup/invocations.jsonl`. The original sweep and its receipts are
untouched. This checkpoint is **not a completed stress or full-gate result**.

## Reproduced causes and repairs

The bounded descendant fixture opened its PID file before writing the integer.
A descheduled writer could be killed by the two-second deadline in that gap.
Invocation 1 reproduced the empty-file `ValueError`; the normal-exit variant also
expired during setup. The fixture now writes a temporary file and atomically
renames it, waits for a complete positive integer, captures the descendant's
psutil identity, then acknowledges readiness. A test shim starts the existing
two-second deadline only after that acknowledgement. Both normal leader exit and
timeout still require descendant exit. The reader and shim have bounded setup
fuses. Identity-aware status/reaping replaces a bare PID kill; empty command-line
text is never used as evidence of death. The descendant's unused output goes to
`DEVNULL`, so a surviving descendant cannot hide behind an inherited output pipe.
The same three-second publication delay passed in invocation 3.

The permission-error fixture had the same publication problem in `owned.json`.
Invocation 6 reproduced `JSONDecodeError` after a real writer was paused with an
empty target. Its writer now atomically renames complete JSON before the existing
readiness check. Invocation 7 passed the same delay. The denied-live-group case
still fails the bounded command with `PermissionError`; a zombie-only group still
permits the timeout result. The half-second deadline and signal-denial injection
are unchanged.

The actual `NetworkInput` reader publishes `error_code='input-eof'` before it
publishes DROP. That diagnostic is an early observation, not a completed reader
handoff. Invocation 2 held this boundary until drain and observed old video.
Invocation 4 used a 150ms scheduling gap and failed the DROP assertion for all
queue sizes 1, 4 and 7. Invocation 5 passed the same gap after synchronization on
the publisher's real second TCP accept. That accept can occur only after the
first reader's DROP handoff. No old-generation rows may follow DROP; actual HOLD
slates, generation advance and fresh media reanchoring remain asserted.

The full-queue file EOF check had the same early observation. Invocation 12
reproduced an empty drain before DROP publication. The test now holds the real
reader immediately after its actual `_send` publishes EOF invalidation; the
asserting thread acknowledges that boundary before releasing it in `finally`.
It retains the real file decoder, full-queue eviction, queue bounds, DROP reason,
repeated close and stopped-thread assertions. Invocation 13 passed the same
150ms publication gap. No production reader or timeout changed.

The six-second fragmented proxy fault can outlive its old three-second control
thread join. Invocation 14 reproduced `fixture-control-failed` using only real
Python loopback sockets, with a full six-second fragment pause and retired peer.
The exact prior retirement repair now permits the fragment timer to finish before
closing the control thread's sockets and checks stop/done before its next select.
The owning regression is included in `tests/m2/test_recovery.py`. No native
encoder, MediaMTX server or credentials are needed by that regression. Invocation
15 passed the same full-duration repro with the exact prior fixture repair.

## Contract checks

Invocation 9 deliberately replaced group signaling with leader-only signaling.
It failed at the command-output cancellation fuse because the descendant retained
an inherited pipe. After routing unused descendant output to `DEVNULL`, invocation
11 failed both exit paths specifically with `Bounded command left a running
descendant`; the test's finalizer killed and waited for its captured identities.
This proves the repaired fixture still rejects the cleanup bug on timeout and
normal leader exit.

Invocation 10 removed only invalid-generation filtering from the runtime drain
function in the probe process. All queue sizes failed the original HOLD assertion
(`PROTECT` or `LIVE` instead of `HOLD`). The actual EOF reader and original
assertions ran. No production file was edited. These deliberate negatives and all
failed attempts remain in the ledger; none counts toward consecutive green stress.

Invocation 16 ran the final short selection without injected scheduling or
production mutations: both bounded tests, both actual-reader EOF tests and the
proxy-retirement regression passed (five tests, no failures/errors/skips). This
selection does not execute the native Egress or saturation tests.

The original recovery assertions are retained: the first reconnect must be the
injected `egress-write-timeout/network-mux`; additional recoveries may only be
contiguous reaped frame-free startup failures. Old/fresh ACK counts, exact PTS,
failed-frame exclusion, immutable old archive, fresh HOLD and moderator retention
remain unchanged. The six-second pause and native five-second deadlines remain.

## Recovery limits and pending work

Prior evidence is in
`/home/elan/.t3/worktrees/irl-shield/t3-af2b13f9/out/live-recovery/`, including
`first-fault-timelines.json`, `reachable-source-identity.json`,
`retirement-checkpoint.patch`, `controller-observation.patch` and
`gate-packet-v2.json`. Its combined patch SHA-256 is
`d7f63244a3127741902479239b56da0dc9d5e03e615f66c5620f148f9b1e6157`.
The current retirement repro independently confirms only the socket-lifetime race.

The prior controller handoff captured index 314 while index 315 actually failed.
Its separate fix revalidates worker identity, inflight frame, last ACK and complete
progress tuple after `/proc` observation. That patch is preserved as a pending
candidate in `out/flake-followup/pending-controller-observation.patch`; it has not
been applied or newly reproduced here. Native reproduction must precede that edit.

Historical native index 503 before pause and index 93 after injection were
worker-reported `egress-write/network-mux` exceptions. Their original exception
class, errno and socket queues were discarded; their exact causes remain
**UNKNOWN**. The separate pre-pause blocked reference produced a parent
`egress-write-timeout` and stayed red. It does not attribute those historical
worker exceptions. These recovery tests construct `Egress` directly and do not
reach runtime or TLS. No TLS/forwarder/wire source was touched.

The native diagnostic driver is prepared under `out/flake-followup/diag/` to retain
first-fault details, worker PID/start ticks, controller/inflight timeline, socket
queues, proxy byte progress and sanitized server-close ordering. It has not been
run in this lane. If a genuine production defect appears, its regression remains
red and an exact production-fix proposal goes to root; no production edit is
within this patch's fence.

No `BURNER_WINDOW_RELEASED` message has arrived at this checkpoint. No CPU burners,
native RTMP recovery, GPU work or full gate were launched. The five consecutive
complete touched-module rounds with 16 owned burners, burner CPU/load receipts,
remaining native recovery repro, and the single `scripts/check` invocation remain
pending. The full gate additionally requires root's explicit scheduling release.
`out/flake-followup/gate-packet.json` binds the proposed command and exact patch;
it does not claim execution. Root owns expansion/W1 and all timed queue jobs.

## Static inventory

`out/flake-followup/module-timer-inventory.json` covers every tracked Python module
under `tests/` at the exact base, including modules with no targeted hits. It lists
baseline source hashes and line-level hits for pidfile, child-written `read_text`,
real sleeps, deadline/timeout, process lifecycle, `/proc` and subprocess patterns.
Mocked calls, controlled clocks and synchronous artifact reads are distinguished
from real child readiness and setup/cancellation fuses. Excluded lanes are listed
without edits or a claim of revalidation.

Unreproduced risks remain in the short Event/Condition fuses of `test_lanes.py`,
`test_motion_worker.py`, `test_clocked_pipeline.py`, M2 relay coordination and M3
HTTP/auth/events/transport. `test_egress_ingest.py` also has a four-second healthy
burst window that a descheduled observer can miss. The synthetic gate compiler
and tiny ffmpeg fixtures use synchronous child exit before reading artifacts;
their 20-second timeouts are cancellation fuses. macOS-only ffmpeg and synthetic
git calls lack local subprocess fuses. None was changed without a matching repro.
No additional test source paths were edited.

The hand-back indexes exact-parent plain archive application, hashes, whitespace
checks, raw red/green logs, pending resource-gated checks and cleanup. No staging,
commit, push, PR, dependency/SDK mutation, Mac, Twitch, bench, owner-data or held-out
operation is part of this lane.

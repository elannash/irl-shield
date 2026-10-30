# Live recovery diagnosis

The original 38a4124 gate remains red. Its two first reconnect causes are unresolved.
This patch repairs a separately proven recovery-fixture retirement race. It does
not repair or excuse the original early native `egress-write` errors.

## Exact pristine comparison

The comparison used exact live `38a41244020f66666d0fcc5101523a00157cff9a`
and main `9e37b2cce6e8e0b5a7afd1fe8e5f2c3e92d14ade`. Live passed all
three module runs. Main passed two and failed one. The main failure was a
third symptom, `blocked_index=310` versus first recovery `failed_index=311`.
Neither original failure reproduced in these six runs. This sample cannot
establish a commit-specific regression rate or prove the live change innocent.

| Trial | Commit | Result | Test wall s | Launcher wall s | Load 1m min / mean / max | CPU PSI some avg10 min / max |
| --- | --- | --- | ---: | ---: | --- | --- |
| 1 | `38a4124` | PASS 3/3 | 41.559 | 42.057 | 7.61 / 8.42 / 9.74 | 1.41 / 3.32 |
| 2 | `9e37b2c` | PASS 3/3 | 65.306 | 65.572 | 8.00 / 10.60 / 13.90 | 1.61 / 7.53 |
| 3 | `9e37b2c` | FAIL 1/3 | 44.400 | 44.754 | 12.82 / 13.90 / 16.02 | 2.14 / 13.22 |
| 4 | `38a4124` | PASS 3/3 | 72.082 | 72.524 | 13.52 / 17.81 / 32.19 | 2.42 / 18.59 |
| 5 | `38a4124` | PASS 3/3 | 68.115 | 68.486 | 28.02 / 31.85 / 35.12 | 1.67 / 8.39 |
| 6 | `9e37b2c` | PASS 3/3 | 44.099 | 44.435 | 31.36 / 32.52 / 34.45 | 1.65 / 4.89 |

Each module contained the same three recovery tests. The launcher used the
same absolute read-only Python 3.11.14 SDK, PyAV 16.0.1, NumPy 2.2.6,
OpenCV 4.11.0.86, pinned MediaMTX 1.21.3, environment and argv.
Live used the assigned worktree; main used a plain `git archive` export.
All tracked bytes matched their pinned commit blobs before and after each run.
No source hooks were installed for this comparison.

Every run acquired `scripts/host-lock shared` on the canonical perf lock,
ran at nice 10 in `app-t3code-agents.slice`, limited native threads to two
and OpenCV to one, and retained raw load and CPU/memory/I/O PSI samples.
Order alternated across pairs. Load changed organically. It was comparable
within some windows and rose substantially across the series. These are
functional trials with pressure context, not isolated timing measurements.
The launcher wall includes any lock wait. The test wall comes from unittest.
No load samples or failed attempts were excluded. No CPU burners ran.

The full matrix, invocation argv, start/end times, raw one-second samples,
receipts, logs and all-source hashes are under `out/live-recovery/`.
[comparison-matrix.json](../out/live-recovery/comparison-matrix.json) defines
the sample frame and [pristine-source-hashes.json](../out/live-recovery/pristine-source-hashes.json)
contains every tracked file hash. Relevant bytes common to both commits:

| Source | SHA-256 at both pristine commits |
| --- | --- |
| `tests/m2/test_recovery.py` | `70d313b796d34e08bef39bc40dc80aefaa52994ae47d9c22d71fe9b1decd4465` |
| `tests/m2/recovery_fixture.py` | `7d8cf391fd76e17ac91de80614bcf0d95adf698ff380e656167cb0605b3d3715` |
| `relay/stream.py` | `60650ddf5e43fd528dcc5afa4fed014d56b280e16e35204568714866dcdcbaf3` |
| `relay/live.py` | `57f8dea8546af832cde76271052a9cf246dacacbda3a2eba73366c380776e583` |
| `relay/mediamtx.py` | `989660d599309fba70b8598841ba31c1eb7fd6bd7de41c0ff44abdef6386da09` |

## Callgraph and original first faults

`EgressRecovery.control_condition` constructs `Egress` directly. The saturation
test constructs `Egress` and passes its direct write adapter to `RelaySession`.
The destination-blip test also constructs `Egress` directly. None calls
`runtime.run`, `EgressWriter`, or `TLSForwarder`.
`runtime.run` constructs the forwarder only inside `if publish_twitch`.
`publish_twitch=False` opens no forwarder. The MediaMTX environment is identical
at the two comparison commits. No live source changed in the merge from live53.
See [callgraph-checkpoint.txt](../out/live-recovery/callgraph-checkpoint.txt).

The copied complete original gate log is
[original-gate.log](../out/live-recovery/original-gate.log), lines 411-429.
Its fragmented case first failed in generation 1, `network-mux`, index 93,
with code `egress-write` at monotonic 159309.147706674. Injection was at
159306.522917934. The later `fixture-control-failed` has no exception class,
socket identity, phase or timestamp in that historical receipt. The first
native failure's errno and exact cause cannot be recovered from that log.

Saturation first failed in generation 1, `network-mux`, index 503, with code
`egress-write` at 159330.997141482. It had no pause and no observed native
kernel wait. Generation 2's `egress-startup-timeout` occurred later and does
not identify the first cause. No original server-close or socket-error trace
survives in the supplied evidence. A MediaMTX timeout remains a hypothesis.

## Proven secondary fixture defect and repair

`FaultProxy._controls` waits six seconds after the first fragmented Ping byte.
An early publisher disconnect makes `_connection` set its `done` event and
join that control thread. The old three-second join expires before the pause
ends. It closes both sockets while the control thread still owns them.
The control thread later finishes its timer and calls `select` on descriptor
`-1`, raising `ValueError` and reporting `fixture-control-failed`.

The new loopback regression retires a publisher immediately after the first
Ping byte. It exercises the real proxy threads and sockets without an encoder,
MediaMTX, credentials or shortened fault. It asserts the full six-second
elapsed pause, no server error, stopped threads and no proxy error.

- [09-proxy-retirement-red/test.log](../out/live-recovery/09-proxy-retirement-red/test.log)
  fails for `fixture-control-failed` on the exact original fixture.
- [10-proxy-retirement-trace-red/events.jsonl](../out/live-recovery/10-proxy-retirement-trace-red/events.jsonl)
  records PID 2299398, control thread TID 2299449, `OSError` errno 9 on the
  tail send at 160291.985096032 and `ValueError` in `select` at
  160291.985284907. Both descriptors are `-1`.
- [11-proxy-retirement-green/test.log](../out/live-recovery/11-proxy-retirement-green/test.log)
  passes the same regression after the repair, with a full six-second pause.

The media thread now allows the entire timer to finish before closing the
control thread's sockets. The control thread checks the stop state before
another read. Exception classification and parser errors remain unchanged.
Production five-second deadlines and the six-second injected fault remain
unchanged. All original recovery test methods and assertions are retained. The continuation changes the saturation controller body to reject stale observations, as documented below.
The original early native error would still fail the strict expectation for
`egress-write-timeout`; this repair cannot turn that error into a pass.

The fixture and old test files are identical on exact main and exact live.
`changes.patch` applies to both pinned archive exports with matching final
hashes, so the conductor can coordinate a fixture follow-up on main.

## Additional observations and limits

The independent pristine main failure at trial 3 shows a stale saturation
observation: the controller captured index 310, then index 311 actually timed
out. The continuation reproduces and repairs that observation race. Its original strict equality assertion remains.

After the six pristine runs, diagnostic hooks recorded worker PID/start ticks,
generation, operation, progress, readiness, native failure details, socket
exceptions and MediaMTX fixed close codes. Those runs are labeled instrumented
and are excluded from the pristine matrix.

The first instrumented run went red with an initial fragmented worker startup
timeout, an `egress-worker-survived` cleanup error, and `safe_failure` accessing
an unassigned output. Saturation had 333 manifest rows against 332 parent ACKs.
These are additional symptoms, not the original first native error.
The worker lifecycle and manifest/ACK paths are in `relay/stream.py`, outside
this packet's edit fence, and were not changed. All observed owned identities
are checked during final cleanup.

The narrower fragmented observation passed. Its first failure was the intended
`egress-write-timeout` at index 93, `network-mux`, worker PID 2292453 with start
ticks 16020629. The final instrumented saturation observation also passed,
with an intended generation-1 timeout at index 312 after its pause. Neither
attributes the original early `egress-write` failure. See diagnostic runs
`07-instrumented-affected`, `08-instrumented-control` and
`12-instrumented-saturation` for complete logs and fixed diagnostic events.
The first diagnostic driver's startup imports added a further confound;
subsequent drivers keep fixture/test imports out of encoder startup.

The retirement-only checkpoint passed its three affected tests without hooks in [13-final-affected/test.log](../out/live-recovery/13-final-affected/test.log). The final combined-source run is [25-final-affected-v2/test.log](../out/live-recovery/25-final-affected-v2/test.log).

No full gate was run in this lane. The one reserved gate requires conductor
coordination. `gate-packet.json` and its hash bind exact source, SDK, binary,
limits, environment and command without launching it. No GPU timing, native
bench, Twitch, key, Mac, package install, staging, commit, push or PR occurred.
The worktree remains locked for Opus review. `handback.json` records the final
budget, process audit, export/apply/whitespace proof and unfinished work.


## Continuation within the same 32-call budget

The original gate remains RED. No pristine N3 comparison was repeated. The
retirement-only patch, source and hand-back are preserved in `checkpoint-20/`.
The continuation adds a separately proven controller-observation repair.

### Worker error versus parent timeout

At exact38 and exact9e37, `relay/stream.py:546-562` reports a parent reply
TimeoutError as `egress-write-timeout`. A generic parent channel exception
reports `egress-write` without an operation field. A worker `error` reply
reaches `_fail(phase, details)` with its operation preserved. Thus historical
`egress-write` plus `network-mux` at index503 identifies a worker-reported
exception, not merely the parent's five-second reply deadline. The same
classification applies to the original fragmented index93 event.

The exact original exception class and errno are irrecoverable from the
retained record. `_encode_worker` constructs those fields at lines444-449,
but `_recover` at lines580-586 copies only the error code and operation into
the recovery event. `Egress.write` clears error details after successful
recovery. The old test persisted neither that first worker reply nor the
MediaMTX close events, socket queues, per-frame phase timeline or controller
heartbeat. Its TemporaryDirectory removes the media/manifest artifacts.
A future green test, an identical source hash, and the later generation2
startup timeout cannot reconstruct the missing original values.

Pure CPU starvation producing a parent reply timeout does not match the
historical error classification. An indirect sequence such as scheduling
pressure causing a server deadline, followed by a native socket exception,
remains possible. So do other native mux errors. The old server-close ordering
and worker errno would distinguish them; neither was retained.

### Executed source identity

[reachable-source-identity.json](../out/live-recovery/reachable-source-identity.json)
records the observed relay/shield functions and exact source comparisons.
Every observed production file is byte-identical between commits except
`relay/security.py`. Every executed function in that file is byte-identical.
`RelayControl` constructs `TwitchDestination`, whose unchanged `__init__`
only initializes its in-memory field. Its changed `destination` method is
never called. Neither `runtime.run` nor TLSForwarder is called. The spawned
encoder still uses unmodified `_encode_worker` from the identical complete
`relay/stream.py`. There is no observed live-only call-path difference to
which these faults can be attributed.

### Native and controller timeline

[first-fault-timelines.json](../out/live-recovery/first-fault-timelines.json)
contains admission, first controller deadline/candidate, raw server-control
message metadata, cumulative media-byte progress, worker identity, kernel
wait, CPU ticks, socket queue, phase/index and parent reply deadlines for
each labeled single-test observation. Control payloads and credentials are
never logged. The event named `native-first-fault-before-stop` is a parent
observation point; its code distinguishes a worker exception from a parent
timeout.

The ordinary instrumented observation passed. At its first real blocked
candidate the worker slept in `poll` with about1.91MB queued on its RTMP
socket. The controller armed before the parent deadline, then the deliberate
pause produced the intended `egress-write-timeout`. This observed mux wait
was backpressure rather than a runnable encoder waiting for CPU.

Fixed controller delays of5.5s and12s did not produce a pre-pause fault while
the prelude continued to drain64bytes per20ms. Several frames still ACKed.
Both produced stale-index failures later. Controller loss alone was therefore
insufficient to reproduce the historical native exception in those schedules.
One delayed run also spent part of the parent reply budget outside its final
network phase and later showed a generation2 startup worker in kernel I/O wait.
That is a recorded extra symptom, not an attribution of historical index503.

The explicit pre-pause reference uses ACK90 admission, a6.2s read hold at the
first native blocked candidate, and a12s controller delay. At monotonic
161330.58683987, the prelude admitted at90ACKs. The first candidate at
161338.217293159 observed generation1, frame310.
Its controller fuse deadline was 161390.602617288.
The reply deadline was 161342.946412754; the first fault was at
161342.973591431, code `egress-write-timeout`, before any pause was reached.
The worker was PID2394483, start ticks16132645,
sleeping in `poll_schedule_timeout.constprop.0` with socket TX queue
1908280bytes. Its CPU tick counts did not increase
between the candidate and first fault. Proxy media-byte progress stopped
through that fault and MediaMTX had no earlier close event. The original
strict test remained red, including its controller lifecycle assertion.
All owned processes eventually exited. This demonstrates an unplanned
pre-pause backpressure timeout reference. Its timeout code differs from the
historical worker exception, so it does not establish that old cause.

### Stable controller observation

The old controller sampled inflight/progress, then read `/proc` without
checking whether that write had completed. The physical handoff probe admits
bounded native reads while those observations are held. The old controller
then arms with index314 while index315 actually times out. The unchanged
original equality assertion fails `315 != 314` in
[22-physical-stale-index-red/test.log](../out/live-recovery/22-physical-stale-index-red/test.log).
This is the same observation inconsistency as pristine main's310/311 red.

The controller now revalidates worker object identity, inflight frame,
last ACK and the complete progress tuple after reading `/proc`. It discards
a changed sample, refreshes observation age and keeps polling. Receipt phase
and indices come from that validated sample. No deadline, kernel-wait
requirement, pause duration or recovery assertion changes. A handoff after
the final guard remains detectable by the existing strict index assertion;
this is not a claim that Python and native state form an atomic transaction.

The same physical probe passes in
[23-physical-stale-index-green/test.log](../out/live-recovery/23-physical-stale-index-green/test.log),
and its receipt confirms that the handoff occurred. A probe with no actual
handoff is required to return nonzero. The final run without hooks exercised
all three affected tests in 45.193s and returned exit0.
The final result is PASS for that affected selection only.
The historical full gate is not relabeled.

`retirement-checkpoint.patch` contains only the first fixture repair and its
new regression. `controller-observation.patch` adds the snapshot guard to
that checkpoint. `changes.patch` is the complete coordinated patch including
this document. Plain exports of both exact commits verify both the combined
patch and the sequential code patches against final SHA-256 values.
The updated immutable full-gate packet is `gate-packet-v2.json`; the earlier
packet is retained as a checkpoint and does not describe the final source.
The full gate remains unrun pending conductor coordination.

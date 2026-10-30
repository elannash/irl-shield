# Deterministic gate sweep

Test-only patch against `9dcb70e70746bead79a98e55f756baf8c07e1352`.
`out/gate-flakes/handback.json` indexes the append-only ledgers, logs, source
hashes, mutation diffs, CPU samples and process cleanup receipts. Proof artifacts
are excluded from the patch. Production bytes and native deadlines are unchanged.

Both complete initial loaded runs selected all 26 tests across the three requested
modules and failed `PROTECT != LIVE` in the saturation fixture (invocations 2–3).
The other historical flakes did not recur naturally in those two runs; their
contracts were audited and exercised with physical negative proofs. No skips or
expected failures were added.

Queue tests now use state and artifacts for completion, with generous cancellation
fuses. `test_preexec_retries.py` inherits that common runner fix and has no direct
file change. Exactly three contended executions, `A1 B1 A2 A3`, successful command
exit and valid `other_busy` classification remain required. Rejected starts still
consume zero execution budget and retain unique trial ordinals and artifacts.
The procfs fixture waits for descendant readiness and keeps both processes alive
through both real snapshots. It requires positive descendant CPU, valid accounting
and exact attribution excluding foreign processes. Watchdog commands wait until
killed rather than exiting on a short sleep; the tests await owned PID exit,
verify lease retention after runner crash and release after the native hard stop,
and leave an unrelated process running.

The saturation source must continue feeding while native egress blocks. Diagnostic
7 measured 174 input evictions and 146 ingest gaps among 153 ACKs. The repaired
fixture uses an independent elapsed-time video producer, real asynchronous detector
lanes, a one-second presentation buffer and bounded 480-frame input retention.
Audio is real encoded silence. This preserves the LIVE assertion and high-entropy
video rather than allowing ingest-gap slates to drain the intended mux load.

A phase-age-only pause also completed without any recovery (invocation 8). The
controller now resolves `network-mux` by name, matches the active unfinished frame,
and requires a sleeping native worker rather than a runnable encoder or idle IPC
reader. Invocation 9 observed `poll_schedule_timeout.constprop.0` at LIVE frame
312, completed index 311, a genuine `egress-write-timeout/network-mux`, 91 warmup
ACKs and a reaped replacement. Invocation 8 had no wait-state capture; attributing
that particular false stall to CPU descheduling remains an inference.

Recovery still requires one injected mux timeout. Additional recoveries may only
be contiguous, reaped, frame-free startup timeouts. At least 90 real old-generation
ACKs, 20 final-generation ACKs, exact media PTS, honest index gaps, failed-frame
exclusion, immutable old archive, fresh HOLD, retained moderator control and cleanup
remain required. Completion follows final-generation ACKs. Setup deadlines are
cancellation fuses; the real six-second pause and native five-second timeouts remain.
Moderator HOLD must precede the old write's actual timeout.

Physical negative / exact-restored green pairs are recorded for the execution cap
(11/12), watchdog lease (13/14), rejected-start budget (15/16), descendant accounting
(17/18), hard-stop reason (19/20), mux phase (21/22), additional recovery classification
(28/29), and cleanup leak (30/31). Reordered production phase indices plus a 0.7s
encode delay at frame 90 pass (23/24). A genuine generation-2 startup delay exceeding
the native timeout passes with a frame-free failed generation (25/26). Cleanup
negative 30 prints the credential-checked diagnostic with `M2_RECOVERY_RECEIPTS`
unset. `recovery_fixture.py` is unchanged.

Failed setup, intermediate repairs and unsuccessful proof attempts remain in the
ledger, including the phone-test interruption. Invocation 5's archive-mux timeout
and transient worker-alive cleanup report ended with its owned scope; the underlying
cause remains unproven. Historical survivor PID 1586171 and parent call 26 also
remain unexplained. Host load and actual burner CPU ticks are recorded as context,
not used to qualify latency or waive a failing contract.

Final complete-module stress runs 32–36 passed consecutively: 26 selected tests
per run, zero failures/errors/skips, with the same 16 owned Python burners on eight
logical CPUs. Every burner advanced real CPU ticks. All 16 were terminated and
reaped at 2026-10-30T18:37:27.189613Z; the parent received the GPU-window release.

The old ten-second pre-execution fuse was deliberately reproduced with slow
synthetic health sampling (37: `hard-stop != drained`). The same delayed sampling
passed with the repaired fuse (38), retaining all four rejections and the first
actual execution. Both test files were then restored exactly. The single unified
Linux gate is invocation 39; its result and the final apply/hash audit are indexed
in the hand-back.

The unified Linux `scripts/check` gate exited 0: 277 tests selected, zero failures
or errors, two existing skips: VideoToolbox requires macOS, and the pinned native
Twitch CLI is unprovisioned. All three requested modules executed; 139 Python files
compiled. The Apple Vision Swift build is explicitly not run
on Linux. The final patch audit checks actual plain-scratch application, every
post-apply hash, all tracked production bytes and absence of owned survivors.

# PR5 writer follow-ups

This patch addresses the three writer findings in the Claude round-2 review
(`pr5-review-claude-r2.json`), against parent
`4f3adbec1e628891bb3cfc855c3a617a851425cf`.

## Readiness and buffered audio

`EgressWriter.write()` reports destination readiness independently of whether
its latest-frame slot accepts, replaces, or skips a result. Startup is neutral
(`None`); a genuine failed write reports `False`; a successful write reports
`True`. A native `None` completion preserves the previous readiness, including
an outage waiting for a network acknowledgement. Skipping a stale result after
a slow successful write preserves healthy readiness. The existing freshness
floor and pending-slot discard still apply.

`tests/integration/test_writer_semantics.py` exercises the real writer,
`RelaySession`, and control state with a controlled engine adapter and output
adapter. The startup case holds the first write open while the session keeps
processing frames. The stale case advances only the writer's clock across a
slow successful write, then sends a pre-completion result in a poll batch with
a fresh result. Both require zero interruptions, LIVE state, unchanged future
audio samples, and delivery of the later nonzero PCM. A separate genuine-outage
case verifies audio invalidation, black HOLD output through a pending native
acknowledgement, and subsequent LIVE output with fresh PCM after readiness.
These tests cover writer/session semantics; they do not qualify the detector,
native encoder, or network recovery protocol.

Receipts in `out/followups/`:

- `02-startup-red.log`: the old initial `False` reports an interruption (`1 != 0`).
- `03-startup-green.log`: neutral startup passes the same session/audio test.
- `04-stale-red.log`: a stale result following success reports an interruption.
- `05-healthy-green.log`: both healthy cases pass after preserving readiness.
- `13-receipts-final.log`: the final affected selection includes both cases and
  the genuine-outage case.

## Stall-test sensitivity

The existing six-second TCP/NUT test still uses the real `NetworkInput`, real
masking engine, real runtime loop, synthetic pixels, and a blocked output
adapter. It now witnesses calls to the real engine's `submit()` and records the
engine's presentation progress. Strictly inside the block (excluding 250 ms
at each end), at least 30 submissions, 30 input-index steps, and 30 engine
outputs must occur. The submitted ingest must be less than one second old.
The reader continuity, generation, bounded queue, moderator HOLD, black output,
fresh post-resume presentation, and unique ordered output-index assertions
remain in place.

The old synchronous passthrough was physically written to `relay/egress.py`.
The test failed with **zero** submissions during the block. The production
writer was restored byte for byte, then the same test passed.

- Mutation: `out/followups/mutations/egress-blocking-mutant.py`, SHA-256
  `403f23ae148bf3bbec9ecd6bbebca9959b968334d94bf4b868d35c02d1a0c51f`.
- Pre-mutation/restored writer SHA-256:
  `29b74fb8ebc1381dfb3c61868f066cba2a0ce349cb5afb95aeb198545cc4b223`.
  This is the intermediate writer before the later shutdown collection method;
  the final source hashes are in `post-apply-sha256.json`.
- `08-stall-blocking-mutant-red.log`: `0 not greater than or equal to 30`.
- `09-stall-restored-green.log`: the restored writer passes the strengthened test.
- The applied diff, mutated source, restoration source, and hash receipt remain
  in `out/followups/mutations/`.
- After adding the shutdown collection method, the physical mutation was repeated
  with a synchronous adapter implementing that method. `14-final-stall-blocking-mutant-red.log`
  again fails for zero during-block submissions, and `15-final-stall-restored-green.log`
  passes after byte-for-byte restoration. Final mutation/restoration hashes are
  recorded in `mutations/final-restoration.json`.
- The sanitized receipt from call 13 is in
  `receipts/test_destination_stall_keeps_real_reader_connected_and_resumes_fresh_hold.json`.
  Its during-block sample contains 166 submissions, 165 input-index steps, and
  165 engine outputs, with zero input failures, disconnections, or egress
  interruptions. This is a functional progress witness, not a performance score.

## Terminal and cleanup failures

Write errors and cleanup errors have separate storage. `close()` joins the
writer and raises only a real cleanup failure or surviving-thread failure.
`raise_if_failed()` collects a terminal write error separately, including after
shutdown if the stop event prevented the next `write()`. The real `run()`
records the primary transport failure, performs all cleanup, collects any late
writer failure, writes diagnostics, and surfaces the fixed transport message.
Genuine cleanup failures remain in `cleanup_errors`; they do not overwrite a
primary transport error. A cleanup-only failure still surfaces the fixed
cleanup message.

`RuntimeWriterFailure` in `tests/integration/test_runtime.py` uses the actual
runtime, asynchronous writer, and engine. Only input/output transport adapters
are synthetic. It requires actual write attempts and resource shutdown,
checks the fixed `egress-recovery-limit` output code, and checks that a
synthetic credentialed URL never appears in the surfaced exception, formatted
traceback, stdout/stderr, or persisted runtime JSON.

- `06-terminal-red.log`: both terminal cases incorrectly become cleanup failures;
  the cleanup-only case already passes.
- `07-writer-runtime-green.log`: write errors and actual cleanup errors are separated.
- `10-terminal-stop-red.log`: after the close-only correction, a terminal write
  racing shutdown could be lost (`RuntimeError not raised`). This failed attempt
  is retained.
- `11-shutdown-green.log`: explicit post-join failure collection fixes that race.
- `13-receipts-final.log`: final runtime, writer, ingest, and existing live-session
  regressions pass together.
- `receipts/test_terminal_*.json` and
  `receipts/test_actual_writer_cleanup_failure_is_reported.json` retain the
  observed runtime summaries, surfaced messages, write attempts, and shutdown
  outcomes from the final affected run.

## Execution and limits

The invocation ledger is `out/followups/invocations.jsonl`; the helper
`run_tests.py` records exact argument vectors, selected tests, source hashes,
UTC times, exits, log names, and thread limits. Call 1 failed before executing
any test because the shell lacked the existing user-bus environment; its log
is retained and it counts against the 16-call limit. Calls 2 onward use
`XDG_RUNTIME_DIR=RUNTIME_DIR` and
`DBUS_SESSION_BUS_ADDRESS=unix:path=RUNTIME_DIR/bus`.

Every test invocation checks the canonical queue for pending/running work and
holds `/tmp/agents/irl-shield/perf.lock` shared and nonblocking. Functional
processes run at nice 10 in `app-t3code-agents.slice`, with OMP/BLAS limits of 2,
OpenCV limit 1, and bytecode writes disabled. The literal read-only integration
SDK interpreter from the packet is used; no packages or overlays were installed.
Call 13 additionally sets `M2_RECOVERY_RECEIPTS` to the lane's own
`out/followups/receipts/` so the existing synthetic receipt helper retains JSON.
There are 15 test-launch attempts (including the initial launch failure) and one
final artifact-validation execution, meeting the 16-execution cap. The artifact
validation applies the patch to plain scratch exported from the exact parent,
compares every resulting file hash, checks whitespace and the file fence, and
audits owned processes. It does not run the full gate or native code.

No native/performance job, bench, held-out evaluation, full gate, Mac work,
Twitch connection, auth, publishing, real key, or old export was exercised or
altered. The conductor owns the unified Linux/Mac gates after integration.
There is no bench scorecard from this lane. No new dependency, model, or dataset
was introduced. All generated test pixels and PCM are original CC0, without
music, text, brands, or logos. No source outside the six-path writer fence was
changed. No staging, commit, push, or PR was performed.

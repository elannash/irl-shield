# PR5 follow-ups

This change starts from `4f3adbec1e628891bb3cfc855c3a617a851425cf`.
It fixes the operator bind diagnostic and writer status/error handling, and
adds the approved startup association rule to the native evidence harness.
The RTMPS investigation takes the explicitly permitted documentation fallback:
**the pinned PyAV egress still does not verify its TLS peer**.

## Operator bind and synthetic soak

`shield run` and `shield login --run` reject a missing bind before starting
authentication. The error names `--host`, `SHIELD_BIND_HOST`, IPv4 loopback
`127.0.0.0/8`, Tailscale `100.64.0.0/10`, and `shield doctor`. The production
bind validation remains unchanged. A synthetic soak defaults to `127.0.0.1`,
even when the operator's phone-facing environment chooses a Tailscale bind.

`tests/integration/test_app.py` exercises the actual CLI and soak parser.
The original code failed both missing-bind cases and the soak default; the
fixed code passes. The soak test stops at the native queue-lease boundary,
before starting any native processes or writing media.

## Writer behavior

[The writer hand-back](PR5-WRITER-FOLLOWUPS.md) records the implementation
and physical mutations. A write that has not completed yet is neutral;
a stale result after a slow successful write retains the last known state.
Neither condition fabricates an outage, sets transport HOLD, or flushes
buffered audio. Actual failure and recovery retain their fail-closed behavior.

The real TCP/NUT reader test requires fresh engine submissions and presented
frames **during** a six-second blocked destination write. Replacing the writer
with the old synchronous path produces zero submissions during the block and
fails. With the restored worker it observes 166 submissions and 165 outputs,
with zero disconnections, input failures or false egress interruptions.
These are functional witnesses under a deliberate stall, not timing receipts.

Terminal writer failures retain their transport classification through the
actual runtime. Cleanup-only errors remain cleanup errors; if both occur,
the transport failure remains primary and cleanup errors remain recorded.
A final error check also covers a terminal write racing runtime shutdown.

## Capture identity and startup association

Pixel identity remains the primary evidence: each captured destination must
match an exact suffix of decoded archive pixels, including generation/index
mapping. The first captured picture is still checked for label edges, HOLD
pixels and LIVE share. No picture or hold observation is removed.

For new native runs, precisely one leading captured frame is excluded only
from absolute timestamp association. Its signed error must be strictly less
than one 30 fps frame period. The receipt reports `startup_alignment` with
its index, manifest identity, error, actual step to the next frame and the
expected manifest step. The second matched frame sets the timestamp origin.
Every remaining absolute association and every consecutive steady-state
interval must agree with the manifest within 2 ms. The startup-to-second
step is reported separately. Two leading excursions cannot be discarded.

The checked-in `tests/integration/fixtures/b508-capture-alignment.json` contains
only CC0 synthetic-capture timestamps, manifest identities and source hashes.
It makes the old receipt's association defect reproducible from a clean
checkout, without its ignored media. An encoded FFV1 fixture exercises the
actual decoder and confirms that every startup picture is still examined.
The tests reject a 13 ms midstream step, two bad leading frames, a 40 ms
first-frame error, an exact one-frame boundary and interval jitter whose
individual absolute errors remain within 2 ms. Disabling the interval guard
causes the interval regression to fail; exact restoration returns green.

The old `b508d46` native receipt remains **FAILED**. Re-analysis under this new
rule is supplemental evidence only, not a new native execution or a changed
historical verdict. No detector, OCR, held-out or native stream rerun is part
of this follow-up.

## TLS evidence and limitation

[The TLS investigation](PR5-TLS-FOLLOWUP.md) and its standalone diagnostic
show that the bundled FFmpeg verifies a peer through configured
`avio_open2()`, but the primary PyAV 16.0.1 output path calls `avio_open()`
without those protocol options. PyAV publishes synthetic H.264 despite an
unrelated CA or wrong hostname. Adding ignored TLS options would give a false
security guarantee, so runtime behavior is unchanged. README and run docs
state the active MITM/stream-key capture risk. Backend verification controls
are green; the actual PyAV security probe is deliberately red. The ordinary
functional gate does not claim peer-verified egress.

One early TLS fixture attempt unintentionally enabled MediaMTX's default MoQ
wildcard listeners (`:8892` TCP/UDP and `:8893` UDP) for approximately three
seconds, 07:05:21–07:05:24 local. It used synthetic certificates and no real
Twitch credentials. Its own server exited and logs record listener closure.
The final fixture explicitly disables MoQ and every ancillary server and
binds RTMPS to `127.0.0.1`. No independent socket inventory was retained; the
claim is limited to the recorded configuration, logs and process cleanup.

## Verification and reproduction

Use the unified pinned Python 3.11 setup documented in [RUN.md](RUN.md), then:

```sh
SHIELD_PYTHON=.venv/bin/python scripts/check
```

The same gate runs the bench, relay, Twitch and integration suites plus
project Python compilation. macOS additionally builds the Swift Vision bridge.
The pinned Twitch CLI integration remains not run by design under the
local-only boundary; its explicit skip does not replace the loopback
pyTwitchAPI tests. This change introduces no package or model installation.

The parent keeps the exact combined patch, source hashes, mutation logs,
both host gate receipts and process audit under
`.tmp/q/pr5-followups/`. The final hand-back reports their actual results;
child exit codes alone are not acceptance evidence. Runtime/native latency,
real phone walking, SRT suitability, A/V sync and secure real Twitch egress
remain outside these functional proofs.

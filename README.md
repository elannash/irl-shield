# IRL Shield

Published historical records use path placeholders: `REPO_ROOT` is the
repository root, `WORKTREE_<id>` identifies the original isolated checkout,
and `OWNER_HOME` is the operator's home directory. `OWNER_TMP` identifies the
original operator-specific scratch root; `RUNTIME_DIR` identifies the user
runtime directory, normally `/run/user/$(id -u)`. `<tailnet-ip>` means the
operator-selected Tailscale IPv4 address. Substitute local values for these
metadata placeholders before using a historical command. Executable scripts
use `$HOME` and UID-derived runtime paths. Historical proof JSON digest values
refer to original bytes at pre-scrub commit `8f12891db2e7347477bfd96329346ba9fd011231`.
The three maintained `SHA256SUMS` files instead identify current delivered
bytes with their original membership, excluding self-hashes. Regenerating those
manifests provides no new evidence that historical commands ran. Immutable v2
`fixtures/fresh-heldout-v2/nonreuse.json` retains its sealed bytes under the conductor's pre-public
exception until the one-shot completes; a later authorized change will record
the old and new hashes.

The repository privacy unittest in `tests/test_repository_privacy.py` scans
Git-tracked text, including symlink target text, for private owner paths and
Tailscale host addresses. It allows only the sealed ledger above. The complete
public policy CIDR `100.64.0.0/10` is permitted; bare host addresses are not.
The existing `scripts/check` gate discovers this test.

IRL Shield is an experimental privacy relay for IRL video. Its masking engine
looks for readable location clues and covers them before presentation. A delayed
frame clock gives asynchronous detector lanes time to work; missing coverage
produces a protected frame, and a local HOLD produces a slate.

The Linux integration command is `python -m shield.cli login|run|doctor`.
[Run instructions](docs/RUN.md) cover private RTMP phone ingest, OBS pull output,
memory-only Twitch authorization, EventSub controls and explicit Twitch publication modes. Native Twitch publishing is not part of local verification. SRT and
walking use remain unqualified; this is not a production relay.

The live application supports Linux only. Windows is unsupported. NVIDIA is
recommended for the default CUDA detector lanes and NVENC encoding. `--cpu`
selects ONNX CPUExecutionProvider for both lanes and libx264 encoding, using the
same pinned environment and cached models. Its default engine presentation
delay is 2.5 seconds; `--delay-seconds` accepts 0.5 through 10 seconds inclusive.
The 0.5-second privacy floor gives detections time to arrive; it does not
guarantee privacy in every scene or at every processing latency. The 10-second
cap bounds delay-related frame and audio buffering; invalid values are refused.
Without these flags, the existing CUDA/NVENC and 1-second delay defaults remain.
Mac OCR grading tools are development tools, not live application support.

**Twitch egress verifies its TLS peer.** PyAV sends RTMP only to a runtime-owned
`127.0.0.1` listener. A standard-library TLS forwarder connects to Twitch on
port 443 with system CAs, certificate verification and hostname checking.
There is no direct unverified RTMPS output route or fallback. The stream key
stays in memory and crosses plaintext only on loopback.

Twitch publication remains off unless selected explicitly.
`--twitch-bandwidth-test` is the default Twitch test mode; `--twitch-live`
requires fresh authorization as `naie` and an attended `LIVE naie` confirmation
each session. Start live publication only in an owner-authorized, attended
session. Omitting both flags keeps authenticated controls without publishing.
[Verified route and loopback proofs](docs/LIVE-EGRESS.md) document the limits:
real Twitch ingest acceptance still requires the owner's attended bandwidth
test, and privacy/walking qualification remains separate.

For a local attended terminal after setup:

```sh
.venv/bin/python -m shield.cli doctor
.venv/bin/python -m shield.cli run --local-only --host 127.0.0.1 --phone-setup
```

For CPU mode after the same setup, from the repository root:

```sh
scripts/walk-linux --local-only --cpu --host 127.0.0.1 --venv .venv \
  --model-cache models/cache --mediamtx-dir .tmp/tools/mediamtx-v1.21.3
```

The root-inspected local CPU collection on an i7-7700K with 8 logical CPUs
observed 3,598 LIVE frames in a complete 120-second steady window, 29.9833 fps,
at a 2.5-second engine delay and 378.426% observed CPU usage (one core = 100%;
partial process accounting including instrumentation). **CPU privacy is NOT
independently graded.** There were no PROTECT, HOLD or slate frames in that
window; the full archive includes protection and HOLD. These hardware-specific
observations do not establish a privacy pass or walking qualification.
[CPU mode and measurement limits](docs/RUN.md#cpu-mode)
include decoder latency, partial CPU accounting, unknowns and the failed clock
guard.

On the 7 natural tune clips (1,050 frames, offline configuration with the
accurate lane at width 1280), CPU and CUDA produced pixel-identical masks. CPU
mode therefore inherits the GPU path's graded results for that configuration.
The native CPU run used width 960 at a 2.5 s delay and is not separately graded.
The known native plaque miss and the comparison's scope are documented in the
CPU run instructions.

The bind address must be supplied with `--host` or `SHIELD_BIND_HOST`. Use
IPv4 loopback for local operation, or the detected Tailscale address for a phone, as described in [docs/RUN.md](docs/RUN.md). Credentials printed for
phone setup go only to the private terminal; do not capture or share them.

Run archives are off by default. Add `--archive <dir>` only when diagnostic
evidence is needed; a low-disk guard stops evidence without stopping the relay.

Gate 1 has not passed. Historical timing results cover the M1 Pro and Linux,
including Linux CPU detection with libx264, but no tune policy meets all privacy
and real-video guards. The frozen held-out evaluation is queued separately;
[the hand-back](docs/M1-HANDBACK.md) distinguishes finished and pending evidence.

The engine accepts timestamped in-memory BGR frames independently of transport.
Apple Vision is available for macOS grading; PP-OCR models use ONNX Runtime on
CPU, Core ML or CUDA in development tools. The live application runs on Linux;
Windows is unsupported.
The selected configuration and its hardware requirements will be recorded with
the final M1 scorecard. A configured 30fps source is never treated as measured
30fps output.

For OCR grading development, the Mac wrapper synchronizes source and provisioned
assets, runs a bounded command and leaves generated media out of git. This is a
bench reproduction, not a live application command:

```sh
scripts/mac --seconds 14400 scripts/host-lock exclusive scripts/bench \
  --candidate vision-union --fast-candidate vision-rectangles \
  --split tune --run-id m1-reproduce-tune \
  --provider coreml --fast-provider coreml --static-model \
  --D 1 --B 6 --A 30 --fast-rate-hz 8 --accurate-rate-hz 4 \
  --fast-width 640 --accurate-width 1280 \
  --fast-limit-side-len 640 --limit-side-len 960 \
  --motion-mode phase --motion-width 320 --motion-min-response .05 \
  --padding .3 --encoder h264_videotoolbox \
  --warmup-seconds 10 --sustained-seconds 30 \
  --area-ceiling .15 --area-ceiling-basis bench/gate-1-policy.json
```

`scripts/bench` provisions hash-pinned fixtures/models and writes
`out/scorecard.json` plus an immutable run directory. This command includes the frozen diagnostic lane settings, proposed15% median
area ceiling and30-second sustained workload. Use a fresh run ID to repeat it.
It reproduces measurement and judging, not a passing policy: no tune candidate
passes all guards. Endpoint-only raw cards cannot claim gate1 until a closed
queue contamination receipt is joined. The one-shot held-out evaluation is
queued separately and remains reserved for the final milestone result.

Current counts, accepted/rejected timing receipts and limits are in
[docs/M1-HANDBACK.md](docs/M1-HANDBACK.md). The per-host overnight scheduler and
safe stop/report commands are in [docs/PERF-QUEUE.md](docs/PERF-QUEUE.md).

The measuring stick covers Latin-script text and Arabic digits observed by
Tesseract `eng`, Vision accurate `en-US`, and PP-OCRv5 English-mobile. Natural
truth requires input confidence at least .9 on two frames; output readings at
.5 can expose a leak. Every visible synthetic label counts. Non-Latin text,
natural text all input judges miss, and single-frame-only natural text remain
unproven. See [bench/README.md](bench/README.md) for the full scoring contract.

Fixtures are licensed CC0 or CC BY, attributed in
[fixtures/ATTRIBUTION.md](fixtures/ATTRIBUTION.md), and muted. They contain
third-party names and logos and are **benchmark-only**, including masked outputs
and previews. No current clip or still is designated demo-ready. Model weights,
download revisions, hashes and licenses are in
[models/manifest.json](models/manifest.json); candidate sources and portability
are in [bench/DETECTORS.md](bench/DETECTORS.md) and
[bench/PORTABILITY.md](bench/PORTABILITY.md).

Architecture decisions and qualifications are recorded in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Experiment history, including rejected
changes, remains in [bench/LOG.md](bench/LOG.md). Built in the owner-designated
Codex thread and its Codex children for the Codex x TwitchCon hackathon.

# IRL Shield

A privacy relay that covers readable text on street signs, storefronts, house numbers and plates in an IRL stream before the video reaches Twitch.

![Generated storefront scene, before on the left and shielded with Patch on the right](docs/images/generated-before-after.png)

Generated scene with fictional names. Before (left) and shielded with Patch (right), from the W8b demo.

## How it works

- Moblin on the phone sends RTMP over Tailscale to the Linux relay.
- The relay delays video by about 1 second to give detectors time to work.
- PP-OCRv6 detectors on CUDA find readable text.
- Masks cover the detected text. Patch is the default; chat can vote for Bar or Patch.
- Frames that have not been checked go out protected. NVENC encodes the video, and a TLS forwarder sends it to Twitch with certificate verification.

## Chat and mod controls

- `!shield hold`: moderators and the broadcaster can hold the stream on a privacy slate.
- `!shield resume`: only the broadcaster can release the chat hold.
- `!skin bar` or `!skin patch`: viewers vote for the mask appearance.
- `!skin lock bar` or `!skin lock patch`: moderators and the broadcaster can lock the appearance. `!skin unlock` releases it.

The private phone dashboard shows relay status, local Hold / Resume controls and QR pairing for Moblin. Keep its pairing credentials private. See [dashboard details](docs/DASHBOARD.md) and [skin controls](docs/SKINS.md#chat-voting).

## Quick start

Requires Linux x86-64 and Python 3.11. An NVIDIA GPU is recommended for CUDA detection and NVENC encoding; `--cpu` is available with a 2.5-second default delay. See [RUN.md](docs/RUN.md) for dependencies, CPU setup and full instructions.

From the repository root, install the pinned environment, transport and models:

```sh
scripts/setup-check
scripts/m2-tools
.venv/bin/python -m models.prepare ppocr-v6-tiny ppocr-v6-small
```

For CUDA with pip-installed NVIDIA libraries:

```sh
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
export OPENCV_FOR_THREADS_NUM=1
export LD_LIBRARY_PATH="$(find "$PWD/.venv/lib/python3.11/site-packages/nvidia" -mindepth 2 -maxdepth 2 -type d -name lib -print | paste -sd :)${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export CUDA_CACHE_PATH="$PWD/.tmp/cuda-cache"
mkdir -p "$CUDA_CACHE_PATH"
.venv/bin/python -m shield.cli doctor
```

Start a local phone-to-OBS run from an attended terminal with Tailscale configured:

```sh
export SHIELD_BIND_HOST="$(tailscale ip -4)"
.venv/bin/python -m shield.cli doctor
.venv/bin/python -m shield.cli run --local-only --phone-setup
```

Pair Moblin using the private dashboard or enter the RTMP URL shown in the private terminal. In OBS, pull `rtmp://<your-tailscale-ip>:19350/shielded`. Keep that terminal off the stream.

For Twitch, bandwidth-test is the default testing mode. Output stays local until you select a publication flag. These attended commands need Infisical credentials and Twitch authorization as described in [RUN.md](docs/RUN.md#twitch-authorization-and-controls):

```sh
infisical run -- .venv/bin/python -m shield.cli login --run --host 127.0.0.1 --twitch-bandwidth-test
```

Live mode is restricted to the configured broadcaster `naie` and requires an owner-authorized, attended session with a fresh `LIVE naie` terminal confirmation:

```sh
infisical run -- .venv/bin/python -m shield.cli login --run --host 127.0.0.1 --twitch-live
```

## Results

On held-out, never-seen footage, **106 of 126 OCR-observed Latin-script text intervals stayed hidden (84%)** in an offline evaluation. Independent OCR engines (Tesseract, Apple Vision and PP-OCR) judged the output. Our 90% target (gate 1) was not met. The median masked area was **13.6%**.

See the [full held-out result and measurement limits](docs/Q-FRESH-HELDOUT-RESULT.md). This offline result does not establish live-stream privacy or latency.

<!-- v3 result added Monday -->

## Limitations

- Small or distant text is the main miss.
- Text only: landmarks and other visual location clues remain visible.
- Linux only, with NVIDIA recommended for the default GPU path.
- Experimental, not a production relay.

## Built with Codex

One Codex thread (GPT-6.1 Sol) and its Codex children wrote the code. Claude Opus conducted and reviewed each PR.

At base `e1aaf4f`: **106 commits on main, 24 merged PRs**, about **18,800 lines of Python source** and **17,400 lines of Python tests**. Line counts include blanks and comments in tracked Python files, excluding vendored licenses and historical code copies under `docs/`.

## License and attribution

See [fixture licenses and attribution](fixtures/ATTRIBUTION.md) and the [model sources, hashes and licenses](models/manifest.json).

## Technical notes and provenance

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

The live and CLI defaults use **PP-OCRv5-mobile in both lanes**, fast 8 Hz and
accurate 4 Hz. At 1280×720 input, lane widths are 640/1280 with separate detector
side caps 640/960 and static OCR tensors 352×640 / 544×960. Padding is 0.3,
before/after windows are 6/30 frames, and maximum lane ages are 6/12 frames.
Detection thresholds are 0.3 / 0.5 with unclip ratio 1.6. CPU mode keeps this
policy while selecting CPU execution, libx264, and its 2.5-second delay.

The selected V5-mobile policy's **2-judge Linux tune screen** hid **127/146
natural intervals** and **49/54 synthetic intervals**. This tune screen is not
a held-out result, realtime qualification, or a privacy pass. The earlier
[held-out result](docs/Q-FRESH-HELDOUT-RESULT.md), **106/126 natural intervals**,
used the **PP-OCRv6-small / PP-OCRv6-tiny policy**, not these V5-mobile defaults.

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

The earlier PP-OCRv6 local CPU collection on an i7-7700K with 8 logical CPUs
observed 3,598 LIVE frames in a complete 120-second steady window, 29.9833 fps,
at a 2.5-second engine delay and 378.426% observed CPU usage (one core = 100%;
partial process accounting including instrumentation). **CPU privacy is NOT
independently graded.** There were no PROTECT, HOLD or slate frames in that
window; the full archive includes protection and HOLD. These hardware-specific
observations do not establish a privacy pass or walking qualification.
[CPU mode and measurement limits](docs/RUN.md#cpu-mode)
include decoder latency, partial CPU accounting, unknowns and the failed clock
guard.

The earlier PP-OCRv6 provider comparison used 7 natural tune clips (1,050
frames, offline configuration with the accurate lane at width 1280); CPU and CUDA produced pixel-identical masks.
That comparison does not grade the current V5-mobile CPU defaults.
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
and real-video guards. The earlier V6 held-out evaluation also failed;
[its result](docs/Q-FRESH-HELDOUT-RESULT.md) is separate from the V5-mobile tune screen.

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
queue contamination receipt is joined. The earlier V6 held-out result is linked
above; this command does not establish V5-mobile held-out quality.

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

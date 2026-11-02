# IRL Shield

A privacy relay that covers readable text on street signs, storefronts, house numbers and plates in an IRL stream before the video reaches Twitch.

![Generated storefront scene, before on the left and shielded with Patch on the right](docs/images/generated-before-after.png)

Generated scene with fictional names. Before (left) and shielded with Patch (right), from the W8b demo.

## How it works

- Moblin on the phone sends RTMP over Tailscale to the Linux relay.
- The relay uses a 1-second processing buffer by default on GPU. Total delay to viewers has not been measured.
- PP-OCRv5-mobile detectors detect text for masking; some text is missed.
- Masks cover the detected text. Patch is the default; chat can vote for Bar or Patch.
- Frames that have not been checked go out protected. NVENC encodes the video, and a TLS forwarder sends it to Twitch with certificate verification.

### Why not a stream delay or an OBS blur?

A delay only buys time; someone still has to spot the sign. A fixed OBS blur covers a screen position. IRL Shield finds moving text inside the processing buffer and lets moderators interrupt output.

## Chat and mod controls

- `!shield hold`: moderators and the broadcaster can hold the stream on a privacy slate.
- `!shield resume`: only the broadcaster can release the chat hold.
- `!skin bar` or `!skin patch`: viewers vote for the mask appearance.
- `!skin lock bar` or `!skin lock patch`: moderators and the broadcaster can lock the appearance. `!skin unlock` releases it.

Hold stops further exposure; it cannot take back frames already sent. Use Hold before a known location clue enters the frame.

The private phone dashboard shows relay status and local Hold / Resume controls. Pairing with Moblin uses a QR code once the relay is installed. Keep its pairing credentials private. See [dashboard details](docs/DASHBOARD.md) and [skin controls](docs/SKINS.md#chat-voting).

## Judge quick start

### Try it locally (no Twitch)

Requires Linux x86-64, Python 3.11 and `uv` on PATH. An NVIDIA GPU is recommended for CUDA detection and NVENC encoding; `--cpu` uses CPU detection and libx264 encoding with a 2.5-second default processing buffer. See [RUN.md](docs/RUN.md) for dependencies and full instructions.

From the repository root, install the pinned environment, transport and models:

```sh
scripts/setup-check
scripts/m2-tools
.venv/bin/python -m models.prepare
```

Start the local relay from an attended terminal. This recipe uses CPU mode; omit `--cpu` for a supported NVIDIA GPU:

```sh
scripts/walk-linux --local-only --cpu --host 127.0.0.1 --venv .venv \
  --model-cache models/cache --mediamtx-dir .tmp/tools/mediamtx-v1.21.3
```

No Twitch credentials, login or publication are needed. Send video from a local RTMP source to the private camera URL shown in the terminal. In OBS, pull `rtmp://127.0.0.1:19350/shielded`. Keep that terminal off the stream.

For a phone source, configure Tailscale on the phone and relay, replace `127.0.0.1` in `--host` with the relay's Tailscale IPv4 address, and pair Moblin through the private dashboard. In OBS, pull `rtmp://<your-tailscale-ip>:19350/shielded`.

<!-- demo-source release asset link added Monday -->

### Bandwidth-test with your own Twitch app

Register your own Twitch app as a public client for device-code login. The relay reads `TWITCH_CLIENT_ID` for that app's client ID and `TWITCH_BROADCASTER_ID` for your broadcaster account's numeric user ID from the process environment. Supply your own values, then run:

```sh
export TWITCH_CLIENT_ID="<your-public-client-id>"
export TWITCH_BROADCASTER_ID="<your-numeric-broadcaster-id>"
scripts/walk-linux --twitch-bandwidth-test --cpu --host 127.0.0.1 --venv .venv \
  --model-cache models/cache --mediamtx-dir .tmp/tools/mediamtx-v1.21.3
```

Omit `--cpu` for GPU mode. `infisical run --` is an optional prefix if you store these variables in Infisical; it is not required by the code. No client secret is required.

Open the activation URL shown privately in the attended terminal and authorize as the broadcaster whose numeric ID you supplied. The requested scopes are `user:read:chat`, `moderator:read:shield_mode` and `channel:read:stream_key`. The relay validates the app and broadcaster IDs and fetches the stream key into memory. Bandwidth-test has no `naie` login restriction.

Use the same private input and OBS steps as the local run. This mode sends to Twitch ingest with `?bandwidthtest=true`; it does not create a public broadcast. See [Twitch authorization and controls](docs/RUN.md#twitch-authorization-and-controls).

## Results

The shipped **PP-OCRv5-mobile default** hid **127/146 natural intervals** and **49/54 synthetic intervals** on the **2-judge Linux tune screen**. This tune screen is not a held-out result, realtime qualification, or a privacy pass. See the [current policy and tune-screen limits](docs/RUN.md#requirements-and-installation).

The earlier **PP-OCRv6-small / PP-OCRv6-tiny policy** was evaluated on a held-out set. In that offline evaluation of six 5-second variants from three fresh licensed sources, **106/126 OCR-observed natural text intervals in Latin script stayed hidden (84%)**. Natural counts include text in both natural and synthetic variants. The synthetic control earned **14/22** hidden intervals because the Zurich variants failed the real-video check.

The median masked area was **13.6%**, with **p95 50.4%**. Tesseract and Apple Vision define natural-text truth; synthetic truth consists of all annotated visible labels, with judges checking their readability in the input. Every credible output judge counts a leak, including PP-OCR.

For that earlier V6 held-out policy, **Gate 1 failed four criteria:** natural text hidden was 84.1%, below 90%; synthetic text credited hidden was 63.6%, below 100%; both Zurich variants failed the real-video guard; and Chicago natural had exactly 2% protected frames, failing the strictly-under-2% per-clip limit.

See the [full held-out result and measurement limits](docs/Q-FRESH-HELDOUT-RESULT.md). This earlier V6 offline result does not grade the V5-mobile default or establish live-stream privacy or latency.

<!-- v3 result added Monday -->

## Limitations

- Small or distant text is the main miss.
- Text only: landmarks and other visual location clues remain visible.
- Linux only, with NVIDIA recommended for the default GPU path.
- Live Twitch mode is currently restricted to `naie`. It requires fresh authorization and an attended `LIVE naie` terminal confirmation for each owner-authorized session.
- Experimental, not a production relay.

## Built with Codex

One Codex builder thread and its Codex children wrote the code; Claude Opus conducted and reviewed the work.

At `origin/main` commit `6e5f0ee`: **113 reachable commits, including 26 PR merge commits**. Counting all lines, including blanks and comments, in tracked `.py` files outside `docs/` gives **19,809 source lines** outside `tests/` and **17,667 test lines** under `tests/`.

## License and attribution

See [fixture licenses and attribution](fixtures/ATTRIBUTION.md) and the [model sources, hashes and licenses](models/manifest.json).

## Technical notes and provenance

### Provenance notes

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

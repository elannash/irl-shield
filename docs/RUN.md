# Run IRL Shield on Linux

This is an experimental RTMP relay. The command layer connects the existing
MediaMTX ingest, two detector lanes, one masking engine and one video encoder.
The live application supports Linux only; Windows is unsupported. NVIDIA is
recommended for the default CUDA/NVENC path. `--cpu` selects CPU detection and
libx264 encoding. Mac OCR grading tools do not provide live application support.
OBS can pull the local shielded RTMP stream. Optional Twitch egress uses the
same encoded packets through a verified TLS forwarder. Bandwidth-test mode
appends `?bandwidthtest=true`; attended live mode is restricted to `naie`.

**Privacy and walking use are unqualified.** SRT is not qualified. The existing
M2 transport starts a private SRT listener, but these instructions expose only
RTMP. Doctor reports requirements and limitations; it does not certify cadence,
A/V synchronization, privacy, or walking suitability. Current integration
receipts are under `out/integration/`; missing receipts mean unverified behavior.

## Requirements and installation

Use Linux x86-64 and Python 3.11. The default GPU mode needs an NVIDIA GPU
supported by CUDA 12.4/cuDNN 9.3 and an NVENC-capable driver. CPU mode uses the
same pinned environment without requiring a GPU. The runtime is ONNX Runtime GPU
1.20.2; do not replace it with CUDA 13 on Pascal. GPU model memory and actual
30fps cadence must be verified on the target machine.

Install into a checkout-local environment; no sudo, account, global package or
system-service changes are needed. `uv` may substitute for `python -m venv` and
pip when already available:

```sh
scripts/setup-check
# Or: python3.11 -m venv .venv
#     .venv/bin/python -m pip install -r requirements-check-linux.txt
scripts/m2-tools
.venv/bin/python -m models.prepare ppocr-v6-tiny ppocr-v6-small
```

See `python -m models.prepare --help` for the model provisioning interface.
Model source, revision, SHA-256 and licenses are in `models/manifest.json`.
MediaMTX v1.21.3 is MIT and hash checked by `relay/mediamtx.py`; `scripts/m2-tools`
fetches only that release into this checkout's `.tmp/tools/`. PyAV 16.0.1 is
BSD-3-Clause; its Linux wheel's bundled FFmpeg includes GPL components. CUDA,
cuDNN, ONNX Runtime, OpenCV and model license details are in
[bench/PORTABILITY.md](../bench/PORTABILITY.md),
[relay/README.md](../relay/README.md), and
[shield/twitch/LICENSES.md](../shield/twitch/LICENSES.md).
pyTwitchAPI 4.5.0 and optional keyring 25.6.0 are MIT; the committed M3 dependency
inventory covers their transitive licenses. The integration adds no library beyond these existing runtime dependencies.
`shield/app/requirements.txt` pins the Python 3.11 overlay, with exact metadata
and source/license links in `shield/app/DEPENDENCIES.json`.

For the default CUDA path with pip-installed NVIDIA libraries, expose their
private library paths before starting Python. CPU mode can use the launcher
below without this NVIDIA library-path setup:

```sh
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
export OPENCV_FOR_THREADS_NUM=1
export LD_LIBRARY_PATH="$(find "$PWD/.venv/lib/python3.11/site-packages/nvidia" -mindepth 2 -maxdepth 2 -type d -name lib -print | paste -sd :)${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export CUDA_CACHE_PATH="$PWD/.tmp/cuda-cache"
mkdir -p "$CUDA_CACHE_PATH"
.venv/bin/python -m shield.cli doctor
```

## CPU mode

`--cpu` explicitly selects ONNX CPUExecutionProvider for both the fast and
accurate lanes and libx264 encoding with the existing ultrafast/zerolatency
settings. It uses the CPU provider in the pinned onnxruntime-gpu distribution;
do not install a second onnxruntime package into that environment. The launcher
skips the NVIDIA library-directory requirement, hides CUDA devices and retains
its existing environment isolation and exclusive lease.

CPU mode defaults to a 2.5-second engine presentation delay.
`--delay-seconds N` overrides the delay in either mode and accepts only finite
values from 0.5 through 10 seconds inclusive, without clamping. The 0.5-second
lower bound is a privacy floor that gives asynchronous detections time to
arrive; it does not guarantee privacy across all scenes and processing latencies.
The 10-second upper bound limits delay-related frame and audio buffer growth.
This delay is only one component of end-to-end latency. Without CPU or delay
flags, the existing CUDA/NVENC path and 1-second engine delay remain unchanged.
Both modes retain fast 8 Hz, accurate 4 Hz, widths 640/960, an accurate box confidence floor of
0.5, and 1280 by 720 output at 30 fps. Configured cadence is not measured output.
Patch appearance, chat PatchBar, authentication, publication approval and HOLD
behavior are unchanged. The direct CLI accepts these options on `run` or
`login --run`.

From the repository root after installation, start an attended local run:

```sh
scripts/walk-linux --local-only --cpu --host 127.0.0.1 --venv .venv \
  --model-cache models/cache --mediamtx-dir .tmp/tools/mediamtx-v1.21.3
```

For a phone connection, use the machine's own Tailscale IPv4 address with
`--host` as described below. To change the engine delay, append, for example,
`--delay-seconds 3`. This local mode performs no Twitch login or publication.
Existing authorization and terminal confirmation still apply when selecting a
Twitch publication mode.

The attended command above runs CPU mode without NVENC, generated plates or a
W8b clip. For a bounded CPU reproduction, append `--seconds 230` and send input
from an attended phone over Tailscale, or from a local RTMP broadcaster UI with
`--local-only --host 127.0.0.1`. Enter the runtime camera URL only in the private
broadcaster UI, using the existing private dashboard or `/dev/tty` phone setup.
Keep credentials out of command arguments, logs, receipts and fixtures. Read the
shielded output in OBS as described below; no Twitch credentials or publication
are needed for this local reproduction.

Replaying the measured W8b source is optional. Its clip build needs NVENC and
cached generated plates, as described in
[DEMO-RENDERER.md](DEMO-RENDERER.md#w8b-opt-in-richer-source); that build and clip
are not required to run CPU mode. With that source already prepared, use fresh
output paths:

```sh
scripts/walk-linux --local-only --cpu --host 127.0.0.1 --venv .venv \
  --model-cache models/cache --mediamtx-dir .tmp/tools/mediamtx-v1.21.3 \
  --seconds 230 --demo-source out/w8b/render-01/source.json \
  --demo-receipt out/cpu-collection/sender.jsonl --archive out/cpu-collection/relay
```

This uses the production local sender and its prepared 30 fps, 210-second
source. It adds no detector cadence override. An archive records effective lane
rates, confidence floors and providers under `runtime.json.configuration.lanes`,
plus `configuration.encoder` and `configuration.delay_seconds`. Those fields
describe the effective configuration, not a privacy score or achieved throughput.

### Observed CPU collection and limits

**CPU privacy is NOT independently graded.** Root builder inspection of saved
CPU native unit 2 output found the engraved **NERALIN LANE** plaque readable
and unmasked at source frame 2700. GPU native unit 26 output also intermittently
missed this plaque; these observations do not establish a provider regression.
This is an observed detection miss, with no detector tuning in this change.

A separate frozen offline provider check used the same source weights and graphs,
changing only CPUExecutionProvider versus CUDAExecutionProvider. Across seven
natural clips with 150 frames each (1,050 frames total), CPU and CUDA masks were
pixel-identical. Every clip had mask IoU p50/minimum 1.000, zero unmatched
provider detections, and CPU-minus-CUDA mask-area p50/p95 deltas of 0 percentage
points. The CUDA replay matched the previously graded baseline125 path exactly,
including all 71 empty, 43 full and 936 nontrivial mask frames.

This comparison used an offline 1-second delay and accurate width 1280, rather
than native CPU mode's 2.5-second delay and accurate width 960. It establishes
provider parity for that frozen offline setup; it does not independently grade
CPU privacy or qualify native privacy, W5, performance or walking use. The
native NERALIN LANE miss above remains. The root-inspected provider-parity
receipt is identified by SHA-256
`af536e062e88ef22157d2504154097032d313eb91e9428ab012d7a0664a754e6`.

The root-inspected local collection on November 1, 2026 UTC used an Intel i7-7700K
at 4.20 GHz with 8 logical CPUs, the GPU hidden, native threads set to 2 and
OpenCV threads set to 1. Both lanes reported CPUExecutionProvider, encoding was
libx264 and the engine delay was 2.5 seconds. The source base was `8f12891` with
the CPU patch; documentation on a newer base does not imply another native run.
These observations are specific to that machine and source, not universal
minimum hardware requirements.

The complete 120-second steady window contained 3,598 independently decoded
LIVE arrivals, 29.9833 fps, with zero PROTECT, HOLD or slate frames and no
unidentified source/output rows in that decoder window. Latency from local
sender mux start to independent decoder arrival was:

| Statistic | Seconds |
| --- | --- |
| p50 | 2.674 |
| p95 | 2.685 |
| p99 | 2.692 |
| Maximum | 2.771 |

All 3,598 of 3,598 decoder arrivals were identified for these quantiles. The
separate encoder-handoff latency series identified 3,537 of 3,598 rows and left
61 unknown; it is not the independent-decoder series. The prior clock guard
remains FAILED at 2.067 ms against its 1.5 ms limit. These latency observations
are descriptive, not a W5 pass, a phone measurement or a guaranteed latency.

Observed CPU usage was 378.426%, with one core equal to 100%. Accounting was
partial, using adjacent common-member process deltas and including measurement
instrumentation. It is not a total-host CPU measurement or complete application
process accounting.

The whole archive was not slate-free. Its 6,817 handoff rows contain 6,130 LIVE,
72 PROTECT and 615 HOLD frames, including 687 slates. Full-archive output/source
identity unknown counts are 667/775. The independent full decoder has 6,757
arrivals, with 6,130 LIVE, 19 PROTECT, 72 HOLD and 536 unknown states; 91 are known
slates and 536 have unknown slate status. Its output/source identity unknown
counts are 536/603. These full-run denominators and unknowns remain in the
receipt; the steady window does not replace them.

There were zero retained warnings and 76 diagnostic drops. That does not prove
warning absence. The collection did not rerun CPU privacy/tune grading or change
the frozen default detector policy, and it does not qualify walking use. The
root-inspected acceptance receipt is identified by SHA-256
`7472eacfe52f08bc64a049b2611caebc257abf1fd84b6ddfb931ba33dfe91a20`.

## Local phone to OBS

Start this from an attended terminal. `--phone-setup` writes runtime publish
credentials to `/dev/tty`, never stdout/stderr, files or process arguments.
Do not record or share that terminal. Supply an explicit bind with `--host` or `SHIELD_BIND_HOST`: IPv4 loopback
(`127.0.0.1`) for a local run, or your own Tailscale IPv4 address in
`100.64.0.0/10` for a phone. Wildcards, public/LAN addresses and IPv6 are rejected.
`doctor` reports `tailscale_ipv4` or the explicit value `unavailable`. If unavailable,
use loopback for local testing; a phone connection requires Tailscale on the host.
For a configured Tailscale host:

```sh
export SHIELD_BIND_HOST="$(tailscale ip -4)"
.venv/bin/python -m shield.cli doctor
.venv/bin/python -m shield.cli run --local-only --phone-setup
```

Enter the displayed private RTMP URL in the phone broadcaster. Add an OBS media
source with URL `rtmp://<your-tailscale-ip>:19350/shielded`. On the same machine use
`rtmp://127.0.0.1:19350/shielded` when explicitly running with `--host 127.0.0.1`.
Ingest is restricted to the `camera` path and random runtime publish
credentials. Only internal credentials may read raw `camera` or publish
`shielded`. Viewers can read only the shielded path. No wildcard listener,
firewall rule, recording service or public host is configured by this command.
Nothing is archived by default: no encoded video, frame log or runtime JSON.
Use `--archive out/my-session` to opt into the full encoded archive and diagnostic
evidence. This can grow for the duration of the session. Before every evidence
write a 128 MiB free-space guard leaves room for the OS/operator; low space or
an I/O error permanently disables that writer's evidence, while relay output
continues. Evidence may therefore be partial. No disk policy changes the engine
or turns a transport failure into a diagnostic success.

M2's bounded egress recovery replaces a stalled writer after reaping its old
worker, asserts an independent egress HOLD, and waits for fresh engine output
and network readiness before releasing that guard. Manual and EventSub holds
remain independent. Recovery can leave honest frame/PTS gaps; it is not a
cadence guarantee. A dedicated writer owns a single replaceable pending frame, so a blocked
destination never blocks draining ingest. Frames are dropped rather than replayed;
HOLD is checked again at the actual encoder handoff. Frames already inside native
encoding cannot be retracted. Generation archives and recovery events are saved
only with `--archive`. Retries use exponential delays from 0.5 to 8 seconds plus
0–20% positive jitter. A continuous outage ends the relay only after at least
60 seconds and five failures; a network-ready ACK resets the outage budget.
OBS and Twitch still share one encoding/mux worker: either destination failing
interrupts both outputs. This change does not claim destination isolation.

SIGINT/Ctrl-C and SIGTERM stop this process and its owned media processes.
For manual HOLD, send SIGUSR1 to this run's PID. SIGUSR2 releases only the manual
hold; it cannot release an EventSub, transport or Shield Mode hold. `--hold`
starts with manual HOLD already asserted. `--seconds N` bounds a run.

## Twitch authorization and controls

Twitch client and broadcaster IDs are read by name from Infisical-injected
`TWITCH_CLIENT_ID` and `TWITCH_BROADCASTER_ID`. A public-client device login uses
the existing approved scopes; stream keys are fetched from Helix in memory.
Do not supply tokens, refresh tokens or stream keys in command arguments.

The following is an **attended, separately authorized recipe**. It was not run
against Twitch during integration testing:

```sh
infisical run -- .venv/bin/python -m shield.cli login --run --host 127.0.0.1 --phone-setup
```

The activation URL is shown only on `/dev/tty`. The token, refresh token and
stream key stay in this process's memory by default. `login` without `--run`
validates then exits, discarding that session. `login --run` continues into the
relay with the same session. `run` also performs login when required. Optional
`--remember` uses M3's secure OS keyring only; it refuses plaintext backends.
No stream key is stored there. The integration does not provision a keyring.

After EventSub reconciliation, moderators and broadcaster may send
`!shield hold`; only the broadcaster may send `!shield resume`. Shield Mode
begin/end controls a separate hold. Connection loss asserts its own hold and
reconciliation preserves manual and newer event holds. HOLD overrides PROTECT,
which overrides LIVE. The same event policy object survives reconnects, keeping
its replay barriers.

Twitch publication requires one explicit, mutually exclusive mode:

- `--twitch-bandwidth-test` sends to test ingest with `?bandwidthtest=true`.
- `--twitch-live` sends live only after fresh token validation identifies the
  exact broadcaster login `naie`, then the owner confirms `LIVE naie` on an
  attended `/dev/tty`. `nale` and every other login are refused. This approval
  lasts for one runtime session and cannot be saved or reused.

Start live publication only in an owner-authorized, attended session.
A stored login or key never turns publication on.
Omit both publication flags to retain authenticated EventSub controls and
local OBS output without publishing. `--local-only` instead disables Twitch
login and controls, and cannot be combined with `login`.

The attended recipes below are external writes requiring their own authorized
session. They have **not** been run as part of local verification:

```sh
# The owner qualifies real ingest acceptance with this attended test first.
infisical run -- .venv/bin/python -m shield.cli login --run --host 127.0.0.1 --twitch-bandwidth-test
# During an owner-authorized, attended live session:
infisical run -- .venv/bin/python -m shield.cli login --run --host 127.0.0.1 --twitch-live
```

The runtime creates one standard-library forwarder on `127.0.0.1` at an
OS-selected port. PyAV writes plain RTMP to that listener; the forwarder
completes TLS verification before forwarding any RTMP bytes to
`live.twitch.tv:443`. `ssl.create_default_context()` supplies system CAs,
`check_hostname=True` and `CERT_REQUIRED`; `server_hostname` is the ingest
hostname. This avoids the pinned PyAV output API's ignored TLS options.
No direct RTMPS destination or unverified fallback remains in the runtime.
TLS/verification failures close the local connection and enter the existing
egress recovery path. The listener accepts replacement writer connections.
The key never appears in process arguments, logs, receipts or archives.

The [live guard](LIVE-GUARD.md) and [forwarder evidence](LIVE-EGRESS.md) describe
synthetic loopback verification, including CA/hostname rejection and the
verification-disable mutation. The [earlier TLS investigation](PR5-TLS-FOLLOWUP.md)
remains a historical record of the direct PyAV defect, not an available runtime
route. Those automated checks use no Twitch connection or real stream key.

### Attended bandwidth observation — October 30, 2026

In session `attended-naie-bandwidth-2026-10-30`, the owner approved the `naie`
device login and ran `scripts/walk-linux --twitch-bandwidth-test` from a clean
checkout at `cd20792`. The conductor observed an established TLS connection
through the verified forwarder to Twitch on port 443. Acknowledged bytes grew
from approximately 1.23 MB to 1.48 MB over eight seconds of privacy-slate output.
The run exited cleanly at 22:43:56 PT: MediaMTX stopped, the connection closed,
and the canonical exclusive lease was released.

This attended observation establishes that Twitch accepted the loopback
`tcUrl` (`rtmp://127.0.0.1:<port>/app`) through that forwarder with the key held
in memory. It is not an automated test or a qualification of live-video FPS,
privacy effectiveness, phone latency, audio or SRT. Future live publication still
requires the separate attended authorization described above.

## Local integration verification

The conductor-approved gate uses the actual pyTwitchAPI transport against an
IPv4-loopback aiohttp OAuth/Helix/EventSub mock. All identities, labels and
flash/beep media are synthetic; no external user records or natural fixtures
are used. Native CUDA/NVENC runs go through the root's perf queue with inherited
canonical EX lease, forced/contended accounting, and retained artifacts.
Untimed functional gates take the canonical SH lock after root coordination. `out/integration/timed-jobs.json` records literal argv and
expected receipts for this task. Do not manually rerun these native jobs while
the queue is active, and do not acquire a nested perf lock inside them.

`scripts/check` is the single functional/compile gate. Provision a Python 3.11
venv using `requirements-check-linux.txt` on Linux or
`requirements-check-mac.txt` on macOS, then run `scripts/check`. Set
`SHIELD_PYTHON=/absolute/path/to/private/venv/bin/python` for a private `.tmp/`
environment; otherwise it uses `.venv/bin/python`. It removes `PYTHONPATH` to
prevent site-package stacking, checks all native imports up front, and refuses
conflicting CPU/GPU ONNX Runtime distributions. Use only the appropriate
platform requirements; never install CPU ORT beside Linux ORT GPU.

On Linux, provision the hash-pinned MediaMTX with `scripts/m2-tools` before
running the gate; M2 recovery tests use its real loopback transport. Those
Linux-native fixtures report their platform skip on macOS.

The gate runs all main, M2, M3 and integration tests in one process and compiles
project Python sources. It prunes `.venv*` directories and environments marked
by `pyvenv.cfg`, so another interpreter’s installed packages are not parsed as
project source. It reports discovery and skip counts. macOS also builds the
Apple Vision Swift bridge. Linux explicitly reports that platform omission.
External Twitch and Q/held-out quality grading stay outside this local gate.

**Native Twitch CLI integration is NOT RUN BY DESIGN (local-only boundary).**
The conductor selected this contract because pinned Twitch CLI 1.1.24 opens
wildcard RPC port 44747 and does not generate chat. No patched CLI, namespace,
SDK or service configuration is used. M3 protocol receipts already merged in
PR2 at `54740e192a62e08c4179f344af2ebb290fff6648` are recorded in
[PROTOCOL.md](../shield/twitch/PROTOCOL.md),
[R3-HANDBACK.md](../shield/twitch/R3-HANDBACK.md), and
[LOG.md](../shield/twitch/LOG.md); the committed handbacks identify retained
native CLI evidence, including `/tmp/agents/irl-shield/m3-twitch/15-cli-probe.log`
and `cli-server.log`. This exclusion is not a claim that the integration ran
that tool.

Native assertions require independently decoded local network pixels and PTS,
including actual non-slate video. Unit tests or an all-slate output cannot
establish native privacy, cadence or HOLD latency. A measured result failing
an assertion stays failed; ordinary functional success does not override it.
No clip or still is designated demo-ready by these instructions.

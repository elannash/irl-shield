# Run IRL Shield on Linux

This is an experimental RTMP relay. The command layer connects the existing
MediaMTX ingest, CUDA detector lanes, one masking engine and one NVENC encoder.
OBS can pull the local shielded RTMP stream. Optional Twitch egress uses the
same encoded packets and always appends `?bandwidthtest=true`.

**Privacy and walking use are unqualified.** SRT is not qualified. The existing
M2 transport starts a private SRT listener, but these instructions expose only
RTMP. Doctor reports requirements and limitations; it does not certify cadence,
A/V synchronization, privacy, or walking suitability. Current integration
receipts are under `out/integration/`; missing receipts mean unverified behavior.

## Requirements and installation

Use Linux x86-64, Python 3.11, an NVIDIA GPU supported by CUDA 12.4/cuDNN 9.3,
and an NVENC-capable driver. The CUDA runtime is pinned to ONNX Runtime GPU
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

If using pip-installed NVIDIA libraries, expose their private library paths
before starting Python:

```sh
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
export OPENCV_FOR_THREADS_NUM=1
export LD_LIBRARY_PATH="$(find "$PWD/.venv/lib/python3.11/site-packages/nvidia" -mindepth 2 -maxdepth 2 -type d -name lib -print | paste -sd :)${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export CUDA_CACHE_PATH="$PWD/.tmp/cuda-cache"
mkdir -p "$CUDA_CACHE_PATH"
.venv/bin/python -m shield.cli doctor
```

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

To publish to Twitch test ingest, the owner must separately authorize that
session and add `--twitch-bandwidth-test`. This is an external publish even
though viewers cannot watch it. It is never part of the local verification
recipe. There is no live-publish flag. Twitch documents the RTMP URL and query
parameter in [Video Broadcast](https://dev.twitch.tv/docs/video-broadcast/).
The destination uses `rtmps://live.twitch.tv:443/app/` with the memory-only key
and mandatory `?bandwidthtest=true`. The pinned Linux PyAV/FFmpeg SDK enumerates
RTMPS and TLS output protocols. Twitch also publishes secure URL templates in
[its ingest catalog](https://ingest.twitch.tv/ingests). No Twitch connection was
made to qualify this endpoint; real Twitch device login and platform behavior
remain an attended check.

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

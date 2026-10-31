# Saturday Linux walk launcher

`scripts/walk-linux` starts the existing `python -m shield.cli run` entrypoint
from one isolated Python 3.11 venv, under the canonical Linux exclusive lease.
Run it from an attended terminal. Choose exactly one publication mode on every
invocation; there is no default.

```sh
# Local phone → shielded OBS output, with no Twitch login or connection:
scripts/walk-linux --local-only

# Only during the owner's authorized, attended Saturday/Sunday session:
infisical run -- scripts/walk-linux --twitch-live
```

LIVE retains the existing fresh validation of the exact broadcaster `naie` and
requires typing `LIVE naie` on `/dev/tty`. `TWITCH_CLIENT_ID` and
`TWITCH_BROADCASTER_ID` come from Infisical. This launcher does not request new
scopes, fetch a key, save a login, or remember approval. Tokens and the runtime
stream key remain in the existing CLI's memory. Development verification must
use `--local-only`; it does not connect to Twitch.

The launcher always enables phone setup and the private dashboard. Phone RTMP
credentials, the dashboard invitation and LIVE confirmation use the existing
`/dev/tty` path. Keep this terminal private: do not record it, redirect it into a
receipt, or share its contents. Nothing is archived by the launcher.

## Existing private installation

Provisioning remains separate; the launcher installs and downloads nothing.
Use the existing Python 3.11 environment containing all exact pins declared by
`requirements-check-linux.txt` and its nested requirements. Select its **venv
directory**, not its Python executable:

```sh
export SHIELD_WALK_VENV=/absolute/path/to/private/venv
scripts/walk-linux --local-only \
  --model-cache /absolute/path/to/existing/models/cache \
  --mediamtx-dir /absolute/path/to/existing/mediamtx-v1.21.3

# --venv overrides SHIELD_WALK_VENV; default is this checkout's .venv.
scripts/walk-linux --local-only --venv /absolute/path/to/private/venv
```

The initial stdlib bootstrap disables site initialization with `-I -S -B` so
site hooks cannot import native packages before the lease. It re-executes the
selected interpreter with `-I -B -u`, disables inherited
Python overlays, requires `include-system-site-packages = false`, rejects
external `sys.path` entries and conflicting CPU ONNX Runtime, and checks every
declared package version from installed metadata before importing OpenCV or the
CLI. The checkout is added only after those checks. This verifies installation
consistency; native CUDA inference and NVENC encoding need their own probe.

`LD_LIBRARY_PATH` is replaced with the selected venv's private NVIDIA wheel
library directories. Inherited `LD_PRELOAD` and CUDA library paths are removed.
The declared Linux pins retain ORT GPU 1.20.2 / CUDA 12.4 / cuDNN 9.3 for Pascal.
Native thread pools are limited to two and OpenCV to one; core dumps are disabled
and the process runs at niceness at least 10. The only launcher-created runtime
cache is `.tmp/walk/cuda-cache`. Model files and the hash-pinned MediaMTX binary
are read from the supplied directories; no model is copied or provisioned.

## Private phone connection

The host is `--host`, then `SHIELD_BIND_HOST`, then the machine's
`tailscale ip -4` result. Missing Tailscale fails closed. The automatic result
must be in `100.64.0.0/10`. Explicit binds accept a Tailscale IPv4 address or
`127.0.0.1`; wildcard, public, LAN and IPv6 addresses are refused. An explicit
Tailscale address must belong to this machine for the underlying listener to
bind successfully.

Use the displayed private **RTMP** camera URL in the phone broadcaster, and open
the dashboard invitation on the phone over Tailscale. OBS reads the `shielded`
RTMP path described in [RUN.md](RUN.md). SRT remains unqualified; the existing
runtime also starts its private SRT listener, and this wrapper does not change
that transport behavior. Do not use SRT for the walk.

For root's bounded loopback verification:

```sh
scripts/walk-linux --local-only --host 127.0.0.1 --seconds 15 \
  --venv /absolute/path/to/private/venv \
  --model-cache /absolute/path/to/existing/models/cache \
  --mediamtx-dir /absolute/path/to/existing/mediamtx-v1.21.3
```

Named options also include `--rtmp-port`, `--rtsp-port`, `--srt-port` and
`--dashboard-port`. Relay ports must be 1024–65535; dashboard port 0 selects a
free port. `--seconds` must be positive and finite. Arbitrary CLI forwarding,
remembered credentials, archive output, mock controls and bandwidth-test mode
are deliberately absent from this attended launcher.

## Lease and stopping

Every SDK/native import and relay operation occurs after the canonical physical
`/tmp/agents/irl-shield/perf.lock` EX lease is held. A root queue may pass its
existing descriptor through `IRL_SHIELD_PERF_QUEUE_LEASE_FD`; `scripts/host-lock`
also preserves a descriptor without that variable. The bootstrap verifies its
actual device/inode and the kernel's per-descriptor `FLOCK ADVISORY WRITE`
record. Environment presence is insufficient. It never acquires a second lock
when reusing a verified lease. Otherwise it attempts EX directly and refuses a
busy host; it does not enqueue another runner or wait behind root's other work.
There is no skip-lock option or test lock-path option on the executable.

The verified FD survives interpreter exec. The CLI runs in that lease-owning
process, preserving its attended terminal and SIGINT/SIGTERM handlers. Ctrl-C
or SIGTERM uses the existing CLI shutdown, which waits for its engine, dashboard
and owned media processes before releasing the lease. Do not kill other lanes,
relay processes or root's runner. SIGKILL cannot run Python cleanup and is not a
graceful stop.

A refused bootstrap exits 2 with a fixed diagnostic. Missing requirements mean
repair/provision the selected venv separately; they never trigger an install or
a fallback interpreter. See [RUN.md](RUN.md) for underlying runtime requirements.

## Qualification

This is a launch wrapper. Privacy, walking suitability, 30 fps cadence, A/V
synchronization and real Twitch ingest acceptance remain separate qualifications.
A dashboard or an all-slate output does not prove readable text was protected.
The implementation hand-back carries root-only focused, native and full-gate
execution packets; absent root receipts, those layers remain unverified.

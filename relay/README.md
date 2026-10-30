# M2 Linux relay

This lane adds a continuous MediaMTX → loopback RTSP/TCP → shared
`MaskingEngine` → hardware encoder → MediaMTX transport. The engine owns every video pixel presented to
egress. Transports own source timestamps, fixed output shape and delayed audio.
The existing Mac NUT experiment remains in `relay.run`; this new launcher is
Linux-only. Native acceptance results are recorded in `M2-HANDBACK.md`.

The initial profile is **unqualified**: Tiny 8 Hz/640, Small 4 Hz/960, D=1 s,
phase correlation width 320/floor .05, padding .3, B=6/A=30. Root's Q work may
replace it. No pooled bench result qualifies this relay, and a slate-only
output cannot pass the privacy/real-video gate.

## Install and run

Python 3.11, the existing NVIDIA driver and public downloadable CUDA 12.4
runtime wheels are required on the Pascal host. No sudo, global CUDA changes,
account or paid service is used. Set up in the T3 agents slice:

```bash
systemd-run --user --scope --slice=app-t3code-agents.slice nice -n 10 scripts/m2-setup-linux
```

For this shared machine, the already pinned GPU environment can instead be
reused read-only. Only PyAV is installed in this lane's private environment:

```bash
M2_GPU_SITE=/home/elan/code/irl-shield/.tmp/linux-probe/.venv/lib/python3.11/site-packages \
  systemd-run --user --scope --slice=app-t3code-agents.slice nice -n 10 scripts/m2-setup-linux
```

Download the two detector files with the repository's existing model setup,
or pass its already verified model cache. The manual phone-setup command is:

```bash
scripts/host-lock exclusive systemd-run --user --scope --slice=app-t3code-agents.slice \
  scripts/m2-live --model-cache /home/elan/code/irl-shield/models/cache \
  --host 127.0.0.1 --archive .tmp/m2/manual-session --phone-setup
```

This explicit interactive-terminal action displays runtime-generated phone
credentials once. Do not redirect, record or save that terminal. Automated
runs omit `--phone-setup` and never print credentials. Listeners require an explicit `--host` or `SHIELD_BIND_HOST`: IPv4 loopback or
a Tailscale address in `100.64.0.0/10`, on ports 19350 (RTMP) and 18890 (SRT).
`python -m shield.cli doctor` reports the detected Tailscale IP or `unavailable`.
The sole internal reader uses TCP RTSP on `127.0.0.1:18554`, protected by the
internal credential. RTSP UDP/multicast transports are disabled. Phone
publication over either RTMP or SRT converges on this reader.
`--host 127.0.0.1` selects local-only operation. No wildcard or IPv6 binding is
allowed. Port conflicts fail startup; an incumbent process is never stopped.

Moblin publishes to `camera`; phone credentials grant no read permission and
cannot publish to `shielded`. OBS pulls `rtmp://<your-tailscale-ip>:19350/shielded`
or `srt://<your-tailscale-ip>:18890?streamid=read:shielded`. Only the internal
runtime credential can publish protected output. Other listeners, recording,
anonymous publication and publisher replacement are disabled.

Ctrl-C stops owned transports and workers. `--seconds N` bounds a run.
MediaMTX config travels over stdin, never a credentialed disk file or argv.
Credentialed libav text is suppressed. MediaMTX stdout/stderr is consumed in
memory and reduced to a bounded ring of fixed close codes; raw lines are never
persisted. Read/write connection timeouts are 10 seconds, matching the pinned
MediaMTX defaults. The engine deadlines govern protection independently of
these connection timeouts. Camera, OBS and Twitch secrets never belong in artifacts.

## M3 integration

Call `relay.runtime.run(..., control_ready=register_callbacks)` inside the same
process. `register_callbacks(control)` receives:

```python
control.hold(True, source='twitch-chat', reason='moderator')
control.hold(False, source='twitch-chat', reason='moderator')
control.hold(True, source='eventsub', reason='shield-mode')
control.set_stream_key(ephemeral_key)
control.set_stream_key(None)
```

Source names are `local`, `twitch-chat`, or `eventsub`; reasons are `manual`,
`moderator`, `shield-mode`, or `synthetic hold`. Map incoming chat/EventSub
events to this vocabulary; do not send raw chat text as reasons. Each source
owns its hold. A reconnect clears only the transport hold.

The application controls acquire the stream key through the authorized Helix
flow and install it in memory. The runtime sends that destination to the sole
encoder worker through a private spawn pipe only when `publish_twitch=True`
(the CLI flag is `--twitch-bandwidth-test`). A configured key alone never forms
a Twitch destination. The route is RTMPS on port 443 with mandatory
`?bandwidthtest=true`; it is an external publish requiring separate session
authorization. No live-publish override exists. Keys never enter argv, logs,
archives or the OS keyring; removal is explicit. No Twitch request was run here.

The pinned Linux RTMPS output does **not** verify the peer certificate or
hostname. An active MITM can impersonate Twitch and capture the stream key;
memory-only storage and bandwidth-test mode do not prevent that attack.
PyAV 16.0.1's primary output open bypasses the protocol options needed to
enable verification in its bundled FFmpeg/GnuTLS backend. Keep Twitch egress
off and use local-only operation while this remains unresolved. The
[TLS follow-up](../docs/PR5-TLS-FOLLOWUP.md) contains the source receipts and
loopback publication/control results. No transport security fix is claimed.

## Evidence and limits

Cold startup seeds the shared engine with a black frame at the configured
shape/PTS and a transport hold. Even the initial slate crosses `engine.poll`.
Engine coverage protects missing frames or stalled lanes. Continuous native
cadence under host contention is not yet qualified; the diagnostic pilot had
multi-second gaps. Encoded monotonic timestamps and egress acknowledgement
timing are recorded for the requalification runs. Reconnecting source timestamps are rebased onto the
same monotonically increasing frame clock. No source-pixel fallback exists.

Decoded input uses an eight-event queue and the engine's own bounded frame
buffer. Audio uses a bounded PCM ring; missing/late/out-of-window samples
become silence and increment counters. Each output frame carries 1,600 mono
48 kHz samples at the matching PTS. Encoded AAC priming and native transport
effects must be measured with the flash/beep fixture; timestamp math alone
does not establish A/V sync.

Archives are off by default. `--archive <dir>` opts in; below 128 MiB free or
on a disk I/O error, diagnostics stop while the relay continues. The encoder
uses a startup fragment bounded to 1 MiB in memory even without an archive.
Opt-in `encoded.flv`, `frames.jsonl` and `runtime.json` describe actual encoded
packets, PTS, per-frame protection/coverage, compressed masks, pixel/PCM hashes
and bounds. An independent native capture is needed to prove network egress.
Root's corrected independent-family OCR grades sealed captures after PR1
merges; this lane never grades itself with the detector's PP family alone.
Existing licensed footage and all its derivatives are **benchmark-only**,
without music, and are not demo-ready.

Timed/20-minute jobs go through root's fresh `scripts/perf-queue` session and
inherit its exclusive lease; never wrap a queue-owned job in another lock.
Short untimed functional checks take the canonical shared host lock; timed jobs
take it exclusively. A dedicated egress writer retains only one replaceable
pending frame and never backpressures ingest. Reconnect delays grow from 0.5
to 8 seconds plus positive jitter, with a minimum 60-second continuous outage
budget. OBS and Twitch still share failures in one native worker.

## Dependencies and licenses

- [MediaMTX v1.21.3](https://github.com/bluenviron/mediamtx/releases/tag/v1.21.3),
  [MIT](https://github.com/bluenviron/mediamtx/blob/v1.21.3/LICENSE).
  `scripts/m2-tools` verifies both the pinned archive and binary SHA-256 before
  use. Downloads live only in `.tmp/tools/`; no daemon or global config.
- [PyAV 16.0.1](https://github.com/PyAV-Org/PyAV/tree/v16.0.1), BSD-3-Clause.
  The installed Linux wheel bundles FFmpeg and GPL components including
  libx264. The LGPL-only description is insufficient for this wheel; FFmpeg
  GPL-2.0-or-later and component notices apply alongside PyAV BSD-3-Clause.
  No native binary is committed or redistributed by this lane. See
  [FFmpeg legal](https://ffmpeg.org/legal.html) and
  [x264 COPYING](https://github.com/mirror/x264/blob/master/COPYING).
- Existing ONNX/CUDA/OpenCV/NumPy/model pins and licenses remain in
  [PORTABILITY.md](../bench/PORTABILITY.md), `models/manifest.json`, and
  `models/licenses/dependencies.json`. No new detector or model is introduced.
- The optional native ACL probe calls the preinstalled
  [libsrt 1.5.4](https://github.com/Haivision/srt/tree/v1.5.4) C ABI,
  MPL-2.0 with BSD portions. It records the library SHA-256 at runtime and
  installs or redistributes nothing. System notices:
  `/usr/share/doc/libsrt1.5-gnutls/copyright`.

Primary transport/auth references:
[MediaMTX config](https://github.com/bluenviron/mediamtx/blob/v1.21.3/mediamtx.yml),
[authentication](https://mediamtx.org/docs/features/authentication),
[RTMP](https://mediamtx.org/docs/publish/rtmp),
[SRT](https://mediamtx.org/docs/publish/srt).

## Queued acceptance

The original session-1 results are sealed red and retained. Session 2 is
`/home/elan/code/irl-shield/.tmp/irl-shield-builder-m2-queue-2`; its diagnostic
pilot exposed `network-mux` / `BrokenPipeError` and was contended. A local
four-second publisher gap reproduced the three-second MediaMTX timeout, then
passed with the ten-second default. The RTMP and SRT A/V requalification jobs
are submitted; exact argv is in `.tmp/m2/session2-av-commands.json`. The queue
remains unsealed pending their results and final soak/read-ACL submissions.
Root owns the runner and stop command. Submission is not a native pass.

For a fresh queue/run directory, pass the existing pinned GPU library paths
in the queued command's scoped environment, and invoke the private Python
interpreter directly with `-m relay.soak`. The harness validates the inherited
canonical exclusive lease, keeps every failed run, and prints the seal digest
for the conductor to retain outside the artifact directory. Root grades each
sealed capture once using the corrected independent-family scorer after PR1
merges. `python -m relay.seal DIRECTORY --expected-sha256 RETAINED_DIGEST`
verifies the frozen file inventory and bytes before grading.

The direct RTMP-reader crash is preserved as a known PyAV 16.0.1 issue in
`M2-HANDBACK.md`; the live decoder uses the one loopback RTSP/TCP path. The
RTSP/TCP read does not expose another Tailscale-facing listener.

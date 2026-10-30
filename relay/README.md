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
  --artifacts .tmp/m2/manual-session --phone-setup
```

This explicit interactive-terminal action displays runtime-generated phone
credentials once. Do not redirect, record or save that terminal. Automated
runs omit `--phone-setup` and never print credentials. The default listeners
are `100.109.49.77:19350` (RTMP) and `100.109.49.77:18890` (SRT).
The sole internal reader uses TCP RTSP on `127.0.0.1:18554`, protected by the
internal credential. RTSP UDP/multicast transports are disabled. Phone
publication over either RTMP or SRT converges on this reader.
`--host 127.0.0.1` selects local-only operation. No wildcard or IPv6 binding is
allowed. Port conflicts fail startup; an incumbent process is never stopped.

Moblin publishes to `camera`; phone credentials grant no read permission and
cannot publish to `shielded`. OBS pulls `rtmp://100.109.49.77:19350/shielded`
or `srt://100.109.49.77:18890?streamid=read:shielded`. Only the internal
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

The Twitch destination is a **stub** with no network implementation. It holds
a supplied key in memory, enforces `?bandwidthtest=true`, and never obtains a
key or contacts Twitch. M3 must acquire credentials through Infisical and the
authorized Twitch flow after owner approval. Key removal is explicit.

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

`encoded.flv`, `frames.jsonl` and `runtime.json` describe actual encoded
packets, PTS, per-frame protection/coverage, compressed masks, pixel/PCM hashes
and bounds. An independent native capture is needed to prove network egress.
Root's corrected independent-family OCR grades the sealed captures; this lane
never grades itself with the detector's PP family alone.
Existing licensed footage and all its derivatives are **benchmark-only**,
without music, and are not demo-ready.

Timed/20-minute jobs go through root's fresh `scripts/perf-queue` session and
inherit its exclusive lease; never wrap a queue-owned job in another lock.
Short untimed functional media checks take the canonical exclusive host lock.

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

The original failures remain sealed. A local four-second publisher gap
reproduced the three-second MediaMTX timeout, then passed with the ten-second
default. A real read/publish-ACL matrix passed uncontended on both allowed
addresses. SRT phone publication remains unqualified because its earlier native
run failed with a timestamp regression and did not resume LIVE after reconnect.

Session 3's first physical RTMP soak completed 20 minutes with both native
output captures decoded, all injected faults survived, and no egress recovery.
That run was contended and memory-constrained: it proves functional robustness,
while timing and strict cadence remain unqualified. Independent privacy grading
is pending. The final contended retry survived two recovery events and resumed
the NVENC writer, but its independent captures are incomplete and encoding had
a 22.525-second wall-clock gap. No overall Gate 2 pass is claimed. The session
at `/home/elan/code/irl-shield/.tmp/irl-shield-builder-m2-queue-3` is now closed,
sealed and drained; no further execution is authorized.
Exact argv and source identity are in `.tmp/m2/session3-soak-command.json` and
`.tmp/m2/source-at-recovery.json`; the hand-back links the audited results.

For a fresh queue/run directory, pass the existing pinned GPU library paths
in the queued command's scoped environment, and invoke the private Python
interpreter directly with `-m relay.soak`. The harness validates the inherited
canonical exclusive lease, keeps every failed run, and prints the seal digest
for the conductor to retain outside the artifact directory. Root grades each
sealed capture once using the corrected independent-family scorer.
`python -m relay.seal DIRECTORY --expected-sha256 RETAINED_DIGEST`
verifies the frozen file inventory and bytes before grading.

The direct RTMP-reader crash is preserved as a known PyAV 16.0.1 issue in
`M2-HANDBACK.md`; the live decoder uses the one loopback RTSP/TCP path. The
RTSP/TCP read does not expose another Tailscale-facing listener.


## Bounded egress recovery

A failed or timed-out write stops and reaps only its encoder/writer process.
The engine, ingest object and control sources remain alive. The presenter drops
the failed frame and remaining precomputed batch, clears old queued audio, and
holds output protection while a fresh writer starts. It resumes from a newly
polled engine result; a moderator hold is preserved. No timestamp is clamped or
failed frame replayed. At most five reconnects are attempted in a 60-second
window, with 250ms backoff; exhaustion returns `egress-recovery-limit`.

Recovery events contain fixed error/operation codes and numeric timing only.
Each writer gets its own `encoded-gNNNN.flv` after the original `encoded.flv`;
`frames.jsonl` appends rows with `egress_generation`. The old archive is never
overwritten. Pending and recent event rings are bounded at64. Worker readiness
is reported separately from encoded-frame acceptance, so the internal egress
hold clears only after a network-ready ACK. There is no production RTMP parser
or control-message bridge.

The real control-fragment/backpressure/hold/limit regressions and full Linux
functional gate 73 pass. The first native 20-minute RTMP soak had zero
recoveries; the final retry recorded an archive-mux timeout, a failed encoder
startup, and successful writing through generation 3. Independent decoding
after that restart is unverified: capture readers only retry startup and do
not reconnect after a read failure. The retry's RTSP capture stopped before
recovery, so that interruption has a separate unknown cause.

The retry was 33.096% slate, predominantly with missing-ingest coverage. Its
first synthetic publisher failed before the scheduled kill; the harness then
misclassified the already-dead publisher as intentionally killed. LIVE output
returned after the replacement publisher and manual HOLD release. Host pressure
and source loss are evidenced; CPU starvation alone and a latched recovery hold
are not established. `M2-HANDBACK.md` records these harness limitations, strict
cadence and privacy limits, and the known SRT publication failure.

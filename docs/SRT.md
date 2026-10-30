# Plain SRT ingest

Phone SRT publication enters MediaMTX's authenticated `camera` path. The production
reader remains loopback RTSP/TCP, using PyAV to decode presentation frames and PCM.
Packet DTS need not equal PTS. No Twitch connection is needed for these checks.

## Timestamp handling

`NetworkInput.timestamp_issues` now reports packet PTS/DTS differences, packet-DTS
regressions, decoded nonincreasing timestamps, missing timestamps and decoded-video
discontinuities. These diagnostics contain numeric timestamps and fixed types;
credentialed URLs and upstream exception strings stay out of receipts.

The decoder's display PTS is preserved. A backward decoded-video jump exceeding
0.5 seconds, or a forward jump exceeding elapsed reader time plus 2 seconds,
invalidates the current source generation. The first decoded frame on the new
timeline receives a newer generation and reanchors the session clock. Old media
cannot follow its DROP through the reader's drain interface. Audio resampling is
restarted with that generation. Smaller nonincreasing decoded timestamps remain
visible in diagnostics and the session's mapped-index drop count.

These thresholds distinguish a source-clock discontinuity from normal B-frame
packet reordering. They do not repair a corrupt bitstream or infer missing PTS.
Missing timestamps still fail closed through the existing reconnect path.

The non-full EOF invalidation guard already landed in `b508d462`; this work retains
that guard and its real TCP/NUT tests. It does not claim that commit fixed the
historical SRT replacement-publisher failure.

## Reconnect and capture

A hard-killed UDP/SRT caller does not send a graceful close. MediaMTX can keep
`camera` owned until peer timeout and reject a new caller as `publisher-collision`.
The synthetic replay tool retries the caller with a bounded 60-second continuous
failure budget. It leaves publisher replacement policy and authentication intact.
A complete source loop resets the retry budget. Retries do not release HOLD: only
newer decoded reader media can do that. Moderator holds remain independent.

`relay.srt_capture.Capture` independently subscribes to SRT and writes the original
MPEG-TS messages into separate files for each connection. It retries receive and
connect failures, records connection generations and hashes each received message.
It never copies packet DTS into a Matroska muxer. A muxer's rejection of copied DTS
therefore cannot terminate this raw capture. Each segment needs its own decode
check; a successful connection alone is not evidence of decodable audio/video.

`relay.srt_replay` paces raw MPEG-TS bytes using video-packet DTS and byte positions.
It adjusts its wall-clock pacing across discontinuities without rewriting packet
PTS/DTS or the payload. Every reconnect starts at the beginning of the fixture.
The initial synthetic source repeats a 12-second clip deliberately, exercising
source-clock discontinuities throughout the soak. This is transport evidence.

## Reproduction and queued acceptance

The short CPU checks are `tests/m2/test_srt_input.py` and
`tests/m2/test_srt_capture.py`, discovered alongside the existing M2 tests. They use
synthetic CC0 H.264 B-frame/AAC video, ephemeral IPv4 loopback listeners and no
accounts or external network. The real reader test uses the production one-second
presentation delay; an artificially short 50 ms delay cannot qualify B-frame ingest.

Run short checks under `scripts/host-lock shared`, nice 10, the agents slice,
native thread caps of 2 and OpenCV's cap of 1. The full unified Linux gate is
`scripts/check` with `SHIELD_PYTHON` set to the provisioned unified interpreter.
It runs only under canonical SH in the root's serialized functional-CI wave.
Do not put `scripts/check` under EX: held-out synthetic checks acquire SH
internally, so an EX parent would deadlock. The earlier gate EX packet is retired;
no SRT gate was submitted by this lane.

`out/srt/timed-jobs.json` separates root SH functional-gate arguments from the
GPU smoke/soak EX job arguments and includes source hashes. Root alone submits
GPU jobs to the canonical exclusive performance queue.
The timed harness verifies the inherited EX descriptor before creating listeners,
starting models or encoding. There is no internal flock. A short GPU smoke must
pass before the 20-minute job. At most one retry of a contended successful soak is
allowed; deterministic failures require diagnosis, not another timed run.

The harness uses ephemeral loopback ports, the existing engine and NVENC writer,
and the M2 accurate-lane stall/HOLD/kill/reconnect/release schedule. Synthetic
flash/tone measurements come from independently decoded network capture segments.
They do not qualify OCR privacy, natural-scene quality or an attended phone session.
Root's forced/contended attempt receipt remains authoritative for timing. A
functional pass does not establish an uncontended throughput result.

The CPU receipts, all execution starts/exits, source hashes and queue packet live
in ignored `out/srt/`. No media or credentials belong in the patch.

## Owner Moblin recording

No Moblin recording has been supplied to this lane yet. Its future path and exact
SHA-256 must come from the conductor. Keep it under ignored `out/` or `.tmp/`, record
`owner-supplied/nonredistributable pending explicit license`, and use it only for
private internal diagnosis. Do not commit it, upload it or describe it as a licensed
redistributable fixture. Raw-file replay is the primary diagnostic once supplied.

For an owner fixture, the timed harness requires `--fixture`,
`--fixture-sha256` and `--private-owner-fixture`. It checks the hash before network
replay. Natural footage with no independently identified visual/audio timing event
has unmeasured perceptual A/V offset; timestamp continuity alone is not lip sync.
An attended Moblin SRT session still requires the owner and is pending.

## Dependencies and licenses

No new package, model or SDK is installed. MediaMTX v1.21.3 is MIT, pinned to binary
SHA-256 `bfa372a169751bbf6da2ebddcbcd2f7d3ab3dca3cc553022162eda36fe03e73d`;
`relay.mediamtx.verified_binary` verifies it. Private tool copies include its LICENSE.
PyAV 16.0.1 is BSD-3-Clause; the existing FFmpeg wheel includes GPL components,
including libx264, so its GPL-2.0-or-later component notices apply. The system
libsrt 1.5 adapter is MPL-2.0 with BSD portions and records its library hash.
Existing source/license pointers are in [relay/README.md](../relay/README.md#dependencies-and-licenses).
The new synthetic fixture generator is dedicated to CC0-1.0 by the IRL Shield
authors. Its timing labels are synthetic; it contains no music or third-party logos.

## SRTLA source review — 2026-10-30

The source review is complete; runtime compatibility remains untested. Only
public official source and license files were read. No SRTLA dependency was
adopted, built, installed or started. Reviewed revisions are BELABOX/srtla
`37862da3d0c13b46956efd3f88877053293d97d6`, BELABOX's patched SRT
`4b6e11be7d2090a3c982c71903b56ed748075e9a`, and MediaMTX `v1.21.3`.
Source snapshots, access timestamps and SHA-256 hashes are in the private
`out/srt/research/sources.json` receipt.

### Availability and licenses

The public `srtla_rec` source is available without a cloud account. My read of its
README is that the receiver is experimental, unsupported and no longer maintained
for production. SRTLA v2 is incompatible with the earlier protocol, so a future
phone trial must identify the sender version. These are source findings, not a
phone compatibility result. [Pinned SRTLA README](https://github.com/BELABOX/srtla/blob/37862da3d0c13b46956efd3f88877053293d97d6/README.md).

The receiver's header grants **AGPL-3.0-or-later**; the repository includes the
AGPL v3 text. Sections 4–6 cover notices/source when conveying it; section 13
covers a modified network-interactive version's source offer. This report does
not classify the whole IRL Shield application under that license.
[Receiver header](https://github.com/BELABOX/srtla/blob/37862da3d0c13b46956efd3f88877053293d97d6/srtla_rec.c#L1-L17),
[license](https://github.com/BELABOX/srtla/blob/37862da3d0c13b46956efd3f88877053293d97d6/LICENSE).
The optional patched SRT fork carries **MPL-2.0**; MediaMTX carries **MIT**.
Their notices remain separate.
[Patched SRT license](https://github.com/BELABOX/srt/blob/4b6e11be7d2090a3c982c71903b56ed748075e9a/LICENSE),
[MediaMTX license](https://github.com/bluenviron/mediamtx/blob/v1.21.3/LICENSE).

### Placement and streamid

A possible topology places a SRTLA receiver ahead of MediaMTX: the phone sends
bonded traffic to the proxy, which forwards ordinary SRT datagrams to MediaMTX's
SRT listener; the existing loopback RTSP reader then feeds Shield. The SRTLA
README assumes SRT caller-to-listener traffic and multiple usable sender links.
Its Linux sender also needs source routing for link selection.
[Pinned topology/prerequisites](https://github.com/BELABOX/srtla/blob/37862da3d0c13b46956efd3f88877053293d97d6/README.md).

My source-level inference is that a direct proxy path should preserve the SRT
handshake's streamid: `handle_srtla_data` forwards the received SRT buffer without
rewriting it, and the reverse handler forwards response buffers. The receiver
does not construct MediaMTX credentials.
[Forwarding handlers](https://github.com/BELABOX/srtla/blob/37862da3d0c13b46956efd3f88877053293d97d6/srtla_rec.c#L353-L489).
MediaMTX's parser accepts `publish:camera:<user>:<password>`; its publication path
passes those fields into authentication. The future sender must supply the
runtime-generated credentialed streamid. This inference needs a real handshake
and reconnect test; no such test ran here.
[Streamid parser](https://github.com/bluenviron/mediamtx/blob/v1.21.3/internal/servers/srt/streamid.go#L23-L98),
[publication authentication](https://github.com/bluenviron/mediamtx/blob/v1.21.3/internal/servers/srt/conn.go#L143-L183).

### Build requirements and integration limits

Source inspection identifies Linux, a C compiler, make and Git for the SRTLA
build; its Makefile links `srtla_rec.o` with `common.o` and has no libsrt link flag.
[Makefile](https://github.com/BELABOX/srtla/blob/37862da3d0c13b46956efd3f88877053293d97d6/Makefile).
An optional patched-SRT receiver/bridge adds a C/C++ toolchain, CMake, OpenSSL
headers/libraries and POSIX threads; Tcl is optional. Its install prefix is
configurable. These are requirements only; no commands were run.
[Patched SRT requirements](https://github.com/BELABOX/srt/blob/4b6e11be7d2090a3c982c71903b56ed748075e9a/README.md#requirements).

The SRTLA README's receiver guidance includes reordering/latency tuning and a
patched C++ SRT receiver; it permits upstream SRT with a performance caveat.
[Receiver guidance](https://github.com/BELABOX/srtla/blob/37862da3d0c13b46956efd3f88877053293d97d6/README.md).
Our pinned MediaMTX uses **Go gosrt v0.12.0**, with its own listener configuration.
Installing a patched C++ libsrt would not change that Go backend. Direct bonding
performance and loss recovery therefore remain unqualified. A separate patched
SRT bridge would be additional implementation, with a new authenticated outbound
connection and runtime-only credentials; it is outside this change.
[MediaMTX dependency](https://github.com/bluenviron/mediamtx/blob/v1.21.3/go.mod),
[listener](https://github.com/bluenviron/mediamtx/blob/v1.21.3/internal/servers/srt/server.go#L109-L124).

The reviewed receiver hardcodes `INADDR_ANY` and offers only listen-port and
backend-host/port arguments. Consequently, unmodified `srtla_rec` cannot satisfy
this task's explicit loopback/Tailscale bind-address rule. That needs a reviewed
future implementation before any listener trial; none was made here.
[CLI and bind](https://github.com/BELABOX/srtla/blob/37862da3d0c13b46956efd3f88877053293d97d6/srtla_rec.c#L626-L676).

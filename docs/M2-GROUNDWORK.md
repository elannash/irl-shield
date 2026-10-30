# M2 local relay groundwork

This is a local transport experiment, authored in the authorized Codex family
on October 29, 2026. Its output is **benchmark only**. The licensed Market
Street fixture contains third-party signs and brands and is unsuitable for the
submission video. Source audio is discarded; the only generated sound is a
1 kHz measurement pulse. No Twitch connection, stream key, public ingest, or
secret is used.

## Status

The current relay adapter uses the new fixed-deadline `submit`/`poll` engine.
Three lightweight adapter checks pass on Linux and, in the root full gate,
on Mac, including the actual new engine with both detector lanes. **The
current adapter has no network revalidation.** The Mac functional-gate receipt
is `/tmp/agents/irl-shield/m1-perf-queue/root-v2-mac-gate-fixed.log`.
The earlier RTMP/SRT measurements below are preserved historical receipts from
the replaced synchronous `push`/`flush` engine. They do not measure the new
engine or its presentation delay.

The Mac `.tmp/m2/runtime` remains the unchanged historical source snapshot.
No Mac command, media run, install or clip ping occurred in the child migration
step. The later root functional gate ran these tests on the main Mac mirror;
it did not resync or rerun the historical local-network snapshot.
The historical runs used a private source copy and virtual environment under
`.tmp/m2/` and each delivered 240 numbered frames with decoded audio through
RTMP → engine → RTMP and SRT → engine → SRT. Their latency and EOF-buffering
limits remain historical findings rather than current acceptance evidence.

The parent granted token `m2-window-20261029T203600Z` for 20:36–20:44 UTC.
All media work and probes finished, with the window released at 20:42:56 UTC.
Before the token, Mac activity was read-only capability checks. One explicit
idle wait lasted 60 seconds; an additional wait ended on the parent's message
without a recorded duration. The earlier hold overlapped Linux authoring.

## Current interface and timestamps

`relay.run` is wired to decode one local RTMP or SRT input into timestamped
raw BGR video and mono 48 kHz signed 16-bit PCM audio in a NUT pipe, call the
new `shield.engine.MaskingEngine`, and encode H.264 VideoToolbox plus AAC
for a local RTMP or SRT sink. This transport composition has not been rerun
since migration. `NoOpDetector.detect(frame)` returns `[]` and `close()` is a
no-op. It does not pretend to mask text.

The engine interface is:

```python
MaskingEngine(lanes, options, motion=None, renderer=None, control=None)
engine.submit(Frame(index, pts_seconds, pixels), now=None)
engine.poll(now=None)  # list[PresentedFrame]
engine.end(last_index=None)
engine.drained
engine.close()
engine.hold(active, source='local', reason='manual', now=None)
engine.stats
```

`lanes` contains `fast` and `accurate` adapters. The M2 benchmark profile uses
both real `DetectorLane` workers with separate `NoOpDetector` instances,
`fps=30` and `delay_seconds=0.1`. The engine's normal default delay is one
second. The relay command exposes `--fps` and `--delay-seconds` and rejects
zero, negative or nonfinite values. Its configured source cadence must match
the demuxed video rate. There is no retained relay `--lookahead` option.

`bridge_nut(source, destination, engine, events)` accepts a fresh engine and
owns its lifetime, including `close()` on success or failure. The caller owns
the NUT source and destination. A bounded 32-message producer queue separates
blocking demux from the caller's presentation/mux loop. POSIX pipe reads are
interruptible so cleanup does not depend on the source sending EOF. After
metadata is available, the caller polls at each received message or a 5 ms
queue timeout, so source stalls cannot stop presentation polling. Mux
backpressure and processing cost can still delay a poll; this is not a
hard-real-time scheduling claim.

Frame indices come from `round((source_pts - first_source_pts) * source_fps)`,
so a source gap does not renumber recovered frames onto already-presented
indices. Submitted frames retain an exact index → original PTS/time-base
entry. When the engine emits a protected placeholder for an unsubmitted
index, the adapter uses `PresentedFrame.pts`, rounded to the source video
time base. Late source frames still reach `submit` for the engine's discard
accounting, while their timestamps cannot overwrite a previously muxed frame.

Only `PresentedFrame.pixels` reaches the video encoder. Delayed frames do not
fall back to source pixels, and protected/slate pixels are not replaced by the
original image. EOF calls `end(last_source_index)` and the adapter polls until
`engine.drained` before flushing and closing the NUT muxer. The output count
can exceed the submitted-frame count when protected missing-index frames are
presented.

Audio stays outside the engine. The NUT bridge remuxes PCM packets with their
source timestamps and bytes. It holds audio until presented video advances,
then releases the remaining audio only after EOF and the engine is drained.
FFmpeg performs the input PCM conversion and output AAC encoding; AAC
priming and container timestamp normalization are
therefore part of the measured end-to-end A/V result. This experiment does
not claim bit-exact compressed-audio passthrough.

The preserved transport helpers use FFmpeg's RTMP listener input and caller
output. SRT uses the upstream
`srt-live-transmit` utility's `file://con` pipes around unmodified FFmpeg:
SRT → MPEG-TS pipe → FFmpeg, and FFmpeg → MPEG-TS pipe → SRT. The SRT utility
uses milliseconds for `latency=120`; FFmpeg's own SRT URL API instead uses
microseconds. See [Haivision's utility documentation](https://github.com/Haivision/srt/blob/master/docs/apps/srt-live-transmit.md)
and [FFmpeg's protocol reference](https://ffmpeg.org/ffmpeg-protocols.html#srt).
The helper uses one-packet application buffering, 1316-byte chunks,
auto-reconnect disabled and a two-second sender close linger. After encoder
EOF, it gets a one-second local drain window and then a graceful SIGTERM,
because this sample utility remained open after stdin EOF in the observed run.
That finite-stream drain is local groundwork, not a WAN delivery guarantee.
No isolated FFmpeg build is necessary for this design.

## Historical setup and command recipe

**Do not use this recipe as current migration validation.** No further Mac or
media run is authorized by the adapter migration. Before a later allowed
window, use the parent-updated private sync manifest: `scripts/m2-mac`
now copies `shield/*.py`, including types, lanes, control, motion and render.
That source-copy fix does not establish another media or network measurement.
The commands below document the historical run forms; the Mac snapshot has
not been resynced with the current relay or engine.

The historical runner synced M2 code, a copy of the engine files, the single
tune fixture, and M2 tests into `~/code/irl-shield/.tmp/m2/runtime`. The runner
uses `bash -lc`, a process-group supervisor, capped thread counts and a
`perl` alarm. It refuses to run without an explicit `--window TOKEN`; a timer
expiring never grants permission. The token is supplied only after the
parent has cleared M1 timing work from the Mac.

From the Linux checkout, after that grant:

```bash
scripts/m2-mac --window PARENT-GRANTED-TOKEN --seconds 300 bash scripts/m2-setup
scripts/m2-mac --window PARENT-GRANTED-TOKEN --seconds 60 ../venv/bin/python -m unittest discover -s tests/m2 -v
scripts/m2-mac --window PARENT-GRANTED-TOKEN --seconds 60 ../venv/bin/python -m relay.scenario --protocol rtmp --baseline --fixture fixtures/sf-market.mp4 --artifacts ../runs/rtmp-direct
scripts/m2-mac --window PARENT-GRANTED-TOKEN --seconds 60 ../venv/bin/python -m relay.scenario --protocol rtmp --fixture fixtures/sf-market.mp4 --artifacts ../runs/rtmp-relay
scripts/m2-mac --window PARENT-GRANTED-TOKEN --seconds 60 ../venv/bin/python -m relay.scenario --protocol srt --baseline --fixture fixtures/sf-market.mp4 --artifacts ../runs/srt-direct
scripts/m2-mac --window PARENT-GRANTED-TOKEN --seconds 60 ../venv/bin/python -m relay.scenario --protocol srt --fixture fixtures/sf-market.mp4 --artifacts ../runs/srt-relay
scripts/m2-mac --window PARENT-GRANTED-TOKEN --seconds 60 ../venv/bin/python -m relay.inspect_runs ../runs
```

`m2-setup` installs the free Homebrew `srt` package with auto-update,
installed-formula upgrade and cleanup disabled. Those flags did **not**
prevent transitive dependency updates: Homebrew installed OpenSSL 4, upgraded
the CA bundle and changed the default OpenSSL links. These actual side effects
are recorded below. The setup also creates M2's private virtual environment
and installs binary wheels only. FFmpeg stayed at its existing 8.1.2 keg.

The direct runs bypass the relay entirely. The relayed runs add its decode,
engine, encode and second network hop. Both sender and receiver use the same
hardware encoder settings and 640×360 at 30 fps. Each scenario sends 240
numbered real-video frames over eight seconds. Default owned ports are
19460 (input) and 19461 (sink); RTMP uses TCP, SRT uses UDP. The harness checks
that it can bind each port before starting and after cleanup. It terminates
only its own process groups and writes each PID and exit status.

## Current event schema and historical measurement limits

`sender/events.jsonl` records every emitted frame index, source epoch in
milliseconds and source video time. The source frame carries that same epoch
and index as 64 black/white cells before encoder input. `sink/events.jsonl`
records each independently decoded marker, wall-clock arrival, PTS, and
latency. `capture.mkv` contains the actual encoded output. The real fixture
remains visible behind the timing strip and flash; no slate-only frame can
meet the frame evidence condition.

Current `relay/engine.jsonl` video events include index, exact/restored PTS and
time base, `source_frame`, `state`, dataclass `coverage`, `deadline`,
`presented_at`, `protected`, `slate`, and bridge residence milliseconds
(`stage_ms`, null for a placeholder). PCM events retain packet PTS/time base
and byte count. The final event includes the engine's public `stats`.
Historical network logs used the previous smaller event schema.
Residence includes BGR conversion, engine processing, NUT write/backpressure
and release of audio; it is not an isolated detector or engine CPU benchmark.
`receipt.json` requires the complete exact frame-index sequence at the sink,
nonempty decoded audio, and at least three matching flash/pulse onsets. It
reports latency minimum, median, p95 and maximum in milliseconds. No metric
drops warmup frames, late frames, or outliers; the sample frame is all 240
sent and received frames in that scenario. Source and sink run on the same
Mac clock. Epoch markers have 1 ms quantization and sink decode arrival is
not physical display latency. Compression robustness is checked by marker
validity and exact index ordering, rather than assumed from an open socket.

A/V offset is decoded audio pulse onset minus decoded video flash onset in
milliseconds, comparing timestamps in the received media. The pulse uses
absolute amplitude above 4000 out of 32768. Each white flash and tone lasts
100 ms every source second. Video onset is quantized to 1/30 s. AAC ringing,
priming, and the threshold can shift the detected audio onset; individual
onsets remain in the receipt for inspection. Added relay latency is the
relayed median minus the matching direct median and is a sequential localhost
comparison, not a WAN estimate or concurrent controlled trial.

## Sources and licenses

| Component | License and source | Use |
| --- | --- | --- |
| PyAV 16.0.1 | [BSD 3-Clause](https://github.com/PyAV-Org/PyAV/blob/v16.0.1/LICENSE.txt), [pinned release](https://pypi.org/project/av/16.0.1/) | NUT demux/mux, raw frames and timestamp access; installed wheel, no copied library code |
| FFmpeg 8.1.2 (existing Mac install) | [FFmpeg license](https://ffmpeg.org/legal.html); existing build has `--enable-gpl --enable-version3`, hence GPL-3.0-or-later | Separate executable for decode and VideoToolbox/AAC encode; unchanged |
| libsrt / srt-live-transmit | [MPL 2.0](https://github.com/Haivision/srt/blob/master/LICENSE), [Homebrew formula](https://github.com/Homebrew/homebrew-core/blob/master/Formula/s/srt.rb) | Separate executable for SRT transport, no service |
| OpenSSL 4.1.0 | [Apache 2.0](https://github.com/openssl/openssl/blob/master/LICENSE.txt), [formula dependency/link behavior](https://github.com/Homebrew/homebrew-core/blob/master/Formula/o/openssl@4.rb) | Homebrew SRT dependency |
| ca-certificates 2026-10-20 | [MPL 2.0, source and recipe](https://github.com/Homebrew/homebrew-core/blob/master/Formula/c/ca-certificates.rb) | OpenSSL dependency; updates the Mozilla CA bundle |
| NumPy 2.2.6 | [BSD 3-Clause](https://github.com/numpy/numpy/blob/v2.2.6/LICENSE.txt) | Array and pulse construction; existing M1 version pin |
| OpenCV Python headless 4.11.0.86 | [MIT package wrapper](https://github.com/opencv/opencv-python/blob/4.11.0.86/LICENSE.txt), OpenCV Apache 2.0 and bundled dependency notices in `cv2/LICENSE-3RD-PARTY.txt` | Existing engine dependency, private install |
| `sf-market` tune fixture | [Street traffic](https://commons.wikimedia.org/wiki/File:Street_traffic.webm), CC BY 3.0, author [Editor](https://www.youtube.com/user/Editor); repo `fixtures/ATTRIBUTION.md` and `fixtures/manifest.json` | Benchmark-only excerpt, resized, with generated timing marks and replacement tone; no source audio |
| Measurement strip, flash and tone | Original code and generated data in this Codex child | Benchmark instrumentation, no music |

No paid service, waitlisted model, expiring backend or additional detector
model is introduced. Installation downloads third-party packages from their
ordinary public sources; media URLs are restricted to literal loopback or
Tailscale IP addresses and reject embedded credentials.

## Current adapter TDD receipts

Migration verification used the lightweight Linux suite:

```bash
nice -n 10 .tmp/m2/linux-venv/bin/python -m unittest discover -s tests/m2 -v
```

Five red/green invocations and one CLI import/help check were used, within
the six-invocation budget:

1. Red against the synchronous bridge: the deterministic new-interface
   adapter failed at `engine.push` with `AttributeError`, exercising the real
   NUT bridge seam rather than an import failure.
2. Green after migration: stalled-pipe/PTS/PCM protection check plus the
   existing host guard passed.
3. Green with an added actual new engine check: both real no-op lanes and
   `delay_seconds=0.1` preserved HOLD through real in-memory NUT.
4. Deliberately bypassing `PresentedFrame.pixels` with source pixels made the
   focused privacy test fail: received values `[20,20,21,22,23,24,25]` instead
   of seven protected zero frames.
5. Restored `bridge.py` byte for byte; all three checks passed again in
   0.136 seconds. The actual-engine check confirmed no new Python threads
   survived the call.
6. `python -m relay.run --help` passed with `--fps` and `--delay-seconds` and
   no `--lookahead`; it started no media processes or network connection.

The deterministic adapter implements the same submit/poll/end/drained/close
interface and is used only to control the input-stall and protection fixture.
It verifies a protected output before the writer releases EOF, source-derived
indices across a gap, seven exact output timestamps for six source frames,
exact PCM bytes/timestamps, final drain/close, and state/coverage/deadline
events. The actual-engine check covers the real lane and engine composition
in HOLD; the root engine suite owns detector coverage and scheduling policy.
These checks use generated arrays and PCM only. They do not exercise RTMP,
SRT, FFmpeg, VideoToolbox or a real detector. The later root Mac functional
gate exercises the adapter environment only, not network or codec behavior.

## Historical execution receipts and remaining work

The historical Linux boundary verification used a private Python 3.11 environment and binary
wheels. Python 3.14 could not satisfy the existing NumPy 2.2.6 pin, so it was
replaced only in M2's scratch environment with Python 3.11, matching the Mac.
`python -m unittest discover -s tests/m2 -v` passed both checks. The media
check constructs and reads real NUT packets, sends six distinct images through
two-frame lookahead, and requires their exact original timestamps plus exact
PCM bytes and audio timestamps. Temporarily adding one tick to the emitted
video PTS made that assertion fail; the original source was restored byte for
byte and both checks passed again. Logs are `.tmp/m2/pts-mutation-red.log`
and `.tmp/m2/boundary-green.log`. The host guard check exercises the actual
URL validator and requires rejection of public hosts and credentials.

Those earlier two synchronous-engine checks passed on the Mac. The historical scenario budget was four
distinct scenarios plus one repair rerun, and was exhausted without an extra
media run. RTMP relay ran first so the parent could announce an actual
engine-to-sink frame; the command forms above are the reusable recipe, not
chronological ordering. The sole repair used the SRT baseline command with
`--artifacts ../runs/srt-direct-repair`.

All following **historical synchronous-engine** latency samples include every decoded optical frame, including
startup and EOF tails. Units are milliseconds, rounded here to three decimals;
the JSON receipts retain unrounded values. A/V offset means audio minus video.

| Scenario | Numbered video frames | Decoded audio samples | Median latency | p95 | Maximum | A/V pulse offsets | Verdict |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| RTMP direct | 240/240 | 385024 | 171.412 | 214.045 | 608.716 | −11.958 to −12.125 ms, 8 pairs | Clean exit, probe clean |
| RTMP relay | 240/240 | 386048 | 640.735 | 700.181 | 783.825 | −24.125 ms, 8 pairs | Clean exit, probe clean |
| SRT direct, first attempt | 58 at sink / 114 emitted before failure | Incomplete | — | — | — | Incomplete | Failed; excluded from passing metrics |
| SRT direct, repair | 240/240 | 385024 | 592.876 | 652.386 | 6114.146 | +0.042 ms, 8 pairs | Media complete; lifecycle failed and final H.264 decode warning |
| SRT relay | 240/240 | 386048 | 1171.021 | 2398.311 | 4214.549 | +0.042 ms, 8 pairs | Clean exit, probe clean |

RTMP added median latency was **469.323 ms** (640.735 − 171.412). The
equivalent SRT subtraction is 578.145 ms, but it is provisional: its baseline
had a lifecycle failure, a decoder warning and a five-second EOF wait that was
subsequently replaced by the one-second drain. It is not an accepted clean
baseline. No warmup or EOF outlier was removed to improve a result.

The first actual relay frame reached the sink at 20:38:33.780 UTC. The relay
recorded index 0, PTS 2048 at time base 1/61440 and residence 1.180208 ms;
the sink decoded optical index 0 with source epoch 1793306312996 ms and
arrival epoch 1793306313779.825 ms. This was immediately reported to the
parent. The two relay engine receipts each end with 240 received, 240 emitted,
376 PCM packets and 770048 PCM bytes. Sink AAC decoding has extra priming/tail
samples, so decoded sample counts are not evidence of bit-exact audio.

FFprobe independently counted 240 H.264 frames at 640×360, 30 fps and mono
48 kHz AAC in both relayed captures. Their probes emitted no decode errors.
The first PNG of each relayed capture was opened and inspected: it is the
real street scene behind the measurement strip and flash, with readable
third-party brands still visible. Neither is demo footage.

The first SRT failure came from `-timeout:3`: version 1.5.7 starts one absolute
alarm, rather than the inactivity behavior described by the current utility
docs. The [versioned utility source](https://github.com/Haivision/srt/blob/v1.5.7/apps/srt-live-transmit.cpp#L431)
contains that alarm. Removing it exposed the sample helper's stdin-EOF hang;
the repair delivered all frames but the sender's five-second wait raised a
timeout. The final SRT relay scenario exercised the bounded graceful shutdown
fix and passed. The original failed artifacts and logs were retained.

Artifacts are at `.tmp/m2/runs/` on Linux and
`~/code/irl-shield/.tmp/m2/runs/` on Mac. Each run contains events, process
receipts, FFprobe JSON, an encoded `sink/capture.mkv`, and
`benchmark-only-first-frame.png`. `inspection.json` combines all five runs,
including failures, and confirms **34/34 owned PIDs exited**. Bind checks
confirmed TCP and UDP ports 19460 and 19461 free after all runs. No sender,
receiver, relay, SRT helper or FFmpeg listener was retained.

Historical Mac installs: Homebrew `srt 1.5.7_1`, `openssl@4 4.1.0`, and
`ca-certificates 2026-10-20` alongside its prior `2026-09-25` keg. Homebrew
unlinked 6570 default symlinks from `openssl@3 3.6.4` and the 20:42 inspection's
`/opt/homebrew/bin/openssl` resolves to
`/opt/homebrew/Cellar/openssl@4/4.1.0/bin/openssl`. The OpenSSL 3 keg remains.
These unexpected global dependency/link changes were reported to the parent
as they happened; this child did not manually relink or remove packages.
The final environment receipt is Mac `.tmp/m2/runs/environment.json`.
FFmpeg remained `/opt/homebrew/Cellar/ffmpeg/8.1.2` and ran successfully after
the install. The private Python environment installed only PyAV 16.0.1,
NumPy 2.2.6 and OpenCV headless 4.11.0.86, with no compilation.

Remaining work: run a later authorized Mac/network revalidation of the current deadline adapter; reduce
transport/mux/EOF buffering; obtain a clean SRT direct
baseline with the final shutdown policy; investigate the RTMP A/V offset and
FFmpeg video timestamp quantization; exercise cross-transport URLs;
then verify a live source and a real detector. The one-second local drain is
not a production shutdown protocol. Cross-transport mode is structurally
supported by independent input/output URLs but was not exercised.
The root M1 bench belongs to the parent; this child does not edit or run its
live runtime during a timing window. Parent integration must pair the relay
hand-back with the required tune scorecard before claiming the stream path
is accepted. Real masking, failure policy, reconnects, phone/Tailscale ingress,
and Twitch bandwidth-test integration remain later M2 work.

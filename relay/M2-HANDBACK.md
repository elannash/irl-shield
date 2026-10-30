# M2 relay hand-back

**Current verdict: RTMP functional robustness is PROVEN by a completed native
20-minute run; timing and strict cadence are NOT QUALIFIED because that run was
contended and memory-constrained. Independent privacy is PENDING root grading;
Q is unqualified. SRT publication remains red. The final retry survived two
egress recovery events but is incomplete, with failed capture coverage and a
22.525-second encoding gap. The queue is closed; no further execution is
authorized. No overall Gate 2 pass is claimed.**

## Source, ownership and stop conditions

Requested/actual branch: `elannash/m2-relay`. Dedicated worktree:
`/home/elan/.t3/worktrees/irl-shield/t3-ae860af9`. The initial operation verified
isolation and exact base `ec1d1f96a1c29ab82109c66f27064f3fd6cb326d`; the prepared
branch was renamed in place. Opus subsequently committed the source checkpoints
`d4a28a99bdda0bc44a685f31cd971babf1263781` and
**`f9dc9482b0a46e4ad453c7da01835d92abc7e87c`**, the current HEAD. This lane did
not stage, commit, push, open a PR, merge, or create/remove a worktree in shell.

All implementation writes stayed in `relay/`, `scripts/m2-*`, `tests/m2/` and
owned ignored scratch. Engine, scorer, judges, cache code, root requirements
and root README were not edited. Current uncommitted paths are only
`relay/M2-HANDBACK.md`, `relay/LOG.md`, and `relay/README.md`.

Conductor extended the original timebox explicitly to **Friday October 30,
08:00 PT / 15:00 UTC** for bounded egress recovery. Model changes and test-budget
increases did not reset elapsed time. The ceiling is **76 invocations**;
**75 executed; the budget is CLOSED by conductor instruction.** Session 3 had
two physical executions, at queue ordinals 2 and 5. Ordinals 1, 3 and 4 were
rejected before execution and spend zero. No third physical soak or additional
test/native execution is authorized, despite the nominal unused slot 76.

The active source is frozen in [source-at-recovery.json](../.tmp/m2/source-at-recovery.json):
31 paths, snapshot SHA256
`fbd7909030da40858d1c83a969a2e70ccbf9491a9a8968f544569c0ac5d22aab`.
The new soak's provenance records HEAD f9dc948 and matches all 61 source hashes.
The reviewed patch against d4a28a9 is [recovery-source.patch](../.tmp/m2/recovery-source.patch),
SHA256 `77ddc0d1edaac4de2221e5d344149299246325f9f50d3e789a973c4b3be91fc4`.
Copies under `.tmp/m2/recovery/` are stale and must not be adopted.

## Gate 2: final per-criterion verdict

Job `36103e2e99f24959888f2f5d2175e282`, queue attempt 2, physical execution 1:
[summary](../.tmp/m2/gate2-v3/m2-v3-rtmp-soak/attempt-2/summary.json),
[runtime](../.tmp/m2/gate2-v3/m2-v3-rtmp-soak/attempt-2/runtime.json),
[parent audit](../.tmp/m2/v3-attempt2-parent-audit.json).
Exit 0; `functional-evidence-complete`; `transport_guards_pass=true`.
Original queue stdout seal:
`2948628190006f3ab35afd350e890279b2dc473f74451d64e8c2680775a9aa90`.
The parent verified the exact inventory, all sizes/hashes/read-only modes:
**25 files, 1,428,817,811 bytes, zero mismatches**. This was a read-only audit,
not a new native execution, decode, test, or OCR call. The manifests and
recomputed PTS/offset/fault totals agree with the sealed summaries.

| Criterion | Verdict and measured evidence |
| --- | --- |
| Native 20-minute execution | **RTMP functional robustness PROVEN by attempt 2:** RTSP capture 36,115 decoded frames over 1203.820 s; SRT output capture 36,110 over 1203.633 s; 36,205 encoded rows. Retry attempt 5's session ran 1208.205 s and wrote 35,944 rows, but its independent captures are incomplete. RTMP phone publication with SRT output capture does not qualify SRT phone publication. |
| Uncontended timing | **NOT QUALIFIED in either execution:** attempt 2 other-busy mean 40.189%/max 73.366%; attempt 5 mean 38.411%/max 75.757%; both `memory_not_ok`, `forced=false`, contamination `valid=false`. |
| Bounded queues and memory | **PARTIAL:** both input queues 8/8, PCM capacity 192,000, declared engine buffer 68/final 29/no evictions. Sampled main+MediaMTX+sender peak summed RSS 1,248,472 KiB attempt 2 / 1,298,856 KiB retry. Encoder-worker memory/FDs, full process tree and GPU/VRAM remain unmeasured; no complete memory qualification. |
| Sender kill, lane stall, reconnect | **PASS functionally in attempt 2:** accurate-stall 109 protected rows; actual live sender kill/reconnect and HOLD/release survive; 202 manual-HOLD rows after 250 ms grace, zero metadata violations. Retry also has 109/202/0 and returns LIVE, but its first sender had already failed before the scheduled kill, so that kill is not a valid second deliberate-kill proof. |
| Audio/video alignment | **MEASURED, timing unqualified:** attempt 2 has 822 pairs per capture; RTSP median +3.271 ms/absolute p95 4.770 ms; SRT output +1.771/2.604 ms. Each has 105 unpaired beeps/22 unpaired flashes. Retry has only pre-recovery prefixes: 122 RTSP pairs 4.688/8.770 ms and 323 SRT pairs 1.729/11.083 ms; no post-recovery A/V proof. |
| No egress gaps above 10 s timeout | **Attempt 2 observed PASS; retry FAIL:** attempt 2 encoded-wall max 464.551 ms, decoded PTS gaps 55/34 ms. Retry encoded-wall gap 22.525 s, presentation gap 22.511 s and 261 skipped manifest indices. Its smaller 8.733 s PTS jump cannot substitute for wall time. |
| Fail-closed frames at source cadence | **Protection metadata guards PASS; cadence NOT QUALIFIED:** attempt 2 has 7,910 protected/6,496 slate/28,295 LIVE rows. Retry has 12,799 protected/11,896 slate/23,145 LIVE rows; 33.096% slate, with a 22.525 s offline gap. There is no continuous decoded network coverage after retry recovery. Independent pixel/OCR verification remains pending. |
| Bounded egress recovery | **Local native regressions PASS; real NVENC writer recovery OBSERVED:** retry archive-mux write timeout and failed next-worker startup produce 2 unique recovery events; writer generation 3 resumes and runs through final LIVE output. Independent post-recovery network decoding is unverified. Algorithmic retry/deadline bounds are implemented; strict wall-time bounds are not qualified under this host pressure. |
| Zero readable labels and real video | **PRIVACY PENDING** corrected independent/all-leak root grading. Attempt 2 RTSP has 29,709 spatial-content frames and 25,537 optical matches; all-slate output is excluded. `gate2_privacy_pass=false` denotes pending grading, not a measured OCR leak count. Q remains unqualified. |

The pressure is visible: 136 accepted input sessions, 245 disconnections, queue
high-water 8/8 and 9,329,678 discarded audio samples. Input generation invalidation
preserves the bound; output continues as LIVE/protected/slate. The 4 missing
input PTS and zero recorded non-increasing PTS are not silently clamped. These
counters prevent representing the run as uninterrupted input or lossless audio.

Resource sampling covers 1,209 samples over 1208.067 s. Full-lifecycle summed
thread range 39–85 and FD range 64–122 include startup/reconnect transients.
Early steady samples 60–120 s have median 66 threads / 112 FDs; late 1080–1140 s have
67/114. Early/late median summed RSS is 1,225,928/606,168 KiB. Those observations
support bounded sampled usage, not a complete process-tree or long-term leak proof.

Encoded timestamps are taken after encode/mux; decoded PTS is a separate clock.
Maximum successful egress write/ACK duration is 477.467 ms. These receipts do not
isolate CPU starvation, GPU, IPC, disk, or network delay; no pure-starvation
cause or proven priority adjustment is claimed. Walk timing still needs an
uncontended native run on a host meeting queue readiness >=80% idle and >=4 GiB
available memory. This lane ran at nice 10; a higher-priority requirement was
not tested. The producer has not been changed to hide gaps by clamping clocks.

## Final retry: verified timeline and harness limitations

Attempt 5 is physical execution 2, invocation 75, native exit 2 / `incomplete`:
[summary](../.tmp/m2/gate2-v3/m2-v3-rtmp-soak/attempt-5/summary.json),
[runtime](../.tmp/m2/gate2-v3/m2-v3-rtmp-soak/attempt-5/runtime.json),
[parent audit](../.tmp/m2/v3-attempt5-parent-audit.json).
Original queue stdout seal
`53d8c9e1a5be466fc80b4f822b7d25729cd07cb52c36ac25101f58f0ca09a8c3`
matches all 29 files / 753,598,406 bytes, with zero integrity mismatches. The 31
frozen and 61 provenance source hashes, exact argv and HEAD f9dc948 match.
Only receipt reading, hashing and FLV tag metadata inspection occurred; no new
native execution, media decode, test or OCR was performed.

The relay session stops normally after 1208.205 s with no runtime cleanup error.
It produces 35,944 manifest rows versus 36,205 engine outputs: 261 indices were
discarded during recovery, never replayed. The three summary errors are short
RTSP span, insufficient RTSP frame count and incomplete SRT output capture.
They do not assert an engine crash. They also do not establish full end-to-end
success after the captures stop.

Times below share the scenario's monotonic origin:

- RTSP's last packet is at 183.056 s and its `ExitError` finish at 185.128 s.
  First egress recovery is 515.608 s, **330.480 s later**. The explanation that
  recovery caused this RTSP stop is contradicted by the sealed timeline.
  The fixed error class does not establish its underlying cause. It is a
  separate early capture interruption, with no reconnect afterward.
- The generation 1 sender reports `BrokenPipeError`, errno 32, `network-mux`
  at 515.214 s, after 14,981 sent frames. Its publisher has already failed before
  the planned 665.008 s kill. `Scenario._stop(kill=True)` records
  `intentional_kill=true` regardless of whether the process was already dead;
  `summarize` consequently exempts this actual exit 2. This is a **harness
  accounting defect**, not successful execution of the intended kill fault.
- Recovery 1 is `egress-write-timeout` with worker operation **`archive-mux`**
  at 515.608 s, failed index 14960. This identifies the observed operation;
  CPU starvation versus I/O/OS pressure remains unproved. It is not evidence
  that the previously injected RTMP control-message mechanism caused this run.
- Generation 2 startup times out at 521.263 s (`encoder-startup`). Its 394-byte
  archive contains headers only, with no encoded audio/video data tags.
  There are **2 unique recovery events**; the append-only recovery file has 3
  rows because startup wrote the first pending event again before failing.
  Consumers must deduplicate identical events rather than count raw lines.
- SRT capture's last packet is 520.863 s; it finishes 520.876 s, during the failed
  writer restart. Generation 3 resumes encoding at 522.174 s. `Capture` retries
  initial connection only; after a read failure it exits. Its failure to follow
  the new publisher is supported by source and timeline, although the precise
  low-level SRT close cause is not recorded. No capture observes generation 3.
- Generation 3 writes 20,984 manifest rows through 1207.812 s/final LIVE. A read-only
  FLV tag audit finds 20,984 encoded video data tags and 32,789 audio data tags
  in its 226,625,526-byte archive. The source writes manifest rows only after
  encoding and network mux return, supporting actual writer/connection recovery;
  these are not a substitute for independent post-recovery decoded egress.

The maximum encoded wall gap is 22.525 s, presentation gap 22.511 s, and measured
write/reply/cleanup call 15.934 s. A nominal five-second reply deadline does not
prove a five-second real-time recovery bound when the host cannot schedule or
complete cleanup promptly. Privacy-safe offline recovery means no substitute
source pixels cross egress; it does not satisfy the uninterrupted-cadence gate.

The retry contains 11,896 slate rows out of 35,944 (**33.096%**). Of these, 9,324
have `ingest-gap` coverage (78.38%). Before any egress recovery, generation 1
already has 3,362 slate rows. The failed publisher leaves no source until the
replacement's first generated frame at 668.552 s, approximately 153.338 s after
the sender error. From resumed generation 3 output at 522.174 s to the planned
668.006 s reconnect, 4,789 written rows are all HOLD/slate. The longest slate run
is 4,927 rows from 522.174–672.593 s; LIVE returns at 672.613 s, 1.608 s after manual
release and 4.061 s after the replacement sender's first generated frame.

This argues against a recovery hold remaining permanently latched. The extended
slate is explained by a real publisher outage plus missing-input/protection
conditions; it cannot be attributed solely to CPU starvation. There are 115
accepted input sessions, 1,001 disconnections, queue 8/8 and last input failure
`input-backpressure`. Those disconnections include failed reconnects during
the publisher outage, not 1,001 proven queue overflows. Walk-day timing
qualification requires a quiet host; a dedicated relay host is a practical
operating condition to validate, rather than a demonstrated cure. Neither
causation by CPU alone nor a sufficient priority adjustment has been
demonstrated. Upstream publisher reconnect behavior must also be exercised
before a phone/walk claim.

Retry sampled RSS peaks at 1,298,856 KiB; thread range 29–84 and FD range 56–122.
As in attempt 2, the sampler excludes the encoder worker and GPU/VRAM. The
session survives, but this retry remains incomplete and timing-unqualified.

## Implementation and integration

The Linux path is MediaMTX → authenticated loopback RTSP/TCP → the existing
shared `MaskingEngine` → one NVENC encoder → MediaMTX. RTMP and SRT publication
converge on one reader. RTMP/SRT listeners bind only 100.109.49.77 or 127.0.0.1;
RTSP is 127.0.0.1 TCP-only. No wildcard/IPv6/UDP RTSP/extra service is enabled.
Startup requires the child process's own listener inodes and fails occupied
ports without stopping an incumbent.

Phone credentials publish only `camera`; internal credentials read `camera`
and publish `shielded`; anonymous viewers may read only `shielded`. Publisher
override is disabled. Runtime credentials travel in memory/stdin/private spawn
pipe, never config files, env, argv, logs or receipts. Explicit TTY-only phone
setup displays once; automated runs suppress it. Libav text is suppressed and
MediaMTX diagnostics become allowlisted fixed codes in bounded rings. MediaMTX
read/write timeouts are 10 s; engine deadlines govern privacy independently.

Cold startup submits a black frame under transport HOLD through the engine.
The sole pixel writer consumes only `engine.poll` results. A deliberate
source-frame bypass failed the structural check, followed by exact restoration
and green. Queue overflow invalidates its input generation. Reconnect clears
old PCM; missing/out-of-window audio becomes silence. Each 30 fps output carries
1,600 mono 48 kHz samples at matching PTS. The native run uses Tiny 8 Hz/640,
Small 4 Hz/960, D=1 s, phase 320/floor .05/pad .3/B=6/A=30, ORT CUDA with CPU operator
fallback permitted. This policy is not a quality-qualified configuration.

Bounded recovery restarts **only egress** after a write deadline, first reaping
its old worker. Engine, ingest and controls remain alive. Failed/precomputed
batches and old audio are discarded. A fresh engine result establishes output
under current HOLD/protection state, and only a network-ready ACK clears the
internal egress hold. Moderator/local/EventSub holds remain independent. At
most five reconnects per 60 s with 250 ms backoff; then `egress-recovery-limit`.
One frame is in flight. Separate archive generations preserve prior bytes;
manifest rows append an `egress_generation`; pending/recent event rings cap 64.
Numeric shared-memory operation diagnostics survive a native worker stall.
There is no production RTMP parser/control-message bridge or timestamp clamp.

M3 uses `relay.runtime.run(..., control_ready=register_callbacks)` in the same
process; the callback receives `hold(active, source, reason)` and
`set_stream_key(key_or_none)`. The key stays in memory. Twitch remains a
bandwidth-test-only interface **stub**, with no network implementation, login,
key retrieval or live publication. Root/M3 own Infisical and CLI integration.
One-command setup/run instructions: [README.md](README.md). Existing Mac NUT
experiment remains; this Linux launcher has no Mac native qualification.

## Tests, diagnoses and retained red evidence

Full Linux functional gate 73 passed: 96 default tests with one Mac-only skip,
19 M2 tests and compileall. Receipt:
[73-full-gate.json](/tmp/agents/irl-shield/m2-relay/73-full-gate.json),
[complete log](/tmp/agents/irl-shield/m2-relay/73-full-gate.log).
The parent ran the full gate itself. No Mac Swift/VideoToolbox run or independent
quality bench was available here. Root grades sealed outputs after its corrected
scorer integration; this lane neither uses the old pooled scorer nor PP-only self-grading.

| Invocations | Evidence |
| --- | --- |
| 1–38 | Parent probes 01–20 plus 18 implementation-child invocations; red receipts preserved |
| 39–42 | Encoder dimensions/header and stale-audio repro/fix; affected 16M2 tests green 42 |
| 43 | Full Linux 96(default, 1 Mac skip)+16 M2+compile pass |
| 44–47 | Four original native queue executions, all red; two pre-exec rejections excluded |
| 48–50 | Capture diagnoses (receipt filenames44–46): empty capture, real Matroska startup failure, raw MPEG-TS capture/decode green |
| 51–52 | Capture/safe-error changes, affected 16M2 tests pass |
| 53 |38 s diagnostic pilot: safely exposed network-mux broken pipes, contended |
| 54–55 |4 s publisher gap red with3 s timeout, same repro green with10 s default |
| 56 | Full Linux gate passes |
| 57–58 |60 s RTMP/SRT native A/V executions, both contended; RTMP green, SRT red |
| 59 | Exact captured DTS regression reproduces real Matroska ValueError(errno22) |
| 60–61 | Earlier20-minute soak fails at 1007.492 s; actual read-ACL matrix passes uncontended |
| 62–64 | High-origin reconnect helper cleanup red, corrected real reconnect green, high-output-PTS CPU/NVENC encode/decode green |
| 65–67 | Operation-diagnostic red/green, full Linux gate green |
| 68–69 | Fragmented valid RTMP control reproduces network-mux hang; rejected bridge experiment fails startup and is removed |
| 70–71 | Recovery native tests: three intended red failures, then three green tests |
| 72–73 | Full Linux 96(default, 1 Mac skip)+19 M2+compile pass, before/after final bounded event-ring refinement |
| 74 | Session 3 queue ordinal 2, physical execution 1: native 20-minute exit 0, contended |
| 75 | Session 3 queue ordinal 5, physical execution 2: session survives two recovery events; incomplete captures, contended, 22.525 s wall gap. Budget CLOSED; no more executions |

Exact latest gate argv is retained by `.tmp/m2/full-gate-73.py` and its JSON/log;
all latest native argv, scoped public CUDA library paths, cwd and receipt
substitution are in [session3-soak-command.json](../.tmp/m2/session3-soak-command.json)
and the queue attempt receipt. Earlier exact commands, hypotheses and source
hashes remain in [LOG.md](LOG.md), child hand-backs, `/tmp/agents/irl-shield/m2-relay/`
and the [pre-audit hand-back archive](../.tmp/m2/M2-HANDBACK-before-v3-audit.md).

The three recovery tests use real sockets/CPU encoding/shared engine with
synthetic no-op detectors. Full Ping reaches 300 ACKs; fragmented Ping reproduces
93 ACKs/network-mux timeout before the fix, then two connections 120 ACKs after.
Backpressure actually saturates a LIVE write before the 6 s read pause and applies
moderator HOLD while blocked; green reaches two connections 309 ACKs with fresh
protected/HOLD/black generation 2 output and no stale index/batch replay. Five
refused reconnections exhaust in 2.358 s with the exact terminal code. All owned
workers/listeners were reaped. [RECOVERY-TESTS-HANDBACK.md](RECOVERY-TESTS-HANDBACK.md)
contains the red command/log; parent green/full receipts are under71/72/73-recovery.

The historical 1007 s timeout was a missing worker ACK, 339 s after reconnect;
its originating stalled operation remains unknown. High-origin reconnect and
high-output-PTS probes did not reproduce it. Probe 68 proves an FFmpeg RTMP
blocking mechanism under injected fragmented control, not attribution of the
historical stall. Bounded recovery covers write stalls without a production
protocol parser. Details: [STALL-ANALYSIS.md](STALL-ANALYSIS.md).

Direct RTMP reading crashes at `av.open`/`av_dict_free` in PyAV 16.0.1. GDB 19
and installed source support an inferred dynamic stream-option allocation/free
mismatch; no upstream library was patched. The live reader uses RTSP/TCP only.
Exact Python 3.11.14/FFmpeg library versions (libavformat62.3.100,
libavcodec62.11.100) are in `.tmp/m2/native-version-receipt.json`; crash receipts
remain. Earlier raw-SRT capture fixes avoid premature Matroska headers, rather
than masking a decoder crash.

**SRT phone publication is red and unsuitable for a walk claim.** The earlier
SRT→RTSP side capture reports DTS 83,970→83,229 at 1/90000; exact replay reproduces
Matroska errno22. Its replacement sender fails network-mux after 8 frames.
The main reader decodes rather than Matroska-remuxes; it delivered 970 offered
frames / 701LIVE generation 1 outputs, but main raw packet DTS was not recorded.
Its 17 mapped-index drops do not identify the raw regression (RTMP had 175 too).
All 684 outputs after the 44 s HOLD release remained HOLD. Whether main decode
encounters the identical raw DTS regression is unverified; no new execution was
spent on that question. Successful SRT *output capture* of RTMP ingest above
does not change this publication limitation.

## Read ACL, bindings and cleanup

The real read/publish-ACL job 046a95aa passes on 127.0.0.1 and 100.109.49.77,
including real three-packet RTSP reads after RTMP/SRT publication, denied
anonymous/bad/phone reads of camera, wrong role/path publication, process-owned
restricted bindings, env/argv credential absence and fixed-code diagnostics.
Uncontended other-busy mean 15.851%/max 18.975%, forced=false, server exit0.
Original seal `a5fe28931a2f0abecbfaa65eb64a32adaa9db514690cf944b501f9b6a425af8b`
and exact one-file inventory were independently verified:
[ACL parent audit](../.tmp/m2/acl-parent-audit.json).

All three queue runners exited; failed artifacts remain sealed. Session 3 at
`/home/elan/code/irl-shield/.tmp/irl-shield-builder-m2-queue-3` is sealed, its
job is `closed-one-shot`, and runner metadata says `drained`. Root runner
4177108 is independently confirmed absent. Exactly two physical executions
and three pre-exec rejections are recorded; the lane count is final at 75/76.

[Final cleanup audit](../.tmp/m2/v3-final-cleanup-audit.json) confirms retry wrapper
561481 and sampled main/MediaMTX/sender PIDs 561483/561485/561598/591574 absent;
no listeners remain on 18554 TCP, 19550 TCP or 19050 UDP, and no Python/MediaMTX/
FFmpeg candidate has this exact worktree cwd. Runtime cleanup errors are empty;
sender and MediaMTX stops are recorded. No local observer or native process is
retained, and no other session's process was stopped. The soak did not record
encoder-worker PID/start identities; the final cwd scan supports cleanup but
is not a complete historical process-tree inventory. No safe-stop action remains
for this lane; root's exited runner was never stopped by this implementation.

## Tools, models, licenses and installs

No sudo, account, payment, global config/package/driver/CUDA change or secret
inspection occurred. Root's pinned CUDA 12.4/ORTGPU 1.20.2 and GPU libraries/cache
are reused read-only. Owned `.tmp/m2/py311` contains PyAV 16.0.1; the unsuitable
initial Python 3.14 environment is unused. Install URL/wheel SHA is in
`.tmp/m2/av311-install.json` and `.tmp/m2/installed-tool-receipt.json`.

- MediaMTX v1.21.3, MIT: archive SHA256
  `0a2ea7eba96023631efa1bea7804823a9145b043b6646a8a05798d4ac24ed635`;
  binary `bfa372a169751bbf6da2ebddcbcd2f7d3ab3dca3cc553022162eda36fe03e73d`.
- PyAV 16.0.1, BSD-3-Clause. Its Linux wheel contains FFmpeg GPL components/
  libx264; LGPL-only labeling is insufficient. FFmpeg GPL-2.0-or-later and
  component notices apply. No native binary is committed or redistributed here.
- Preinstalled libsrt 1.5.4, MPL-2.0 with BSD portions; no install/redistribution;
  SHA256 `30af7a9de19c8644f76fcb3f8c0b269bc48b98271deaca497cfdc6ff4ed099b6`.
- PP-OCRv6 Tiny/Small, Apache-2.0: Tiny
  `193bab7a04fca699a6c82e6abb5b81bdb28177f0abd4062552b04908dafb19f8`;
  Small `d73e0058b7a8086bbd57f3d10b8bcd4ff95363f67e06e2762b5e814fe9c9410e`.
  URLs/revisions/parameters/providers/licenses are in native provenance and
  `models/manifest.json`; existing dependency records remain in
  `models/licenses/dependencies.json` and `bench/PORTABILITY.md`.
- sf-market tune fixture, CC BY 3.0, SHA256
  `bed20032b30bcdfebb32f137809b71cedf8486c7881020e5e955a91aa28aca7c`.
  Original synthetic labels/stamps/flashes/tones are CC0. Source audio is
  discarded; no music. **All existing fixtures and derivatives remain
  BENCHMARK-ONLY, not demo-ready.** Code/docs are English; repo remains private.

No root scorer was copied and no output was self-graded with PP alone. Every
sealed native output remains available for one corrected independent grade.
Outstanding: qualified timing/cadence; independent privacy/Q;
complete resource coverage; SRT publication/reconnect; independently decoded
post-recovery NVENC egress; Mac gate; owner-approved phone/Twitch integration.
None is claimed complete by functional exit 0.

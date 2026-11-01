# M2 runtime diagnostic receipt audit

ISSUES — the first executed diagnostic pilot finished and its original seal verifies. It reproduced a short runtime failure, with sender `BrokenPipeError` / errno 32 / `network-mux` preceding the encoder's structured `network-mux` failure. The receipts do not establish the originating cause or establish that this is the cause of the older soak failures. No fix or further producer run was performed by this collector.

Audit cutoff: 2026-10-30 05:59 UTC. The original M2 timebox remains approximately 03:55–11:55 UTC; it was not reset. Return on this first executed result, without waiting for the intentionally unsealed runner to exit.

## Worktree and authority

- Collector worktree: `WORKTREE_t3-4bccf43b`.
- Branch renamed in place from `t3/4bccf43b` to `elannash/m2-runtime-receipts`; HEAD remains `ec1d1f96a1c29ab82109c66f27064f3fd6cb326d`. Initial worktree was clean.
- Only owned writes: this untracked hand-back and ignored `.tmp/m2-runtime-receipts/audit.py` plus `audit.json`. No source changes, tests, media decoding, ML/native/GPU execution, API calls, installs, staging, commits, pushes, PRs, merges, queue changes, or process controls.
- Parent `WORKTREE_t3-ae860af9` was read-only. Skills read: receipt-audit, research; diagnosis source/hypothesis checks were also read before interpreting errors. No children or outbound messages.

## Evidence roots

These aliases below identify exact absolute paths, not alternate sources:

- **A** = `WORKTREE_t3-ae860af9/.tmp/m2/gate2-v2/runtime-diagnostic/attempt-2`
- **J** = `REPO_ROOT/.tmp/irl-shield-builder-m2-queue-2/linux/jobs/964a641f6a044396bca18921c192457a`
- **M** = `WORKTREE_t3-ae860af9/.tmp/m2`
- **C** = `WORKTREE_t3-4bccf43b/.tmp/m2-runtime-receipts`

Sample frame: only this job's artifacts, its single diagnostic attempt directory, the named driver/marker receipts, and hashes of provenance-listed parent files and the named source artifact. Other queue jobs and earlier native results were excluded. JSONL aggregates include every nonempty line once; no OCR, media interpretation, threshold selection, or resampling was performed. Per-file verification and numerical aggregations are in **C**`/audit.json`; the stdlib collector is **C**`/audit.py`.

## Queue execution accounting and raw semantics

At the cutoff there are two queue reservation directories, `001` and `002`:

| Reservation | Actual command invocation | Physical native pilot | Outcome |
| --- | --- | --- | --- |
| 001 | No | No | Pre-exec readiness rejection; `execution_started=false`, `execution_attempt=null`, return code null |
| 002 | Yes, execution attempt 1 | One evidenced pilot | Closed; command and wrapper return codes both 2; no stop reason |

Thus: **one executed queue command, one evidenced physical pilot, one pre-exec rejection, zero recorded marker refusals** in this job as of the cutoff. Reservations do not equal native attempts. Job state is `pending` after the failed command, because the queue remains unsealed/retry-capable; the result itself is finalized. This collector did not wait for, authorize, or request another command. A subsequent guard-only command would be a new command invocation but would not, by itself, prove another physical pilot.

Receipts: **J**`/job.json` (`attempts`, `preexec_rejections`, `state`), **J**`/attempts/001/attempt.json`, **J**`/attempts/002/attempt.json`, **J**`/attempts/002/command-exit.json`; **M**`/runtime-diagnostic-started.json` records `started_at=1793339720.0872898`, purpose `single native runtime diagnosis`. Reservation 002 spans 05:55:09.945–05:56:17.499 UTC, including readiness/final health sampling; command-exit time is 05:56:01.629 UTC. This is distinct from native runtime duration below.

The packet's pre-pilot whole-program counter was 52/58. This target contributes one executed command and one physical pilot; the collector contributes zero tests/native executions. The whole-program counter was not independently re-audited, and readiness rejection 001 spends no native attempt.

`forced=false` in both reservations. Reservation 002's start-health receipt has 81.127762% idle, 5,564,137,472 available bytes, `memory_ok=true`, `partial_cpu_window=false`: the recorded readiness sample exceeds 80% idle and 4 GiB. The inherited exclusive lease is recorded in **A**`/provenance.json:138`: `/tmp/agents/irl-shield/perf.lock`, device 66306, inode 29775811, `exclusive=true`, `nested_flock=false`. This audits recorded metadata; it does not re-acquire or test the lease.

Reservation 001 start/end idle readings were 75.870772% and 70.140382%, respectively. Its contamination fields are `valid=false`, `contended=true`, reason `cpu_accounting_unavailable`; these do not describe a native failure because nothing executed.

Reservation 002 retains `contamination_policy=other-busy-v2`, `contamination.valid=true`, `contended=true`, mean other-busy 40.581464%, max 61.525800%, reason `other_busy`, `benchmark_verdict=unassessed`. These fields are preserved without relabeling contended as invalid accounting, or interpreting contention as the runtime cause.

All four periodic samples report valid accounting with method `linux-proc-tree-own-plus-reaped-v2`, 8 CPUs, 100 clock ticks/second. Their reported percentages are host-capacity percentages; in each recorded sample `other_busy_percent = total_busy_percent - job_tree_busy_percent`:

| Periodic JSON array index | Total busy % | Job-tree busy % | Other busy % | Available bytes |
| --- | ---: | ---: | ---: | ---: |
| 0 | 60.224833 | 18.105143 | 42.119689 | 4,321,533,952 |
| 1 | 47.596762 | 24.973226 | 22.623536 | 4,891,574,272 |
| 2 | 63.123176 | 27.124007 | 35.999170 | 4,602,163,200 |
| 3 | 68.491592 | 6.965792 | 61.525800 | 5,754,863,616 |

Source: **J**`/attempts/002/periodic-health.json`, array elements 0–3 and their `cpu_accounting` objects; start/end health and finalized contamination are in the same attempt's JSON receipts. The end sample is 61.124570% idle, 5,431,066,624 available bytes. These are finite sampled windows, not proof that readiness conditions persisted continuously.

## First observable error ordering

| Monotonic time | Observation | Receipt |
| ---: | --- | --- |
| 111709.038293079 | RTSP reader finishes with `status=eof` | **A**`/rtsp/transport.json:1` |
| 111709.041323357 | SRT reader finishes with `status=read-ended`, `error_class=RuntimeError` | **A**`/srt/transport.json:1` |
| 111709.051116620 | Earliest timestamped sender/encoder exception: sender `BrokenPipeError`, errno 32, phase `network-mux` | **A**`/sender-01-exit.json:2` |
| 111709.344778019 | Runtime `EgressError`, output code `egress-write`, input code `input-open`; encoder phase `egress-write`, operation `network-mux`, `BrokenPipeError`, errno 32 | **A**`/runtime.json:3` |

The runtime failure observation is 0.293661399 seconds after the sender exception. The SRT reader's `RuntimeError` and EOF are transport termination observations, not proof of an earlier native encoder exception. The outer **A**`/failure.json:3` class is `RuntimeError`, phase `runtime`, status `incomplete`, with diagnostics suppressed; it does not supersede the structured encoder/sender receipts. Queue return code 2 is an executed-command result, not a pre-exec readiness failure or an observed wrapper/IPC timeout. No wrapper timeout is evidenced in the finalized queue receipt.

The sender process exited 2, `intentional_kill=false`, `stopped=true`, generation 1, according to **A**`/sender-processes.json:1`. Its top-level `failed=false` coexists with that nonzero exit and **A**`/sender-01-exit.json`'s `status=failed`; the latter records the native failure. MediaMTX exited 0 with `stopped=true` in **A**`/mediamtx-exit.json:1`; without an exit timestamp this does not locate MediaMTX's shutdown in the ordering or prove that it caused the failures.

**Cause still unverified.** The receipts show network-mux broken pipes and preceding transport termination, but do not establish why publication or the network path closed. `input_code=input-open` is reported without an independently timestamped input failure here. This audit does not identify a local fix, attribute the failure to contention, or equate this failure with either older generic soak failure.

## Native output, holds, transport, and bounds

Configured duration is 120 seconds; **A**`/runtime.json:17` records only **38.037523190 seconds**, `status=failed`, `output_frames=955`, empty `cleanup_errors`. **A**`/provenance.json` declares RTMP publication, NVENC, shared Tiny/Small CUDA-provider lanes, D1, SRT capture, and functional mode. These are recorded configuration, not independent proof of each hardware operation.

| Measurement | Receipt / aggregation scope | Recorded result |
| --- | --- | --- |
| Output manifest | **A**`/frames.jsonl:1` through line 955, all rows, unique index count 955 | Indices 0–954; PTS 0–31.8 s; 955/30 = 31.833333 s nominal coverage |
| Presentation wall span | Same rows, last minus first `presented_at` | 33.186425167 s; first 111672.559144932, last 111705.745570099 |
| Cadence gaps | All 954 adjacent presentation differences | Maximum 2.297759779 s; 16 gaps greater than 100 ms; max presentation lateness versus deadline 3.855533103 s |
| Manifest states | All 955 output rows | HOLD 341; PROTECT 110; LIVE 504; `protected=true` 451; slate 425; non-slate 530 |
| HOLD duration | State rows at declared 30 fps | 341/30 = 11.366667 s nominal; six runs, longest 89/30 = 2.966667 s (terminal run) |
| Terminal HOLD | **A**`/frames.jsonl:867` through line 955 | PTS 28.866667–31.8; not evidence of recovery |
| Manifest A/V | All output rows' `audio_pts_samples`, `audio_samples`, `pts`, declared 48 kHz | 1,528,000 samples; maximum absolute declared audio-PTS/video-PTS difference 0; no decoded sync measurement |
| Sender manifest | **A**`/sender-01.jsonl:1` through line 958 | Generation 1 only; indices 15–972; PTS 0.5–32.4 s; max `late_ms` 3833.176808 |
| Runtime sessions | **A**`/runtime.json:19`, `session` | 5 sessions, 29 disconnections; `video_drops=0`; `audio_dropped_samples=304008`; final audio buffer 0 / capacity 192000 |
| Input queue | **A**`/runtime.json:27` | Capacity 8, high-water 8; reached its bound |
| Engine | **A**`/runtime.json`, `engine` | 958 outputs, 454 protected, 0 late-ingest, final buffered 1, 0 buffer evictions |
| Lane/motion counters | Same `engine.lanes` and `motion_worker` | Fast completed 170 / failed 0; accurate completed 89 / failed 0; each offered 611; motion completed 611, dropped 0, errors empty, stopped |
| Engine transition evidence | Same `engine.transitions`, all 21 entries | Reasons: startup 1, ingest-drop 5, ingest-gap 5, covered 7, unresolved-motion-accurate-coverage 3 |

The engine's 958/454 counts and output manifest's 955/451 counts are different proof layers. This audit does not turn their three-frame difference into a measured transport drop or claim all engine emissions reached output. Non-slate flags establish manifest labeling only; no image was decoded or visually judged.

Declared bounds in **A**`/provenance.json:23`: engine buffer 68 frames; maximum 4 frames per poll; input queue 8; lane sample capacity 4096; decoder/encoder threads 2 each; concurrent sender bound 1; capture queue `none; packets remuxed synchronously`. Runtime sample capacity is 4096. Only final engine occupancy and recorded counters are available here; a continuous engine-buffer high-water proof is absent. Process thread counts below include the complete processes and do not measure encoder-thread-setting violations.

Independent transport receipts:

- RTSP: **A**`/rtsp/transport.json` says opened, 34 startup retries, 2278 packets, EOF; connected-to-finished interval 34.134788466 s. All 2278 **A**`/rtsp/packets.jsonl` rows total 9,059,722 payload bytes: 1389 nonempty audio packets and 889 nonempty video packets. Video PTS exists in 887/889 rows (two excluded from PTS range); video PTS range 0.034–29.595455556 s, audio range -0.000333333–29.588395833 s. Packet-arrival span 32.860567742 s; maximum adjacent arrival gap 2.010362417 s. Sealed container is `rtsp/network.mkv`, 9,075,811 bytes. Packet counts do not establish decoded frame count or audio alignment.
- SRT: **A**`/srt/transport.json` says opened, 34 startup retries, 8986 messages, 10,153,128 bytes, scope `SRT MPEG-TS message`, terminated `read-ended` / `RuntimeError`. All 8986 packet rows sum to that byte count; arrival span 34.150676888 s, maximum adjacent arrival gap 3.259036770 s. Sealed raw transport is `srt/network.ts`, 10,153,128 bytes. Message count is not a video-frame count, nor independent A/V decode proof.
- Existing `summary.json`, decoded summary files, and `capture_errors.json` are absent in this sealed inventory. Absence of `capture_errors.json` is not proof of error-free capture; the SRT transport JSON explicitly records termination. No offline decode or new decoded summary was generated by this collector.

Resource sample frame: all 36 **A**`/resources.jsonl` rows, monotonic 111671.570658507–111709.058104188, three listed PIDs per row; finite samples, not a soak or a whole-host inventory.

| PID / recorded role | RSS min–max KiB | Threads min–max | FD min–max |
| --- | ---: | ---: | ---: |
| 3490377 / runtime resource entry | 426644–928892 | 21–56 | 43–60 |
| 3490392 / MediaMTX exit receipt PID | 35920–47892 | 9–12 | 10–14 |
| 3490434 / sender process receipt PID | 9140–252304 | 1–16 | 6–45 |

Peak sum of listed process RSS in one sample is 1,227,512 KiB. Runtime recorded VmHWM reaches 932,420 KiB. GPU allocation telemetry and a long-duration memory plateau are unverified; the process RSS samples do not establish either. Per-process sample bounds and HOLD-run line ranges are retained in **C**`/audit.json`.

## Original seal and provenance verification

Original printed seal SHA-256 from **J**`/attempts/002/stdout.log`:

`f9bc76d821f2adf2a81c601a155e23736e446ab1786715d463f7f43a219ae896`

Read-only stdlib streaming verification found:

- **A**`/seal.json` hashes to exactly that original stdout digest. The expected seal was not regenerated or replaced.
- All **19** sealed file entries match both byte count and SHA-256. Directory inventory excluding `seal.json` has zero missing and zero extra files.
- All **61** `provenance.source_sha256` entries match the current parent-worktree files; no missing files or mismatches. This verifies those frozen bytes, not that the parent HEAD alone contains its working changes. Recorded parent branch is `elannash/m2-relay`, HEAD `ec1d1f96a1c29ab82109c66f27064f3fd6cb326d`.
- **M**`/session2-diagnostic-command.json`'s driver digest matches the current **M**`/diagnostic-pilot-once.py`: `c293095423cd2bf4bf9993a95089c0eb07d4d4b845268a342c48259325026c6e`. Direct argv was not reproduced in this report.
- The source artifact named by **A**`/source.json` matches its recorded SHA-256 `bed20032b30bcdfebb32f137809b71cedf8486c7881020e5e955a91aa28aca7c`. Model binaries, dependency installations, MediaMTX binary, and license URLs were not independently revalidated by this collector; provenance declarations are preserved as declarations.

**A**`/source.json:5` explicitly scopes the source as `BENCHMARK-ONLY; not demo-ready`. It records tune fixture `sf-market`, CC BY 3.0, 1280×720 at 30 fps, five-second source; original audio discarded, generated timing tones only, no music. Synthetic labels/flash/stamps/tones are declared CC0-1.0. **A**`/provenance.json` records Apache-2.0 for both models and MIT for MediaMTX. These license statements were read from receipts; no external licensing research was performed.

## Remaining proof and cleanup

- Privacy remains **PENDING**, awaiting corrected independent OCR after PR1 merge. Q is **unqualified** regardless of transport receipt integrity. No OCR grading or primary benchmark scorecard is available from this incomplete diagnostic run.
- Neither a completed 120-second diagnostic nor a 20-minute soak is proven. Older short soak failures remain unexplained; no old generic error is promoted into an identified cause.
- Decoded real-video quality, independent A/V sync, RTSP/SRT decoded success, complete reconnect recovery, long-duration queue/resource stability, and originating failure cause remain unverified. There is no green bench/gate claim. The packet's existing 16-test pass was not rerun or independently audited here.
- No observer was needed: command-exit already existed on initial inspection. No observer PID was created, no long-lived collector process remains, and there is nothing owned to terminate. The short stdlib collector exited. Scratch is retained under **C**, ignored by git.
- Root runner PID **3442769** was still present when checked and remains root-owned. Nothing was opened, sealed, stopped, requeued, or changed in its queue. Recorded diagnostic ports are TCP 18554, TCP 19550, UDP 19050; the sender/MediaMTX exit receipts say stopped, but no new live-port probe was run.
- Root-only stop command, retained for parent handoff and **not executed**: `REPO_ROOT/scripts/perf-queue --queue-dir REPO_ROOT/.tmp/irl-shield-builder-m2-queue-2 stop linux`.
- Collector handling note: an exploratory tool projection inadvertently printed oversized numeric telemetry arrays, and an initial helper path typo emitted a local `FileNotFoundError` traceback. The helper path was corrected; subsequent extraction used bounded projections, and neither output was copied into this hand-back. No runtime raw exception text or secret values were included in this hand-back.

Receipt-only work is complete. Parent should inspect the raw artifacts and decide the cause/fix and any further producer work; this child has no follow-up work.

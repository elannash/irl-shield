# M2 native queue receipt hand-back

**ISSUES — collection complete; no transport/20-minute/privacy gate pass.** All three jobs reached terminal queue states. The root runner drained and exited without collector intervention. Four native commands ran, all returned **2**; two additional reservations were rejected before execution. No collector tests, media processing, model/GPU/API calls, queue mutations, or process signals were performed.

Collected through 2026-10-30T05:33:28.812097+00:00; own observer exited 2026-10-30T05:32:57Z, exit **0**. Original M2 start ~03:55Z and cutoff ~11:55Z were retained; no timebox reset. This hand-back completes before the cutoff.

## Checkout, authority, and execution accounting

- Dedicated worktree: `WORKTREE_t3-0d32c18a`. Prepared branch `t3/m2-queue-receipts` was renamed in place to requested/actual **`elannash/m2-queue-receipts`**. Base and current HEAD: `ec1d1f96a1c29ab82109c66f27064f3fd6cb326d`. No worktree created or removed; no stage, commit, push, PR, or merge.
- Owned uncommitted deliverable: `relay/QUEUE-HANDBACK.md` (untracked, intentionally not staged). Ignored collector-only scratch: `.tmp/m2-queue-receipts/`. No implementation changes. Parent source was read only.
- **6 queue reservations / 4 executed native commands / 2 pre-execution rejections.** Starting from the supplied parent baseline **43/52 executed**, the updated count is **47/52 executed**. Do not charge a native execution for a `rejected_before_exec=true` reservation, or omit either executed soak attempt because it was contended. Collector test budget used: **0**.
- Accounting, command-exit receipts, CPU recomputation, log fingerprints, and process/port checks: [final state audit](WORKTREE_t3-0d32c18a/.tmp/m2-queue-receipts/final-state-audit.json:1). Native queue state, not agent state, determined completion. Observation chronology: [observer events](WORKTREE_t3-0d32c18a/.tmp/m2-queue-receipts/observer.jsonl:1).

| Job | Final queue state | Queue slots | Native executions | First available fixed failure code / phase |
| --- | --- | ---: | ---: | --- |
| m2-rtmp-av | `failed` | 2 | 1 | command/wrapper **2**, `decoded-analysis` |
| m2-srt-av | `failed` | 1 | 1 | command/wrapper **2**, `decoded-analysis` |
| m2-soak | `exhausted-contended` | 3 | 2 | command/wrapper **2**, `runtime; unintentional sender exit 2` |

The fixed phases are from sealed `failure.json`; credentialed exception details are suppressed. No deeper exception/code or ordering of internal failures is claimed. A failed command is distinct from readiness rejection and from contamination.

## Every attempt, including red and rejected receipts

| Attempt | Command / wrapper exit | Rejected before exec | Forced | Contended | Other-busy mean / max (%) | Raw queue receipt |
| --- | --- | --- | --- | --- | --- | --- |
| m2-rtmp-av #1 | None / None | True | False | True | unavailable; no command | [attempt.json](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/359c4d901f1a4d35b5152a7132be0a0b/attempts/001/attempt.json:1) |
| m2-rtmp-av #2 | 2 / 2 | False | False | False | 12.593 / 15.516 | [attempt.json](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/359c4d901f1a4d35b5152a7132be0a0b/attempts/002/attempt.json:1) |
| m2-srt-av #1 | 2 / 2 | False | False | False | 11.983 / 28.088 | [attempt.json](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/ecab6ba5f532409291ee08a32cbe7a8f/attempts/001/attempt.json:1) |
| m2-soak #1 | 2 / 2 | False | False | True | 30.619 / 100.000 | [attempt.json](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/b33563fb522d46bbb49dd4c6d6a302f8/attempts/001/attempt.json:1) |
| m2-soak #2 | None / None | True | False | True | unavailable; no command | [attempt.json](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/b33563fb522d46bbb49dd4c6d6a302f8/attempts/002/attempt.json:1) |
| m2-soak #3 | 2 / 2 | False | False | True | 17.393 / 47.752 | [attempt.json](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/b33563fb522d46bbb49dd4c6d6a302f8/attempts/003/attempt.json:1) |

RTMP #1 and soak #2 are **pre-execution readiness rejections**, with null command/wrapper exits and no native artifact directory. Their unavailable periodic CPU accounting is expected for no execution; it is not a native test failure. RTMP #1 start idle was 74.842%; soak #2 start idle was 78.947%. No manual retry, reopen, requeue, seal, readiness override, or lock action occurred.

All six attempt directories retain their original files. Where produced, these include `attempt.json`, `stdout.log`, `stderr.log`, `command-exit.json`, `start-health.json`, `periodic-health.json`, `end-health.json`, child/launch/sampling files. Raw stdout/stderr were read locally and retained in place; stderr text/private argv were not copied into this hand-back. File hashes and line/byte counts are in the final audit; original native seal prints are in each executed attempt’s stdout. Queue receipt target `summary.json` is absent for all four executions.

## Original seals and artifact audits

The expected digest in every audit came from the **original queue stdout print**, never from a newly generated seal. Python stdlib streaming hashes verified the existing seal bytes, schema, exact file inventory, sizes, every manifest file hash, absence of symlinks, and stdout output-directory identity. No native code or tests were executed for these audits. All four seals verify (**82 manifest entries across four bundles**), while each bundle contains an empty SRT capture; integrity does not make a failed artifact complete.

| Executed attempt | Original printed seal SHA-256 | Entries | Audit / raw stdout |
| --- | --- | ---: | --- |
| m2-rtmp-av #2 | `cf3f2d2b3f8667f5fc6f1686ef375a162cd142217b74010cb917c1285ee7159b` | 22 | [audit](WORKTREE_t3-0d32c18a/.tmp/m2-queue-receipts/m2-rtmp-av-attempt-2-audit.json:1) / [stdout](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/359c4d901f1a4d35b5152a7132be0a0b/attempts/002/stdout.log:1) |
| m2-srt-av #1 | `d47a3b7020e11fd6cfa5e27351447917ec91c42ccb153ebeccc5086e11904365` | 22 | [audit](WORKTREE_t3-0d32c18a/.tmp/m2-queue-receipts/m2-srt-av-attempt-1-audit.json:1) / [stdout](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/ecab6ba5f532409291ee08a32cbe7a8f/attempts/001/stdout.log:1) |
| m2-soak #1 | `7d451e4deaa17c5243499d88f7cdea58cb8681a0ff71b621dce4c80845ca0277` | 19 | [audit](WORKTREE_t3-0d32c18a/.tmp/m2-queue-receipts/m2-soak-attempt-1-audit.json:1) / [stdout](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/b33563fb522d46bbb49dd4c6d6a302f8/attempts/001/stdout.log:1) |
| m2-soak #3 | `81afba40d734558f53fd38275c9c0cbea0fa0401111f5a2e9322caebee1774f2` | 19 | [audit](WORKTREE_t3-0d32c18a/.tmp/m2-queue-receipts/m2-soak-attempt-3-audit.json:1) / [stdout](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/b33563fb522d46bbb49dd4c6d6a302f8/attempts/003/stdout.log:1) |

- **m2-rtmp-av #2:** [failure](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-rtmp-av/attempt-2/failure.json:1) · [runtime](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-rtmp-av/attempt-2/runtime.json:1) · [source](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-rtmp-av/attempt-2/source.json:1) · [provenance](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-rtmp-av/attempt-2/provenance.json:1) · [seal](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-rtmp-av/attempt-2/seal.json:1) · [frame/PTS rows](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-rtmp-av/attempt-2/frames.jsonl:1) · [resources](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-rtmp-av/attempt-2/resources.jsonl:1) · [sender exits](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-rtmp-av/attempt-2/sender-processes.json:1) · [MediaMTX exit](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-rtmp-av/attempt-2/mediamtx-exit.json:1) · [listeners](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-rtmp-av/attempt-2/listeners.json:1).
- **m2-srt-av #1:** [failure](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-srt-av/attempt-1/failure.json:1) · [runtime](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-srt-av/attempt-1/runtime.json:1) · [source](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-srt-av/attempt-1/source.json:1) · [provenance](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-srt-av/attempt-1/provenance.json:1) · [seal](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-srt-av/attempt-1/seal.json:1) · [frame/PTS rows](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-srt-av/attempt-1/frames.jsonl:1) · [resources](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-srt-av/attempt-1/resources.jsonl:1) · [sender exits](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-srt-av/attempt-1/sender-processes.json:1) · [MediaMTX exit](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-srt-av/attempt-1/mediamtx-exit.json:1) · [listeners](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-srt-av/attempt-1/listeners.json:1).
- **m2-soak #1:** [failure](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-soak/attempt-1/failure.json:1) · [runtime](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-soak/attempt-1/runtime.json:1) · [source](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-soak/attempt-1/source.json:1) · [provenance](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-soak/attempt-1/provenance.json:1) · [seal](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-soak/attempt-1/seal.json:1) · [frame/PTS rows](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-soak/attempt-1/frames.jsonl:1) · [resources](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-soak/attempt-1/resources.jsonl:1) · [sender exits](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-soak/attempt-1/sender-processes.json:1) · [MediaMTX exit](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-soak/attempt-1/mediamtx-exit.json:1) · [listeners](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-soak/attempt-1/listeners.json:1).
- **m2-soak #3:** [failure](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-soak/attempt-3/failure.json:1) · [runtime](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-soak/attempt-3/runtime.json:1) · [source](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-soak/attempt-3/source.json:1) · [provenance](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-soak/attempt-3/provenance.json:1) · [seal](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-soak/attempt-3/seal.json:1) · [frame/PTS rows](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-soak/attempt-3/frames.jsonl:1) · [resources](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-soak/attempt-3/resources.jsonl:1) · [sender exits](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-soak/attempt-3/sender-processes.json:1) · [MediaMTX exit](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-soak/attempt-3/mediamtx-exit.json:1) · [listeners](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-soak/attempt-3/listeners.json:1).

- **m2-rtmp-av #2, additional raw receipts:** [stderr](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/359c4d901f1a4d35b5152a7132be0a0b/attempts/002/stderr.log:1) · [command exit](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/359c4d901f1a4d35b5152a7132be0a0b/attempts/002/command-exit.json:1) · [start health](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/359c4d901f1a4d35b5152a7132be0a0b/attempts/002/start-health.json:1) · [periodic health](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/359c4d901f1a4d35b5152a7132be0a0b/attempts/002/periodic-health.json:1) · [end health](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/359c4d901f1a4d35b5152a7132be0a0b/attempts/002/end-health.json:1) · [SRT transport](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-rtmp-av/attempt-2/srt/transport.json:1) · [fault events](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-rtmp-av/attempt-2/events.jsonl:1) · [RTSP decoded summary](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-rtmp-av/attempt-2/rtsp/decoded-summary.json:1) · [RTSP decoded PTS rows](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-rtmp-av/attempt-2/rtsp/decoded.jsonl:1).
- **m2-srt-av #1, additional raw receipts:** [stderr](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/ecab6ba5f532409291ee08a32cbe7a8f/attempts/001/stderr.log:1) · [command exit](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/ecab6ba5f532409291ee08a32cbe7a8f/attempts/001/command-exit.json:1) · [start health](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/ecab6ba5f532409291ee08a32cbe7a8f/attempts/001/start-health.json:1) · [periodic health](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/ecab6ba5f532409291ee08a32cbe7a8f/attempts/001/periodic-health.json:1) · [end health](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/ecab6ba5f532409291ee08a32cbe7a8f/attempts/001/end-health.json:1) · [SRT transport](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-srt-av/attempt-1/srt/transport.json:1) · [fault events](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-srt-av/attempt-1/events.jsonl:1) · [RTSP decoded summary](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-srt-av/attempt-1/rtsp/decoded-summary.json:1) · [RTSP decoded PTS rows](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-srt-av/attempt-1/rtsp/decoded.jsonl:1).
- **m2-soak #1, additional raw receipts:** [stderr](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/b33563fb522d46bbb49dd4c6d6a302f8/attempts/001/stderr.log:1) · [command exit](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/b33563fb522d46bbb49dd4c6d6a302f8/attempts/001/command-exit.json:1) · [start health](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/b33563fb522d46bbb49dd4c6d6a302f8/attempts/001/start-health.json:1) · [periodic health](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/b33563fb522d46bbb49dd4c6d6a302f8/attempts/001/periodic-health.json:1) · [end health](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/b33563fb522d46bbb49dd4c6d6a302f8/attempts/001/end-health.json:1) · [SRT transport](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-soak/attempt-1/srt/transport.json:1) · [fault events](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-soak/attempt-1/events.jsonl:1).
- **m2-soak #3, additional raw receipts:** [stderr](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/b33563fb522d46bbb49dd4c6d6a302f8/attempts/003/stderr.log:1) · [command exit](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/b33563fb522d46bbb49dd4c6d6a302f8/attempts/003/command-exit.json:1) · [start health](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/b33563fb522d46bbb49dd4c6d6a302f8/attempts/003/start-health.json:1) · [periodic health](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/b33563fb522d46bbb49dd4c6d6a302f8/attempts/003/periodic-health.json:1) · [end health](REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1/linux/jobs/b33563fb522d46bbb49dd4c6d6a302f8/attempts/003/end-health.json:1) · [SRT transport](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-soak/attempt-3/srt/transport.json:1) · [fault events](WORKTREE_t3-ae860af9/.tmp/m2/gate2/m2-soak/attempt-3/events.jsonl:1).

For both short runs, `rtsp/decoded-summary.json` and `rtsp/decoded.jsonl` exist and were read; SRT decoded receipts do not exist. For both executed soak attempts, **neither RTSP nor SRT decoded summaries/rows exist**, because the runtime failed before decoded analysis. `summary.json` is absent in every executed attempt. All four `srt/network.mkv` files are **zero bytes**; their transport receipts say `opened=true`, `status=read-ended`, `packets=0`. Each SRT packet log contains a row, so `packets=0` is the transport’s completed/remuxed counter, not proof of no network receipt. No missing decoded file is treated as a zero-error continuity pass.

## What the available receipts actually exercise

| Measurement | RTMP #2 | SRT #1 | Soak #1 | Soak #3 |
| --- | ---: | ---: | ---: | ---: |
| Requested seconds | 30.000 | 30.000 | 1200.000 | 1200.000 |
| Runtime seconds | 38.213 | 38.227 | 30.228 | 435.290 |
| Written output frame rows | 1105 | 1104 | 715 | 12909 |
| LIVE, non-slate frame rows | 612 | 597 | 532 | 11806 |
| Protected frame rows | 493 | 507 | 183 | 1103 |
| Scheduled-stall-window protected rows | 109 | 118 | 0 | 109 |
| Hold rows / violations | 203 / 0 | 203 / 0 | 0 / 0 | 0 / 0 |
| Runtime sessions / disconnections | 2 / 39 | 5 / 10 | 3 / 16 | 19 / 33 |
| Audio dropped samples | 148764 | 319173 | 190837 | 1212775 |
| Input queue high-water / capacity | 8 / 8 | 8 / 8 | 8 / 8 | 8 / 8 |
| RTSP decoded frames | 1015 | 1014 | UNAVAILABLE | UNAVAILABLE |
| RTSP decoded span (s) | 33.819 | 33.784 | UNAVAILABLE | UNAVAILABLE |
| RTSP max video PTS gap (s) | 0.054 | 0.054 | UNAVAILABLE | UNAVAILABLE |
| RTSP nonincreasing video PTS | 0 | 0 | UNAVAILABLE | UNAVAILABLE |
| RTSP spatial-content / optical-match frames | 646 / 519 | 623 / 453 | UNAVAILABLE | UNAVAILABLE |
| RTSP A/V pairs | 18 | 15 | UNAVAILABLE | UNAVAILABLE |
| RTSP A/V offset median (ms) | 22.198 | 7.042 | UNAVAILABLE | UNAVAILABLE |
| RTSP A/V absolute p95 (ms) | 38.691 | 15.375 | UNAVAILABLE | UNAVAILABLE |
| Unpaired flashes / beeps | 0 / 8 | 1 / 11 | UNAVAILABLE | UNAVAILABLE |
| Native 20-minute observation | not requested | not requested | NOT COMPLETED | NOT COMPLETED |

Counts use the complete raw frame-row stream per attempt, not pooled runs or unique source images. RTSP decoded counts, audio sample counts, timestamp ordering/gaps and spatial/optical flags were re-enumerated from existing decoded JSONL using stdlib, with no media re-decoding. Both short RTSP captures have no video gap over two 30fps frame periods and no nonincreasing audio/video PTS. These are partial capture checks, **not an overall transport pass**. A/V values are the existing native optical-onset / frequency-coded-tone measurements (matching only within ±8 seconds); no additional synchronization threshold or privacy pass is claimed.

Both short fault schedules completed: hold start ~20.5s, intentional generation-1 sender kill ~21.5s, reconnect ~24.5s, release ~27.5s. Their 203 hold rows each have zero metadata violations. Soak #1 and #3 record only sender-start: no scheduled hold/kill/reconnect/release event occurred before early failure. Their zero hold violations are **not a passed hold guard**. The soak #3 stall-window count is frame metadata only. Both soak senders exited 2 without intentional-kill status. No native 1,200-second span or decoded soak continuity/A/V measurement is available. There is no native `transport_guards_pass=true` summary.

## Source, readiness, bounds, and resource limits

Each executed `source.json` declares the **sf-market tune fixture**, CC BY 3.0, 1280×720 at 30fps, 5-second source footage looped by the harness; generated labels `742 CEDAR LANE` / `19 ORCHARD WAY`, optical/flash marks and timing tones are CC0-1.0. It declares original source audio discarded and no music. These are source metadata receipts, not a new visual/audio or license review. All footage and derivatives remain **BENCHMARK-ONLY; not demo-ready**. The short RTSP captures’ spatial-content and optical-match rows support real video in those captures, not an independent privacy verdict. No held-out split or old pooled OCR scorer was used.

Every executed provenance bundle records parent branch `elannash/m2-relay` at `ec1d1f96a1c29ab82109c66f27064f3fd6cb326d`; all **61 source hashes in each of the four bundles** matched the frozen parent at audit time. They declare `h264_nvenc`, CUDA detector backends, and a canonical exclusive lease with `nested_flock=false`. This establishes recorded provenance and source consistency, not full GPU utilization or independent backend execution coverage.

Readiness requires ≥80% host idle and ≥4 GiB available memory. The runner was repeatedly observed alive at identity `3141521@10617088`, sleeping in `futex_do_wait`, while readiness records advanced; early samples below 80% explain the wait. [sanitized readiness/identity/lock snapshots](WORKTREE_t3-0d32c18a/.tmp/m2-queue-receipts/readiness-snapshots.jsonl:1). No waiting-only interval was graded as native failure.

`other-busy-v2` periodic contamination uses interval-weighted other-busy CPU (total busy minus measured job-tree busy): mean >20% or any sample >40% is contended; unavailable accounting or bad memory also contaminates. All four executed attempts had valid recorded periodic accounting and passing memory samples. The collector recomputed their means/maxima from the raw samples and matched every queue claim. Soak #1 exceeded mean and peak; soak #3 exceeded peak despite mean <20%. Forced execution is always contended; **all six reservations here were unforced**, and no stop reason was recorded. Root policy remains force 2026-10-30 15:00Z (08:00 PT), hard stop 16:00Z (09:00 PT); neither was reached. The collector’s earlier original cutoff never changed.

Input high-water stayed 8/8 in all executed attempts. Provenance declares engine buffer capacity 68, max 4 frames per poll, lane sample capacity 4096, 2 decoder/encoder threads, one concurrent sender, and synchronous capture remuxing. End-state engine buffer counts are snapshots, **not measured peak occupancy**. No unrecorded engine/encoder queue or resource bound is certified.

| Resource receipt scope | RTMP #2 | SRT #1 | Soak #1 | Soak #3 |
| --- | ---: | ---: | ---: | ---: |
| Resource sample rows | 39 | 39 | 28 | 435 |
| Main-process peak sampled RSS (KiB) | 932656 | 930724 | 947296 | 947572 |
| Periodic CPU health samples | 6 | 6 | 4 | 44 |
| Accounted CPU interval seconds | 53.606 | 56.327 | 30.233 | 432.801 |

Resource JSONL covers the harness main process, MediaMTX, and sender PIDs only. Encoder worker/spawn-helper RSS, threads and FDs are omitted; GPU/VRAM is unmeasured. Per-PID sampled RSS/HWM, thread and FD maxima are retained in each collector audit. Periodic queue CPU-tree accounting is broader than that resource sampler, but sampling cannot certify unsampled transient workers. No full-process memory ceiling, no-leak result, or 20-minute endurance result is claimed.

## Stop receipts and remaining work

All four runtimes have `cleanup_errors=[]`; each MediaMTX exit receipt is `exitcode=0, stopped=true`. Both short runs record generation 1 intentionally killed with exit -9 and generation 2 stopped with exit 0; their generation-1 standalone exit file is absent. Both soak runs record the sole sender stopped with unintentional exit 2 and a `sender-01-exit.json` status of `failed`. No `cleanup-failure.json` was produced. The collector checked **28 unique recorded/sampled PIDs**, including observer, root runner, queue children, resource PIDs, and CPU-tree members: all `/proc/<pid>` paths were absent. No bound listener remained on 18554/TCP, 19050/UDP, or 19550/TCP at the final snapshot. These are point-in-time checks; encoder shutdown lacks a dedicated standalone encoder-exit receipt.

Own observer PID **3186229** exited normally (0), confirmed absent. Root runner PID **3141521** drained and was confirmed absent; it was never signaled by the collector. **No expressly retained queued jobs, PIDs, or ports remain.** Historical root-owned safe-stop command, not executed:

```text
REPO_ROOT/scripts/perf-queue --queue-dir REPO_ROOT/.tmp/irl-shield-builder-m2-queue-1 stop linux
```

**Unverified / unfinished:** overall transport guards; any SRT decoded output, PTS continuity or A/V offset; the requested native 20-minute span; decoded soak video or A/V; soak scheduled hold/reconnect completion; independent pixel-level hold/stall correctness; comprehensive encoder/GPU resource coverage; underlying suppressed runtime/decoded-analysis exception details. No implementation fixes or reruns were authorized here. Parent owns audit and any follow-up. **Privacy grade remains PENDING corrected independent OCR after PR1 merge; Q not qualified**, even for partial RTSP measurements. Prior parent 96+16 gate claims were not rerun or independently regraded.

Skills used: `receipt-audit` (claim/artifact/limit separation) and `research` (sample frame, measurement inclusions, and raw evidence pointers). Raw red receipts remain in their original queue/native directories; scratch contains only observer/audit artifacts, no copied media or implementation.

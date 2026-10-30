# M1 evidence and overnight measurement hand-back

Snapshot: 2026-10-30 03:11 UTC / October29 evening PT. Gate1 has not passed;
held-out grading is pending. Overnight queued work is explicitly authorized.
This report distinguishes accepted timing from incomplete privacy qualification. All footage, stills and masked previews are benchmark-only, not
demo-ready; they can contain third-party brands/logos and contain no music.

## What the numbers mean

The primary unit is a string × visible interval. One readable output frame
fails the entire interval. The seven tune clips contain435 natural intervals
across natural and synthetic variants, and54 known synthetic visible intervals.
The same physical sign can contribute in both variants. Scope is Latin-script
text and Arabic digits observed by English-configured judges: Tesseract eng,
Vision accurate en-US and PP-OCRv5 English-mobile. Natural input truth requires
confidence>=.9 on at least two frames; any output judge reading at>=.5 can expose
a leak. Known synthetic visibility gaps start new intervals, while natural OCR
gaps remain continuously scored. Non-Latin, single-frame natural text and text
all input judges miss remain unproven.

The discriminating controls hide0/61 natural and0/4 synthetic intervals without
masks. A slate also earns0/61 and0/4 because it fails the real-video guard.
All54 current tune synthetic input controls are readable. Receipts:
[controls](../bench/results/judge-controls.json) and
[measurement contract](../bench/README.md).

## Detector comparison

The initial four-model comparison uses the same intended source clock: fast8Hz
at640px, accurate4Hz at1280px (PP max-side960), D1s, B6/A30, padding.3,
phase320 response floor.5 and fixed-shape PP sessions. It is ideal/offline
content quality, with detector completion at source PTS; it cannot establish
wall throughput or latency. The 8.19% protection rate invalidates every row.
Raw hiding is retained to show the trade, rather than selecting on optimistic
privacy credit from protected frames.

| Accurate candidate | Weight/runtime license and source | Portability | Natural hidden | Difference from Vision | Synthetic hidden | Median masks | Protected | Real video |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Vision accurate + rectangles | Apple SDK/framework terms; [Vision](https://developer.apple.com/documentation/vision); weights not redistributed | macOS only |370/435=85.06% | reference |48/54=88.89% |10.85% |8.19% |pass |
| PP-OCRv5 mobile | Apache-2.0 weights; [model card](https://huggingface.co/PaddlePaddle/PP-OCRv5_mobile_det); ORT MIT | Mac Core ML/CPU and Linux CUDA/CPU exercised; Windows untested |385/435=88.51% |+3.45pp |46/54=85.19% |12.22% |8.19% |fail |
| PP-OCRv6 small | Apache-2.0; [model card](https://huggingface.co/PaddlePaddle/PP-OCRv6_small_det_onnx); ORT MIT | same portable interface |393/435=90.34% |+5.29pp |46/54=85.19% |13.00% |8.19% |fail |
| PP-OCRv6 tiny | Apache-2.0; [model card](https://huggingface.co/PaddlePaddle/PP-OCRv6_tiny_det_onnx); ORT MIT | same portable interface |353/435=81.15% |−3.91pp |46/54=85.19% |11.53% |8.19% |fail |

PP-OCRv6 medium is also scored, with a different actual encoded CUDA policy:
Tiny fast8Hz/Medium accurate4Hz, phase floor.05, dynamic ONNX. It hides380/435
natural (87.36%) and44/54 synthetic (81.48%), with13.22% median masks and.333%
protection. Real video fails. The matched static Small actual CUDA run has the
same380/435 and44/54 counts,13.78% median masks and.619% protection; real video
fails too. These are contended diagnostics, and they do not establish a medium
quality win. The static Medium retry did not drain and is incomplete.

Source-card identities, exact options and current counts are in
[the tune comparison](../bench/results/m1-tune-comparison.json). Weight revisions,
SHA-256s and licenses are in [the model manifest](../models/manifest.json).

## Quality hill climb

E1 changes only motion. Against the initial Small/Tiny baseline393/435 natural,
46/54 synthetic,8.19% protection, lowering the phase floor to.2 gives368/435,
46/54 and1.81%; floor.05 gives369/435,44/54 and.286%. ORB plus the existing
phase fallback gives376/435,41/54 and2.762%. Every row fails real video. None is
a guard-valid winner. Lower protection removes optimistic hiding credit; a
smaller protection percentage alone is not a privacy improvement.

The .5→.6 box-confidence follow-up loses42 natural intervals:327/435 natural,
44/54 synthetic,11.744% median masks,.286% protection, real-video false.
Rejected. Vision with only phase floor.05 gives337/435 natural,47/54 synthetic,
11.558% median masks,.286% protection, real-video true. It is still below gate
quality. The Small/Tiny30Hz follow-up completes385/435 natural,46/54 synthetic,
15.560% median masks and.286% protection. It improves16 natural and two
synthetic intervals, but real video remains false and it is rejected. Vision30Hz gives355/435 natural,46/54 synthetic,14.214% median masks and
.286% protection, with real-video false. Reject. The frozen diagnostic policy
therefore retains Vision8Hz/4Hz with phase floor.05; no tune winner passes all
guards. The15% proposed median-area ceiling is frozen before held-out in
[gate-1-policy](../bench/gate-1-policy.json).

The main retained causes are intermittent mask coverage, detector omissions and
brief edge entries. In the initial Vision policy,55 of65 failed natural
intervals have a zero-overlap leak, ten only partial overlap;31 have a zero-overlap
leak despite an accepted same-frame accurate result. Nonexclusive attributes
include15 near-edge,12 small-text and seven fast-pan intervals. A concrete PP
failure on clear pavement returns a95.3%-of-frame Tiny quad and99.8% Small quad.
This directly explains a real-video failure; it is not evidence that every
large detection can safely be filtered. Known two-frame synthetic edge entries
at78–79 and148–149 remain in truth. See [LEAKS](../bench/LEAKS.md),
[the E1 receipt](../bench/results/e1-motion-comparison.json), and
[the append-only experiment log](../bench/LOG.md).

## Host comparison and sustained performance

All numbers below are measured, rather than configured frame rates. Performance
uses a repeated licensed San Francisco workload, 1,200 actual encoded frames:
300 startup/warmup plus 900 steady frames over 30 seconds. D is1.0s in every row.
Quality columns use the corresponding all-seven-clip **ideal/offline tune** card;
these score mask content at the intended source schedule, not physical lane
completion. They must not be mistaken for the same sustained movie's privacy
score or a held-out pass. All three quality policies fail at least one guard.

| Host | Detector lanes | Encoder | Natural hidden | Synthetic hidden | Median masks | Steady p95 | Emitted fps | Protected, steady | Load1 start→end; minimum sampled idle |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| M1 Pro, Vision | rectangles30Hz + union4Hz | VideoToolbox |355/435=81.61% |46/54=85.19% |14.214% |1.210s |30.118 |0% |2.53→2.21;64.10% |
| M1 Pro, Vision-free | Tiny8Hz + Small4Hz, Core ML | VideoToolbox |369/435=84.83% |44/54=81.48% |12.692% |1.199s |30.125 |0.111% |2.85→2.41;73.13% |
| i7-7700K +1080Ti | Tiny8Hz + Small4Hz, CUDA | NVENC |369/435=84.83% |44/54=81.48% |12.692% |1.127s |30.078 |0% |1.42→1.51;69.93% |
| i7-7700K, CPU detection | Tiny8Hz + Small4Hz, ORT CPU | NVENC |same ideal policy, native privacy ungraded |same |same |1.125s |30.077 |0% |.96→2.84;50.03% |
| i7-7700K, fully CPU | Tiny8Hz + Small4Hz, ORT CPU | libx264 |same ideal policy, native privacy ungraded |same |same |1.066s |30.009 |0% |.77→2.60;46.60% |

The actual encoded static Small/CUDA tune card, measured while contended, has
380/435 natural,44/54 synthetic and13.777% median masks, rather than the ideal
369/435 card above; real video still fails. Host timing and ideal quality are
reported separately because asynchronous completion can change mask coverage.
No joint quality/performance winner is established.

Mac CPU-only detector lanes with VideoToolbox also qualify at30.152fps,
1.199s p95,0% steady protection,227.74% CPU and706.86MiB peak RSS.
Its first packet is1.492s and mean/max other busy11.56%/29.58%; both recorded
active providers are CPUExecutionProvider only. Encoding still uses Apple hardware.
Mac upscaled1080p Core ML/VideoToolbox reaches30.116fps,1.205s p95,0%,
111.47% CPU and799.78MiB; it is a processing-cost receipt, not native1080p truth.

On Linux, Tiny30Hz/Small4Hz CUDA reaches30.079fps and1.128s p95,0% protection,
CPU182.34% and1,277.34MiB peak tree RSS. Upscaled1080p reaches30.069fps,
1.185s,0%,CPU187.70%,RSS1,434.58MiB; this measures1080p processing cost,
not native1080p text quality. Medium4Hz/Tiny8Hz CUDA now completes a clean
static sustained receipt at30.072fps,1.124s p95,0%,CPU158.23%,RSS1,486.79MiB.
Its earlier dynamic quality card is not silently assigned to that static run.

The fully CPU row records only CPUExecutionProvider for both lanes and a literal
libx264 encoder command, with CPU377.78%,RSS720.31MiB,first packet1.273s,
other-session busy mean3.20%/maximum4.91%. The fresh CPU-detection/NVENC row
uses358.70% CPU,RSS843.66MiB,first packet1.166s,mean/max other busy2.3%/3.2%.
CPU-only timing therefore works on this host/workload; a claim that a GPU is
required would be unsupported. Independent native CPU privacy qualification is
still pending. Vision CPU-only execution is not implemented and is never inferred
from a `--provider cpu` label.

Mac Small/Core ML uses98.84% CPU,RSS528.83MiB,first packet1.446s; Vision30 uses
117.79% CPU,RSS954.70MiB,first packet1.395s. Linux CUDA8 uses155.73% CPU,
RSS1,248.93MiB,first packet1.136s. One core equals100% throughout. CPU/RSS use10ms process-tree samples over
the trial, including decode/encoder drain and engine close; primary latency,
protection and wall output rate use steady frames only. Packet timing is the
observed FFmpeg mux-progress upper bound, not network or glass-to-glass delay.
First-packet startup is relative to the established source clock. Model loading
and preflight/warmup time are separate raw receipt fields; these packet numbers
are not total cold application startup. Neither is charged as recurring frame
latency. Endpoint
memory is normal on all accepted rows. Raw START/END memory-pressure, swap,
load and during-job samples are retained with every attempt.

Five-repeat stage CPU diagnostics use identical retained SF input/quads. Median
projection plus rendering is1.350ms/frame for Mac Vision,1.366ms for Mac Small,
and3.247ms for Linux Small. Motion is1.859/1.761ms on Mac and3.004ms on Linux.
These are CPU costs, excluding timeline/control/transport, under recorded
warn/critical pressure; they establish no clean wall latency. The clean full
poll CPU is1.743ms/output for Mac Small,2.371ms for Vision30,4.561ms for
Linux CUDA8,7.275ms for CUDA30 and4.503ms for CPU/libx264. Device execution
is not attributed as CPU. The under8ms emit-path CPU target is met on these
sustained workloads, without a guarantee for arbitrary numbers of quads.

Accepted/rejected joined rows, options, startup, coverage and lane rate summaries:
[Linux](../bench/results/perf-queue-linux.json),
[Mac](../bench/results/perf-queue-mac.json).
The first two Linux movies/mask archives were independently hash/PTS audited in
[/tmp/agents/irl-shield/m1-perf-queue/linux-first-clean-artifact-audit.json](/tmp/agents/irl-shield/m1-perf-queue/linux-first-clean-artifact-audit.json).
The other rows are accepted from hash-bound benchmark frame/packet counters plus
closed queue evidence; an additional independent whole-movie audit is not claimed.

## Contamination policy proof and historical labels

The owner's revised policy measures other sessions' CPU, not the benchmark's
own CPU. Readiness remains>=80% idle plus normal memory. During a job,
other_busy=max(0,total_busy−identity-bound job-tree busy), as percent of host
capacity. A duration-weighted mean above20%, any sample above40%, unavailable
accounting or bad memory rejects trust. Linux includes waited child CPU without
double counting; Mac credits stable descendants conservatively. A departed or
unproven child remains other load. During-job Mac global ticks use the installed
Mach host_statistics API so final partial windows are measured. START/END and
readiness retain the requested top/memory_pressure/sysctl commands.

Both hosts passed the actual four-core-job / separate-three-core-burner /
remove-burner proof. These are real processes, not mocked sensor values:

| Host | Clean-before mean other busy | Separate burner mean | Clean-after mean | Proof |
| --- | ---: | ---: | ---: | --- |
| Linux |3.30% |39.46%, contended: other_busy |2.18% |pass, violation, revert, pass |
| Mac |3.78% |41.21%, contended: other_busy |5.47% |pass, violation, revert, pass |

All four owned workers were credited; no separate burner PID was credited.
Every known proof identity exited, with cleanup recorded. Receipts:
[Linux](../bench/results/other-busy-proof-linux.json) and
[Mac](../bench/results/other-busy-proof-mac.json).
The counter implementation is hash45dbdd1a8745e14b1573adadc218b9d1c00de66183a02ebd97942beca36eaeed.

History is not relabeled. Requested original Mac rows are:

| Historical job | Original label | Minimum sampled idle | fps / steady p95 |
| --- | --- | ---: | --- |
| root-ppocr-v6-small-coreml-720-fast8 |uncontended, accepted |73.13% |30.125 /1.199s |
| root-vision-union-coreml-720-fast30 |uncontended, accepted |64.10% |30.118 /1.210s |
| root-vision-union-coreml-720-fast8 |contended, retained |59.75% |30.133 /1.206s, diagnostic |

The first two never crossed the old60% rule and stay accepted. The third has
a fresh linked `-v2` job10e1ab8da0094039a97e876707de989f; its original attempt
stays held. Linux CPU attempt1 remains contended at23.61% idle/401.02% CPU.
The new linked `-v2` qualification passed under the revised rule; history was
not rewritten.

## Gate1 and held-out

**Gate1 is not passed.** No tune configuration meets all privacy/real-video
guards. The first frozen held-out measurement completed, but its mean other-session
load20.0586% exceeds the20% limit. It remains contended. Attempt2 rejected before execution; attempt3 also completed, but a sample
exceeded40% other busy (about42.0%). The measurement job is exhausted-contended. The one-shot grader is queued/running
with attempt3, the last complete contended plan; no quality count is invented before its final card; pending counts are not called zero or inferred
from tune. Scope is **Latin-script text and Arabic digits; judges Tesseract eng,
Vision accurate en-US and PP-OCRv5 English-mobile**. Non-Latin is unproven.

| Held-out criterion | Status at snapshot | Receipt/limit |
| --- | --- | --- |
| Natural hidden>=90% |pending held-out |frozen diagnostic tune337/435=77.47% |
| Synthetic hidden100% |pending held-out |tune47/54=87.04% |
| Median masked area<=15% |pending held-out |proposal frozen before grading; tune11.558% |
| Real-video guard |pending held-out |frozen tune passes; portable higher-recall rows fail |
| D<=1s |configured1s, actual presentation recorded |held-out measurement pending |
| Steady p95<=1.3s, source-rate720p30 |accepted separate sustained workloads on both hosts |same-policy held-out join pending |
| Protected frames<2% |pending held-out |tune aggregate.286%; stronger per-clip check fails |

The15% median ceiling is justified by10.85%/11.56% real-video-preserving Vision
medians, allowing3.44percentage points above the lower-protection policy while
retaining85% of the frame at the median. The per-LIVE-frame outside-mask guard
still requires at least50% real video. The proposal cannot rescue another failure.

Selected diagnostic policy: Vision union4Hz1280 + rectangles8Hz640, D1,
B6/A30,phase320 floor.05,padding.3. Policy hash is
f9cda20e6c60c29601ee6ddf25ea0d9bd01cbf0d1f9e5ece37b9c0d3039b27ed.
Held-out measurement job0cb3636276794a17b2de710d18c318c2 may retry for host
trust without OCR; grade jobbbe7774e838b468098e48903b807c97a selects by
closed measurement evidence before grading, then grades once and verifies reuse.
Both jobs migrated before first execution, with a source-revision ledger, to immutable
`.tmp/m1-final-source-v2`, pipeline hash264dcc9b4abfd0c7ca5d7dc0a75143bc0f165a23a18a28e003e801b55d60706f.
The detector/area policy did not change. Final Mac results will be
`out/m1-heldout-final/scorecard.json` and canonical `out/scorecard.json`.

## Queue lifecycle and verification

Linux runner **PID2773686**, nice10 in `app-t3code-agents.slice`; Mac runner
**PID74976**, nice10. Both are detached with nohup and use the canonical local
`/tmp/agents/irl-shield/perf.lock`. Their start identities are recorded. Safely
request stop with `scripts/perf-queue stop linux` or
`scripts/mac --no-sync scripts/perf-queue stop mac`; these do not signal a stored
possibly reused PID. Logs/metadata are in each root checkout `.tmp/perf-queue/`.
The owner expressly requested these overnight survivors. Runners stop by
Friday09:00PT; jobs still waiting at08:00PT run as labeled contended diagnostics.
Linux submissions are sealed after all18 planned jobs finish or retain their
failure; runner2773686 is now **drained and exited**, with identity_matches=false
at02:54UTC. Do not send a signal to this historical PID. Mac remains open only for
queued GStreamer setup. A root producer-complete marker permits setup to seal
Mac after submitting its five exact jobs. FAST's unperformed Mac work is not
silently added as a new overnight job. Hard stop remains09:00PT.

Priority1 root timing runs precede priority2 lane timings. One-shot held-out
OCR is priority3. Mac GStreamer SDK/data setup is priority4 after M1 work, and
records per-attempt Homebrew before/after inventories before submitting its own
five priority2 jobs. Untimed quality work must hold a shared lease and no new
long quality work starts while timing is queued. Full details:
[PERF-QUEUE](PERF-QUEUE.md).

Root full Mac verification passes **96 M1 tests (one Linux-procfs integration
skip),3 relay tests, compileall and optimized Swift compilation**. The first Mac
run correctly failed when a Linux-only real-procfs integration was not scoped;
the explicit platform skip leaves its Linux real-process proof required.
[/tmp/agents/irl-shield/m1-perf-queue/root-v2-mac-gate-fixed.log](/tmp/agents/irl-shield/m1-perf-queue/root-v2-mac-gate-fixed.log)
retains the complete green run. Fifteen worker counter-policy red/green logs
were hash checked, with17 focused tests green. The live proof above exercises
both native implementations beyond synthetic parser cases.

No checkpoint-after2dd52a6 change is staged or committed. The conductor owns
review, commit, PR and merge.

## Reproduce and changed files

From a clean Linux checkout with the documented Mac alias, after the overnight
queues drain or are cooperatively stopped, the **one complete measurement
command** is the command in [README](../README.md). It performs
repo-local setup, hash-pinned fixture/model provisioning, Swift compilation,
all-seven-clip tune measurement/judging and the30-second sustained workload,
then writes `out/scorecard.json` and one-screen baseline deltas. It reproduces a
diagnostic policy, not a pass. Raw direct cards require a closed queue join
before performance can establish gate acceptance. Use a new run ID for another
run. The one-shot held-out command is reserved and already queued.

A full fresh ten-clip download/setup from an empty checkout has **not** been
rerun; one cold clip provision and all ten existing hash checks were verified.
Mac-specific three-judge grading remains required. Linux setup/private CUDA
pins and direct native commands are in [LINUX_BENCH](LINUX_BENCH.md) and
[PORTABILITY](../bench/PORTABILITY.md). Exact installs, dependency side effects,
model/dataset licenses and pending installs are in [INSTALLS](../bench/INSTALLS.md).
No paid service, credential, global Python package or host driver was installed.

Core code and contracts: `shield/{engine,motion,timeline,control,render}.py`,
`bench/{clocked_pipeline,clocked_bench,scoring,judges,onnx_detectors}.py`,
`Sources/VisionBridge/main.swift`; fixtures/manifests/license attribution and
model manifests. Post-checkpoint root changes add motion/quality experiment
runners, `bench/perf_queue.py`, the joined reporter and one-shot held-out grader,
`scripts/{perf-queue,host-lock}`, associated tests and receipts, requirements/setup
refinements, README, architecture, taxonomy, queue and hand-back documentation.
Use `git diff 2dd52a6` plus untracked paths for the current review scope; the
checkpoint already includes the earlier M1 implementation authored here.

## Separate M2 groundwork and merit lanes

M2 owns `relay/`, `scripts/m2-*`, `tests/m2/`, `requirements-relay.txt` and
[docs/M2-GROUNDWORK.md](M2-GROUNDWORK.md). Historical local RTMP reaches240frames,
relay median640.7ms/p95700.2ms, additional median469.3ms and24.1ms audio lead.
SRT reaches240frames but p95 is2.398s and the direct baseline failed, so it is
provisional. The network numbers predate the asynchronous engine; current
adapter tests establish NUT/frame/HOLD behavior, not new network latency.
All34 owned media processes/ports were confirmed stopped. Homebrew SRT provides
SRT despite the unchanged Mac FFmpeg build. No Twitch or public network was used.

Merit-lane branches remain separate and uncommitted at2dd52a6, without an M1
source merge: `elannash/m1-gst`, `elannash/m1-openvino`, and `elannash/m1-fast`.
GStreamer transport and OpenVINO adapters are implemented; native timing is now
landing through the root queue. GStreamer retains experimental status: its old
diagnostic pair showed no accepted advantage and full720p SRT/RTMP/Mac/OCR
qualification is incomplete. OpenVINO's fresh Linux CPU-detector/NVENC sustained
row reaches30.067fps,1.157s p95,0% protected,242.16% CPU; native privacy and
Mac sustained-stream qualification remain pending. Its comparison job stops on the frozen v1
warning-pressure guard after Tiny640 and Tiny960; Tiny960 fails strict box
parity. The GStreamer all-tune measurement likewise stops on that v1 warning
guard after partial clips. Queue accounting is clean in both, but neither
incomplete artifact qualifies. Frozen lane health policy and old labels are
not silently rewritten to the root's newer Linux memory adapter. FAST reaches its three-hour timebox with hash/queue-verified detector costs:
CPU640 p50/p95288.15/312.71ms, CPU1024752.17/788.14ms,
CUDA64033.08/38.48ms and CUDA102464.15/68.42ms. OnnxTR and its pinned weights
are Apache-2.0: [runtime license](https://github.com/felixdittrich92/OnnxTR/blob/06fd099fd48510f4202d1fb43db5ed23d5f61c80/LICENSE),
[weight model card](https://huggingface.co/Felix92/onnxtr-fast-tiny/blob/f694deb1e32bddfd96d33be5e1e7b804564594ab/README.md).
Root retrieved the pinned model card and verified its declared license and hash. All-seven FAST/union privacy, area, complementarity, Core ML
cost and stream fps remain unmeasured. Root independently verified all four
runtime receipt hashes/sizes, normal endpoint memory, closed queue accounting,
current source fingerprint171449fd, weight hash28867779 and unchanged earlier
manifest entries. The eight-test log is read; a root rerun/full gate for that
branch and full code review are not claimed. Exact49-package private installs
are listed in INSTALLS.
The Mac OpenVINO CPU comparison is now complete and clean: other busy mean12.52%,
maximum26.99%, normal recorded memory. Three repetitions across21 frames from
all seven tune clips yield63 full calls per runtime/model/side. Tiny640 ORT vs
OpenVINO total-call p50/p95 is24.69/28.35 vs26.80/27.87ms; Small960 is
139.96/142.27 vs123.47/127.71ms. Tiny960 and Small640 also complete; all four
native box-parity checks pass. This establishes CPU-call/parity evidence, not
Mac stream throughput or privacy. Root checked the closed queue and exact raw
artifact hash/size. [Compact receipt](../bench/results/openvino-mac-comparison.json).
Its private27-package Mac SDK installation is recorded in INSTALLS.

Each lane keeps its own `bench/LOG-*.md`, private venv/mirror and artifacts for
conductor review. Root has not accepted their implementation as a replacement
or merged their code. Lane install and source receipts remain in their worktrees.

## Remaining limits and next step

One transport-free engine runs on both hosts, with backend/encoder configuration.
Core ML/CUDA/CPU are exercised; Windows is untested. No primary deployment host
is selected because privacy still fails. Linux timing is competitive, including
a completely CPU path, so Apple hardware is not required by the engine design.
The full current judge set still needs Mac Vision.

Live phone footage, live Tailscale, Twitch publish/chat/Shield Mode, SRTLA,
reconnect command deduplication and formal control-state verification remain
unproven. The next quality work should target the retained zero-overlap and
edge-entry failures and false giant quads, measured on tune with the same
independent judges. Review the FAST diversity and OpenVINO/GStreamer receipts
on merit before choosing a primary host. Complete the already-frozen held-out
one-shot evaluation and report it without further tuning on that split.


The separate lane artifacts are retained without a code merge:

- GStreamer: `/home/elan/.t3/worktrees/irl-shield/t3-ae5d7088/.tmp/gst/HAND_BACK.md`;
  <t3-thread://v2/a3857748-9579-4ce2-b37e-5d3cd3faad44/thread:delegated-task:command%3Amcp%3A3d408788-9494-4f24-96dd-9cc912db980d%3Adelegate-task%3Afc9fe6f7-02ea-46b8-b4a3-0e1c30a80d6c>.
- OpenVINO: `/home/elan/.t3/worktrees/irl-shield/t3-14dc4ccc/.tmp/openvino/handback.json`;
  <t3-thread://v2/a3857748-9579-4ce2-b37e-5d3cd3faad44/thread:delegated-task:command%3Amcp%3A3d408788-9494-4f24-96dd-9cc912db980d%3Adelegate-task%3A31d78287-84e1-459f-a446-28c31f60b6c4>.
- FAST: `/home/elan/.t3/worktrees/irl-shield/t3-1b7da09d/out/fast-handback.json`;
  <t3-thread://v2/a3857748-9579-4ce2-b37e-5d3cd3faad44/thread:delegated-task:command%3Amcp%3A3d408788-9494-4f24-96dd-9cc912db980d%3Adelegate-task%3A1c712348-2ce6-4780-b349-c6c9699b0175>.

Root audit is `.tmp/m1/merit-lane-audit.json`. The three-branch result summary
was queued to the conductor; all code remains separate, unstaged and uncommitted.


## Final attribution follow-up and failed Linux jobs

The conductor's20:06PT hypothesis remains **untested**: Apple Vision/Core ML
may induce CPU in XPC/ML services or kernel_task outside the job tree. The
existing stable-descendant lower bound can also leave new/departed job children
uncredited. Neither explanation is established by the native burner proof.
No service CPU is subtracted or relabeled. High END idle alone does not prove
that earlier job-window samples were clean.

Two matched Vision8Hz/30Hz diagnostic jobs are now queued after the active
held-out grader, with the same frozen pipeline/flags and exclusive host lease.
They record total/job/other busy plus the top five stable non-job processes by
CPU delta and executable basename, and uncredited endpoint job PIDs. This
permits a rate comparison without guessing names from unrelated historical
PIDs. The observer does not change production classification. CPU attribution
and names are separate endpoint scans with their scan times retained; short-
lived external processes can be absent from the top-five list. A synthetic
endpoint arithmetic/exclusion check and Mac compilation pass; native execution
and causal analysis are pending. Packet `.tmp/m1/service-diagnostic-jobs.json`;
observer `.tmp/m1/mac-service-observer.py`. If service attribution is confirmed,
a separate change and renewed external-burner proof are still required before
any named service receives an exclusion.

| Failed Linux job | Retained cause | CPU queue status |
| --- | --- | --- |
| gst-linux-gst | Ljubljana traffic preflight: legacy v1 full-memory PSI avg10=.25% exceeds its<.1% normal threshold despite8.74GB available; all-clip run stops |clean, other mean1.77%/max5.18% |
| gst-linux-nut | Ljubljana traffic preflight: legacy v1 full PSI avg10=.47% with8.48GB available; all-clip run stops |clean,9.18%/31.48% |
| gst-linux-network | GStreamer source supplies no video for ten seconds; ingest failure propagates, local SRT receipt incomplete |clean,9.43%/10.07% |
| openvino-linux-compare | v1 warning-pressure guard stops before the remaining Small cases; Tiny960 strict parity also fails in the retained completed subset |clean,1.68%/2.10% |

These four failures are command/benchmark failures under clean queue CPU
accounting, not evidence of missing Linux plugins. Their original stderr,
partial artifacts and labels remain intact. Raw attempts are under root
`.tmp/perf-queue/linux/jobs/{7b22173a250345feabda70f634d3e727,707989e5b6374199a79d7e155587a67c,64f65ecfaca747c581623f07e39531d1,7cf65773a5e84dd9b0ac1ee7ef15a19d}`.


Final builder cutoff: approximately03:13UTC /20:13PT. The Mac grader is still
running; no held-out privacy count or final scorecard is available. This is a
partial timebox hand-back under the authorized overnight-queue plan, not a
claim that the milestone definition of done is met. Mac runner74976 remains
identity-verified; Linux2773686 is drained/exited. The retained root resume note
is `.tmp/m1/RESUME.md`; no root/manual benchmark or proof burner survives outside
the authorized Mac queue. Three merit lanes are finished; all branches remain
uncommitted for conductor review. The one-line M1 hand-back notice is queued to
the conductor alongside this hand-back.

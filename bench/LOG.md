# Tune experiment ledger

All measurements are on M1 Pro. Held-out clips stay unopened until the final run.

| Run | Change | Natural intervals | Synthetic intervals | End-to-end fps | Decision |
| --- | --- | --- | --- | --- | --- |

## Instrumentation checks before pilot

Five initial scoring checks passed on Mac; fresh read-only review found four boundary cases:
long/moving OCR gaps, longer OCR readings discarded by deduplication, small contained fragments,
and one-digit house numbers. Exact counterexamples were reproduced by the reviewer and added
at the scoring boundary; the scorer retains longer readings, links across the clip and
interpolates gap geometry. Natural intervals remain inferred and this limit is documented.
A synthetic input readability control and separate 30fps-paced latency measurement now gate
acceptance. These are measurement corrections, not detector tune iterations.

`pilot-vision-fast` was aborted during the first accurate judge's ANE model compilation;
stack samples are in Mac `out/vision-stack.txt` and `out/pilot-stack.txt`. Its partial
30-frame natural pipeline measured15.29fps and residence p95 .392s; no quality scorecard
was produced and it is not an accepted detector measurement. Retry changes only requested
recognition languages from four Latin languages to en-US; it adds a30s response deadline.

## Positive-control calibration (no detector tuning)

`control-unmasked` exposed a failed natural judge:83/138 natural intervals and87/157
synthetic-variant natural intervals were falsely hidden on no-mask re-encoding. Inspecting
raw readings showed mostly low-confidence isolated Tesseract fragments on non-text. The
initial primary result is invalid for detector selection. Input confidence and temporal
support were calibrated against this negative control, retaining output leak thresholds:

| Input confidence | Required observations | Natural control hidden/total | Synthetic-variant natural control hidden/total |
| --- | --- | --- | --- |
| .5 | 1 | 83/138 | 87/157 |
| .8 | 2 | 1/32 | 3/42 |
| .9 | 2 | 0/30 | 1/36 |
| .9 | 3 | 0/27 | 0/33 |

Freeze input confidence>=.9 and>=2 observed frames per inferred interval. This keeps more
brief text than3-observation filtering and leaves one false-hidden interval in66 (1.52%)
on this control. Output judges still count readings at>=.5 (Tesseract>=50), making leak
checking more sensitive than truth creation. Excluded unstable intervals are recorded,
not silently absorbed. Natural results now explicitly cover persistent high-confidence
OCR-observed Latin text; one-frame-only natural text remains unproven. Synthetic labels
are never dropped by this filter and still require the unmasked control. The per-frame
truth before filtering remains in the evidence for audit. New detector measurements use
this frozen calibration. Calibration receipts: `out/control-unmasked/*evidence.json`.

The `control-slate` run correctly grants0/62 natural and0/4 synthetic intervals privacy
credit despite no OCR on output; video guard fails, mask area100%. Nine scoring tests
passed on Mac. Corpus frozen at10 source clips (7tune,3heldout),5s720p30 each, all muted;
Commons source-license snapshots and prepared hashes are tracked. Full comparison starts
with Vision accurate+rectangles, PP-OCRv5mobile, PP-OCRv6small, all common parameters.

`control-unmasked-calibrated` rerun with the frozen thresholds:1/62 natural intervals
falsely hidden(1.61%),0/4 synthetic hidden, real-video pass,0% masks. This replaces the
placeholder baseline. Full tune bake-off uses the same judge thresholds for every detector.
Earlier pilot natural metrics had the uncalibrated denominator and are retained only as
instrumentation history, not valid comparative results.

Speed probes (no quality judges; not gate scores): PP-OCRv5mobile CPU960 max-side minimum
5.77fps across two5s variants; dynamic CoreML3.09fps across two2s variants, with28/24
CoreML graph partitions and CPU fallback. Neither reaches the target. These probes ran
beside one judge job and are conservative, not isolated sustained measurements. Static
ONNX input shapes are being checked independently before deciding whether to pursue them.

## Second measurement review

A fresh read-only review reproduced a denominator false pass: merging two separate
MARKET occurrences could turn9/11 hidden into9/10. Natural association now requires
spatial overlap with the last or constant-velocity predicted box, retaining interpolation
for OCR gaps. Counterexample is in tests/test_metrics.py. All trial observations are
retained; bench.regrade applies this same corrected scorer to every completed trial,
writing new artifacts and preserving original cards. The calibrated unmasked control
regrades to0/61 natural and0/4 synthetic hidden. This is the new baseline reference.

Gate receipts now bind source SHA, actual pipeline+bridge executable fingerprint,
900+actualframes at expected resolutions/rates/pacing, consistent FPS accounting, and
finite latency. Every annotated synthetic interval must be readable in the source;
previous5% unobservable allowance removed. Failures in cleanup close all lanes; scripts/mac
uses a process-group watchdog on synced runs. New codec and transport-free frame-buffer
tests accompany extraction of shield.engine.MaskingEngine. This source extraction adds
an owned frame snapshot so future transport buffers can be reused safely.

Owner portability steer: prefer portable models when quality/speed are close; test winner
CPU as well as acceleration and check Linux. Linux CUDA probes completed on two PP models;
receipts and scope are in bench/PORTABILITY.md. Windows remains untested. All previews and
clips remain benchmark-only under the new Hackathon rules at HEAD8e8868d.

## Deadline engine restructure (tune only; held-out still untouched)

The conductor replaced the synchronous gate with D<=1s, encoded added latency
p95<=1.3s,720p30 source-clock output and<2% protection. Historical synchronous
cards cannot pass this gate. `shield.engine` now owns the delay buffer, newest-frame
worker lanes, deadline-filtered timeline, motion projection, explicit coverage,
control state and render seam. The legacy engine remains only under `bench` to
reproduce earlier reference runs.

TDD slices at the public frame/control interface went red before green: no coverage
protects at the deadline; both lanes allow LIVE; foreign-scene masks cannot replace
fresh same-scene coverage; protection escalation measures from the missed deadline;
nonfinite timestamps/rates are rejected before starting the clock; empty detections
cannot bridge scene cuts; input-buffer overruns become protected gaps; input arriving
after its deadline is dropped even before poll; subnanosecond early polls emit nothing;
and overdue output batches are bounded so HOLD can intervene. Motion, lane, control,
render and clocked-adapter child receipts are retained under `/tmp/agents/irl-shield/`.
Global transforms are cached across clues from the same detection; no identity fallback
is invented when motion is unknown. Vision now reuses requests and returns quads.

| Run | One change / finding | Quality delta | Performance / decision |
| --- | --- | --- | --- |
| clocked-smoke-tiny | First real paced integration | Not judged | FFmpeg rejected `.01` stats_period; corrected to `0.01`, reran. No scorecard accepted. |
| clocked-smoke-tiny-v2 | Correct FFmpeg syntax | Not judged |86% protection, encoded p95 2.694s; reference bake-off contended. Failed, diagnostic only. |
| clocked-smoke-tiny-cv1 | Limit nested OpenCV thread pool to1 | Not judged |72.67% protection, encoded p95 2.550s; isolated own heavy jobs. Still failed; retain the concurrency cap and fix the adapter. |
| clocked-profile-tiny | Diagnostic profiler, same detector configuration | Not judged | Source5s took8.89s in drive; sink writes3.87s and rendering2.06s. Profiling overhead prevents a throughput claim. Decode producer was independent but ingest submission still serialized behind egress; correcting that seam. |

The reference bake-off was interrupted cleanly at a judge call to free the Mac.
Completed pipeline files and per-frame OCR cache remain available for resume; this
is not a detector failure or an accepted partial quality card. No held-out run has
been opened or used for these decisions.

Independent review reproduced two more clock defects: input arriving after its
deadline could become LIVE before the first poll, and an epsilon early poll could
pass a negative protection duration to the renderer. Both were reproduced red
and fixed at the engine seam. The legacy `vision-scheduled` composite is rejected
by the clocked adapter because it relabeled old accurate boxes with the newest
frame index. Completion-time/coverage-age boundary cases are now retained tests.

`bench.faults` exercised real worker scheduling on synthetic video: fast-lane
stall22/54protected, accurate-lane stall22/54, ingest drop12/54, and a scene cut
during a detector stall5/54. Every scenario emitted all54source-clock frames;
no uncovered LIVE or raw protected output escaped. These intentionally injected
fault fractions are not normal-performance scores. Receipt:
`/tmp/agents/irl-shield/m1-faults/receipt.json`.

A clean-cache Mac fixture check freshly downloaded sf-market from its licensed
source, verified source SHA, generated muted720p30 with VideoToolbox and verified
the noncanonical encoded hash through its recipe/source receipt. Output SHA:
`d19052982f793d2db5ec7220e95d477de55224f75fb7470c8ed7283baaba72bf`.
This exercises the clean setup cache-miss path without replacing the frozen cache.

Tiny inference-only fixed-shape probe (same first tune frame,2warm+10measured):
640px CPU8.76fps/CoreML55.91fps;960px CPU8.43fps/CoreML36.97fps. CPU640
p95.234s and CoreML640p95.0263s; CPU960p95.1439s and CoreML960p95.0308s.
These are not end-to-end or quality claims. `out/tiny-inference-probe.json` retains
all times, boxes, model/provider/version metadata and loading cost. The loop
included DB postprocessing but reused one decoded frame.

The independent-ingest change passed a held-writer test using the actual engine,
but the first accelerated smoke still failed. Stage instrumentation then measured
150frames: motion3.641s(total),coverage.236s,render2.312s and poll-lock waiting2.461s.
The latter overlaps work; these totals are not additive wall time. `clocked-stage-profile`
had5.33% protection,24.58fps observed output and encoded p95 3.381s. No OCR quality
was scored. The earlier accelerated `clocked-tiny-ingest-thread` was worse
(86.67% protection,p95 5.959s); both remain failed receipts. M1 host memory sampling
also showed17.5GB swap in use, so desktop contention is a recorded limitation.
Next one-parameter trial uses the already-tested phase-correlation motion mode
instead of always extracting ORB features. Source rate, lanes, D and padding stay fixed.

The phase trial ran while evidence collection overlapped disk I/O; it is not an
isolated performance receipt. It had26% protection and p95 3.467s. Bounded FFmpeg
filter/input threads and probe size reduced this to16%/3.303s, still failing.
Reducing the fast lane from30Hz to8Hz gave0% protection,29.42fps and p95 2.387s
on the same short natural clip; accurate lane remained4Hz. No quality judged yet.
A native mask application replaces NumPy boolean indexing with equivalent OpenCV
bitwise masking; existing geometry/outside-pixel tests pass. Subsequent short-run
performance remained noisy, and neither this nor the encoder changes is accepted
as a privacy-quality improvement until the full scored bench runs.

FFmpeg8.1.2 source confirms `AV_CODEC_FLAG_LOW_DELAY` enables VideoToolbox's
one-in/one-out rate-control mode (libavcodec/videotoolboxenc.c1575-1586):
https://github.com/FFmpeg/FFmpeg/blob/n8.1.2/libavcodec/videotoolboxenc.c#L1575
Adding it still failed. A separate60-frame constant-pixel encoder probe isolated
startup: VideoToolbox first packet3.497s, x264 first packet.065s, with x264 p95
added encode latency.0427s. The actual street pipeline with x264 veryfast, however,
was18.49fps/p95 4.203s/10% protection. Next one-change trial uses x264 ultrafast;
source frame count, output pixel fidelity and OCR guards remain required.

## Conductor correction: steady performance and quality priority

All short, contended wall-clock trials above are diagnostics, not accepted perf
receipts. The conductor identified other sessions' Jest jobs and restic backup,
with15-minute load around55 on8cores. They remain untouched. New perf receipts
must have30+seconds steady state after warmup, startup reported separately,
load/memory_pressure/vm.swapusage at both ends, and warn/critical pressure invalidates
acceptance. VideoToolbox is preferred again; its first-packet delay is startup,
not a claimed per-frame cost. A quiet window is confirmed02:00–03:00UTC Oct30.
Poll from02:00 every2min for load1<4 and normal pressure; ifstillbusy02:30, take
and label a contended receipt. Hand back after the receipt, by03:15UTC latest.

Motion estimation now runs once per source frame on its own bounded worker,
phase correlation320px default. Expensive estimation does not hold the emission
lock; transform commits/projections synchronize briefly. A real stalled-history
adapter reproduced the old blocking behavior red; the worker version emits PROTECT
and permits HOLD without waiting, then joins cleanly. Queue drops/errors are
explicit. New per-stage thread-CPU timings and full emit-poll CPU timing accompany
wall times. Rasterization paints clipped ROIs into owned output pixels and mask;
retained outputs are not reused behind a caller's back.

Five CPU-cost repetitions on16consecutive sf-market frames with37–54retained
quads/frame: median phase motion2.137ms/thread-CPU/frame, projection.660ms,
ROI rendering2.624ms, projection+render3.284ms. Full timeline/control overhead is
excluded from that component sum and is separately instrumented in the real
engine. Tiny960CoreML inference median17.523ms/process-CPU/call,24.460ms/wall
(diagnostic wall only). Each repetition records raw pressure/swap and load:
load1=13.45,load5=22.18,load15=40.44,pressure normal. Receipt:
`out/cpu-cost-phase-roi.json`. The profiling command does not claim sustainedFPS.

Regraded all7tune Vision reference with the corrected scorer:313/435natural
intervals hidden(71.954%),52/52synthetic. Taxonomy found122failed intervals:
117havezero maskoverlap in≥1leaking frame,5onlypartialcoverage.96of117are
covered≥95%on another directly observed box in the same interval;72ofthose
alsohavezero-overlap direct observed leak geometry. This makes intermittent
recall and motion-aware lookahead the first quality lever. Some leak geometry
is interpolated, so cause labels remain evidence-backed heuristics, not new
manual ground truth. Details and representative benchmark-only crops are in
`bench/LEAKS.md` and `/tmp/agents/irl-shield/m1-taxonomy/`.

An offline quality runner is being added to hold the intended source-index sample
rates constant while blocking for detectors. Its virtual completion times are
explicit ideal scheduling, never real-time evidence or gate eligibility. This
lets content-quality hill climbs continue under host contention. Real deadline
coverage/protection and latency will be judged by the quiet-window sustained
script and the final actual held-out run, without retuning on held-out.

The live fixture manifest's old synthetic_seed values were unused preview seeds.
They now record the EXACT SHA256(clip ID), first-four-byte little-endian seeds
already used by the benchmark; variant preparation reads that field directly.
No generated label, source pixel, split or source/license changed. Manifest hash
changes are metadata-only. The seed policy is explicit in the manifest.

A second5-repetition CPU profile includes the owned Vision bridge process:
Vision union inference58.449ms/process-tree-CPU/call median,118.188ms/wall
(diagnostic only), with the same16tune frames. The parent Python process alone
would undercount that CPU. Geometry+render remains2.941ms/thread-CPU/frame on
that repetition set; model/caller differences do not make it a pipelineFPS result.
Receipt: `bench/results/cpu-cost-vision-union.json`.

Fresh acceptance review found an async-motion deadline hole: detector receipts
were deadline-filtered, but a transform completed AFTER the deadline could be used
by a late poll. A deterministic-clock counterexample went red(LIVE/raw on frame1)
then green(PROTECT), while timely frame0 remains LIVE. Motion completion times
are bounded and checked across every transform in the path. Legacy composite
rejection now also covers the offline quality entry/factory/CLI, preventing stale
accurate boxes being relabeled with current source PTS. The frozen four-candidate
quality run uses none of that legacy backend and remains unchanged.

Protection counterexample: a400px synthetic house label1842 survived the proposed
20×11 full-frame preview blur. Tesseract's normal --psm11 judge read1842 at94%
confidence. The same four large-label inputs were all readable before protection;
8,59 andCEDARAVE were not output-readable, but1842 was. The temporary PROTECT
stage now downsamples to1×1 and resizes up, preserving no spatial glyph shapes,
then uses the existing slate after persistence. A literal spatial-information
counterexample went red then green; the three-judge Mac repro reads none of the
four protected outputs. LIVE masks are unchanged. Historical coarse repro and
fixed receipts are kept separately under out/protect-coarse-reproduced and
out/protect-solid. This is an evidence-based adaptation of the proposed blur.

Another scoring counterexample showed that a known short house target7 was
incorrectly granted privacy when an output judge read the joined line7 MAIN ST.
Leak checking now counts a standalone short token in a longer reading, while
not matching7 inside1847. Input association/deduplication rules are unchanged.
Red/green regression passes. Regrading the calibrated no-mask control still gives
0/61natural and0/4synthetic hidden; the seven-clip synchronous reference remains
313/435natural,52/52synthetic, with1094instead of1091leaking(frame,interval)pairs.
Frozen quality cards will be regraded with the same rule before comparison.
No original card or movie is overwritten.

The ROI renderer batches edge/padding geometry while retaining float32 OpenCV
hulls and exact raster operations.1152valid mask/pixel comparisons across203
synthetic cases, plus66matching rejects, were exact. Five75-call Linux CPU
repetitions:50quads5.197→.777ms,150quads15.123→1.759ms,300quads29.564→2.927ms.
These are Linux component CPU costs, not M1 throughput. Retained output ownership
and encoded-pixel caller tests pass. The frozen quality renderer produces the
same LIVE pixels; temporary protection is now stricter as described above.

### 2026-10-29 22:49Z — scorer frozen and quality receipt interruption

The output-only short-token check now recognizes a known `7` in `7 MAIN` or `7MAIN`, but not inside `1847` or `1847MAIN`. Input association and the interval denominator are unchanged. Regression red/green is retained in the scoring tests. Regrading retained OCR observations with this final scorer gives unmasked control **0/61 natural, 0/4 synthetic hidden**, and historical Vision union **313/435 natural (71.95%), 52/52 synthetic**. The v3 geometry taxonomy reconciles 122 failed intervals: 118 zero-overlap, four partial; 1,094 leaking frame/interval pairs, 576 on direct input observations. Ninety-seven zero-overlap intervals have another directly observed box at least95% covered. No held-out data was read.

The frozen Mac quality loop's remote shell exited143 after12/14 completed Vision variants. No owned detector/judge processes survived. Completed evidence is retained, incomplete Mazatlan artifacts are preserved under `interrupted-artifacts`, and an explicitly bounded detached resume runs only the missing variants before continuing the three portable candidates. No cause beyond the observed shell termination is claimed. Partial Vision results cannot establish a winner: London bus reports52/150 natural protected frames due to unresolved motion coverage, which fails the comparison guard. Keep this failure visible while investigating motion reliability. No accepted performance claim comes from this contended run.

The opaque renderer batches quad geometry while preserving exact masks/pixels in1,152 valid reference pairs and matching66 rejected cases. Five-repeat Linux thread-CPU medians improved from5.197 to0.777ms at50quads,15.123 to1.759ms at150, and29.564 to2.927ms at300. This is a stage CPU receipt, not Mac throughput. `bench/results/render-cpu-comparison.json` records the scope.

A large-digit adversarial OCR probe falsified20x11 PROTECT blur: Tesseract read `1842` at94% confidence. PROTECT now downsamples to1x1 then restores dimensions, removing all spatial text detail; four readable input labels have no output readings across the three judges. HOLD and persistent PROTECT remain black slates. LIVE opaque pixels are unchanged. Counterexample and fixed receipts are `bench/results/protect-{coarse-counterexample,solid}.json`.

Owned OCR judges are constructed only after all clocked measurements finish, so idle recognition models do not contaminate the measured engine RSS or host pressure. Borrowed resident judges are explicitly labelled non-isolated. Fifteen clocked orchestration/guard tests pass, including deliberate cleanup mutation and720p/1080p guard cases. Real healthy sustained receipts remain pending the02:00–03:00UTC quiet window; the final deadline is03:15UTC.

### 2026-10-29 22:53Z — full initial clocked-policy tune quality, guard failure retained

The14-variant Vision union source-scheduled card, regraded under the frozen scorer, gives **370/435 natural (85.06%, +13.10pp over the synchronous reference),47/52 synthetic (90.38%, −9.62pp),8.19% protection**, median masked area10.85%, p95=100%. It is **rejected**, since neither quality nor protection meets the requirements. This gain cannot be credited to motion/lookahead alone because protected frames also hide text. No held-out evaluation has occurred.

A Linux replay of the retained detector receipts confirms that motion is a distinct coverage problem on London bus: phase320 protects52/150 natural and53/150 synthetic frames; ORB reduces these to28 and31 but still fails. The photometric alignment guard is not the limiting threshold: loosening its .6 bound changes no phase acceptance. Lower phase-response floors are now explicit bench parameters, default unchanged at.5. A deterministic80%-occluded translated synthetic scene is tracked within1.5pixels with floor.2 while an unrelated replacement remains rejected; invalid floors fail. Red/green receipts are in `/tmp/agents/irl-shield/m1-motion-replay/threshold-{red,green}.log`. A lower floor is only an experiment until all7 tune clips pass independent OCR and area/protection guards.

Mac full functional checks now pass **62 M1 tests plus3 relay tests**, compileall and optimized Swift bridge compilation. Two test-harness defects were repaired: a subprocess mock intercepted macOS `platform`'s binary `file` call, and a real codec check used subtle pre-encode color ramps as frame IDs. The repaired codec test reads robust spatial binary IDs. A deliberate next-frame-pixels/current-index production mutation fails1≠0, then the byte-for-byte restored implementation passes. No production codec change was needed. Receipt: `/tmp/agents/irl-shield/m1-motion-replay/codec-order-mutation.json`.

### 2026-10-29 — known synthetic visibility gaps, scoring correction v4/v5

A denominator audit found two labels in Mazatlan whose known visibility drops and returns under fast camera motion. Synthetic IDs had been merged across those known invisible gaps. They now form separate visible intervals; natural OCR gaps continue to be scored continuously. A literal regression fails with one merged interval and passes with two separately scored intervals, excluding readings during the known invisible gap. All seven tune clips therefore contain **54 synthetic intervals, not52**. No fixture pixels or truth annotations changed.

Regrading original complete raw OCR gives initial offline Vision **370/435 natural,48/54 synthetic**, with all54 synthetic input controls readable. The historical synchronous reference gives313/435 natural and54/54 synthetic hidden, but its old input evidence lacks unfiltered readings for the two newly split controls. Those two are explicitly unverified: its judge-discrimination guard is now false rather than borrowing unverifiable readings. The no-mask pilot remains0/61 natural and0/4 synthetic hidden. Every ongoing frozen bake-off card will be rescored with this same correction. The scorer’s receipt hash identifies it; original evidence is never overwritten.

### 2026-10-29 — receipt completeness before further quality tuning

The clocked receipt now reports actual source-clock **presentation-delay p50/p95 before encoding**, separately from encoded added latency and configuredD. Coverage is frame-weighted: nearest fast/accurate age distributions, missing fractions, covered fraction and reason counts, with separate startup/steady/full windows. A literal worked-example test fails when the new fields are absent and passes with startup excluded from steady summaries. The held-out scorecard aggregates these same actual frame records; no configured number substitutes for a measured delay.

Batch projection now performs deadline/path validation once per detection receipt. Five-repeat Linux medians at50/150/500quads: projection2.076/4.911/17.522→0.106/0.342/1.116ms; projection plus owned rendering2.990/7.100/23.568→1.242/2.516/7.757ms. At500quads some repetitions exceed8ms, so this is not an emit-path guarantee. Exact translation/perspective/reverse/identity masks and pixels and late-interior-frame rejection are retained in `bench/results/motion-batch-cpu.json` and OS scratch.

The experimental phase floor.05 still passes all four synthetic fault scenarios (54frames each): fast stall21 protected, accurate stall21, ingest drop12, motion burst5. No uncovered LIVE frame or raw protected pixel array escaped. This checks the invariant, not the geometric accuracy of every accepted transform. Independent OCR on all7 tune clips remains necessary before retaining the threshold.

### 2026-10-29 23:12Z — independent late scoring audit and repairs

The read-only audit reproduced two P2 errors in the retrospective regrader. A rotated clocked quality window could be paired with unrotated source truth and falsely score1/1 hidden; a rescore from100% to0% could retain a stale+50pp delta against a50% baseline. Public synthetic regressions fail for those exact reasons, then pass after repair. `bench.regrade` now rejects clocked/windowed evidence before creating an output directory; it is only for original unrotated legacy/offline receipts. Actual clocked evaluation continues to use the correct presentation/source-frame mapping directly. Rescored copies recompute canonical percentage-point deltas, preserve null unknowns and identify the exact current baseline; the legacy fractional-delta field is removed from those copies. Original cards remain unchanged.33 affected tests pass. Audit and red/green proof: `/tmp/agents/irl-shield/m1-late-score-review/`.

The same audit verified source-clock presentation delay, frame-weighted coverage aggregation across distinct origins, startup exclusion, zero warmup behavior and motion-threshold wiring, without finding another P1. Those are synthetic arithmetic/wiring receipts; accepted Mac performance still awaits the quiet window.

Linux portability now covers tiny and medium as well as v5 mobile and v6 small. On identical20 source frames, tiny CPU/CUDA mean inference66.01/9.36ms and medium714.61/37.27ms; exact CPU/CUDA boxes and real CUDA kernel events are verified. These are shared-Linux inference rates, not emitted fps or an M1 gate claim. No new install or model rewrite was needed. `bench/PORTABILITY.md` records the complete scope.

### 2026-10-30 00:00Z — host serialization and static comparisons

The conductor checkpointed the tree at `2dd52a6`; the builder leaves subsequent edits uncommitted. A common Perl `flock` exec wrapper now serializes timed host work exclusively and untimed quality with shared leases, at `/tmp/agents/irl-shield/perf.lock`. Actual OS-process checks prove shared coexistence, exclusion until every reader releases, and a reader waiting for a writer; a deliberately removed-lock copy fails with `exclusive/shared exclusion violated`, then the unchanged real wrapper passes. Receipt: `/tmp/agents/irl-shield/m1-lock-proof/receipt.json`.

All four initial ideal/offline detector policies completed. Raw natural results are Vision370/435, PP-v5 mobile385/435, v6-small393/435 and v6-tiny353/435. Every initial policy fails guards and remains diagnostic; raw synthetic52-interval cards must be regraded to the current54-interval definition. The Mac sustained queue now polls immediately every two minutes for load1<4 plus normal memory pressure, with the fallback contended run at02:30UTC. Linux static comparison support was installed privately and pinned; an initial static Small/Tiny CUDA trial was rejected before inference for warning PSI pressure, with no accepted speed claim.

`bench.motion_bakeoff` prepares E1 on all seven tune clips with exact copied source/truth SHA-256s, fixed static detector settings and current judges/rendering. Its baseline phase floor.5, floors.2/.05 and ORB+phase fallback.5 differ only in the stated motion policy. This is ideal/offline quality and never substitutes for a clocked receipt. It is queued behind the root Mac sustained receipts, as directed. Separate Sol-xhigh worktree lanes investigate GStreamer, FAST diversity and OpenVINO; all timed work waits for a completed root sustained receipt on that host.

The first Linux readiness launcher had a receipt-classification defect: a retained preflight rejection file was mistaken for a completed sustained trial. The marker was revoked and the lanes were steered immediately. Readiness now requires at least900 steady and1200 encoded frames; a real rejection/complete-but-invalid pair exercises that distinction in `/tmp/agents/irl-shield/m1-lock-proof/readiness-counterexample.json`. This changes scheduling only and grants no accepted performance number. A static Small/Tiny CUDA diagnostic is completing under the same exclusive host lease.

### 2026-10-30 00:30Z — E1 exposes protection credit and a concrete false positive

The fresh Small/Tiny E1 baseline at phase floor.5 gives393/435 natural,46/54 synthetic,8.1905% protection, median12.996% masks, real-video false. Floor.2 gives368/435 natural (−5.747pp),46/54 synthetic,1.8095% protection (−6.381pp), median12.805%, real-video false. Floor.05 gives369/435 natural,44/54 synthetic,.2857% protection, median12.692%, real-video false. Neither lower threshold is a standalone quality win. Mazatlan synthetic still has4/150 protected frames, exceeding the unchanged stricter per-clip guard; aggregate protection alone conceals that concentration. ORB remains in progress.

A retained frame45 from Mazatlan shows clear feet/pavement, with no readable text. PP's raw detections explain the area failure, independently of tracking: Tiny640 returns a95.3%-of-frame quad at box score.599, and Small960 returns99.8% at.508. The same broad failure occurs under Core ML and CUDA. CPU inference on that exact frame confirms the probabilities; raising only pixel threshold does not remove the giant regions. A box-confidence .5→.6 experiment is therefore queued on all7 tune clips, with exact source bytes, independent judges and all guards. No giant-box geometry filter is introduced. Source images and raw probability/box receipts live in `/tmp/agents/irl-shield/m1-mask-inspection/`; they are benchmark-only, not demo-ready.

Raw phase.05 synthetic leaks include London-bus PINE STREET at frames96–97 and BXR219 at96, and Mazatlan's plate/edge entries. CEDAR AVE is known visible only at78–79 and again148–149. The8Hz schedule never samples148/149. Increasing fast sampling is the next candidate lever after confidence, rather than dropping those visible intervals from ground truth.

The complete ORB+phase-.5 E1 alternative gives376/435 natural,41/54 synthetic,2.7619% protection, median12.487% masks, real-video false. It is rejected as a standalone replacement. No E1 policy is guard-valid. The phase-.05 configuration is used only as a lower-protection diagnostic base for the confidence experiment, not called a winner. The full current counts are retained in `bench/results/e1-motion-comparison.json`.

Actual CUDA medium (dynamic ONNX, lower phase floor.05, same8Hz tiny/4Hz accurate policy) grades380/435 natural,44/54 synthetic,.3333% protection, median13.216% masks, real-video false. Its short per-clip timelines and sustained receipt are explicitly contended; static-medium follow-up stopped with a retained clock-drain timeout on the busy host and is not a complete scorecard. Neither result supplies an accepted performance claim.

### 2026-10-30 01:30Z — failed confidence filter, Vision motion check, overnight queue

The one-knob Small/Tiny box-confidence change .5→.6 (`e2-small-box060`, an experiment name unrelated to the research report's static-shape E2) gives327/435 natural,44/54 synthetic,.2857% protection, median11.744% masks and real-video false. Relative to phase-.05 it loses42 natural intervals (−9.655pp), with no synthetic gain or guard repair. **Revert/reject**. Giant region suppression by area is not introduced.

Vision union with only the phase response floor .5→.05 (`v1-vision-phase005`) gives337/435 natural,47/54 synthetic,.2857% protection, median11.558%, p9525.715%, real-video true. The lower protection removes optimistic privacy credit: natural is−7.586pp and synthetic−1.852pp from the original Vision policy. Aggregate protection passes; the stronger per-clip check still fails on Mazatlan. Reject it as a standalone gate configuration, retain as a diagnostic base. Two isolated next experiments change fast sampling8→30Hz, one with Tiny/Small and one with Vision rectangles/union. All7 tune clips, exact source bytes and the existing three judges remain required; partial progress does not earn a score.

The owner superseded every fixed quiet window with an overnight per-host queue. New Linux health receipts use `linux-available-owner-v2`: at least4GiB available is memory-ready; PSI remains diagnostic. Old `linux-psi-memavailable-v1` warning/critical receipts stay rejected. Literal changed-policy cases fail red, then pass; the legacy-warning case stays invalid. A forced queue-deadline trial explicitly sets `contended` and cannot pass performance trust. The19 affected clocked-adapter tests pass. Direct10s CPU-idle sampling and during-job contamination belong to the queue receipt, an additional requirement beyond the benchmark's endpoint memory check. No accepted host-performance receipt exists at this entry.

### 2026-10-30 01:45Z — per-frame Tiny sampling does not close the quality gap

`h3-small-fast30` changes only Tiny fast sampling8→30Hz from the phase-.05 Small/Tiny source. All7 tune clips complete:385/435 natural (88.506%,+16intervals/+3.678pp),46/54 synthetic (85.185%,+2intervals/+3.704pp),.2857% protection unchanged, median masked area15.560% (+2.868pp), p9565.958%. Real video remains false and the stronger per-clip protection guard remains false. **Reject as a passing configuration**; retain as diagnostic evidence that sampling helps some intervals but does not establish100% synthetic privacy or solve false-positive area. No held-out feedback was used.

The production queues are now detached and identity-verified: LinuxPID2644125, nice10 in app-t3code-agents.slice; MacPID26083. Root accelerated/CPU-only/1080p trials have priority1; lane jobs priority2. Live10s preflight samples were Linux32.69% idle/5.64GiB available, Mac2.4% idle/pressure warning. Neither is accepted timing. Root full Mac gate passes85M1+3relay tests, compileall and optimizedSwift, after repairing two canonical-temp-path test expectations. Linux30-test queue/clock integration passes. The root-only joined reporter rejects a quiet-looking raw endpoint receipt when periodic queue CPU is contaminated, and rejects a changed artifact hash/size. Old contended receipts stay diagnostic.

Root integration also found a forced-deadline metadata mismatch before enqueueing the final held-out measurement: the lower-level `run` marks forced options contended, while `clocked_bench` could still declare a noncontended measurement plan. The sealed-bundle options check would correctly reject it rather than silently grade it. A public deferred-orchestration regression fails `False != True`, then passes for FORCED0/1 after setting the CLI's option before any measurement. The plan and every raw/sustained receipt now agree. The already queued standalone performance sources remain immutable at139a0555; the final held-out orchestration will use a new frozen snapshot. No source or old receipt was overwritten.

The proposed median-area ceiling is frozen at15% in `bench/gate-1-policy.json`, before held-out grading. The real-video-preserving Vision tune medians are10.85% and11.56%;15% allows3.44percentage points above the lower-protection policy while retaining at least85% unmasked image at the median. The independent per-LIVE-frame50% outside-video guard remains. This proposal cannot rescue another failed guard. Final diagnostic configuration selection waits only for the already-running Vision30Hz tune card; no new long untimed quality job starts while the timed queue is populated.

### 2026-10-30 01:53Z — final tune decision frozen, no passing winner

`v2-vision-fast30` changes only Vision rectangles fast8→30Hz from `v1-vision-phase005`. All7 tune clips:355/435 natural (81.609%,+18intervals/+4.138pp),46/54 synthetic (85.185%,−1interval/−1.852pp),.2857% protection unchanged, median14.214% masks (+2.656pp), p9533.757%, real-video **false**. Reject. Faster sampling alone does not close privacy and can break image preservation.

The final held-out diagnostic policy is **Vision union accurate4Hz1280 + Vision rectangles fast8Hz640, D1 B6/A30, phase320 floor.05, padding.3**, with15% proposed median area. Its tune card is337/435 natural,47/54 synthetic, median11.558%,.286% protected, real-video true; stronger per-clip protection still fails on Mazatlan. No tune winner passes all guards. The choice is frozen by receipt hash in `bench/gate-1-policy.json` before any held-out grading. Final measurement may retry only for queue trust; a separate lower-priority one-shot grader selects by trust before OCR and never tunes from held-out.

### 2026-10-30 01:55Z — first accepted Linux sustained receipts

The root priority1 queue found an actual quiet period. Static Tiny8Hz/Small4Hz with CUDA+NVENC, D1/A30/B6/floor.05, passes both queue trust and the raw benchmark guards:1200encoded frames,300warmup+900steady, observed30.0779fps, steady added p951.12747s,0% protected, CPU155.73% (one core100), peak tree RSS1248.93MiB. Queue START83.56% idle, END88.66%, minimum periodic69.93%; start/end memory normal. The30Hz Tiny-only rate change also passes:30.0789fps,p951.12802s,0% protected,CPU182.34%,RSS1277.34MiB, minimum sampled idle68.11%. No sample crossed the60% contamination bound.

These are accepted **performance** receipts on the repeated SF workload, not a privacy-gate pass. Small/Tiny tune cards still fail image/privacy guards, and the frozen held-out policy is Vision. Root independently checks movie/mask hashes,1200consecutive mask records and every actual demux packet PTS; receipt `/tmp/agents/irl-shield/m1-perf-queue/linux-first-clean-artifact-audit.json`. Full joined rows and health histories are retained in `bench/results/perf-queue-linux.json`; original queue attempts and movies remain under `.tmp/perf-queue` and `out/perf-queue`. Mac is still waiting for readiness; no Mac speed number is invented.

The first CPU-detector/NVENC trial finishes1200/900frames at30.0721fps,p951.20093s,0% protection,RSS801.46MiB, but401.02% process-tree CPU and minimum queue idle23.61% make it contended. The current global-idle rule includes our own job: average401% on8threads already exceeds its40%-busy budget, so this configuration may be unable to earn an uncontended receipt even on an otherwise idle host. Blocker evidence sent to Opus; no threshold/label changed and retries remain. A separate Small/Tiny CPU+libx264 row4777228d993349898db1ddf8b6576117 tests the GPU-free encoding path, distinct from CPU detection with NVENC. Medium's first attempt rejected before execution when its second START sample fell below80% readiness; it is not a measured Medium speed.

### 2026-10-30 02:04Z — owner replaces contamination policy, history retained

Opus reproduced the CPU self-contamination issue and replaced the rule. Readiness stays at80% idle plus memory OK. New job-window samples subtract only the root-bound job-tree CPU from total host busy; contamination is mean other_busy>20% or any other_busy>40%, with incomplete accounting/health rejected. Old CUDA receipts remain accepted under the stricter old pointwise rule; old CPU attempt1 remains contended. The new mean20% criterion is additionally stricter for a zero-work job; only the single-sample40% criterion reduces to the old idle60% boundary.

Both owned runners were cooperatively stopped at02:04UTC. The old Linux CPU job is held with all original attempts/labels preserved; a new linked qualification will use the revised rule. Other pending jobs will run under the new runner after validation. Linux1080p completed under the old rule before stop; Medium's second attempt was interrupted and remains retained, not relabeled. The queue author updates CPU ancestry/reaped-child counters, partial-window closure and named other_busy reasons test-first. Root prepares real4-worker / separate3-worker / removed-burner proof, with every process bounded and owned.

A new direct-card guard also prevents an endpoint-only raw/deferred scorecard from claiming gate1 before closed queue evidence is joined. The public orchestration regression failed for missing queue_environment, then passes with that field false. The one-shot finalizer sets it only from its selected verified queue measurement, alongside its existing performance/quality guards. This changes acceptance evidence, not pixels, interval counts or the frozen detector policy. The unstarted held-out jobs will migrate to a new immutable orchestration snapshot, retaining their original source/cwd revision in metadata.


### 2026-10-30 02:42Z — native other-load proof, runners restored, clean CPU receipts

Root verified counter implementation45dbdd1a and15 retained red/green log hashes.
The full Mac gate passes96M1 tests (one Linux-procfs integration skip),3relay,
compileall and optimized Swift. The initial Mac gate correctly exposed the
unscoped Linux real-procfs test; explicit platform scoping repairs that test,
while both hosts still require their real native proof. The first partial-window
Mac sampler would have rejected every normal completion; the revised native
Mach four-tick host counter measures those tails while exact top sampling remains
for readiness/START/END. Installed SDK ABI and live tick deltas were checked.
No detector/renderer policy changed.

Both real four-core/separate-three-core/remove-burner proofs pass. Linux mean
other busy3.30%→39.46% (`other_busy`)→2.18%; Mac3.78%→41.21% (`other_busy`)→5.47%.
All four job workers were attributed, no foreign worker was credited and every
known proof identity exited. Raw samples and cleanup are retained; compact
tracked receipts are `results/other-busy-proof-{linux,mac}.json`. The old Mac
proof waiter was stopped by its exact owned identity before the passing proof;
no other session's process was touched.

Linux resumed atPID2773686 and Mac atPID74976, both nohup/nice10, with Linux
inside app-t3code-agents.slice. Identity-safe cooperative stop commands are
`scripts/perf-queue stop linux` and `scripts/mac --no-sync scripts/perf-queue stop mac`.
The explicit overnight09:00PT hard stop remains. Held-out measurement and grading
jobs migrated before first execution to immutable final source264dcc9b, with an
append-only source revision and unchanged frozen detector/area policy. Mac's
quiet hour is not extended by these runners; they subsequently wait for readiness.

Original Mac Small/Core ML fast8 and Vision union fast30 remain **uncontended**,
minimum idle73.13% and64.10%, respectively:30.125fps/1.199s/.111% protected and
30.118fps/1.210s/0%. Vision fast8 stays contended at59.75% idle; a fresh linked
-v2 job requalifies it instead of changing history. Original Linux CPU/NVENC
attempt1 also stays contended. Its linked v2 qualifies at30.077fps/1.125s/0%,
other mean/max2.3%/3.2%. Fully CPU ORT+libx264 qualifies30.009fps/1.066s/0%,
CPU377.78%,RSS720.31MiB,other mean/max3.20%/4.91%. Both detector active-provider
lists are CPU only and the literal encoder argv uses libx264. These are timing
receipts, not independent CPU-path privacy acceptance.

Clean Linux1080p CUDA8 gives30.069fps/1.185s/0%; Medium CUDA8 gives
30.072fps/1.124s/0%. Fresh OpenVINO CPU-detector/NVENC gives30.067fps/1.157s/0%,
242.16% CPU, but its CPU comparisons and privacy qualification remain incomplete.
Mac CPU detector/VideoToolbox qualifies30.152fps/1.199s/0%, and upscaled1080p
Core ML/VideoToolbox30.116fps/1.205s/0%. All sustained rows use10s startup plus
30s steady. Joined artifacts retain pressure/swap/load/coverage/startup; no raw
memory-only card establishes gate1. No tune winner or held-out score is inferred.


### 2026-10-30 02:46Z — first held-out measurement retained, not judged

The first frozen held-out measurement exits0 and seals its plan, but revised
queue accounting labels it contended: mean other busy20.0586%,maximum36.8842%.
The limit is strictly20%; no near-boundary exception or relabel is introduced.
It waits for a new quiet measurement attempt. No held-out OCR was run and no
quality decision was made from held-out. The final grader will select by trust
before independent OCR, not by the quality of these attempts.


### 2026-10-30 02:53Z — merit-lane hand-backs joined, no implementation swap

All three actual branches are verified at2dd52a6: elannash/m1-gst,
elannash/m1-openvino and elannash/m1-fast, with separate uncommitted source.
Root checked21GST source/options hashes, fiveOpenVINO source hashes, and FAST's
source fingerprint171449fd plus all four queue/runtime hash/size pairs. Existing
FAST manifest entries compare equal; only Apache-2.0 FAST tiny is introduced,
weight28867779. Eight FAST target tests are green by the read retained log;
root full-gate/implementation acceptance for merit branches is not claimed.

FAST's closed clean30s detector costs: CPU640288.15/312.71ms, CPU1024752.17/788.14ms,
CUDA64033.08/38.48ms, CUDA102464.15/68.42ms p50/p95. Natural/synthetic privacy,
area and complete-interval complementarity are **unmeasured**, as are Core ML and
stream fps. OpenVINO's clean CPU/NVENC stream is30.067fps/1.157s/0%, but its
comparison stops on v1 warning pressure and Tiny960 strict parity remains false.
GST's fresh FFmpeg comparator is clean30.07fps/1.135s/0%; GST/NUT all-clip
qualification remains incomplete. Their older contended pairs are not promoted.
These are ledger merges of the lane outcomes, with full branch LOG files retained
for separate PR review; no lane implementation replaces the M1 default.

One summary with all three branches and qualified numbers was queued to Opus.
Linux has all18 submissions terminal and is sealed for exit. Mac has a producer-
complete marker: its remaining priority4GST setup seals only after submitting
its five prepared priority2jobs. FAST's Mac SDK/model setup and quality work stay
unsubmitted after its explicit three-hour timebox. No new quality job starts.


### 2026-10-30 02:59Z — Mac OpenVINO CPU receipt lands; held-out grading begins

The queued Mac SDK/compare prerequisite completes with normal raw pressure and
clean closed other-busy accounting (mean12.52%,max26.99%). Root verifies its
artifact hash/size. Three repetitions of21 frames across seven tune clips give
63 full calls each. Tiny640 ORT vsOpenVINO p50/p95 total-call24.69/28.35 vs
26.80/27.87ms; Small960139.96/142.27 vs123.47/127.71ms. All four native
Tiny/Small at640/960 strict box-parity checks pass. This is accepted CPU-call
cost/parity only, not a Mac OpenVINO stream or privacy result. Private27-package
Mac SDK installs are recorded in INSTALLS. Raw/compact artifacts remain in
`.tmp/m1/openvino-mac-{comparison,attempt}.json` and tracked
`results/openvino-mac-comparison.json`.

Held-out's second and third attempts reject before execution. Its complete
first plan remains contended at mean other20.0586%; the job is exhausted-contended.
The one-shot grader may now select that only complete plan by trust before OCR,
retain its invalid performance status, and report privacy once. No quality number
is manufactured from an incomplete grader. Linux all18jobs are terminal and
runner2773686 is drained/exited; Mac runner74976 alone remains live.


### 2026-10-30 03:09Z — attribution hypothesis remains untested; diagnostic jobs queued

Opus20:06PT proposes Apple ML/XPC/kernel work outside the process tree as a
possible source of Mac other_busy. No conclusion or service exclusion is made.
After the active held-out grader, two matched Vision8/30Hz jobs7b8967f73e814da1a52a463ff153578a
and4460653a1ffb4c608aeb87cb5e34710f use the same source139a0555 and observer
`.tmp/m1/mac-service-observer.py`. Per sample they retain top-five stable
non-job CPU deltas/names alongside unchanged total/job/other metrics, with scan
latency and uncredited endpoint job PIDs. No production counter changed. The
synthetic endpoint exclusion/arithmetic check and Mac compilation pass; native
execution, causality and a possible service-specific fix/proof are unfinished.
Mac's owner quiet period ends; no extension is requested or enforced.

Root reads all four failed Linux stderr artifacts. GST and NUT stop on frozen
v1 per-clip warning-pressure guards; OpenVINOcompare likewise stops on warn
and retains Tiny960 parity false; local SRTnetwork propagates no-video10s timeout.
All four have clean CPU queue accounting. No missing-plugin explanation or
reclassification is introduced. Causes and attempt IDs are in M1-HANDBACK.


### 2026-10-30 03:11Z — correction from complete attempt artifacts

The root03:10joined artifact audit corrects the earlier03:00 status inference:
held-out attempt3 **completed**, with30.11fps/1.206s steady p95/0% protected,
but remains contended because maximum other_busy is about42.0% (>40%), despite
mean about19.3%. Only attempt2 rejected before execution. The one-shot grader
therefore selects attempt3, the **last complete contended measurement**, under
the frozen pre-OCR selection rule. It does not select attempt1. Earlier root
status prose about two rejected preflights was wrong; original attempt files
and labels were never altered. No quality score or policy changed.


### 2026-10-30 04:27Z — PR1 family independence, guard proof and cache identity

Rescored all14 retained tune comparison/E1/E3 cards before changing OCR cache identity; all original pooled counts reproduce. PP Small A30 changes393/435 pooled to318/343 independent natural,46/54 synthetic; Linux static Small321/343 natural,44/54 synthetic. Real-video guards still fail; no policy wins or new Q measurement. Explicit per-lane detector families exclude their judges from input truth, output leaks and synthetic controls. Mixed PP+Vision reports only Tesseract and fails the two-independent-engine guard. Secondary pooled numbers remain labeled ineligible.

One failed LIVE guard zeroes natural/synthetic credit through both entry points. Physical all→any mutation fails both subtests; exact source restore passes. A timestamp-pyc alias during a quick repeat was caught by the full suite; proof now uses -B and clears only its own scoring bytecode between legs. Final Mac scripts/check and Linux gate both exit0:104 tests with1 platform skip plus3 relay tests and compilation; Mac also builds optimized Swift. Cache schema2 includes ONNX detector implementation, OCR/runtime/OS versions and geometry. Full table, provenance, mutation/gate artifact hashes and commands are in docs/PR1-R1-FIXES.md and results/pr1-r1-proof.json. No new installs.

The fresh all7 tune OCR re-judge is queued untimed/SH behind the sealed Mac timed queue, frozen fixed source, PID54753, deadlineFri09AMPT; no fresh numbers yet. M2 fresh Linux queue irl-shield-builder-m2-queue-1 is open with detached nice10 runner3141521 in the agent slice, same lock and other_busy-v2, hardstopFri09AMPT. Both process stop commands are in the hand-back. Historical one-shot heldout finishes unchanged at47/60 pooled natural,22/22 synthetic,19.88%medianarea,0%protection, real-video false/gatefalse; correlated pooled result is not promoted to independent.


### 2026-10-30 04:38Z — correction: independent truth, all-judge output leaks

Conductor corrects the prior instruction: independence constrains truth/input controls only. Every credible output judge, including the candidate family, counts as a leak. The previous independent-both policy/figures above are superseded, with their artifacts retained. A same-family-only output regression fails under physical independent-output mutation and passes after byte-exact restoration. The all→any live-guard mutation was also rerun on final source, red/revert/green. Both final full gates exit0:105tests with1 platformskip plus3relaytests, compilation and MacSwift build. No installs.

All14 retained cards rescored into out/pr1-r1-truth-only-rescore-v2; pooled/independent-both/newprimary columns are in results/pr1-truth-only-rescore.json and docs/PR1-R1-FIXES.md. Primary SmallA30 311/343 (90.67%)natural and46/54 (85.19%)synthetic; LinuxstaticSmall 304/343 (88.63%)natural and44/54 (81.48%)synthetic. All original pooled counts reproduce; truth denominators unchanged from independent-both and hidden credit never increases with all output judges. Real-video guards remain false.

Old queued rejudge54753 stopped before OCR; replacement22977 uses frozen final source and all-judge leaks, SH after sealed Mac timed queue drains, hardstopFri09AMPT. No fresh OCR score yet. M2queue3141521 unchanged. Qchildren await fixed committed head; no Q policy measurements started.


## Q frozen baseline and B12 preparation — 2026-10-30T10:16:02.128467+00:00

Source frozen at a8a06e30c2e5bdd8be054bbddf3c69169fe64e39 after the deferred PR4 P2 checks. `.tmp/q/frozen-a8a06e3/plan.json` pins 64 source files, all 14 tune source/truth pairs and four existing model artifacts; plan SHA256 `2f01bde798fa2d6e6637c2936e8b208ea85bdf17f37aa3388b4306cf288b6633`. Baseline is Small960 accurate4Hz / Tiny640 fast8Hz, CUDA, static models, NVENC, D1/A30/B6, phase320/.05, padding.3, opaque, median ceiling.15 with `bench/gate-1-policy.json` as basis.

All 14 baseline natural/synthetic variants rendered and sealed; source and media accounting passed each bundle. Serial Mac cache-schema3 judging is running on the sealed pixels. Primary truth/input controls exclude Paddle family; output leaks use every judge. Metrics and guard verdicts are pending; no quality or performance pass is claimed. Logs and immutable bundles: `out/q-base-a8a06e3-cache3-v3/`, `.tmp/q/frozen-a8a06e3/render-controller.log` and `grade-controller.log`.

Predeclared arm Q3 changes only `before`6→12, with source, input hashes, all other knobs and the ceiling/basis unchanged. Rendering runs separately on Linux while the baseline is judged on the Mac; its score waits behind the serialized judge lane. Bundles `out/q-b12-a8a06e3-cache3-v3/`. Decision pending; promote only after natural improvement plus synthetic, real-video, area, protection and separately qualified performance guards.


## Q baseline measured — 2026-10-30T10:52:45.966975+00:00

Frozen a8a06e3 baseline completed all14 sealed variants and serialized schema3 Mac judging. Primary independent truth (Tesseract eng + Vision accurate en-US), ALL output judges: natural298/343 (86.8805%), synthetic44/54 (81.4815%). Input positive controls54/54 readable. Median masked area12.6941%, p95 55.0451%; aggregate protection6/2100 (0.2857%), worst clip Mazatlan synthetic4/150 (2.6667%). Real-video guard fails on both Mazatlan variants; zero credit is correctly assigned to every interval of those clips. Comparison invalid; no winner or promotion. Performance remains unqualified: this is ideal/offline content quality with `real_time_verified:false`, never a steady-state receipt.

Receipt `out/q-base-a8a06e3-cache3-v3/scorecard.json`, SHA256 `6d2fd085331950a618fac550918618b1196bbb1641069e39d219f1bc4ef8a010`. Root audit `.tmp/q/frozen-a8a06e3/baseline-receipt-audit.json` rehashed64sourcefiles,14bundle/grade seals,140artifacts and one schema3 cache signature with no mismatches. B12 differs only in `before:6→12`, all14 renders done, serial judging active.


## Q3 B12 measured and rejected — 2026-10-30T11:10:22.693316+00:00

Only `before:6→12` changed. All14 pairs complete, same source/input/readings/intervals/cache3, exact detector/motion geometry unchanged. Primary natural298/343 and synthetic44/54 unchanged fromB6; median area12.6941%→13.8357% (+1.1417pp), aggregate protection0.2857% unchanged. Mazatlan real-video false and synthetic per-clip protection2.6667% remain. REJECT; no privacy gain and more mask area. No guard-valid winner and no performance acceptance. B12receipt `out/q-b12-a8a06e3-cache3-v3/scorecard.json` SHA256 `20fcf04d20b754d84738321c0e4d10a4a1242871ddd9e7eb3f64ffb166be69e5`. Full per-clip table, changed raw leak intervals and receipts in `docs/Q-B6-B12.md` and `bench/results/q-b6-b12-comparison.json`. Root rehashed64sources/14bundle-grade seals/140artifacts, identical saved detector/motion geometry and input truth verified. Giant audit is next, before any new arm; held-out stays unspent.


## Giant audit rejected; diagnostic fallback frozen — 2026-10-30T11:45:39.160255+00:00

Exact actual-engine/motion replay reproduces all300Mazatlanframes including mask hashes and coverage. Both lanes originate rawgiants; motion preserves each polygon area. RemovingALLrawquadareas>=.5 stillleaves61/82naturaloversizedframes and frame45 mask.528395 fromsmallerreceipts. Synthetic haszerorawgiants but33oversizedLIVEunions, so a rawgiant-only rule cannot fix it; fouradditionalPROTECTframes reflect missingaccurate-motioncoverage. Reject overlap/recognizer,densitycount, simplehighprobabilitysupport and testedunclipcap as safeblocker fixes. Thirteenpositivecloseups/fullframecontrols retainink undercap, but frame45stillmasks~.906 perlane. No productionadapter, no corpusmetrics, no relaxedguard. Rootreadcode/reports/probes/24affectedtestlog,openedpavementandfull-frame11, verified3sourcefiles+101artifacthashes, audit `.tmp/q/giant-audit-receipt-audit.json`. Childauditpatch SHA8a0ff528426aa2ef90723abf33cd11ca617edd7f79f4c5a52b18247e4d248e34 is diagnostic-only.

No guard-valid tune configuration was established. Following the conductor's explicit fallback rule, `bench/q-final-policy.json` freezes BASELINE B6 unchanged for the single fresh-heldout diagnostic. It is NOT a winner and NOT privacy/performance-qualified. Failed tunechecks: natural,synthetic,per-clipprotection,realvideo. No heldout pixels/detection/OCR/score have informedselection. Extra padding/inputsize/model/FAST arms remain unrun; the known union/giant blocker and finalheldout deadline take priority. Next: conductorcommitfrozenpolicy/reports, applyheldoutpatchseparately+gate, renderonceLinux and judgeonceMac withfixedstatepath; report asis/offline real_time_verified:false.


## Fresh heldout evaluated once — 2026-10-30T12:19:36.979497+00:00

Executing26c8db1, frozenpolicy dcbc96c8/dataset46a4461c, singleLinuxCUDA/NVENCrender and singleMacpersistentjudgepass completed. Primary106/126natural84.1270%,14/22synthetic63.6364%; controls22/22readable. Medianarea13.5967%passes15%ceiling; p95area50.3944%. Aggregateprotection6/900=.6667%passes, Chicago natural3/150exact2%failsstrictperclip. BothZurichvariantsrealvideoFALSE (31/9badLIVEframes). Manchester14rawnaturalleaks; Zurichguardzeroes6natural+8syntheticintervals despite no rawsyntheticleaks. No privacywin, comparisoninvalid, offline real_time_verified:false, gate1false/unqualifiedperformance. No retuning/repeat. Fullcard `bench/results/q-fresh-heldout-once.json` SHA7865083bba59da5c25954b4db97fa27487b3f082355ff15485137f5d61c55272; proof/data/perclipreport in `bench/results/q-fresh-heldout-once-proof.json` and `docs/Q-FRESH-HELDOUT-RESULT.md`. Rootverified6bundle/gradeseals+66artifacts/frozenidentities/schema3/bothspentmarkers. Test-onlyGitfixturefixafterrender reproducedMac4errors then fullMac167+3+Swift and fullLinux167+3+compilegreen; earlierLinuxmissingPyAVSDKfailure preserved, correctedbyexistingunified3.11read-onlySDK,noinstalls.

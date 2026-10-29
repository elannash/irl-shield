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

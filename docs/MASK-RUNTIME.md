# Rounded-mask runtime observation

Rounded **Patch is the CLI and session default**. Chat offers **Patch and Bar**,
including moderator locks. Signed and Frosted remain selectable only by explicit
configuration. The owner approved all four materials' appearance on licensed
real-footage previews. The default and vote-set decisions below were made by
the conductor from the measurements; they are not an owner performance verdict.

## W5b render revision — October 31, 2026

The optimized painter shares dilation and distance transforms for overlapping
irregular masks, resolves material ownership before constructing Frosted/Signed
paint, and caches only tiny source-independent disk kernels. It retains the
original Frosted cell means, grain and reconstruction. All original polygon
pixels remain opaque and retain their paint.

Unit 3 passed 18 owning tests, three physical coverage/ownership mutations
failed behaviorally, and restored tests passed. All 600 full-image, mask and
alpha comparisons (four materials × 150 saved SF Market frames) matched the
previous rounded painter exactly. The same source passed a 363-test full gate
with two explicit Linux skips. This validates the tested pixels and geometry;
it does not establish a new OCR hidden score on other clips.

The full-150-frame offline render comparison observed Bar p99 19.854 ms versus
unrounded Bar 20.388 ms, a −0.534 ms delta. Its raw queue flags include
`cpu_accounting_unavailable` and `other_busy`; these timings remain diagnostic.

The following separate native jobs used the same actual local launcher,
1280×720/30 fps repeated licensed source, CUDA detector lanes, NVENC, ten-second
warmup and 120-second steady window. Deltas use the original unrounded Bar
reference below. Acceptance requires ≥29.5 fps, no extra slates, and both p95
and p99 latency deltas ≤+50 ms. CPU and maximum latency do not gate.

| Optimized material | fps | LIVE / slate | p95 delta, ms | p99 delta, ms | CPU, one core=100% | Literal guard |
|---|---:|---:|---:|---:|---:|---|
| Signed | 22.233 | 2668 / 0 | +402.483 | +455.942 | 147.383% | FAIL |
| Patch | 30.000 | 3600 / 0 | -1.343 | +0.529 | 107.183% | PASS |
| Bar | 29.992 | 3597 / 2 | +29.285 | +24.342 | 107.000% | FAIL |

**Patch passed and is the default.** Signed failed throughput and latency and
stays config-only. Bar literally failed the no-extra-slate condition: its two
single-frame PROTECT ACKs were indices 3752 and 3902, each loop phase 2 of the
150-frame repeated clip, with LIVE neighbours and zero egress recoveries.

**Conductor decision, made after the result:** retain Bar in chat on its earlier
passing rounded-Bar receipt (`36245885…` below), together with the revision's
exact paint parity and lower observed offline cost. The conductor's post-hoc
diagnosis is fail-closed coverage at the artificial hard cut, with detector-phase
alignment varying between runs, rather than paint cost. The recorded seam
positions support that interpretation but do not prove its cause. The decision
is not a unit-7 pass, and the literal failure remains in the table and raw data.
No frames or seam windows were removed from any current measurement.

All three new native jobs were unforced, single physical executions under the
canonical exclusive lock. Patch and Bar retain raw `queue_contended` with
`cpu_accounting_unavailable`; Signed additionally retains `other_busy`. No run
is relabelled uncontended, and Signed's result does not isolate an intrinsic
paint-cost cause. Each run's seven recorded native process identities were gone
at root's audit; cleanup reported no survivors.

Frosted remains **final as config-only for this revision**. Its one separate
coarse-field offline attempt passed 21 owning tests and its ≤12-LSB comparison
bound (observed maximum 6), but full-render p95 was **49.134 ms**, above 20 ms on
the prescribed 12-frame set. That approximation is not included in the shipped
painter, and no further Frosted native unit was run.

For future measurements, the conductor recommends a non-looping source, or a
fixed seam exclusion window declared before the run. This does not change the
current receipts. The Sunday demo source must avoid hard loop cuts inside the
recorded window; fail-closed protection at such cuts remains enabled.

| W5b receipt | SHA-256 |
|---|---|
| Exact 600 comparisons / 750 timed renders | `feb8354b37384abeb10edc0057d6a3e479e46eae436530ee95f9ad11bdafd283` |
| Optimized Signed native, unit 5 | `8227a5c5dbe31fb720b3fba17685f4f8b4453ff40384143aa703becc5cd5b4bb` |
| Optimized Patch native, unit 6 | `be3c10c2a8b28bb823bcca92c6d17a99fea5e7e0eefe26f99d2a0796c3e131c1` |
| Optimized Bar native, unit 7 | `b136a202211bca7fa6b546f195be4cdd73e6516efe74015ba3e597829a0ae3b7` |
| Frosted offline attempt closure | `a9983f2fbf6295c7aa4f7b79d16d3a1eff3f7cf50e5248da8a386fb670d0e179` |

The measured optimized painter SHA-256 is
`35aa3a6fd3bbe46ad48b82bc378a02891221149e377ddaae5d7c0c62e824e2b1`.
W5b used seven measurement units, preserving its failed profiler/preflight and
harness attempts without refunds or retries. Root's final integration gate is
separate from those native measurements. Raw evidence remains in the W5b
hand-back; the summaries here neither qualify phone/Twitch latency nor claim
GPU headroom, maximum FPS, OCR recall or a real walk.

## Earlier rounded revision — historical observations

## Native local comparison — October 30–31, 2026

Each arm used the actual `scripts/walk-linux --local-only` launcher, the pinned
Linux GPU environment, both CUDA detector lanes and NVENC. A licensed, silent,
five-second natural SF Market clip was repeated at 1280×720 and 30 fps. The
pipeline had to show source video, completed inference in both lanes, a LIVE
encoded acknowledgement and independently decoded output before ten seconds
of warmup and a complete 120-second steady window.

The reference used the original unrounded Bar painter from `323868e9`.
The two candidates used the same rounded-paint source, with only the selected
material changed. Metadata observers did not alter frames or masking decisions.
Input and output timestamp translations were established by matching unchanged
H.264 packet content, then checked for every joined frame.

| Steady-window observation | Original Bar | Rounded Bar | Rounded Frosted |
|---|---:|---:|---:|
| Independent decoded frames | 3,598 | 3,597 | 1,799 |
| Sustained fps | 29.983 | 29.975 | 14.992 |
| LIVE / slate frames | 3,598 / 0 | 3,597 / 0 | 1,465 / 334 |
| Output index gaps | 2 | 3 | 1,798 |
| Local latency p50, seconds | 1.122843 | 1.130522 | 2.477058 |
| Local latency p95, seconds | 1.131862 | 1.150687 | 2.611045 |
| Local latency p99, seconds | 1.158514 | 1.185865 | 2.632654 |
| Local latency max, seconds | 1.248064 | 1.298541 | 2.693108 |
| Relay-tree CPU, one core = 100% | 100.883% | 125.675% | 149.542% |

The conductor clarified the initially unspecified latency statistic before
receiving the Frosted result: both p95 and p99 must remain within the reference
plus 50 ms; maximum is reported separately. Rounded Bar met the observed
29.5 fps, no-extra-slate and latency conditions: **p95 +18.825 ms, p99 +27.351 ms**.
Its maximum rose **50.477 ms**. Frosted failed throughput, slate and latency
conditions. No failed or prototype run was relabelled as a pass.

All three native jobs were unforced, exclusive and single-attempt. The queue
marked them **contended because its CPU accounting was unavailable**. Those raw
flags remain unchanged; these are local diagnostic observations, not an
uncontended performance qualification or a headroom claim. The separate relay
CPU measurement covers the steady CLI process tree and excludes the publisher,
independent decoder, controller and queue. It cannot account for an undiscovered
short-lived child between snapshots.

Latency is publisher frame emission to independently decoded local output,
including the product delay. Frames enter by decode time inside the steady
window. Dropped or still-pending frames do not enter latency quantiles, which
is why throughput, gaps and slate counts are reported alongside them. This is
not phone, wireless or Twitch end-to-end latency. No OCR, privacy, GPU-utilization,
maximum-FPS, different-footage or real-walk acceptance follows from these runs.
Saturday's planned walk was cancelled; the measurements still inform the demo's
runtime default.

## Paint at the actual natural-footage region distribution

A separate quiet, unforced, uncontended CPU measurement reconstructed the exact
Renderer regions for all 1,050 natural tune frames and verified every original
mask union against its sealed bundle. It retained zero-region frames. Actual
regions per frame were **p50 33, p95 96, maximum 102**; connected components were
5 / 12 / 14 and are a different population. The SF Market region distribution
was 82.5 / 101 / 102.

| Paint only, milliseconds | p50 | p95 | Max |
|---|---:|---:|---:|
| Frosted | 19.368 | 72.209 | 419.447 |
| Bar | 12.305 | 30.690 | 120.728 |
| Signed | 13.346 | 33.614 | 128.407 |
| Patch | 12.544 | 31.595 | 123.905 |

There were 1,050 measured calls per material and 84 separate warmup calls.
Decode, region reconstruction and mask verification were excluded from paint
timing. The prior 24-mask, 2 ms proxy failed for all materials; its receipts
remain failed. The conductor replaced that proxy with the native runtime
comparison for this default decision.

Rounded Bar used 24.792 additional CPU percentage points, about 0.248 of one
core, in the native comparison. Its new work includes outward envelopes,
distance-based feather alpha and a color-canvas blend, whereas the reference
only paints original rasters. The timing study did not isolate those stages;
it does not establish their individual shares of the increase.

## Receipt identities

The approved repeated input is SHA-256
`36528042bc7cd24815d595655c9f535e75ad8fef0b6fc29243ffe4e62d18aada`.
The evaluated rounded painter is
`75d4e32b33a158dbbef4d88f2db7b32f2cefb3414e70b2588b49c7531004948a`.
The original unrounded painter is
`35b92ec87075aeb12a0be6acecf60fc7d66a50c0d6bc9a23f090be64860199ac`.

| Receipt | SHA-256 |
|---|---|
| Natural 1,050-frame paint | `f859c28ad005ac8c8a13df42b3c8aaad6caf1bd52b11bf704233b83c06c613b0` |
| Original Bar 120 s | `d34b277030b9a5b5e3cb5cee7b7279cf6b67b54898fcb2d0c4b92a9576c2cbfb` |
| Rounded Bar 120 s | `36245885dae0d999c98de899267f336cab7a2d10a0c4d789cbdfd5b937a3961e` |
| Rounded Frosted 120 s | `5719589c00ad223ee24d0588ebc90c0e9866ce2e9db14e99c381e7780cb2f4b6` |
| p99 derivation | `74074e223f745fbbb0fbcca8b1cb1ee7e9c61358f349449937dda5c767d2fd4b` |

Raw metadata, immutable packets, source bindings, cleanup records and prototype
failures are retained under the root hand-back's `w5-walk-acceptance-12` evidence
folder. They are review artifacts, not demo footage. The earlier polygon,
original-paint, overlap and outside-only-alpha proofs remain the source
coverage evidence; this performance comparison does not replace them.

# Rounded-mask runtime observation

Rounded **Bar is the CLI and session default**. Frosted, Signed and Patch remain
selectable by explicit configuration. Only Bar is chat-votable, including
moderator locks; Signed and Patch have no passing native receipt, and Frosted
failed the local 720p30 runtime comparison below and has no
30 fps qualification. The owner approved the four materials' appearance on
licensed real-footage previews; this document records performance separately.

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

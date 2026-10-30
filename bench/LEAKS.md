# Retained leak taxonomy

`bench.leaks` explains an existing scorecard without rerunning OCR, changing truth,
or modifying its videos. All output images are benchmark evidence: source footage
may contain readable third-party names and logos. They are not demo-ready assets.
Footage attribution stays in `fixtures/ATTRIBUTION.md`; existing NumPy/OpenCV
dependency notices are in `models/licenses/dependencies.json`. No dependency,
model, footage or font is introduced.

```sh
nice -n 10 models/.venv311/bin/python -B -m bench.leaks \
  out/regraded-v5-bakeoff-vision-union/scorecard.json \
  --media-root out/bakeoff-vision-union \
  --out /tmp/agents/irl-shield/m1-taxonomy
```

The module limits OpenCV and each video decoder to two threads. It uses CPU only.
`--geometry-only` produces the interval/mask counts without decoding pixels or
creating images; the full run adds photometric heuristics and up to ten image
panels. Each panel has input, encoded output, and mask columns with the same
OCR-inferred target box marked. `contact-sheet.png` combines those panels.
`per_variant.geometry_summary` records the fast geometry phase; full photometric
attributes are retained per interval and aggregated per clip and overall.

The report requires every scorecard clip variant, reconciles its natural total
and hidden count against retained intervals, and stops on missing evidence,
invalid frame accounting or failed real-video guards. It deliberately does not
turn a video-guard failure into a detected OCR leak. Natural content appears in
both natural and synthetic variants: totals describe scored intervals, not unique
physical signs. Synthetic scorecard totals remain separate and unchanged.

## Primary classification

One mutually exclusive class is assigned per failed natural interval, using its
least-covered leaking frame. Equal-coverage representatives prefer an actual
input OCR observation over interpolated geometry.

| Class | Recorded evidence |
| --- | --- |
| `detector-miss` | At least one leaking frame has exactly zero target-box pixels covered, and the historical AABB runner detected every frame (`stride=1`). This is a mask omission, not evidence of a scheduling omission. |
| `partial-mask-coverage` | Every leaking frame has some mask overlap, but at least one has uncovered target-box pixels. This is geometry evidence, not proof that more padding is the right fix. |
| `fully-covered-box/output-match-or-truth-uncertainty` | Every leaking target box is fully covered. Inspect fuzzy OCR association, interpolated geometry, mask provenance and output text before attributing a detector failure. |
| `zero-mask-overlap/cause-unresolved` | A non-synchronous/new run has a zero-overlap leak without explicit timing evidence. Zero overlap alone cannot distinguish detection from scheduling. |
| `unprotected-coverage/timing-failure` | A retained clocked record explicitly reports bad coverage while leaving the frame unprotected. |

Each leaking frame retains its interpolated float box, clipped integer pixel ROI,
covered and visible pixel counts, fraction, height, observation/interpolation flag,
and source frame index. The ROI rounds box minima down and maxima up, then clips
to the frame. Coverage is exact for this rasterized visible AABB, not for individual
glyphs. A natural track is still inferred OCR truth and can be associated wrongly.

Mask sources, in preference order:

1. Saved `.mask-pixels.zip`, checked against recorded mask hash and area.
2. Historical AABB records reconstructed with the frozen `shield.masking` helper
   and that scorecard's padding, checked against recorded mask area.
3. Retained quads reconstructed through the opaque renderer, checked against area.

The first path supports current clocked artifacts with the same file naming. The
historical AABB path is the verified target of this work. Saved mask pixels are
preferred for clocked runs; arbitrary future renderer styles are not supported.

## Nonexclusive attributes

Attributes count intervals with at least one qualifying leaking frame. They may
overlap and must not be added together as primary causes. The report also gives
height bins over leaking frames and over each interval's median leaking height.

| Attribute | Heuristic |
| --- | --- |
| Small text | Box height at most 16 source pixels by default (`--small-height`). This does not establish physical distance. |
| Near edge | Target touches the outer 2% of either frame dimension. |
| Edge-entry candidate | Near-edge leak within three frames of the first input OCR observation. This may be clip start or an OCR gap, not actual physical entry. |
| Target motion or box jitter | Center displacement between adjacent input OCR observations, divided by frame gap, is at least `max(8px, 0.5 × target height)` per frame. OCR grouping/jitter can imitate motion. |
| Low sharpness / blur candidate | Input target ROI grayscale Laplacian variance is below 80 by default (`--blur-threshold`). Size, texture, compression and exposure also affect it. |
| Fast-pan candidate | Global phase correlation response at least 0.5 and translation at least 8 source pixels per frame. This is an estimate, not tracked camera ground truth. |
| Motion-blur candidate | Low sharpness co-occurs on the same frame with the target-motion or fast-pan condition. It remains a hypothesis. |
| Interpolated leak geometry | At least one leak occurs between input observations rather than on an observed input OCR box. |
| Intermittent mask coverage | A zero-overlap detector-miss interval also has at least one directly observed input OCR box with 95% or greater mask coverage. This measures changing mask coverage, not proof of a specific detector's recognition or a scheduling failure. |
| Partial coverage on some leak frame | At least one leaking frame has nonzero incomplete coverage, even if a different zero-overlap frame determines the interval's primary class. |

No confidence probability is invented. Primary classifications are labelled
automatic geometry; attributes are labelled heuristic. Representative inspection
can confirm visible mask placement and text appearance, but is not new manual
ground truth. Keep any inspection annotations separate from the automatic count.

## Limits

The tool trusts the supplied scorecard's already-corrected `leak_frames`; it does
not silently rerun fuzzy matching. It does not infer a timing miss merely because
a neighboring frame was detected. Historical synchronous `stride=1` omissions
remain detector misses, including intermittent detection. Laplacian variance and
phase correlation use source pixels, while the judge's leak was in encoded output.
They can prioritize experiments, not establish causation or prove privacy.

No benchmark score, gate decision, threshold calibration or production renderer
is changed by this analysis. A promising intervention still needs the full tune
bench and its independent OCR judges before any held-out milestone claim.

## Current seven-clip tune receipt

The corrected `regraded-v5-bakeoff-vision-union` scorecard contains 14 variants of
all seven tune clips: 313/435 natural intervals hidden and 54/54 synthetic
intervals hidden. The historical input-control evidence verifies52 of54 synthetic intervals after visibility splitting, so its judge-discrimination guard is false; the new offline Vision receipt verifies all54. Its 122 failed natural intervals reconcile to 118 intervals
with at least one zero-overlap leak and four with only partial overlap. There
are 1,094 leaking frame/interval pairs; a frame can belong to multiple intervals.

| Clip | Natural total | Hidden | Failed |
| --- | ---: | ---: | ---: |
| SF Market | 146 | 107 | 39 |
| Ljubljana walk | 66 | 44 | 22 |
| Ljubljana traffic | 57 | 37 | 20 |
| London Croydon | 36 | 19 | 17 |
| London bus POV | 101 | 85 | 16 |
| Illinois night | 17 | 17 | 0 |
| Mazatlán Aquiles | 12 | 4 | 8 |

Of the 118 zero-overlap intervals, 92 have zero overlap on an actual input OCR
observation; 26 rely on interpolated leak geometry. Ninety-seven also have at
least 95% mask coverage on another directly observed box in the same interval.
Seventy-three satisfy both stronger conditions. Twenty-one zero-overlap intervals
never reach 95% coverage on their observed boxes.

Prioritize evaluating motion-projected temporal mask coverage on the 97
intermittent intervals, then detector recall on the 21 without a high-coverage
observation. These historical stride1 omissions do not establish a scheduling
failure, and the taxonomy does not prove that temporal projection will succeed.
Moving objects, parallax and OCR association remain limits. The four partial
cases need individual inspection before choosing a padding change.

Median leaking-box heights per interval are: three at most 12px, 54 in
(12,24]px, 41 in (24,48]px, and 24 above 48px. The failure class includes large
text as well as small text. Default nonexclusive photometric heuristics flag
14 low-sharpness intervals and 11 fast-pan intervals; zero satisfy the same-frame
motion-blur conjunction. These threshold-dependent counts are hypotheses, not
manual motion-blur labels. All generated images remain benchmark-only.

## Initial source-scheduled policy, seven tune clips

The full initial Vision policy (`regraded-v4-offline-vision-union-a30`) hides
370/435 natural and48/54 synthetic intervals, but protects8.19% of frames and is
rejected. Its65 failed natural intervals contain55 with a zero-overlap leak and
ten with only partial mask coverage; there are518 leaking frame/interval pairs.
Nonexclusive attributes include12 intervals with text height<=16px,15 near an
edge, six edge-entry candidates, seven fast-pan candidates and two low-sharpness
candidates. No interval meets the same-frame motion-blur conjunction.

Saved source-clock coverage shows31 intervals with zero overlap despite an
accepted **same-frame accurate-lane receipt**. This is direct evidence of an
omission by the accurate model/resize path, rather than merely insufficient
wall-clock detector throughput. Sixteen of those31 have a same-frame input OCR observation as well. The rest can
reflect interpolated truth; even direct observations can contain OCR association errors. Between-sample zero overlap occurs in54 intervals; those
cannot be attributed to timing alone because detection, independent object
motion, projection and interpolation remain alternatives. The overlapping counts
must not be added together. The compact receipt is
`bench/results/initial-clocked-policy-taxonomy.json`.

The historical taxonomy reader expects a performance record to obtain dimensions.
For this offline analysis only, a scratch adapter derived1280x720 from each
saved raster record and added that dimension field; it changed no scores,
truth, detections or pixels. Raw report, sample omissions and inspected contact
sheet are under `/tmp/agents/irl-shield/m1-async-taxonomy/`. Inspection confirms
examples of unmasked moving-vehicle text and small storefront text, while some
short OCR targets remain ambiguous. The current next lever is detector recall
and resolution; protection reliability is being addressed separately.

## Current E1 evidence: low protection is not sufficient

The complete seven-clip Small/Tiny phase-.05 card retains56 actual natural OCR-leak intervals plus10 intervals whose privacy credit is removed only because a clip fails the real-video guard. Its66 primary natural failures must not all be called detector misses. Synthetic failures similarly comprise6 actual leaked intervals and4 additional guard-only failures (44/54 credited hidden). These counts come directly from the retained interval flags and per-variant real-video verdicts, without rerunning OCR.

The area failure has an observed detector false-positive cause: on Mazatlan natural frame45, a clear view of feet and pavement, Tiny640 returns a95.3%-of-frame polygon at confidence.599 and Small960 a99.8% polygon at.508. This occurs with both Core ML and CUDA. The CPU probability/threshold probe and source frames are in `/tmp/agents/irl-shield/m1-mask-inspection/`; none is demo-ready. Raising pixel thresholds alone preserves giant regions on that frame; box-confidence.6 is the next measured experiment. This is not evidence that all large text boxes are false, so no area-based suppression is applied.

The6 actual synthetic leaks are4 Mazatlan intervals (plate4NV635; CEDAR AVE at78–79; plate7KQ482 at131–149; CEDAR AVE at148–149) and2 London-bus intervals (PINE STREET at96–97 and BXR219 at96). The known two-frame edge-entry intervals remain in ground truth. An8Hz source schedule skips both final frames148/149; increasing the fast rate is the next sampling experiment after confidence. Other partial-coverage and independent-object-motion causes remain hypotheses until the corresponding masks/detections are compared.

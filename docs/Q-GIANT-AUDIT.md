# Q giant audit

**Decision: do not integrate a confirmation or cap arm.** The literal
lane-overlap OR crop-recognizer rule is falsified. The new probes confirm unclip
inflation, but do not establish a safe rule that fixes the known guard failures.
Only the audit tool and these reports are proposed for application. No existing
source file, engine option, guard, scorer, judge, stream or transport changed.

Base `a8a06e30c2e5bdd8be054bbddf3c69169fe64e39`; branch
`elannash/q-giant-audit`, initially clean, now locked for Opus receipt review.
No commits, staging, pushes, PRs, Mac work, children or root source/cache writes.
Root's prescribed q-run leases are the only shared coordination writes.
Assets are benchmark-only, no music, not demo-ready. Candidate corpus quality,
area/protection deltas and real-video improvement are **null/not evaluated**.
The baseline/B12 aggregate status supplied by the conductor is not a result of
this lane. No held-out pixels were opened and no candidate all7 render was run.

## Exact historical diagnosis

`out/giant-audit/natural.json` and `synthetic.json` are read-only replays of the
sealed `out/q-base-a8a06e3-cache3-v3/mazatlan-aquiles-*` bundles. Both replay all
150 frames with zero mismatches: quads, coverage, control state, raster SHA256,
packed-mask archive bytes, and every incoming motion diagnostic. The complete
local pipeline fingerprint matches the sealed baseline:
`11af5d7146601537c87a5f5224a2f13bfb0ba5a7dbba7c992a3c99647a000c7e`.
See `out/giant-audit/source-identity.json` for constituent source hashes.

The tool recreates Detection records from exact saved receipt data and passes
them through the actual MaskingEngine and actual MotionHistory over sequentially decoded sealed input pixels. Each
projection call is tagged by receipt object identity, lane, source index and
quad index. This preserves actual before/after eligibility, completion deadline,
projection direction, path connectivity, timeline pruning and receipt union.
It is not a spatial-nearness match. Its interface is:

```sh
/home/elan/code/irl-shield/scripts/q-run \
  /home/elan/.t3/worktrees/irl-shield/t3-4fb60399 exec -- \
  /home/elan/code/irl-shield/.tmp/linux-probe/.venv/bin/python -u -B \
  -m bench.giant_audit --bundle /absolute/sealed/mazatlan-aquiles-natural \
  --out out/giant-audit/new-natural.json
```

Use the synthetic bundle for the other variant. Output creation is exclusive;
use a new output path when rerunning. The saved commands/logs and bundle/input
hashes identify the actual runs, not the illustrative `/absolute/sealed` path.

The selected population is encoded records with actual mask_fraction>=.5,
including protection: natural 82/150, synthetic 37/150. It is not a scored-window,
source-unique or OCR denominator. Natural selected frames are all LIVE.
Synthetic splits into 33 LIVE and 4 PROTECT (frames 64–67). Those 4 are caused by
`unresolved-motion-accurate-coverage`; they must remain fail closed. Removing
PROTECT or relabeling rejected detections as PROTECT is not proposed.

Natural's historical raw giants (quad 0 in every listed receipt):

| Lane / model | Source index | Raw quad area / frame |
| --- | ---: | ---: |
| fast / Tiny | 34 | .5470355903 |
| fast / Tiny | 38 | .6503190104 |
| fast / Tiny | 42 | .9249414063 |
| fast / Tiny | 45 | .9554492188 |
| fast / Tiny | 49 | .9443554688 |
| fast / Tiny | 53 | .7645117188 |
| accurate / Small | 38 | .9978309462 |
| accurate / Small | 45 | .9978309462 |
| accurate / Small | 53 | .9478700087 |

Every raw polygon and receipt timestamp is in
`out/giant-audit/historical-raw-giants.json`; every selected frame's connected
and rejected projection call, raw and projected polygon and lane union is in the
replay artifacts. For natural 45 the exact historical polygons are:

- Tiny: `[[0,0],[1278,0],[1278,676],[0,702]]`.
- Small: `[[0,0],[1279,0],[1279,719],[0,719]]`.

These are detector-origin giants. Phase motion translates individual polygons;
maximum normalized polygon-area change over all selected components in both
replays is below 3.4e-16. This does not mean motion is irrelevant to the union:
translated smaller receipts from multiple source indices accumulate over the
actual timeline and affect which pixels are masked.

Deleting every connected raw quad>=.5 as a **diagnostic counterfactual only**
still leaves 61/82 natural selected frames at>=.5 masked. Natural 45 remains
.5283951823 masked by smaller receipts alone. No policy that only changes the
triggered giants can reduce below that unchanged-union floor.

Other examples, computed with the unchanged production Renderer/padding:

- Natural 0: fast union .591948785; largest raw quad is source 0 area .235789931,
  padded individual .494164497. Aggregation takes it over the guard boundary.
- Natural 63: largest raw quad is fast source 60 area .377330729, padded/projected
  individual .624304470; total .638684896. A raw .5 trigger misses it.
- Natural 105: fast union .548825955, accurate union .017021484. Largest raw quad
  is fast source 113 area .123098958, projected/padded individual .153496094.
- Synthetic 90: fast union .532406684, accurate .050963542. Largest raw quad is
  fast source 113 area .145, projected/padded individual .169990234.
- Synthetic 105: total .568298611, fast .568250868, accurate .035314670.
  Synthetic has **zero** raw quads>=.5 in its entire historical receipt stream.

`bench/metrics.py:fidelity` requires at least half of raster pixels outside the
mask, as well as outside MAE<12 and std>8. Synthetic's 33 oversized LIVE unions
are consequently a different problem from a single detector giant. A .5
raw-giant-only rule is the identity operation on that synthetic stream, so it
cannot fix both Mazatlan guard failures. No guard is weakened.

## Confidence and the prior rejected rule

Historical detector confidence is **unavailable**. Saved detections carry quads,
source/completion PTS and diagnostic durations, but no box scores. Motion JSON's
confidence is a motion-fit heuristic, not detector confidence. Historical fields
remain null in every audit artifact.

Prior receipts were read directly in worktree `t3-1edd6a04`:

- `out/q2/retained-probability-probe.json`: Tiny640 area .952727322, boxscore
  .598573709; Small960 area .997830946, boxscore .508023693, pixel threshold .3.
  These are distinct area and score fields. This was a direct-source probe.
- `out/q2/recognizer-e1-cuda/probe.json`: pavement hallucinates `11` at .53872
  and is retained by the rejected .5 recognizer policy; all 8 positives retain.
- `out/q2/secondary-detector-cpu.json`: oblique BXR219 and 824 have zero spatial
  support, despite crop recognition BXR219 .99392 and 824 .9084. Rectification
  (`secondary-detector-rectified-cpu.json`) still misses both number views.

The old Tiny probe does not include the baseline fast lane's initial 640x360
resize. Its score cannot be attached to the baseline's historical Tiny quad.
Both lanes nevertheless produce giants in the actual historical receipts, so
lane agreement is independently insufficient. The conductor accepted rejection
of the literal overlap-OR-recognizer rule before new inference.

## New bounded tune/challenge probes

`out/giant-audit/probe/probe.json` records **new** CUDA inference with exact pinned
static Tiny/Small models, baseline preprocessing and parameters (.3 pixel,
.5 box, 1.6 unclip), OMP2/OpenCV1, nice10, app slice, canonical SH and per-host
quality serialization. Active providers and allowed CPU operator partitioning
are recorded; no timing or throughput qualification is claimed.

Population: natural source 34/38/45/53, synthetic 64/90/105; 8 hash-checked Q2
close-ups; 5 original full-frame synthetic street/store/plate/house 824/house 11
controls. There are 40 detector calls and 20 bounded crop recognitions in one
probe invocation, with no corpus OCR pass or scoring. All 12 source/lane pairs
that actually have a scheduled historical receipt reproduce its exact raw
geometry. Accurate 34 and accurate 64 are explicitly unscheduled new probes.

New frame 45 scores: Tiny `.6005475733978568`, Small `.5080196312209374`.
Raw areas remain `.95544921875` and `.9978309461805556`. These newly measured
scores are not historical receipt fields and differ from the prior probe's
scores. Source/model/tensor/map hashes are retained. Both unchanged baseline
lanes mask all known source ink in all 13 positive controls (1.0 each); that is
baseline-control evidence, not proof about an unimplemented filter.

### Density: no operational source glyph-height signal

The pavement crop again reads `11` .53872. A valid full-frame synthetic house 11
reads `11` .99976, and contains two source-space ink components of height 416px
(width 199/198px). The full-frame house 824 and all 8 earlier positives remain
mandatory controls. Short recognized text is not evidence that a giant is false.

The current crop recognizer gives text/confidence; its normalized 48px input
height is not source glyph height. The probe reports source glyph height null
for natural pavement, and source-space component boxes only where original
synthetic ink is actually known. No fabricated height or count-only rejection
is implemented. A general source-glyph-height estimator is not disproved;
it has not been defined or validated by this packet.

### Probability support: counterexample to simple high-support rejection

The probe observes the actual RapidOCR DB postprocessor, with exact contour to
output geometry matching. It records filled-contour probabilities, thresholded
foreground support, pre-unclip min-rectangle probabilities and output box score.
It does not zip sorted boxes to unsorted scores (the installed library sorts
geometry separately).

False Tiny pavement 38 versus true Tiny full-frame house 11:

| Statistic | False pavement 38 | True full-frame 11 |
| --- | ---: | ---: |
| pre-unclip box mean | .7857569145 | .6034748716 |
| filled-contour mean | .9448620081 | .9052463174 |
| contour p10 | 0.8969932973 | 0.6231491148 |
| pre-unclip rectangle median | .9860 (rounded) | .9496 (rounded) |

A monotone minimum on any of these shown summaries that rejects that false
pavement also rejects the required short-number positive. Even the 8 original
close-ups alone would miss this counterexample. This rejects these simple
one-summary arms, not every possible use of a probability map; no confidence
threshold search or multi-feature classifier was introduced.

### Unclip: cause confirmed, half-frame cap rejected as blocker fix

False frame 45 Tiny contour area is about .2428 of the map; its pre-unclip minimum
rectangle is .3706729834; post-unclip/clipping raw quad is .9554492188. Small's
pre-unclip rectangle is .4698265554 and final quad .9978309462. This is genuine
postprocessing expansion before MotionHistory. True close-up text also expands
strongly (for example oblique BXR219 Tiny .232770025 pre-rectangle to .7125 raw),
so expansion alone does not prove absence of text.

One scratch-only cap (`out/giant-audit/cap/cap.json`) reuses the saved maps with
maximum raw fraction .5. It reduces unclip expansion around the original
rectangle and never shrinks detected support; uncappable original support is
retained. The same knob applies to both lanes, with no family overrides.
All 13 positives retain all source ink under the actual Renderer, including
full-frame house 11. **The candidate is still rejected.** Capped frame 45 masks
.906357422 Tiny/.905570747 Small even for the single source receipt, after
unchanged padding. The actual timeline's smaller-receipt floor .5283951823 and
synthetic identity-operation argument are stronger evidence that it cannot
solve the blocker. No cap adapter or engine option is proposed for production.
A lower trigger, different expansion method or multi-feature confirmation would
be a different, unvalidated candidate; this report does not call it disproved.

## Verification, artifacts and limits

Eleven budgeted invocations, including 3 failures: missing user-bus setup before any
test; missing pytesseract in the GPU SDK for one existing test import; first
replay's 30-minute lease timeout before decoding. No failed attempt is hidden.
The retry used the existing complete CPU SDK and passed all 24 affected motion,
deadline and offline-schedule tests. A synthetic audit check preserves distinct
same-source lane identities, accepts exact replay, and rejects an intentionally
corrupted stored raster hash. Its deliberate-invalid-input branch is not a
production-policy red/green fix. There is no such fix or claimed policy
regression pair in this rejected lane. No new permanent test-only seam exists.

See `bench/LOG-giant-audit.md` for exact commands/counting, the retained command
scripts and logs in `out/giant-audit`, and `handback.json` for SHA256/Git blob
identities, patch and intended post-application file hashes. Files are
intentionally new/untracked; Opus applies the patch. Base HEAD is unchanged.
No full gate, Swift build, Mac OCR, final heldout or realtime qualification was
performed. No process remains from this lane at hand-back (see process receipt).

No new model, dependency, font, dataset or license was introduced. Existing
licenses: NumPy BSD-3-Clause; OpenCV/RapidOCR/Paddle OCR Apache-2.0; ONNX Runtime
MIT; ONNX Apache-2.0. Model identities/licenses are in models/manifest.json,
models/licenses/dependencies.json and probe metadata; natural fixture attribution
is in fixtures/ATTRIBUTION.md. Generated challenge labels are original synthetic
assets and benchmark-only. Models/root caches were read-only; before/after file
hashes and mtimes are in the receipt. Decoded frames remain OS-cleared scratch at
`/tmp/agents/irl-shield/giant-audit/`; review outputs live in this worktree's
ignored `out/giant-audit/`. Neither contains an approved demo or quality claim.

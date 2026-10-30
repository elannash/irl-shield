# Q1 edge clamp: hypothesis falsified

Q1 finds no edge-clipping defect in the requested retained tune evidence. Keep
`shield/motion.py`, `shield/render.py` and their tests unchanged. The branch is
`elannash/q1-edge-clamp`, renamed in place from `t3/q1-edge-clamp`, at the exact
clean starting HEAD `0648e0f64d599b223d101f6643ed7d75a36331e3`. No staging,
commits, pushes, PRs or merges were performed.

The hypothesis was that projected quads crossing the frame were clipped to
empty or dropped. The evidence instead shows retained offscreen vertices,
correct clipping of visible polygon portions, and missing target geometry
before rasterization. This does not establish the cause of every OCR leak.

## Projection and raster evidence

`MotionHistory.project_many` transforms every vertex and returns the entire
receipt (`shield/motion.py:216`). It has no frame-edge clipping operation. A
missing transform, invalid projective denominator, or inconsistent denominator
sign returns `None` for the entire receipt. That is unresolved motion, not an
empty detection. The engine ignores that receipt and still requires valid
coverage from both lanes (`shield/engine.py:111`). Q1 preserves these invariants.

`Renderer.render` expands the original convex hull before clipping its ROI
(`shield/render.py:79`). Only the raster bounds are intersected with the image
(`shield/render.py:95`); fixed-point polygon coordinates retain the offscreen
vertices. OpenCV fills the visible portion inside that ROI. Q1 does not clamp
corners or convert invalid geometry into coverage.

The diagnostic uses full-canvas rasterization of each **unexpanded** original
quad as an independent interior oracle. It does not reuse renderer padding or
ROI arithmetic. It separately compares the complete production-rendered mask
with each saved raster's SHA-256 and mask area. Source and artifact hashes are
recorded in `out/q1/retained-edge-audit-pinned.json`.

The sample is exactly the 15 `near-edge` intervals in the historical initial
Vision taxonomy, all of their leaking frames, and PP Small phase-.05 synthetic
Mazatlán frames 78, 79, 148 and 149. These are tune data only. The historical
15 are scored intervals across natural and synthetic variants, not 15 unique
physical signs or a PP Small truth denominator. That old taxonomy is diagnostic
history; it is not a new primary scorecard.

- 45 distinct historical frame records plus four PP synthetic frame records.
- All 49 saved mask hashes and areas reproduce exactly through the current renderer.
- 206 occurrences of quads with offscreen vertices; 128 have visible original polygon pixels.
- Zero original visible polygon pixels are lost by the padded renderer.
- Ten of the 15 intervals have no target overlap in any audited leaking frame;
  five have some padded overlap. Their per-frame counts and identifiers are
  retained, without changing OCR association or truth.

| PP synthetic frame | Visible target AABB pixels | Original quad overlap | Actual padded mask overlap | Coverage |
| --- | ---: | ---: | ---: | --- |
| 78 | 5,270 | 0 | 0 | LIVE, fast age 1, accurate age 5 |
| 79 | 4,080 | 0 | 0 | LIVE, fast age 0, accurate age 4 |
| 148 | 15,080 | 0 | 0 | LIVE, fast age 1, accurate age 5 |
| 149 | 21,141 | 0 | 0 | LIVE, fast age 2, accurate age 6 |

At 78/79 the only offscreen quad is entirely left of the image, away from CEDAR
AVE at the bottom. At 148/149 two quads straddle the left edge and render
6,668/6,164 and 6,291/5,810 original visible pixels respectively, with no loss.
CEDAR AVE is on the right. There is no target quad for an edge clamp to recover.
The inspected input/output/mask crops remain at
`/tmp/agents/irl-shield/q1-edge-clamp/cedar-edge-frames.png`. They show actual
unmasked synthetic lettering; they are benchmark-only, not demo assets.

Cached detector replay through the real `MaskingEngine`, `MotionHistory` and
`Renderer` covers the seven historical clip variants containing the 15
intervals: 1,050 decoded frames and 520 projection calls at the audited target
frames. There are 81 unresolved whole receipts and zero partial receipt drops.
Every non-null projection preserves its input quad count. A separate 150-frame
PP replay records 36 target-frame projection calls, five unresolved and zero
partial drops. Frame 78 has an unreliable motion step, both in the original
diagnostics and in replay. Later accepted detections cover other objects; the
8 Hz schedule samples 147 but neither 148 nor 149. No sampling or motion policy
is changed in this lane.

**Replay limit:** Linux decoding/motion estimates do not reproduce the retained
Mac floating-point quads or masks bit for bit. The PP replay reproduces 12/150
mask hashes and 4/150 quad lists; the maximum target-frame coordinate difference
is 0.1293 px. All 150 coverage verdicts match. This replay establishes the path
and absence of selective drops, not an exact cross-host output comparison. The
49 saved-quads-to-saved-mask checks above *are* exact. No wall-time or privacy
acceptance is inferred from replay.

## Checks and red-capability

Seven executable diagnostic cases cross the public motion/render seams: four
boundary slivers, a rotated quad, a fully offscreen quad, and unresolved motion.
Expected masks are literal worked pixel examples, including the renderer's
documented 3 px padding floor. Expected covered counts are 36, 27, 36, 27, 48,
and zero. Unresolved motion must remain `None`.

The deliberate renderer mutation drops any quad with an offscreen corner.
It physically changes the `visible` predicate and fails with
`left-sliver: visible pixels differ` (exit 1). Restoring the renderer byte for
byte makes the same command pass (exit 0). This is a positive control for the
diagnostic, **not a claim that the unmodified engine had the bug**. The diff,
red/green logs and hash receipt are in `.tmp/q1/edge-drop-*` and
`.tmp/q1/renderer-drop-mutant.diff`. The renderer's restored SHA-256 is
`e197ebec4b7aaeb6f762d7742bcc94d2665528dbc820d990a85d4bd3179007d3`.

The affected motion/render suite passes ten tests. One complete Linux
functional run passes 105 main tests (one platform skip), three relay tests,
and Python compilation. Exact commands and exit codes are in
`.tmp/q1/linux-functional-gate.json`; the full log is
`.tmp/q1/linux-functional-gate.log`. It runs at nice 10 in the agent slice,
with native workers capped at two and OpenCV at one. The Mac Swift bridge
build is not exercised by that Linux run. No production regression test was
added because Q1 found no production bug or behavior change.

## Quality receipts and decision

No new score is claimed from geometry or cached detections. The primary
contract remains independent natural truth and synthetic input controls
(Tesseract + Vision for PP) and leaks from **all** output judges, including PP.
Synthetic annotations remain unchanged. The following complete seven-clip,
14-variant cards are historical context, read from the corrected retained
rescore; they are different execution modes and are not a one-knob comparison.

| Historical primary card | Natural | Synthetic | Median / p95 area | Protected aggregate / worst variant | Real video |
| --- | --- | --- | --- | --- | --- |
| E1 Small phase .05 offline | 293/343 (85.42%) | 44/54 (81.48%) | 12.692% / 55.512% | 0.286% / 2.667% Mazatlán synthetic | false |
| Linux static Small real clock | 304/343 (88.63%) | 44/54 (81.48%) | 13.777% / 56.675% | 0.619% / 7.333% Mazatlán synthetic | false |

Both fail the per-clip protected guard and real-video guard. Neither is an
accepted Q change. Both medians are below the proposed 15% ceiling; that does
not waive any other guard. Full paths and SHA-256s, per-variant fields, model
identities and the absence of a measured Q1 delta are in `out/q1/handback.json`.

**Decision: reject the proposed edge-clamp intervention; retain the engine
unchanged.** No accepted privacy, area, protection, throughput or latency
improvement is claimed. The root common CUDA/NVENC offline baseline and fresh
Mac OCR are still pending the root pilot/queue release. Heavy rendering and
Mac OCR have not been launched by Q1. A no-change lane can reference the shared
baseline once its source/options/input identities and actual card are verified;
the historical cards above cannot substitute for it.

Root subsequently mandated five P2 benchmark corrections before Q acceptance:
registry-only family provenance, independent-engine gate tests, the shared fast
default, OpenCV/tessdata cache identity, and venv exclusion. Q1 has passed no
`detector_families` override, including an empty override. Its initial unit and
functional evidence belongs to `0648e0f`, before that follow-up. Final Mac OCR
and Q scorecard acceptance remain held for root's fixed-head/harness notice.
Root owns the common-source rebase; these lane-owned files remain uncommitted.

## Reproduction and hand-back

The pinned lightweight diagnostic ran with the shared root harness, without
copying or editing its common files:

```sh
/home/elan/code/irl-shield/scripts/q-run "$PWD" exec -- \
  /home/elan/code/irl-shield/.tmp/linux-probe/.venv/bin/python -u -B \
  -m bench.q1_edge_audit \
  --taxonomy /tmp/agents/irl-shield/m1-async-taxonomy/report/taxonomy.json \
  --historical-root /home/elan/code/irl-shield/out/offline-vision-union-a30 \
  --pp-root .tmp/q1/e1-small-phase-005 \
  --out out/q1/retained-edge-audit-pinned.json
```

Replay commands for all seven historical variants are stored literally in
`.tmp/q1/projection-replay-launches.json`. Each replay takes and releases a
separate canonical shared lease. The four-target PP replay command is recorded
in the lane log. This work introduces no package, model, dataset, service or
license. Existing model licenses are retained in the model metadata; existing
fixture attribution remains in `fixtures/ATTRIBUTION.md`.

Owned source deliverables are `bench/q1_edge_audit.py`,
`bench/q1_projection_replay.py`, this document, and `bench/LOG-q1.md`. Generated
receipts live in `out/q1/` and `.tmp/q1/`; they are gitignored. All source
deliverables are intentionally unstaged/untracked for Opus to review and commit.
No Mac mirror or retained background job was created. No held-out path was read.

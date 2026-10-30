# Q3: older-receipt persistence

Status: investigation in progress; no accepted policy or engine change.

The lane started at `2026-10-30T04:47:21Z` in the dedicated worktree
`/home/elan/.t3/worktrees/irl-shield/t3-4b7457f3`, clean at
`0648e0f64d599b223d101f6643ed7d75a36331e3`. The prepared branch
`t3/q3-persistence` was renamed in place to the requested
`elannash/q3-persistence`. No staging, commits, pushes or PR work is authorized.
The six-hour deadline is `2026-10-30T10:47:21Z` (03:47:21 PT).

On explicit root instruction, `git merge --ff-only` advanced this dedicated
branch to `efd513fe079c14ab4af4d9f0f9c1fcc78b855c96` for the P2 fixes,
preserving both owned untracked documents. This is a base advance; no Q3 commit,
staging, push or PR merge occurred. Engine, motion and renderer hashes remain
identical to the original probe source. `out/q3/p2-source-hashes.json` records
the updated common source; the original hashes remain retained.

A second explicitly authorized fast-forward advanced the branch to
`f2f57892b731949d17ce62ba4dcd84d74fb26ab0`, preserving the two untracked
documents. B12 still differs from the supplied policy only in `before`;
no family override is present. PR #4 review and the root's frozen manifest and
exact launch notice remain pending. The root explicitly requested idle state
with no GPU, Mac OCR or tests during this hold. Verification usage is 2/24;
the original deadline remains `2026-10-30T10:47:21Z`.

## Hypothesis and scope

Increasing B from 6 to 12 frames may close short gaps after the last text
detection by retaining older, motion-projected quads. A30 already paints
before later detections. Only `options.before` varies: Small accurate 4 Hz at
1280/side960, Tiny fast 8 Hz at 640/side640, D1, A30, phase320 response .05,
padding .3, opaque, static ONNX, CUDA and NVENC remain fixed. Fast and accurate
coverage age limits remain 6 and 12 frames.

The existing implementation is sufficient for the experiment:

- `shield/engine.py`, `_coverage_and_quads`: available receipts must have no
  error and complete by the presentation deadline. B/A restrict source indices;
  `project_many` must accept the receipt's motion path. The nearest connected
  receipt determines each lane's age, checked against the separate limit.
- `shield/engine.py`, `poll`: history retention uses the same B value.
- `shield/motion.py`, `MotionWorker.project_many`: all motion frames must
  complete by the deadline. Synchronous `MotionHistory` is the existing offline
  adapter, with virtual source-clock completion; it establishes no runtime claim.

The engine seam remains frames/control in, masked frames/masks/coverage out.
No new interface or host-specific engine is needed.

## Preliminary receipts

`out/q3/literal-persistence-probe.json` records a small synthetic-pixel check
through `MaskingEngine.submit/poll` and the real `MotionHistory`. A first-frame
quad followed by fresh empty receipts stops painting at frame 7 with B6,
continues through frame 12 with B12, and expires at frame 13. Both policies
remain LIVE with nearest receipt ages zero. At B24, first-frame-only receipts
become PROTECT at frame 7; failed, late, and disconnected old detections do not
paint over fresh current-scene coverage. This is diagnostic verification of
existing behavior, not a new numeric-option unit test or a red/green bug fix.

`out/q3/historical-gaps.json` and
`out/q3/historical-persistence-opportunities.json` inspect all 14 variants of the
historical **offline Core ML** `e1-small-phase-005` tune run. Input interval
truth is independent and leaks include every judge, but OCR uses the old cache.
These artifacts cannot serve as the new Linux baseline.

The candidate screen associates a detection with an independent input
observation at the **exact receipt source frame** when the axis-aligned quad
bounds overlap at least half the input box, then checks that all intervening
motion edges are valid. This is necessary evidence for a plausible older
detection, not proof of correct projected geometry or closed leaks. Missing
same-source observations can hide opportunities from this screen.

It finds plausible connected older detections for six leaking intervals at
B12 (four natural, two synthetic), the same six at B18, and seven at B24.
B12 therefore provides the first useful experiment. B18 adds no intervals to
this preliminary screen.

Historical Mazatlan has 78 natural and 33 synthetic LIVE frames with over-half
raster masks, all failing the real-video guard. With identical receipts and
motion, B increases produce a mask superset on already-LIVE frames. They
cannot repair an existing over-half mask failure. The refreshed common Linux
baseline must establish whether that obstruction remains in the comparable run.

## Acceptance and pending work

Use only the root's shared cross-host harness: seven tune clips, natural and
synthetic (14 variants), identical sealed inputs and annotations, refreshed
independent input truth and all-judge output leaks. No held-out reads, new
models, downloads, installs or licenses are needed. The proposed median area
ceiling stays 15%; aggregate and per-clip protection and real-video guards
remain binding. Every diagnostic cost is untimed, with no performance claim.

The root has supplied `scripts/q-run` and `bench/quality_bundle.py`. They are
called from the root checkout without copying or editing common helpers.
`out/q3/b12-policy.json` differs from the supplied base policy only in B6 ->
B12; neither config uses a detector-family override. The sealed input manifest
and config/helper hashes are retained in `out/q3/`.

Root review requires five P2 benchmark fixes before accepting results: registry
family enforcement, independent-engine gate tests, shared fast-lane defaults,
OpenCV/tessdata cache identity, and venv exclusion. Mac OCR and final acceptance
remain held until PR #4 merges and the root sends the frozen common CUDA/NVENC
baseline launch. PR #3 merged as main `62b536f`; the retained-scoring,
retry-headroom and harness followups are now in the Q3 base at `f2f5789`.
Their presence does not release the hold. The unjudged root CUDA pilot is not
a score.

Pending: root fixed-source notice and common baseline; all-seven B12 scorecard; exact
hashes/commands and same-mode deltas; bounded decision on B18/B24; one full
functional gate; final diff/artifact inspection; final process-exit proof and
`out/q3/handback.json`.

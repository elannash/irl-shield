# Offline quality bundles

The common adapter renders on Linux CUDA/NVENC and judges the actual sealed
movies on the Mac with Tesseract, Vision and PP recognition. It calls the same
`render_offline` engine path and `_score_saved` scorer as the existing bench.
It never treats unjudged pixels or offline timing as a privacy/performance pass.
Fixtures remain benchmark-only, without audio, and are not demo-ready assets.
Licenses remain in fixtures/ATTRIBUTION.md and models/manifest.json; there are
no new packages, models or datasets.

Status: PR #3 is merged as `62b536f`. Two retained-judging followups and this
harness's separate reviewed commit precede accepted fresh quality cards.
The preparation at `.tmp/q/baseline-preparation-efd513f.json` is superseded by
these changes. No fresh quality result is claimed by this document.
The pre-P2 pilot under out/q-base-v1 is ungraded and will not provide Q numbers.

## Source and locks

Call the absolute root script with the lane's own worktree. It imports the
lane's engine/model/render modules, never substitutes the root engine. Each
clip holds the canonical shared perf lease and a root-local exclusive quality
lease, so a host has one heavy quality job at a time. Timed jobs still use their
exclusive canonical lease and the perf queue. Release leases between clips;
do not wrap the entire corpus in a second shared lease. Linux runs nice10 in
the agent slice, uses pinned private CUDA libraries and per-worktree CUDA cache;
native workers are two and OpenCV uses one thread in rendering and grading.
Each command's process group is bounded to 30minutes, including subprocesses.
The task's earlier timebox still applies.

`scripts/q-run WORKTREE exec -- COMMAND ARG...` is the same locked, untimed
path for one short diagnostic. It is not a performance receipt.

## Render, grade, aggregate

Root provides `.tmp/q/inputs.json` containing exactly seven tune clip pairs,
original input/truth paths and hashes, and `.tmp/q/base-policy.json` with the
fixed Small960/Tiny640 CUDA4/8Hz, D1/A30/B6, phase320/.05, opaque .3padding,
NVENC policy and the proposed15% area ceiling. These are task scratch, not a
new dataset or a replacement committed baseline. No family overrides are
allowed; the candidate/lane registry determines truth families.

```sh
/root-checkout/scripts/q-run /lane-worktree render \
  --inputs /root-checkout/.tmp/q/inputs.json \
  --config /lane-worktree/.tmp/policy.json \
  --directory /lane-worktree/out/trial/CLIP-natural --clip CLIP
```

Add `--synthetic` for its annotated counterpart. Detectors come directly from
the registered policy. The unused arbitrary adapter hook was removed because
it could introduce an undeclared detector family. A later ensemble needs a
registered policy and its own source/model provenance.

Rendering writes source, truth, encoded output, actual packed raster masks,
source-index detector receipts, motion verdicts and engine diagnostics. The
version-2 bundle manifest hashes every artifact and has its own sidecar hash. There is
no natural/synthetic credit until grading. Changing a covered artifact fails
before any OCR call, as exercised by the integration test and physical guard
mutation. The input manifest is read once and sealed as `inputs.json`; copied
source and truth bytes must match that snapshot before any model is loaded.
Verification repeats that binding. Earlier version-1 pilot bundles are rejected.

Sync the lane's exact source and bundle into its own Mac mirror, excluding git,
venvs, caches and other output. The shared root helper/script also exists on the
Mac. Grade using that root script, the lane's mirror as WORKTREE, and the local
bundle path:

```sh
/root-mirror/scripts/q-run /lane-mirror grade \
  --directory /lane-mirror/out/trial/CLIP-natural \
  --cache /root-mirror/out/judge-cache
```

The same scoring source and helper must match the render provenance. Grading
verifies bytes and source identity before and after OCR, preserves raw readings, and uses
independent input truth/controls with all output judges. It also verifies
actual outside-mask video. Grade/evidence hashes are checked on aggregation.
After exactly all14 variants have been graded on the Mac:

```sh
/root-mirror/scripts/q-run /lane-mirror aggregate \
  --directory /lane-mirror/out/trial --run-id TRIAL
```

The complete card reports natural/synthetic hidden fractions, median/p95 area,
real-video preservation and aggregate/per-clip protection. A missing or duplicate
variant cannot aggregate. All fourteen plans must share an input-manifest,
pipeline and helper identity. Aggregation reads masks only from each current
verified bundle directory; old absolute grading paths cannot supply masks
after a bundle moves. The scorecard retains that common run identity.
`real_time_verified` and gate eligibility remain false.
A new trial uses a new directory; no command overwrites an earlier bundle/grade.

## Verification receipts

- tests/test_quality_bundle.py renders synthetic frames through the engine and
  FFmpeg. Its reader depends on actual input/output pixels; natural/synthetic
  denominators and hiding credit are asserted. It retains pre-OCR integrity
  checks, rejects mixed manifests and copy races, proves a manifest is one
  snapshot, and demonstrates that relocation cannot read forged mask fractions
  through an old grading path.
- `.tmp/q/harness-review-red.log` reproduces both aggregation holes.
- `.tmp/q/harness-copy-red.log` reproduces source/truth copy races and a manifest
  identity changing during rendering.
- `.tmp/q/harness-review-proof/mutations.json` records physical mutations that
  score output pixels as input and disable artifact checks. Each fails its
  assertion, then passes after exact source restoration.
- `.tmp/q/compile-venv-red.log` shows the Python3.14 NumPy syntax failure under
  Python3.11; `.tmp/q/compile-venv-green.log` shows source compilation with the
  ignored-venv exclusion.
- Earlier integrated Mac/Linux functional gates passed at `efd513f`: 126 main
  tests and three relay tests on each host, compilation, and the Mac Swift
  build. These runs include the experimental bundle test. They establish
  functional checks, not a fresh quality or performance score.

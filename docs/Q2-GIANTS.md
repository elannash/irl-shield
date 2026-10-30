# Q2: confirmation of giant detector quads

Status: rejected tested policies; optional prototypes remain uncommitted for review. Work started 2026-10-30 04:47:20 UTC;
stop by 10:47:20 UTC (six-hour packet timebox, before the 14:00 UTC deadline).
Requested and actual branch: `elannash/q2-giants`. Initial prepared branch:
`t3/q2-giants`. HEAD: `0648e0f64d599b223d101f6643ed7d75a36331e3`.
The initial worktree was clean. No commits, staging, pushes, or PRs are authorized.

## Diagnosis and hypotheses

The retained Mazatlan natural frame 45 was opened, not merely inferred from a
score. It shows feet and pavement and no readable location text. Its raw
probability receipt reports Tiny640 at 95.272732% frame area (score .598574)
and Small960 at 99.783095% (score .508024), both at pixel threshold .3.
Sources: `/tmp/agents/irl-shield/m1-mask-inspection/mazatlan-natural-45.png`
and `probability-probe.json` in that directory. These are benchmark-only assets.

The sealed Linux static Small output's frame 45 has mask_fraction 1.0, state
LIVE, protected false, coverage ok; its raster mask is hashed
`cd1fb537c37464dc6bc2db970eb5416d81a8d9a72df3ecc98e44d3a083380fef`.
Source: `/home/elan/code/irl-shield/out/linux-static-small-tune/mazatlan-aquiles-natural-masked.masks.json`,
frame record 45. Detector quads precede motion; the raw probability receipt
shows the false region without relying on a tracking explanation.

Ranked falsifiable hypotheses:

1. A PP English recognizer on a rectified candidate crop rejects false pavement
   while retaining large close-up text, including high-angle text. Predict:
   negative confirmation on frame 45 and positive confirmation on all challenge
   text cases using identical thresholds. Failure rejects this policy.
2. An alternate PP detector provides spatially comparable corroboration on true
   close-ups but not pavement. Agreement of the existing Tiny/Small pair is
   already falsified by the retained receipt: both produce false giants.
3. Confirmation misses hard real text or repeats pavement hallucinations. If
   challenges expose this, do not promote the filter regardless of area savings.

## Seam and test scope

`QuadConfirmationDetector.detect_quads(pixels)` wraps an existing detector.
Area at least 50% of input image only triggers confirmation; it never directly
rejects. Ordinary quads pass unchanged. A confirmer takes the same pixels and
quad and returns True (retain), False (reject), or None (uncertain, retain).
Injected adapters own model selection. No engine subclass or second engine.

Existing seam is sufficient. Root can wrap each `backends[lane]` after its
normal common factory creates it and before `render_offline` receives it:

```python
from shield.quad_confirmation import QuadConfirmationDetector
backends[lane] = QuadConfirmationDetector(backends[lane], confirmer,
                                         large_fraction=.5)
```

There is no proposed common-engine patch. Confirmers must be separately owned
per lane; wrappers own/close their detector and confirmer. A PP recognizer stays
Paddle family. Vision is judge only. Full quality options, static shapes,
providers, source clocks, and encoders must match the root common baseline.

The new test owns adapter selection at the production detector seam. It catches
both leaving a known false giant and blindly dropping equal-size real text,
while retaining an ordinary quad. The actual Renderer observes resulting mask
pixels. Synthetic pixel recognition is a controlled external-model fake, not
proof that PP can distinguish those images. Real-model challenge probes and the
all-seven tune quality card remain separate required evidence for acceptance.
No test-only production hook is introduced. Existing lane/offline tests do not
exercise confirmation because it did not exist at the fixed base.

## Experiment ledger

- E0: two existing detector lanes agree on false pavement. Reject that
  confirmation rule from retained raw evidence; no new inference or cost.
- E1: crop recognition at the existing .5 confidence threshold, giant trigger
  .5 frame area. Planned; GPU/Mac work held until shared harness authorization.

## Verification ledger

1. `python -B -m unittest discover -s tests -p test_quad_confirmation.py -v`:
   RED with pass-through adapter, expected `[ORDINARY]` but actual included GIANT;
   one test, failure. Receipt `out/q2/test-01-red.log`.
2. Same command after confirmation selection implementation: GREEN, one test.
   Receipt `out/q2/test-02-green.log`.

Both used existing `/home/elan/code/irl-shield/models/.venv311/bin/python`,
`nice -n 10`, OMP_NUM_THREADS=2, OPENBLAS_NUM_THREADS=1. No install/download.
Test budget: 8/24 invocations (six affected-test runs, main suite and relay suite). Full Linux functional gate passed once at the end.
All timings in any Q2 diagnostic will be untimed observations, never performance
acceptance. No score, guard improvement, or all-seven result is claimed.

### Additional TDD slices

3. RED: unavailable confirmation raises instead of retaining the original quad;
   uncertainty counters are absent. `out/q2/test-03-red.log`, two test methods.
4. GREEN: uncertain/failed confirmation keeps its original mask and explicitly
   reports uncertainty/error counts. `out/q2/test-04-green.log`.
5. RED: stubbed crop recognition always confirms; a blank candidate is rescued
   by unrelated ink elsewhere in the frame. `out/q2/test-05-red.log`.
6. GREEN: rectified crop input and confidence discriminate the two regions.
   `out/q2/test-06-green.log`, three methods pass.

The latter model-boundary test checks real crop selection with a synthetic
external recognizer. It catches accidental full-frame reading, which the
adapter-selection test cannot observe. The uncertainty test catches recognizer
errors turning into lost masks; stats explicitly surface these errors. No
production caller is added only for tests.

### E1 falsification

The nine-case CPU challenge probe was run under the shared canonical perf lock,
app-t3code-agents.slice, nice10, native workers2 and OpenCV threads1. Its exit0
only establishes completion; its artifact says pass=false. No GPU or Mac OCR
was launched. Command:

```sh
XDG_RUNTIME_DIR=/run/user/1000 \
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus \
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=2 \
systemd-run --user --scope --slice=app-t3code-agents.slice nice -n 10 \
timeout 60 scripts/host-lock shared \
/home/elan/code/irl-shield/models/.venv311/bin/python -B -m bench.q2_probe \
  --out out/q2/recognizer-e1-cpu \
  --pavement out/q2/sealed-mazatlan-natural-frame45-input.png \
  --cache-dir /home/elan/code/irl-shield/models/cache --provider cpu
```

Reading `out/q2/recognizer-e1-cpu/probe.json`: the sealed decoded frame45
pavement hallucinates `11`, confidence .53872. The .5 policy retains its giant;
the rendered mask remains full frame. All eight original synthetic close-up
street/store/plate/number front/oblique cases retain. Their confidence range
is .57426–.99992. This does not prove real-world safety; E1 is rejected because
it fails the concrete false-pavement test. Diagnostic call observations span
.03356–.04325s; these are untimed CPU observations, not throughput/latency or
performance acceptance. The PP recognizer model hash is
`c3461add59bb4323ecba96a492ab75e06dda42467c9e3d0c18db5d1d21924be8`.

Generated challenge images were inspected (including oblique two-line store).
The sealed input and near-black output were opened for visual diagnosis.
The output decoded pixel range is 0–2, consistent with encoded opaque masking.
`out/q2/retained-diagnosis.json` scans only the 14 sealed tune mask artifacts,
all encoded records (450 each, 6300 total), rather than a source-unique or
scored-window denominator. Its mask counts are diagnostics and are not scores.
No held-out files were opened by this lane.

### E1 provider confirmation through the shared root harness

After root authorized lightweight challenge execs, the identical nine cases
were run using the pinned Linux CUDA environment and common serialized quality
lease. No corpus render or Mac OCR was run. Command:

```sh
/home/elan/code/irl-shield/scripts/q-run \
  /home/elan/.t3/worktrees/irl-shield/t3-1edd6a04 exec -- \
  /home/elan/code/irl-shield/.tmp/linux-probe/.venv/bin/python -u -B \
  -m bench.q2_probe --out out/q2/recognizer-e1-cuda \
  --pavement out/q2/sealed-mazatlan-natural-frame45-input.png \
  --cache-dir /home/elan/code/irl-shield/models/cache --provider cuda
```

`out/q2/recognizer-e1-cuda/probe.json` was read. CUDAExecutionProvider is active,
with explicitly recorded CPU operator partition fallback allowed. Pavement
again hallucinates `11` at .53872 and stays fully masked. Eight of eight
synthetic positives retain. The pavement after image was opened and remains
black. This replicates the failed discrimination on the primary host/provider;
it is not an offline-baseline comparison or any performance acceptance.

### E2 alternate PP detector, rejected with a safety counterexample

Two bounded CPU diagnostics used pinned PP-OCRv5 mobile at side640, confidence
.5, workers2, cv1 and the same shared lock/app slice/nice10. They do not modify
the engine or choose an acceptance threshold. Exact scripts are retained in
`out/q2/probe_detector.py` and `out/q2/probe_detector_rectified.py`, with logs
`secondary-detector-cpu.log` and `secondary-detector-rectified-cpu.log`.
Commands used the same systemd/timeout/shared-lock prefix as E1 CPU, with
`PYTHONPATH=.` and existing Python to execute respectively
`.tmp/q2/probe_detector.py` and `.tmp/q2/probe_detector_rectified.py`.
The retained scripts are byte copies of those executed.

Direct detection receipt: `out/q2/secondary-detector-cpu.json`. Pavement yields
one supporting quad covering 4.85776% of the giant. Therefore any-support
confirmation also retains the false giant. Demanding spatial comparability
cannot preserve the oblique plate `BXR219` or number `824`: both return zero
secondary detections, while E1's independent recognition of those synthetic
inputs reads them at .99392 and .90838. The oblique `824` image was opened and is
clearly readable. No positive spatial-support floor can retain a zero-support
candidate. This is a concrete false-negative/privacy counterexample.

To distinguish a perspective failure from a confirmation-policy failure, a
second diagnostic rectified the exact annotated candidate before resizing to
a fixed 640x352 detector input. Receipt:
`out/q2/secondary-detector-rectified-cpu.json`. Pavement still gives a 5.00181%
support. Street-oblique and both number-front/number-oblique return zero
support. Dewarping does not resolve the counterexample. This changes only
input rectification and is separately labeled; it is not pooled with E1 or a
one-knob corpus comparison. The PP-v5 model SHA is
`4d97c44a20d30a81aad087d6a396b08f786c4635742afc391f6621f5c6ae78ae`.

No confidence-threshold search, ensemble, additional model, or external service
was attempted. On root's explicit steering, these tested arms are rejected
before an all-seven run. This conclusion does not rule out every conceivable
confirmation policy. The actual huge-quad failure is confirmed, not falsified.

## Final hand-back

- Decision: reject E0 existing-lane agreement, E1 .5 crop recognition, and E2
  alternate-detector support (direct and rectified). No default pipeline change,
  accepted detector policy, or common hook was introduced. Optional adapter and
  E1 prototype are uncommitted review material, not approved integration.
- Corpus natural%, synthetic%, median/p95 area, real-video guard, aggregate and
  worst-clip protection, and baseline deltas: **null / not evaluated** for Q2.
  No all-seven scorecard exists. Root explicitly authorized challenge-only
  rejection and prohibited expanding to ensembles/higher thresholds.
- Historical sealed Linux reference only: primary304/343 natural,44/54 synthetic;
  p50 area13.7772895%, p9556.6750814%; real-video false; aggregate protection
  .6190476%, worst clip7.3333333% (Mazatlan synthetic). This is the original
  real-clock reference, not the common offline baseline or a Q2 comparison.
  Counts come from fixed-base rescore; area/protection from original scorecard.
- Full Linux functional gate:108 main tests (one platform skip),3 relay tests,
  Python compilation, exit0 in one fail-fast shell command. Receipt:
  `out/q2/test-07-full-functional-gate.log`; executable command copy
  `out/q2/full-functional-gate.sh`. No production model/OCR/network was exercised
  by those synthetic tests. Swift optimized build and Mac gate were not run.
- No package install, model download, new SDK/model/dataset license, secret,
  Twitch operation, external publishing, Mac write, or owned retained process.
  Existing dependency/model license pointers are recorded in prototype headers.
- Source/model/input/artifact hashes and process exit checks are in
  `out/q2/handback.json`. `git diff --check` passes. All changes are new owned
  files, untracked/uncommitted intentionally; no existing common file changed.
- Unfinished by rejection scope: safe confirmation algorithm, all-seven primary
  quality/guard evaluation, regression in an accepted integrated policy, Mac
  mirror/platform gate, realtime costs, and deployment. No held-out reads or
  tuning were performed. There is no accepted quality or performance claim.

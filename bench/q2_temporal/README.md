# Q2 temporal readiness — HELD

Code readiness PASS; evaluation BLOCKED. No arm quality, screen, video, OCR,
Mac, GPU, CUDA, ORT or NVENC execution took place. No winner or near miss exists.
PHONE_TEST_DONE/GPU_RELEASED and an exact root-relayed V2_FROZEN manifest SHA
are absent. These are independent barriers. Do not infer release from idleness.

Base: `65891cb0b515bc0c34ec4ded89aa6a3228992cc2`.
App branch: `t3/temporal-optical-flow-tracking`, unchanged and locked.
Worktree: `/home/elan/.t3/worktrees/irl-shield/t3-26ca396c`.
Task: <t3-thread://v2/a3857748-9579-4ce2-b37e-5d3cd3faad44/thread:delegated-task:command%3Amcp%3A4604c41b-99c6-432d-bed9-120571e9de69%3Adelegate-task%3A22093f51-5cd1-411b-a06d-bd805ee95e07>.
No staging, commits, pushes, PRs, delegation or other-worktree edits.

## Implementation and opt-in

`policies/flow.json` differs from `policies/baseline.json` in just
`options.motion_mode = "flow"`. Pass its options to the existing MaskingEngine.
Baseline phase/ORB computation, engine phase default, renderer, lane union,
coverage ages, receipt deadlines, padding and protection behavior are retained.
The supplied JSON policies copy the historical frozen baseline OPTIONS, not
historical results. They must produce a NEW paired baseline on the final source
fingerprint before any comparison. `arms.policy_for(new_baseline, "flow")`
regenerates the isolated change when root supplies its new paired baseline.

MotionHistory flow mode detects Shi–Tomasi image corners and follows them with
pyramidal Lucas–Kanade in both directions. At least 12 tracks and 60% of detected
corners must pass both status checks, remain in bounds and return within one
analysis pixel. RANSAC homography requires 12 inliers, a 60% inlier ratio and
spatial support in both frames. The existing alignment/area/overlap checks still
validate the transform. There is no phase fallback after failed flow. Low
texture, missing intermediate frames, invalid transforms, cuts and generation
changes disconnect the path, including empty receipts. Exact equal textured
frames retain the existing stationary identity-transform optimization.

The fitted transform projects every quad vertex in its original coordinate
system and preserves vertex order. This is global image-corner tracking with a
camera transform; it does not independently track each text object or promise
to resolve parallax/nonrigid motion. No real-scene behavior is established.

For flow, MaskingEngine constructs the history with a projection horizon of
`floor(D * fps)` and also checks that horizon at receipt admission, including
injected motion adapters. Direct MotionHistory flow callers MUST supply
`max_projection_frames`; no unbounded flow fallback exists. The public
`arms.motion_for(options, fps)` adapts render_offline's existing explicit
`motion=` argument. No benchmark factory is monkeypatched.

Call `engine.submit(frame, now=..., generation=captured_ingest_generation)` for
each live flow frame. MotionWorker carries that captured token with its queued
pixels. Tokens are nonnegative integers, and global frame indices must keep
increasing across generation changes. Uninterrupted files use token zero.
No transport was edited: a future live adapter must relay its actual captured
generation; omitting that relay cannot establish protection against an invisible
reconnect with consecutive indices. New same-generation receipts can establish
coverage immediately at their own source frame without crossing the break.

## Separate D sweep, no adoption

Tracking stays at D1. Four additional policies keep phase motion:

| Arm | D seconds | A at 30 fps | Semantics changed |
| --- | ---: | ---: | --- |
| baseline / flow | 1 | 30 | flow changes only the tracking algorithm and its bounded-path contract |
| d2-fixed-a | 2 | 30 | delay only |
| d3-fixed-a | 3 | 30 | delay only |
| d2-derived-a | 2 | 60 | delay plus future-receipt eligibility |
| d3-derived-a | 3 | 90 | delay plus future-receipt eligibility |

Derived-A is `floor(D * fps)`, a semantic coupling of two options. Fixed-A
isolates extra presentation time but may add little hiding in the ideal offline
schedule because A and coverage maximum ages remain fixed. Derived-A expands
union eligibility; it can increase overmasking and does not extend maximum
coverage ages. After authorized execution, report natural hiding percentage-point
gain per added delay second against a paired D1 baseline, separately for these
families, along with all guards and actual sustained latency. No D>1 arm may be
adopted without the owner decision. None has been executed.

## Exact frozen-harness blockers (not edited)

- `bench/offline_quality.py:129` creates MotionHistory without a projection
  horizon. `flow.json` therefore fails before presentation. Necessary seam:
  pass the source-derived `floor(fps * delay)` to the existing motion factory,
  or expose its already-supported explicit motion argument to sealed rendering
  at `bench/quality_bundle.py:227`. This needs coordinator authority outside
  Lane C. Do not inject a fake mode or bypass source identity.
- `bench/offline_quality.py:117` restricts delay to [0,1]. Its CLI also checks
  that range at line 506. D2/D3 sealed quality needs an explicitly authorized
  experimental seam retaining all guards. Lane C leaves these restrictions.
- `bench/clocked_pipeline.py:734` restricts D to [0,1]. Its CLI accepts only
  phase/orb at line 888. Flow D1 can use its public `run(input, output,
  candidate, options)` interface with the flow policy. D2/D3 remain blocked in
  that interface too. No alternate renderer/scheduler removes those checks.
- Existing cost helpers have no known-ORT-userstream CUDA-event measurement.
  Sustained host and CPU receipts alone cannot satisfy the GPU-ms/source-frame
  requirement. Root must supply verifiable device profiling or instrumented
  same-stream CUDA events; metric remains UNVERIFIED until then.

## Execution plan, entirely unexecuted

`execution-plan.json` contains literal screen and sustained argv arrays plus
the complete tune-pair expansion list. Root owns all execution,
queue assignment and budget accounting. Inputs/performance derivatives and
judge cache still require root identity verification and provisioning. Never
submit this plan to an active queue or start a runner before root authorization.
The dedicated Mac mirror is `/Users/elannash/code/irl-shield-q2-temporal-26ca396c`.
`sync-mirror.sh` is the single unexecuted sync entry point; it excludes git,
builds, outputs, scratch, environments and caches and does not delete remote
files. It has not contacted the Mac. Root must provision existing authorized
model/fixture cache access in that mirror; no models were downloaded here.

After BOTH barriers and the harness seam decision, first screen a newly rendered
paired baseline and flow arm on the frozen tune Mazatlan natural/synthetic pair.
Reject a cheap counterexample; surviving that screen proves no all7 quality.
Then all seven tune clips / fourteen variants need full sealed scorecards under
the same final branch bytes, frozen tune manifest and judge-cache signature.
Never regrade historical a8 bundles using this helper/source fingerprint.
Historical baseline/B12 numbers are not the common baseline. Both giant streams
contain raw detector/union problems; tracking is not a rectangle-cap hypothesis.

Truth is independent Tesseract eng plus Vision accurate en-US. Output leakage
uses ALL THREE independent judges including PP-v5 English. Keep actual registry
family union, credit, real-video checks, natural hidden >=90%, synthetic
through-interval 100%, every clip protected <2%, and area ceiling <=.15 verified
with validate_area_ceiling and its basis receipt. Any guard failure is failure.
Do not use all-slate frames as evidence. The Mac judge remains the persistent
bench helper under the canonical SH/serialized Vision lock, never an EOF
single-frame fallback. No heldout-v2 assets were read or evaluated. Root alone
owns the exactly-once final v2 evaluation Sunday Nov 1 06 PT / 14 UTC.

For EACH surviving arm: root EX performance queue, readiness/other_busy-v2,
memory/load receipts, no overlap with phone/root NVENC. Use 1920x1080 at 30 fps,
10 s warmup, >=30 s steady trials while actual NVENC is active, and median of
>=5 cost repetitions. Retain sustained fps and p95 added latency. Device events
must bracket real detector work on its known ORT user stream, with source-frame
denominator and lane call counts. State H2D/D2H inclusion, async copies, waits,
pre/postprocessing and CPU motion/render separately. Device kernels/copies on
other streams must be joined or verifiably profiled. Sum parallel lane event
service costs as work, not elapsed critical-path latency. CPU motion and render
need separate CPU/wall scopes; host-wall time is never labeled GPU time.
No q-run SH lease establishes performance. Missing device timing blocks promotion.

## CPU receipts and limitations

See `bench/LOG-q2-temporal.md`, `out/q2-temporal/10-final-green.log`,
`10-tests.json`, and the exact runnable command copies in that directory.
Final focused run: 28 tests, zero errors/failures/skips, OpenCV one CPU thread.
Synthetic public interfaces exercised real flow/shear projection, inverse
projection, empty-receipt connectivity, occlusion/low texture/gaps, generation
closure/recovery through asynchronous engine submission, D horizon admission,
late motion and legacy phase/reference behavior. No OCR, models or video codecs
were invoked by this focused selection.

Test ownership: MotionHistory tests own geometric mapping and connected paths;
they cannot prove detector recall or live decode behavior. Engine tests own
receipt admission, protection and generation forwarding through MotionWorker;
they cannot prove an untouched ingest adapter relays real generation tokens.
Existing motion-worker tests own asynchronous deadline enforcement. Each new
test uses an established public interface and extends the existing test files;
no test-only production hook exists. The synthetic backward-consistency witness
was found with a bounded original-image occlusion/translation fixture sweep,
not a real-scene screen. No new font, footage, model, dependency or service was
introduced; OpenCV Apache-2.0 and NumPy BSD-3-Clause licenses are already recorded.

Physical guard proof: `09-mutation.diff` records five applied mutations; the
six selected tests fail five times for actual projection/LIVE/union violations.
`09-restoration.json` confirms byte-for-byte restoration, followed by final green.
`08-fb-fixture.log` independently exercises the backward-error-only mutation on
the original synthetic scenes. Initial unsupported-interface red runs and one
incorrect test expectation are retained, not represented as production defects.

Full `scripts/check` was not run: it discovers encoded-video/quality-bundle and
heldout harness tests (`tests/test_quality_bundle.py`, `tests/test_heldout_bench.py`)
that perform rendering and fixture creation, outside this readiness-only barrier.
No missing service was encountered in the focused CPU run. The full gate and
Mac native build remain unverified. Baseline preservation is supported by source
review and synthetic regression tests, not a new real-video pixel equivalence
proof. Pipeline fingerprint changes, so a same-final-source paired baseline is
mandatory even with default phase behavior preserved.

All owned test subprocesses exited; MotionWorker tests close their workers and
assert stopped state. No persistent process or Mac mirror was started. Patch,
post-application hashes, artifact inventory and source identity are in
`.tmp/q2-temporal/handback.json`; root applies the patch, not another writer's tree.

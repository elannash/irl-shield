# Q2 precision: code ready, measurement HELD

Base `65891cb0b515bc0c34ec4ded89aa6a3228992cc2`, assigned branch
`t3/q2-mask-precision`. No commit, staging, push, PR, child delegation, model
change, Mac command, shared queue operation, fixture write or real-scene read.
See `bench/LOG-q2-precision.md` and `out/q2-precision/` for local CPU receipts.

Neither `PHONE_TEST_DONE/GPU_RELEASED` nor the exact root-relayed
`V2_FROZEN manifestSHA` has arrived. All arm results, tune screens, corpus
renders, OCR, GPU work and performance measurements remain HELD. This lane
never evaluates fresh-heldout-v2. Root owns its single final frozen-policy
evaluation on Sunday 2026-11-01 14:00Z. Spent v1 was not used.

## What the source and historical audit establish

`shield/render.py` already fills convex quads with mitered offsets, padding
normal to each edge, scaled by the shorter opposite-edge mean, with a 3px
floor. `shield/masking.py` is a separate historical box renderer and is
unchanged. This is not a rectangle conversion or a detection filter.

The read-only audit is
`/home/elan/.t3/worktrees/irl-shield/t3-4fb60399/docs/Q-GIANT-AUDIT.md`.
Its sections “Exact historical diagnosis” and “Unclip” establish that actual
raw detector giants and accumulated projected smaller quads both matter.
Both original giant streams remain raw. Padding cannot repair oversized bare
quads or an oversized bare union. The earlier cap/confirmation ideas remain
rejected; this adapter introduces neither one.

Historical inputs/policies/plan were read at
`/home/elan/code/irl-shield/.tmp/q/frozen-a8a06e3/`. The plan points to
`/home/elan/code/irl-shield/out/q-base-a8a06e3-cache3-v3/`; it does not point
to `out/frozen`. Metadata hashes are in
`out/q2-precision/historical-metadata.json`. No historical bundle was replayed
or regraded with these new helper bytes. Historical quality numbers and B12
are not the common baseline for these arms.

## One lever per arm

| File | Single change from baseline | Harness readiness |
| --- | --- | --- |
| `baseline.json` | New source, ordinary padding `.30` | Existing quality CLI |
| `padding-020.json` | `options.padding=.20` | Existing quality CLI |
| `padding-010.json` | `options.padding=.10` | Existing quality CLI |
| `padding-000.json` | `options.padding=0` | Existing quality CLI; retains 3px floor |
| `union-015.json` | Enable padding-union budget `.15` | Public renderer ready; sealed harness injection missing |

The four ordinary policy files preserve all other historical baseline options,
including actual Tiny/Small identities, scheduling, motion, CUDA providers,
NVENC, independent judges, and `.15` area ceiling with its existing basis.
No detector family override exists. `union-015.json` is an adapter declaration,
not a quality CLI policy; passing it as a policy must not be represented as
an evaluated cap arm.

`Renderer` adds only a keyword-only `padding_floor=3` argument. Its default
expression is unchanged in meaning and all ordinary call sites are untouched.
The new `PaddingBudgetRenderer(max_mask_fraction=.15)` is passed at the existing
`MaskingEngine(..., renderer=...)` or `render_offline(..., renderer=...)` seam.
It retains ordinary rendering when the full union fits. Otherwise it measures
the bare raster union, then tests twelve common padding scales between zero
and one. Both `.3 * shorter_edge` and the 3px floor scale together. This is a
bounded feasible search, not a claim of the exact maximal raster scale.

Every trial is ORed with the bare raster mask to cover fixed-point edge
rounding. All raw quad pixels remain black. The cap counts the union, not
the sum of quad areas, and includes clipped raster edges. A bare union that
exceeds the limit is returned unchanged, with `budget.satisfied=False` and
its actual pixel counts. This is an unsatisfied experimental budget, never a
quality pass. The established scorer/guards still decide quality. The cap
does not relabel output PROTECT, select detections, trim quad support, change
clues, or solve raw-union failures. PROTECT/HOLD retain their original behavior.
The adapter has no badge; baseline badge remains false.

Up to fourteen complete CPU renders can be needed per capped LIVE frame.
That cost is unmeasured and may disqualify the prototype. This is a conservative
first adapter, not a realtime claim. No new dependency/model/license is added;
existing NumPy BSD-3-Clause and OpenCV Apache-2.0 notices apply.

## Test contracts and limits

The owning seam is `render(frame, quads, state, clues)` and its returned actual
pixels/mask. Existing render tests are extended for removable floor and
height-based padding. New masking tests protect union accounting, overlapping
duplicate quads, no-trim over-budget failures, full-frame raw geometry, rotated,
skewed and clipped containment, owned output, invalid input and protection.
These catch disabled budgets and dropped quads without an internal spy or
test-only export. They do not establish OCR hiding, natural truth, actual
positive-control coverage, real video, scheduling performance or throughput.

The historical thirteen positive controls, including full-frame house 11,
remain mandatory after release. They were not decoded or replayed here.
Synthetic full-frame and quad containment establish preservation of the supplied
bare geometry, not that the detector's bare quads enclose all real source ink.
Each real positive must still retain all known ink under the new padding arm;
any loss rejects it. No positivity claim transfers from the old audit.

Physical disabled-cap and dropped-quad mutations produced assertion failures;
the adapter was restored byte for byte. The initial feature red runs were
missing-option/missing-module errors and are not counted as behavioral guard
proof. `09-final-cpu.log` is the restored green affected suite and default
equivalence check. It compares actual output bytes to the base renderer on
synthetic frames only. The final gate result is recorded in the lane log.

## Deferred screen and performance plan

`prepared-argv.json` contains unexecuted literal argument arrays, not a launcher.
Root must supply both barrier messages and the active exclusive performance
queue before any dependent run. It must apply this patch, verify source identity,
then render a new same-branch baseline on the exact frozen tune input manifest
SHA `4db58cb96244791874447951b893af48f99b6bd165a59c46884a40a3c5226972`
and the same judge/cache signature. Source fingerprint checks stay enabled.
The added renderer module changes the fingerprint even when not selected.
Synthetic equality does not authorize bypassing a fingerprint guard.

Cheap screens cover only Mazatlan natural/synthetic counterexamples, paired
against the new baseline. They cannot establish all7 quality. Retain every
failure. Candidates surviving cheap screens require all seven tune clips and
all fourteen variants, sealed masks/movies/detection and engine receipts, then
the full independent scorecard. Input truth remains Tesseract eng + Vision
accurate en-US and all three output leak judges include PP-v5 English. Targets
remain natural >=90%, synthetic through-interval 100%, real-video guard,
backed ceiling <=.15 validated by `validate_area_ceiling`, and protection <2%
on every clip. A failed guard is a failed arm. No policy is frozen here.

Use the one `sync-mirror.sh` script only after authority to resume Mac work;
it excludes git/build/output/temp/venv/cache trees and writes only
`/Users/elannash/code/irl-shield-q2-precision-5e31c93b`.
Grade with the existing persistent helper under serialized SH host leases,
using exactly
`/Users/elannash/code/irl-shield-integration-run/.tmp/integration/venv/bin/python`.
No single-frame EOF fallback. The Linux interpreter is exactly
`/home/elan/.t3/worktrees/irl-shield/t3-7cba93a7/.tmp/integration/venv/bin/python`.
No interpreter symlink resolution or package overlay is used.

For every arm, root must run separate exclusive perf-queue trials after phone
release, retaining readiness, START/END/periodic `other-busy-v2`, memory/load,
device/provider/model/source hashes, active NVENC, 30fps source accounting,
10s warmup then >=30s steady output, sustained fps and p95 added latency.
Use >=5 repetitions for cost summaries; report their median. Time startup
separately. Shared q-run leases are untimed and never establish this result.

Actual GPU time per source frame is still blocked. `onnx_detectors.py` has
neither a controlled `user_compute_stream` nor device-event instrumentation,
and `nsys` is not installed in PATH. The prepared clocked argv reports host/
pipeline throughput and latency only. It is not a GPU timing command. The
profiling argv is a blocked template for an already-authorized, available device
profiler; no installation is proposed. Without verifiable device receipts or
CUDA events on the actual ORT stream, GPU time is unavailable and no arm may
be promoted. GPU kernels and H2D/D2H activity need their own inclusion report;
do not sum overlapped kernels and call it elapsed time. Record per-lane events
and counts plus aggregate device-active interval union normalized by source
frames. Host resize/pre/postprocessing, CPU operator fallback, phase motion,
projection, cap search, copy/wait and encoder drain need separately labeled
CPU/wall receipts. NVENC overlap and source emission remain concurrent.

Necessary fenced seams, not edited: `quality_bundle.render` must pass a selected,
fingerprinted renderer to `render_offline` and retain budget receipts; the
clocked adapter must inject the same renderer instead of constructing only the
ordinary Renderer. Detector instrumentation or an existing device profiler is
needed for real GPU timing. Any changed helper bytes require another paired
same-branch baseline. No source/signature/cache guard is relaxed.

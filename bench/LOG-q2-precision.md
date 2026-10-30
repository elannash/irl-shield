# Q2 precision lane log

**ISSUES: CPU code ready; measurement HELD.**

Base `65891cb0b515bc0c34ec4ded89aa6a3228992cc2`, initially clean, branch
`t3/q2-mask-precision`, path
`/home/elan/.t3/worktrees/irl-shield/t3-5e31c93b`. App branch/HEAD retained;
worktree locked for coordinator application. No staging, commits, pushes or PRs.

Task:
<t3-thread://v2/a3857748-9579-4ce2-b37e-5d3cd3faad44/thread:delegated-task:command%3Amcp%3A4604c41b-99c6-432d-bed9-120571e9de69%3Adelegate-task%3Aa97fa9fb-f02e-4e0f-8207-19156058d9e6>

Read required skills: codebase-design, tdd, test-review/references/gate.md,
diagnosing-bugs Source/hypothesis checks, research Measurements/metered calls,
receipt-audit. Read actual render/masking code and adjacent tests, architecture,
harness/registry/fingerprint/ORT source and CPU gate. No glossary/ADR file found.
No delegation, provider/model/effort change. Roles and Mac shell traps read for
applicable scope. No Mac command executed.

## Implementation and evidence limits

The existing renderer fills convex quads with mitered offsets, shorter-edge-mean
proportional padding and 3px floor. shield/masking.py is a separate historical
box renderer; untouched. The new keyword-only Renderer padding_floor=3 retains
ordinary defaults. The optional PaddingBudgetRenderer measures actual clipped
raster union and reduces only a common padding scale, including the floor.
Every candidate unions back the bare raster mask. Over-budget bare geometry
is returned intact with budget.satisfied=False; no quad selection, ink trimming,
PROTECT relabeling or guard change. PROTECT/HOLD bypass the budget. At most
fourteen CPU renders per frame; this cost is unverified.

Fixed-padding configs change only options.padding from .3 to .2/.1/0 and retain
the 3px floor. union-015.json describes the separate opt-in adapter, not a
CLI-ready quality policy. All original scheduling/model/identity/guard options
remain. No model/dependency/license introduced; existing NumPy BSD-3-Clause and
OpenCV Apache-2.0 apply.

Historical evidence read only: frozen-a8a06e3 inputs/policies/plan and the giant
audit report plus out/giant-audit JSON metadata in t3-4fb60399. The plan points
to /home/elan/code/irl-shield/out/q-base-a8a06e3-cache3-v3/. No out/frozen path
assumed. Historical exact replay metadata records zero mismatches for both
streams; the report establishes detector-origin giants plus accumulated
smaller receipts. Padding cannot repair a bare-union floor over the bound.
No historical replay/regrade or new scene measurement occurred. Historical
baseline/B12 numbers are not this lane's common baseline.

The actual thirteen positive controls, especially full-frame house 11, are
mandatory after release. They were not replayed here. Synthetic full-frame
and rotated/skewed/clipped containment do not establish real-source ink coverage
or OCR hiding. The adapter cannot claim those positives survive until screened.

## Red/green and tested seams

Tests cross public Renderer.render, PaddingBudgetRenderer.render and existing
engine/deadline interfaces, observing actual pixels/masks. They protect shorter
edge scaling, removable floor, union rather than sum/per-quad budgets, duplicate
overlap, no-trim impossible budgets, rotated/skewed/clipped containment, owned
outputs, protection and invalid input. No test-only export/internal spy added.
They do not establish real-scene quality, OCR, timing or throughput.

01/03 are missing-feature reds (keyword/module); those alone are not physical
guard proof. Mutation 07 set the budget to the whole frame: the test failed on
1419 masked pixels >1200, plus false satisfied status on raw over-budget quads.
Mutation 08 erased over-budget bare quads: false satisfied status failed.
Diffs retained at out/q2-precision/07-cap-mutation.diff and 08-drop-mutation.diff.
Both restored byte for byte. 09 then passed 23 affected tests and 96 synthetic
default byte-equivalence comparisons to the exact base renderer. This is not
permission to reuse historical fingerprint identities. New same-branch baseline
required, with unchanged source/signature/cache guards.

Full CPU gate 10 was attempted once with the exact prescribed SDK and CUDA
hidden. It generated temporary synthetic movies with stub detectors/judges and
tested temporary queues. It performed no real model inference or corpus screen.
The supervisor hit 240s, terminated/reaped its process group, and produced no
final gate verdict. Its partial log contains FAIL for the existing
PerformanceQueue.test_forced_jobs_receive_queue_context_and_hard_deadline_stops_only_owned_group.
No traceback was printed before timeout. Targeted unchanged rerun 12 passed in
5.103s; the cause is unresolved and the full gate remains incomplete. No queue
fix was made outside the fence. Gate imports passed on provisioned Python3.11;
no missing service/credential was reported before interruption. Mac/Swift unrun.

## Invocation ledger

**12/20 used, 8 reserved.** Every failed/red/rerun check is counted. Zero
benchmark, real-scene render, grade, profile or GPU invocations. The full gate's
temporary synthetic movie tests are unit tests, not new arm renders/metrics.
Read-only/setup retrievals, packaging/hash checks and one corrected worktree-lock
usage error are separate in out/q2-precision/retrieval.log.

Commands below used .tmp/q2-precision/run_cpu.py: nice10, OMP/OpenBLAS/MKL=2,
OpenCV=1, CUDA_VISIBLE_DEVICES empty, PYTHONPATH removed. Tests used exactly
/home/elan/.t3/worktrees/irl-shield/t3-7cba93a7/.tmp/integration/venv/bin/python;
no symlink resolution or package overlay. The system Python supervisor did not
run project tests itself. Per-command logs and receipt JSON contain argv/cwd,
start/end/PID/exit. Invocation 10 timeout receipt was reconstructed from the
supervisor's TimeoutExpired and verified process exit; no gate success claimed.

01. `01-floor-red`: exit 1; `out/q2-precision/01-floor-red.log`

```text
/home/elan/.t3/worktrees/irl-shield/t3-7cba93a7/.tmp/integration/venv/bin/python -B -m unittest discover -s tests -p test_render.py -v
```

02. `02-floor-green`: exit 0; `out/q2-precision/02-floor-green.log`

```text
/home/elan/.t3/worktrees/irl-shield/t3-7cba93a7/.tmp/integration/venv/bin/python -B -m unittest discover -s tests -p test_render.py -v
```

03. `03-union-red`: exit 1; `out/q2-precision/03-union-red.log`

```text
/home/elan/.t3/worktrees/irl-shield/t3-7cba93a7/.tmp/integration/venv/bin/python -B -m unittest discover -s tests -p test_mask_precision.py -v
```

04. `04-union-green`: exit 0; `out/q2-precision/04-union-green.log`

```text
/home/elan/.t3/worktrees/irl-shield/t3-7cba93a7/.tmp/integration/venv/bin/python -B -m unittest discover -s tests -p test_mask_precision.py -v
```

05. `05-synthetic-geometry`: exit 0; `out/q2-precision/05-synthetic-geometry.log`

```text
/home/elan/.t3/worktrees/irl-shield/t3-7cba93a7/.tmp/integration/venv/bin/python -B -m unittest discover -s tests -p 'test_*render*.py' -v
```

06. `06-budget-guards`: exit 0; `out/q2-precision/06-budget-guards.log`

```text
/home/elan/.t3/worktrees/irl-shield/t3-7cba93a7/.tmp/integration/venv/bin/python -B -m unittest discover -s tests -p test_mask_precision.py -v
```

07. `07-cap-disabled-red`: exit 1; `out/q2-precision/07-cap-disabled-red.log`

```text
/home/elan/.t3/worktrees/irl-shield/t3-7cba93a7/.tmp/integration/venv/bin/python -B -m unittest discover -s tests -p test_mask_precision.py -v
```

08. `08-drop-overbudget-red`: exit 1; `out/q2-precision/08-drop-overbudget-red.log`

```text
/home/elan/.t3/worktrees/irl-shield/t3-7cba93a7/.tmp/integration/venv/bin/python -B -m unittest discover -s tests -p test_mask_precision.py -v
```

09. `09-final-cpu`: exit 0; `out/q2-precision/09-final-cpu.log`

```text
/home/elan/.t3/worktrees/irl-shield/t3-7cba93a7/.tmp/integration/venv/bin/python -B .tmp/q2-precision/final_cpu.py
```

10. `10-full-cpu-gate`: exit 1; `out/q2-precision/10-full-cpu-gate.log`

```text
env SHIELD_PYTHON=/home/elan/.t3/worktrees/irl-shield/t3-7cba93a7/.tmp/integration/venv/bin/python SHIELD_GATE_RECEIPT=out/q2-precision/full-gate.json bash scripts/check
```

11. `11-artifact-validation`: exit 0; `out/q2-precision/11-artifact-validation.log`

```text
/home/elan/.t3/worktrees/irl-shield/t3-7cba93a7/.tmp/integration/venv/bin/python -B .tmp/q2-precision/check_artifacts.py
```

12. `12-queue-failure-triage`: exit 0; `out/q2-precision/12-queue-failure-triage.log`

```text
/home/elan/.t3/worktrees/irl-shield/t3-7cba93a7/.tmp/integration/venv/bin/python -B -m unittest discover -s tests -p test_perf_queue.py -k forced_jobs -v
```

## HELD work and exact blockers

- Neither PHONE_TEST_DONE/GPU_RELEASED nor the exact root-relayed V2_FROZEN
  manifestSHA arrived. No screen/arm metric can start. Fresh-heldout-v2 was
  never touched; root owns its single final frozen-policy Sunday Nov1 14UTC
  evaluation. Spent v1 unused.
- Existing fixed-padding configs fit the options.padding seam. For union-015,
  quality_bundle.render omits render_offline(renderer=...), and the clocked
  adapter constructs ordinary Renderer. Needed seam: select/fingerprint the
  opt-in renderer and retain budget receipts. No fenced file was edited or
  monkeypatched. No silent default-render cap result is provided.
- GPU time/source frame unavailable: actual ORT factory exposes no known
  user_compute_stream/device-event instrumentation, and command -v nsys found
  none. Host/pipeline/CPU-cost clocks are not GPU time. No promotion without
  verifiable device timings while NVENC runs at source30fps.
- Full CPU gate incomplete, with one unreproduced test failure (above).
- Actual positives, cheap Mazatlan counterexamples, all7 tune/14 variants,
  sealed scorecard and all performance trials unrun. No measured best guardpass,
  closest nearmiss, winner, source-frame GPU cost or quality improvement exists.

README and prepared-argv.json document exact unexecuted quality/clocked/cost
argv and required receipts. The device-profiler argv is a blocked template;
union timing argv is null until its harness seam exists. Ordinary cost argv
requests >=5 repetitions; paced argv requests10s warmup +30s steady,30fps,NVENC.
Root must supply its active exclusive perf queue and existing libraries/caches;
this lane did not query/start/submit to it. Readiness, other-busy-v2, memory/load,
START/END/periodic health, device/provider/source/model hashes, fps/p95 and actual
CUDA kernel/copy receipts are required. Every quality guard/truth/judge remains.

sync-mirror.sh syntax checked but never executed; source-only sync targets
/Users/elannash/code/irl-shield-q2-precision-5e31c93b and excludes git/build/out/
tmp/venv/cache. Mac uses exactly the integration-run SDK, persistent Vision helper
and serialized SH leases. No EOF fallback. Shared q-run remains untimed.

Delivery: .tmp/q2-precision/implementation.patch; out/q2-precision/postapply.sha256;
out/q2-precision/handback.json; CPU/mutation/retrieval/process logs. Final handback
lists exact files/postSHA256 and patch/artifact hashes. Generated source files
stay intentionally untracked for Opus application. Process receipt confirms
owned subprocesses exited. Worktree lock retained for review; HEAD unchanged.

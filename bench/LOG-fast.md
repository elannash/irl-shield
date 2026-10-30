# FAST implementation and measurement ledger

## 2026-10-29 — implementation lane start

Requested and actual branch: `elannash/m1-fast` (renamed in place from
`t3/onnxtr-fast-detector`). Verified clean base HEAD before edits:
`2dd52a610eb569ac51eedc84b7840fa852da96c9`. Task start receipt:
2026-10-29 23:51:13 UTC; hard stop 2026-10-30 02:51:13 UTC.
All changes remain uncommitted. No push, PR, merge, Twitch or external inference.

Loaded `codebase-design` and `tdd`; read the test gate, required routing and
shell sections, architecture, detector/portability/leak docs and source ledger.
The seam is existing `detect_quads(uint8 BGR) -> pixel quads`; quality uses
`offline_quality.run_file(backends=...)`. Common factory, engine, render,
scorer, scheduling and transport sources remain untouched.

## Provenance

FAST Tiny: OnnxTR 0.9.0, upstream source commit
`06fd099fd48510f4202d1fb43db5ed23d5f61c80`, Apache-2.0. Weight source is
Felix92/onnxtr-fast-tiny revision
`f694deb1e32bddfd96d33be5e1e7b804564594ab`; the pinned model card explicitly
labels the weights Apache-2.0. Verified local weight bytes: 34,110,202,
SHA-256 `2886777913e837ea3a5ab79f7fb9fd5db5897fc6560f21d16a4f54c64fc0b357`.
Model card SHA-256:
`699ba52493a824258ad58e2c05aead19c7c8ec9dc48c852cd0bd894035a06aad`.
Configuration SHA-256:
`fc4c6885d04e108e7b3c25fea5f0daed9bc10edd951252d9df26a06e0c8eaf72`.
OnnxTR wheel SHA-256:
`bb8a47af8253e51c81950519d30e499373830cc20a27552c41a0b888f9171a05`.
Exact URLs are in the FAST-only manifest entry and `bench/fast-licenses.json`.
No dataset or demo asset is introduced. All planned output remains
benchmark-only, contains no audio, and may include third-party signage.

## Synthetic checks before readiness

`nice -n 10 .tmp/fast/.venv/bin/python -m unittest bench.fast_test -v`:
4 tests passed. The no-op detector first failed the geometry assertion;
`.tmp/fast/test-red-adapter.log` and `.tmp/fast/test-green-adapter.log` retain
red/green. A deliberate protected-credit mutation failed `2 != 1`, production
was restored byte-for-byte, and the suite returned green; raw logs:
`.tmp/fast/test-red-protected-mutation.log`, `.tmp/fast/test-green-restored.log`.
Latest checks also reject failed fidelity guards. Unit tests protect BGR/RGB,
rotated polygon/confidence separation, closed adapter, absent requested EP,
source-schedule replay/scaling, union, and full-interval complementarity.
They do not establish real model recall or performance.

`python3 -m compileall -q bench/fast*.py` and
`bash -n bench/fast-host bench/fast-setup`: passed.

The new synthetic ONNX integration test exercises actual OnnxTR preprocessing,
postprocessing and CPU EP with a small generated graph. It awaits the isolated
package environment; no pretrained inference is needed for that test.

## Root priority and pending measurements

Both `/tmp/agents/irl-shield/m1-20261029-ready.json` markers were absent at
initial checks. `bench/fast-host shared true` stopped at its readiness gate:
`jq: error: Could not open file .../m1-20261029-ready.json: No such file or directory`.
No lane package install, timed inference or video-quality run has started.
The dedicated Mac mirror is `~/code/irl-shield-fast`; no root checkout/env/cache
was mutated. All lane generated data belongs in `.tmp/fast`, own `out/`, or
`/tmp/agents/irl-shield/fast/`.

Pending: isolated installs/license inventories, synthetic ONNX test, full gate,
all7 tune scorecards for FAST alone and best-v6+FAST, guarded per-interval
complementarity, and independent >=30s post-warmup detector cost for CoreML,
CUDA and CPU. No quality or speed result is claimed yet.

The read-only initial v6 small baseline advertises 393/435 natural hidden,
46/52 synthetic hidden and 8.190476% protected, with real-video/protection guards
failed. These are old raw figures, not accepted quality or performance. The
comparison driver rescores retained evidence with the current scorer and does
not use box recall or protection as recovered-interval credit.

### Host-lock/barrier clarification

All load-heavy setup (pip, model derivation/download, media preparation and
quality) must use the same SHARED host lease after `complete:true`; timing uses
EXCLUSIVE. Root may retain EX for additional comparisons after publishing its
first complete receipt. The launchers recheck the marker after obtaining the
lease, preventing a queued command from using a marker corrected while it
waited. A synthetic regression verifies `complete:true,valid:false` permits
work, then a correction to `complete:false` rejects it. Five lightweight tests
now pass. Linux's corrected false marker was observed; no Linux install or
measurement had started under its brief earlier true marker.

### 2026-10-30 00:19Z — Linux isolated setup completed

Corrected root readiness observed `complete:true`, 900 steady / 1200 encoded,
root receipt SHA-256
`5f159ae501f2c407de74b33d3b6f676506d22296259f403cb0037ea7d99db24e`.
The root's receipt remains invalid; it is only the setup barrier release.

Ran `bench/fast-linux shared bench/fast-setup`; exit 0. It waited on root EX,
then held SH during the entire pip install. Setup unit
`run-p2163827-i6354935.scope` finished and is inactive. Own venv:
`.tmp/fast/.venv` (Python 3.11.14). OnnxTR 0.9.0, ORT GPU 1.20.2, ONNX 1.23.2,
NumPy 2.2.6, OpenCV 4.11.0.86, SciPy 1.16.3 and the existing pinned CUDA
12.4/cuDNN 9.3 packages installed; exact full versions: `.tmp/fast/freeze.txt`.
New transitive pins filelock 4.2.4 (MIT), fsspec 2026.9.0 (BSD-3-Clause),
hf-xet 1.7.1 (Apache-2.0) are recorded in FAST-only requirements/licenses.
No CPU ORT was installed alongside GPU ORT.

Raw receipts: `.tmp/fast/setup-linux.log`, `.tmp/fast/install-report.json`,
`.tmp/fast/license-inventory.json` (49 distributions with notice hashes),
`.tmp/fast/setup-health-start.log`, `.tmp/fast/setup-health-end.log`.
Setup health showed elevated PSI/load, so it is diagnostic setup evidence,
not an accepted performance receipt. No pretrained inference or timing started.
Mac marker still absent. Synthetic integration command is queued under SH.

### 2026-10-30 00:27Z — first inference-cost receipts

Identical Mac v6-small natural input copied under SH to
`out/fast-runtime-source.mp4`; SHA-256
`85cfbe902c06e902ec86116b005a7d54e19ab728f0b660fed9b45f9c479195d7`.
Both runs used EX, batch1 static 1024-square, threads2, three warmup calls,
and >=30 steady seconds. Costs include OnnxTR preprocessing and postprocessing.
They are detector calls, not a source/output fps claim.

- CUDA first run: 405 calls / 30.008830s; p50 72.242ms, p95 87.971ms;
  1.012863 CPU cores; startup 1.795246s. Profile: 48 CUDA events, no CPU
  provider events. Memory normal start/end, but startup load 8.41748 / 8 CPUs
  exceeds the load threshold. **Contended diagnostic, invalid performance.**
  Raw `out/fast-runtime-cuda-1024/runtime.json`, sibling ORT profile and
  `perf-health.json`; log `.tmp/fast/runtime-cuda-1024.log`.
- CPU: 34 calls / 30.431751s; p50 878.187ms, p95 988.005ms;
  1.960591 CPU cores; startup 1.204467s. Profile: 28 CPU events.
  Normal health/load at both boundaries; **valid detector-cost receipt**.
  Raw `out/fast-runtime-cpu-1024/runtime.json`, sibling ORT profile and
  `perf-health.json`; log `.tmp/fast/runtime-cpu-1024.log`.
- CUDA repeat `out/fast-runtime-cuda-1024-quiet` rejected before inference:
  memory PSI full avg10=.12% => warn. Exact rejection and raw health are in
  `.tmp/fast/runtime-cuda-1024-quiet.log` and sibling `rejected-health.json`.
  No timing number exists for that rejected attempt.

The synthetic real-OnnxTR + replay suite passed 7 tests in the lane environment;
`.tmp/fast/integration-linux.log`. `pip check` found no broken requirements.
The cache preparation verified local FAST weights and read-only symlinks to
root's PP-OCR judge files; `.tmp/fast/cache-linux.log`.

Conductor's Mazatlan finding is a detector false-box issue, not solely motion:
`/tmp/agents/irl-shield/m1-mask-inspection/probability-probe.json` shows Tiny's
95.3% and Small's 99.8% frame coverage at frame45. This lane does not alter PP
or suppress large geometry. FAST-alone's geometry/fidelity remains to be
measured. Complementarity uses raw leaked=true tracks; a separate field reports
raw-hidden intervals whose quality credit was zeroed by a failed baseline guard.

### 2026-10-30 00:35Z — Mazatlan raw geometry diagnostic

Exact conductor-named source copied under SH:
`out/fast-mazatlan-source.mp4`, SHA-256
`5bf016285a12457e0554e29f8764e6a94780821fea8ffee63162bdd5e2fa5a28`.
Untimed CUDA probe used FAST Tiny default .1/.1 and canonical Renderer padding.3
on every frame34–60 at static640 and1024. Frame45 source SHA-256
`71d1a880a19b9bca05ae8be9e37336a52838099a5f5591aad3aaed280c914e58`.
Opened frame45 source and rendered output: feet/pavement, no FAST mask.
Benchmark-only: shoe marks may remain visible; never a demo-ready asset.

- 640: 27/27 frames empty; padded raster area max0%.
- 1024: 2/27 frames nonempty; padded raster area max0.0694444%; raw largest
  quad area max0.0137329%; frame45 empty at both sizes.
- Start/end memory pressure **critical**. This is rejected for accepted
  quality/performance, retained solely as an explicitly labeled raw detector
  diagnostic; it is not an OCR recall score or whole-pipeline guard result.

Raw `out/fast-mazatlan-probe-diagnostic/probe.json` includes model, provider,
static artifact and frame hashes/quads; sibling `health.json` and PNGs retain
pressure and visible proof. Harness `.tmp/fast/probe_mazatlan.py`; command:
`bench/fast-linux shared env PYTHONPATH="$PWD" .tmp/fast/.venv/bin/python .tmp/fast/probe_mazatlan.py out/fast-mazatlan-source.mp4 out/fast-mazatlan-probe-diagnostic --diagnostic`.
An earlier strict attempt rejected before model load;
`out/fast-mazatlan-probe/rejected-health.json` and `.tmp/fast/mazatlan-probe.log`.
All processes from these probes exited. No PP code or geometry was suppressed.

### 2026-10-30 00:46Z — healthy CUDA and source snapshots

A fresh EX run at `out/fast-runtime-cuda-1024-quiet2/runtime.json` passed:
402 calls / 30.002391s, p50 72.651ms, p95 91.030ms, CPU1.014556 cores,
startup1.921643s, 48 profiled CUDA events. Normal memory PSI at both boundaries;
load4.88037 ->4.00830 on8 logical CPUs. This is an accepted **detector-cost**
receipt; it establishes no stream output fps.

CUDA640: 755 calls / 30.031001s, p50 38.575ms, p95 48.491ms,
CPU1.024160 cores. Start normal/end warn; **invalid, diagnostic only**.
Raw `out/fast-runtime-cuda-640/runtime.json`; log `.tmp/fast/runtime-cuda-640.log`.
CPU640 then rejected at preflight; `.tmp/fast/runtime-cpu-640.log` and sibling
`out/fast-runtime-cpu-640/rejected-health.json`. No timing exists for that attempt.

Cost receipt code snapshots are saved under `out/fast-source/`:
- `8e50eca8882495e6acdcef665505693cd8b1a47ed8c2685e275faee2f2c48d3c`
  (first diagnostic CUDA; reconstructed prior reporting-only change, then its
  exact fingerprint verified against that receipt).
- `9d9d359f0a525de3515f8a28922a5046bf7943dd110e7cd00829f20934c26ad5`
  (valid CPU1024).
- `cbbf0529aeeb97c174973b69501e3ea349b2d4553691c369b77213261802ac23`
  (valid CUDA1024; current quality code also freezes/checks its borrowed
  reference scorecard before/after evaluation).
Each folder has a byte hash manifest and a sibling `.tar.gz`. Changes between
these snapshots only added quality-report/provenance fields, not detector,
weights, static derivation, runtime or benchmark cost logic.

Installed OnnxTR wheel SHA was checked against the manifest and matched.
The lane's 1.7GB completed pip HTTP cache was deleted under SH after all setup
processes exited; install report, license hashes, built langdetect wheel,
installed environment and all measurement artifacts remain. No root cache changed.

### Fresh setup bootstrap check

A minimal scratch fixture with no `.tmp/fast/.venv` reproduced the Linux
launcher's bootstrap error: `line11: .tmp/fast/.venv/bin/python: No such file or directory`.
The launcher now uses `FAST_PYTHON` or an existing private interpreter, falling
back to `python3.11`, to check readiness and enter the lease. Setup can then
create its private environment. The same scratch invocation subsequently
created `ran.txt` containing `bootstrap reached command`, with no environment
preinstalled; this proves the requested command actually ran. Raw red/green:
`.tmp/fast/bootstrap-red.log`, `.tmp/fast/bootstrap-green.log` and
`.tmp/fast/bootstrap-fixture/ran.txt`. No global environment changed.

The Mac launcher records its own PID/PGID in `.tmp/fast/command.pid` and creates
an isolated process group, so an over-time owned job can be stopped remotely
without touching another session. A lightweight local exec proof exited and
left matching PID/PGID. All owned jobs remain stopped between operations.

### Conductor queue plan supersedes manual timing

New binding conductor instruction: `scripts/perf-queue` detached per-host runner,
root sustained priority1 and lane timing priority2; >=80% CPU idle for10s plus
Mac normal pressure/Linux>=4GiB available, checks120s, EX canonical lock. No NEW
manual timed runs. Original task deadline remains 02:51:13Z. Untimed work uses
SH and no long untimed work begins once timed jobs are queued on that host.
Queued jobs may finish overnight under root; no other-session process is touched.
No lane timed job was active when this instruction arrived.

Prepared direct argv/cwd/unique `{attempt}` receipts in
`out/fast-queue/jobs.json`. No queued argv calls `fast-host`, `fast-linux` or
host-lock; the runner owns EX. CPU/CUDA1024 already have valid receipts.
Remaining timing definitions: Linux CUDA640 and CPU640 (setup ready), Mac
CoreML1024/640 (NOT setup ready; own Mac env/weights still absent). Mac jobs
must not be enqueued for execution before setup. The runtime currently rejects
abnormal pressure itself; forced-contended integration awaits root's queue
contract rather than silently overriding health.

### Complementarity also reports new raw leaks

Extended the existing literal-interval test with a baseline-hidden interval
that FAST exposes. The test first failed with missing `new_raw_leaked_intervals`.
The comparator now reports new raw leaks and the net raw-hidden interval change
beside recovered baseline leaks, keeping the denominator raw leaked=true.
The seven targeted tests pass again; `.tmp/fast/test-red-new-leaks.log` and
`.tmp/fast/integration-new-leaks-green.log`. This prevents a recovered fraction
from obscuring privacy regressions elsewhere. No new model or runtime-cost
behavior changed; scorecards still require all3 actual OCR judges and guards.

### Live queue submitted; overnight ownership retained by root

Read root `docs/PERF-QUEUE.md`. Implemented its exact four environment values:
FORCED/ATTEMPT/RECEIPT/LEASE_FD. The inherited descriptor must match canonical
perf.lock inode. FORCED=1 permits diagnostic execution through abnormal
preflight pressure and always produces measurement_trust.valid:false, including
when endpoint health happens to be normal. Normal runs retain strict preflight.
Eight targeted tests pass, including forced-invalid and wrong-lease cases;
`.tmp/fast/test-red-queue-context.log`, `.tmp/fast/integration-queue-final.log`.
The foreground benchmark never reacquires perf.lock. Nice10/slice are inherited
from root's runner; an extra relative nice increment was removed from queued argv.

Enqueued once using root absolute CLI, priority2, lane fast, queues left OPEN:
- CUDA640 `4f84136911c94c848626352ae4e14775`
- CPU640 `d20a1d71cd384975834d2e35f065ef34`
- CUDA1024 `04030b32631f4e8ab0ec8cceb5a5ef60`
- CPU1024 `ff049f7d437b4d3f82bc7d052097b0d6`

Unique artifacts: `out/fast-queue-{cuda,cpu}-{640,1024}-{attempt}/runtime.json`,
with `perf-health.json` or preflight `rejected-health.json`. Raw immutable
submission responses and exact argv: `out/fast-queue/enqueued-linux.json`.
The two1024 repeats obtain periodic queue evidence required by the new protocol;
older endpoint-valid manual measurements remain unchanged and are not promoted
to joined queue trust. Queued jobs may finish overnight under root's explicit
retention instruction; no root runner/process is stopped by this lane.

Mac CoreML jobs were NOT enqueued: private SDK/weights still absent. Root's queued
Mac timing prohibits starting long untimed setup/quality, so full gate/all7 and
CoreML remain a reported prerequisite. No long untimed job is started on either
host while timing jobs are queued. No new manual timed run followed the override.

Root reporter currently filters clocked `.performance.json` schemas; FAST
`runtime.json` is detector-cost and requires its own join case. It must never
be relabeled as stream fps. Root was informed; common reporter remains untouched.

### Diagnostic frame storage

Extracted diagnostic PNGs moved to OS scratch
`/tmp/agents/irl-shield/fast/mazatlan-diagnostic/`. Raw JSON/health receipts stay
under `out/fast-mazatlan-probe-diagnostic/`. The two opened frame45 views show
feet/pavement and no FAST mask; branded shoe marks keep them benchmark-only.
The active continuity checkpoint is `.tmp/fast/STATE.md`; source remains stable
for retained queued jobs. Mac availability check01:59Z:9 pending timing jobs,
runner checking-readiness; no long setup/quality started.

### 2026-10-30 02:42Z — pre-handback scope and queue evidence

Final source review covered the adapter, static derivation, replay/input-OCR seam,
interval comparison, all7 driver, standalone timing and host launchers. Only the
FAST manifest entry differs from HEAD; all previous manifest data compare equal.
`git diff --check` passes and the manifest remains tracked. New FAST files remain
untracked, intentionally uncommitted for Opus. No common engine/factory/scorer
file changed. The last code test remains eight passing tests; the only later
source-tree edit corrects README timing examples to the mandatory root queue.

One own-job status snapshot, taken between02:39:37Z and02:40:09Z, found all four
Linux FAST jobs pending with zero attempts. Saved only lane jobs and root-runner
identity to `out/fast-queue/status-final.json`; no parent/T3 task was polled.
Exact argv and immutable enqueue responses remain in the original submission
receipts. `out/fast-handback.json` records branch/HEAD, the complete20-path change
list, install/license receipts, full raw endpoint health, queued IDs/paths and
explicit null values for all unmeasured quality/CoreML fields. It must not be
read as an all7 scorecard. No new manual timing or long untimed work started.

### Late queued detector-cost receipts

Before the original timebox, queued runtime artifacts arrived. Manual join
verified each runtime and endpoint-health file against queue SHA/size receipts,
closed exit0, unforced/uncontended state, periodic accounting/contamination and
START/END memory. `out/fast-queue/joined-handback.json` records exact rows,
periodic mean/max other-busy, CPU, raw health and source paths. This is
standalone detector cost only. No three-judge quality or stream fps is inferred.

All four first attempts closed cleanly before deadline. Accepted joined costs
(p50/p95ms, native CPU core equivalents): CPU640288.146/312.711,2.001717;
CPU1024752.170/788.142,1.971669; CUDA64033.085/38.477,1.026147;
CUDA102464.149/68.417,1.013283. Steady durations all>=30s. Queue mean/max
other-busy percentages respectively4.967/8.351,3.452/4.218,11.843/16.805,
2.603/3.485. All raw benchmark endpoints normal; exact load/swap/PSI are
in runtime/perf-health and joined report. Root benchmark_verdict remains
unassessed; acceptance here is detector-cost only, not quality or stream fps.
The final chart was re-previewed at390px,417px content, no console errors.

### Timebox hand-back

Original three-hour deadline reached. Requested/actual branch elannash/m1-fast;
HEAD unchanged2dd52a610eb569ac51eedc84b7840fa852da96c9. All source UNCOMMITTED.
Final process audit: no manually owned or active FAST timing process remains.
All four queued first attempts closed cleanly; root runner left untouched.
Quality/CoreML/full Mac gate remain unfinished for the documented setup/queue
prerequisite. Continuation `.tmp/fast/RESUME.md`; full change list and final
process/source audits retained beside it. No push, PR, merge or subagents.

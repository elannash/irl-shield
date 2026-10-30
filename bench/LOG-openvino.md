# OpenVINO CPU lane

Task started 2026-10-29 23:51 UTC; two-hour timebox. Requested and actual branch
`elannash/m1-openvino`, base HEAD `2dd52a610eb569ac51eedc84b7840fa852da96c9`.
All changes remain uncommitted for Opus review. Only `bench/openvino*` and this
ledger are owned. Engine/common bench/renderer files are unchanged.

Loaded codebase-design, tdd, test-review gate, research measurement guidance;
read routing Roles/Packets/Conducting/Tool access and machines Shell traps.
Test seam: public parity comparison catches count loss, reorder, duplicate reuse,
coordinate drift, vacuous empty evidence and malformed coordinates. It does not
establish real model parity; the CLI must retain actual fixture detections.
Initial red (NotImplementedError): `/tmp/agents/irl-shield/openvino/red-count.log`.
The adapter seam is detect/detect_quads/close; real native integration checks use
synthetic ONNX and pinned real fixtures rather than inventing runtime responses.

## Dependencies and provenance

- OpenVINO 2026.0.0: Apache-2.0, [license](https://github.com/openvinotoolkit/openvino/blob/2026.0.0/LICENSE).
  [System requirements](https://docs.openvino.ai/2026/about-openvino/release-notes-openvino/system-requirements.html)
  explicitly list Apple Silicon/macOS ARM64; attempt native execution, no emulation.
  [CPU precision](https://docs.openvino.ai/2026/openvino-workflow/running-inference/inference-devices-and-modes/cpu-device.html#supported-model-precision)
  distinguishes FP32/FP16/BF16; FP32 is the comparison default. Explicit reduced
  precision hints are optional, unquantized, and must not inherit FP32 parity credit.
- Existing models: `models/manifest.json`, tiny/small Apache-2.0 source license,
  source weights SHA and derived static SHA retained in each receipt.
- Existing RapidOCR 3.10.0 Apache-2.0, ONNX Runtime MIT, NumPy BSD-3-Clause,
  OpenCV Apache-2.0, ONNX Apache-2.0, psutil BSD-3-Clause; existing inventory
  `models/licenses/dependencies.json`. No new models/datasets introduced.
- Fixtures remain benchmark-only, not demo-ready: licensed muted source attribution
  in `fixtures/ATTRIBUTION.md`. Only the seven tune clips may be sampled.

## Host protocol

Private Linux venv `.tmp/openvino/.venv`; Mac mirror `~/code/irl-shield-openvino`
and private `.tmp/openvino/.venv`. Root caches read only; copy required weights
into lane-owned cache before static derivation. Readiness marker initially absent
on both hosts. No heavy install/timing/performance baseline before complete:true.
Shared perf lock path `/tmp/agents/irl-shield/perf.lock` on each host; EX timing,
SH untimed heavy work. Source health rejects warn/critical/unknown. Timings retain
raw health/load/swap/PSI or memory_pressure at both ends.

## Implementation checks before readiness

- Pure parity suite: four tests pass. Deliberately weakening the comparison to
  accept only matched candidate counts falsely accepted a lost ORT detection;
  the regression failed with `AssertionError: True is not false`. Restored source
  byte-for-byte and reran green. Raw logs:
  `/tmp/agents/irl-shield/openvino/{mutation-count,unit-restored}.log`.
- Every compare row checks decoded ORT maps against the existing public
  `PPOCRDetector.detect` result, then matches OpenVINO boxes one-to-one at
  IoU>=.95 and max axis-aligned coordinate error<=2px. All-empty frames cannot
  establish nonempty parity evidence. FP32 is measured first; reduced precision
  hints, if tested, get independent rows and no inherited parity result.
- Seven tune fixture cache hashes match the frozen manifest. Read-only audit:
  `/tmp/agents/irl-shield/openvino/fixture-cache-audit.json`.
- Official PyPI 2026.0.0 native CPython3.11 wheels exist: Linux x86-64 SHA256
  `ba999f7fea57958a533a715afa976704ea6acf39dfd271a89ce78594e7aaa488`,
  macOS ARM64 SHA256
  `107743d5d5b8c7f5adfce67ab4a2941e6da86073eb06f77522b95597fe5d16e5`.
  Raw public package metadata: `/tmp/agents/irl-shield/openvino/openvino-pypi.json`.
  Installation uses `--no-deps` with the complete existing pinned requirements;
  the unused OpenVINO telemetry/conversion dependency is intentionally omitted.
  Inference calls `Core.compile_model` on the verified ONNX file, no converter CLI.

## Reproduction

The caller holds the common host lock; these commands are run with native thread
limits at2, OpenCV at1, nice10, and Linux `app-t3code-agents.slice`. Readiness is
checked by the CLI before any model loads. `compare` samples all seven tune clips;
`clocked` measures actual packet output separately from startup; `quality` uses
injected OpenVINO backends with the existing offline scorer and three judges.
`grade-clocked` grades the final source cycle of a retained sustained movie,
without changing its original processing environment or claiming a corpus gate.

```bash
uv venv --python python3.11 .tmp/openvino/.venv
uv pip install --python .tmp/openvino/.venv/bin/python --no-deps -r bench/openvino-requirements.txt
.tmp/openvino/host-lock exclusive .tmp/openvino/.venv/bin/python -m bench.openvino_bench compare \
  --model-cache /home/elan/code/irl-shield/models/cache \
  --fixtures /home/elan/code/irl-shield/fixtures/cache --out out/openvino/linux-comparison.json
.tmp/openvino/host-lock exclusive .tmp/openvino/.venv/bin/python -m bench.openvino_bench clocked \
  --model-cache /home/elan/code/irl-shield/models/cache \
  --source /home/elan/code/irl-shield/fixtures/cache/sf-market.mp4 \
  --encoder h264_nvenc --out out/openvino/sustained.mp4
.tmp/openvino/.venv/bin/python -m unittest bench.openvino_test -v
```

The runtime has no model download path. Private copied model cache holds static
ONNX derivatives, never the root's cache. Encoder selection is independent of
detector CPU execution; NVENC/VideoToolbox is identified in each performance card.
`libx264` is available explicitly, but is not the Linux default or an all-CPU claim.

- Native Mac synthetic suite: 4/4 pass on Python3.11.15 in the lane venv; no model execution.
  All seven tune fixture hashes match Linux/frozen manifest. Receipts:
  `/tmp/agents/irl-shield/openvino/mac-source-unit.log`, `mac-fixture-audit.json`.

Host-lock clarification retained: after readiness complete:true, load-heavy
untimed pip/setup/media/quality also acquires the SAME SH lease. Root may still
hold EX for additional comparisons; lane jobs wait on that lease. No root process
is stopped and no nested lock is acquired. No timebox extension was authorized.

Common pipeline fingerprint independently recomputed from the live source:
`17ec5477dc6f6f02d6c2370cc4e4e8726de2fe91eea1a244b9977a18b8a40b18`,
exactly the packet fingerprint. Receipt: `/tmp/agents/irl-shield/openvino/common-fingerprint.txt`.

Root corrected a transient Linux readiness publication at approximately00:03UTC:
a preflight rejection was not a30s run, marker reverted to complete:false. This
lane observed no complete:true and had started no heavy install/timed work.
Respect the corrected barrier; Mac readiness is separate and unaffected.

Linux root readiness published complete:true at00:04:28UTC with900steady and1200
encoded frames; its receipt is valid:false/contended and grants no performance
credit here. Private setup was launched under the SH lease atnice10 in
app-t3code-agents.slice. First launch failed before any install because this
shell lacked XDG_RUNTIME_DIR/DBUS_SESSION_BUS_ADDRESS; standard `/run/user/<uid>`
user-bus paths resolved it. Retry waits on the actual shared lease, not a timer.
Raw logs: `/tmp/agents/irl-shield/openvino/linux-install{,-retry}.log`.

Linux installation completed from native wheels under SH lease. SDK smoke executed
a literal synthetic `[[1,2]] * 2` graph and returned `[[2,4]]`, CPU-only i7-7700K,
FP32 hint. `/tmp/agents/irl-shield/openvino/linux-native-smoke.log`.
Existing suite:72tests pass, one Mac VideoToolbox skip; log `linux-tests.log`.
Private `av16.0.1` (existing BSD-3-Clause PyAV plus bundled FFmpeg LGPL obligations)
was added from the existing relay requirements solely to run the full M2 tests.
Install/version receipts: `.tmp/openvino/installed.txt`, `linux-install-av.log`.
Postinstall memory health was warn; no timed inference was accepted there. It
returned normal before EX comparison launch; raw health in
`linux-postinstall-health.json` and `linux-precompare-health.json`. Load averages
were elevated and remain raw evidence, never silently treated as an idle host.

First Linux timed comparison acquired EX but rejected preflight on warn memory
pressure before creating its private model cache (no model inference/parity rows).
The command exited1. `/tmp/agents/irl-shield/openvino/linux-comparison.log`.
Follow-up raw health at00:22UTC is critical by Linux PSI heuristic, despite6.7GB
MemAvailable: memory SOME avg10=25.47%, FULL avg10=20.60%. No timing result is
accepted. `linux-rejected-comparison-health.json` contains raw PSI/swap/load.
No root process was touched. One read-only /proc/locks check confirmed a Python
EX holder and waiting Perl leases; no alternate lock or bypass was used.

Remaining Linux synthetic checks: M2 transport3/3 pass (`linux-m2-tests.log`), lane
4/4 pass (`linux-lane-tests.log`), compileall bench/fixtures/models/shield/relay
exit0. Full `scripts/check` remains Mac-only because of its Swift/Vision build;
no Linux full-gate claim is made. No lane process is retained after these checks.

## First native parity and measurement correction

The first completed diagnostic (`out/openvino/linux-diagnostic-comparison.json`)
used identical21sampledframes across all7tune clips,63calls/runtime/config.
Strict IoU>=.95 and coordinate error<=2px parity passed tiny640, small640,
small960. Tiny960 failed count parity on London bus POV134: ORT2boxes,
OpenVINO3boxes; both ORT boxes matched exactly, with one extra13×15OpenVINO box.
No tolerance was relaxed. This is FP32 threshold sensitivity, not a parity pass.
Raw frame/tensor hashes, both box lists and map error are retained in that card.

Those first timings are **retired diagnostics**: code review found two live ORT
sessions plus OpenVINO, and SHA hashing inside the nominal total-call region.
The source-visible issues would contaminate native CPU attribution/call scope.
Loaded diagnosing-bugs source/hypothesis guidance; real CLI is the executable
check, not mocked sessions. Saved exact old sources in
`.tmp/openvino/measurement-v1.py` (initial mixed-session diagnostic) and
`measurement-v2.py` (first sequential-runtime implementation).

Current comparator uses one live runtime model session at a time and times
public `detect` calls directly. Raw-map calls are separate; receipt hashing is
outside both timed regions. The benchmark inspects the pinned RapidOCR3.10.0
wrapped map session for raw ORT maps because the common public detector only
returns boxes; it adds no engine/factory interface. An all-normal tiny640 row
in the partial sequential run measured public calls ORT29.03/38.86ms median/p95,
OpenVINO21.62/31.81ms, process CPU59.34vs36.92ms median. The run then encountered
warn pressure and stopped before small; it is partial, **not a complete clean
comparison**. Full diagnostic rerun retains explicit invalid timing status.

The standalone sustained wrapper now uses10s startup +30s steady,1200encoded
frames, to match the root receipt shape. This changes only its own adapter
options; common engine source remains byte-identical.

Subsequent complete sequential-runtime diagnostics were rejected **before model
loading** on critical PSI, including the explicitly contended mode. Critical and
unknown health are never bypassed. Logs `linux-isolated-diagnostic{,-retry}.log`,
raw follow-up `linux-diagnostic-rejection-health.json`. The sustained candidate is
Small960 accurate4Hz + Tiny640 fast8Hz (the two lane configurations with strict
FP32 box parity in the first diagnostic),10s startup +30ssteady, CPU detectors,
NVENC encoder. It is queued under EX with strict normal-health preflight; no
accepted sustained performance claim exists until its own START/END receipts.

The exact-snapshot rejection receipt path was exercised on a real critical-health
preflight: `out/openvino/linux-final-diagnostic.rejected-1793320973671413271.json`
contains status, false performance_valid, exact guard health, options and source
identity. No model work occurred in that rejected attempt. With warning pressure
recovered, one explicitly contended Small/Tiny sustained diagnostic is attempted;
even normal endpoints cannot make its timing valid. It still requires the same
EX lease, complete root marker, and noncritical/nonunknown preflight. This is an
invalid diagnostic receipt, never a replacement for the requested healthy trial.

## First actual sustained diagnostic (CPU detection, NVENC encode)

`out/openvino/linux-sustained-diagnostic.performance.json` completed1200encoded
frames,300startup +900steady. Observed steady30.074fps, latency median1.158s /
p95=1.174s,0/900protected, CPU276.205% (onecore100), peak treeRSS807.76MiB,
emitting-poll threadCPU5.078ms/output. Fast7.975Hz, accurate4.0Hz, zero lane
errors. START/END/preflight were all normal. **Invalid performance receipt**
because `--contended` was explicitly supplied: rejection reason
`contended-diagnostic-trial`; throughput/latency clock guards false by design,
protection true. The flag/receipt is preserved; it is not retroactively relabeled.
A fresh strict trial is queued to establish accepted performance independently.
Raw summary: `/tmp/agents/irl-shield/openvino/linux-sustained-diagnostic-summary.json`.
Movie, exact raster masks/egress/model/source/runtime/options receipts are sibling
files in `out/openvino/`. No natural/synthetic privacy fraction has been scored.

Final-cycle pixel guard (not OCR privacy scoring) checked actual encoded output
against source and actual hash-verified raster masks for150frames. All150 passed
existing `bench.metrics.fidelity`; median mask12.094%, p95 mask14.670%, outside
MAE median2.613/p95=2.720. `out/openvino/linux-sustained-diagnostic.guard.json`.
This guard was itself health-diagnostic (warn→critical), and no natural/synthetic
interval score or accepted full quality trial is claimed. Helper source:
`.tmp/openvino/guard.py`; first launch lacked PYTHONPATH and failed before decoding;
retry used `env PYTHONPATH=.` under SH. Python optimization was0 (assertions active).

Parity source/static SHA and matched IoU/count summary:
`/tmp/agents/irl-shield/openvino/native-parity-summary.json`. Tiny64032/32 exact;
Tiny96090/91 (90exact matches +oneextra, strictfail); Small64056/56exact;
Small960116/116, minIoU.9921875, maxcoordinateerror1px. These are box parity
observations on21unique fixture frames, not independent OCR privacy scores.

## Raw-map preprocessing regression and correction

An input-hash audit found42/42 Tiny640/960 tensor mismatches between the initial
artifact-configured path and the later raw-map probe. RapidOCR's defaults are
mean/std0.5, not the artifact's ImageNet values. Public detector calls and the
sustained stream always used artifact parameters; the later **raw-map inference
probes/timings are retired**. Saved affected code in `measurement-v4.py` and
`measurement-v5.py`; original correct detector/test snapshots are
`.tmp/openvino/openvino_detector-v1.py`, `openvino_test-v1.py`.

Added one shared `preprocess_for` used by adapter construction, static-shape
planning and raw-map probes. Synthetic32×32BGR[0,128,255] must normalize to
[-2.117904,.20518208,2.64] in FP32NCHW. Regression went red on the wrong defaults
(actual[-1,.003922,1], maxerror1.64), then green with manifest parameters. Five
lane tests now pass. Raw red/green: `preprocess-unit-{red,green}.log` under OS
scratch. The receipt audit `preprocess-red.log` also fails on the old real tensor
hashes; a corrected native rerun must pass the same hash audit before its map
numbers are used. No detector/engine threshold, weight, renderer or scheduler
changed. This corrects instrumentation and preserves actual model preprocessing.

Corrected native side640 rerun completed on14unique frames (2per all7tune clips),
28calls/runtime/model, one live runtime at a time. All28 audited model/frame
input tensor hashes match the correct first artifact-configured receipt;
`/tmp/agents/irl-shield/openvino/preprocess-native-green.log` reports0mismatches.
`out/openvino/linux-final-side640.json` has statuscomplete/source_unchanged:true.
Tiny64024/24 and Small64035/35 box instances pass strict parity. Full-call
median/p95(ms): Tiny ORT34.30/47.58, OpenVINO26.63/35.20; Small ORT61.47/67.95,
OpenVINO61.17/75.42. These remain **diagnostic**, not accepted timings: explicit
contendedflag; Tiny ORT phase startedwarn, other phase endpointsnormal. Raw-map
inputs in this card are corrected. The earlier wrong-input probes remain retired.
A corrected full640/960 matrix is queued with the same guards and source.

The now-shared production normalization helper was mutation-tested: replace its
artifact mean/std with RapidOCR defaults (one confirmed replacement), observe the
same3channel numerical failures, restore byte-for-byte, rerun5tests green. SHA256
of restored file matches the saved original. `preprocess-mutation-red.log` and
`preprocess-restored-green.log`. This verifies the regression guards the actual
helper used by adapter initialization, static-shape planning and raw probes.

## Conductor queue migration

New conductor plan received at approximately01:13UTC: no further manual timed
launches. No owned timed process was active at receipt. Prepared exact priority2
job specs in `.tmp/openvino/timed-jobs.json`: Linux CPU comparison, Linux strict
Small960/Tiny640 sustained trial, native Mac CPU comparison. Direct argv has
nice10/thread2/Perl alarm600 but **does not reacquire perf.lock**. Each output is
under a unique `queue-<job>-{attempt}/` directory; raw rejected/partial artifacts
remain separate. Queue holds EX and its detached runner owns lifecycle.

Linux private environment is ready. Mac private venv is empty and source mirror
is an earlier checkpoint; current source sync and SH private SDK installation
must precede those timed jobs. Root complete:true marker is still a CLI barrier;
Mac marker remained absent at last read. No new long untimed quality job will
start once that host has timed work queued. Original01:51UTC lane timebox remains;
queued jobs may finish after hand-back under the conductor's explicit overnight
plan. Queue CLI/location is awaited, never inferred or polled through T3 status.

Untimed follow-up argv/preconditions are prepared in
`.tmp/openvino/untimed-followups.json`: Mac SDK setup, own Vision/judge setup,
full `scripts/check`, all7tune-clips natural+synthetic offline quality, and grading
an exact queued Linux sustained bundle on Mac. They are **not launched** and need
SH; long quality must wait until that host's timed queue is empty. Source identity
checks prevent grading an older diagnostic checkpoint as current source.

Clarification: the earlier description of Tiny960 as "threshold sensitivity" is
my inference from its small FP32 map delta and one extra box, not an operator-level
cause diagnosis. The count/IoU observations are measured; the exact cause remains
unproven. No source or tolerance was changed to turn it into a pass.

Conductor acknowledged reading both prepared packets and will consume/enqueue the
two Linux jobs centrally behind root priority1. Mac inference must not be enqueued
against the empty SDK environment; conductor may arrange an isolated prerequisite
setup after root, otherwise Mac stays explicitly pending. No queue runner or job
was launched by this lane after the no-manual-timing directive.

The conductor's newer Linux readiness policy is owner-v2 (available>=4GiB, PSI
diagnostic). This frozen worktree still uses the original
linux-psi-memavailable-v1 health adapter and strict gates. Old strict rejections
remain failures; diagnostic flags/results are never relabeled under the newer
policy. The source/argv packet checksums remain unchanged.

Confirmed once through the central Linux CLI: comparison job
`7cf65773a5e84dd9b0ac1ee7ef15a19d`, sustained job
`30f19e4c05c64961916892ee8f577ef3`, both priority2/pending with no attempts at
that snapshot. No duplicate enqueue or seal. Snapshot:
`.tmp/openvino/perf-queue-linux-status.json`; direct commands/output templates
remain in `timed-jobs.json`.

Conductor subsequently provided hash-verifying root driver
`.tmp/m1/openvino-queue-driver.py`, preserving all5 frozen source hashes and
original argv while forwarding queue FORCED=1 as explicit --contended. It also
added a priority2 Mac combined setup+comparison prerequisite after actual closed
root1200/900frame artifact verification; native Mac SDK/inference still pending.
Root reported retained runners Linux2644125/Mac26083 waiting health. They are
root-owned, not this lane's processes; no polling/stopping/duplicate submission.

Exact archived files for every5lane-source hash in the completed sustained
v4diagnostic were resolved. Receipt:
`/tmp/agents/irl-shield/openvino/sustained-source-archive-audit.json`.
Current code, job specs and all original diagnostic/rejection receipts are kept
separate. Conductor owns queued completion and future qualification after the
original lane01:51UTC timebox.

## Timebox hand-back

Requested/actual branch: `elannash/m1-openvino`; HEAD remains
`2dd52a610eb569ac51eedc84b7840fa852da96c9`. Six new Git-untracked files, no
tracked-file changes, no commit/push/PR/merge. All5 frozen code/dependency/test
source hashes match the conductor packet. Common pipeline fingerprint remains
`17ec5477dc6f6f02d6c2370cc4e4e8726de2fe91eea1a244b9977a18b8a40b18`.
Full hand-back data/hashes: `.tmp/openvino/handback.json`; ready direct argv:
`.tmp/openvino/timed-jobs.json`; untimed prerequisites/follow-ups:
`.tmp/openvino/untimed-followups.json`. Exact historical sources for the completed
diagnostic are retained and audited separately from current code.

Verdict: native Intel CPU adapter works and an explicitly invalid CPU/NVENC
sustained diagnostic emitted30.074fps, encoded p95=1.174s,0%steady protection,
276.2%CPU,1200total/900steady frames. This is **not accepted performance or an OCR
privacy qualification**. Source/backend/normalization corrections are documented;
retired probes are not used as current evidence. Five current lane tests pass,
including numerical normalization and lost-count regression mutation proofs.
Existing suite72total/1platformskip and M2threepass; Python compilation passes.

Unfinished at lane hand-back: healthy accepted full call-latency matrices on both
hosts; a healthy accepted current-source sustained trial; native Mac SDK execution
and parity; three-judge natural/synthetic interval scorecards; native Mac full
gate. Root centrally owns Linux jobs7cf65773a5e84dd9b0ac1ee7ef15a19d and
30f19e4c05c64961916892ee8f577ef3, plus its Mac setup+compare prerequisite. No
duplicate submissions, no manual timing after queue migration, no queue sealing.
Root's hash-verifying wrapper handles FORCED without editing frozen lane code.

All25 scopes started by this lane were checked inactive; cleanup receipt:
`/tmp/agents/irl-shield/openvino/owned-scope-cleanup.json`. Root explicitly retains
its own Linux2644125/Mac26083 overnight runners; this lane did not stop or own
them. Worktree stays locked for their source references. Conductor/reaper releases
it after queued jobs and receipt collection finish. Held-out media, root caches,
other sessions' processes, common engine/render/bench code, and secrets were not
modified. All output assets remain muted benchmark-only, never demo-ready.

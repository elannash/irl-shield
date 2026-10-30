# Q2 execution readiness

This is bench preparation on base `65891cb0b515bc0c34ec4ded89aa6a3228992cc2`.
It contains no quality score, GPU measurement, NVENC trial or acceptance claim.
The conductor subsequently reported GPU_RELEASED; V2_FROZEN remains held. This
implementation task still has CPU-only authority. The phone relay and MediaMTX
are live state and were not touched.

## Render factories and sealed diagnostics

`quality_bundle.render(..., factories=RenderFactories(...))` accepts explicit
renderer and motion factories. Named module functions within the integration
root are hashed by relative path. Closures and lambdas are refused. Identity
contains the function names, parameter snapshot and source hashes. The existing
pipeline fingerprint additionally includes every shield Python file and every
Q2 execution Python file. Adapter identity is checked after rendering, during
verification and grading, and across aggregation. No absolute source hash
exemption exists. New source files must be included when Opus applies the patch.

The ordinary CLI can select the built-in factories through the config's new
`execution` object. `policies/union-015.json` chooses PaddingBudgetRenderer with
an explicit .15 budget; `policies/flow-d1.json` chooses flow via motion_mode.
Neither child implementation is copied here. Their imports fail closed on this
unchanged base until Opus applies those patches. Recall policies continue to
use the existing detector family registry and ordinary factory.

Injected renderers keep their optional dataclass budget in every presentation's
`render_budget` record. Null is retained for protected frames when the adapter
returns no budget. `masked.masks.json` is already a hashed sealed bundle
artifact, so limit/covered/minimum pixels, padding scale and satisfied=false
survive relocation and deferred grading. An impossible bare-quad budget does
not discard or trim any quad. Clocked injected rendering retains the same
per-frame diagnostic, covered by the queue execution artifact manifest. Default
rendering is unchanged; a synthetic comparison checks pixel and mask equality
against the existing Renderer, and existing affected tests remain green.

Flow history receives `max_projection_frames=floor(D*fps)`, including fractional
fps. The clocked factory wraps it in the existing MotionWorker. Missing or bad
projection paths still yield protection in the real engine. D1 is the only
prepared timing arm. D2/D3 are intentionally absent: safely supporting them
requires changes to `render_offline`'s delay validator,
`clocked_pipeline._run_file`'s delay validator and VideoSource's buffering delay
validator, a longer checked history/projection horizon, and associated production
validation. No D>1 validator, engine, live-generation adapter or child file was
changed. Production generation forwarding remains a separate temporal-lane gap.

## Queue entry and release inputs

`bench/q2_execution/plan.json` holds the literal, unexecuted argv templates,
config paths and required inputs. Root must replace every angle-bracket input
and submit the exact measurement separately. The Python path deliberately uses
the authorized existing SDK without resolving its symlink or stacking sites.
All timing is 1280x720, 30fps, D1, static ONNX, NVENC. Baseline is Tiny640 at8Hz
and Small960 at4Hz, .15 area ceiling with `bench/gate-1-policy.json` as its basis.
Accurate lane input width remains1280, with detector limit side960. Arm-specific
recall knobs retain their prepared values. There is no1080p source preparation.

The root-provided release file must contain literal GPU_RELEASED=true and
V2_FROZEN equal to the exact supplied64hex manifest SHA. The conductor released
GPU execution while the functional phone test was unfinished; PHONE_TEST_DONE
is descriptive metadata and does not gate this authorized execution.
This is the conductor's freeze attestation; this bench does not open the v2
manifest or dataset. Every execution requires the active Linux queue receipt,
matching queue environment/attempt and lease inode, plus the inherited canonical
performance descriptor showing an exclusive FLOCK WRITE lock in Linux fdinfo.
Missing flags, changed freeze hash, wrong queue, wrong inode or shared lease
fail before model construction or decoding. CPU tests use only temporary fake
release/queue records, and never produce a real release marker.

Invoke queued.render directly through this module. Do not nest quality_bundle's
CLI clip_lease, scripts/host-lock or scripts/linux-bench inside an inherited EX
lease. Root must supply a current queue: the older checked-in queue deadlines
are not a launch plan. Source/config/output arguments are root-relative;
absolute paths and symlink escapes are rejected. Config bytes are checked again
at completion. Release/queue receipts are recorded; the queue's closed-attempt
trust and contamination review are still required after any run.

## CUDA device intervals

`gpu-cost` runs five cost repetitions by default and refuses fewer. Each runs
the actual clocked source, two actual detector lanes and NVENC with10seconds
warmup then30seconds steady. It reuses production verified models, static
model derivation, PPOCRDetector and RapidOCR preprocessing/postprocessing. It
checks GPU0's1080Ti identity, CUDA runtime12 and compute capability6.1 at runtime.
No CUDA library is loaded by importing these modules or running synthetic tests.

The small optional `session_factory`/`user_compute_stream` seams in
`onnx_detectors.py` are necessary because the existing constructor creates its
session internally, and RapidOCR requires a real ORT InferenceSession. A pure
outside proxy would fail RapidOCR's isinstance check; replacing its internals
or duplicating detector initialization would lose the shared verification and
preprocessing path. The standalone measured adapter uses this optional seam,
then wraps the actual session's run method. Normal session options and outputs
are unchanged. Only the explicit adapter passes user_compute_stream. ORT's
reported CUDA provider options must confirm both has_user_compute_stream=1 and
the exact nonzero pointer before any event result can be recorded.

Each event interval selects the CUDA device, drains the known stream, records
start, calls synchronous ORT run, records end and waits for the end event before
cudaEventElapsedTime. Failed inference still attempts end/wait; event and wait
errors are retained and invalidate cost. Cleanup failures also invalidate the
trial. No host elapsed time is substituted. Host monotonic timestamps select
the steady window and are clearly separate from device_ms.

The scope is a **device-timeline interval around session.run**, not kernel-only
busy time. It includes ordered copies/waits and idle host gaps inside run. It
excludes preprocessing, postprocessing, pre-start drain, NVENC's own cost and
other streams. Lane intervals may overlap: their sum is workload interval cost,
not total-device utilization. CPU operator partitions remain allowed and
recorded by the existing provider policy. Actual placement, copy ordering and
Pascal support still require the real released run; no mock proves those facts.

Steady samples are selected by inference-start host time in the post-warmup
source window. Per-inference cost divides the valid device interval sum by
actual measured calls. Per-source-frame cost divides by every steady presented
source frame, including frames that caused no inference. The raw detector calls,
input tensor hashes/shapes/dtypes, event phases/errors, quads hashes, active
providers, stream options, original and actual static model hashes, source hash,
code fingerprint, driver and package/license receipts are retained. A mismatch
between detector calls and event rows invalidates the cost. Partial failures
retain gpu-cost.json and its SHA even when execution cannot finish sealing.
Completed execution.json seals all output artifacts by hash/size.

Explicit streams, pre-start synchronization and post-run waits can alter
scheduling. Every event run is acceptance_eligible=false and requires paired
normal-provider/output parity before acceptance. Use the separate ordinary
clocked argv for sustained fps, p95 latency and protected fraction; their existing
clock guards are preserved. Cost trials retain those metrics and clock guards
separately. No precision/temporal/recall arm has yet been scored by this task.

## Licenses and validation

No model, dataset, binary, dependency or installation is introduced. Existing
model licenses/sources stay in models/manifest.json and actual backend metadata;
fixtures stay under fixtures/ATTRIBUTION.md. Synthetic test pixels have no brands,
logos or audio. ONNX Runtime is MIT; RapidOCR and OpenCV are Apache-2.0; NumPy is
BSD-3-Clause, with dependency notices already in models/licenses/dependencies.json.

The installed nvidia-cuda-runtime-cu12 wheel identifies12.4.127 and NVIDIA
Proprietary Software in its METADATA, with License.txt containing the CUDA SDK
EULA. The ABI used here is read from that wheel's cuda_runtime_api.h and
driver_types.h. CUDA/cuBLAS/cuDNN/etc and the NVIDIA driver/NVENC remain vendor
runtime dependencies under their installed terms; none is copied. Runtime
receipts inventory installed NVIDIA wheels and hash their installed license
files, plus ORT/RapidOCR/NumPy/OpenCV. License sources are NVIDIA's
https://docs.nvidia.com/cuda/eula/index.html and the installed wheel License.txt;
FFmpeg build licensing remains https://ffmpeg.org/legal.html and the retained
FFmpeg build/command. This task read metadata/source only, with no CUDA call.

Affected CPU synthetic tests run under canonical SH, nice10,
app-t3code-agents.slice, native worker limits2 and OpenCV1. Evidence lives in
out/q2-execution: append-only calls.jsonl, red/green logs, final-cpu.log,
handback.json, complete changes.patch and post-apply-sha256.json. This is not a
full host/GPU gate. Opus must apply this patch and the separate child patches,
rerun synthetic compatibility on the final common fingerprint, establish both
release receipts, provision the exact tune input paths/current queue and then
explicitly authorize measurement. No stage, commit, push or PR is performed.

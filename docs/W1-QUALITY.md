# W1 source preparation and execution contract

W1 continues the existing composed Q2 worktree at65891cb. Historical Q2 calls,
failed gates and checkpoints remain unchanged. The new phase has120 command
invocations recorded append-only in out/w1/invocations.jsonl; the last12 are
reserved for final gates/hand-back. The first checkpoint is2026-10-30 20Z. v1
walk freeze is2026-10-31 13Z; final policy freeze is2026-11-01 14Z. No v2 media
is used here. The c366e5d manifest Git blob alone was hashed to the exact supplied
bb284c1cc701eadf3e7b4dc463e8bf6f46cc6cd606436e033d8cbee3fbf43093.

## Current implementation

MotionHistory now has opt-in box-flow. Each detection supplies its own feature
region; forward/backward LK consistency, local affine inliers, feature spread,
geometry and horizon checks precede projection. This differs from global corner
flow: two independently moving synthetic signs project differently. An atomic
receipt with a failed active local track protects instead of silently dropping
that detection. Empty receipts still require a connected global motion path.

tracking_persist_frames explicitly retains projected geometry after the last
observation, while ordinary lane age/freshness checks still govern coverage.
The duration cannot exceed floor(D*fps). Later observations also project
backward within the existing source window, filling detection gaps. Nothing
bridges missing frames or captured transport generations. Frame.generation is
optional zero for uninterrupted files; decoded nonzero generations fence the
engine in every mode. The old optical-flow submit keyword remains supported.

Default detector rates, padding and rendering are unchanged. Twenty actual
synthetic output frames were compared byte for byte with the initial composed
engine/offline adapters, including masks, pixels, quads and state. The test is
not a throughput result. Physical generation, static-box and unknown-as-clean
mutations produced named assertion failures; all changes were restored and the
affected core tests passed. A reason-code compatibility failure and a test-loader
failure remain in the ledger with their subsequent fixes.

D2/D3 require explicit diagnostic_delay opt-in through benchmark functions and
config.execution. Production/default offline and VideoSource validators still
reject D>1. Diagnostic receipts cannot authorize adoption. Actual total added
latency, including native transport, must remain<=3s; D3 bench buffering can
therefore fail the total-latency requirement even if its quality improves.
Adoption above1s remains reserved Opus. See out/w1/relay-generation-hooks.json
for the exact RelaySession.video hook; W1 has not edited relay/runtime/CLI.

The core fence is released in out/w1/core-release.json. Root owns subsequent
wiring. W5 may call shield.masking.text_geometry(quads) for exact projected quads
and shorter-opposite-edge text-height estimates. Actual raster masks remain the
paint authority and cannot be shrunk from those estimates. W1 makes no stable
object-ID claim: W7 geometric association must remain labeled an estimate.

## Arms and evidence

bench/w1/arms.json ranks18 prepared policy files and separately lists blocked
open-vocabulary work. Baseline is measured first on the final common source.
The current historical baseline is invalid; no winner is carried forward.
Box-flow is the first isolated tracking lever. Persistence and diagnostic delay
variants name box-flow as their conditional parent; they do not pretend to be
one-knob comparisons against a phase-motion baseline. Only guard-passing natural
improvements may stack.

Recall wrappers retain original quads plus v5server detector quads, original plus
CLAHE/gamma-pair detections, or full-frame plus overlapping-tile detections.
Every actual component inference passes through its own measured detector
adapter. Registry provenance remains Paddle OCR; no family override is allowed.
The existing Small1280, Medium960, threshold and accurate8Hz arms remain separate.
Model cache preparation copied only existing licensed, hash-verified public model
weights into this worktree own cache; the root cache and pinned SDK stay unchanged.

The composed baseline already uses polygon geometry and height-based padding.
Those are not new gains. Prepared precision levers change padding or tighten its
union budget. Bare quads are never cut to meet .15. Per-frame diagnostic failures
are sealed in mask records and tallied explicitly per clip; an impossible budget
rejects an arm. Full-frame11 and the actual eight audit-positive closeups remain
mandatory real checks, not claims transferred from synthetic tests. Their source
frames have not been inspected or scored by W1. The old giant overlap/recognizer
recipe is not reintroduced. Higher box thresholds remain screening hypotheses
until all7 tune pairs and these positives pass.

Lighting stress defines dark, backlit and motion-blurred variants for all7 tune
clips, explicitly dev-only. Each variant requires independent truth at the
transformed input and all-judge output leaks. Ordinary-input truth cannot be
reused. Variant preparation/decoding is not executed before the barriers. W5
contrast/sharpen/upscale readers must be added by its integration owner; no
means-only Frosted or shield/skins change is made here.

Flicker is supplemental evidence: distinct per-clip unmasked frames inside one
truth interval between observed fully masked anchors. Independent input truth
and all output leak judges are preserved. Unsampled/input-unobserved, partial-mask
and protected observations are unknown, never clean. A recognized output leak
overrides a full-mask claim. Full truth-box coverage is a geometric anchor, not
proof that every glyph is unreadable. Raw interval states, unknown counts and
per-clip leak indices are retained alongside actual mask observations. Existing
privacy, .15 area+basis, per-clipPROTECT<2% and real-video guards remain unchanged.

## Queue-only execution

No arm metrics run until the final composition full SH gate exits0, functional
CUDA provider/output parity exits0, and the V2 manifest receipt is verified.
GPU_RELEASED is explicit true; PHONE_TEST_DONE is informational, not a GPU
prerequisite. Owner relay1422729 and MediaMTX1426487 are external live state.
Only Sweep owns pressure burners; no timing starts while those are active.

bench.w1.identity freezes source inventory, models and all W1 configs. A changed
helper/source/model/config invalidates the freeze and requires a new baseline.
bench.w1.parity is a root-queued synthetic functional check of six provisioned
model/shape combinations. It compares normal vs verified explicit CUDA streams
exactly and requires nonempty detections. It is not an arm score and omits event
costs. Root supplies the full-gate receipt, current EX queue, release JSON and
private CUDA12 library environment. No old queue/deadline is assumed.

bench.w1.execute renders all14 tune variants under the inherited root EX lease;
it acquires no nested host lock. bench.q2_execution.queued clocked/gpu-cost calls
for W1 configs require the same source/gate/parity evidence. All timing remains
720p30 NVENC,10s warmup plus>=30s steady, with>=5 cost repetitions. Device events
include ordered copies/waits and device-timeline host gaps; they are not kernel
busy time. No host wall interval is relabeled GPU time. Raw component calls,
source-frame denominator, providers, hashes, stream settings and errors remain
visible. Per-source-frame costs include frames with no inference, and nested
model costs are summed without claiming total-device utilization.

Mac grading uses the exact same frozen source and sealed pixels, serialized by
root in SH with its own mirror/cache. There is no EOF one-shot fallback. Root
can call quality_bundle.grade for each bundle, then aggregate. The W1 report
joins verified bundles to closed queue receipts and a raw native-relay receipt;
queue contamination, incomplete cost, source mismatches or missing live feasibility
cannot qualify a winner. Model code/weights remain licensed separately. The three
open-vocabulary model cards and original/runtime code licenses are snapshotted
in out/w1/model-license-receipts.json and models/w1-openvocab-manifest.json.
Those cards declare Apache-2.0, but no weights/runtime/export is provisioned for
those candidates and no speed or readiness is claimed.

A concrete immutable execution packet is issued only after root provides actual
paths/lease metadata and the source freeze is final. Missing inputs remain explicit,
not fabricated placeholders submitted to a queue. No staging, commit, push or PR
is done by W1. Canonical bench/LOG.md integration is proposed separately to root.

## Owner stack-selection continuation

The cap is160 new-phase invocations;93 previously spent and the original16-call
ledger remain preserved. The hard checkpoint stop is2026-10-30 23:30Z. See
bench/w1/staged-arm-plan.json and combination-row.schema.json. Selection uses
only the seven licensed natural tune variants, interval-weighted independent OCR
counts, natural flicker and frame-weighted natural raster area. Synthetic overlays
are a separate regression set and never enter that numerator. Spentv1 stays
explicitly dev-only, separate from the primary score. Owner-real paths have not
been supplied/authorized. No V2 media is accessed.

The search screens model at fixed size, then resolution, tracking, lighting, D,
layered recall and best-frame factors; it does not launch the full model/size grid.
Greedy additions stop below0.5percentage-point natural-hidden gain or a speed
guard break. No actual cost means ineligible. Sustained30fps, measured GPU
utilization<=70%, actual CPU within a supplied walk budget, total end-to-end
latency includingD<=3s, real-video and OCR no-regression evidence are required.
The numeric CPU budget remains unknown and is reported pending. Paced30fps
does not establish maximum sustainableFPS, and event intervals do not establish
GPU utilization. Top3 combinations need full metrics and W12 pairwise privacy/
readable-hit/watchability evidence. W12 owns its harness; W1 changes none of it.
Final recommendation/adoption remains an owner decision, especially D>1.

A second-stage local crop classifier follows open-vocabulary proposals only.
models/w1-verifier-manifest.json records primary SigLIP model metadata/revision/
weight hashes; no model is downloaded, constructed or exported. Logo confirmation
is separate from mask removal. Removal remains blocked until BOTH text detectors
explicitly agree not-text on the same source/generation/crop, all-judge no-regression
retains actual positives/full-frame11, and a physical guard mutant fails then
restores green. Missing/error/unobserved is not a negative. A giant produced by
both text detectors cannot become removable merely because a classifier says
wall. No classifier/removal adapter is released. Cost must include actual1080Ti
GPUms/CROP, crop counts and end-to-end source-frame cost; no cloud product API.
Any actual model/registry/source addition requires a new freeze and paired baseline.

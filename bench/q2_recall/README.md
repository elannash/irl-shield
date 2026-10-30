# Q2 recall lane: code ready, execution HELD

Five opt-in policies reuse existing detector options. No detector, masking,
engine, judge, registry, model manifest, license or shared harness file changes.
Baseline policy bytes are copied exactly from the historical frozen policy;
that is a configuration reference, not a measured common baseline. Run a new
baseline at `65891cb0b515bc0c34ec4ded89aa6a3228992cc2` alongside candidates.

| Policy | Only change from baseline | Effect |
| --- | --- | --- |
| `baseline.json` | none | Tiny640 8 Hz, Small960 4 Hz |
| `small1280.json` | `limit_side_len: 960 -> 1280` | Accurate detector tensor resolution |
| `medium960.json` | `candidate: ppocr-v6-small -> ppocr-v6-medium` | Accurate model, existing cache and Apache-2.0 license |
| `det020.json` | `thresh: .3 -> .2` | DB pixel threshold, **both lanes** |
| `box040.json` | `box_thresh: .5 -> .4` | DB box threshold, **both lanes** |
| `accurate8hz.json` | `accurate_rate_hz: 4 -> 8` | Accurate source sampling rate |

The thresholds are shared because `offline_quality._make_backends` forwards
the same options to both `pipeline.detector_for` calls. A lane-specific threshold
would need a separate harness seam and is not implemented here. All policies
retain `static_model: true`, `.15` area ceiling and its existing basis,
opaque style, `.3` padding, Tiny fast lane, phase motion and original coverage
guards. The registry resolves the actual detector-family union to `paddleocr`.
No family override exists in this lane.

## CPU readiness receipts

The declared quality widths are 640 fast / 1280 accurate, not the final ONNX
tensor widths. `pipeline.detector_for` and RapidOCR preprocessing turn 16:9
inputs into these NCHW tensors:

- Fast Tiny640: `1 x 3 x 352 x 640`.
- Accurate Small960 or Medium960: `1 x 3 x 544 x 960`.
- Accurate Small1280: `1 x 3 x 704 x 1280`.

The detector constructor's general `limit_side_len` default is 960. Quality
explicitly overrides fast to 640 and accurate to 960. No static artifact is
derived in this lane; later existing `prepare_static` derives it from the same
verified weights. Cached Tiny, Small and Medium were hash-checked read-only at
`/home/elan/code/irl-shield/models/cache`. This worktree has no model/fixture
cache provisioned, so root must use existing cached files at execution time;
no download is authorized. Mac grading additionally needs the existing V5
mobile detector and English recognizer.

`test_recall.py` exercises the public preparation interface and detector
preprocessor. Guards reject changed baseline bytes, combined arms, and a
substituted input manifest. Each guard has physical removal -> expected failed
assertion -> byte restoration -> passing run receipts. It uses temporary
synthetic metadata and NumPy arrays, with no ONNX session, detection, OCR or video.
These checks establish preparation/shape behavior only. They cannot establish
runtime model compatibility, GPU cost or hiding quality.

Full `scripts/check` is held: its discovery includes
`tests/test_quality_bundle.py`, whose `setUp` invokes FFmpeg and whose tests call
actual bundle rendering. That crosses the current no-video-render barrier.
No full gate was attempted. Native Mac checks are also held.

## Prepare commands without executing them

From the applied checkout, with a fresh output path:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
OPENCV_FOR_THREADS_NUM=1 PYTHONDONTWRITEBYTECODE=1 \
nice -n 10 \
  /home/elan/.t3/worktrees/irl-shield/t3-7cba93a7/.tmp/integration/venv/bin/python \
  -B -m bench.q2_recall.prepare \
  --inputs /home/elan/code/irl-shield/.tmp/q/frozen-a8a06e3/inputs.json \
  --output out/q2-recall/plan.json
```

The plan pins exact tune-manifest SHA256
`4db58cb96244791874447951b893af48f99b6bd165a59c46884a40a3c5226972`
and baseline-policy SHA256
`0c1ef57d668b52d549676d842d433ed72abe07218642b70104ddc65092d18002`.
It writes literal render/grade/aggregate arrays for each policy, and five
unexecuted clocked performance arrays per policy. These are an inventory, not
authorization to execute all of them or exceed the invocation budget. It never
reads source video, starts a detector/encoder, acquires a queue or runs a command.
The existing harness continues to own all input, source, cache and bundle checks.

The generated current-worktree plan lives in `out/q2-recall/plan.json` and must
be regenerated after root applies the patch. Run from that checkout's cwd.
Root must preserve the exact input manifest and paired baseline's code identity.
No historical bundle is regraded. The new files are outside existing schema-3
cache-source contributors and pipeline fingerprint lists. Source equality does
not establish runtime cache-signature equality: root must record the actual Mac
`Judges.metadata.cache_signature` and compare it across baseline/arms and with
the intended frozen judge cache. Do not force a mismatched cache signature.

## Held screen and scorecard sequence

No screen starts until root relays **all** of PHONE_TEST_DONE, GPU_RELEASED,
the exact V2_FROZEN manifest SHA and the active EX performance queue. Elapsed
time is irrelevant. This lane never reads or evaluates v2, even after freeze.
Root alone owns the final exactly-once v2 evaluation on Nov 1, 2026 at 14:00 UTC.

After release, first render paired baseline/arm tune counterexamples: both
Mazatlan variants, then existing mandatory synthetic positives including
oblique BXR219/824 and large short house 11. Use already licensed tune controls;
do not select scenes from v2. Both historical giant streams contain raw detector
output; do not infer a rectangle-only or lane-agreement fix. A cheap failure
can reject an arm; a cheap pass establishes no all-seven quality conclusion.

Only surviving arms proceed to all seven tune clips / all fourteen variants,
with independent Tesseract eng + Vision accurate en-US input truth/input controls
and **all three** output judges, including PP-v5 English. Preserve sealed masks,
source fingerprints, source frame accounting, and real-video evidence. Require
natural hidden >=90%, synthetic through-interval hidden 100% for gate 1,
real-video guard, median area <=.15 backed by `validate_area_ceiling` and its
basis, and protected <2% on **every clip**. Any guard failure is failure.
Do not use historical 298/343, 44/54, 12.7% or B12 as a common baseline.
No best guard-pass or closest near-miss is measured yet.

Full arm qualification plus five repetitions for every arm cannot fit the
remaining lane invocation budget as separate commands. Root must account for
every later execution and arrange sufficient authorized budget before running;
do not disguise multiple renders/profiles as one invocation.

## Timing contract and exact missing seam

`plan.json` has five `clocked_argv` repetitions for baseline and every arm:
existing `bench.clocked_pipeline`, exact Python path above, NVENC, 30 seconds
steady after 10 seconds warmup, 720p30 source, and explicit policy flags. Its
source is the frozen sf-market natural input. This is an initial matched-cost
source; root must also qualify the slowest tune source and 1080p if required.
Root runs only through its post-release **EX** queue. A q-run shared lease is
untimed and cannot qualify performance. Commands assume existing original
fixture cache for the CLI's licensing check as well as the frozen derivative.
The runtime environment must expose the existing ORT CUDA/cuDNN libraries and
two-thread limits without Python-path overlays or resolving the SDK symlink.

Those commands establish sustained delivery / p95 added latency receipts and
NVENC overlap, **not GPU event time**. GPU event argv is explicitly null. The
missing seam is concrete: `bench.onnx_detectors._session` builds its CUDA EP
internally without `user_compute_stream`, while `bench.pipeline.detector_for`
filters options before constructing the detector. Neither public interface
admits a timing stream. Adding only an event around `detect_quads` on another
stream measures unrelated work. No host-wall measurement may be relabeled GPU.

After release, root needs either verified device profiling covering the actual
ORT work, or an opt-in known-userstream path through those two interfaces.
The latter requires an authorized change to the fenced `bench/pipeline.py`;
this lane did not make it. The detector then needs an opt-in timing interface
around the actual ONNX call, preserving ordinary defaults and metadata. Any
source change triggers fresh paired baseline/cache identity requirements.

For the known-userstream option, create/own the CUDA stream with the existing
CUDA runtime (ctypes and existing wheels only), configure ORT to use that exact
stream, and check provider options plus actual active CUDA EP. Record CUDA
start/stop events on it, ensure all inference work/copy streams join before the
stop event, synchronize stop, then use `cudaEventElapsedTime`. Keep these receipts:

- GPU model/driver/ORT/runtime identities, stream pointer and provider options,
  static model/source weights and input tensor shape/hash.
- Warmup exclusion and at least 30 seconds steady at 30 source fps while NVENC
  actually runs. Five accepted cost repetitions; medians across repetitions.
- Event milliseconds per inference for each lane, actual steady detector call
  counts, and `(fast_event_ms + accurate_event_ms) / steady_source_frames`.
  Configured Hz is not a call-count denominator.
- Device intervals cover kernels and any H2D/D2H operations proven to occur on
  that stream or joined streams. Separately record transfers/copy/host wait and
  CPU preprocessing, threshold/unclip postprocessing, motion, mask rendering,
  decode/encode and end-to-end wall latency. Do not imply events cover CPU work.
- Queue EX lease plus readiness, other_busy-v2, memory/load start/during/end,
  absence of phone/root competing workloads, encoder progress/PTS, sustained
  fps, p95 latency, and process cleanup. Contaminated/missing receipts fail.

If event inclusion or stream identity cannot be verified, GPU time stays
unverified and the arm is not promotable, regardless of quality.

## Mac handoff

`bash bench/q2_recall/sync-mac.sh` is the single prepared **source** sync script,
not executed. Its only destination is
`/Users/elannash/code/irl-shield-q2-recall-bccad190`; it excludes `.git`, `.build`,
`out`, `.tmp`, venvs and caches and performs no delete. It never touches another
mirror or integration checkout. Root separately transfers selected sealed
bundles after rendering. Provision this mirror's already-existing weights and
build the actual current `.build/vision-bridge` from its matching source before
grading, using the specified Mac SDK interpreter
`/Users/elannash/code/irl-shield-integration-run/.tmp/integration/venv/bin/python`.
No single-frame/EOF bridge substitute is permitted. Generated grade argv uses
the existing per-host quality serialization plus canonical SH lease and the
persistent `bench.vision.Vision` helper. Match its current source/build identity
and judge runtime signature; no Mac command was executed in this hand-back.

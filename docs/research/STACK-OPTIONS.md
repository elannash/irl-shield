# IRL Shield stack options

Research date and all external-source access dates: **2026-10-29 UTC**. Decision
horizon: code freeze **2026-11-01, 20:00 America/Los_Angeles**. This is read-only
research against the working tree, not an implementation or a new performance
receipt. No packages, weights, host jobs, Twitch calls, or benchmarks were run.

Evidence labels used throughout:

- **Our measured receipt (R):** an existing project measurement, with its scope;
  **R/inspection** identifies a source/configuration inspection rather than a run.
- **Published benchmark (PB):** an upstream measured result, never a directly
  comparable IRL Shield score unless explicitly stated.
- **Inference (I):** a recommendation, estimate, or conclusion from cited primary
  documentation. API, license, and platform descriptions accompanying these
  conclusions are upstream documentation facts, **not published benchmarks**.

**I — Recommendation:** keep Python, ONNX Runtime, PP-OCRv6, opaque masks, the
deadline engine, and the present FFmpeg/PyAV transport composition for this
deadline. Spend the remaining quality budget on motion reliability and the
already-integrated tiny/small/medium lane combinations. Adopt uv for Python
setup; use MediaMTX when building the multi-client relay shell and pyTwitchAPI
for EventSub. Do not begin a TensorRT, GStreamer, native Core ML, or video-text
transformer migration before the pending sustained receipt. The evidence behind
this prioritization is in the shortlist and sections 1–8 below.

## Ranked swap shortlist

**I — Ranking method:** expected impact on the actual blockers × confidence in
the direction ÷ engineering hours, with privacy quality ahead of incidental
setup speed. Estimates below are implementation/configuration and first
verification time, excluding unattended OCR duration. There is no defensible
numeric forecast of score or FPS gains. Confidence describes the opportunity,
not confidence that the resulting configuration will pass. Four entries are
intentional: the other new tools require integration work that the current bench
cannot yet exercise, so they are not presented as ready-to-confirm swaps.

Platform notation: **M** = Apple Silicon macOS; **L** = Linux/i7-7700K + Pascal
GTX 1080 Ti, CUDA 12; **W** = Windows/NVIDIA. Upstream platform availability is
not IRL Shield validation. **The Windows app and full Windows bench are untested.**

| Rank | Swap / verdict | Expected gain and evidence | Confidence | Cost | Platforms and license | Confirmation |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | **Bench first:** phase-only motion at response floor .5 → the existing lower-floor phase alternatives and ORB/RANSAC | Fewer false coverage failures; potentially better interval hiding and less full-frame protection. **R:** London-bus replay reduces protected natural frames from 52/150 with phase to 28/150 with ORB, still a failure. It is not proof of better geometric privacy. [LOG:289–309](../../bench/LOG.md#L289) | High that this is a blocker; medium that tuning alone solves it | 2–4 h | M/L/W CPU, no new accelerator. OpenCV [Apache-2.0][opencv-license], Python wrapper MIT. L already runs the components; W integration untested. | E1; all six metrics; reject lower protection if OCR leakage rises |
| 2 | **Keep and standardize after bench:** dynamic ONNX/Core ML execution → fixed-shape ONNX sessions for each lane | Lower dispatch/partition overhead and more dependable lane service time. **R:** existing tiny fixed-shape Mac probe reaches 55.91 inference Hz at 640 and 36.97 at 960, not pipeline FPS; older dynamic v5 trial had many Core ML partitions. Different probes/models prevent attributing the whole difference to static shapes. [LOG:61–65,142–147](../../bench/LOG.md#L142) | High that fixed shapes deserve the first runtime comparison; medium on incremental gain because already available | 1–2 h | M Core ML; L CUDA/CPU; W CUDA/CPU upstream, untested here. ORT [MIT](../../models/licenses/dependencies/onnxruntime/LICENSE), PP weights Apache-2.0 [cards][pp-small-card]. NVIDIA libraries retain proprietary terms in [PORTABILITY:198–205](../../bench/PORTABILITY.md#L198). | E2; same model, tensor sizes, lane rates and pixels; compare dynamic/static |
| 3 | **Bench first:** Vision accurate/union or tiny accurate lane → v6-small, then v6-medium; retain tiny fast lane | Better recall at a bounded accurate-lane rate, without changing the detector interface. **PB:** Paddle reports detection Hmean 80.6/84.1/86.2 for tiny/small/medium on its own mixed-image benchmark. **R:** Pascal mean inference is 9.36/14.31/37.27 ms in separate tiny/small/medium probes; no street-video quality winner exists. [PP benchmark][pp-report], [PORTABILITY:99–143](../../bench/PORTABILITY.md#L99) | Medium; published accuracy order is not our leak score | 2–4 h | M Core ML/CPU; L pinned CUDA12/CPU verified; W ORT CUDA/CPU available, app untested. Models/RapidOCR Apache-2.0; ORT MIT; NVIDIA runtime terms as rank 2. | E3; same tiny fast lane, motion, widths and rates; independent OCR judges |
| 4 | **Swap:** venv/pip provisioning → uv-managed Python 3.11 + hash-locked requirements, retaining native media prerequisites | More reproducible setup and fewer Python-version/environment steps. No video-performance gain expected. **I** from uv's Python management and requirements workflow; do not use its advertised install-speed multiplier as our setup measurement. [uv docs][uv-docs] | High for packaging fit; medium for total judge setup because native tools remain | 2–3 h | M/L/W native. uv [MIT or Apache-2.0][uv-license]; dependency/model/native-library licenses unchanged. No driver installation implied. | E4; fresh environment, package/model identity check, then the same six-metric bench |

### Runnable confirmation experiments

**I — Execution conditions:** these are **future recipes, not commands run by this
research task**. Run serially in a conductor-cleared Mac window, from the Mac
repo root, using Bash, with its already-provisioned fixtures, models, FFmpeg,
Tesseract, and compiled `.build/vision-bridge`. If a prerequisite is absent, setup
is a separate authorized step; these commands deliberately bypass `scripts/bench`,
which can install/download. No Twitch or network stream is needed. Existing
arguments are checked against [clocked_bench.py:206–252](../../bench/clocked_bench.py#L206).

**I — Common experiment harness:** run this definition once in that future shell.
The configuration is a reproducible comparison point, not an announced winner.
Reuse a fresh tag if repeating an experiment; output directories cannot overwrite
previous evidence.

```bash
STACK_RUN_TAG="stack-$(date -u +%Y%m%dT%H%M%SZ)"
stack_bench() {
  local experiment="$1"
  shift
  "${STACK_PYTHON:-.venv/bin/python}" -m bench.clocked_bench \
    --split tune --seconds 5 --warmup-seconds 10 --sustained-seconds 30 \
    --D 1 --B 6 --A 30 --padding 0.3 \
    --fast-candidate ppocr-v6-tiny --candidate ppocr-v6-tiny \
    --fast-rate-hz 8 --accurate-rate-hz 4 \
    --fast-width 640 --accurate-width 1280 \
    --fast-limit-side-len 640 --limit-side-len 960 \
    --provider coreml --fast-provider coreml \
    --motion-mode phase --motion-width 320 --motion-min-response 0.5 \
    --encoder h264_videotoolbox --run-id "$STACK_RUN_TAG-$experiment" "$@"
}
```

**I — E1, motion:** only the motion setting changes. Review the London-bus result
but select using **all seven tune clips**, natural and synthetic, not that clip
alone. Lower response thresholds increase the risk of accepting wrong motion;
inspect direct observed leaking boxes and retain the scene-cut/stall guards.

```bash
stack_bench motion-phase-050 --static-model
stack_bench motion-phase-020 --static-model --motion-min-response 0.2
stack_bench motion-phase-005 --static-model --motion-min-response 0.05
stack_bench motion-orb --static-model --motion-mode orb
```

**I — E2, static shape:** same model and lane settings, dynamic versus static.
Confirm actual provider kernel partitions as well as service times: enumerating
Core ML as available does not prove useful acceleration. There is no FP16/INT8
change in this experiment.

```bash
stack_bench shape-dynamic
stack_bench shape-static --static-model
```

**I — E3, model:** first compare tiny/small/medium with the same tiny fast lane.
Then compare the existing Vision accurate-lane option while still retaining the
same tiny fast lane. That is a lane comparison, not the historical all-Vision
reference configuration. If medium misses deadlines, lower its rate in a
separately named experiment rather than silently changing multiple variables.

```bash
stack_bench model-tiny --static-model
stack_bench model-small --static-model --candidate ppocr-v6-small
stack_bench model-medium --static-model --candidate ppocr-v6-medium
stack_bench model-vision --static-model --candidate vision-union
```

**I — E4, setup:** compare the current environment with a fresh uv environment on
the **same** machine, keeping the model cache and native executables identical.
These install commands are documentation only; none were executed. The generated
lock is a proposed artifact, not a lockfile delivered by this research task.
Do not combine `requirements-linux-gpu.txt` with the CPU/Core ML runtime file.

```bash
stack_bench setup-existing --static-model
mkdir -p .tmp
STACK_PYTHON_VERSION="$(.venv/bin/python -c 'import platform; print(platform.python_version())')"
uv python install "$STACK_PYTHON_VERSION"
uv venv --python "$STACK_PYTHON_VERSION" .tmp/stack-uv-env
uv pip compile --python-version "$STACK_PYTHON_VERSION" --generate-hashes \
  requirements.txt requirements-models.txt requirements-relay.txt \
  --output-file ".tmp/$STACK_RUN_TAG-mac-requirements.txt"
uv pip sync --python .tmp/stack-uv-env/bin/python --require-hashes \
  ".tmp/$STACK_RUN_TAG-mac-requirements.txt"
uv pip check --python .tmp/stack-uv-env/bin/python
STACK_PYTHON=.tmp/stack-uv-env/bin/python
stack_bench setup-uv --static-model
unset STACK_PYTHON
```

**I — Every experiment's required comparison:** report natural %, synthetic %,
median area over **all** scored masks, steady encoded p95, observed emitted FPS,
and protected % (overall, each clip, and sustained). Use the actual card, not a
model-only FPS number. A runnable reader for every generated scorecard follows:

```bash
python3 - "out/$STACK_RUN_TAG-"*/scorecard.json <<'PY'
import json
import sys
for filename in sys.argv[1:]:
    with open(filename) as file:
        card = json.load(file)
    sustained = card.get('sustained') or {}
    def percent(value):
        return None if value is None else 100 * value
    print(json.dumps({
        'scorecard': filename,
        'natural_percent': percent(card['natural']['hidden_fraction']),
        'synthetic_percent': percent(card['synthetic']['hidden_fraction']),
        'median_masked_area_percent': percent(card['masked_area_fraction']['p50']),
        'steady_p95_seconds': sustained.get('realtime_added_latency_seconds', {}).get('p95'),
        'emitted_fps': sustained.get('output_wall_rate_fps'),
        'minimum_quality_clip_emitted_fps': card.get('minimum_clip_fps'),
        'protected_percent': percent(card.get('protected_fraction')),
        'sustained_protected_percent': percent(sustained.get('protected_fraction')),
        'per_clip_protected_percent': [
            [row['clip'], row['synthetic_variant'],
             percent(row['performance']['protected_fraction'])]
            for row in card['clips']
        ],
        'gate': card['gate_1'],
    }))
PY
```

**R/inspection — Interpretation limits:** the five-second quality runs remain
short timing diagnostics; only the extra sustained run has 30 seconds steady
after warmup. Tune cards are not held-out acceptance. These commands deliberately
do not invent `--area-ceiling` or `--area-ceiling-basis`, so they cannot earn a
green gate. Adoption requires a tune-derived area ceiling, healthy performance
receipts, then the conductor's milestone held-out evaluation. Required targets:
natural ≥90%, synthetic 100%, real video, configured D≤1 s, steady encoded
p95≤1.3 s, source-cadence 720p30, protected <2%. Preserve raw timing, model and
fixture hashes, scorer identity, and startup separately. [bench/README:107–139](../../bench/README.md#L107),
[clocked_bench.py:140–167,408–430](../../bench/clocked_bench.py#L140).

## 1. Text detection, spotting, and selective masking

**Verdict — I: KEEP the PP-OCRv6/ORT family; BENCH FIRST for lane sizes; keep
Vision as the Mac comparison and independent judge. No verified portable
replacement is demonstrably better on our moving street footage.**

**R/inspection — Current stack verified:** Python 3.11, NumPy 2.2.6, OpenCV
headless 4.11.0.86, Pillow 11.2.1, pytesseract .3.13, psutil 7.0.0,
RapidOCR 3.10.0, ORT 1.31.1 CPU/Core ML, and PyAV 16.0.1 match the requirements
files. The isolated Pascal environment uses ORT-GPU 1.20.2/CUDA12.4/cuDNN9.3.
All five PP detector names, including tiny, are now implemented; DETECTORS.md's
earlier tiny-wrapper caveat is stale relative to
[onnx_detectors.py:20–26](../../bench/onnx_detectors.py#L20).
`detect_quads` preserves PP polygon geometry for the engine; the old portability
probe's axis-aligned-box seam is not the only interface.
[requirements](../../requirements.txt), [model requirements](../../requirements-models.txt),
[GPU requirements](../../requirements-linux-gpu.txt), [relay requirements](../../requirements-relay.txt),
[onnx_detectors.py:147–160](../../bench/onnx_detectors.py#L147).

**R — Baseline quality is not accepted:** the currently retained, corrected
initial offline Vision card is **370/435 natural = 85.06%, 48/54 synthetic =
88.89%, median area 10.85%, protection 8.19%**, with no real-time verification.
It fails. Its improvement cannot be attributed solely to model/motion because
protected frames also hide text. The older synchronous reference has
313/435 natural, 54/54 synthetic but lacks verification of two synthetic input
controls and is ineligible. These are different policies, not a valid detector
speed ranking. Sources: [initial card](../../bench/results/initial-vision-clocked-policy.json),
[reference card](../../bench/results/reference-vision-union.json),
[LOG:297–315](../../bench/LOG.md#L297). No held-out data was evaluated for this report.

**PB — Relevant upstream comparison:** Paddle's v6 introduction reports detection
Hmean **80.6 tiny / 84.1 small / 86.2 medium**, versus v5 mobile 75.2 and server
81.6, on its in-house 16-category image benchmark. This supports measuring the
larger lane, not declaring a winner on moving video. Its end-to-end OCR table
includes recognition and image I/O; those latencies do not measure our
detection-only path. [Official report, §3.1 and §3.3][pp-report].

**I — Candidate comparison, based on primary sources:**

| Candidate | Availability/license | M / L-Pascal / W | Decision before freeze |
| --- | --- | --- | --- |
| PP-OCRv6 tiny/small/medium | Official ungated ONNX weights, Apache-2.0 on each model card [tiny][pp-tiny-card], [small][pp-small-card], [medium][pp-medium-card] | M ORT CPU/Core ML route (tiny measured; no medium-on-Mac receipt established here); L all three CPU/CUDA measured; W ORT CPU/CUDA upstream, untested here | Best expected value: already integrated, same DB-style postprocessing. Choose E3's winner; keep tiny fast lane unless quality disproves it. |
| FAST via docTR/OnnxTR | FAST author repo Apache-2.0 with GitHub-release checkpoints; OnnxTR Apache-2.0, ONNX pretrained FAST variants and explicit CPU/CUDA/Core ML/OpenVINO options [FAST][fast], [OnnxTR][onnxtr], [license][onnxtr-license] | CPU portable; M Core ML and L/W CUDA paths are upstream options. Exact graph partitioning, Pascal pin compatibility and our latency/recall are unverified | Best architecture-diverse follow-up, **not a proven upgrade**. 4–8 h adapter/provenance/rotation work; do only if existing v6 misses cannot meet quality. Prefer OnnxTR export path over original FAST's compiled postprocessing. |
| CRAFT | Author code MIT; pretrained general/IC15 weights linked from author README; no separate explicit weight grant found beyond the repository license [author README/license][craft] | CPU and CUDA implementation; ONNX/Core ML conversion not supplied/verified here; W PyTorch/CPU possible, not a validated deployment | Character-region diversity could help disconnected text. Weight-rights clarification plus export/postprocessing cost makes it weaker than OnnxTR for this deadline. No assertion that CRAFT beats v6. |
| Original DBNet/DBNet++ | Downloadable models in author's tree; no explicit root license verified [DB repo][db] | Original deformable-convolution/PyTorch path; Core ML and Pascal/Windows deployment not established | Reject this artifact route under the required permissive-weight constraint. Apache-licensed docTR DB implementations are a separate option, not a license for these weights. |
| TransDETR | Author README says MIT and links pretrained models; requires custom deformable-attention and rotated ROIAlign builds, and says recognition code is withheld [TransDETR][transdetr] | Documented Linux/CUDA; no working M Core ML/CPU/W route established | Real video temporal modeling, but not a portable drop-in; reject before freeze. |
| GoMatching / GoMatching++ | Author code/models public, but README states research-only and no explicit permissive root license was found [author README, Statement][gomatching] | Detectron/custom-op CUDA research stack; M Core ML/CPU/W not established | Reject license/deployment fit despite relevance to video. Do not contact authors or sign up. |

**PB — Why FAST and video spotters remain candidates:** FAST publishes
Total-Text image-detection quality/speed tables; GoMatching publishes video
tracking/spotting metrics. Neither source supplies the same fixtures, independent
OCR leak scoring, hardware, and deadline policy as IRL Shield. Comparing those
numbers to PP's in-house Hmean or our interval-hiding percentage would be invalid.
[FAST Model Zoo][fast], [GoMatching results][gomatching].

**I — A recognizer cannot safely decide which text to leave visible:** a crop
recognizer such as the already bundled Apache-2.0
[English v5 recognizer][pp-rec] can prioritize street/plate/number-like detections
or label them for a local UI. It cannot guarantee that all location-bearing text
is identified: a shop name, short digit, unfamiliar language, or partial sign may
be identifying despite low recognition confidence. A semantic classifier creates
another false-negative stage and cannot recover text the detector never found.
Keep masks on all detected text; never use failed recognition or a benign class
as permission to unmask. The existing short-digit and failed-blur receipts make
this concrete. [LOG:248–285](../../bench/LOG.md#L248). This is a privacy inference,
not a claimed classifier benchmark.

## 2. Inference runtimes, precision, shapes, batching

**Verdict — I: KEEP ORT; use fixed shapes first. BENCH FIRST for OpenVINO only
if CPU-only deployment becomes a requirement. Defer native Core ML conversion.**

**R — Measured scope:** Linux's same-20-frame, 544×960-input probes show tiny
CPU/CUDA mean **66.01/9.36 ms**, small **207.05/14.31 ms**, medium
**714.61/37.27 ms**. CPU/CUDA integer boxes match and real CUDA kernel events were
recorded. Warmup is two frames; timing is the other 18, including profiler
overhead. Runs had different shared-host load. v5/small serial CUDA+NVENC trials
only reached **21.53/21.49 FPS**; tiny/medium have no corresponding encoded
receipt. This argues against a runtime rewrite justified by an inference-only
number. [PORTABILITY:81–143,174–179](../../bench/PORTABILITY.md#L81).

**I — Runtime decision table:**

| Runtime | M / L-Pascal / W; license | Recommendation and limit |
| --- | --- | --- |
| ONNX Runtime | M CPU/Core ML; L CPU/pinned CUDA12; W CPU/CUDA upstream. MIT; CUDA/cuDNN proprietary redistributable terms, not MIT [CUDA EP][ort-cuda], [cuDNN matrix][cudnn], [local license receipts](../../bench/PORTABILITY.md#L181) | Keep proven platform-specific pins. Current PyPI GPU defaults from 1.27 are CUDA13; separate CUDA12 builds exist but still need exact cuDNN/architecture validation. Do not replace this working Pascal combination with “latest.” |
| TensorRT current | Linux/Windows NVIDIA, **no Pascal**; no Mac. Free NVIDIA SDK under its [license agreement][trt-license], not wholly Apache-licensed because some OSS components are | Current official support matrix identifies **11.4.1, SM≥7.5**. CUDA12 wheels do not restore SM6.1 support. Avoid. [Current matrix][trt-matrix] |
| TensorRT 8.6 legacy | Historical Linux/Windows SM6.x route, no Mac; NVIDIA SDK license | Official hardware history says Pascal was deprecated in 8.6; archived matrix lists SM≥6.0. This is a legacy integration branch, not current support. Old engine builds/provider/version bindings and calibration cost lose to the measured ORT path. Do not claim TensorRT 8.6 is “latest Pascal.” [Hardware history][trt-history], [8.6 matrix][trt-old] |
| OpenVINO | M Apple-Silicon **CPU**, L Intel CPU (not CUDA on Pascal), W Intel CPU/GPU; [Apache-2.0][openvino-license] | Official requirements include 6th–14th-gen Intel Core and Apple Silicon CPU. Good CPU fallback candidate for the 7700K; no project result proves it faster. Use latency mode/single-request first, same ONNX/preprocessing, not automatic throughput batching. 3–6 h adapter + receipt. [Requirements][openvino-system], [CPU implementation][openvino-cpu] |
| Native Core ML via coremltools + Swift | M runtime only; no L or W native inference. coremltools [BSD-3-Clause][coreml-license]; runtime is Apple proprietary system framework under the applicable [Apple software terms][apple-license] | ORT already uses Core ML MLProgram/ALL with compiled cache and static-shape support. A native port only earns its cost if profiling shows material fallback/copy/dispatch overhead. Modern coremltools documents PyTorch/TensorFlow conversion, not a supported direct current ONNX import; the existing ONNX files do not make this a trivial export. 8–16+ h; defer. [ORT Core ML EP][ort-coreml], [Apple conversion workflow][coreml-convert] |
| ncnn | CPU/Vulkan across M/L/W, not CUDA12 EP; [BSD-3-Clause][ncnn-license] | Credible small native deployment runtime, but another conversion/preprocess/precision path with no local result. No expected deadline advantage over already-working ORT; defer. |

**I — FP16:** keep FP32 ONNX as the portable reference. A Mac FP16 candidate can
reduce bandwidth and exploit Core ML's execution choices, but still needs raw-map,
box, OCR and latency checks. Do not apply “FP16 is faster” to the 1080 Ti:
NVIDIA's Pascal guide distinguishes high-throughput GP100 FP16 from much slower
consumer GP104 FP16; the 1080 Ti's GP102 is not a Tensor-Core GPU. That is grounds
to measure, not a guaranteed acceleration. The guide explicitly describes GP102
as similar to GP104. [Pascal guide §1.4.1–1.4.2][pascal].

**I — INT8:** defer until FP32 quality has margin. For the Intel AVX2 CPU, ORT
documents QDQ/S8S8 as a starting point and U8S8 saturation risks; representative
**tune-only** calibration must include tiny digits, low contrast, motion blur and
edge entry. A smaller file is not evidence of fewer leaks. ORT's GPU INT8 guide
requires Tensor-Core-capable hardware and uses TensorRT, so “Pascal supports
DP4A” does **not** make our CUDA EP path an INT8 upgrade. OpenVINO may exploit
INT8 on CPU, but quantization needs the same six-metric experiment and an adapter.
OpenVINO also converts FP16 computations to FP32 on CPUs without native FP16;
FP16 weights do not magically give the 7700K fast FP16 arithmetic.
[ORT quantization][ort-quant], [OpenVINO CPU precision][openvino-cpu].

**I — Shapes and batching:** fixed lane input shapes are the least expensive
runtime improvement (E2). Keep batch 1 and newest-frame queues for live detection.
Temporal batches deliberately wait for future samples and use the delay budget;
throughput benchmarks can hide the resulting deadline misses. Crop batching is
reasonable for offline judges or a nonblocking optional recognizer, never a
reason to stall the masking deadline. ORT explicitly warns that dynamic shapes
can hurt Core ML performance. [Core ML EP options][ort-coreml],
[engine deadline ownership](../ARCHITECTURE.md#L12).

## 3. Video pipeline and Python concurrency

**Verdict — I: KEEP FFmpeg + NUT + PyAV for this freeze. BENCH FIRST for reducing
copies after the integrated pipeline is measured; defer GStreamer/zero-copy work.**

**R/inspection — What actually exists:** FFmpeg decodes to raw BGR and PCM in NUT;
PyAV demuxes it, converts video to NumPy, submits to the engine, and muxes
presented raw video plus gated PCM back to NUT. A second FFmpeg encodes H.264/AAC.
This is already a hybrid in-process/subprocess design. It is **not compressed
audio passthrough**: input audio is converted to mono 48 kHz PCM and re-encoded.
The current network adapter has no post-migration Mac/network validation;
historical eight-second transport receipts are not new-engine evidence.
[media.py:54–104](../../relay/media.py#L54),
[bridge.py:44–83,121–168](../../relay/bridge.py#L44),
[M2-GROUNDWORK:10–24,86–105](../M2-GROUNDWORK.md#L10).

**I — Options:**

| Pipeline | M / L-Pascal / W and license | Trade for this project |
| --- | --- | --- |
| Existing FFmpeg subprocesses + PyAV | FFmpeg runs on M/L/W with platform codecs; PyAV BSD-3-Clause; FFmpeg LGPL-2.1-or-later or GPL according to build. Existing Mac FFmpeg is GPL-3.0-or-later, not generically LGPL. [FFmpeg license][ffmpeg-license], [PyAV license][pyav-license], [M2 licenses](../M2-GROUNDWORK.md#L189) | Keep process isolation, timestamp-bearing NUT, bounded queues and explicit ownership. Windows pipe shutdown and encoder selection still need work; package availability alone is not an app port. |
| Full PyAV/libav in-process | M/L/W; BSD-3-Clause wrapper plus actual linked FFmpeg terms | Could remove raw pipe copies and process handoffs, and permit compressed AAC packet remux with careful time-base handling. No automatic A/V-sync or latency guarantee. Pinned v16 **does have hardware-acceleration APIs**—old stable caveat pages saying hardware decode is unsupported are obsolete for this version. [v16 source][pyav-hw] |
| GStreamer appsink/appsrc + native plugins | M VideoToolbox `vtenc_h264`; L/W nvcodec CUDA memory; CPU on all. Core LGPL-2.1, selected plugin/dependency licenses separately [license][gst-license], [nvh264enc][gst-nv], [vtenc][gst-vt] | Best longer-term candidate if we need one media clock, reconnection/state control and GPU memory negotiation. Rewriting the adapter, error paths, timestamps and packaging is 12–24+ h, without local evidence of a gain. |
| PyNvVideoCodec | Linux/Windows NVIDIA; no Mac. The Python library is **MIT**, per NVIDIA; the underlying Video Codec SDK has separate [NVIDIA terms][nvcodec-license] | Current supported GPU families start at Turing, excluding Pascal. Good modern-RTX option, wrong current host. Do not substitute a CUDA13 package. [Official product/license page][pynv], [current system requirements][pynv-system] |

**I — True NVDEC → CUDA → NVENC:** FFmpeg already documents GPU-resident decode,
CUDA filters and encode; GStreamer's `nvh264enc` accepts `memory:CUDAMemory`.
Neither gives this project zero-copy merely by choosing NVENC. Our NumPy renderer,
OpenCV CPU motion, and CPU DB postprocessing still require host data. A real port
would retain full-resolution decode surfaces on the GPU, create a small detector
input, apply opaque quads/slates with a GPU kernel, and pass the masked surface
to NVENC; it must also keep the fixed-delay buffer and fail-closed ownership.
Downloading small probability maps or detector samples is different from
round-tripping every full-resolution frame. This is a substantial alternative
pipeline, not a flag. [NVIDIA FFmpeg guide][nv-ffmpeg], [GStreamer caps][gst-nv].

**I — A/V:** preserve source PTS/time bases and delay audio by the same
presentation clock; copying compressed AAC packets could avoid a second audio
encode if the source codec/container allow it. It still needs AAC priming,
discontinuity/reconnect and interleave tests. GStreamer provides clock/latency
machinery but its `appsrc` queues also require bounds and backpressure handling.
OBS buffering is an additional delay. Retain the generated flash/pulse and exact
frame-ID checks and measure at the sink, not only before the encoder.
[GStreamer latency][gst-latency], [appsrc][gst-appsrc],
[existing timing scope](../M2-GROUNDWORK.md#L153).

**I — GIL/free-threaded Python:** keep 3.11. NumPy documents that many low-level
operations release the GIL; native inference and codec work must be profiled
separately from Python bookkeeping. Free-threading only removes a Python
interpreter bottleneck, not CPU/GPU transfers, encoder buffering, locks, or slow
detectors. Python's docs warn unsupported extensions may re-enable the GIL.
The pinned binary stack would need a new compatibility matrix. Existing
projection/render batching already has receipts, making this a poor time to
change interpreters. [NumPy threads][numpy-threads], [Python free threading][python-ft],
[LOG:303–307](../../bench/LOG.md#L303).

## 4. Ingest, relay, OBS, and Twitch egress

**Verdict — I: SWAP the eventual one-client listener shell to MediaMTX for normal
RTMP/SRT clients; KEEP the masking engine. BENCH FIRST for optional bonded SRTLA.
KEEP conventional H.264/AAC RTMP-family Twitch publishing.** This is an integration
recommendation, not a claim that MediaMTX is in the repo or already faster.

**I — Best broad protocol front door:** MediaMTX supports protocol conversion
among RTMP, SRT, RTSP and WebRTC without writing each server. It supplies native
standalone binaries for macOS/Linux/Windows and is [MIT][mtx-license]. CPU/GPU
generation is immaterial to this routing layer. Estimated integration 3–6 h:
phone → private `raw` path → engine → separate `shielded` path → OBS/Twitch.
Only the protected path may be used by viewers. The current `input_nut` RTMP
adapter is a listener, so it must become a client when reading MediaMTX; starting
the server alone does not integrate it. [Protocol capabilities][mtx-protocols],
[install platforms][mtx-install], [input_nut](../../relay/media.py#L54).

**I — SRT is not SRTLA:** MediaMTX and SRS advertise SRT, not BELABOX SRTLA bond
termination. MediaMTX's documented publish URL is
`srt://HOST:8890?streamid=publish:raw&pkt_size=1316`; encoder StreamID settings
must match. Standard StreamID syntax is also documented. Test each Moblin,
Larix, IRL Pro, and BELABOX mode actually claimed in the README; do not infer
bonding from successful single-link SRT. Tailscale carries IP connectivity; it
does not implement SRTLA aggregation. [MediaMTX SRT docs][mtx-srt],
[BELABOX SRTLA protocol/prerequisites][belabox-srtla].

**I — Server comparison:**

| Option | M / L-Pascal / W; license | Decision |
| --- | --- | --- |
| MediaMTX | Native M/L/W, GPU-independent; MIT | Preferred compact RTMP/SRT/RTSP gateway. No promise of a 1-second phone-to-viewer budget. |
| SRS | Official current tree documents M/Linux and native Windows x64 in v8; MIT plus third-party licenses [README][srs], [Windows docs][srs-windows] | Credible maintained alternative. Do not repeat the older “Windows requires Cygwin/WSL” claim. No project requirement justifies switching to its larger server feature set over MediaMTX. |
| BELABOX original `srtla_rec` | Linux supported, WSL1 historically confirmed; native M/W unsupported; AGPL-3.0 [license][belabox-license] | Upstream explicitly marks the receiver unsupported/not suitable for production and directs users to a paid cloud. Reject that hosted route; do not sign up. |
| IRLServer `srtla_rec` + IRL SRT server | Receiver fork AGPL-3.0, IRL server MIT, patched SRT [MPL-2.0][irl-srt-license]; server documents M/Linux, no native W. Receiver-on-Mac is not separately verified. WSL/Linux deployment is a separate unverified option [receiver][irl-srtla], [receiver license][irl-srtla-license], [server][irl-srt-server] | Best free SRTLA compatibility experiment if bonding is required for the demo. Use the maintained receiver/server combination and its pinned SRT fork; do not presume forwarding it to generic upstream libsrt preserves behavior. 4–8+ h and portability costs; optional, not a core prerequisite. |
| `srt-live-transmit` | M/L/W build paths, MPL-2.0 [SRT license][srt-license] | Keep already-working shim for the current Mac FFmpeg without SRT. Upstream calls it a sample app; a native libsrt-enabled FFmpeg build is simpler later, but replacing the live Mac toolchain before the receipt adds risk. [Utility docs][srt-transmit] |

**I — Latency contract:** D≤1 s is the relay presentation buffer, not an honest
claim of ≤1 s across cellular bonding, Tailscale, retransmission, relay encoding,
OBS and Twitch delivery. SRT's receive latency spends a separate retransmission
budget. The BELABOX example uses 2000 ms; lowering it to fit a product slogan can
lose media. Record relay-added latency separately from full sender-to-sink
latency. Also preserve units: `srt-live-transmit` uses ms for its latency option;
FFmpeg's SRT URL option is microseconds. [SRT utility][srt-transmit],
[FFmpeg SRT options][ffmpeg-protocols], [M2 units receipt](../M2-GROUNDWORK.md#L94).

**I — OBS egress:** for the least code, publish H.264/AAC into MediaMTX and add a
network Media Source in OBS; MediaMTX's own OBS instructions use
`rtsp://localhost:8554/stream` (use our `shielded` path instead). SRT/MPEG-TS is also appropriate where already
configured, with its added receive latency measured. RTMP reading works through
the server; OBS being able to **publish** RTMP does not make OBS an RTMP server.
Avoid NDI/virtual-camera routes for this deadline: more dependencies, with audio
and synchronization still to solve. OBS platform availability covers M/L/W; it
does not validate our Windows relay. OBS itself is [GPL-2.0-or-later][obs-license].
[MediaMTX OBS instructions][mtx-obs],
[read/publish capabilities][mtx-protocols].

**I — Twitch egress according to Twitch's current docs:**

- **RTMP / RTMPS:** the documented baseline is the RTMP ingest URL plus runtime
  stream key and optional `?bandwidthtest=true`. Keep single H.264/AAC output;
  use TLS when the selected official ingest endpoint/client supports RTMPS.
  Keep bandwidth-test mode until a live session is authorized. FFmpeg supports
  RTMPS, but our local-only URL helper currently allows neither RTMPS nor public
  Twitch hosts; the production egress adapter is still work to build.
  [Twitch broadcasting guide][twitch-ingest], [FFmpeg protocols][ffmpeg-protocols],
  [local_url](../../relay/media.py#L9).
- **Enhanced RTMP / Enhanced Broadcasting:** E-RTMP specifies newer codec and
  multitrack extensions; Twitch is a participant, but that does not make every
  extension/codec valid at every ingest. Twitch's Enhanced Broadcasting workflow
  is real, with multiple encodes and negotiated stream configuration. Use the
  streamer's existing OBS integration if wanted, after the protected feed reaches
  it. Building a multitrack Twitch encoder adds cost without helping privacy.
  [E-RTMP specification][ertmp], [Twitch announcement][twitch-enhanced].
- **WHIP:** MediaMTX/SRS/OBS supporting WHIP is not proof of public Twitch WHIP
  ingest. The current Twitch developer guide documents RTMP; no general public
  Twitch WHIP endpoint/contract was found in that guide. Do not substitute Amazon
  IVS documentation or old experiments for Twitch support. Keep WHIP out of
  direct Twitch egress unless Twitch publishes the applicable production contract.
  This is a conclusion about the available docs, not proof Twitch has never run
  a WHIP experiment. [Twitch guide][twitch-ingest].

**I — Validation needed after integration:** current `bench.clocked_bench` is a
file/codec bench, not a MediaMTX network bench. Extend the timestamp/flash/pulse
scenario to the chosen gateway and **real** detector lanes, score the received
natural/synthetic output with the frozen scorer, and record all six metrics plus
A/V offset and reconnect failure behavior. The old `relay.scenario` uses no-op
detectors and cannot confirm this recommendation. There is no invented existing
`--mediamtx` flag or claim of a completed network experiment here.
[relay/run.py:29–32](../../relay/run.py#L29), [scenario scope](../M2-GROUNDWORK.md#L145).

## 5. Motion and tracking

**Verdict — I: BENCH FIRST with the existing phase/ORB choices; next add sparse
local pyramidal LK if those fail. Do not add NVIDIA OFA or a heavyweight tracker.**

**R — Why this layer ranks first:** the corrected leak taxonomy and London-bus
motion replay show intermittent coverage failure, not merely insufficient model
capacity. Lowering the photometric guard did not change phase acceptance. A lower
phase-response floor passed synthetic fault checks, but those checks establish
fail-closed scheduling, not geometric correctness on all street clips.
[LOG:277–309](../../bench/LOG.md#L277),
[initial taxonomy](../../bench/results/initial-clocked-policy-taxonomy.json).

**I — Comparison, using the APIs' documented capabilities:**

| Approach | M / L-Pascal / W; license | Fit |
| --- | --- | --- |
| Phase correlation + ORB/RANSAC | CPU M/L/W, OpenCV Apache-2.0 | Keep cheap translation as baseline; ORB can fit camera rotation/perspective. Neither captures all independent object motion or parallax. Tune thresholds only through E1. |
| Sparse pyramidal LK around text quads | CPU M/L/W, already in OpenCV, Apache-2.0 [tracking API][cv-track] | Best next implementation if global projection fails: forward/backward consistency and sufficient surviving points per ROI, with redetection, age limits and scene-cut invalidation. Estimated 4–8 h. Cannot discover new text by itself; uncertainty must still protect. |
| DIS optical flow | CPU M/L/W, OpenCV Apache-2.0 [DIS API][cv-dis] | Dense field handles local motion better in principle; try ULTRAFAST/FAST at reduced resolution, then aggregate motion around each quad with occlusion checks. More computation and mask-warp validation than sparse LK. 6–10 h; no local speed/quality receipt. |
| NVIDIA Optical Flow SDK | **No M, no Pascal**. Supported NVIDIA Linux/Windows Turing+; NVIDIA SDK terms [official page][nvofa] | Dedicated hardware is attractive on newer streamer PCs, but does not exist in the 1080 Ti. An SDK download requiring a developer account is also outside this research's account boundary. Reject for this entry; no sign-up. |
| Apple Vision registration | M only, Apple proprietary system framework [translation][vision-translation], [homography][vision-homography] | Could replace global motion on Mac, but duplicates an already-portable seam. No timing/recall receipt proves a gain. Keep as a Mac-specific fallback experiment, not the default. |
| Vision object tracking / optical flow | M only, Apple proprietary framework [track object][vision-track], [optical flow][vision-flow] | Object tracking propagates an initialized box, not text recall or reliable perspective quads. Apple explicitly describes dense optical-flow requests as resource-intensive. Not the cheapest portable fix. |
| ByteTrack-style box association | Association logic CPU M/L/W; author implementation MIT [ByteTrack][bytetrack] | Useful for identities and associating low-score detector observations; not a substitute for pixel motion or new-text detection. The repo already has source-indexed temporal union. Axis-aligned boxes/Kalman assumptions are a poor automatic replacement for perspective quads and camera cuts. 4–8 h without a demonstrated need; defer. |

**I — Preserve the privacy invariant:** a propagated box is a mask proposal, not
fresh detector coverage. Keep result source index, completion deadline, transform
path completion times, age bounds and scene identity. Tracking confidence cannot
permit stale/uncovered LIVE output. The engine's async-motion deadline bug was
already reproduced and fixed; new tracking must not undo that boundary.
[ARCHITECTURE:19–34](../ARCHITECTURE.md#L19), [LOG:239–246](../../bench/LOG.md#L239).

## 6. Twitch integration

**Verdict — I: SWAP “no library yet” for pyTwitchAPI's EventSub WebSocket client;
keep a small owned device-code adapter if the library's polling behavior does not
match Twitch's current contract. Do not write the WebSocket lifecycle from scratch.**

**I — pyTwitchAPI is the closest fit:** its first-party source has
`EventSubWebsocket`, reconnect/resubscription handling, revocation callback and
message-ID deduplication history; its base exposes chat and Shield Mode topics.
`oauth.CodeFlow` really calls Twitch's device endpoint—it is not just an
authorization-code flow with a misleading name. It is [MIT][twitchapi-license],
uses asyncio/aiohttp and is suitable for M/L/W without a GPU. The app-level
callback, token storage and Windows behavior are still untested. Estimate 3–6 h
for a minimal adapter plus offline lifecycle fixtures.
[WebSocket source][twitchapi-ws], [EventSub topic source][twitchapi-base],
[CodeFlow source][twitchapi-oauth].

**R/inspection — Maintenance check:** GitHub's current release metadata lists
pyTwitchAPI **4.5.0, released 2025-05-21**; its repository is not archived and
was pushed on 2026-10-20. TwitchIO's latest release is **3.3.2, 2026-08-04**.
Thus pyTwitchAPI is a fit-based choice, not a claim of faster release cadence.
Pin and verify the release rather than installing moving `master`; the inspected
source links describe the retrieved implementation. If the small adapter needs
newer event coverage absent from that release, prefer TwitchIO before maintaining
a private client fork. [pyTwitchAPI release API][twitchapi-release],
[repository metadata][twitchapi-repo], [TwitchIO release API][twitchio-release].

**I — Keep ownership of the device flow:** the inspected CodeFlow polls once per
second and does not visibly use a returned interval; do not assume its helper
fully implements the current device authorization contract. Implement/verify
poll timing, expiration, denial, refresh and token validation at startup and
hourly against Twitch's documentation, retaining synthetic fixtures before any
live use. Avoid the library's convenience JSON token-storage helper: this repo
requires Infisical,
and the stream key stays runtime memory only. This is a source-based caveat,
not a reproduced live API defect. [CodeFlow implementation][twitchapi-oauth],
[Twitch device flow][twitch-auth], [token validation][twitch-validate].

**I — TwitchIO 3 is a maintained alternative, not an IRC-only library:** current
docs describe EventSub, Shield Mode events and a bot command framework. It is
[MIT][twitchio-license] and cross-platform Python. Prefer it if command routing
becomes the product; for three event types and a small headless relay, its
OAuth/web/bot framework adds more surface than necessary. Its documented default
OAuth server is not evidence that it already gives the requested device flow.
[Current TwitchIO quickstart][twitchio], [Web/OAuth reference][twitchio-oauth].

**I — Correctness the library does not supply for us:**

- Use `channel.chat.message`, `channel.shield_mode.begin` and `.end`; check
  moderator/broadcaster identity for commands, including Shared Chat provenance.
  Request only needed read scopes; receive-only Shield Mode requires
  `moderator:read:shield_mode` (or the manage scope), with moderator ID matching
  the WebSocket user token. Getting the stream key requires its own authorized
  user scope. [Subscription types][twitch-topics], [Get Stream Key][twitch-key].
- Twitch events are at-least-once. Deduplicate by message ID and apply idempotent
  source-keyed holds. A `.end` event clears only Twitch Shield Mode's hold, never
  a moderator/local hold. [WebSocket reference][twitch-ws-reference],
  [existing precedence](../ARCHITECTURE.md#L48).
- A hard disconnect loses events; there is no replay. Keep the control source
  untrusted/held until reconnected and resubscribed, then reconcile **Get Shield
  Mode Status** rather than assuming the last state is current. A chat hold lost
  during disconnect cannot be reconstructed from that status; require an explicit
  subsequent release for any reconnect uncertainty hold. Planned server
  reconnects have a different handover flow. [Twitch lifecycle][twitch-ws],
  [Shield Mode status][twitch-shield-status].

**I — Account boundary:** no service registration was performed. Researching a
free client is within scope; a real Twitch login/app registration remains the
already-planned Twitch integration, not an account needed to evaluate a model or
install a free tool. Judges must be able to replay synthetic controls without a
Twitch account; real Twitch operation necessarily needs the streamer's account.

## 7. One-command setup for judges

**Verdict — I: SWAP Python environment setup to uv, KEEP native OS media tools;
do not make Docker the default. BENCH FIRST for pixi only if native prerequisite
installation becomes the dominant clean-machine failure.**

**R/inspection — Current limitation:** `scripts/setup` is Darwin-only, installs
Homebrew tools, creates a Python 3.11 venv and compiles Swift. The main bench
constructs Vision judges and uses Mac fixture preparation. Portable detector
inference is measured; portable one-command application setup is not delivered.
uv alone will not create a Windows CLI, replace POSIX pipe handling, supply an
Apple OCR judge, or install an NVIDIA driver. [scripts/setup](../../scripts/setup),
[bench.judges](../../bench/judges.py), [clocked_bench:196–202](../../bench/clocked_bench.py#L196),
[bridge.py:26–41](../../relay/bridge.py#L26).

**I — Packaging comparison:**

| Tool | License / M, L-Pascal, W support | Choice |
| --- | --- | --- |
| uv | MIT/Apache-2.0; native M/L/W, installs/manages Python; no GPU dependency [docs][uv-docs], [license][uv-license] | Best low-cost change. E4 verifies fresh environment equivalence. Hash-lock dependencies per platform/runtime and checksum model/native-tool downloads. Keep CUDA and CPU ORT packages mutually exclusive. |
| pixi | BSD-3-Clause; native M/L/W, lockable conda + PyPI environments and task runner [docs][pixi], [license][pixi-license] | Strongest alternative for managing Python **and** ffmpeg/libsrt/Tesseract binaries. More migration than uv; must verify each channel's FFmpeg encoders, macOS VideoToolbox, old Pascal CUDA pins and exact licenses. 4–8 h. It cannot supply Apple system frameworks in Linux. |
| conda / Miniforge-style environment | conda BSD-3-Clause; M/L/W, packages have individual licenses [conda license][conda-license] | Works, but a larger environment/channel story than needed. Use free community channels rather than assuming every Anaconda distribution/service is free. No detector-performance advantage established. Prefer pixi if moving into this ecosystem. |
| Docker Engine CPU / NVIDIA Linux | Moby Apache-2.0; containers Linux-native, Mac/Windows generally via VM; NVIDIA toolkit needs host driver [Moby license][docker-license], [NVIDIA setup][container-toolkit] | Useful optional Linux reproducibility target. A CPU container cannot be advertised as real-time without a gate receipt. GPU container must pin CUDA12/cuDNN/ORT and cannot hide incompatible driver/GPU constraints. |
| Docker Desktop | Proprietary subscription terms, free only within its stated eligible categories; M/W. GPU passthrough to Linux containers documented on WSL2/NVIDIA, not native Apple Vision/VideoToolbox [Mac terms][docker-mac], [GPU support][docker-gpu] | Poor universal default under “free for judges”; Mac Linux containers do not run the native Apple pipeline. WSL2 compute availability is not proof our NVENC path is supported/performs there. Native Windows binaries are cheaper where possible. |
| Homebrew | BSD-2-Clause package manager; M/Linux, no native W; package licenses separate [license][brew-license] | Keep narrowly for Mac-native prerequisites. Pin/document tested versions; dependency side effects were observed even with no-upgrade flags. Do not upgrade the active perf toolchain. [M2 setup receipt](../M2-GROUNDWORK.md#L138) |

**I — Smallest shippable setup design:** one `setup` entry selects a tested native
profile (Mac Core ML/Vision; Linux CUDA12/Pascal or CPU; Windows portable profile),
installs Python with uv, syncs the matching lock, verifies checksummed weights and
media tools, then runs a local synthetic replay. Keep the replay free of external
credentials; real Twitch login is a separate command. Use per-platform native
FFmpeg with required SRT/RTMP/encoder features rather than silently falling back
to an untested codec. This is proposed work, not a CLI claimed to exist.
[uv resolution/locking][uv-lock], [architecture CLI status](../ARCHITECTURE.md#L113).

## 8. Other replacements and scope corrections

**Verdict — I: KEEP current language, image libraries, opaque rendering, judges,
and the deadline engine. Finish integration and evidence before adding another
framework. No clearly better library replaces the remaining hot paths today.**

**I — Current foundations are appropriate:** Python 3.11 ([PSF license][python-license]),
NumPy (BSD-3-Clause), OpenCV (Apache-2.0; MIT Python wrapper), Pillow
([MIT-CMU][pillow-license]), psutil ([BSD-3-Clause][psutil-license]) and PyAV
(BSD-3-Clause plus linked FFmpeg obligations) are available across M/L/W at the
library level. Keep the pins through the freeze; none of the supplied evidence
justifies a language rewrite or dependency upgrade as the first speed lever.
NumPy/ORT/OpenCV/RapidOCR license snapshots are in
[models/licenses](../../models/licenses/README.md) and the
[dependency inventory](../../models/licenses/dependencies.json).

**R — Recent renderer/projection changes already address obvious overhead:** the
Linux component receipt reports 50-quad rendering medians 5.197→.777 ms and
500-quad projection 17.522→1.116 ms, with exact geometry/pixel checks. These are
CPU component results, not Mac throughput. Keep the batched opaque renderer; a
new compositor has no demonstrated incremental benefit. [render receipt](../../bench/results/render-cpu-comparison.json),
[motion batch receipt](../../bench/results/motion-batch-cpu.json),
[LOG:269–307](../../bench/LOG.md#L269).

**I — Keep independent readability judges:** Tesseract/Vision accurate/PP-English
recognition exercise different failure modes. Replacing all with a newer PP
recognizer would reduce independence exactly where the detector is PP. Retain
the frozen scorer, known synthetic truth, unmasked controls and all-slate guard;
“faster judging” is not a live-stream optimization. Tesseract's
[Apache-2.0 source][tesseract], the PP recognizer's
[Apache-2.0 card][pp-rec] and the existing Mac-only Vision distinction cover the
licenses/platform limits; Tesseract/PP can run M/L/W but Vision cannot.
[bench truth/independence contract](../../bench/README.md#L43).

**R/inspection — Integration gap outranks a new stack:** `relay.run` instantiates
two `NoOpDetector`s, hardcodes VideoToolbox egress, and accepts only local/Tailscale
RTMP/SRT URLs. Its current code is explicitly groundwork. Before claiming a
phone-to-Twitch product, connect the real lanes, platform encoder selection,
runtime-only Twitch key and source-keyed controls, then obtain a received-output
scorecard. Windows `select` on pipe descriptors also needs a portable shutdown
path; installing Windows-compatible packages alone is insufficient.
[relay.run:15–32](../../relay/run.py#L15), [media.py:9–20,93–104](../../relay/media.py#L9),
[bridge.py:26–41](../../relay/bridge.py#L26), [README:8–18](../../README.md#L8).

**I — Change trigger:** if the pending healthy Mac receipt still cannot emit
720p30 after the existing batching/static-shape/motion work, profile the actual
integrated critical path. If copies/encoding dominate, a small in-process PyAV
prototype comes before a full GStreamer migration; if lane service dominates,
choose the already-measured Pascal host or smaller lane input/rate before a new
runtime. Any trade must preserve all six scorecard metrics and the real-video,
coverage and scene-cut guards. [Existing Linux evidence](../../bench/PORTABILITY.md#L174),
[PyAV v16 hardware API][pyav-hw], [NVIDIA GPU pipeline docs][nv-ffmpeg].

## Rejected or deferred options

Each line is **I**, based on the cited primary evidence; “defer” does not mean
the tool is bad outside this deadline/hardware combination.

- **Current TensorRT:** no SM6.1 support; CUDA12 packaging does not change that. [Matrix][trt-matrix]
- **Legacy TensorRT 8.6 adoption:** possible historical Pascal route, but integration/calibration and a legacy dependency branch lose to verified ORT. [History][trt-history]
- **Unpinned latest ORT-GPU/CUDA/cuDNN:** CUDA13 defaults and lost Pascal library support; preserve the tested pins. [ORT][ort-cuda], [CUDA archive][cuda-archive]
- **Native Core ML rewrite now:** Mac-only, conversion/graph-parity cost; existing ORT already invokes Core ML. [Apple workflow][coreml-convert]
- **FP16-everywhere policy:** consumer Pascal is not GP100/Tensor-Core hardware; no measured win. [Pascal guide][pascal]
- **GPU INT8 as an ORT-CUDA switch:** ORT's documented route requires Tensor Core hardware/TensorRT, not this Pascal path. [Quantization guide][ort-quant]
- **Original DBNet++ weights:** permissive license not established from the author tree. [Repository][db]
- **CRAFT as immediate default:** no v6 street-video win and no verified direct Core ML artifact/weight grant beyond repo MIT. [Author README][craft]
- **GoMatching/GoMatching++:** research-only statement, permissive licensing not established, no portable runtime path. [Statement][gomatching]
- **TransDETR:** custom CUDA ops, missing recognition code, no verified all-platform deployment. [Author README][transdetr]
- **EAST author's implementation:** GPL-3.0; fails this task's permissive detector constraint. [Author license][east-license]
- **Ultralytics general YOLO checkpoints:** no vetted scene-text weights in this survey; AGPL/commercial terms do not meet the detector constraint. [Licensing][yolo-license]
- **Semantic/recognition-based unmasking:** another false-negative stage; no evidence of zero missed identifying text. [PP recognizer][pp-rec], [short-digit receipts](../../bench/LOG.md#L259)
- **GStreamer/true GPU zero-copy before freeze:** viable long-term, but requires a new GPU renderer/ownership path, not simply NVENC caps. [Caps][gst-nv]
- **PyNvVideoCodec current:** supported GPU list starts at Turing, no Mac/Pascal fit. [Product requirements][pynv]
- **NVIDIA Optical Flow SDK:** no Pascal accelerator; account-required SDK evaluation is also outside scope. [Requirements][nvofa]
- **Vision tracking as universal default:** Apple-only, no project quality/speed win established. [API][vision-track]
- **ByteTrack as a drop-in privacy tracker:** identity association does not supply new detections or perspective-correct masks. [Author repository][bytetrack]
- **BELABOX Cloud/paid receiver:** payment/service dependency excluded; public original receiver is explicitly unsupported. [BELABOX README][belabox-srtla]
- **Direct Twitch WHIP:** no production public contract found in the current Twitch ingest guide. [Guide][twitch-ingest]
- **Custom Enhanced Broadcasting stack:** extra encodes/negotiation do not improve privacy; let OBS own it. [Twitch announcement][twitch-enhanced]
- **Free-threaded Python migration:** extension compatibility change without proof the interpreter is the bottleneck. [Python docs][python-ft]
- **Docker as universal judge setup:** Linux containers cannot supply the native Apple pipeline; Desktop eligibility and GPU setup add conditions. [Mac terms][docker-mac], [GPU docs][docker-gpu]

## Source ledger and snapshot

All sources below are primary sources accessed **2026-10-29 UTC**, including
license files. “Current” describes the fetched page on this access date; release
numbers are not inferred from search-engine timestamps. No cloud inference,
paid API, sales form, waitlist, or new account was used. Apple symbol pages were
read through their official `.md` representations when the HTML required JS.
Twitch's help article for current stream-quality options returned a CSS/loading
shell, so no precise new-codec rollout or tier eligibility is asserted from it.
The web reader initially failed on the historical TensorRT archive; a subsequent
ordinary HTTPS read reached the archive and confirmed the SM≥6.0 statement.
The current matrix independently settles the actual Pascal decision.

**R/inspection — Report verification:** all 103 external reference URLs in the
first verification pass returned HTTP 200 via ordinary HTTPS; the three GitHub
release/maintenance API references added afterward were also read successfully.
All local link targets exist, all six Bash code blocks pass `bash -n`, the embedded
Python reader parses, and every option used in E1–E3 exists in the current bench
argument definitions. These are document/recipe checks, not benchmark execution.
The report is a new **untracked** file; it was not staged or committed.

**R/inspection — Sample frame:** the five requested docs, requirements files,
engine/detector/motion/masking code, local relay adapters, bench entry points,
existing result JSON and license inventory. Excluded: held-out media/evaluation,
private credentials, Mac filesystem/process inspection, GPU jobs, model downloads,
and any external account reads. Working-tree HEAD at start:
`8e8868d9f3329fc603efd5ce377669c0307d4431`. Much of the working tree is untracked
and belongs to concurrent work, so HEAD alone does not bind these conclusions.
Requested-doc SHA-256 snapshots read during research:

| File | SHA-256 |
| --- | --- |
| AGENTS.md | `c4289f6bcbac3454136fb04777fd59d219c6347ae6678d1ccaa0321a24797358` |
| docs/ARCHITECTURE.md | `8b59f1d111daa92c9ecbee2c2529261712b04fa93511886816f8fdcdf3c32baf` |
| bench/DETECTORS.md | `ef34430a5cf93b6f480df90100cae331e08227e2d5d8c18ec5dc93f9f664e5e4` |
| bench/PORTABILITY.md | `1b271b8661cc7cb4ecb5f2b91ce97d7ab02b9043e7e49d827d029c015b60b5e1` |
| bench/LOG.md | `2f642651936d671493b4e877ce47e224477750f31464b1c5afba9cdd4e6e4bb9` |

[pp-report]: https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/docs/version3.x/algorithm/PP-OCRv6/PP-OCRv6.en.md
[pp-tiny-card]: https://huggingface.co/PaddlePaddle/PP-OCRv6_tiny_det_onnx
[pp-small-card]: https://huggingface.co/PaddlePaddle/PP-OCRv6_small_det_onnx
[pp-medium-card]: https://huggingface.co/PaddlePaddle/PP-OCRv6_medium_det_onnx
[pp-rec]: https://huggingface.co/PaddlePaddle/en_PP-OCRv5_mobile_rec
[fast]: https://github.com/czczup/FAST
[onnxtr]: https://raw.githubusercontent.com/felixdittrich92/OnnxTR/main/README.md
[onnxtr-license]: https://raw.githubusercontent.com/felixdittrich92/OnnxTR/main/LICENSE
[craft]: https://raw.githubusercontent.com/clovaai/CRAFT-pytorch/master/README.md
[db]: https://github.com/MhLiao/DB
[transdetr]: https://github.com/weijiawu/TransDETR
[gomatching]: https://raw.githubusercontent.com/Hxyz-123/GoMatching/main/README.md
[east-license]: https://github.com/argman/EAST/blob/master/LICENSE
[yolo-license]: https://www.ultralytics.com/legal
[ort-cuda]: https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html
[ort-coreml]: https://onnxruntime.ai/docs/execution-providers/CoreML-ExecutionProvider.html
[ort-quant]: https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html
[cudnn]: https://docs.nvidia.com/deeplearning/cudnn/backend/v9.3.0/reference/support-matrix.html
[cuda-archive]: https://docs.nvidia.com/cuda/cuda-features-archive/index.html
[trt-matrix]: https://docs.nvidia.com/deeplearning/tensorrt/latest/getting-started/support-matrix.html
[trt-history]: https://docs.nvidia.com/deeplearning/tensorrt/latest/architecture/architecture-overview.html#hardware-support-lifetime
[trt-old]: https://docs.nvidia.com/deeplearning/tensorrt/archives/tensorrt-861/support-matrix/
[trt-license]: https://docs.nvidia.com/deeplearning/tensorrt/latest/reference/sla.html
[openvino-system]: https://docs.openvino.ai/2026/about-openvino/release-notes-openvino/system-requirements.html
[openvino-cpu]: https://docs.openvino.ai/2026/openvino-workflow/running-inference/inference-devices-and-modes/cpu-device.html
[openvino-license]: https://raw.githubusercontent.com/openvinotoolkit/openvino/master/LICENSE
[coreml-convert]: https://apple.github.io/coremltools/docs-guides/source/convert-pytorch-workflow.html
[coreml-license]: https://raw.githubusercontent.com/apple/coremltools/main/LICENSE.txt
[apple-license]: https://www.apple.com/legal/sla/
[pascal]: https://docs.nvidia.com/cuda/pascal-tuning-guide/index.html
[ncnn-license]: https://raw.githubusercontent.com/tencent/ncnn/master/LICENSE.txt
[opencv-license]: https://raw.githubusercontent.com/opencv/opencv/4.11.0/LICENSE
[cv-track]: https://docs.opencv.org/4.x/dc/d6b/group__video__track.html
[cv-dis]: https://docs.opencv.org/4.x/de/d4f/classcv_1_1DISOpticalFlow.html
[nvofa]: https://developer.nvidia.com/opticalflow/download
[vision-translation]: https://developer.apple.com/documentation/vision/vntranslationalimageregistrationrequest.md
[vision-homography]: https://developer.apple.com/documentation/vision/vnhomographicimageregistrationrequest.md
[vision-track]: https://developer.apple.com/documentation/vision/vntrackobjectrequest.md
[vision-flow]: https://developer.apple.com/documentation/vision/vngenerateopticalflowrequest.md
[bytetrack]: https://github.com/FoundationVision/ByteTrack
[ffmpeg-license]: https://ffmpeg.org/legal.html
[ffmpeg-protocols]: https://ffmpeg.org/ffmpeg-protocols.html#srt
[nv-ffmpeg]: https://docs.nvidia.com/video-technologies/video-codec-sdk/13.0/ffmpeg-with-nvidia-gpu/index.html
[pyav-license]: https://raw.githubusercontent.com/PyAV-Org/PyAV/v16.0.1/LICENSE.txt
[pyav-hw]: https://raw.githubusercontent.com/PyAV-Org/PyAV/v16.0.1/av/codec/hwaccel.pyx
[pynv]: https://developer.nvidia.com/pynvvideocodec
[pynv-system]: https://docs.nvidia.com/video-technologies/pynvvideocodec/read-me/system-requirements-common.html
[nvcodec-license]: https://developer.nvidia.com/nvidia-video-codec-sdk-license-agreement
[gst-license]: https://raw.githubusercontent.com/GStreamer/gstreamer/main/LICENSE
[gst-nv]: https://gstreamer.freedesktop.org/documentation/nvcodec/nvh264enc.html
[gst-vt]: https://gstreamer.freedesktop.org/documentation/applemedia/vtenc_h264.html
[gst-appsrc]: https://gstreamer.freedesktop.org/documentation/app/appsrc.html
[gst-latency]: https://gstreamer.freedesktop.org/documentation/additional/design/latency.html
[numpy-threads]: https://numpy.org/doc/stable/reference/thread_safety.html
[python-ft]: https://docs.python.org/3/howto/free-threading-python.html
[python-license]: https://docs.python.org/3.11/license.html
[pillow-license]: https://raw.githubusercontent.com/python-pillow/Pillow/11.2.1/LICENSE
[psutil-license]: https://raw.githubusercontent.com/giampaolo/psutil/release-7.0.0/LICENSE
[tesseract]: https://github.com/tesseract-ocr/tesseract/blob/main/LICENSE
[mtx-protocols]: https://mediamtx.org/docs/features/publish-and-read
[mtx-install]: https://mediamtx.org/docs/kickoff/install
[mtx-license]: https://raw.githubusercontent.com/bluenviron/mediamtx/main/LICENSE
[mtx-srt]: https://mediamtx.org/docs/publish/srt
[mtx-obs]: https://mediamtx.org/docs/read/obs-studio
[obs-license]: https://github.com/obsproject/obs-studio/blob/master/COPYING
[srs]: https://github.com/ossrs/srs/blob/develop/README.md
[srs-windows]: https://www.ossrs.net/lts/en-us/docs/v8/doc/windows
[belabox-srtla]: https://raw.githubusercontent.com/BELABOX/srtla/main/README.md
[belabox-license]: https://raw.githubusercontent.com/BELABOX/srtla/main/LICENSE
[irl-srtla]: https://raw.githubusercontent.com/irlserver/srtla/main/README.md
[irl-srtla-license]: https://raw.githubusercontent.com/irlserver/srtla/main/LICENSE
[irl-srt-license]: https://raw.githubusercontent.com/irlserver/srt/belabox/LICENSE
[irl-srt-server]: https://github.com/irlserver/irl-srt-server
[srt-license]: https://raw.githubusercontent.com/Haivision/srt/master/LICENSE
[srt-transmit]: https://raw.githubusercontent.com/Haivision/srt/master/docs/apps/srt-live-transmit.md
[twitch-ingest]: https://dev.twitch.tv/docs/video-broadcast/
[ertmp]: https://github.com/veovera/enhanced-rtmp/blob/main/docs/enhanced/enhanced-rtmp-v2.md
[twitch-enhanced]: https://blog.twitch.tv/en/2024/01/08/introducing-the-enhanced-broadcasting-beta
[twitchapi-license]: https://raw.githubusercontent.com/Teekeks/pyTwitchAPI/master/LICENSE.txt
[twitchapi-ws]: https://raw.githubusercontent.com/Teekeks/pyTwitchAPI/master/twitchAPI/eventsub/websocket.py
[twitchapi-base]: https://raw.githubusercontent.com/Teekeks/pyTwitchAPI/master/twitchAPI/eventsub/base.py
[twitchapi-oauth]: https://raw.githubusercontent.com/Teekeks/pyTwitchAPI/master/twitchAPI/oauth.py
[twitchapi-release]: https://api.github.com/repos/Teekeks/pyTwitchAPI/releases/latest
[twitchapi-repo]: https://api.github.com/repos/Teekeks/pyTwitchAPI
[twitchio-license]: https://raw.githubusercontent.com/PythonistaGuild/TwitchIO/main/LICENSE
[twitchio]: https://twitchio.dev/en/stable/getting-started/quickstart.html
[twitchio-oauth]: https://twitchio.dev/en/latest/references/web.html
[twitchio-release]: https://api.github.com/repos/PythonistaGuild/TwitchIO/releases/latest
[twitch-auth]: https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/#device-code-grant-flow
[twitch-validate]: https://dev.twitch.tv/docs/authentication/validate-tokens/
[twitch-topics]: https://dev.twitch.tv/docs/eventsub/eventsub-subscription-types/
[twitch-key]: https://dev.twitch.tv/docs/api/reference/#get-stream-key
[twitch-ws]: https://dev.twitch.tv/docs/eventsub/handling-websocket-events/
[twitch-ws-reference]: https://dev.twitch.tv/docs/eventsub/websocket-reference/
[twitch-shield-status]: https://dev.twitch.tv/docs/api/reference/#get-shield-mode-status
[uv-docs]: https://docs.astral.sh/uv/
[uv-license]: https://github.com/astral-sh/uv#license
[uv-lock]: https://docs.astral.sh/uv/pip/compile/
[pixi]: https://pixi.prefix.dev/latest/
[pixi-license]: https://raw.githubusercontent.com/prefix-dev/pixi/main/LICENSE
[conda-license]: https://raw.githubusercontent.com/conda/conda/main/LICENSE
[docker-license]: https://raw.githubusercontent.com/moby/moby/master/LICENSE
[docker-mac]: https://docs.docker.com/desktop/setup/install/mac-install/
[docker-gpu]: https://docs.docker.com/desktop/features/gpu/
[container-toolkit]: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html
[brew-license]: https://raw.githubusercontent.com/Homebrew/brew/master/LICENSE.txt

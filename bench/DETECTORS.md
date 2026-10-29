# Downloadable detector candidates

Reviewed 2026-10-29. These are candidates for the licensed-video bench, not
claims about IRL Shield accuracy or Apple Silicon latency. The upstream
benchmarks use different evaluation data and hardware. The project scorecard
decides which detector ships.

The artifact shortlist contains five offline, Apache-2.0 model artifacts:

| Bench name | Artifact | Why measure it |
| --- | --- | --- |
| `ppocr-v5-mobile` | RapidOCR ONNX conversion of PP-OCRv5 mobile detector | Established lightweight baseline for edge deployment. |
| `ppocr-v5-server` | RapidOCR ONNX conversion of PP-OCRv5 server detector | Larger v5 comparison that can reveal a recall/latency trade. |
| `ppocr-v6-small` | Official PaddlePaddle PP-OCRv6 small ONNX detector | Current mobile/desktop tier; a practical successor to v5 mobile. |
| `ppocr-v6-medium` | Official PaddlePaddle PP-OCRv6 medium ONNX detector | Current higher-capacity comparison for the largest recall budget. |
| `ppocr-v6-tiny` | Official PaddlePaddle PP-OCRv6 tiny ONNX detector | A smaller edge candidate; raw CPU/CUDA inference is verified in PORTABILITY.md, while the full tune quality comparison is in progress. |

PaddleOCR describes v5 mobile/server as efficiency/accuracy variants in its
[v5 model list](https://paddlepaddle.github.io/PaddleOCR/main/en/version3.x/pipeline_usage/OCR.html).
The [v6 introduction](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/algorithm/PP-OCRv6/PP-OCRv6.en.md)
identifies tiny, small, and medium deployment tiers and reports improved
in-house detection results over v5 server. Its results are a reason to include
v6, not a substitute for this project's street-video evaluation. The v6
[small](https://huggingface.co/PaddlePaddle/PP-OCRv6_small_det_onnx) and
[medium](https://huggingface.co/PaddlePaddle/PP-OCRv6_medium_det_onnx) official
ONNX model cards identify the weights as Apache-2.0. Manifest entries link
to immutable model revisions and the exact source configs.

The [official tiny ONNX card](https://huggingface.co/PaddlePaddle/PP-OCRv6_tiny_det_onnx/blob/2ba1506c0380b8f0b03dd142459aac66d4421f6c/README.md)
identifies its license as Apache-2.0 and its detector as 0.43M parameters.
The public, ungated artifact is 1,780,590 bytes; its manifest entry pins the
download revision and SHA-256. The [matching upstream config](https://huggingface.co/PaddlePaddle/PP-OCRv6_tiny_det_onnx/raw/2ba1506c0380b8f0b03dd142459aac66d4421f6c/inference.yml)
uses BGR, `1/255` scaling, ImageNet mean/std, and DB postprocessing. Provision
it with `python models/prepare.py ppocr-v6-tiny`. Its public detector name is
integrated in the common wrapper and can serve either lane, including tiny fast
plus small/medium accurate combinations. See `bench/PORTABILITY.md` for the
verified raw runtime scope; the full scorecard decides quality.

The v5 conversions and their expected SHA-256 values come from
[RapidOCR v3.10.0's registry](https://github.com/RapidAI/RapidOCR/blob/v3.10.0/python/rapidocr/default_models.yaml).
Their upstream model cards identify the
[mobile detector](https://huggingface.co/PaddlePaddle/PP-OCRv5_mobile_det),
[server detector](https://huggingface.co/PaddlePaddle/PP-OCRv5_server_det), and
[English recognizer](https://huggingface.co/PaddlePaddle/en_PP-OCRv5_mobile_rec)
as Apache-2.0. Conversion changes representation; the upstream attribution
and license obligations remain. Copies of PaddleOCR's license, RapidOCR's
license, and RapidOCR's model notice are retained under `models/licenses/`.
The RapidOCR notice's explicitly enumerated bundled artifacts are v6 models;
the v5 provenance is established separately through its registry and the
upstream model cards.

## Alternatives checked

| Family | Primary-source finding | M1 choice |
| --- | --- | --- |
| DBNet++ | The [author's repository](https://github.com/MhLiao/DB) supplies trained models and describes a PyTorch/CUDA/deformable-convolution setup. Its root tree had no explicit license file at review time. | Defer a separate original-weight port; the selected PP detectors already use DB-style output decoding with a simpler ONNX deployment path. No permissive-license claim is made for the original DBNet++ weights. |
| CRAFT | [Official implementation](https://github.com/clovaai/CRAFT-pytorch) publishes character-region/affinity detection and pretrained weights. Its [license](https://github.com/clovaai/CRAFT-pytorch/blob/master/LICENSE) is MIT. | Credible architecture-diverse follow-up if the selected candidates miss disconnected or small characters. Its official deployment is PyTorch; adding and verifying an ONNX export is outside this first integration. |
| EAST | The [author's implementation](https://github.com/argman/EAST) uses a [GPL-3.0 license](https://github.com/argman/EAST/blob/master/LICENSE). | Excluded from the permissive shortlist. A different implementation does not establish the weight license. |
| Ultralytics YOLO | The [YOLO26 docs](https://docs.ultralytics.com/models/yolo26/) describe general object-detection checkpoints, and the [license page](https://www.ultralytics.com/legal) documents AGPL/commercial terms. | No vetted permissive, pretrained scene-text checkpoint was identified in this survey. A general COCO detector does not provide a scene-text detector without separate training. |

## Setup and offline execution

Use Python 3.11 in a virtual environment. The pinned ONNX Runtime
release provides macOS arm64 wheels for Python 3.11–3.14; the runtime also
works on Linux CPU for the integration smoke check. No CUDA or PyTorch
package is required.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-models.txt
.venv/bin/python models/prepare.py
.venv/bin/python models/prepare.py --verify-only
```

`prepare.py` is the only download entry point. It uses the standard library,
checks every artifact against `models/manifest.json`, and atomically places
verified files in gitignored `models/cache/`. Existing corrupt artifacts
produce a hard failure. To download just the pilot and its judge:

```sh
.venv/bin/python models/prepare.py ppocr-v5-mobile ppocr-v5-english-rec ppocr-v6-small ppocr-v6-medium
```

Pass `--cache-dir /path/to/cache` at preparation and `cache_dir` at inference
to relocate the cache. Construction verifies the model hash again, then
injects the explicit ONNX Runtime session into RapidOCR's preprocessing and
postprocessing. It bypasses RapidOCR's downloader. The recognizer requires
the pinned model's embedded character dictionary and does not fetch a
dictionary or font. Runtime errors propagate to the bench.

```python
from bench.onnx_detectors import create_detector, create_recognizer

detector = create_detector("ppocr-v6-small", {"threads": 2})
boxes = detector.detect(frame_bgr)
metadata = detector.metadata
detector.close()

reader = create_recognizer({"threads": 2, "text_score": 0.5})
rows = reader.read(frame_bgr)
reader.close()
```

Frames are uint8 BGR arrays with height and width at least 32. Boxes are
`[x0, y0, x1, y1]` in original-frame pixels, with top-left origin and exclusive
right/bottom edges. `detect` returns enclosing axis-aligned boxes; `detect_quads` preserves the
detector polygons for motion projection and rendering.
The reader returns `{"text": str, "confidence": float, "box": [...]}` rows.

CPU is the default provider. `provider="coreml"` requires the CoreML execution
provider and allows unsupported subgraphs to run on CPU. Both requested and
active providers are recorded; this is not a claim that the entire model
runs on the Neural Engine. Provider availability or activation failures
raise instead of silently relabelling a CPU run as CoreML. The
[ONNX Runtime CoreML documentation](https://onnxruntime.ai/docs/execution-providers/CoreML-ExecutionProvider.html)
describes provider configuration and unsupported-operator fallback.

## Parameters and judging limits

Shared options are `cache_dir`, `provider` (`cpu`/`coreml`), `threads` (default
2), `limit_side_len` (960), `limit_type` (`max`), `thresh` (0.3), `box_thresh`
(0.5), `unclip_ratio` (1.6), `use_dilation` (true), `max_candidates` (1000), and
`score_mode` (`fast`). These common postprocessing defaults are the bench
starting point, rather than each upstream model's tuned defaults. Record
every override and tune only against the tune split. The manifest retains
the upstream postprocessing settings for comparison.

All detector artifacts use their official BGR/ImageNet mean and standard
deviation from the linked `inference.yml` files. This is explicit because
RapidOCR 3.10.0's global config uses a different normalization default.

The reader adds `detector_name` (default `ppocr-v5-mobile`) and `text_score`
(0.5). It detects text independently of Apple Vision, rectifies each crop,
then runs the pinned PP-OCRv5 English-mobile CTC recognizer. It is suitable
as a non-Apple readability judge for Vision. It shares the PP-OCR family
with the PP candidates, so PP detector results also need an independent
family's judge. Its prepass can miss text, and its English-focused dictionary
limits what it can demonstrate; a missing OCR result is not proof of masking.

`requirements-models.txt` pins all 20 resolved runtime packages. The package
license inventory and copied notices are in `models/licenses/dependencies.json`
and `models/licenses/dependencies/`. The inventory records the Linux CPython
3.11 wheels used for this smoke check; native-wheel bundled components may
differ on macOS. Model weights are Apache-2.0; the dependency stack also
contains MPL-2.0 packages and native third-party notices. Review those notices
when redistributing binaries rather than describing the whole stack as
uniformly Apache/MIT.

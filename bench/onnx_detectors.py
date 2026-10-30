"""Offline PP-OCR detectors and a non-Apple OCR reader for the video bench.

Frames use OpenCV's uint8 BGR convention. Returned boxes are axis-aligned,
top-left-origin pixel coordinates, with exclusive right and bottom edges.
"""

from importlib.metadata import version
from bench.independence import candidate_metadata

import numpy as np
import onnxruntime as ort
from omegaconf import OmegaConf
from rapidocr.ch_ppocr_det import TextDetector
from rapidocr.ch_ppocr_rec import TextRecInput, TextRecognizer
from rapidocr.utils.process_img import get_rotate_crop_image
from rapidocr.utils.typings import EngineType

from models.prepare import DEFAULT_CACHE, verified_path


DETECTOR_NAMES = (
    "ppocr-v5-mobile",
    "ppocr-v5-server",
    "ppocr-v6-small",
    "ppocr-v6-tiny",
    "ppocr-v6-medium",
)
COMMON_OPTIONS = {
    "cache_dir", "provider", "threads", "limit_side_len", "limit_type", "thresh",
    "box_thresh", "unclip_ratio", "use_dilation", "max_candidates", "score_mode", "static_shape",
}


def _validate_options(options, extra=()):
    unknown = set(options) - COMMON_OPTIONS - set(extra)
    if unknown:
        raise ValueError(f"Unknown OCR options: {', '.join(sorted(unknown))}")


def _frame(frame):
    if not isinstance(frame, np.ndarray) or frame.dtype != np.uint8:
        raise TypeError("frame_bgr must be a uint8 numpy array")
    if frame.ndim != 3 or frame.shape[2] != 3 or min(frame.shape[:2]) < 32:
        raise ValueError("frame_bgr must have shape H×W×3 with both sides at least 32 pixels")
    return np.ascontiguousarray(frame)


def _session(name, options, *, user_compute_stream=None):
    path, artifact = verified_path(name, options.get("cache_dir", DEFAULT_CACHE))
    static_metadata=None
    if options.get('static_shape') and artifact['task']=='det':
        from bench.static_model import prepare_static
        path,static_metadata=prepare_static(path,artifact['sha256'],*options['static_shape'],options.get('cache_dir',DEFAULT_CACHE))
    provider = options.get("provider", "cpu")
    if provider not in {"cpu", "coreml", "cuda"}:
        raise ValueError("provider must be 'cpu', 'coreml', or 'cuda'")
    requested={"cpu":"CPUExecutionProvider","coreml":"CoreMLExecutionProvider","cuda":"CUDAExecutionProvider"}[provider]
    if requested not in ort.get_available_providers():
        raise RuntimeError(f"Requested {requested}; available: {ort.get_available_providers()}")
    threads = options.get("threads", 2)
    if isinstance(threads, bool) or not isinstance(threads, int) or threads < 1:
        raise ValueError("threads must be a positive integer")
    ort.disable_telemetry_events()
    config = ort.SessionOptions()
    config.intra_op_num_threads = threads
    config.inter_op_num_threads = 1
    config.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    config.enable_cpu_mem_arena = False
    providers = [requested]
    if provider == "coreml":
        # Unsupported CoreML operators execute on CPU; the scorecard records this.
        providers = [
            (requested, {"ModelFormat": "MLProgram", "MLComputeUnits": "ALL",
                         "RequireStaticInputShapes":"1" if static_metadata else "0",
                         "ModelCacheDirectory":str(DEFAULT_CACHE/'coreml-compiled')}),
            "CPUExecutionProvider",
        ]
    if provider=='cuda':
        providers=[('CUDAExecutionProvider',{'gpu_mem_limit':2*1024**3,'arena_extend_strategy':'kSameAsRequested',
                   'cudnn_conv_algo_search':'HEURISTIC','cudnn_conv_use_max_workspace':'0','do_copy_in_default_stream':'1'}),
                   'CPUExecutionProvider']
    if user_compute_stream is not None:
        if provider != 'cuda' or type(user_compute_stream) is not int or user_compute_stream <= 0:
            raise ValueError('Explicit user compute stream requires CUDA and a nonzero stream pointer')
        providers[0][1]['user_compute_stream'] = str(user_compute_stream)
    session = ort.InferenceSession(str(path), sess_options=config, providers=providers)
    session.disable_fallback()
    if user_compute_stream is not None:
        actual = session.get_provider_options().get('CUDAExecutionProvider', {})
        if (actual.get('has_user_compute_stream') != '1'
                or int(actual.get('user_compute_stream', '0')) != user_compute_stream):
            raise RuntimeError('ORT did not verify the explicit CUDA user compute stream')
    if requested not in session.get_providers():
        raise RuntimeError(f"ONNX Runtime did not activate requested provider {requested}")
    # Provider failure must not turn a measured CoreML run into an unlabelled CPU run.
    session.disable_fallback()
    metadata = {
        **candidate_metadata(name), "name": name,
        "static_artifact":static_metadata,
        "model_path": str(path),
        "sha256": artifact["sha256"],
        "license": artifact["license"],
        "license_source": artifact["license_source"],
        "source": artifact["source"],
        "download_url": artifact["url"],
        "execution_provider": requested,
        "active_execution_providers": session.get_providers(),
        "cpu_operator_partition_fallback_allowed":provider in {"coreml","cuda"},
        "threads": threads,
        "onnxruntime_version": ort.__version__,
        "rapidocr_version": version("rapidocr"),
    }
    if user_compute_stream is not None:
        metadata['experimental_user_stream'] = session.get_provider_options()['CUDAExecutionProvider']
    return session, metadata, artifact


def _bounds(polygon, height, width):
    x0 = max(0, int(np.floor(polygon[:, 0].min())))
    y0 = max(0, int(np.floor(polygon[:, 1].min())))
    x1 = min(width, int(np.ceil(polygon[:, 0].max())) + 1)
    y1 = min(height, int(np.ceil(polygon[:, 1].max())) + 1)
    return [x0, y0, x1, y1]


class PPOCRDetector:
    def __init__(self, name, options, *, session_factory=None):
        session, self.metadata, artifact = (session_factory or _session)(name, options)
        params = {
            "limit_side_len": options.get("limit_side_len", 960),
            "limit_type": options.get("limit_type", "max"),
            "mean": artifact["preprocess"]["mean"],
            "std": artifact["preprocess"]["std"],
            "thresh": options.get("thresh", 0.3),
            "box_thresh": options.get("box_thresh", 0.5),
            "max_candidates": options.get("max_candidates", 1000),
            "unclip_ratio": options.get("unclip_ratio", 1.6),
            "use_dilation": options.get("use_dilation", True),
            "score_mode": options.get("score_mode", "fast"),
        }
        if params["limit_type"] not in {"min", "max"}:
            raise ValueError("limit_type must be 'min' or 'max'")
        if not isinstance(params["limit_side_len"], int) or params["limit_side_len"] < 32:
            raise ValueError("limit_side_len must be an integer at least 32")
        for key in ("thresh", "box_thresh"):
            if not 0 <= params[key] <= 1:
                raise ValueError(f"{key} must be between 0 and 1")
        if params["unclip_ratio"] <= 0 or params["max_candidates"] < 1:
            raise ValueError("unclip_ratio and max_candidates must be positive")
        if params["score_mode"] not in {"fast", "slow"}:
            raise ValueError("score_mode must be 'fast' or 'slow'")
        self.metadata["parameters"] = params
        cfg = OmegaConf.create(params, flags={"allow_objects": True})
        cfg.engine_type = EngineType.ONNXRUNTIME
        # Injecting a verified session bypasses RapidOCR's model-download resolver.
        cfg.session = session
        self._detector = TextDetector(cfg)

    def _polygons(self, frame):
        if self._detector is None:
            raise RuntimeError("Detector is closed")
        output = self._detector(frame)
        return [] if output.boxes is None else output.boxes

    def detect(self, frame_bgr):
        frame = _frame(frame_bgr)
        height, width = frame.shape[:2]
        return [_bounds(polygon, height, width) for polygon in self._polygons(frame)]

    def detect_quads(self,frame_bgr):
        frame=_frame(frame_bgr)
        return [polygon.astype(float).tolist() for polygon in self._polygons(frame)]

    def close(self):
        self._detector = None


class PPOCRRecognizer:
    def __init__(self, options):
        self._text_score = options.get("text_score", 0.5)
        if not 0 <= self._text_score <= 1:
            raise ValueError("text_score must be between 0 and 1")
        detector_options = {k: v for k, v in options.items() if k in COMMON_OPTIONS}
        self._detector = create_detector(options.get("detector_name", "ppocr-v5-mobile"), detector_options)
        try:
            session, rec_metadata, _ = _session("ppocr-v5-english-rec", options)
            if "character" not in session.get_modelmeta().custom_metadata_map:
                raise RuntimeError("Pinned recognizer is missing its embedded character dictionary")
            cfg = OmegaConf.create({
                "engine_type": EngineType.ONNXRUNTIME,
                "lang_type": "en",
                "rec_batch_num": 6,
                "rec_img_shape": [3, 48, 320],
                "rec_keys_path": None,
                "font_path": None,
            }, flags={"allow_objects": True})
            cfg.session = session
            self._recognizer = TextRecognizer(cfg)
        except Exception:
            self._detector.close()
            raise
        self.metadata = {
            "name": "ppocr-v5-english",
            "detector": self._detector.metadata,
            "recognizer": rec_metadata,
            "text_score": self._text_score,
            "language": "English and Latin characters in the model's embedded dictionary",
            "independence": "Non-Apple engine; shares PP-OCR family with PP-OCR detector candidates",
        }

    def read(self, frame_bgr):
        if self._recognizer is None:
            raise RuntimeError("Recognizer is closed")
        frame = _frame(frame_bgr)
        polygons = self._detector._polygons(frame)
        if len(polygons) == 0:
            return []
        crops = [get_rotate_crop_image(frame, polygon.astype(np.float32)) for polygon in polygons]
        output = self._recognizer(TextRecInput(img=crops))
        height, width = frame.shape[:2]
        return [
            {"text": text, "confidence": float(score), "box": _bounds(polygon, height, width)}
            for polygon, text, score in zip(polygons, output.txts, output.scores, strict=True)
            if text.strip() and score >= self._text_score
        ]

    def close(self):
        self._recognizer = None
        self._detector.close()


def create_detector(name: str, options: dict | None = None):
    if name not in DETECTOR_NAMES:
        raise ValueError(f"Unknown detector {name!r}; choose one of {DETECTOR_NAMES}")
    options = dict(options or {})
    _validate_options(options)
    return PPOCRDetector(name, options)


def create_recognizer(options: dict | None = None):
    options = dict(options or {})
    _validate_options(options, extra=("detector_name", "text_score"))
    return PPOCRRecognizer(options)

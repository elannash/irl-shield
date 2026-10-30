"""FAST through OnnxTR at the existing BGR -> pixel-quad detector seam."""
from importlib.metadata import version
from pathlib import Path
import math

import numpy as np

from models.prepare import verified_path


PROVIDERS = {'cpu': 'CPUExecutionProvider', 'cuda': 'CUDAExecutionProvider',
             'coreml': 'CoreMLExecutionProvider'}


def provider_config(provider, available, cache_dir):
    if provider not in PROVIDERS:
        raise ValueError('provider must be cpu, cuda or coreml')
    requested = PROVIDERS[provider]
    if requested not in available:
        raise RuntimeError(f'Requested {requested}; available: {available}')
    if provider == 'coreml':
        return [(requested, {'ModelFormat': 'MLProgram', 'MLComputeUnits': 'ALL',
                             'RequireStaticInputShapes': '1',
                             'ModelCacheDirectory': str(Path(cache_dir) / 'fast-coreml')}),
                'CPUExecutionProvider']
    if provider == 'cuda':
        return [(requested, {'gpu_mem_limit': 2 * 1024**3,
                             'arena_extend_strategy': 'kSameAsRequested',
                             'cudnn_conv_algo_search': 'HEURISTIC',
                             'cudnn_conv_use_max_workspace': '0',
                             'do_copy_in_default_stream': '1'}), 'CPUExecutionProvider']
    return [requested]


def _load_predictor(*, cache_dir, provider='cpu', side=1024, bin_thresh=.1, box_thresh=.1,
                    profile_prefix=None):
    import cv2
    import onnxruntime as ort
    from onnxtr.models.detection.models.fast import FAST
    from onnxtr.models import detection_predictor
    from onnxtr.models.engine import EngineConfig
    from bench.fast_static import prepare_static

    if isinstance(side, bool) or not isinstance(side, int) or side < 32 or side % 32:
        raise ValueError('side must be a positive multiple of 32')
    if any(not math.isfinite(x) or not 0 <= x <= 1 for x in (bin_thresh, box_thresh)):
        raise ValueError('FAST thresholds must be finite and between zero and one')
    providers = provider_config(provider, ort.get_available_providers(), cache_dir)
    path, artifact = verified_path('fast-tiny', cache_dir)
    path, static = prepare_static(path, artifact['sha256'], side, cache_dir)
    cv2.setNumThreads(2)
    ort.disable_telemetry_events()
    config = ort.SessionOptions()
    config.intra_op_num_threads = 2
    config.inter_op_num_threads = 1
    config.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    config.enable_cpu_mem_arena = False
    if profile_prefix is not None:
        config.enable_profiling = True
        config.profile_file_prefix = str(profile_prefix)
    model = FAST(str(path), engine_cfg=EngineConfig(providers=providers, session_options=config),
                 cfg={'input_shape': (3, side, side), 'mean': tuple(artifact['preprocess']['mean']),
                      'std': tuple(artifact['preprocess']['std'])},
                 assume_straight_pages=False, bin_thresh=bin_thresh, box_thresh=box_thresh)
    model.runtime.disable_fallback()
    if PROVIDERS[provider] not in model.runtime.get_providers():
        raise RuntimeError(f'ONNX Runtime did not activate requested provider {PROVIDERS[provider]}')
    predictor = detection_predictor(model, assume_straight_pages=False, batch_size=1,
                                    preserve_aspect_ratio=True, symmetric_pad=True)
    metadata = {'name': 'fast-tiny', 'model_path': str(path), 'sha256': artifact['sha256'],
                'source': artifact['source'], 'license': artifact['license'],
                'license_source': artifact['license_source'], 'static_artifact': static,
                'onnxtr_version': version('onnxtr'), 'onnxruntime_version': ort.__version__,
                'requested_provider': PROVIDERS[provider],
                'active_execution_providers': model.runtime.get_providers(),
                'provider_options': model.runtime.get_provider_options(),
                'cpu_operator_partition_fallback_allowed': provider != 'cpu',
                'threads': 2, 'side': side, 'bin_thresh': bin_thresh, 'box_thresh': box_thresh,
                'rotated_quads': True, 'preprocess': artifact['preprocess']}
    return predictor, metadata


class FastDetector:
    def __init__(self, **options):
        self._predictor, self.metadata = _load_predictor(**options)

    def detect_quads(self, frame_bgr):
        if self._predictor is None:
            raise RuntimeError("FAST detector is closed")
        if not isinstance(frame_bgr, np.ndarray) or frame_bgr.dtype != np.uint8:
            raise TypeError("frame_bgr must be a uint8 numpy array")
        if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3 or min(frame_bgr.shape[:2]) < 32:
            raise ValueError("frame_bgr must have shape H×W×3, sides at least 32")
        height, width = frame_bgr.shape[:2]
        predictions = self._predictor([np.ascontiguousarray(frame_bgr[..., ::-1])])
        if len(predictions) != 1:
            raise ValueError("FAST must return exactly one prediction page")
        polygons = np.asarray(predictions[0], dtype=float)
        if polygons.size == 0:
            return []
        if polygons.ndim != 3 or polygons.shape[1:] != (5, 2) or not np.isfinite(polygons).all():
            raise ValueError("FAST returned invalid normalized polygons")
        points = np.clip(polygons[:, :4], 0, 1) * [width, height]
        return points.tolist()

    def end_profile(self):
        if self._predictor is None:
            raise RuntimeError('FAST detector is closed')
        return self._predictor.model.runtime.end_profiling()

    def close(self):
        self._predictor = None

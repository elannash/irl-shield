"""CPU-only OpenVINO adapter for the existing transport-free detector seam.

OpenVINO: Apache-2.0, https://github.com/openvinotoolkit/openvino/blob/2026.0.0/LICENSE
Uses existing Apache-2.0 RapidOCR preprocessing/postprocessing and hash-pinned
Apache-2.0 Paddle ONNX weights from models/manifest.json. No downloads at inference.
"""
from importlib.metadata import version

import numpy as np
from rapidocr.ch_ppocr_det import TextDetector
from rapidocr.ch_ppocr_det.utils import DBPostProcess, DetPreProcess

from bench.onnx_detectors import _bounds, _frame
from bench.static_model import prepare_static
from models.prepare import verified_path, load_manifest


def preprocess_for(name, side):
    params = load_manifest()['artifacts'][name]['preprocess']
    return DetPreProcess(side, 'max', params['mean'], params['std'])


class OpenVINODetector:
    def __init__(self, name, *, cache_dir, static_shape, precision='fp32', threads=2,
                 limit_side_len=960, thresh=.3, box_thresh=.5, unclip_ratio=1.6):
        import openvino as ov

        if name not in ('ppocr-v6-tiny', 'ppocr-v6-small'):
            raise ValueError('OpenVINO comparison supports PP-OCRv6 tiny/small only')
        if precision not in ('fp32', 'fp16', 'bf16'):
            raise ValueError('precision must be fp32, fp16, or bf16; quantization is not implicit')
        if isinstance(threads, bool) or threads not in (1, 2):
            raise ValueError('threads must be 1 or 2')
        if not 0 <= thresh <= 1 or not 0 <= box_thresh <= 1 or unclip_ratio <= 0:
            raise ValueError('Invalid postprocessing thresholds')
        path, artifact = verified_path(name, cache_dir)
        path, static = prepare_static(path, artifact['sha256'], *static_shape, cache_dir)
        self.preprocess = preprocess_for(name, limit_side_len)
        self.postprocess = DBPostProcess(thresh=thresh, box_thresh=box_thresh, max_candidates=1000,
                                        unclip_ratio=unclip_ratio, use_dilation=True, score_mode='fast')
        core = ov.Core()
        properties = {'PERFORMANCE_HINT': 'LATENCY', 'INFERENCE_NUM_THREADS': threads,
                      'NUM_STREAMS': 1, 'INFERENCE_PRECISION_HINT':
                      {'fp32': ov.Type.f32, 'fp16': ov.Type.f16, 'bf16': ov.Type.bf16}[precision]}
        self.compiled = core.compile_model(str(path), 'CPU', properties)
        self.request = self.compiled.create_infer_request()
        self.shape = tuple(static['input_shape'])
        self.metadata = {
            'name': name, 'runtime': 'OpenVINO', 'openvino_version': ov.__version__,
            'rapidocr_version': version('rapidocr'), 'execution_provider': 'CPU',
            'execution_devices': list(self.compiled.get_property('EXECUTION_DEVICES')),
            'device_full_name': core.get_property('CPU', 'FULL_DEVICE_NAME'),
            'supported_precision_capabilities': list(core.get_property('CPU', 'OPTIMIZATION_CAPABILITIES')),
            'precision_requested': precision,
            'precision_hint_effective': str(self.compiled.get_property('INFERENCE_PRECISION_HINT')),
            'performance_hint': str(self.compiled.get_property('PERFORMANCE_HINT')),
            'threads': self.compiled.get_property('INFERENCE_NUM_THREADS'),
            'streams': self.compiled.get_property('NUM_STREAMS'), 'batch_size': 1,
            'source': artifact['source'], 'sha256': artifact['sha256'], 'model_path': str(path),
            'static_artifact': static, 'license': artifact['license'], 'license_source': artifact['license_source'],
            'runtime_license': 'Apache-2.0',
            'runtime_license_source': 'https://github.com/openvinotoolkit/openvino/blob/2026.0.0/LICENSE',
            'parameters': {'limit_side_len': limit_side_len, 'limit_type': 'max',
                           'mean': artifact['preprocess']['mean'], 'std': artifact['preprocess']['std'],
                           'thresh': thresh, 'box_thresh': box_thresh, 'max_candidates': 1000,
                           'unclip_ratio': unclip_ratio, 'use_dilation': True, 'score_mode': 'fast'},
        }
        if self.metadata['execution_devices'] != ['CPU']:
            self.close()
            raise RuntimeError('CPU-only OpenVINO execution was not activated')

    def infer(self, tensor):
        """Synchronous batch1 map inference, also used by the parity/timing CLI."""
        if self.request is None:
            raise RuntimeError('Detector is closed')
        if tensor.dtype != np.float32 or tensor.shape != self.shape:
            raise ValueError(f'Expected float32 tensor {self.shape}, got {tensor.dtype} {tensor.shape}')
        output = self.request.infer({0: np.ascontiguousarray(tensor)})
        return output[self.compiled.output(0)].copy()

    def boxes_from_map(self, prediction, frame_shape):
        boxes, _ = self.postprocess(prediction, tuple(frame_shape[:2]))
        return TextDetector.sorted_boxes(boxes) if len(boxes) else []

    def detect_quads(self, frame_bgr):
        frame = _frame(frame_bgr)
        tensor = self.preprocess(frame)
        if tensor is None:
            raise RuntimeError('Preprocessing did not produce a tensor')
        return [box.astype(float).tolist() for box in self.boxes_from_map(self.infer(tensor), frame.shape)]

    def detect(self, frame_bgr):
        frame = _frame(frame_bgr)
        return [_bounds(np.asarray(quad), *frame.shape[:2]) for quad in self.detect_quads(frame)]

    def close(self):
        self.request = None
        self.compiled = None

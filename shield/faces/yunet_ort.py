"""Experimental FP32 YuNet ORT arm; exact same MIT weights as OpenCV.

Decode follows OpenCV 4.11.0 face_detect.cpp (Apache-2.0); independent NumPy
implementation. See fixtures/faces/licenses and docs/FACES.md for source pins.
CUDA construction is opt-in and must run only under conductor's EX queue.
"""
from pathlib import Path
import json
import time
import cv2
import numpy as np
from .detector import model_path
from .policy import Face, FaceBatch, FaceTracker

OUTPUT_NAMES = tuple(f'{kind}_{stride}' for kind in ('cls', 'obj', 'bbox', 'kps') for stride in (8, 16, 32))


def prepare(frame_bgr):
    """Top-left BGR letterbox into exact graph shape. No mean/scale/RGB swap."""
    if frame_bgr.dtype != np.uint8 or frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3 or min(frame_bgr.shape[:2]) < 1:
        raise ValueError('expected nonempty uint8 BGR frame')
    h, w = frame_bgr.shape[:2]
    scale = min(1., 640 / max(h, w))
    rw, rh = max(1, round(w * scale)), max(1, round(h * scale))
    small = cv2.resize(frame_bgr, (rw, rh)) if (rh, rw) != (h, w) else frame_bgr
    padded = np.zeros((640, 640, 3), np.uint8)
    padded[:rh, :rw] = small
    return padded, (w / rw, h / rh)


def decode(outputs, threshold=0.6):
    """Return Nx15 xywh / five landmarks / score, before source mapping.

    Integer-truncated boxes for NMS intentionally match OpenCV 4.11, including
    its special one-candidate branch. Scores are sqrt(clamp(cls)*clamp(obj)).
    """
    rows = []
    for stride in (8, 16, 32):
        count = (640 // stride) ** 2
        cls = np.asarray(outputs[f'cls_{stride}'], dtype=np.float32).reshape(count)
        obj = np.asarray(outputs[f'obj_{stride}'], dtype=np.float32).reshape(count)
        boxes = np.asarray(outputs[f'bbox_{stride}'], dtype=np.float32).reshape(count, 4)
        points = np.asarray(outputs[f'kps_{stride}'], dtype=np.float32).reshape(count, 10)
        if not all(np.isfinite(a).all() for a in (cls, obj, boxes, points)):
            raise ValueError('non-finite YuNet graph output')
        scores = np.sqrt(np.clip(cls, 0, 1) * np.clip(obj, 0, 1))
        indices = np.flatnonzero(scores >= threshold)
        if not len(indices):
            continue
        selected = boxes[indices]
        grid = np.column_stack((indices % (640 // stride), indices // (640 // stride))).astype(np.float32)
        centers = (grid + selected[:, :2]) * stride
        with np.errstate(over='raise', invalid='raise'):
            sizes = np.exp(selected[:, 2:]) * stride
        landmarks = (points[indices].reshape(-1, 5, 2) + grid[:, None, :]) * stride
        rows.append(np.column_stack((centers - sizes / 2, sizes, landmarks.reshape(-1, 10), scores[indices])))
    if not rows:
        return np.empty((0, 15), np.float32)
    result = np.concatenate(rows).astype(np.float32)
    if not np.isfinite(result).all():
        raise ValueError('invalid decoded YuNet geometry')
    if len(result) > 1:
        keep = cv2.dnn.NMSBoxes(result[:, :4].astype(int).tolist(), result[:, 14].tolist(), threshold, 0.3, top_k=5000)
        result = result[np.asarray(keep, dtype=int).reshape(-1)]
    return result


def source_faces(rows, shape, scales):
    h, w = shape
    sx, sy = scales
    faces = []
    for row in rows:
        x, y, bw, bh = (float(v) for v in row[:4])
        # Ignore graph predictions wholly inside added padding, not visible faces.
        if x * sx >= w or y * sy >= h or (x + bw) * sx <= 0 or (y + bh) * sy <= 0:
            continue
        box = (max(0., x * sx), max(0., y * sy), min(float(w), (x + bw) * sx), min(float(h), (y + bh) * sy))
        faces.append(Face(box, float(row[-1])))
    return tuple(faces)


def profile_placement(path, *, expect_cuda):
    events = json.loads(Path(path).read_text())
    nodes = [event for event in events if event.get('cat') == 'Node' and event.get('name', '').endswith('_kernel_time')]
    providers = {}
    unknown = []
    for event in nodes:
        provider = event.get('args', {}).get('provider')
        if not provider:
            unknown.append(event.get('name'))
        else:
            providers.setdefault(provider, []).append({'name':event['name'], 'duration_us':event.get('dur'), 'op':event.get('args', {}).get('op_name')})
    cuda = providers.get('CUDAExecutionProvider', [])
    cpu = providers.get('CPUExecutionProvider', [])
    return {'profile_path':str(path), 'kernel_events':len(nodes), 'providers':providers,
            'cpu_fallback_events':cpu if expect_cuda else [], 'unknown_events':unknown,
            'placement_verified': bool(nodes) and not unknown and (bool(cuda) and not cpu if expect_cuda else set(providers) == {'CPUExecutionProvider'}),
            'gpu_kernel_ms_per_source_frame':None,
            'note':'ORT provider event durations identify placement; they are not CUDA device-event timings.'}


class YuNetORTDetector:
    family = 'YuNet'

    def __init__(self, *, provider='CUDAExecutionProvider', profile_prefix,
                 allow_cpu_fallback=False, user_compute_stream=None):
        import onnxruntime as ort
        if provider not in ('CUDAExecutionProvider', 'CPUExecutionProvider'):
            raise ValueError('explicit CUDA or CPU provider required')
        if provider not in ort.get_available_providers():
            raise RuntimeError('requested YuNet provider unavailable: ' + provider)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.enable_profiling = True
        options.profile_file_prefix = str(profile_prefix)
        if provider == 'CUDAExecutionProvider' and not allow_cpu_fallback:
            options.add_session_config_entry('session.disable_cpu_ep_fallback', '1')
        provider_options = {'device_id': '0', 'use_tf32': '0', 'cudnn_conv_algo_search': 'DEFAULT'} if provider == 'CUDAExecutionProvider' else {}
        if user_compute_stream is not None:
            if provider != 'CUDAExecutionProvider':
                raise ValueError('CUDA stream requires CUDA provider')
            provider_options['user_compute_stream'] = str(user_compute_stream)
        providers = [(provider, provider_options)]
        if allow_cpu_fallback and provider == 'CUDAExecutionProvider':
            providers.append('CPUExecutionProvider')
        self.session = ort.InferenceSession(str(model_path('yunet-2023mar')), sess_options=options, providers=providers)
        self.session.disable_fallback()
        if provider not in self.session.get_providers():
            raise RuntimeError('YuNet provider initialization fell back: ' + repr(self.session.get_providers()))
        inputs = self.session.get_inputs()
        outputs = self.session.get_outputs()
        if len(inputs) != 1 or inputs[0].shape != [1, 3, 640, 640] or inputs[0].type != 'tensor(float)':
            raise ValueError('unexpected YuNet graph input schema')
        if {o.name for o in outputs} != set(OUTPUT_NAMES):
            raise ValueError('unexpected YuNet graph output schema')
        self.input_name = inputs[0].name
        self.provider = provider
        self.backend = 'ort-cuda-fp32' if provider == 'CUDAExecutionProvider' else 'ort-cpu-fp32'
        self.graph_schema = {'input':{'name':inputs[0].name,'shape':inputs[0].shape,'type':inputs[0].type},
                             'outputs':[{'name':o.name,'shape':o.shape,'type':o.type} for o in outputs]}
        self.tracker = FaceTracker()
        self.profile_path = None

    def infer_rows(self, frame_bgr):
        padded, scales = prepare(frame_bgr)
        tensor = np.ascontiguousarray(padded.transpose(2, 0, 1)[None], dtype=np.float32)
        return decode(self.infer_tensor(tensor)), scales

    def infer_tensor(self, tensor):
        arrays = self.session.run(list(OUTPUT_NAMES), {self.input_name:tensor})
        return dict(zip(OUTPUT_NAMES, arrays))

    def detect(self, frame_bgr, source_index, generation):
        if source_index < 0 or generation < 0:
            raise ValueError('invalid source metadata')
        shape = frame_bgr.shape[:2]
        try:
            rows, scales = self.infer_rows(frame_bgr)
            batch = FaceBatch(source_index, generation, shape, time.monotonic(), source_faces(rows, shape, scales))
        except Exception as error:
            # External runtime/device failures are coverage failures, never empty success.
            batch = FaceBatch(source_index, generation, shape, time.monotonic(), error=type(error).__name__)
        return self.tracker.assign(batch)

    def finish_profile(self):
        if self.profile_path is None:
            self.profile_path = self.session.end_profiling()
        return profile_placement(self.profile_path, expect_cuda=self.provider == 'CUDAExecutionProvider')

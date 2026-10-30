"""Pinned MIT YuNet adapter. OpenCV wheel execution is explicitly CPU-only."""
import hashlib
import json
from pathlib import Path
import time
import cv2
import numpy as np
from .policy import Face, FaceBatch, FaceTracker

ROOT = Path(__file__).resolve().parents[2]


def model_path(model_id, root=ROOT):
    root = Path(root)
    manifest = json.loads((root / 'models/faces-manifest.json').read_text())
    entry = next(m for m in manifest['models'] if m['id'] == model_id)
    path = root / 'models/cache/faces' / entry['filename']
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
        raise ValueError('face model hash mismatch: ' + model_id)
    return path


class YuNetDetector:
    family = 'YuNet'
    backend = 'opencv-dnn-cpu'

    def __init__(self, model=None, *, score_threshold=0.6, max_side=640):
        if not 0 < score_threshold < 1 or max_side < 128:
            raise ValueError('invalid YuNet configuration')
        cv2.setNumThreads(1)
        self.max_side = max_side
        self.net = cv2.FaceDetectorYN.create(str(model or model_path('yunet-2023mar')), '',
                    (320, 320), score_threshold, 0.3, 5000, cv2.dnn.DNN_BACKEND_OPENCV, cv2.dnn.DNN_TARGET_CPU)
        self.tracker = FaceTracker()

    def detect(self, frame_bgr, source_index, generation):
        if frame_bgr.dtype != np.uint8 or frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
            raise ValueError('expected uint8 BGR frame')
        height, width = frame_bgr.shape[:2]
        if min(height, width) < 1 or source_index < 0 or generation < 0:
            raise ValueError('invalid face source metadata')
        try:
            scale = min(1., self.max_side / max(height, width))
            small = cv2.resize(frame_bgr, (max(1, round(width * scale)), max(1, round(height * scale)))) if scale < 1 else frame_bgr
            sh, sw = small.shape[:2]
            self.net.setInputSize((sw, sh))
            _, rows = self.net.detect(small)
            faces = []
            if rows is not None:
                if not np.isfinite(rows).all():
                    raise ValueError('non-finite YuNet result')
                for row in rows:
                    x, y, w, h = (float(v) for v in row[:4])
                    box = (max(0., x * width / sw), max(0., y * height / sh),
                           min(float(width), (x + w) * width / sw), min(float(height), (y + h) * height / sh))
                    if box[2] <= box[0] or box[3] <= box[1]:
                        raise ValueError('degenerate YuNet result')
                    faces.append(Face(box, float(row[-1])))
            batch = FaceBatch(source_index, generation, (height, width), time.monotonic(), tuple(faces))
        except (cv2.error, ValueError) as error:
            batch = FaceBatch(source_index, generation, (height, width), time.monotonic(), error=type(error).__name__)
        return self.tracker.assign(batch)

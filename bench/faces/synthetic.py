"""Deterministic fictional adult placement. Natural backgrounds stay local."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import math
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Truth:
    person_id: str
    box: tuple[float, float, float, float]
    visible_fraction: float


def load_assets(root=ROOT):
    root = Path(root)
    manifest = json.loads((root / 'fixtures/faces/assets.json').read_text())
    assets = []
    for entry in manifest['assets']:
        path = root / entry['path']
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('synthetic face asset hash mismatch')
        image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if image is None or image.ndim != 3 or image.shape[2] != 4:
            raise ValueError('synthetic face asset requires BGRA alpha')
        assets.append((image, tuple(entry['face_box_xyxy'])))
    if len(assets) < 2:
        raise ValueError('two independent fictional adults required')
    return assets


def overlay(frame_bgr, index, assets, scenario='selfie-bystander'):
    if frame_bgr.dtype != np.uint8 or frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3 or index < 0:
        raise ValueError('invalid synthetic source')
    h, w = frame_bgr.shape[:2]
    # Fractions specify upper-body cutout heights and centers, not detector boxes.
    placements = {
        'selfie-bystander': ((0, 0.25, 1.25, 1.28), (1, 0.77, 0.70, 0.48)),
        'bystanders-only': ((0, 0.25, 0.66, 0.32), (1, 0.75, 0.69, 0.40)),
        'equal-large': ((0, 0.25, 1.0, 0.94), (1, 0.75, 1.0, 0.94)),
        'edge-entry': ((0, -0.12 + (index % 60) / 120, 0.82, 0.54), (1, 0.73, 0.72, 0.30)),
        'no-people': (),
    }
    if scenario not in placements:
        raise ValueError('unknown synthetic people scenario')
    result = frame_bgr.copy()
    truth = []
    for ai, cx, bottom, fraction in placements[scenario]:
        image, face = assets[ai]
        scale = h * fraction / image.shape[0]
        rh, rw = max(1, round(image.shape[0] * scale)), max(1, round(image.shape[1] * scale))
        cutout = cv2.resize(image, (rw, rh), interpolation=cv2.INTER_AREA)
        left = round(cx * w - rw / 2 + 0.01 * w * math.sin(index / 12 + ai))
        top = round(bottom * h - rh)
        x0, y0, x1, y1 = max(0, left), max(0, top), min(w, left + rw), min(h, top + rh)
        if x1 > x0 and y1 > y0:
            piece = cutout[y0 - top:y1 - top, x0 - left:x1 - left]
            alpha = piece[:, :, 3:4].astype(np.float32) / 255.
            result[y0:y1, x0:x1] = np.rint(piece[:, :, :3] * alpha + result[y0:y1, x0:x1] * (1 - alpha)).astype(np.uint8)
        fx0, fy0, fx1, fy1 = face
        box = (left + fx0 * rw / image.shape[1], top + fy0 * rh / image.shape[0],
               left + fx1 * rw / image.shape[1], top + fy1 * rh / image.shape[0])
        clipped = (max(0., box[0]), max(0., box[1]), min(float(w), box[2]), min(float(h), box[3]))
        area = max(0., clipped[2] - clipped[0]) * max(0., clipped[3] - clipped[1])
        full = (box[2] - box[0]) * (box[3] - box[1])
        if area:
            truth.append(Truth(f'adult-{ai}', clipped, area / full))
    return result, tuple(truth)

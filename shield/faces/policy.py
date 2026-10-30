"""Exact-source face coverage, geometric tracking and a one-face selfie heuristic.

No identity or biometric embeddings are computed. Tracks describe overlap only.
A fresh empty detection is evidence of detector completion, never proof of absence.
"""
from dataclasses import dataclass, replace
import math
import numpy as np


@dataclass(frozen=True)
class Face:
    box: tuple[float, float, float, float]  # Half-open source-pixel xyxy.
    confidence: float
    track_id: str | None = None

    def __post_init__(self):
        if (len(self.box) != 4 or not all(math.isfinite(v) for v in self.box)
                or self.box[2] <= self.box[0] or self.box[3] <= self.box[1]
                or not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1):
            raise ValueError('invalid face geometry or confidence')


@dataclass(frozen=True)
class FaceBatch:
    source_index: int
    generation: int
    shape: tuple[int, int]  # Height, width of the detected source frame.
    completed_at: float  # Same monotonic clock as the caller's now.
    faces: tuple[Face, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class FaceCoverage:
    ok: bool
    reason: str
    source_index: int
    generation: int


@dataclass(frozen=True)
class FacePlan:
    coverage: FaceCoverage
    faces: tuple[Face, ...]
    masked_track_ids: tuple[str, ...]
    exempt_track_id: str | None
    mask: np.ndarray
    area_pixels: int
    area_fraction: float
    requires_hold: bool


def iou(a, b):
    intersection = max(0., min(a[2], b[2]) - max(a[0], b[0])) * max(0., min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union if union else 0.


class FaceTracker:
    """One-to-one IoU association; IDs reset across stream generations.

    A new id after a miss is preferable to claiming identity continuity. Tracks
    never extrapolate coverage, and must not be used as biometric identifiers.
    """
    def __init__(self, min_iou=0.25):
        if not 0 < min_iou <= 1:
            raise ValueError('min_iou must be in (0,1]')
        self.min_iou = min_iou
        self.generation = -1
        self.index = -1
        self.serial = 0
        self.previous = ()

    def assign(self, batch: FaceBatch) -> FaceBatch:
        if batch.generation < self.generation:
            raise ValueError('face generation moved backwards')
        if batch.generation != self.generation:
            self.previous = ()
            self.serial = 0
            self.index = -1
            self.generation = batch.generation
        if batch.source_index <= self.index:
            raise ValueError('face source index did not advance')
        self.index = batch.source_index
        if batch.error:
            self.previous = ()
            return replace(batch, faces=())
        pairs = sorted(((iou(old.box, new.box), oi, ni)
                        for oi, old in enumerate(self.previous)
                        for ni, new in enumerate(batch.faces)), reverse=True)
        used_old, ids = set(), {}
        for overlap, oi, ni in pairs:
            if overlap >= self.min_iou and oi not in used_old and ni not in ids:
                used_old.add(oi)
                ids[ni] = self.previous[oi].track_id
        assigned = []
        for ni, face in enumerate(batch.faces):
            if ni not in ids:
                self.serial += 1
                ids[ni] = f'face:{batch.generation}:{self.serial}'
            assigned.append(replace(face, track_id=ids[ni]))
        self.previous = tuple(assigned)
        return replace(batch, faces=self.previous)


class FacePolicy:
    def __init__(self, mode='bystanders', selfie_min_fraction=0.08,
                 padding=0.25, max_result_age_seconds=0.5):
        if mode not in ('bystanders', 'all', 'off'):
            raise ValueError('face mode must be bystanders, all or off')
        if not math.isfinite(selfie_min_fraction) or not 0 < selfie_min_fraction <= 1:
            raise ValueError('selfie_min_fraction must be in (0,1]')
        if not math.isfinite(padding) or not 0 <= padding <= 1:
            raise ValueError('padding must be in [0,1]')
        if not math.isfinite(max_result_age_seconds) or max_result_age_seconds <= 0:
            raise ValueError('max_result_age_seconds must be positive')
        self.mode = mode
        self.selfie_min_fraction = selfie_min_fraction
        self.padding = padding
        self.max_result_age_seconds = max_result_age_seconds

    def plan(self, shape, source_index, generation, batch: FaceBatch | None, *, now):
        height, width = shape
        if min(shape) < 1 or source_index < 0 or generation < 0 or not math.isfinite(now):
            raise ValueError('invalid presentation frame metadata')
        mask = np.zeros(shape, np.uint8)
        reason = 'fresh'
        if self.mode == 'off':
            return FacePlan(FaceCoverage(True, 'off', source_index, generation), (), (), None, mask, 0, 0., False)
        if batch is None:
            reason = 'missing'
        elif batch.error:
            reason = 'detector-error'
        elif batch.generation != generation:
            reason = 'generation-mismatch'
        elif batch.source_index != source_index:
            reason = 'source-mismatch'
        elif batch.shape != tuple(shape):
            reason = 'shape-mismatch'
        elif not math.isfinite(batch.completed_at) or not 0 <= now - batch.completed_at <= self.max_result_age_seconds:
            reason = 'stalled'
        elif any(face.track_id is None for face in batch.faces) or len({f.track_id for f in batch.faces}) != len(batch.faces):
            reason = 'untracked'
        elif any(not (0 <= f.box[0] < f.box[2] <= width and 0 <= f.box[1] < f.box[3] <= height) for f in batch.faces):
            reason = 'invalid-geometry'
        if reason != 'fresh':
            mask[:] = 255
            return FacePlan(FaceCoverage(False, reason, source_index, generation), (), (), None,
                            mask, height * width, 1., True)
        faces = batch.faces
        exempt = None
        if faces and self.mode == 'bystanders':
            largest = max(range(len(faces)), key=lambda n: (faces[n].box[2] - faces[n].box[0]) * (faces[n].box[3] - faces[n].box[1]))
            x0, y0, x1, y1 = faces[largest].box
            if (x1 - x0) * (y1 - y0) > self.selfie_min_fraction * height * width:
                exempt = largest
        masked = []
        for n, face in enumerate(faces):
            if n == exempt:
                continue
            x0, y0, x1, y1 = face.box
            dx, dy = (x1 - x0) * self.padding, (y1 - y0) * self.padding
            left, top = max(0, math.floor(x0 - dx)), max(0, math.floor(y0 - dy))
            right, bottom = min(width, math.ceil(x1 + dx)), min(height, math.ceil(y1 + dy))
            mask[top:bottom, left:right] = 255
            masked.append(face.track_id)
        area = int(np.count_nonzero(mask))
        return FacePlan(FaceCoverage(True, reason, source_index, generation), faces, tuple(masked),
                        faces[exempt].track_id if exempt is not None else None, mask, area,
                        area / (height * width), False)


def opaque(frame_bgr, mask, color=(24, 24, 24)):
    """Source-independent inside mask; no blurred facial structure is retained."""
    if frame_bgr.dtype != np.uint8 or frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
        raise ValueError('expected uint8 BGR frame')
    if mask.shape != frame_bgr.shape[:2] or mask.dtype != np.uint8 or not np.isin(mask, (0, 255)).all():
        raise ValueError('expected binary uint8 face mask in source coordinates')
    if len(color) != 3 or any(not isinstance(v, int) or not 0 <= v <= 255 for v in color):
        raise ValueError('color must contain three bytes')
    result = frame_bgr.copy()
    result[mask != 0] = color
    return result

"""Neutral privacy pixels, independent of detectors and transport.

Original project implementation; no external images, fonts or other assets.
Uses existing NumPy (BSD-3-Clause, https://numpy.org/doc/stable/license.html)
and OpenCV (Apache-2.0, https://opencv.org/license/) dependencies.
"""
from dataclasses import dataclass
import math

import cv2
import numpy as np


@dataclass
class Rendered:
    pixels: np.ndarray
    mask: np.ndarray
    protected: bool
    slate: bool


class Renderer:
    """Rasterize convex four-point quads with equal padding normal to each edge.

    Padding is a fraction of the shorter opposite-edge mean, with a 3px floor.
    Offset edges meet at miters; points may be supplied in any order.
    """

    def __init__(self, style='opaque', padding=.3, badge=False, slate_after=1.0):
        if style != 'opaque':
            raise ValueError('Unsupported render style; expected opaque')
        if not math.isfinite(padding) or padding < 0:
            raise ValueError('Padding must be finite and nonnegative')
        if not math.isfinite(slate_after) or slate_after < 0:
            raise ValueError('Slate threshold must be finite and nonnegative')
        self.style = style
        self.padding = padding
        self.badge = badge
        self.slate_after = slate_after

    def render(self, frame_bgr, quads, state: str, clues: int, protect_duration: float = 0):
        """Return owned pixels and the actual covered union; invalid input raises ValueError.

        PROTECT/HOLD cover the whole image and do not depend on valid detector
        geometry. Optional badge pixels also count toward the covered mask.
        """
        if (not isinstance(frame_bgr, np.ndarray) or frame_bgr.dtype != np.uint8
                or frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3
                or min(frame_bgr.shape[:2]) < 1):
            raise ValueError('Expected a nonempty HxWx3 uint8 BGR frame')
        if state not in ('LIVE', 'PROTECT', 'HOLD'):
            raise ValueError('Expected LIVE, PROTECT or HOLD state')
        if not math.isfinite(protect_duration) or protect_duration < 0:
            raise ValueError('Protection duration must be finite and nonnegative')
        h, w = frame_bgr.shape[:2]
        protected = state != 'LIVE'
        slate = state == 'HOLD' or (state == 'PROTECT' and protect_duration >= self.slate_after)
        if protected:
            mask = np.full((h, w), 255, np.uint8)
            if slate:
                pixels = np.zeros_like(frame_bgr)
            else:
                # Even a 20×11 preview retained readable large house numbers.
                # A single color preserves no spatial letter or digit shapes.
                coarse = cv2.resize(frame_bgr, (1,1),
                                    interpolation=cv2.INTER_AREA)
                pixels = cv2.resize(coarse, (w, h), interpolation=cv2.INTER_LINEAR)
        else:
            mask = np.zeros((h, w), np.uint8)
            pixels = frame_bgr.copy()
            points = np.asarray(list(quads), np.float64)
            if len(points):
                limit = np.iinfo(np.int32).max / 256 - 1
                if (points.shape[1:] != (4, 2) or not np.isfinite(points).all()
                        or np.abs(points).max() > limit):
                    raise ValueError('Expected four finite rasterizable quad points')
                # Preserve OpenCV's float32 hull precision and corner ordering;
                # all subsequent edge arithmetic can share one batched pass.
                hulls = [cv2.convexHull(quad) for quad in points.astype(np.float32)]
                if any(len(hull) != 4 for hull in hulls):
                    raise ValueError('Expected four distinct convex quad corners')
                points = np.asarray(hulls, np.float64).reshape(-1, 4, 2)
                edges = np.roll(points, -1, axis=1) - points
                lengths = np.linalg.norm(edges, axis=2)
                distance = np.maximum(3, self.padding * np.minimum((lengths[:, 0] + lengths[:, 2]) / 2,
                                                                   (lengths[:, 1] + lengths[:, 3]) / 2))
                normals = np.stack((edges[:, :, 1], -edges[:, :, 0]), axis=2) / lengths[:, :, None]
                previous = np.roll(normals, 1, axis=1)
                denominator = 1 + (previous * normals).sum(axis=2)
                if (denominator <= 1e-12).any():
                    raise ValueError('Quad corners are too acute to offset reliably')
                expanded = points + distance[:, None, None] * (previous + normals) / denominator[:, :, None]
                if not np.isfinite(expanded).all() or np.abs(expanded).max() > limit:
                    raise ValueError('Padded quad exceeds raster coordinates')
                lower = np.maximum(0, np.floor(expanded.min(axis=1))).astype(int)
                upper = np.minimum([w, h], np.ceil(expanded.max(axis=1)) + 1).astype(int)
                visible = (lower < upper).all(axis=1)
                fixed = np.rint((expanded[visible] - lower[visible, None, :]) * 256).astype(np.int32)
                bounds = np.concatenate((lower, upper), axis=1)[visible]
                for (left, top, right, bottom), quad in zip(bounds, fixed):
                    cv2.fillConvexPoly(mask[top:bottom, left:right], quad, 255, lineType=cv2.LINE_8, shift=8)
                    cv2.fillConvexPoly(pixels[top:bottom, left:right], quad, (0, 0, 0), lineType=cv2.LINE_8, shift=8)
        if self.badge:
            text = f'Shield on | {clues} clues hidden'
            (width, height), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, .5, 1)
            corner = (min(w, width + 12) - 1, min(h, height + baseline + 12) - 1)
            cv2.rectangle(pixels, (0, 0), corner, (0, 0, 0), thickness=-1)
            cv2.rectangle(mask, (0, 0), corner, 255, thickness=-1)
            cv2.putText(pixels, text, (6, height + 6), cv2.FONT_HERSHEY_SIMPLEX, .5,
                        (255, 255, 255), thickness=1, lineType=cv2.LINE_AA)
        return Rendered(pixels, mask, protected, slate)

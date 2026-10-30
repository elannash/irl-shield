"""Coarse-mean Frosted and source-independent opaque materials.

NumPy and OpenCV use the repository's existing BSD-3-Clause and Apache-2.0
dependencies. No geometry, detector or transport policy is implemented here.
"""
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np


SKINS = ('frosted', 'bar', 'patch', 'signed', 'petals', 'ripple', 'confetti', 'cloud')
PATTERNS = SKINS[4:]


@dataclass(frozen=True)
class MaskRegion:
    """A caller-owned binary local raster at integer frame position (left, top).

    text_height is the caller's estimate in output pixels, before padding.
    The raster must fit within the frame. Overlap is legal; supplied order wins.
    """
    left: int
    top: int
    raster: np.ndarray
    text_height: float


@dataclass
class Painted:
    pixels: np.ndarray
    mask: np.ndarray
    alpha: np.ndarray
    skin: str
    fallback_reason: str | None = None


def cell_extents(width, height, text_height):
    """Return local half-open rectangles, row-major, used for exact cell sums.

    Partition the entire region bounding rectangle with floor(i * size / n).
    Each axis has max(1, min(4, floor(size / minimum))) cells, where minimum
    is ceil(max(24, 1.5 * text_height, long_axis / 4)). Thus no terminal sliver
    is created. A bounding axis shorter than minimum has one clipped cell.
    Rectangle pixels outside an irregular raster contribute only to its mean.
    No pixel outside the region bounding rectangle is read.
    """
    if (not isinstance(width, int) or not isinstance(height, int)
            or min(width, height) < 1 or not math.isfinite(text_height)
            or text_height <= 0):
        raise ValueError('Expected positive dimensions and finite positive text height')
    side = math.ceil(max(24, 1.5 * text_height, max(width, height) / 4))
    nx, ny = max(1, min(4, width // side)), max(1, min(4, height // side))
    return [(x * width // nx, y * height // ny,
             (x + 1) * width // nx, (y + 1) * height // ny)
            for y in range(ny) for x in range(nx)]


@lru_cache(maxsize=128)
def _grain(height, width, seed):
    # Stable spatial grain avoids a shimmering per-frame noise field.
    y, x = np.indices((height, width), dtype=np.uint32)
    hashed = (x * np.uint32(1664525)) ^ (y * np.uint32(1013904223)) ^ np.uint32(seed)
    noise = ((hashed ^ (hashed >> 13)) % 5).astype(np.float32) - 2
    noise.setflags(write=False)
    return noise[:, :, None]


def _frosted(source, text_height, desaturation, seed):
    height, width = source.shape[:2]
    cells = cell_extents(width, height, text_height)
    nx = sum(top == 0 for _, top, _, _ in cells)
    ny = len(cells) // nx
    means = np.array([source[t:b, l:r].mean(axis=(0, 1), dtype=np.float64)
                      for l, t, r, b in cells], np.float32).reshape(ny, nx, 3)
    if desaturation:
        gray = means @ np.array([.114, .587, .299], np.float32)
        means = means * (1 - desaturation) + gray[:, :, None] * desaturation
    # Four samples per cell make Gaussian sigma=2 equal to half a cell.
    # Filtering this bounded intermediate avoids a wide full-frame kernel.
    smooth = cv2.resize(means, (nx * 4, ny * 4), interpolation=cv2.INTER_CUBIC)
    smooth = cv2.GaussianBlur(smooth, (0, 0), 2, borderType=cv2.BORDER_REPLICATE)
    paint = cv2.resize(smooth, (width, height), interpolation=cv2.INTER_CUBIC)
    paint += _grain(height, width, seed)
    return np.clip(np.rint(paint), 0, 255).astype(np.uint8)


class SkinPainter:
    """Atomic full-coverage paint with immutable cached pattern assets.

    HOLD and PROTECT return a source-independent opaque field. A presentation
    layer can replace that field with its own safe slate. Skin changes happen
    at the render call, never by fading through unpainted source pixels.
    """
    def __init__(self, assets=None, desaturation=0.0, grain_seed=913):
        if not math.isfinite(desaturation) or not 0 <= desaturation <= 1:
            raise ValueError('Desaturation must be finite in [0, 1]')
        if type(grain_seed) is not int or not 0 <= grain_seed < 2**32:
            raise ValueError('Grain seed must be a uint32 integer')
        self.desaturation = desaturation
        self.grain_seed = grain_seed
        self.textures = {}
        self.asset_errors = {}
        directory = Path(assets) if assets is not None else Path(__file__).resolve().parents[2] / 'fixtures/skins'
        try:
            manifest = json.loads((directory / 'attribution.json').read_text())
            entries = {row['name']: row for row in manifest['assets']}
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.asset_errors = {name: f'Asset manifest unavailable: {type(error).__name__}' for name in PATTERNS}
            return
        for name in PATTERNS:
            try:
                entry = entries[name]
                path = directory / f'{name}.png'
                raw = path.read_bytes()
                if hashlib.sha256(raw).hexdigest() != entry['sha256']:
                    raise ValueError('asset hash mismatch')
                texture = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_UNCHANGED)
                if (texture is None or texture.dtype != np.uint8 or texture.ndim != 3
                        or texture.shape[2] not in (3, 4) or min(texture.shape[:2]) < 1
                        or (texture.shape[2] == 4 and not (texture[:, :, 3] == 255).all())):
                    raise ValueError('asset is not opaque BGR/BGRA')
                texture = texture[:, :, :3].copy()
                texture.setflags(write=False)
                self.textures[name] = texture
            except (OSError, KeyError, TypeError, ValueError, cv2.error) as error:
                self.asset_errors[name] = f'Asset unavailable: {type(error).__name__}'

    def paint(self, frame_bgr, regions, *, state='LIVE', skin='frosted'):
        if (not isinstance(frame_bgr, np.ndarray) or frame_bgr.dtype != np.uint8
                or frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3
                or min(frame_bgr.shape[:2]) < 1):
            raise ValueError('Expected a nonempty HxWx3 uint8 BGR frame')
        if state not in ('LIVE', 'HOLD', 'PROTECT') or skin not in SKINS:
            raise ValueError('Unknown privacy state or skin')
        h, w = frame_bgr.shape[:2]
        if state != 'LIVE':
            return Painted(np.full_like(frame_bgr, (21, 19, 17)),
                           np.full((h, w), 255, np.uint8), np.full((h, w), 255, np.uint8), 'bar')
        regions = list(regions)
        for region in regions:
            raster = region.raster
            if (type(region.left) is not int or type(region.top) is not int
                    or not isinstance(raster, np.ndarray) or raster.dtype != np.uint8
                    or raster.ndim != 2 or min(raster.shape) < 1
                    or not np.isin(raster, (0, 255)).all()
                    or region.left < 0 or region.top < 0
                    or region.left + raster.shape[1] > w or region.top + raster.shape[0] > h):
                raise ValueError('Expected an in-frame binary uint8 local mask raster')
            cell_extents(raster.shape[1], raster.shape[0], region.text_height)
        reason = self.asset_errors.get(skin) if skin in PATTERNS else None
        effective = 'bar' if reason else skin
        pixels = frame_bgr.copy()
        mask = np.zeros((h, w), np.uint8)
        for region in regions:
            rh, rw = region.raster.shape
            left, top = region.left, region.top
            target = pixels[top:top + rh, left:left + rw]
            selected = region.raster != 0
            if effective == 'frosted':
                # Always read the original frame, including in overlapping masks.
                paint = _frosted(frame_bgr[top:top + rh, left:left + rw],
                                 region.text_height, self.desaturation, self.grain_seed)
            elif effective in PATTERNS:
                texture = self.textures[effective]
                # Frame-anchored repeat; neither source color nor detector order
                # changes pattern phase. Texture is decoded only at startup.
                ys = np.arange(top, top + rh) % texture.shape[0]
                xs = np.arange(left, left + rw) % texture.shape[1]
                paint = texture[ys[:, None], xs]
            elif effective == 'patch':
                paint = np.full((rh, rw, 3), (174, 188, 191), np.uint8)
            elif effective == 'signed':
                paint = np.full((rh, rw, 3), (24, 21, 18), np.uint8)
                if min(rh, rw) >= 40:
                    cx, cy = rw // 2, rh // 2
                    radius = min(8, rh // 6, rw // 6)
                    vertices = np.array([[cx-radius, cy-radius], [cx+radius, cy-radius],
                                         [cx+radius, cy], [cx, cy+radius], [cx-radius, cy]], np.int32)
                    cv2.fillConvexPoly(paint, vertices, (151, 148, 143))
            else:
                paint = np.zeros((rh, rw, 3), np.uint8)
            np.copyto(target, paint, where=selected[:, :, None])
            np.maximum(mask[top:top + rh, left:left + rw], region.raster,
                       out=mask[top:top + rh, left:left + rw])
        return Painted(pixels, mask, mask.copy(), effective, reason)

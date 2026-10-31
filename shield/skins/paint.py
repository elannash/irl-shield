"""Coarse-mean Frosted and source-independent opaque materials.

NumPy and OpenCV use the repository's existing BSD-3-Clause and Apache-2.0
dependencies. Upstream geometry and detector/transport policy stay caller-owned.
"""
from dataclasses import dataclass
from functools import lru_cache
import math

import cv2
import numpy as np


SKINS = ('frosted', 'bar', 'signed', 'patch')


@dataclass(frozen=True)
class MaskRegion:
    """A caller-owned binary local raster at integer frame position (left, top).

    text_height is the caller's estimate in output pixels, before padding.
    The raster must fit within the frame. Original overlaps use supplied order;
    an extension cannot displace an original region's paint.
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
    # Native integer channel sums avoid per-pixel Python-array reductions.
    # Float64 division before float32 conversion preserves the old means.
    sums = np.array([cv2.sumElems(source[t:b, l:r])[:3]
                     for l, t, r, b in cells], np.float64)
    areas = np.array([(r-l) * (b-t) for l, t, r, b in cells], np.float64)
    means = (sums / areas[:, None]).astype(np.float32).reshape(ny, nx, 3)
    if desaturation:
        gray = means @ np.array([.114, .587, .299], np.float32)
        means = means * (1 - desaturation) + gray[:, :, None] * desaturation
    # Four samples per cell make Gaussian sigma=2 equal to half a cell.
    # Filtering this bounded intermediate avoids a wide full-frame kernel.
    smooth = cv2.resize(means, (nx * 4, ny * 4), interpolation=cv2.INTER_CUBIC)
    smooth = cv2.GaussianBlur(smooth, (0, 0), 2, borderType=cv2.BORDER_REPLICATE)
    # Single-channel cubic kernels use native vector lanes without changing
    # the interpolation grid, coefficients or original averaging rectangle.
    paint = cv2.merge([cv2.resize(channel, (width, height), interpolation=cv2.INTER_CUBIC)
                       for channel in cv2.split(smooth)])
    paint += _grain(height, width, seed)
    return np.clip(np.rint(paint), 0, 255).astype(np.uint8)


def _rounded_alpha(height, width, radius, grow):
    """Exact raster-distance feather from one symmetric corner, without a cache.

    Radius is bounded; straight edges have integer distances. Only a small
    corner needs EDT. Its right/bottom edges reach the straight portions, so
    every exterior pixel's nearest opaque pixel is present in this quadrant.
    """
    feather = 6
    height, width = height + 2 * (grow + feather), width + 2 * (grow + feather)
    size = math.ceil(radius) + feather
    axis = np.arange(size, dtype=np.float32) + .5
    gap = np.maximum(feather + radius - axis, 0)
    corner = ((gap[:, None] ** 2 + gap ** 2) <= radius ** 2).astype(np.uint8) * 255
    distance = cv2.distanceTransform(255 - corner, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    t = np.clip(distance / feather, 0, 1)
    corner_alpha = np.rint(255 * (1 - t * t * (3 - 2 * t))).astype(np.uint8)
    alpha = np.full((height, width), 255, np.uint8)
    t = np.arange(feather, 0, -1, dtype=np.float32) / feather
    edge = np.rint(255 * (1 - t * t * (3 - 2 * t))).astype(np.uint8)
    alpha[:feather] = edge[:, None]
    alpha[-feather:] = edge[::-1, None]
    np.minimum(alpha[:, :feather], edge[None, :], out=alpha[:, :feather])
    np.minimum(alpha[:, -feather:], edge[None, ::-1], out=alpha[:, -feather:])
    alpha[:size, :size] = corner_alpha
    alpha[:size, -size:] = corner_alpha[:, ::-1]
    alpha[-size:, :size] = corner_alpha[::-1]
    alpha[-size:, -size:] = corner_alpha[::-1, ::-1]
    return alpha


@lru_cache(maxsize=9)
def _disk(grow):
    # Radius <=24 bounds grow to 0..8; only these tiny binary kernels persist.
    y, x = np.ogrid[-grow:grow + 1, -grow:grow + 1]
    kernel = (x * x + y * y <= grow * grow).astype(np.uint8)
    kernel.setflags(write=False)
    return kernel


def _bounds(region, frame_height, frame_width):
    rh, rw = region.raster.shape
    radius = min(24., max(6., .3 * min(rh, rw)))
    grow = math.ceil(max(radius * (1 - 1 / math.sqrt(2)),
                         (2 * radius - min(rh, rw)) / 2))
    return (max(0, region.left - grow - 6), max(0, region.top - grow - 6),
            min(frame_width, region.left + rw + grow + 6),
            min(frame_height, region.top + rh + grow + 6), radius, grow)


def _merged_bounds(boxes):
    """Disjoint rectangle groups; each input already contains its 6px feather."""
    merged = []
    for left, top, right, bottom in boxes:
        index = 0
        while index < len(merged):
            l, t, r, b = merged[index]
            if left <= r and l <= right and top <= b and t <= bottom:
                left, top, right, bottom = min(left, l), min(top, t), max(right, r), max(bottom, b)
                merged.pop(index)
                index = 0
            else:
                index += 1
        merged.append((left, top, right, bottom))
    return merged


def _feather(opaque):
    distance = cv2.distanceTransform(255 - opaque, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    t = np.clip(distance / 6, 0, 1)
    return np.rint(255 * (1 - t * t * (3 - 2 * t))).astype(np.uint8)


def _union_alpha(mask, boxes, rectangles):
    # Distance to a union is the minimum distance to its members. The feather
    # is monotone in that distance. Disjoint 6px-expanded groups cannot supply
    # each other's positive feather, so each group needs just one exact EDT.
    alpha = np.zeros_like(mask)
    for left, top, right, bottom in _merged_bounds(boxes):
        alpha[top:bottom, left:right] = _feather(mask[top:bottom, left:right])
    # mask initially contains only irregular regions. Add rectangles after the
    # EDT so their original corner stencil supplies their exact alpha bytes.
    for left, top, opaque, local_alpha in rectangles:
        height, width = local_alpha.shape
        target = alpha[top:top + height, left:left + width]
        np.maximum(target, local_alpha, out=target)
        target = mask[top:top + height, left:left + width]
        np.maximum(target, opaque, out=target)
    return alpha


def _envelope(region, frame_height, frame_width):
    """Round outward before clipping; dilate irregular rasters, never erode.

    Pixel centers are half-integers in half-open pixel-square bounds. Ceil
    expansion covers original square corners; tiny boxes grow to fit the
    diameter. Original pixels are always unioned back as a safeguard.
    """
    rh, rw = region.raster.shape
    left, top, right, bottom, radius, grow = _bounds(region, frame_height, frame_width)
    feather = 6
    ox, oy = region.left - left, region.top - top
    if cv2.countNonZero(region.raster) == rh * rw:
        full = _rounded_alpha(rh, rw, radius, grow)
        x, y = grow + feather - ox, grow + feather - oy
        alpha = full[y:y + bottom - top, x:x + right - left]
        opaque = cv2.compare(alpha, 255, cv2.CMP_EQ)
        opaque[oy:oy + rh, ox:ox + rw] = 255
        alpha[oy:oy + rh, ox:ox + rw] = 255
    else:
        original = np.zeros((bottom - top, right - left), np.uint8)
        original[oy:oy + rh, ox:ox + rw] = region.raster
        opaque = cv2.dilate(original, _disk(grow), borderType=cv2.BORDER_CONSTANT, borderValue=0)
        cv2.bitwise_or(opaque, original, opaque)
        alpha = None
    return left, top, opaque, alpha


def _constant_geometry(regions, height, width):
    """Union same-radius irregular rasters before dilation; no local colors."""
    mask = np.zeros((height, width), np.uint8)
    groups, boxes, irregular_boxes, rectangles = {}, [], [], []
    for region in regions:
        nonzero = cv2.countNonZero(region.raster)
        if not nonzero:
            continue
        if nonzero == region.raster.size:
            left, top, opaque, local_alpha = _envelope(region, height, width)
            eh, ew = opaque.shape
            boxes.append((left, top, left + ew, top + eh))
            rectangles.append((left, top, opaque, local_alpha))
        else:
            left, top, right, bottom, _, grow = _bounds(region, height, width)
            groups.setdefault(grow, []).append((region, (left, top, right, bottom)))
    for grow, members in groups.items():
        for left, top, right, bottom in _merged_bounds([box for _, box in members]):
            original = np.zeros((bottom - top, right - left), np.uint8)
            for region, box in members:
                if not (left <= box[0] and top <= box[1] and box[2] <= right and box[3] <= bottom):
                    continue
                rh, rw = region.raster.shape
                x, y = region.left - left, region.top - top
                target = original[y:y + rh, x:x + rw]
                cv2.bitwise_or(target, region.raster, target)
            opaque = cv2.dilate(original, _disk(grow), borderType=cv2.BORDER_CONSTANT, borderValue=0)
            cv2.bitwise_or(opaque, original, opaque)
            target = mask[top:bottom, left:right]
            np.maximum(target, opaque, out=target)
            boxes.append((left, top, right, bottom))
            irregular_boxes.append((left, top, right, bottom))
    alpha = _union_alpha(mask, irregular_boxes, rectangles)
    return mask, alpha, boxes


class SkinPainter:
    """Outward-only rounded paint; global opaque protection gates every feather.

    HOLD and PROTECT return a source-independent opaque field. A presentation
    layer can replace that field with its own safe slate. Skin changes happen
    at the render call, never by fading through unpainted source pixels.
    """
    def __init__(self, desaturation=0.0, grain_seed=913):
        if not math.isfinite(desaturation) or not 0 <= desaturation <= 1:
            raise ValueError('Desaturation must be finite in [0, 1]')
        if type(grain_seed) is not int or not 0 <= grain_seed < 2**32:
            raise ValueError('Grain seed must be a uint32 integer')
        self.desaturation = desaturation
        self.grain_seed = grain_seed

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
                    or cv2.countNonZero(cv2.inRange(raster, 1, 254))
                    or region.left < 0 or region.top < 0
                    or region.left + raster.shape[1] > w or region.top + raster.shape[0] > h):
                raise ValueError('Expected an in-frame binary uint8 local mask raster')
            cell_extents(raster.shape[1], raster.shape[0], region.text_height)
        pixels = frame_bgr.copy()
        prepared = []
        if skin in ('bar', 'patch'):
            mask, alpha, boxes = _constant_geometry(regions, h, w)
        else:
            mask = np.zeros((h, w), np.uint8)
            boxes, irregular_boxes, rectangles = [], [], []
            for region in regions:
                if not cv2.countNonZero(region.raster):
                    continue
                left, top, opaque, local_alpha = _envelope(region, h, w)
                eh, ew = opaque.shape
                prepared.append((region, left, top, opaque, local_alpha))
                boxes.append((left, top, left + ew, top + eh))
                if local_alpha is not None:
                    rectangles.append((left, top, opaque, local_alpha))
                else:
                    target = mask[top:top + eh, left:left + ew]
                    np.maximum(target, opaque, out=target)
                    irregular_boxes.append((left, top, left + ew, top + eh))
            alpha = _union_alpha(mask, irregular_boxes, rectangles)
        if not boxes:
            return Painted(pixels, mask, alpha, skin)
        left = min(box[0] for box in boxes)
        top = min(box[1] for box in boxes)
        right = max(box[2] for box in boxes)
        bottom = max(box[3] for box in boxes)
        area = np.s_[top:bottom, left:right]
        canvas = np.zeros((bottom - top, right - left, 3), np.uint8)
        if skin == 'patch':
            cv2.rectangle(canvas, (0, 0), (right-left-1, bottom-top-1), (174, 188, 191), -1)
        if skin in ('frosted', 'signed'):
            owner = np.zeros((bottom - top, right - left), np.int32)
            for index, (region, x, y, opaque, local_alpha) in enumerate(prepared, 1):
                eh, ew = opaque.shape
                target = owner[y-top:y-top+eh, x-left:x-left+ew]
                target[opaque != 0] = index
                local_union = alpha[y:y+eh, x:x+ew]
                feather = (local_union != 0) & (local_union != 255)
                if feather.any():
                    if local_alpha is None:
                        local_alpha = _feather(opaque)
                    target[feather & (local_alpha == local_union)] = index
            # Originals override extensions in supplied order, just as the
            # previous final restore loop did. Ownership contains no color.
            for index, (region, _, _, _, _) in enumerate(prepared, 1):
                rh, rw = region.raster.shape
                target = owner[region.top-top:region.top-top+rh, region.left-left:region.left-left+rw]
                target[region.raster != 0] = index
            visible = np.bincount(owner.ravel(), minlength=len(prepared) + 1)
            for index, (region, x, y, opaque, _) in enumerate(prepared, 1):
                if not visible[index]:
                    continue
                rh, rw = region.raster.shape
                if skin == 'frosted':
                    # Always read original averaging cells, never painted video.
                    paint = _frosted(frame_bgr[region.top:region.top + rh, region.left:region.left + rw],
                                     region.text_height, self.desaturation, self.grain_seed)
                else:
                    paint = np.empty((rh, rw, 3), np.uint8)
                    cv2.rectangle(paint, (0, 0), (rw-1, rh-1), (24, 21, 18), -1)
                    if min(rh, rw) >= 40:
                        cx, cy = rw // 2, rh // 2
                        radius = min(8, rh // 6, rw // 6)
                        vertices = np.array([[cx-radius, cy-radius], [cx+radius, cy-radius],
                                             [cx+radius, cy], [cx, cy+radius], [cx-radius, cy]], np.int32)
                        cv2.fillConvexPoly(paint, vertices, (151, 148, 143))
                eh, ew = opaque.shape
                px, py = region.left - x, region.top - y
                extended = cv2.copyMakeBorder(paint, py, eh-py-rh, px, ew-px-rw, cv2.BORDER_REPLICATE)
                # A partial feather can never win against global alpha255.
                # Equal-alpha winners retain the caller's supplied order.
                winner = cv2.compare(owner[y-top:y-top+eh, x-left:x-left+ew], index, cv2.CMP_EQ)
                target = canvas[y-top:y-top+eh, x-left:x-left+ew]
                cv2.copyTo(extended, winner, target)
        weight = alpha[area].astype(np.float32) / 255
        # One native blend, with zero source weight on ALL opaque protection.
        # The explicit opaque copy also commits those bytes without blending.
        blended = cv2.blendLinear(canvas, frame_bgr[area], weight, 1 - weight)
        cv2.copyTo(blended, alpha[area], pixels[area])
        cv2.copyTo(canvas, mask[area], pixels[area])
        return Painted(pixels, mask, alpha, skin)

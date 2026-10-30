"""Opt-in padding budget; raw detector quads are never discarded or trimmed.

Uses the existing NumPy (BSD-3-Clause) and OpenCV (Apache-2.0) dependencies.
This adapter has no detector, OCR, stream, or guard authority.
"""
from dataclasses import dataclass
import math

import cv2

from shield.render import Rendered, Renderer


@dataclass(frozen=True)
class PaddingBudget:
    limit_pixels: int
    covered_pixels: int
    minimum_pixels: int | None
    padding_scale: float
    satisfied: bool


@dataclass
class BudgetedRendered(Rendered):
    budget: PaddingBudget | None


class PaddingBudgetRenderer:
    """Reduce a common scale on proportional padding AND its normal 3px floor.

    The actual clipped raster union is bounded, never summed polygon areas.
    If bare quads exceed the requested fraction, return all of them and report
    satisfied=False. The caller must retain that failure. PROTECT/HOLD bypass
    budgeting. There is no badge in this experimental adapter.

    At most 14 ordinary renders per LIVE frame: full, bare, then 12 bisections.
    This conservative CPU implementation needs separate performance validation.
    """

    def __init__(self, *, max_mask_fraction, padding=.3, slate_after=1.):
        if (isinstance(max_mask_fraction, bool) or not math.isfinite(max_mask_fraction)
                or not 0 <= max_mask_fraction <= 1):
            raise ValueError('Mask fraction must be finite and between zero and one')
        self.max_mask_fraction = max_mask_fraction
        self.renderer = Renderer(padding=padding, slate_after=slate_after)

    def render(self, frame_bgr, quads, state: str, clues: int, protect_duration: float = 0):
        quads = list(quads) if state == 'LIVE' else quads
        full = self.renderer.render(frame_bgr, quads, state, clues, protect_duration)

        def result(rendered, minimum, scale):
            covered = cv2.countNonZero(rendered.mask)
            budget = PaddingBudget(limit, covered, minimum, scale, covered <= limit)
            return BudgetedRendered(rendered.pixels, rendered.mask, rendered.protected,
                                    rendered.slate, budget)

        if full.protected:
            return BudgetedRendered(full.pixels, full.mask, full.protected, full.slate, None)
        limit = math.floor(self.max_mask_fraction * full.mask.size)
        if cv2.countNonZero(full.mask) <= limit:
            return result(full, None, 1.)

        bare = Renderer(padding=0, padding_floor=0).render(frame_bgr, quads, state, clues)
        minimum = cv2.countNonZero(bare.mask)
        if minimum >= limit:
            return result(bare, minimum, 0.)
        low, high, best = 0., 1., bare
        for _ in range(12):
            scale = (low + high) / 2
            candidate = Renderer(padding=self.renderer.padding * scale,
                                 padding_floor=3 * scale).render(frame_bgr, quads, state, clues)
            # Fixed-point raster rounding need not be perfectly nested. Retain
            # every bare raster pixel even if an offset edge rounds inward.
            cv2.bitwise_or(candidate.mask, bare.mask, dst=candidate.mask)
            candidate.pixels[bare.mask > 0] = 0
            if cv2.countNonZero(candidate.mask) <= limit:
                low, best = scale, candidate
            else:
                high = scale
        return result(best, minimum, low)

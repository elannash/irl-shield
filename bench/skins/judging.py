"""Output attack views preserve the existing independent truth policy."""
import math

import cv2
import numpy as np

from bench.independence import independent_readings, judging_scope, policy_metadata


def attack_views(crop):
    """Original, contrast stretch, unsharp mask, 2x and their combined attack.

    These transforms operate on painted output only, never on input truth.
    """
    if crop.dtype != np.uint8 or crop.ndim != 3 or crop.shape[2] != 3 or min(crop.shape[:2]) < 1:
        raise ValueError('Expected a nonempty BGR uint8 crop')
    low, high = np.percentile(crop, [1, 99], axis=(0, 1))
    stretched = np.clip((crop.astype(np.float32) - low) * 255 / np.maximum(1, high - low), 0, 255).astype(np.uint8)
    sharp = cv2.addWeighted(crop, 2, cv2.GaussianBlur(crop, (0, 0), 1), -1, 0)
    combined = cv2.addWeighted(stretched, 2, cv2.GaussianBlur(stretched, (0, 0), 1), -1, 0)
    return [('original', crop, 1), ('contrast', stretched, 1), ('sharpen', sharp, 1),
            ('upscale2x', cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC), 2),
            ('contrast-sharpen-upscale2x', cv2.resize(combined, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC), 2)]


def _touches_mask(reading, mask, scale=1):
    box = reading.get('box')
    if box is None or len(box) != 4 or not all(math.isfinite(v) for v in box):
        # A judge that omits geometry cannot safely exonerate a reading.
        return True
    left, top = max(0, math.floor(box[0] / scale)), max(0, math.floor(box[1] / scale))
    right, bottom = min(mask.shape[1], math.ceil(box[2] / scale)), min(mask.shape[0], math.ceil(box[3] / scale))
    return right > left and bottom > top and bool(mask[top:bottom, left:right].any())


def judge_output(judges, source, painted, regions, *, candidate, options):
    """Return every output judge and every credible mask-overlapping reading.

    Primary truth excludes declared detector families. It cannot silently
    continue with fewer than two independent engines. Output never excludes
    a detector-family judge. This function does not compute a hidden fraction
    without annotated truth or claim all-slate video is useful output.
    """
    families = policy_metadata(candidate, options)['detector_families']
    scope = judging_scope(families)
    if not scope['sufficient_independent_engines']:
        raise ValueError('Skin primary truth needs at least two independent judge engines')
    aliases = {'tesseract-5-psm11': 'tesseract', 'vision-accurate': 'vision-accurate',
               'ppocr-independent': 'ppocr-independent'}
    available = {aliases[name] for name in judges.names if name in aliases}
    if len(available & set(scope['truth_judges'])) < 2:
        raise ValueError('Skin primary truth is missing an actual independent judge engine')
    scope = {**scope, 'available_judges': sorted(available)}
    truth_all = judges.read(source)
    truth = independent_readings([truth_all], families)[0]
    records, leaks = [], []
    def read(view, label, mask, scale=1):
        readings = judges.read(view)
        records.append({'view': label, 'shape': list(view.shape), 'readings': readings})
        for item in readings:
            if item.get('judge') not in scope['output_leak_judges']:
                raise ValueError('Output reading has an undeclared judge')
            if (item.get('text', '').strip() and item.get('confidence', 0) >= .5
                    and _touches_mask(item, mask, scale)):
                leaks.append({'view': label, **item})
    read(painted.pixels, 'full-output', painted.mask)
    for index, region in enumerate(regions):
        h, w = region.raster.shape
        crop = painted.pixels[region.top:region.top+h, region.left:region.left+w]
        for name, view, scale in attack_views(crop):
            read(view, f'region-{index}/{name}', region.raster, scale)
    return {'judge_independence': scope, 'truth_all_judges': truth_all,
            'primary_independent_truth': truth, 'output_judges': records,
            'credible_output_leaks': leaks, 'passed': not leaks,
            'hidden_fraction': None, 'scope': 'Paint-only probe; no scheduling, real-video score or coverage recall claim.'}

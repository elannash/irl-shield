"""Resolve optional detector policy at the lane construction boundary."""
import math
from numbers import Real


def lane_detector_options(options, lane):
    if lane not in ('fast', 'accurate'):
        raise ValueError('Detector lane must be fast or accurate')
    resolved = dict(options)
    floor = resolved.pop('accurate_box_thresh', None)
    if floor is not None:
        if isinstance(floor, bool) or not isinstance(floor, Real) or not 0 <= floor <= 1 or not math.isfinite(floor):
            raise ValueError('accurate_box_thresh must be a finite number between 0 and 1, or None')
        if lane == 'accurate':
            resolved['box_thresh'] = floor
    return resolved

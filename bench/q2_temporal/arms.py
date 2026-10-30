"""Opt-in temporal policies; no evaluation, model loading or shared writes."""
from copy import deepcopy
import math

from shield.motion import MotionHistory


ARMS = ('baseline', 'flow', 'd2-fixed-a', 'd3-fixed-a', 'd2-derived-a', 'd3-derived-a')


def policy_for(baseline, arm, *, fps=30):
    """Derive one isolated arm from a caller's paired D1/phase policy.

    Fixed-A changes presentation delay alone. Derived-A changes both delay
    and the eligible future-receipt window; it is a separate experiment.
    No D>1 policy is an adoption decision or accepted by the frozen harness.
    """
    if arm not in ARMS:
        raise ValueError('Unknown temporal arm')
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError('Source fps must be positive and finite')
    policy = deepcopy(baseline)
    options = policy['options']
    if options.get('motion_mode') != 'phase' or options.get('delay_seconds') != 1:
        raise ValueError('Temporal arms require a paired D1/phase baseline')
    if arm == 'flow':
        options['motion_mode'] = 'flow'
    elif arm.startswith(('d2-', 'd3-')):
        options['delay_seconds'] = int(arm[1])
        if arm.endswith('derived-a'):
            options['after'] = math.floor(options['delay_seconds'] * fps)
    return policy


def motion_for(options, fps):
    """Adapter for render_offline's existing explicit motion argument.

    Sealed quality_bundle does not expose that argument; do not monkeypatch
    its factory or replace its fingerprint to inject this adapter.
    """
    delay = float(options.get('delay_seconds', 1))
    if not math.isfinite(delay) or delay < 0 or not math.isfinite(fps) or fps <= 0:
        raise ValueError('Invalid source fps or delay')
    horizon = math.floor(delay * fps)
    return MotionHistory(max_frames=max(120, horizon + options.get('before', 6) + 4),
                         analysis_width=options.get('motion_width', 320),
                         mode=options.get('motion_mode', 'phase'),
                         phase_min_response=options.get('motion_min_response', .5),
                         max_projection_frames=horizon)

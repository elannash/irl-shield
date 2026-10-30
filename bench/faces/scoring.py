"""Control-gated residual detection plus independent synthetic placement truth.

Residual detection is a privacy warning signal, not an identity recognition test.
Opaque source-independent pixels provide a stronger guarantee inside their mask.
"""
import math
import numpy as np
from shield.faces.policy import iou


def match_faces(faces, truth, threshold=0.25):
    pairs = sorted(((iou(f.box, t.box), fi, ti) for fi, f in enumerate(faces)
                    for ti, t in enumerate(truth)), reverse=True)
    found, used = {}, set()
    for overlap, fi, ti in pairs:
        if overlap >= threshold and fi not in used and ti not in found:
            used.add(fi)
            found[ti] = fi
    return found, len(faces) - len(used)


def expected_exemption(truth, mode, shape, selfie_min_fraction):
    if mode != 'bystanders' or not truth:
        return None
    index = max(range(len(truth)), key=lambda n: (truth[n].box[2] - truth[n].box[0]) * (truth[n].box[3] - truth[n].box[1]))
    x0, y0, x1, y1 = truth[index].box
    return index if (x1 - x0) * (y1 - y0) > shape[0] * shape[1] * selfie_min_fraction else None


def crop(frame, box, margin=0.35):
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = box
    dx, dy = (x1 - x0) * margin, (y1 - y0) * margin
    return frame[max(0, math.floor(y0 - dy)):min(h, math.ceil(y1 + dy)),
                 max(0, math.floor(x0 - dx)):min(w, math.ceil(x1 + dx))]


def score_frame(before, after, truth, plan, judge, *, mode, selfie_min_fraction=0.08,
                natural_background=False):
    if before.shape != after.shape or plan.mask.shape != before.shape[:2]:
        raise ValueError('score geometry mismatch')
    controls, residuals, coverage = [], [], []
    exempt = expected_exemption(truth, mode, before.shape[:2], selfie_min_fraction)
    for ti, person in enumerate(truth):
        # Crop-local controls make the judge see small placements at useful scale.
        # Control overlap is checked; a face elsewhere in the crop is insufficient.
        control_crop = crop(before, person.box)
        output_crop = crop(after, person.box)
        in_faces = judge.detect(control_crop)
        out_faces = judge.detect(output_crop)
        # Each crop is centered on known face truth. Require a box covering center.
        ch, cw = control_crop.shape[:2]
        controls.append(any(f.box[0] <= cw / 2 <= f.box[2] and f.box[1] <= ch / 2 <= f.box[3] for f in in_faces))
        residuals.append(len(out_faces))
        x0, y0, x1, y1 = person.box
        region = plan.mask[max(0, math.floor(y0)):math.ceil(y1), max(0, math.floor(x0)):math.ceil(x1)]
        coverage.append(float(np.count_nonzero(region)) / region.size if region.size else 0.)
    required = [i for i in range(len(truth)) if mode != 'off' and i != exempt]
    input_valid = bool(truth) and all(controls)
    leaks = sum(coverage[i] < 0.99 or residuals[i] > 0 for i in required)
    actual_residual = len(judge.detect(after))
    matches, unmatched = match_faces(plan.faces, truth)
    behavior_ok = (len(plan.masked_track_ids) == 0 and not np.any(plan.mask)) if mode == 'off' else (
        not plan.requires_hold and all(coverage[i] >= 0.99 for i in required)
        and (exempt is None or coverage[exempt] < 0.01))
    return {'mode': mode, 'truth_faces': len(truth), 'input_face_controls': controls,
            'controls_ok': input_valid, 'required_face_indices': required,
            'expected_exempt_index': exempt, 'actual_exempt_track_id': plan.exempt_track_id,
            'placement_coverage_fraction': coverage, 'crop_residual_counts': residuals,
            'unmasked_required_faces': leaks, 'output_face_count': actual_residual,
            'detector_matched_truth': len(matches),
            'detector_false_positives': None if natural_background else unmatched,
            'detector_unmatched_truth_boxes': unmatched,
            'false_positive_note': 'Natural background can contain unlabeled real faces; unmatched detections are not false positives.' if natural_background else 'Entirely synthetic scene with exhaustive placement truth.',
            'face_area_pixels': plan.area_pixels, 'face_area_fraction': plan.area_fraction,
            'coverage_ok': plan.coverage.ok, 'requires_hold': plan.requires_hold,
            'mode_behavior_ok': behavior_ok,
            'privacy_pass': input_valid and mode != 'off' and not leaks and behavior_ok,
            'text_real_video_guard': 'not evaluated by face scorer; existing text/real-video guard must run unchanged',
            'text_area_fraction': None, 'gpu_source_frame_ms': None}

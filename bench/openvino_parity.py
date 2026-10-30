"""Order-independent, one-to-one box parity for runtime comparisons."""
import math


def compare_boxes(reference, candidate, *, min_iou=.95, max_coordinate_error=2.):
    if not 0 < min_iou <= 1 or not math.isfinite(max_coordinate_error) or max_coordinate_error < 0:
        raise ValueError('Finite coordinate tolerance and IoU in (0, 1] are required')
    for box in [*reference, *candidate]:
        if (len(box) != 4 or not all(math.isfinite(v) for v in box)
                or box[2] <= box[0] or box[3] <= box[1]):
            raise ValueError('Boxes must have finite coordinates and positive area')

    def pair(a, b):
        intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
        union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
        return intersection / union, max(abs(x - y) for x, y in zip(a, b))

    pairs = {(i, j): pair(a, b) for i, a in enumerate(reference) for j, b in enumerate(candidate)}
    edges = {i: sorted((j for j in range(len(candidate))
                        if pairs[i, j][0] >= min_iou and pairs[i, j][1] <= max_coordinate_error),
                       key=lambda j: (-pairs[i, j][0], j)) for i in range(len(reference))}
    assigned = {}

    def assign(i, visited):
        for j in edges[i]:
            if j in visited:
                continue
            visited.add(j)
            if j not in assigned or assign(assigned[j], visited):
                assigned[j] = i
                return True
        return False

    for i in range(len(reference)):
        assign(i, set())
    matches = [{'reference': i, 'candidate': j, 'iou': pairs[i, j][0],
                'max_coordinate_error': pairs[i, j][1]} for j, i in sorted(assigned.items())]
    return {'pass': len(matches) == len(reference) == len(candidate),
            'nonempty_evidence': bool(reference) and bool(candidate),
            'reference_count': len(reference), 'candidate_count': len(candidate),
            'matches': matches,
            'unmatched_reference': sorted(set(range(len(reference))) - set(assigned.values())),
            'unmatched_candidate': sorted(set(range(len(candidate))) - set(assigned)),
            'tolerances': {'min_iou': min_iou, 'max_coordinate_error_pixels': max_coordinate_error}}

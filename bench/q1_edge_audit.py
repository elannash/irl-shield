"""Retained tune geometry audit; no inference, scoring, or truth changes.

Existing NumPy (BSD-3-Clause) and OpenCV (Apache-2.0) dependencies only.
Footage stays benchmark-only under fixtures/ATTRIBUTION.md; no new asset.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import zipfile

import cv2
import numpy as np

from bench.leaks import box_at, region
from shield.motion import MotionHistory
from shield.render import Renderer


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def boundary_checks():
    """Worked pixel examples at public seams, independent of offset internals.

    A 3px floor expands [-6,.25]x[4,6] to [-9,3.25]x[1,9].
    A diamond with diagonals 8px expands by 3*sqrt(2) on each axis.
    Integer scanlines of that diamond have literal widths 1,2,...,7,...,2.
    """
    frame = np.full((12, 12, 3), 173, np.uint8)
    left = [[-6, 4], [.25, 4], [.25, 6], [-6, 6]]
    right = [[11.75, 4], [18, 4], [18, 6], [11.75, 6]]
    diamond = [[-6, 6], [-2, 2], [2, 6], [-2, 10]]
    expected_left = np.zeros((12, 12), np.uint8)
    expected_left[1:10, :4] = 255
    expected_right = np.zeros((12, 12), np.uint8)
    expected_right[1:10, 9:] = 255
    expected_diamond = np.zeros((12, 12), np.uint8)
    for y, width in enumerate([1, 2, 3, 4, 5, 6, 7, 6, 5, 4, 3, 2]):
        expected_diamond[y, :width] = 255
    cases = [('left-sliver', left, expected_left),
             ('right-sliver', right, expected_right),
             ('top-sliver', np.asarray(left)[:, ::-1].tolist(), expected_left.T),
             ('bottom-sliver', np.asarray(right)[:, ::-1].tolist(), expected_right.T),
             ('rotated-left', diamond, expected_diamond),
             ('fully-offscreen', [[-20, 4], [-16, 4], [-16, 6], [-20, 6]],
              np.zeros((12, 12), np.uint8))]
    # Identical textured frames give an exact valid camera transform without
    # reaching into history state or replacing motion estimation.
    textured = np.random.default_rng(1).integers(0, 256, (32, 32, 3), dtype=np.uint8)
    history = MotionHistory(mode='phase', analysis_width=32)
    history.add(0, textured)
    history.add(1, textured.copy())
    results = []
    for name, quad, expected in cases:
        projected = history.project(quad, 0, 1)
        np.testing.assert_array_equal(projected, quad, err_msg=name + ': projection changed vertices')
        rendered = Renderer(padding=0).render(frame, [projected], 'LIVE', 1)
        np.testing.assert_array_equal(rendered.mask, expected, err_msg=name + ': visible pixels differ')
        np.testing.assert_array_equal(rendered.pixels[expected == 0], frame[expected == 0])
        if np.any(expected):
            assert not rendered.pixels[expected > 0].any(), name + ': mask did not obscure pixels'
        results.append({'case': name, 'expected_mask_pixels': int(np.count_nonzero(expected)), 'pass': True})
    unknown = MotionHistory(mode='phase', analysis_width=32)
    unknown.add(0, np.zeros((32, 32, 3), np.uint8))
    unknown.add(1, np.zeros((32, 32, 3), np.uint8))
    assert unknown.project(left, 0, 1) is None, 'Unresolved motion became geometry'
    results.append({'case': 'unresolved-remains-none', 'pass': True})
    return results


def saved_mask(archive, row):
    shape = row['mask_shape']
    packed = np.frombuffer(archive.read(f"{row['frame']:08d}.bin"), np.uint8)
    assert len(packed) == (int(np.prod(shape)) + 7) // 8
    mask = np.unpackbits(packed, count=int(np.prod(shape)), bitorder='little').reshape(shape) * 255
    assert hashlib.sha256(mask.tobytes()).hexdigest() == row['mask_sha256']
    assert abs(float(np.count_nonzero(mask) / mask.size) - row['mask_fraction']) < 1e-12
    return mask


def inspect_row(row, archive):
    """Check each original polygon interior against actual padded pixels.

    Direct full-canvas rasterization of the *unexpanded* polygon is the
    independent oracle. It uses neither renderer ROI bounds nor offset math.
    """
    saved = saved_mask(archive, row)
    frame = np.full((*saved.shape, 3), 173, np.uint8)
    replay = Renderer().render(frame, row['quads'], row['state'], len(row['quads']))
    assert np.array_equal(replay.mask, saved), f"Saved mask replay differs at {row['frame']}"
    height, width = saved.shape
    crossing = []
    for index, quad in enumerate(row['quads']):
        points = np.asarray(quad)
        if ((points >= [0, 0]) & (points <= [width - 1, height - 1])).all():
            continue
        original = np.zeros(saved.shape, np.uint8)
        hull = cv2.convexHull(points.astype(np.float32)).reshape(4, 2)
        cv2.fillConvexPoly(original, np.rint(hull * 256).astype(np.int32), 255, shift=8)
        rendered = Renderer().render(frame, [quad], 'LIVE', 1).mask
        missing = int(np.count_nonzero((original > 0) & (rendered == 0)))
        crossing.append({'quad_index': index, 'quad': quad,
                         'original_visible_pixels': int(np.count_nonzero(original)),
                         'padded_visible_pixels': int(np.count_nonzero(rendered)),
                         'uncovered_original_pixels': missing})
        assert not missing, f"Visible polygon lost at frame {row['frame']} quad {index}"
    return {'frame': row['frame'], 'state': row['state'], 'coverage': row['coverage'],
            'saved_mask_sha256': row['mask_sha256'], 'saved_mask_exact_replay': True,
            'quad_count': len(row['quads']), 'crossing_quads': crossing}, saved


def target_coverage(row, box, mask):
    x0, y0, x1, y1 = region(box, mask.shape[1], mask.shape[0])
    assert x1 > x0 and y1 > y0, 'Audit target has no visible pixels'
    raw = np.zeros((y1 - y0, x1 - x0), np.uint8)
    for quad in row['quads']:
        hull = cv2.convexHull(np.asarray(quad, np.float32)).reshape(4, 2)
        cv2.fillConvexPoly(raw, np.rint((hull - [x0, y0]) * 256).astype(np.int32), 255, shift=8)
    return {'visible_box_pixels': raw.size,
            'unexpanded_polygon_target_pixels': int(np.count_nonzero(raw)),
            'covered_pixels': int(np.count_nonzero(mask[y0:y1, x0:x1]))}


def audit_retained(taxonomy, historical_root, pp_root):
    report = json.loads(taxonomy.read_text())
    intervals = [item for item in report['intervals'] if 'near-edge' in item['attributes']]
    assert len(intervals) == 15, 'Wrong historical sample: expected the fixed 15 near-edge intervals'
    groups = defaultdict(list)
    for item in intervals:
        groups[item['variant']].append(item)
    provenance = {str(taxonomy): digest(taxonomy)}
    natural, frames = [], []
    for variant, items in groups.items():
        prefix = historical_root / (variant + '-masked')
        records_path = prefix.with_suffix('.masks.json')
        archive_path = prefix.with_suffix('.mask-pixels.zip')
        for path in [records_path, archive_path]:
            provenance[str(path)] = digest(path)
        records = json.loads(records_path.read_text())
        measurements = {}
        with zipfile.ZipFile(archive_path) as archive:
            for index in sorted({f['frame'] for item in items for f in item['frames']}):
                summary, mask = inspect_row(records[index], archive)
                frames.append({'variant': variant, **summary})
                measurements[index] = mask
        for item in items:
            targets = []
            for measurement in item['frames']:
                index = measurement['frame']
                mask = measurements[index]
                geometry = target_coverage(records[index], measurement['box'], mask)
                assert geometry['covered_pixels'] == measurement['covered_pixels'], item['id'] + ': taxonomy mask differs'
                assert geometry['visible_box_pixels'] == measurement['visible_box_pixels'], item['id'] + ': target area differs'
                targets.append({'frame': index, 'box': measurement['box'],
                                **geometry})
            natural.append({'id': item['id'], 'clip': item['clip'], 'variant': item['variant'],
                            'track_id': item['track_id'], 'text': item['text'], 'frames': targets})
    prefix = pp_root / 'mazatlan-aquiles-synthetic-masked'
    records_path = prefix.with_suffix('.masks.json')
    archive_path = prefix.with_suffix('.mask-pixels.zip')
    # PP's retained scored observations define the four requested visible targets;
    # truth is read only and never filtered or rewritten.
    pp_evidence = pp_root / 'mazatlan-aquiles-synthetic-masked.evidence.json'
    for path in [records_path, archive_path, pp_evidence]:
        provenance[str(path)] = digest(path)
    records = json.loads(records_path.read_text())
    tracks = json.loads(pp_evidence.read_text())['synthetic']
    synthetic = []
    with zipfile.ZipFile(archive_path) as archive:
        for index in [78, 79, 148, 149]:
            summary, mask = inspect_row(records[index], archive)
            track, = [t for t in tracks if t['text'] == 'CEDAR AVE' and t['first'] <= index <= t['last']]
            box = box_at(track, index)
            synthetic.append({**summary, 'text': track['text'], 'box': box,
                              **target_coverage(records[index], box, mask),
                              'retained_output_leak': index in track['leak_frames']})
    crossing = [q for row in [*frames, *synthetic] for q in row['crossing_quads']]
    return {'scope': 'Historical 15 Vision near-edge natural intervals plus PP Small phase .05 CEDAR AVE frames 78/79/148/149; tune only; no new scoring',
            'historical_natural_intervals': natural, 'historical_frame_rows': frames,
            'pp_synthetic_frames': synthetic, 'artifact_sha256': provenance,
            'summary': {'natural_intervals': len(natural), 'historical_unique_frame_rows': len(frames),
                        'synthetic_frames': len(synthetic), 'crossing_quad_occurrences': len(crossing),
                        'crossing_with_original_visible_pixels': sum(q['original_visible_pixels'] > 0 for q in crossing),
                        'uncovered_original_pixels': sum(q['uncovered_original_pixels'] for q in crossing)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-check-only', action='store_true')
    parser.add_argument('--taxonomy', type=Path)
    parser.add_argument('--historical-root', type=Path)
    parser.add_argument('--pp-root', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    cv2.setNumThreads(1)
    result = {'boundary_checks': boundary_checks(), 'untimed': True, 'new_dependencies': []}
    if not args.self_check_only:
        if not all([args.taxonomy, args.historical_root, args.pp_root]):
            parser.error('Retained audit requires taxonomy, historical-root and pp-root')
        result.update(audit_retained(args.taxonomy, args.historical_root, args.pp_root))
    result['source_sha256'] = {name: digest(Path(name)) for name in
                               ['shield/motion.py', 'shield/render.py', 'bench/q1_edge_audit.py']}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'out': str(args.out), 'summary': result.get('summary'),
                      'boundary_checks': len(result['boundary_checks'])}))


if __name__ == '__main__':
    main()

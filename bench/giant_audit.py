"""Read-only tune giant diagnosis. No detector policy or scoring changes.

Uses existing NumPy (BSD-3-Clause) and OpenCV (Apache-2.0). Input fixtures retain
fixtures/ATTRIBUTION.md licenses; decoded images are benchmark-only, no music.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import zipfile

import cv2
import numpy as np

from shield.engine import MaskingEngine
from shield.motion import MotionHistory
from shield.render import Renderer
from shield.types import Detection, Frame


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def area(quad):
    points = np.asarray(quad, dtype=float)
    return float(abs(np.dot(points[:, 0], np.roll(points[:, 1], -1)) -
                     np.dot(points[:, 1], np.roll(points[:, 0], -1))) / 2)


def checked_bundle(directory):
    plan = read(directory / 'bundle.json')
    if digest(directory / 'bundle.json') != (directory / 'bundle.sha256').read_text().strip():
        raise ValueError('Sealed manifest hash mismatch')
    if plan['clip'] != 'mazatlan-aquiles':
        raise ValueError('This diagnosis is restricted to Mazatlan tune variants')
    # Grade files are deliberately outside this audit and may be owned by root.
    identities = {}
    for name in ('input.mp4', 'masked.detections.json', 'masked.motion.json',
                 'masked.masks.json', 'masked.mask-pixels.zip', 'engine.json'):
        path = directory / name
        identity = {'sha256': digest(path), 'bytes': path.stat().st_size}
        if identity != plan['artifacts'][name]:
            raise ValueError('Sealed artifact mismatch: ' + name)
        identities[name] = identity
    return plan, identities


class RecordedLane:
    """Release exact historical detections on their source offer; no inference."""
    def __init__(self, rows, identities):
        self.rows = {row['source_index']: row for row in rows}
        self.results = []
        self.seen = 0
        self.identities = identities

    def offer(self, frame):
        row = self.rows.get(frame.index)
        if row is not None:
            if row['source_pts'] != frame.pts or row['completed_at'] != frame.pts:
                raise ValueError('Receipt does not use the ideal source completion clock')
            quads = row['quads']
            self.identities[id(quads)] = row
            self.results.append(Detection(row['lane'], frame.index, quads, row['completed_at']))
            self.seen += 1

    def drain(self):
        result, self.results = self.results, []
        return result

    def close(self):
        pass

    @property
    def stats(self):
        return {'replayed': self.seen}


class TracedMotion:
    """Observe real MotionHistory projections by receipt identity, never proximity."""
    def __init__(self, history, identities):
        self.history, self.identities = history, identities
        self.calls = {}

    def add(self, index, pixels):
        self.history.add(index, pixels)

    def project_many(self, quads, source, target, deadline=None):
        row = self.identities[id(quads)]
        if row['source_index'] != source:
            raise ValueError('Receipt identity/source mismatch')
        projected = self.history.project_many(quads, source, target, deadline)
        self.calls.setdefault(target, []).append({
            'lane': row['lane'], 'source_index': source, 'completed_at': row['completed_at'],
            'connected': projected is not None, 'raw_quads': quads,
            'projected_quads': projected,
        })
        return projected


def replay(directory, threshold):
    plan, identities = checked_bundle(directory)
    stored = read(directory / 'masked.masks.json')
    diagnostics = read(directory / 'masked.motion.json')
    detections = read(directory / 'masked.detections.json')
    options, fps = plan['options'], plan['source_fps']
    history = MotionHistory(max_frames=max(120, math.ceil(fps * options['delay_seconds']) + options['before'] + 4),
                            analysis_width=options['motion_width'], mode=options['motion_mode'],
                            phase_min_response=options['motion_min_response'])
    receipt_ids = {}
    motion = TracedMotion(history, receipt_ids)
    lanes = {name: RecordedLane(rows, receipt_ids) for name, rows in detections.items()}
    engine = MaskingEngine(lanes, {**options, 'fps': fps}, motion=motion)
    cap = cv2.VideoCapture(str(directory / 'input.mp4'))
    if not cap.isOpened():
        raise RuntimeError('Cannot decode sealed input')
    seen = emitted = 0
    rows, mismatches = [], []
    renderer = Renderer(padding=options['padding'])

    def present(until, inclusive, masks):
        nonlocal emitted
        while emitted < seen:
            deadline = emitted / fps + options['delay_seconds']
            if deadline > until or (not inclusive and deadline == until):
                break
            batch = engine.poll(now=deadline)
            if not batch:
                raise RuntimeError('Replay presentation stalled')
            for frame in batch:
                original = stored[emitted]
                if frame.index != emitted:
                    raise ValueError('Replay reordered frames')
                comparisons = {
                    'quads_exact': frame.quads == original['quads'],
                    'coverage_exact': asdict(frame.coverage) == original['coverage'],
                    'state_exact': (frame.state, frame.protected, frame.slate) ==
                                   (original['state'], original['protected'], original['slate']),
                    'mask_hash_exact': hashlib.sha256(frame.mask.tobytes()).hexdigest() == original['mask_sha256'],
                    'raster_archive_exact': np.packbits(frame.mask > 0, bitorder='little').tobytes() ==
                                            masks.read(f'{emitted:08d}.bin'),
                }
                if not all(comparisons.values()):
                    mismatches.append({'frame': emitted, **comparisons})
                if original['mask_fraction'] >= threshold:
                    calls = motion.calls[emitted]
                    connected = [call for call in calls if call['connected']]
                    pixels = np.zeros((*frame.mask.shape, 3), np.uint8)
                    size = frame.mask.size

                    def fraction(quads):
                        return float((renderer.render(pixels, quads, 'LIVE', len(quads)).mask > 0).mean())

                    components = []
                    for call in connected:
                        for i, (raw, projected) in enumerate(zip(call['raw_quads'], call['projected_quads'], strict=True)):
                            components.append({'lane': call['lane'], 'source_index': call['source_index'],
                                               'quad_index': i, 'raw_quad': raw, 'projected_quad': projected,
                                               'historical_confidence': None,
                                               'raw_fraction': area(raw) / size,
                                               'projected_fraction': area(projected) / size})
                    largest = max(components, key=lambda c: c['projected_fraction'], default=None)
                    if largest:
                        largest = {**largest, 'individual_padded_fraction': fraction([largest['projected_quad']])}
                    rows.append({'frame': emitted, 'mask_fraction': original['mask_fraction'],
                                 'state': frame.state, 'coverage': asdict(frame.coverage),
                                 'projection_calls': calls, 'components': components, 'largest': largest,
                                 'lane_mask_fractions': {name: fraction([c['projected_quad'] for c in components if c['lane'] == name])
                                                         for name in lanes},
                                 'connected_raw_union_fraction': fraction([c['raw_quad'] for c in components]),
                                 'without_raw_giants_fraction': fraction([c['projected_quad'] for c in components if c['raw_fraction'] < threshold]),
                                 **comparisons})
                motion.calls.pop(emitted, None)
                emitted += 1

    try:
        with zipfile.ZipFile(directory / 'masked.mask-pixels.zip') as masks:
            for index in range(plan['frames']):
                ok, pixels = cap.read()
                if not ok:
                    raise RuntimeError('Sealed input truncated')
                pts = index / fps
                present(pts, False, masks)
                engine.submit(Frame(index, pts, pixels), now=pts)
                seen += 1
                actual = {'frame': index, 'pts': pts, **history.diagnostics(index)}
                if actual != diagnostics[index]:
                    mismatches.append({'motion_frame': index, 'actual': actual, 'stored': diagnostics[index]})
                present(pts, True, masks)
            if cap.read()[0]:
                raise RuntimeError('Unexpected extra source frame')
            engine.end(seen - 1)
            while not engine.drained:
                present(emitted / fps + options['delay_seconds'], True, masks)
    finally:
        cap.release()
        engine.close()
    if any(lane.seen != len(lane.rows) for lane in lanes.values()) or emitted != len(stored):
        raise ValueError('Replay did not consume every frame/receipt')
    return {'bundle': str(directory), 'bundle_sha256': digest(directory / 'bundle.json'),
            'input_artifacts': identities, 'mode': 'historical-receipt-replay-no-inference',
            'historical_confidence_available': False, 'threshold': threshold,
            'frames': emitted, 'selected_frames': len(rows), 'mismatches': mismatches,
            'exact_replay': not mismatches, 'rows': rows, 'corpus_metrics': None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--threshold', type=float, default=.5)
    args = parser.parse_args()
    if not math.isfinite(args.threshold) or not 0 < args.threshold <= 1:
        parser.error('threshold must be in (0, 1]')
    cv2.setNumThreads(1)
    result = replay(args.bundle.resolve(), args.threshold)
    with args.out.open('x') as output:
        output.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('bundle', 'frames', 'selected_frames', 'exact_replay')}))
    if not result['exact_replay']:
        raise SystemExit('Historical replay mismatch; provenance claims unavailable')


if __name__ == '__main__':
    main()

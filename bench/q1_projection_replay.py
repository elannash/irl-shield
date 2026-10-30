"""Replay one retained tune clip's cached detections through the real engine.

No detector inference, OCR, encoding, scoring, or truth edits. Existing NumPy
(BSD-3-Clause) and OpenCV (Apache-2.0); footage licenses stay in ATTRIBUTION.md.
This is diagnostic replay, never a timing or content-quality comparison.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path

import cv2
import numpy as np

from bench.offline_quality import render_offline
from bench.q1_edge_audit import digest
from shield.motion import MotionHistory


class CachedDetector:
    def __init__(self, rows, width, fps, rate):
        expected = [i for i in range(150) if i == 0 or
                    int(np.floor(i * rate / fps + 1e-9)) > int(np.floor((i - 1) * rate / fps + 1e-9))]
        assert [r['source_index'] for r in rows] == expected, 'Cached schedule does not match the policy'
        self.rows, self.width, self.cursor = rows, width, 0

    def detect_quads(self, pixels):
        row = self.rows[self.cursor]
        self.cursor += 1
        assert list(pixels.shape) == row['detector_input_shape'], 'Replay resized detector input differently'
        return (np.asarray(row['quads']).reshape(-1, 4, 2) * pixels.shape[1] / self.width).tolist()


class ProjectionTrace(MotionHistory):
    def __init__(self, targets, **options):
        super().__init__(**options)
        self.targets, self.receipts = targets, []

    def project_many(self, quads, source_index, target_index, deadline=None):
        result = super().project_many(quads, source_index, target_index, deadline)
        if target_index in self.targets:
            if result is not None:
                assert len(result) == len(quads), 'Projection silently dropped part of a receipt'
            self.receipts.append({'source': source_index, 'target': target_index,
                                  'source_quads': quads, 'projected_quads': result,
                                  'unresolved_motion_frames': [i for i in range(min(source_index, target_index) + 1,
                                                                              max(source_index, target_index) + 1)
                                                               if not self.diagnostics(i)['valid']]})
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--targets', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    cv2.setNumThreads(1)
    targets = {int(n) for n in args.targets.split(',')}
    options = json.loads(args.card.read_text())['options']
    records_path = args.prefix.with_suffix('.masks.json')
    detections_path = args.prefix.with_suffix('.detections.json')
    records = json.loads(records_path.read_text())
    detections = json.loads(detections_path.read_text())
    capture = cv2.VideoCapture(str(args.source), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
    assert capture.isOpened(), 'Cannot open retained source'
    fps = capture.get(cv2.CAP_PROP_FPS)
    assert len(records) == 150 and int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) == 150
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    backends = {lane: CachedDetector(rows, width, fps, options[lane + '_rate_hz'])
                for lane, rows in detections.items()}
    motion = ProjectionTrace(targets, max_frames=120, analysis_width=options['motion_width'],
                             mode=options['motion_mode'], phase_min_response=options.get('motion_min_response', .5))
    observed = []

    def frames():
        try:
            for index in range(150):
                ok, pixels = capture.read()
                assert ok, f'Retained source truncated at {index}'
                yield pixels
        finally:
            capture.release()

    def emit(frame):
        row = records[frame.index]
        exact_mask = sha256(frame.mask.tobytes()).hexdigest() == row['mask_sha256']
        exact_quads = frame.quads == row['quads']
        same_coverage = (frame.coverage.ok == row['coverage']['ok'] and
                         frame.coverage.reason == row['coverage']['reason'])
        observed.append({'frame': frame.index, 'exact_mask': exact_mask, 'exact_quads': exact_quads,
                         'same_coverage': same_coverage, 'state': frame.state,
                         'quad_max_abs_difference': float(np.max(np.abs(np.asarray(frame.quads) - np.asarray(row['quads']))))
                         if frame.quads and len(frame.quads) == len(row['quads']) else None})

    run = render_offline(frames(), fps, backends, options, emit, motion=motion)
    assert len(observed) == 150 and all(b.cursor == len(b.rows) for b in backends.values())
    artifacts = [args.source, args.card, records_path, detections_path]
    sources = ['shield/motion.py', 'shield/render.py', 'shield/engine.py',
               'bench/offline_quality.py', 'bench/q1_projection_replay.py']
    result = {'scope': 'Cached detections, actual decoded frames and actual MotionHistory/MaskingEngine/Renderer; no new scoring',
              'untimed': True, 'options': options, 'source_fps': fps,
              'artifact_sha256': {str(p): digest(p) for p in artifacts},
              'source_sha256': {p: digest(p) for p in sources},
              'frames': observed, 'projection_receipts': motion.receipts,
              'summary': {'frames': len(observed),
                          'exact_masks': sum(r['exact_mask'] for r in observed),
                          'exact_quads': sum(r['exact_quads'] for r in observed),
                          'same_coverage': sum(r['same_coverage'] for r in observed),
                          'projection_receipts': len(motion.receipts),
                          'unresolved_receipts': sum(r['projected_quads'] is None for r in motion.receipts),
                          'partial_receipt_drops': 0},
              'new_model_calls': 0, 'new_ocr_calls': 0,
              'motion_diagnostics': run['motion']}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'out': str(args.out), **result['summary']}))


if __name__ == '__main__':
    main()

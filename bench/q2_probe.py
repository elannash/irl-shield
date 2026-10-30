"""Bounded Q2 recognizer challenges; no scorer changes or performance claims.

Images use original synthetic labels and existing OpenCV Hershey glyphs. The
optional pavement input is a licensed tune frame, never demo-ready. Dependencies
and the pinned model are already licensed in the project manifests.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time

import cv2
import numpy as np

from bench.q2_confirmers import create_confirmer
from shield.quad_confirmation import QuadConfirmationDetector
from shield.render import Renderer


def challenges():
    """Equal-area candidates: street/store/plate/number, plus oblique versions."""
    width, height = 1280, 720
    quad = np.float32([[32, 24], [1248, 24], [1248, 696], [32, 696]])
    oblique = np.float32([[16, 64], [1248, 16], [1136, 704], [144, 656]])
    for kind, lines in (('street', ['PINE STREET']), ('store', ['CEDAR', 'MARKET']),
                        ('plate', ['BXR219']), ('number', ['824'])):
        sign = np.full((672, 1216, 3), (220, 230, 220), np.uint8)
        line_height = 672 // len(lines)
        for index, text in enumerate(lines):
            # Stretch only the synthetic sign plane; perspective is then applied
            # to the entire plane so the provided quad is the exact inverse warp.
            size, baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 3, 8)
            glyphs = np.full((size[1] + baseline + 24, size[0] + 24, 3), 230, np.uint8)
            cv2.putText(glyphs, text, (12, size[1] + 12), cv2.FONT_HERSHEY_SIMPLEX,
                        3, (5, 5, 5), 8, cv2.LINE_AA)
            plane = cv2.resize(glyphs, (1112, line_height - 48))
            top = index * line_height + 24
            sign[top:top + plane.shape[0], 52:1164] = plane
        origin = np.float32([[0, 0], [1215, 0], [1215, 671], [0, 671]])
        for label, points in (('front', quad), ('oblique', oblique)):
            image = cv2.warpPerspective(sign, cv2.getPerspectiveTransform(origin, points),
                                        (width, height), borderValue=(100, 110, 120))
            yield f'{kind}-{label}', image, points.tolist(), True


class Replayed:
    metadata = {'name': 'q2-probe-quad', 'detector_families': ['paddleocr']}

    def __init__(self, quad):
        self.quad = quad

    def detect_quads(self, pixels):
        return [self.quad]

    def close(self):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--pavement', type=Path)
    parser.add_argument('--cache-dir', type=Path, required=True)
    parser.add_argument('--provider', default='cuda', choices=('cpu', 'cuda'))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    cv2.setNumThreads(1)
    cases = list(challenges())
    if args.pavement:
        pixels = cv2.imread(str(args.pavement))
        if pixels is None:
            raise ValueError('Cannot read pavement input')
        height, width = pixels.shape[:2]
        # Retained Small .3 frame45 geometry, expressed by pixel edges.
        cases.insert(0, ('pavement', pixels,
                        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], False))
    confirmer = create_confirmer({'cache_dir': args.cache_dir, 'provider': args.provider, 'threads': 2})
    rows = []
    try:
        for name, pixels, quad, expected in cases:
            detector = QuadConfirmationDetector(Replayed(quad), confirmer)
            began = time.perf_counter()
            result = detector.detect_quads(pixels)
            elapsed = time.perf_counter() - began
            before = Renderer().render(pixels, [quad], 'LIVE', 1)
            after = Renderer().render(pixels, result, 'LIVE', len(result))
            image = args.out / f'{name}-input.png'
            cv2.imwrite(str(image), pixels)
            cv2.imwrite(str(args.out / f'{name}-before.png'), before.pixels)
            cv2.imwrite(str(args.out / f'{name}-after.png'), after.pixels)
            rows.append({'case': name, 'expected_retained': expected, 'retained': bool(result),
                         'pass': bool(result) == expected, 'quad': quad,
                         'input_path': str(image), 'input_sha256': hashlib.sha256(pixels.tobytes()).hexdigest(),
                         'input_png_sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
                         'reading': confirmer.last_reading, 'stats': detector.stats,
                         'before_mask_fraction': float((before.mask > 0).mean()),
                         'after_mask_fraction': float((after.mask > 0).mean()),
                         'diagnostic_wall_seconds': elapsed})
    finally:
        confirmer.close()
    result = {'mode': 'untimed-challenge-probe', 'quality_scorecard': False,
              'policy': {'large_fraction': .5, 'recognizer_confidence': .5},
              'metadata': confirmer.metadata, 'rows': rows, 'pass': all(row['pass'] for row in rows),
              'no_realtime_or_corpus_acceptance': True}
    (args.out / 'probe.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'pass': result['pass'], 'artifact': str(args.out / 'probe.json'),
                      'cases': [{key: row[key] for key in ('case', 'retained', 'pass', 'reading')} for row in rows]}))


if __name__ == '__main__':
    main()

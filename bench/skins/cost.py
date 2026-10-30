"""720p/24-mask paint cost, executable ONLY by the canonical EX queue."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import time

import cv2
import numpy as np
import psutil

from shield.skins import SkinPainter
from shield.skins.paint import SKINS
from .synthetic import cost_scene


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frames', type=int, default=300)
    parser.add_argument('--warmup', type=int, default=30)
    parser.add_argument('--skin', choices=(*SKINS, 'all'), default='all')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.frames < 30 or args.warmup < 1:
        parser.error('Need at least 30 measured frames and one warmup')
    cv2.setNumThreads(1)
    frame, regions = cost_scene()
    painter = SkinPainter()
    rows = []
    for skin in SKINS if args.skin == 'all' else [args.skin]:
        for _ in range(args.warmup):
            result = painter.paint(frame, regions, skin=skin)
        durations = []
        start_cpu = time.process_time_ns()
        for _ in range(args.frames):
            start = time.perf_counter_ns()
            result = painter.paint(frame, regions, skin=skin)
            durations.append((time.perf_counter_ns() - start) / 1e6)
        cpu_seconds = (time.process_time_ns() - start_cpu) / 1e9
        rows.append({'requested_skin': skin, 'actual_skin': result.skin,
                     'fallback_reason': result.fallback_reason, 'frames': args.frames,
                     'median_ms': float(np.median(durations)), 'p95_ms': float(np.percentile(durations, 95)),
                     'cpu_seconds': cpu_seconds, 'cpu_percent_of_one_core_at_30fps': cpu_seconds / args.frames * 30 * 100,
                     'p95_within_2ms': bool(np.percentile(durations, 95) <= 2),
                     'samples_ms': durations})
    root = Path(__file__).resolve().parents[2]
    paths = list((root/'shield/skins').glob('*.py')) + list((root/'bench/skins').glob('*.py'))
    paths += list((root/'fixtures/skins').glob('*'))
    card = {'scope': 'Paint only, uint8 BGR 1280x720, 24 opaque 160x48 masks, text-height 24, no detector/transport. Static scene, warmed caches.',
            'host': platform.node(), 'platform': platform.platform(), 'opencv': cv2.__version__,
            'opencv_threads': cv2.getNumThreads(), 'warmup_frames': args.warmup,
            'rss_bytes_after': psutil.Process().memory_info().rss, 'rows': rows,
            'source_sha256': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(card, indent=2) + '\n')
    print(json.dumps({row['requested_skin']: {k: row[k] for k in ('median_ms', 'p95_ms', 'cpu_percent_of_one_core_at_30fps')} for row in rows}, indent=2))
    return 0 if all(row['p95_within_2ms'] and row['actual_skin'] == row['requested_skin'] for row in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())

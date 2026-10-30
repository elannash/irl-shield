"""Canonical queue-only independent OCR of synthetic Frosted attack views."""
import argparse
import hashlib
import json
import os
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--expected-python', type=Path, required=True)
    parser.add_argument('--tesseract', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if not args.cache.resolve().is_relative_to(root) or not args.out.resolve().is_relative_to(root):
        raise ValueError('OCR cache and receipt must be inside the dedicated W5 mirror')
    paths = list((root/'shield/skins').glob('*.py')) + list((root/'bench/skins').glob('*.py'))
    paths += [root/name for name in ('bench/judges.py', 'bench/vision.py', 'bench/independence.py',
                                     'bench/onnx_detectors.py', 'models/manifest.json', 'models/prepare.py',
                                     'Sources/VisionBridge/main.swift')]
    card = {'schema_version': 1, 'status': 'running', 'stage': 'preflight',
            'environment': {name: os.environ.get(name) for name in
                ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                 'VECLIB_MAXIMUM_THREADS', 'OPENCV_FOR_THREADS_NUM',
                 'PYTHONDONTWRITEBYTECODE', 'PYTHONNOUSERSITE', 'PATH')},
            'fixture': 'W5 synthetic paint-only control',
            'candidate': 'vision-accurate', 'options': {},
            'source_sha256': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}}
    try:
        from .preflight import check_environment
        card['preflight'] = check_environment(root, args.expected_python, args.tesseract)
        from bench.judges import Judges
        from shield.skins import SkinPainter
        from .judging import judge_output
        from .synthetic import scene
        source, regions = scene()
        painted = SkinPainter().paint(source, regions)
        card['stage'] = 'persistent-judges-start'
        judges = Judges('vision-accurate', args.cache)
        try:
            card['stage'] = 'output-judging'
            result = judge_output(judges, source, painted, regions, candidate='vision-accurate', options={})
        finally:
            judges.close()
        card.update(result)
        card['judge_runtime'] = judges.metadata
        card['paddle_runtime'] = judges.paddle.metadata
        card['status'] = 'complete'
        if not card['primary_independent_truth']:
            raise RuntimeError('No independent input reading; output-only silence cannot prove hiding')
        card['stage'] = 'complete'
    except Exception as error:
        card.update(status='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(card, indent=2) + '\n')
    print(json.dumps({'passed': card['passed'], 'leaks': card['credible_output_leaks'],
                      'primary_truth_readings': len(card['primary_independent_truth'])}, indent=2))
    return 0 if card['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

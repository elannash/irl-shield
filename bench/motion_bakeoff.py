"""E1: change only global-motion policy on exact retained tune input bytes.

Uses existing licensed fixtures, detectors, judges and render modules. Output is
ideal/offline content quality, never an accepted sustained performance receipt.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

import cv2

from bench import offline_quality as quality
from bench.judges import Judges


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-run', required=True)
    parser.add_argument('--prefix', default='e1-motion')
    args = parser.parse_args()
    cv2.setNumThreads(1)
    root = Path(__file__).resolve().parents[1]
    if any(Path(value).name != value for value in (args.source_run, args.prefix)):
        parser.error('Run names must be basenames')
    source_dir = root / 'out' / args.source_run
    source_card = json.loads((source_dir / 'scorecard.json').read_text())
    candidate = source_card['candidate']
    clips = [clip for clip in json.loads((root / 'fixtures/manifest.json').read_text())['clips']
             if clip['split'] == 'tune']
    if len(clips) != 7 or source_card.get('split') != 'tune':
        raise ValueError('E1 requires the complete seven-clip tune split')
    baseline = json.loads((root / 'bench/baseline.json').read_text())
    snapshot = quality._fingerprint()
    orchestrator_sha256 = digest(__file__)
    inputs = {}
    for clip in clips:
        for synthetic in (False, True):
            label = clip['id'] + ('-synthetic' if synthetic else '-natural')
            source = source_dir / (label + '-input.mp4')
            truth = source.with_suffix('.truth.json')
            inputs[label] = {'input_sha256': digest(source), 'truth_sha256': digest(truth)}
    for suffix, mode, floor in [('phase-050', 'phase', .5), ('phase-020', 'phase', .2),
                                ('phase-005', 'phase', .05), ('orb-050', 'orb', .5)]:
        run_id = args.prefix + '-' + suffix
        directory = root / 'out' / run_id
        directory.mkdir(parents=True, exist_ok=False)
        options = {**source_card['options'], 'motion_mode': mode, 'motion_min_response': floor}
        results, backends = [], None
        judge = Judges(candidate, root / 'out/judge-cache')
        try:
            for clip in clips:
                for synthetic in (False, True):
                    label = clip['id'] + ('-synthetic' if synthetic else '-natural')
                    source = directory / (label + '-input.mp4')
                    original = source_dir / source.name
                    shutil.copyfile(original, source)
                    shutil.copyfile(original.with_suffix('.truth.json'), source.with_suffix('.truth.json'))
                    if digest(source) != inputs[label]['input_sha256'] or digest(source.with_suffix('.truth.json')) != inputs[label]['truth_sha256']:
                        raise ValueError('E1 input bytes changed')
                    if backends is None:
                        backends = quality._make_backends(candidate, options, quality._media(source)['resolution'])
                    print(f'{run_id}: {label}', flush=True)
                    row = quality.run_file(source, directory / (label + '-masked.mp4'), candidate,
                                           options, judge=judge, backends=backends)
                    results.append({'clip': clip['id'], 'synthetic_variant': synthetic, **row})
                    (directory / 'progress.json').write_text(json.dumps(results, indent=2) + '\n')
        finally:
            judge.close()
            if backends:
                for backend in backends.values():
                    backend.close()
        if quality._fingerprint() != snapshot or digest(__file__) != orchestrator_sha256:
            raise RuntimeError('E1 code changed during evaluation')
        card = quality.build_scorecard(results, candidate, options, run_id=run_id, split='tune', baseline=baseline)
        card.update({'pipeline_sha256': snapshot,
                     'experiment': {'name': 'E1', 'source_run': args.source_run,
                                    'inputs': inputs, 'orchestrator_sha256': orchestrator_sha256, 'changed': ['motion_mode', 'motion_min_response'],
                                    'scope': 'Same source/model/options except listed motion policy; ideal/offline only'}})
        (directory / 'scorecard.json').write_text(json.dumps(card, indent=2) + '\n')
        print(json.dumps({key: card[key] for key in ('run_id', 'natural', 'synthetic', 'protected_fraction', 'masked_area_fraction', 'comparison_valid')}), flush=True)


if __name__ == '__main__':
    main()

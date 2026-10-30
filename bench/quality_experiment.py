"""One-knob tune experiment on retained input bytes, with the existing judges.

Uses only existing licensed fixtures/models/libraries. Ideal/offline quality
cannot establish a real-time gate pass. The caller holds a shared host lease.
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
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--candidate', choices=('vision-union','vision-accurate','vision-fast','ppocr-v5-mobile','ppocr-v6-tiny','ppocr-v6-small','ppocr-v6-medium'))
    parser.add_argument('--fast-candidate')
    parser.add_argument('--box-thresh', type=float)
    parser.add_argument('--accurate-rate-hz', type=float)
    parser.add_argument('--fast-rate-hz', type=float)
    parser.add_argument('--fast-width', type=int)
    parser.add_argument('--accurate-width', type=int)
    parser.add_argument('--A', dest='after', type=int)
    parser.add_argument('--padding', type=float)
    parser.add_argument('--motion-mode', choices=('phase', 'orb'))
    parser.add_argument('--motion-min-response', type=float)
    parser.add_argument('--limit-side-len', type=int)
    args = parser.parse_args()
    if any(Path(value).name != value or value in ('.', '..') for value in (args.source_run, args.run_id)):
        parser.error('Run names must be basenames')
    cv2.setNumThreads(1)
    root = Path(__file__).resolve().parents[1]
    source_dir = root / 'out' / args.source_run
    source_card = json.loads((source_dir / 'scorecard.json').read_text())
    candidate = args.candidate or source_card['candidate']
    clips = [clip for clip in json.loads((root / 'fixtures/manifest.json').read_text())['clips']
             if clip['split'] == 'tune']
    if len(clips) != 7 or source_card.get('split') != 'tune':
        raise ValueError('Experiments require all seven tune clips')
    changed = {key: value for key, value in vars(args).items()
               if key not in ('source_run', 'run_id') and value is not None
               and value != (source_card['candidate'] if key == 'candidate' else source_card['options'].get(key))}
    if len(changed) != 1:
        parser.error('Change exactly one option per experiment')
    options = {**source_card['options'], **{key:value for key,value in changed.items() if key != 'candidate'}}
    baseline = json.loads((root / 'bench/baseline.json').read_text())
    snapshot, orchestrator = quality._fingerprint(), digest(__file__)
    directory = root / 'out' / args.run_id
    directory.mkdir(parents=True, exist_ok=False)
    results, backends, inputs = [], None, {}
    judge = Judges(candidate, root / 'out/judge-cache')
    try:
        for clip in clips:
            for synthetic in (False, True):
                label = clip['id'] + ('-synthetic' if synthetic else '-natural')
                source = directory / (label + '-input.mp4')
                original = source_dir / source.name
                inputs[label] = {'input_sha256': digest(original), 'truth_sha256': digest(original.with_suffix('.truth.json'))}
                shutil.copyfile(original, source)
                shutil.copyfile(original.with_suffix('.truth.json'), source.with_suffix('.truth.json'))
                if digest(source) != inputs[label]['input_sha256'] or digest(source.with_suffix('.truth.json')) != inputs[label]['truth_sha256']:
                    raise ValueError('Experiment input bytes changed')
                if backends is None:
                    backends = quality._make_backends(candidate, options, quality._media(source)['resolution'])
                print(f'{args.run_id}: {label}; change={changed}', flush=True)
                row = quality.run_file(source, directory / (label + '-masked.mp4'), candidate,
                                       options, judge=judge, backends=backends)
                results.append({'clip': clip['id'], 'synthetic_variant': synthetic, **row})
                (directory / 'progress.json').write_text(json.dumps(results, indent=2) + '\n')
    finally:
        errors=[]
        for resource in [judge, *(backends.values() if backends else [])]:
            try:
                resource.close()
            except Exception as error:
                errors.append(error)
        if errors:
            raise ExceptionGroup('Experiment cleanup failed', errors)
    if quality._fingerprint() != snapshot or digest(__file__) != orchestrator:
        raise RuntimeError('Experiment code changed during evaluation')
    card = quality.build_scorecard(results, candidate, options, run_id=args.run_id, split='tune', baseline=baseline)
    card.update({'pipeline_sha256': snapshot,
                 'experiment': {'source_run': args.source_run, 'source_scorecard_sha256': digest(source_dir / 'scorecard.json'),
                                'inputs': inputs, 'orchestrator_sha256': orchestrator, 'changed': changed,
                                'scope': 'Same input/model/options except listed change; ideal/offline only'}})
    (directory / 'scorecard.json').write_text(json.dumps(card, indent=2) + '\n')
    print(json.dumps({key: card[key] for key in ('run_id', 'natural', 'synthetic', 'protected_fraction', 'masked_area_fraction', 'comparison_valid')}), flush=True)


if __name__ == '__main__':
    main()

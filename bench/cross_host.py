"""Sealed clocked measurements, graded later without changing their processing host.

Uses existing Python/NumPy/OpenCV dependencies and existing licensed fixtures.
Bundles are benchmark-only, contain no audio, and are not demo-ready assets.
The hash manifest detects accidental changes; it is not a digital signature.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path

from bench import clocked_pipeline
from bench.clocked_pipeline import file_sha256, host_environment


def bundle_file(directory, relative):
    path = directory / relative
    if Path(relative).is_absolute() or not path.resolve().is_relative_to(directory.resolve()):
        raise ValueError('Measurement artifact escapes its bundle')
    return path


def validate_performance(result, candidate, pipeline_sha256, expected_options):
    output = Path(result['output'])
    performance = result['performance']
    raw = json.loads(output.with_suffix('.performance.json').read_text())
    if json.loads(json.dumps(performance)) != raw:
        raise ValueError('Embedded and raw performance receipts differ')
    if performance['pipeline_sha256'] != pipeline_sha256 or performance['candidate'] != candidate:
        raise ValueError('Measurement performance source/candidate identity mismatch')
    if json.loads(json.dumps(performance['options'])) != json.loads(json.dumps(expected_options)):
        raise ValueError('Measurement performance options differ from its plan')
    for key, path in (('source_sha256', Path(result['source'])), ('output_sha256', output),
                      ('mask_pixels_sha256', output.with_suffix('.mask-pixels.zip'))):
        if performance[key] != file_sha256(path):
            raise ValueError(f'Measurement performance {key} mismatch')
    for suffix in ('.masks.json', '.egress.json'):
        if not output.with_suffix(suffix).is_file():
            raise ValueError(f'Measurement lacks {suffix}')


def validate_card(card, directory):
    for result in card['clips']:
        validate_performance(result, card['candidate'], card['pipeline_sha256'], card['options'])
    sustained = card['sustained']
    if sustained is not None:
        matches = [result for result in card['clips']
                   if result['performance']['source_sha256'] == sustained['source_sha256']]
        if not matches:
            raise ValueError('Measurement sustained source differs from every retained input')
        options = {**card['options'], 'repeat_seconds': sustained['options']['repeat_seconds']}
        validate_performance({'source': matches[0]['source'], 'output': str(directory / 'sustained-masked.mp4'),
                              'performance': sustained}, card['candidate'], card['pipeline_sha256'], options)


def seal_measurement(card, directory):
    """Write an exclusive immutable plan after all timing, without any judge."""
    directory = Path(directory)
    card = deepcopy(card)
    if card['pipeline_sha256'] != clocked_pipeline.fingerprint():
        raise ValueError('Measurement source identity changed before sealing')
    validate_card(card, directory)
    for result in card['clips']:
        result['processing_paths'] = {key: result[key] for key in ('source', 'output', 'truth')}
        for key in ('source', 'output', 'truth'):
            result[key] = str(Path(result[key]).resolve().relative_to(directory.resolve()))
    artifacts = {str(path.relative_to(directory)): {'sha256': file_sha256(path), 'bytes': path.stat().st_size}
                 for path in sorted(directory.rglob('*')) if path.is_file()}
    plan = {'schema_version': 1, 'status': 'awaiting-grading', 'card': card,
            'processing_environment': host_environment(),
            'pipeline_sha256': card['pipeline_sha256'], 'artifacts': artifacts,
            'grading_contract': 'bench.clocked_bench.score_video and aggregate_card; final source cycle after warmup',
            'scope': 'Benchmark-only exact input/output/truth/mask bytes; no quality score exists until grading'}
    path = directory / 'measurement-plan.json'
    with path.open('x') as stream:
        stream.write(json.dumps(plan, indent=2) + '\n')
    with path.with_suffix('.sha256').open('x') as stream:
        stream.write(file_sha256(path) + '\n')
    print(json.dumps({'measurement_plan': str(path), 'status': plan['status']}), flush=True)
    return plan


def verify_measurement(plan_path):
    """Validate code identity and every sealed byte before opening OCR engines."""
    plan_path = Path(plan_path)
    directory = plan_path.parent
    if file_sha256(plan_path) != plan_path.with_suffix('.sha256').read_text().strip():
        raise ValueError('Measurement plan hash mismatch')
    plan = json.loads(plan_path.read_text())
    if plan['schema_version'] != 1 or plan['status'] != 'awaiting-grading':
        raise ValueError('Unsupported measurement plan')
    if plan['pipeline_sha256'] != clocked_pipeline.fingerprint() or plan['card']['pipeline_sha256'] != plan['pipeline_sha256']:
        raise ValueError('Measurement source identity mismatch; grade the frozen source snapshot')
    for name, expected in plan['artifacts'].items():
        path = bundle_file(directory, name)
        if path.stat().st_size != expected['bytes'] or file_sha256(path) != expected['sha256']:
            raise ValueError(f'Measurement artifact hash mismatch: {name}')
    relocated_card = deepcopy(plan['card'])
    for result in relocated_card['clips']:
        for key in ('source', 'output', 'truth'):
            if result[key] not in plan['artifacts']:
                raise ValueError(f'Measurement plan omitted {key}')
            bundle_file(directory, result[key])
        result['source'] = str(bundle_file(directory, result['source']))
        result['output'] = str(bundle_file(directory, result['output']))
    validate_card(relocated_card, directory)
    return plan


def grade(plan_path, judge=None):
    """Score actual encoded frames with existing judges, outside every timed run."""
    from bench.clocked_bench import aggregate_card, score_video

    plan_path = Path(plan_path)
    plan = verify_measurement(plan_path)
    card = deepcopy(plan['card'])
    directory = plan_path.parent
    card['processing_environment'] = plan['processing_environment']
    card['grading_environment'] = host_environment()
    owned = judge is None
    try:
        if owned:
            from bench.judges import Judges
            judge = Judges(card['candidate'], directory.parent / 'judge-cache')
        for result in card['clips']:
            for key in ('source', 'output', 'truth'):
                result[key] = str(bundle_file(directory, result[key]))
            truth = json.loads(Path(result.pop('truth')).read_text())
            result.update(score_video(result['source'], result['output'], judge, truth))
        card['judges'] = list(judge.names)
    finally:
        if owned and judge is not None:
            judge.close()
    verify_measurement(plan_path)
    card['measurement_plan_sha256'] = file_sha256(plan_path)
    card['grading_scope'] = 'Actual encoded Linux/other-host output graded after timing; processing environment and metrics preserved'
    return aggregate_card(card, directory)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('verify', 'grade'))
    parser.add_argument('--plan', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.action == 'verify':
        plan = verify_measurement(args.plan)
        print(json.dumps({'verified': str(args.plan), 'artifacts': len(plan['artifacts'])}))
        return plan
    return grade(args.plan)


if __name__ == '__main__':
    main()

"""One-shot fresh heldout evaluation through the reviewed quality bundle contract.

Render once on Linux, transfer the sealed directory, then judge once on Mac.
No runtime detector, renderer, scoring algorithm or family override is added.
"""
import argparse
import json
from pathlib import Path
import platform
import subprocess

from bench import quality_bundle as bundle

CODE_ROOT = Path(__file__).resolve().parents[1]


def exclusive_json(path, value):
    """Persist the spent attempt before the first physical render or OCR call."""
    with Path(path).open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')
        stream.flush()
        import os
        os.fsync(stream.fileno())


def source_identity(root):
    quality = bundle.modules(root)
    return {'pipeline_sha256': quality._fingerprint(),
            'orchestrator_sha256': bundle.digest(bundle.__file__),
            'heldout_orchestrator_sha256': bundle.digest(__file__)}


def start(*, root, dataset, dataset_sha256, policy, policy_sha256, policy_commit,
          directory, lock_root, cache_root=None, state_directory=None):
    root, dataset, policy, directory = map(Path, (root, dataset, policy, directory))
    if bundle.digest(dataset) != dataset_sha256 or bundle.digest(policy) != policy_sha256:
        raise ValueError('Frozen dataset or policy SHA-256 differs')
    # Tracked scorecards retain spent state when scratch markers are absent.
    tracked = subprocess.check_output(
        ['git', '-C', str(CODE_ROOT), 'ls-files', '-z', '--', 'bench/results/*.json'], text=True)
    for name in filter(None, tracked.split('\0')):
        result = json.loads((CODE_ROOT / name).read_text())
        if result.get('heldout_freeze', {}).get('dataset_sha256') == dataset_sha256:
            raise ValueError('Heldout dataset already spent by tracked result: ' + name)
    commit = subprocess.check_output(['git', '-C', str(CODE_ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    if policy_commit != commit:
        raise ValueError('Final policy commit must equal the executing source checkout HEAD')
    manifest, snapshot, _ = bundle.frozen_dataset(dataset)
    config_snapshot = policy.read_bytes()
    config = json.loads(config_snapshot)
    from bench.metrics import validate_area_ceiling
    from bench.independence import policy_metadata
    validate_area_ceiling(config['options'].get('area_ceiling'), config['options'].get('area_ceiling_basis'), required=True)
    policy_metadata(config['candidate'], config['options'])
    if cache_root is not None and state_directory is None:
        raise ValueError('Read-only cache override requires a separate writable one-shot state directory')
    for row in manifest['inputs']:
        for name, key in (('source', 'source_sha256'), ('truth', 'truth_sha256')):
            if bundle.digest(bundle.dataset_file(root, row[name], cache_root)) != row[key]:
                raise ValueError('Frozen heldout media/truth changed: ' + row[name])
    if directory.exists():
        raise FileExistsError(directory)
    identity = {'dataset_sha256': dataset_sha256, 'policy_sha256': policy_sha256,
                'policy_commit': policy_commit, **source_identity(root)}
    marker = (Path(state_directory) / (dataset_sha256 + '.started.json') if state_directory is not None
              else bundle.checked_file(root, manifest['evaluation_marker']))
    marker.parent.mkdir(parents=True, exist_ok=True)
    exclusive_json(marker, {**identity, 'status': 'started', 'directory': str(directory.resolve())})
    directory.mkdir(parents=True, exist_ok=False)
    (directory / 'dataset.json').write_bytes(snapshot)
    (directory / 'policy.json').write_bytes(config_snapshot)
    bundle.write_json(directory / 'inputs.json', {'fixture_manifest_sha256': dataset_sha256,
                                                'clips': manifest['inputs']})
    state = {**identity, 'status': 'rendering', 'completed': [], 'benchmark_only': True,
             'demo_ready': False, 'real_time_verified': False}
    bundle.write_json(directory / 'evaluation.json', state)
    try:
        for row in manifest['inputs']:
            label = row['clip'] + ('-synthetic' if row['synthetic_variant'] else '-natural')
            with bundle.clip_lease(lock_root, 'linux' if platform.system() == 'Linux' else 'mac'):
                bundle.render(root, directory / 'inputs.json', directory / 'policy.json', directory / label,
                              row['clip'], row['synthetic_variant'], dataset=directory / 'dataset.json', cache_root=cache_root)
            current = source_identity(root)
            if current != {k: identity[k] for k in current}:
                raise ValueError('Heldout source changed during rendering')
            if bundle.digest(directory / 'policy.json') != policy_sha256 or bundle.digest(directory / 'dataset.json') != dataset_sha256:
                raise ValueError('Heldout frozen snapshot changed during rendering')
            state['completed'].append(label)
            bundle.write_json(directory / 'evaluation.json', state)
        state['status'] = 'awaiting-judging'
    except BaseException as error:
        state.update(status='partial-failed', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        bundle.write_json(directory / 'evaluation.json', state)
    return state


def grade(*, root, directory, lock_root, cache=None):
    directory = Path(directory)
    state = json.loads((directory / 'evaluation.json').read_text())
    if state['status'] != 'awaiting-judging':
        raise ValueError('Heldout evaluation is incomplete or already spent')
    if (bundle.digest(directory / 'dataset.json') != state['dataset_sha256'] or
            bundle.digest(directory / 'policy.json') != state['policy_sha256']):
        raise ValueError('Heldout frozen snapshot changed before judging')
    current = source_identity(root)
    if current != {key: state[key] for key in current}:
        raise ValueError('Heldout grading source differs from the frozen render source')
    manifest, _, expected = bundle.frozen_dataset(directory / 'dataset.json')
    paths = sorted(directory.glob('*/bundle.json'))
    plans = [bundle.verify(path.parent) for path in paths]
    if len(plans) != 6 or {(p['clip'], p['synthetic_variant']) for p in plans} != expected:
        raise ValueError('All six heldout pairs must be sealed before judging')
    policy = json.loads((directory / 'policy.json').read_text())
    for plan in plans:
        if plan['candidate'] != policy['candidate'] or plan['options'] != policy['options']:
            raise ValueError('Heldout render differs from the final frozen policy')
        if plan.get('dataset_identity', {}).get('manifest_sha256') != state['dataset_sha256']:
            raise ValueError('Heldout render differs from the final frozen dataset')
        if any(plan[key] != state[key] for key in ('pipeline_sha256', 'orchestrator_sha256')):
            raise ValueError('Heldout render source differs from the frozen source')
    exclusive_json(directory / 'JUDGING.started.json', state)
    state.update(status='judging', judged=[])
    try:
        for path in paths:
            with bundle.clip_lease(lock_root, 'mac' if platform.system() == 'Darwin' else 'linux'):
                bundle.grade(root, path.parent, cache=cache)
            current = source_identity(root)
            if current != {key: state[key] for key in current}:
                raise ValueError('Heldout source changed during judging')
            if (bundle.digest(directory / 'policy.json') != state['policy_sha256'] or
                    bundle.digest(directory / 'dataset.json') != state['dataset_sha256']):
                raise ValueError('Heldout frozen snapshot changed during judging')
            state['judged'].append(path.parent.name)
            bundle.write_json(directory / 'evaluation.json', state)
        card = bundle.aggregate(root, directory, 'fresh-heldout-once', dataset=directory / 'dataset.json')
        card['heldout_freeze'] = {k: state[k] for k in ('dataset_sha256', 'policy_sha256', 'policy_commit',
                                                       'heldout_orchestrator_sha256')}
        card['licenses'].append('fixtures/fresh-heldout/ATTRIBUTION.md')
        bundle.write_json(directory / 'scorecard.json', card)
        state['status'] = 'complete'
        return card
    except BaseException as error:
        state.update(status='partial-failed', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        bundle.write_json(directory / 'evaluation.json', state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=CODE_ROOT)
    parser.add_argument('--lock-root', type=Path, required=True)
    actions = parser.add_subparsers(dest='action', required=True)
    make = actions.add_parser('render')
    for name in ('dataset', 'policy', 'directory'):
        make.add_argument('--' + name, type=Path, required=True)
    make.add_argument('--cache-root', type=Path, help='Read-only relocated assets; leaves all frozen paths/hashes intact')
    make.add_argument('--state-directory', type=Path, help='Writable retained one-shot state, required with cache override')
    for name in ('dataset-sha256', 'policy-sha256', 'policy-commit'):
        make.add_argument('--' + name, required=True)
    read = actions.add_parser('grade')
    read.add_argument('--directory', type=Path, required=True)
    read.add_argument('--cache', type=Path)
    args = vars(parser.parse_args())
    action = args.pop('action')
    result = start(**args) if action == 'render' else grade(**args)
    print(json.dumps({'status': result.get('status', 'complete'), 'benchmark_only': True,
                      'real_time_verified': False}, indent=2))


if __name__ == '__main__':
    main()

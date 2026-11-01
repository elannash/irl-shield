"""One-shot fresh heldout evaluation through the reviewed quality bundle contract.

Render once on Linux, transfer the sealed directory, then judge once on Mac.
No runtime detector, renderer, scoring algorithm or family override is added.
"""
import argparse
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess

from bench import quality_bundle as bundle
from bench import heldout_resources as resources

CODE_ROOT = Path(__file__).resolve().parents[1]
V2_STARTED = 'bench/results/fresh-heldout-v2-started.json'
V3_STARTED = 'bench/results/fresh-heldout-v3-started.json'


def git(*args):
    return subprocess.check_output(['git', '-C', str(CODE_ROOT), *args])


def v2_preflight(root, dataset, policy, manifest, policy_commit, policy_sha256):
    """The explicit final commit, never the later receipt commit, freezes policy/code."""
    version = 'v3' if manifest['dataset_id'] == 'fresh-heldout-v3' else 'v2'
    label = 'Fresh heldout ' + version
    not_before = datetime.fromisoformat(manifest['evaluation_reservation']['not_before_utc'].replace('Z', '+00:00'))
    if datetime.now(timezone.utc) < not_before:
        raise ValueError(label + ' cannot start before ' + manifest['evaluation_reservation']['not_before_utc'])
    frozen_at = datetime.fromisoformat(git('show', '-s', '--format=%cI', policy_commit).decode().strip())
    if frozen_at < not_before:
        raise ValueError(label + ' requires the final policy commit after the reservation freeze')
    if root.resolve() != CODE_ROOT.resolve():
        raise ValueError(label + ' must execute from its frozen source checkout')
    # status may otherwise refresh/write the index before resource validation.
    if git('--no-optional-locks', 'status', '--porcelain', '--untracked-files=all').strip():
        raise ValueError(label + ' requires a clean committed source and policy checkout')
    for path, expected in ((dataset, bundle.digest(dataset)), (policy, policy_sha256)):
        name = path.resolve().relative_to(CODE_ROOT.resolve()).as_posix()
        if hashlib.sha256(git('show', policy_commit + ':' + name)).hexdigest() != expected:
            raise ValueError(label + ' dataset/policy differs from the final policy commit')
    quality = bundle.modules(root)
    if Path(quality.__file__).resolve() != (CODE_ROOT / 'bench/offline_quality.py').resolve():
        raise ValueError(label + ' imported pipeline differs from the frozen source checkout')
    if version == 'v3':
        for module, name in ((bundle, 'bench/quality_bundle.py'), (resources, 'bench/heldout_resources.py'),
                             (None, 'bench/heldout_bench.py')):
            path = Path(module.__file__) if module is not None else Path(__file__)
            if path.resolve() != (CODE_ROOT / name).resolve():
                raise ValueError('Fresh heldout v3 imported harness differs from the frozen source checkout')
        # Git flags such as assume-unchanged cannot substitute different source
        # or model registry bytes behind a clean status report.
        for name in git('ls-tree', '-r', '--name-only', policy_commit, '--',
                        'bench', 'shield', 'models', 'requirements.txt', 'requirements-models.txt').decode().splitlines():
            path = CODE_ROOT / name
            if not path.is_file() or resources.digest(path) != hashlib.sha256(git('show', policy_commit + ':' + name)).hexdigest():
                raise ValueError('Fresh heldout v3 source/resource registry differs from the final policy commit')


def committed_v2_spent(dataset_sha256):
    # Refs are shared across linked worktrees. A policy-tree checkout must see
    # prior starts even when the receipt was later deleted from a newer tree.
    seen = set()
    for commit in git('rev-list', '--all').decode().splitlines():
        entries = git('ls-tree', '-r', '-z', commit, '--', 'bench/results').split(b'\0')
        for entry in filter(None, entries):
            metadata, name = entry.split(b'\t', 1)
            _, kind, blob = metadata.decode().split()
            if kind != 'blob' or not name.endswith(b'.json') or blob in seen:
                continue
            seen.add(blob)
            result = json.loads(git('cat-file', 'blob', blob))
            if result.get('heldout_freeze', {}).get('dataset_sha256') == dataset_sha256:
                raise ValueError('Heldout dataset already spent by committed receipt/result: ' + name.decode())


def reserve_v2_host(identity):
    # V2 reserves before commit. V3 calls this after its started ref exists,
    # as a secondary cross-checkout guard. There is no alternate state location.
    dataset_id = identity.get('dataset_id', 'fresh-heldout-v2')
    if dataset_id not in ('fresh-heldout-v2', 'fresh-heldout-v3'):
        raise ValueError('Unsupported reserved heldout host identity')
    path = Path.home() / '.local/state/irl-shield' / (
        dataset_id + '-' + identity['dataset_sha256'] + '.started')
    missing = []
    ancestor = path.parent
    while not ancestor.exists():
        missing.append(ancestor)
        ancestor = ancestor.parent
    path.parent.mkdir(parents=True, exist_ok=True)
    for directory in reversed(missing):
        fd = os.open(directory.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    try:
        exclusive_json(path, {'schema_version': 1, 'status': 'started', 'dataset_id': dataset_id,
                              'started_at_utc': datetime.now(timezone.utc).isoformat(),
                              'heldout_freeze': identity})
    except FileExistsError:
        raise ValueError('Heldout dataset already spent by host marker: ' + str(path)) from None
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def v2_output_preflight(directory, marker):
    # Render bookkeeping must not invalidate the clean-source check after the
    # durable receipt has already consumed the one-shot attempt.
    if marker.resolve().is_relative_to(directory.resolve()):
        raise ValueError('Fresh heldout v2 state marker must be outside the output directory')
    for path in (directory, marker):
        try:
            name = path.resolve().relative_to(CODE_ROOT.resolve()).as_posix()
        except ValueError:
            continue
        try:
            git('check-ignore', '--quiet', '--no-index', '--', name)
        except subprocess.CalledProcessError as error:
            if error.returncode != 1:
                raise
            raise ValueError('Fresh heldout v2 output/state inside the checkout must be Git-ignored') from error


def v3_output_preflight(directory, marker, identity):
    if (CODE_ROOT / V3_STARTED).exists():
        raise FileExistsError(CODE_ROOT / V3_STARTED)
    try:
        git('show-ref', '--verify', '--quiet', started_ref(identity))
    except subprocess.CalledProcessError as error:
        if error.returncode != 1:
            raise
    else:
        raise ValueError('Fresh heldout v3 started ref already exists')
    cache = Path(identity['resource_binding']['model_cache'])
    for path in (directory, marker):
        if path.resolve().is_relative_to(cache) or cache.is_relative_to(path.resolve()):
            raise ValueError('Fresh heldout v3 output/state must be separate from the model cache')
        resources.writable_destination(path, identity['resource_binding']['minimum_free_bytes'])
    resources.writable_destination(CODE_ROOT / V3_STARTED, 1)
    resources.writable_destination(Path.home() / '.local/state/irl-shield' / (
        'fresh-heldout-v3-' + identity['dataset_sha256'] + '.started'), 1)


def started_path(identity):
    return V3_STARTED if identity.get('dataset_id') == 'fresh-heldout-v3' else V2_STARTED


def receipt_commit_preflight(identity):
    """Refuse known commit failures before reserving the v3 attempt."""
    if not (CODE_ROOT / V3_STARTED).parent.is_dir():
        raise ValueError('Heldout receipt directory is missing: bench/results')
    for name in ('GIT_AUTHOR_IDENT', 'GIT_COMMITTER_IDENT'):
        git('var', name)
    try:
        signing = git('config', '--bool', '--get', 'commit.gpgsign').decode().strip()
    except subprocess.CalledProcessError as error:
        if error.returncode != 1:
            raise
        signing = 'false'
    if signing != 'false':
        raise ValueError('Heldout receipt commits require commit.gpgsign=false before reservation')
    def git_path(name):
        path = Path(git('rev-parse', '--git-path', name).decode().strip())
        return path if path.is_absolute() else CODE_ROOT / path

    for name in ('CHERRY_PICK_HEAD', 'MERGE_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply'):
        path = git_path(name)
        if path.exists() or path.is_symlink():
            raise ValueError('Heldout receipt Git operation in progress: ' + name)
    hooks = git_path('hooks')
    for name in ('pre-commit', 'prepare-commit-msg', 'commit-msg', 'post-commit', 'reference-transaction'):
        path = hooks / name
        if os.access(path, os.X_OK):
            raise ValueError('Heldout receipt commit has an unqualified executable hook: ' + name)
    refs = ['index', 'HEAD', 'packed-refs', started_ref(identity)]
    reflogs = ['logs/HEAD']
    try:
        branch = git('symbolic-ref', '--quiet', 'HEAD').decode().strip()
        refs.append(branch)
        reflogs.append('logs/' + branch)
    except subprocess.CalledProcessError as error:
        if error.returncode != 1:
            raise
    for name in refs:
        path = git_path(name)
        lock = path.with_name(path.name + '.lock')
        if lock.exists() or lock.is_symlink():
            raise FileExistsError('Heldout receipt Git lock already exists: ' + name)
        resources.writable_destination(path, 1)
    for name in reflogs:
        path = git_path(name)
        if path.exists() or path.is_symlink():
            if (path.is_symlink() or not path.is_file() or not path.stat().st_mode & 0o222
                    or not os.access(path, os.W_OK)):
                raise ValueError('Heldout receipt Git reflog is not writable: ' + name)
            try:
                fd = os.open(path, os.O_WRONLY | os.O_APPEND)
            except OSError as error:
                raise ValueError('Heldout receipt Git reflog is not writable: ' + name) from error
            else:
                os.close(fd)
        try:
            resources.writable_destination(path, 1)
        except (OSError, ValueError) as error:
            raise ValueError('Heldout receipt Git reflog is not writable: ' + name) from error
    for name in ('objects', 'refs', 'logs'):
        path = git_path(name)
        resources.writable_destination(path / '.irl-shield-write-probe', 1)


def started_ref(identity):
    return 'refs/irl-shield/fresh-heldout-v3/' + identity['dataset_sha256'] + '/started'


def verify_started_commit(identity, receipt_commit, receipt):
    path = started_path(identity)
    if (receipt.get('heldout_freeze') != identity
            or git('rev-parse', 'HEAD').decode().strip() != receipt_commit
            or git('rev-parse', 'HEAD^').decode().strip() != identity['policy_commit']
            or git('diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD').decode().splitlines() != [path]
            or json.loads(git('show', 'HEAD:' + path)) != receipt
            or git('--no-optional-locks', 'status', '--porcelain', '--untracked-files=all').strip()):
        raise ValueError('Heldout started receipt must be the sole committed change after the frozen policy')
    if identity.get('dataset_id') == 'fresh-heldout-v3':
        if git('rev-parse', '--verify', started_ref(identity)).decode().strip() != receipt_commit:
            raise ValueError('Heldout started receipt lost its exclusive durable Git ref')


def commit_v2_start(identity, directory):
    dataset_id = identity.get('dataset_id', 'fresh-heldout-v2')
    name = started_path(identity)
    receipt = {'schema_version': 1, 'status': 'started', 'dataset_id': dataset_id,
               'started_at_utc': datetime.now(timezone.utc).isoformat(),
               'directory': str(directory.resolve()), 'heldout_freeze': identity}
    path = CODE_ROOT / name
    v3 = dataset_id == 'fresh-heldout-v3'
    head = git('rev-parse', 'HEAD') if v3 else None
    if not v3:
        path.parent.mkdir(parents=True, exist_ok=True)
    created = exclusive_json(path, receipt)
    # Hooks run. Before a v3 receipt commits, failure must undo only this call's
    # staging and exclusively created file. V2 retains its spent-on-failure rule.
    try:
        git('add', '--', name)
        git('-c', 'core.fsync=committed', 'commit', '--only', '-m',
            'docs(bench): record ' + dataset_id.replace('-', ' ') + ' started', '--', name)
    except BaseException as error:
        if v3:
            try:
                if git('rev-parse', 'HEAD') == head:
                    try:
                        git('reset', '-q', '--', name)
                    except BaseException as cleanup:
                        error.add_note('V3 receipt unstage incomplete: ' + repr(cleanup))
                    current = path.lstat()
                    if (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino):
                        path.unlink()
                    else:
                        error.add_note('Receipt path was replaced; its new file was retained')
            except BaseException as cleanup:
                error.add_note('V3 receipt rollback incomplete: ' + repr(cleanup))
        raise
    receipt_commit = git('rev-parse', 'HEAD').decode().strip()
    if v3:
        # An all-zero old value means create-only, including detached HEAD.
        # Ref creation is the normal spend point. On failure, the committed
        # receipt remains spent through history, without a host marker or rewind.
        git('-c', 'core.fsync=loose-object,reference', 'update-ref', '--create-reflog',
            started_ref(identity), receipt_commit, '0' * len(receipt_commit))
    verify_started_commit(identity, receipt_commit, receipt)
    return receipt_commit, receipt


def exclusive_json(path, value):
    """Write and fsync a create-only receipt or marker, returning file identity."""
    path = Path(path)
    created = None
    try:
        with path.open('x') as stream:
            created = os.fstat(stream.fileno())
            stream.write(json.dumps(value, indent=2) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException as error:
        # Open failures did not create a file. A failed write owns only its inode.
        if created is not None:
            try:
                current = path.lstat()
                if (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino):
                    path.unlink()
                else:
                    error.add_note('Receipt path was replaced; its new file was retained')
            except BaseException as cleanup:
                error.add_note('Exclusive JSON write cleanup incomplete: ' + repr(cleanup))
        raise
    return created


def source_identity(root):
    quality = bundle.modules(root)
    return {'pipeline_sha256': quality._fingerprint(),
            'orchestrator_sha256': bundle.digest(bundle.__file__),
            'heldout_orchestrator_sha256': bundle.digest(__file__),
            'resource_preflight_sha256': bundle.digest(resources.__file__)}


def start(*, root, dataset, dataset_sha256, policy, policy_sha256, policy_commit,
          directory, lock_root, cache_root=None, state_directory=None, model_cache=None):
    root, dataset, policy, directory = map(Path, (root, dataset, policy, directory))
    if bundle.digest(dataset) != dataset_sha256 or bundle.digest(policy) != policy_sha256:
        raise ValueError('Frozen dataset or policy SHA-256 differs')
    manifest, snapshot, _ = bundle.frozen_dataset(dataset)
    if hashlib.sha256(snapshot).hexdigest() != dataset_sha256:
        raise ValueError('Frozen dataset snapshot differs from its requested SHA-256')
    v2 = manifest['dataset_id'] == 'fresh-heldout-v2'
    v3 = manifest['dataset_id'] == 'fresh-heldout-v3'
    reserved = v2 or v3
    if not v3 and model_cache is not None:
        raise ValueError('Explicit model cache binding requires fresh heldout v3')
    if reserved:
        committed_v2_spent(dataset_sha256)
    host = 'linux' if platform.system() == 'Linux' else 'mac'
    with bundle.clip_lease(lock_root, host) if reserved else nullcontext():
        if reserved:
            # Another checkout may have started while this lease waited.
            committed_v2_spent(dataset_sha256)
        # V3 spend evidence is committed content, never an uncommitted index entry.
        # Earlier corpus versions retain their existing tracked-result behavior.
        tracked = (git('ls-tree', '-r', '--name-only', '-z', 'HEAD', '--', 'bench/results').decode()
                   if v3 else subprocess.check_output(
                       ['git', '-C', str(CODE_ROOT), 'ls-files', '-z', '--', 'bench/results/*.json'], text=True))
        for name in filter(None, tracked.split('\0')):
            if v3 and not name.endswith('.json'):
                continue
            result = json.loads(git('show', 'HEAD:' + name) if v3 else (CODE_ROOT / name).read_text())
            if result.get('heldout_freeze', {}).get('dataset_sha256') == dataset_sha256:
                raise ValueError('Heldout dataset already spent by tracked result: ' + name)
        commit = subprocess.check_output(['git', '-C', str(CODE_ROOT), 'rev-parse', 'HEAD'], text=True).strip()
        if policy_commit != commit:
            raise ValueError('Final policy commit must equal the executing source checkout HEAD')
        if reserved:
            v2_preflight(root, dataset, policy, manifest, policy_commit, policy_sha256)
        config_snapshot = policy.read_bytes()
        if hashlib.sha256(config_snapshot).hexdigest() != policy_sha256:
            raise ValueError('Frozen policy snapshot differs from its requested SHA-256')
        config = json.loads(config_snapshot)
        from bench.metrics import validate_area_ceiling
        from bench.independence import policy_metadata
        validate_area_ceiling(config['options'].get('area_ceiling'), config['options'].get('area_ceiling_basis'), required=True)
        policy_metadata(config['candidate'], config['options'])
        binding = resources.preflight(root, config, manifest, model_cache) if v3 else None
        if cache_root is not None and state_directory is None:
            raise ValueError('Read-only cache override requires a separate writable one-shot state directory')
        for row in manifest['inputs']:
            for name, key in (('source', 'source_sha256'), ('truth', 'truth_sha256')):
                if bundle.digest(bundle.dataset_file(root, row[name], cache_root,
                                                    dataset_id=manifest['dataset_id'])) != row[key]:
                    raise ValueError('Frozen heldout media/truth changed: ' + row[name])
        if directory.exists():
            raise FileExistsError(directory)
        identity = {'dataset_sha256': dataset_sha256, 'policy_sha256': policy_sha256,
                    'policy_commit': policy_commit, **source_identity(root)}
        if v3:
            identity.update(dataset_id='fresh-heldout-v3', resource_binding=binding)
        marker = (Path(state_directory) / (dataset_sha256 + '.started.json') if state_directory is not None
                  else bundle.checked_file(root, manifest['evaluation_marker']))
        if marker.exists():
            raise FileExistsError(marker)
        if reserved:
            v2_output_preflight(directory, marker)
            if v3:
                v3_output_preflight(directory, marker, identity)
                receipt_commit_preflight(identity)
            if not v3:
                reserve_v2_host(identity)
            receipt_commit, receipt = commit_v2_start(identity, directory)
            if v3:
                reserve_v2_host(identity)
            current = source_identity(root)
            if current != {key: identity[key] for key in current}:
                raise ValueError('Heldout source changed while committing started receipt')
        marker.parent.mkdir(parents=True, exist_ok=True)
        exclusive_json(marker, {**identity, 'status': 'started', 'directory': str(directory.resolve())})
        directory.mkdir(parents=True, exist_ok=False)
        (directory / 'dataset.json').write_bytes(snapshot)
        (directory / 'policy.json').write_bytes(config_snapshot)
        bundle.write_json(directory / 'inputs.json', {'fixture_manifest_sha256': dataset_sha256,
                                                    'clips': manifest['inputs']})
        state = {**identity, 'status': 'rendering', 'completed': [], 'benchmark_only': True,
                 'demo_ready': False, 'real_time_verified': False}
        if reserved:
            state['started_receipt_commit'] = receipt_commit
        if v3:
            state['started_receipt_ref'] = started_ref(identity)
        bundle.write_json(directory / 'evaluation.json', state)
        try:
            for row in manifest['inputs']:
                label = row['clip'] + ('-synthetic' if row['synthetic_variant'] else '-natural')
                if reserved:
                    verify_started_commit(identity, receipt_commit, receipt)
                with nullcontext() if reserved else bundle.clip_lease(lock_root, host):
                    resource_args = {'model_cache': binding['model_cache'], 'resource_binding': binding,
                                     'started_receipt': {'identity': identity, 'commit': receipt_commit,
                                                         'receipt': receipt}} if v3 else {}
                    if v3 and (bundle.digest(directory / 'policy.json') != policy_sha256
                               or bundle.digest(directory / 'dataset.json') != dataset_sha256):
                        raise ValueError('Heldout frozen snapshot changed before rendering')
                    bundle.render(root, directory / 'inputs.json', directory / 'policy.json', directory / label,
                                  row['clip'], row['synthetic_variant'], dataset=directory / 'dataset.json',
                                  cache_root=cache_root, **resource_args)
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


@contextmanager
def grading_resources(manifest, policy, directory, cache):
    if manifest['dataset_id'] != 'fresh-heldout-v3':
        yield None
        return
    from bench.judges import Judges
    judge = Judges(policy['candidate'], cache or directory / 'judge-cache')
    try:
        judge.preflight()
        yield judge
    finally:
        judge.close()


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
        if manifest['dataset_id'] == 'fresh-heldout-v3' and plan.get('resource_binding') != state.get('resource_binding'):
            raise ValueError('Heldout render resources differ from the frozen start')
    host = 'mac' if platform.system() == 'Darwin' else 'linux'
    with bundle.clip_lease(lock_root, host), grading_resources(manifest, policy, directory, cache) as judge:
        exclusive_json(directory / 'JUDGING.started.json', state)
        state.update(status='judging', judged=[])
        try:
            for path in paths:
                bundle.grade(root, path.parent, judge=judge, cache=cache)
                current = source_identity(root)
                if current != {key: state[key] for key in current}:
                    raise ValueError('Heldout source changed during judging')
                if (bundle.digest(directory / 'policy.json') != state['policy_sha256'] or
                        bundle.digest(directory / 'dataset.json') != state['dataset_sha256']):
                    raise ValueError('Heldout frozen snapshot changed during judging')
                state['judged'].append(path.parent.name)
                bundle.write_json(directory / 'evaluation.json', state)
            run_id = {'fresh-heldout-v1': 'fresh-heldout-once', 'fresh-heldout-v2': 'fresh-heldout-v2-once',
                      'fresh-heldout-v3': 'fresh-heldout-v3-once'}[manifest['dataset_id']]
            card = bundle.aggregate(root, directory, run_id, dataset=directory / 'dataset.json')
            card['heldout_freeze'] = {k: state[k] for k in ('dataset_sha256', 'policy_sha256', 'policy_commit',
                                                           'heldout_orchestrator_sha256')}
            card['licenses'].append({'fresh-heldout-v1': 'fixtures/fresh-heldout/ATTRIBUTION.md',
                                     'fresh-heldout-v2': 'docs/FRESH-HELDOUT-V2.md',
                                     'fresh-heldout-v3': 'docs/FRESH-HELDOUT-V3.md'}[manifest['dataset_id']])
            if 'started_receipt_commit' in state:
                card['heldout_freeze']['started_receipt_commit'] = state['started_receipt_commit']
            if manifest['dataset_id'] == 'fresh-heldout-v3':
                card['heldout_freeze'].update(started_receipt_ref=state['started_receipt_ref'],
                                              resource_binding=state['resource_binding'],
                                              resource_preflight_sha256=state['resource_preflight_sha256'])
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
    make.add_argument('--model-cache', type=Path, help='Required v3 binding to existing, hash-verified selected model resources')
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

"""Fresh heldout contracts, with generated pixels and fake detector/judge boundaries."""
from datetime import datetime, timezone
from functools import partial
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bench import heldout_bench, quality_bundle as bundle
import test_quality_bundle as tune

ROOT = Path(__file__).resolve().parents[1]


class HeldoutDataset(unittest.TestCase):
    def setUp(self):
        self.commit = 'a' * 40
        # An rsync mirror has no Git metadata. Replace only this external
        # metadata provider; encoded fixture I/O keeps real subprocesses.
        def git_metadata(command, **kwargs):
            if command[-2:] == ['rev-parse', 'HEAD']:
                return self.commit + '\n'
            return subprocess.check_output(command, **kwargs)
        provider = SimpleNamespace(check_output=git_metadata)
        commit_lookup = patch.object(heldout_bench, 'subprocess', provider)
        commit_lookup.start()
        self.addCleanup(commit_lookup.stop)
        self.fixture = tune.QualityBundle(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base = self.fixture.base
        self.cache = self.base / 'fixtures/cache/fresh-heldout'
        self.cache.mkdir(parents=True)
        for key in ('source', 'truth'):
            path = getattr(self.fixture, key)
            destination = self.cache / path.name
            path.rename(destination)
            setattr(self.fixture, key, destination)
        self.dataset = self.base / 'dataset.json'
        self.ids = ['fresh-a', 'fresh-b', 'fresh-c']
        # The generated clip belongs to this test, never to the sealed real corpus.
        rows = [{'clip': clip, 'synthetic_variant': variant,
                 'source': 'fixtures/cache/fresh-heldout/source.mp4',
                 'truth': 'fixtures/cache/fresh-heldout/truth.json',
                 'source_sha256': bundle.digest(self.fixture.source),
                 'truth_sha256': bundle.digest(self.fixture.truth)}
                for clip in self.ids for variant in (False, True)]
        bundle.write_json(self.dataset, {'schema_version': 1, 'status': 'frozen-ungraded',
            'dataset_id': 'fresh-heldout-v1', 'split': 'heldout', 'evaluation_marker': 'EVALUATION.started.json',
            'clips': [{'id': clip, 'split': 'heldout'} for clip in self.ids], 'inputs': rows})
        self.inputs = self.base / 'heldout-inputs.json'
        self.data = {'fixture_manifest_sha256': bundle.digest(self.dataset), 'clips': rows}
        bundle.write_json(self.inputs, self.data)

    def test_explicit_dataset_requires_every_unique_pair_and_exact_frozen_hashes(self):
        data, snapshot = bundle.entries(self.base, self.inputs, dataset=self.dataset)
        self.assertEqual(len(data['clips']), 6)
        self.assertEqual(snapshot, self.inputs.read_bytes())
        for change, message in (
                ('missing-third', 'Quality input manifest must contain exactly all six unique heldout pairs'),
                ('changed-media', 'Quality heldout input differs from its frozen dataset')):
            with self.subTest(change=change):
                bad = json.loads(json.dumps(self.data))
                if change == 'missing-third':
                    bad['clips'] = bad['clips'][:4]
                else:
                    bad['clips'][0]['source_sha256'] = '0' * 64
                bundle.write_json(self.inputs, bad)
                with self.assertRaises(ValueError) as error:
                    bundle.entries(self.base, self.inputs, dataset=self.dataset)
                self.assertEqual(str(error.exception), message)

    def test_escaping_paths_in_frozen_rows_are_rejected(self):
        original = json.loads(self.dataset.read_text())
        for key, escape in (('source', '/tmp/unsealed.mp4'), ('truth', '../unsealed.json')):
            with self.subTest(key=key, escape=escape):
                manifest = json.loads(json.dumps(original))
                manifest['inputs'][0][key] = escape
                bundle.write_json(self.dataset, manifest)
                bundle.write_json(self.inputs, {'fixture_manifest_sha256': bundle.digest(self.dataset),
                                                'clips': manifest['inputs']})
                with self.assertRaises(ValueError) as error:
                    bundle.entries(self.base, self.inputs, dataset=self.dataset)
                self.assertEqual(str(error.exception), 'Quality artifact escapes its sealed directory')

    def corpus(self):
        directory = self.base / 'corpus'
        for clip in self.ids:
            for variant in (False, True):
                path = directory / (clip + ('-synthetic' if variant else '-natural'))
                with patch('bench.pipeline.detector_for', side_effect=lambda *args: tune.Detector()):
                    bundle.render(self.base, self.inputs, self.fixture.config, path, clip, variant,
                                  dataset=self.dataset)
                bundle.grade(ROOT, path, judge=tune.Judge())
        return directory

    def test_sealed_relocation_and_missing_third_pair(self):
        original = self.corpus()
        relocated = self.base / 'relocated'
        shutil.copytree(original, relocated)
        shutil.rmtree(original)
        self.fixture.source.unlink()
        self.fixture.truth.unlink()
        card = bundle.aggregate(ROOT, relocated, 'fresh-test', dataset=self.dataset)
        self.assertEqual(card['split'], 'heldout')
        self.assertEqual(card['frames'], 24)
        self.assertEqual(len(card['clips']), 6)
        self.assertFalse(card['gate_1']['pass'])
        self.assertFalse(card['real_time_verified'])
        self.assertEqual(card['quality_run_identity']['dataset_identity']['manifest_sha256'],
                         bundle.digest(self.dataset))
        # Losing both variants of the third clip must not earn a subset score.
        for variant in ('natural', 'synthetic'):
            shutil.rmtree(relocated / ('fresh-c-' + variant))
        (relocated / 'scorecard.json').unlink()
        with self.assertRaisesRegex(ValueError, 'All six heldout pairs'):
            bundle.aggregate(ROOT, relocated, 'subset', dataset=self.dataset)
        self.assertFalse((relocated / 'scorecard.json').exists())

    def test_v2_encoded_bundles_keep_dataset_identity_after_relocation(self):
        manifest = json.loads(self.dataset.read_text())
        manifest.update(dataset_id='fresh-heldout-v2', evaluation_reservation={
            'maximum_evaluations': 1, 'evaluation_started': False,
            'not_before_utc': '2026-11-01T14:00:00Z'})
        for index, clip in enumerate(manifest['clips']):
            clip.update(source_sha256=str(index) * 64, source_path=f'original-{index}.webm',
                        source_url=f'https://example.invalid/original-{index}')
        v2_cache = self.cache.with_name('fresh-heldout-v2')
        self.cache.rename(v2_cache)
        self.fixture.source = v2_cache / self.fixture.source.name
        self.fixture.truth = v2_cache / self.fixture.truth.name
        for row in manifest['inputs']:
            for key in ('source', 'truth'):
                row[key] = row[key].replace('cache/fresh-heldout/', 'cache/fresh-heldout-v2/')
        bundle.write_json(self.dataset, manifest)
        bundle.write_json(self.inputs, {'fixture_manifest_sha256': bundle.digest(self.dataset),
                                       'clips': manifest['inputs']})
        original = self.corpus()
        relocated = self.base / 'v2-other-host'
        original.rename(relocated)
        shutil.rmtree(v2_cache)
        card = bundle.aggregate(ROOT, relocated, 'v2-synthetic', dataset=self.dataset)
        self.assertEqual(card['quality_run_identity']['dataset_identity'], {
            'dataset_id': 'fresh-heldout-v2', 'split': 'heldout',
            'manifest_sha256': bundle.digest(self.dataset)})
        self.assertEqual(len(card['clips']), 6)
        self.assertEqual(card['frames'], 24)
        self.assertFalse(card['gate_1']['pass'])
        self.assertFalse(card['real_time_verified'])
        for path in relocated.glob('*/bundle.json'):
            self.assertEqual(bundle.verify(path.parent)['dataset_identity']['dataset_id'], 'fresh-heldout-v2')

    def test_judging_preflight_rejects_policy_dataset_and_source_before_ocr(self):
        directory = self.base / 'evaluation'
        with patch('bench.pipeline.detector_for', side_effect=lambda *args: tune.Detector()):
            heldout_bench.start(root=self.base, dataset=self.dataset,
                dataset_sha256=bundle.digest(self.dataset), policy=self.fixture.config,
                policy_sha256=bundle.digest(self.fixture.config), policy_commit=self.commit,
                directory=directory, lock_root=self.base)
        evaluation = directory / 'evaluation.json'
        policy = directory / 'policy.json'
        dataset = directory / 'dataset.json'
        plan = next(directory.glob('*/bundle.json'))
        seal = plan.with_suffix('.sha256')
        saved = {path: path.read_bytes() for path in (evaluation, policy, dataset, plan, seal)}
        for fault, message in (
                ('policy', 'Heldout render differs from the final frozen policy'),
                ('dataset', 'Heldout render differs from the final frozen dataset'),
                ('source', 'Heldout render source differs from the frozen source')):
            with self.subTest(fault=fault):
                try:
                    state = json.loads(saved[evaluation])
                    if fault == 'policy':
                        config = json.loads(saved[policy])
                        config['options']['before'] += 1
                        bundle.write_json(policy, config)
                        state['policy_sha256'] = bundle.digest(policy)
                    elif fault == 'dataset':
                        dataset.write_bytes(saved[dataset] + b'\n')
                        state['dataset_sha256'] = bundle.digest(dataset)
                    else:
                        changed = json.loads(saved[plan])
                        changed['orchestrator_sha256'] = '0' * 64
                        bundle.write_json(plan, changed)
                        seal.write_text(bundle.digest(plan) + '\n')
                    bundle.write_json(evaluation, state)
                    # These remain valid sealed renders; the corpus freeze must reject them.
                    for path in directory.glob('*/bundle.json'):
                        bundle.verify(path.parent)
                    with patch.object(bundle, 'grade', side_effect=AssertionError('OCR must not start during preflight')) as physical:
                        with self.assertRaises(ValueError) as error:
                            heldout_bench.grade(root=ROOT, directory=directory, lock_root=self.base)
                        self.assertEqual(str(error.exception), message)
                        physical.assert_not_called()
                    self.assertFalse((directory / 'JUDGING.started.json').exists())
                    self.assertFalse((directory / 'scorecard.json').exists())
                    self.assertEqual(evaluation.read_bytes(), (json.dumps(state, indent=2) + '\n').encode())
                finally:
                    for path, content in saved.items():
                        path.write_bytes(content)

    def test_tracked_result_spends_dataset_without_any_retained_marker(self):
        subprocess.run(['git', 'init', '-q', str(self.base)], check=True)
        results = self.base / 'bench/results'
        results.mkdir(parents=True)
        tracked = results / 'spent.json'
        bundle.write_json(tracked, {'heldout_freeze': {'dataset_sha256': '0' * 64}})
        (self.base / '.gitignore').write_text('bench/results/ignored.json\n')
        subprocess.run(['git', '-C', str(self.base), 'add', 'bench/results/spent.json', '.gitignore'], check=True)
        bundle.write_json(results / 'ignored.json', {
            'heldout_freeze': {'dataset_sha256': bundle.digest(self.dataset)}})
        options = dict(root=self.base, dataset=self.dataset, dataset_sha256=bundle.digest(self.dataset),
            policy=self.fixture.config, policy_sha256=bundle.digest(self.fixture.config),
            policy_commit=self.commit, directory=self.base / 'evaluation', lock_root=self.base)
        marker = self.base / 'EVALUATION.started.json'
        with patch.object(heldout_bench, 'CODE_ROOT', self.base), patch.object(bundle, 'render') as physical:
            # Neither an ignored matching result nor a tracked unrelated result spends this dataset.
            heldout_bench.start(**options)
            self.assertEqual(physical.call_count, 6)
            marker.unlink()
            shutil.rmtree(options['directory'])
            bundle.write_json(tracked, {'heldout_freeze': {'dataset_sha256': bundle.digest(self.dataset)}})
            subprocess.run(['git', '-C', str(self.base), 'add', 'bench/results/spent.json'], check=True)
            physical.reset_mock()
            for state in (self.base / 'nonexistent-state', None):
                with self.subTest(state=state):
                    self.assertFalse(marker.exists())
                    if state is not None:
                        self.assertFalse(state.exists())
                    with self.assertRaisesRegex(ValueError, '^Heldout dataset already spent by tracked result: bench/results/spent.json$'):
                        heldout_bench.start(**options, state_directory=state)
                    self.assertFalse(options['directory'].exists())
                    self.assertFalse(marker.exists())
                    if state is not None:
                        self.assertFalse(state.exists())
                    self.assertEqual(physical.call_count, 0)

    def test_one_shot_render_repeats_have_no_physical_effect_even_after_failure(self):
        commit = self.commit
        for fail in (False, True):
            with self.subTest(fail=fail):
                directory = self.base / ('failed-run' if fail else 'complete-run')
                marker = self.base / 'EVALUATION.started.json'
                marker.unlink(missing_ok=True)
                calls = []
                def physical(*args, **kwargs):
                    calls.append((args[4], args[5]))
                    if fail:
                        raise RuntimeError('synthetic render failure')
                    return {'status': 'awaiting-judging'}
                with patch.object(bundle, 'render', side_effect=physical):
                    options = dict(root=self.base, dataset=self.dataset,
                        dataset_sha256=bundle.digest(self.dataset), policy=self.fixture.config,
                        policy_sha256=bundle.digest(self.fixture.config), policy_commit=commit,
                        directory=directory, lock_root=self.base)
                    if fail:
                        with self.assertRaisesRegex(RuntimeError, 'synthetic render failure'):
                            heldout_bench.start(**options)
                    else:
                        heldout_bench.start(**options)
                    with self.assertRaises(FileExistsError):
                        heldout_bench.start(**{**options, 'directory': self.base / 'another-output'})
                self.assertEqual(len(calls), 1 if fail else 6)
                status = json.loads((directory / 'evaluation.json').read_text())
                self.assertEqual(status['status'], 'partial-failed' if fail else 'awaiting-judging')
                self.assertFalse(status['real_time_verified'])

    def test_one_shot_judging_after_relocation_consumes_all_six_once(self):
        commit = self.commit
        directory = self.base / 'evaluation'
        with patch('bench.pipeline.detector_for', side_effect=lambda *args: tune.Detector()):
            heldout_bench.start(root=self.base, dataset=self.dataset,
                dataset_sha256=bundle.digest(self.dataset), policy=self.fixture.config,
                policy_sha256=bundle.digest(self.fixture.config), policy_commit=commit,
                directory=directory, lock_root=self.base)
        relocated = self.base / 'other-host'
        directory.rename(relocated)
        self.fixture.source.unlink()
        self.fixture.truth.unlink()
        killed = self.base / 'killed'
        shutil.copytree(relocated, killed)
        real_grade = bundle.grade
        def fake_judges(root, path, **kwargs):
            return real_grade(root, path, judge=tune.Judge())
        with patch.object(bundle, 'grade', side_effect=fake_judges) as physical:
            card = heldout_bench.grade(root=ROOT, directory=relocated, lock_root=self.base)
            with self.assertRaisesRegex(ValueError, 'already spent'):
                heldout_bench.grade(root=ROOT, directory=relocated, lock_root=self.base)
        self.assertEqual(physical.call_count, 6)
        self.assertEqual(len(card['clips']), 6)
        self.assertEqual(card['heldout_freeze']['policy_commit'], commit)
        self.assertFalse(card['gate_1']['pass'])
        self.assertEqual(json.loads((relocated / 'evaluation.json').read_text())['status'], 'complete')
        self.assertTrue((relocated / 'JUDGING.started.json').is_file())

        evaluation = killed / 'evaluation.json'
        before_grade = evaluation.read_bytes()
        with patch.object(bundle, 'grade', side_effect=RuntimeError('synthetic interrupted first grade')) as physical:
            with self.assertRaisesRegex(RuntimeError, '^synthetic interrupted first grade$'):
                heldout_bench.grade(root=ROOT, directory=killed, lock_root=self.base)
            self.assertEqual(physical.call_count, 1)
            # A kill skips finally: restore exactly the awaiting-judging bytes it would leave.
            evaluation.write_bytes(before_grade)
            with self.assertRaises(FileExistsError):
                heldout_bench.grade(root=ROOT, directory=killed, lock_root=self.base)
            self.assertEqual(physical.call_count, 1)
        self.assertEqual(evaluation.read_bytes(), before_grade)
        self.assertTrue((killed / 'JUDGING.started.json').is_file())

    def test_changed_commit_or_input_media_rejects_before_one_shot_is_spent(self):
        for fault in ('commit', 'media'):
            with self.subTest(fault=fault):
                if fault == 'media':
                    self.fixture.source.write_bytes(self.fixture.source.read_bytes() + b'changed')
                expected = ('Final policy commit' if fault == 'commit'
                            else 'Frozen heldout media/truth changed')
                with patch.object(bundle, 'render') as physical:
                    with self.assertRaisesRegex(ValueError, expected):
                        heldout_bench.start(root=self.base, dataset=self.dataset,
                            dataset_sha256=bundle.digest(self.dataset), policy=self.fixture.config,
                            policy_sha256=bundle.digest(self.fixture.config),
                            policy_commit='b' * 40 if fault == 'commit' else self.commit,
                            directory=self.base / 'run', lock_root=self.base)
                self.assertEqual(physical.call_count, 0)
                self.assertFalse((self.base / 'EVALUATION.started.json').exists())

    def test_read_only_cache_override_seals_hashes_without_writing_asset_root(self):
        commit = self.commit
        checkout = self.base / 'empty-checkout'
        checkout.mkdir()
        state = self.base / 'writable-state'
        before = {p.name: bundle.digest(p) for p in self.cache.iterdir()}
        self.cache.chmod(0o555)
        self.addCleanup(self.cache.chmod, 0o755)
        with patch('bench.pipeline.detector_for', side_effect=lambda *args: tune.Detector()):
            heldout_bench.start(root=checkout, dataset=self.dataset,
                dataset_sha256=bundle.digest(self.dataset), policy=self.fixture.config,
                policy_sha256=bundle.digest(self.fixture.config), policy_commit=commit,
                directory=checkout / 'out', lock_root=self.base,
                cache_root=self.cache, state_directory=state)
        self.assertEqual({p.name: bundle.digest(p) for p in self.cache.iterdir()}, before)
        self.assertEqual(len(list(state.glob('*.started.json'))), 1)
        self.assertFalse((checkout / 'fixtures').exists())
        self.assertEqual(len(list((checkout / 'out').glob('*/bundle.json'))), 6)
        for path in (checkout / 'out').glob('*/bundle.json'):
            self.assertEqual(bundle.verify(path.parent)['status'], 'awaiting-judging')


class HeldoutV2Start(unittest.TestCase):
    """Real temporary Git history; only the physical renderer and UTC clock are fakes."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        # Match the executing source bytes in a disposable repository. No source
        # commits, staging or hooks touch the worker's assigned checkout.
        for folder in ('bench', 'shield'):
            for source in (ROOT / folder).glob('*.py'):
                target = self.base / folder / source.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        for name in ('fixtures/prepare.py', 'fixtures/manifest.json', 'models/manifest.json', 'requirements.txt',
                     'requirements-models.txt', 'Sources/VisionBridge/main.swift'):
            target = self.base / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        (self.base / '.gitignore').write_text('out/\n.tmp/\nfixtures/cache/\n__pycache__/\n')
        self.cache = self.base / 'fixtures/cache/fresh-heldout-v2'
        self.cache.mkdir(parents=True)
        self.rows = []
        self.clips = []
        for index, clip in enumerate(('v2-a', 'v2-b', 'v2-c')):
            self.clips.append({'id': clip, 'split': 'heldout', 'source_sha256': str(index) * 64,
                               'source_path': f'original-{clip}.webm',
                               'source_url': f'https://example.invalid/{clip}'})
            for variant in (False, True):
                label = clip + ('-synthetic' if variant else '-natural')
                source = self.cache / (label + '.mp4')
                truth = self.cache / (label + '.truth.json')
                # These are deliberately not media; any unmocked render must fail.
                source.write_text('synthetic bytes for ' + label)
                truth.write_text('[]')
                self.rows.append({'clip': clip, 'synthetic_variant': variant,
                    'source': source.relative_to(self.base).as_posix(),
                    'truth': truth.relative_to(self.base).as_posix(),
                    'source_sha256': bundle.digest(source), 'truth_sha256': bundle.digest(truth)})
        self.dataset = self.base / 'dataset.json'
        bundle.write_json(self.dataset, {'schema_version': 1, 'dataset_id': 'fresh-heldout-v2',
            'split': 'heldout', 'status': 'frozen-ungraded', 'clips': self.clips, 'inputs': self.rows,
            'evaluation_marker': 'fixtures/cache/fresh-heldout-v2/EVALUATION.started.json',
            'evaluation_reservation': {'maximum_evaluations': 1, 'evaluation_started': False,
                                     'not_before_utc': '2026-11-01T14:00:00Z'}})
        self.policy = self.base / 'policy.json'
        bundle.write_json(self.policy, {'candidate': 'ppocr-v6-small', 'options': {
            'area_ceiling': .15, 'area_ceiling_basis': 'synthetic-fixture'}})
        self.git('init', '-q')
        for name, value in (('user.name', 'Synthetic heldout test'), ('user.email', 'test@example.invalid'),
                            ('commit.gpgsign', 'false'), ('core.hooksPath', str(self.base / '.git/no-hooks'))):
            self.git('config', name, value)
        self.git('add', '.')
        self.commit = self.commit_at('2026-11-01T14:00:00+00:00')
        from bench import offline_quality
        for module, name, value in (
                (heldout_bench, 'CODE_ROOT', self.base),
                (heldout_bench, '__file__', str(self.base / 'bench/heldout_bench.py')),
                (bundle, '__file__', str(self.base / 'bench/quality_bundle.py')),
                (offline_quality, 'ROOT', self.base),
                (offline_quality, '__file__', str(self.base / 'bench/offline_quality.py'))):
            override = patch.object(module, name, value)
            override.start()
            self.addCleanup(override.stop)
        lease = patch.object(bundle, 'clip_lease', partial(bundle.clip_lease, lock_root=self.base / '.tmp/locks'))
        lease.start()
        self.addCleanup(lease.stop)
        clock = patch.object(heldout_bench, 'datetime', wraps=datetime)
        self.clock = clock.start()
        self.addCleanup(clock.stop)
        self.clock.now.return_value = datetime(2026, 11, 1, 14, 0, tzinfo=timezone.utc)
        self.directory = self.base / 'out/evaluation'
        self.state = self.base / 'out/state'

    def git(self, *args, **kwargs):
        return subprocess.check_output(['git', '-C', str(self.base), *args], **kwargs).decode().strip()

    def commit_at(self, timestamp):
        self.git('commit', '-qm', 'test: freeze synthetic final policy', '--allow-empty',
                 env={**os.environ, 'GIT_AUTHOR_DATE': timestamp, 'GIT_COMMITTER_DATE': timestamp})
        return self.git('rev-parse', 'HEAD')

    def start(self, **changes):
        options = dict(root=self.base, dataset=self.dataset, dataset_sha256=bundle.digest(self.dataset),
                       policy=self.policy, policy_sha256=bundle.digest(self.policy), policy_commit=self.commit,
                       directory=self.directory, lock_root=self.base, cache_root=self.cache,
                       state_directory=self.state)
        return heldout_bench.start(**{**options, **changes})

    def assert_unspent(self):
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.commit)
        self.assertFalse((self.base / heldout_bench.V2_STARTED).exists())
        self.assertFalse(self.state.exists())
        self.assertFalse(self.directory.exists())

    def test_committed_start_survives_lost_state_and_exists_at_first_render(self):
        calls = []
        def physical(*args, **kwargs):
            receipt = json.loads(self.git('show', 'HEAD:' + heldout_bench.V2_STARTED))
            self.v2_evidence = {'at': 'first render spy entry', 'prior_physical_calls': len(calls),
                'head': self.git('rev-parse', 'HEAD'), 'parent': self.git('rev-parse', 'HEAD^'),
                'tracked_receipt': receipt, 'status_porcelain': self.git('status', '--porcelain'),
                'changed_paths': self.git('diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD')}
            self.assertEqual(receipt['status'], 'started')
            self.assertEqual(receipt['heldout_freeze']['policy_commit'], self.commit)
            self.assertEqual(receipt['heldout_freeze']['policy_sha256'], bundle.digest(self.policy))
            self.assertEqual(receipt['heldout_freeze']['dataset_sha256'], bundle.digest(self.dataset))
            self.assertEqual(self.git('rev-parse', 'HEAD^'), self.commit)
            self.assertEqual(self.git('diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD'),
                             heldout_bench.V2_STARTED)
            self.assertEqual(self.git('status', '--porcelain'), '')
            calls.append((args[4], args[5]))
            raise RuntimeError('synthetic first render interrupted')
        with patch.object(bundle, 'render', side_effect=physical):
            with self.assertRaisesRegex(RuntimeError, '^synthetic first render interrupted$'):
                self.start()
        self.assertEqual(calls, [('v2-a', False)])
        receipt_commit = self.git('rev-parse', 'HEAD')
        evaluation = json.loads((self.directory / 'evaluation.json').read_text())
        self.assertEqual(evaluation['status'], 'partial-failed')
        self.assertEqual(evaluation['policy_commit'], self.commit)
        self.assertEqual(evaluation['started_receipt_commit'], receipt_commit)
        shutil.rmtree(self.base / 'out')
        # Also lose the worktree receipt; the committed object must still win.
        (self.base / heldout_bench.V2_STARTED).unlink()
        with self.assertRaisesRegex(ValueError, '^Heldout dataset already spent by committed receipt/result:'):
            heldout_bench.committed_v2_spent(bundle.digest(self.dataset))
        with patch.object(bundle, 'render') as physical:
            with self.assertRaisesRegex(ValueError, '^Heldout dataset already spent by committed receipt/result:'):
                self.start(directory=self.base / 'out/restart')
            physical.assert_not_called()
        self.assertFalse(self.state.exists())
        self.assertFalse((self.base / 'out').exists())
        self.assertEqual(self.git('rev-parse', 'HEAD'), receipt_commit)

    def test_too_early_start_has_no_physical_or_persistent_effect(self):
        self.clock.now.return_value = datetime(2026, 11, 1, 13, 59, 59, tzinfo=timezone.utc)
        with patch.object(bundle, 'render') as physical:
            with self.assertRaisesRegex(ValueError, '^Fresh heldout v2 cannot start before 2026-11-01T14:00:00Z$'):
                self.start()
            physical.assert_not_called()
        self.assert_unspent()

    def test_v2_manifest_cannot_rebind_reservation_sources_or_cache_prefix(self):
        original = self.dataset.read_bytes()
        for fault, message in (('reservation', 'immutable one-shot reservation'),
                               ('source', 'three distinct source identities'),
                               ('prefix', 'frozen cache prefix')):
            with self.subTest(fault=fault):
                manifest = json.loads(original)
                if fault == 'reservation':
                    manifest['evaluation_reservation']['not_before_utc'] = '2026-10-31T14:00:00Z'
                elif fault == 'source':
                    manifest['clips'][1]['source_sha256'] = manifest['clips'][0]['source_sha256']
                else:
                    manifest['inputs'][0]['source'] = 'fixtures/cache/fresh-heldout/source.mp4'
                try:
                    bundle.write_json(self.dataset, manifest)
                    with self.assertRaisesRegex(ValueError, message):
                        bundle.frozen_dataset(self.dataset)
                finally:
                    self.dataset.write_bytes(original)
        self.assert_unspent()

    def test_wrong_prefreeze_policy_commit_is_rejected_after_reservation_opens(self):
        self.commit = self.commit_at('2026-10-31T23:00:00+00:00')
        with patch.object(bundle, 'render') as physical:
            with self.assertRaisesRegex(ValueError, '^Fresh heldout v2 requires the final policy commit after the reservation freeze$'):
                self.start()
            physical.assert_not_called()
        self.assert_unspent()

    def test_committed_policy_bytes_are_checked_even_when_git_status_is_clean(self):
        original = self.policy.read_bytes()
        self.git('update-index', '--assume-unchanged', '--', 'policy.json')
        try:
            changed = json.loads(original)
            changed['options']['padding'] = .2
            bundle.write_json(self.policy, changed)
            self.assertEqual(self.git('status', '--porcelain'), '')
            with patch.object(bundle, 'render') as physical:
                with self.assertRaisesRegex(ValueError, '^Fresh heldout v2 dataset/policy differs from the final policy commit$'):
                    self.start()
                physical.assert_not_called()
            self.assert_unspent()
        finally:
            self.policy.write_bytes(original)
            self.git('update-index', '--no-assume-unchanged', '--', 'policy.json')

    def test_output_and_state_placement_cannot_spend_before_render(self):
        for changes, message in (
                ({'directory': self.base / 'evaluation'}, 'output/state inside the checkout must be Git-ignored'),
                ({'state_directory': self.base / 'state'}, 'output/state inside the checkout must be Git-ignored'),
                ({'state_directory': self.directory / 'state'}, 'state marker must be outside the output directory')):
            with self.subTest(changes=changes), patch.object(bundle, 'render') as physical:
                error = None
                try:
                    self.start(**changes)
                except ValueError as caught:
                    error = caught
                self.assert_unspent()
                self.assertIsNotNone(error)
                self.assertRegex(str(error), '^Fresh heldout v2 ' + message + '$')
                physical.assert_not_called()

    def test_final_policy_commit_remains_authoritative_after_receipt_advances_head(self):
        with tempfile.TemporaryDirectory() as outside, patch.object(bundle, 'render') as physical:
            state = self.start(directory=Path(outside) / 'evaluation', state_directory=Path(outside) / 'state')
        self.assertEqual(physical.call_count, 6)
        self.assertEqual(state['completed'], [row['clip'] + ('-synthetic' if row['synthetic_variant'] else '-natural')
                                             for row in self.rows])
        self.assertEqual(state['status'], 'awaiting-judging')
        self.assertEqual(state['policy_commit'], self.commit)
        self.assertNotEqual(state['policy_commit'], self.git('rev-parse', 'HEAD'))
        self.assertEqual(state['started_receipt_commit'], self.git('rev-parse', 'HEAD'))
        with patch.object(bundle, 'render') as physical:
            with self.assertRaisesRegex(ValueError, 'already spent by committed receipt/result'):
                self.start(policy_commit=state['started_receipt_commit'])
            physical.assert_not_called()

    def test_changed_source_policy_or_commit_cannot_spend_attempt(self):
        source = self.base / 'bench/quality_bundle.py'
        for path, content, changes, message in (
                (source, source.read_bytes() + b'\n# changed\n', {}, 'clean committed source and policy'),
                (self.policy, self.policy.read_bytes() + b'\n', {}, 'clean committed source and policy'),
                (None, None, {'policy_commit': 'b' * 40}, 'Final policy commit must equal')):
            with self.subTest(path=path, changes=changes):
                saved = path.read_bytes() if path else None
                try:
                    if path:
                        path.write_bytes(content)
                    with patch.object(bundle, 'render') as physical:
                        with self.assertRaisesRegex(ValueError, message):
                            self.start(**changes)
                        physical.assert_not_called()
                    self.assert_unspent()
                finally:
                    if path:
                        path.write_bytes(saved)

    def test_receipt_commit_failure_never_reaches_render_and_cannot_retry(self):
        hooks = self.base / '.git/no-hooks'
        hooks.mkdir()
        hook = hooks / 'pre-commit'
        hook.write_text('#!/bin/sh\nexit 73\n')
        hook.chmod(0o755)
        with patch.object(bundle, 'render') as physical:
            with self.assertRaises(subprocess.CalledProcessError):
                self.start()
            physical.assert_not_called()
        self.assertTrue((self.base / heldout_bench.V2_STARTED).exists())
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.commit)
        self.assertFalse(self.directory.exists())
        self.assertFalse(self.state.exists())
        with patch.object(bundle, 'render') as physical:
            with self.assertRaisesRegex(ValueError, 'already spent by tracked result'):
                self.start()
            physical.assert_not_called()

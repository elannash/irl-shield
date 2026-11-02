"""Fresh heldout contracts, with generated pixels and fake detector/judge boundaries."""
from datetime import datetime, timezone
from contextlib import contextmanager, nullcontext
from functools import partial
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

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


class HeldoutV3JudgingReadiness(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.policy = {'candidate': 'ppocr-v6-small', 'options': {}}
        self.manifest = {'dataset_id': 'fresh-heldout-v3'}
        bundle.write_json(self.directory / 'dataset.json', self.manifest)
        bundle.write_json(self.directory / 'policy.json', self.policy)
        self.identity = {'pipeline_sha256': '1' * 64, 'orchestrator_sha256': '2' * 64,
                         'heldout_orchestrator_sha256': '3' * 64, 'resource_preflight_sha256': '4' * 64}
        self.state = {**self.identity, 'orchestrator_sha256': '2' * 64,
            'status': 'awaiting-judging', 'policy_commit': 'a' * 40,
            'dataset_sha256': bundle.digest(self.directory / 'dataset.json'),
            'policy_sha256': bundle.digest(self.directory / 'policy.json'),
            'resource_binding': {'synthetic': True}}
        self.state['started_receipt_ref'] = ('refs/irl-shield/fresh-heldout-v3/' +
                                            self.state['dataset_sha256'] + '/started')
        bundle.write_json(self.directory / 'evaluation.json', self.state)
        self.before = (self.directory / 'evaluation.json').read_bytes()
        self.expected = {(clip, variant) for clip in ('a', 'b', 'c') for variant in (False, True)}
        for clip, variant in sorted(self.expected):
            path = self.directory / (clip + ('-synthetic' if variant else '-natural'))
            path.mkdir()
            bundle.write_json(path / 'bundle.json', {'clip': clip, 'synthetic_variant': variant,
                **self.policy, 'dataset_identity': {'manifest_sha256': self.state['dataset_sha256']},
                'pipeline_sha256': self.state['pipeline_sha256'],
                'orchestrator_sha256': self.state['orchestrator_sha256'],
                'resource_binding': self.state['resource_binding']})
        # Source/artifact identity has real-byte and encoded tests elsewhere.
        # This fixture owns only readiness, marker ordering and owner reuse.
        for override in (
                patch.object(heldout_bench, 'source_identity', return_value=self.identity),
                patch.object(bundle, 'frozen_dataset', return_value=(self.manifest, b'', self.expected)),
                patch.object(bundle, 'verify', side_effect=lambda path: json.loads((path / 'bundle.json').read_text())),
                patch.object(bundle, 'clip_lease', side_effect=lambda *a, **kw: nullcontext()),
                patch.object(bundle, 'aggregate', return_value={'licenses': []})):
            override.start()
            self.addCleanup(override.stop)

    def test_unavailable_judges_leave_grading_unspent(self):
        for fault in ('constructor', 'probe'):
            with self.subTest(fault=fault):
                judge = Mock()
                judge.preflight.side_effect = RuntimeError('synthetic reader unavailable')
                factory_error = RuntimeError('synthetic reader unavailable') if fault == 'constructor' else None
                with patch('bench.judges.Judges', return_value=judge, side_effect=factory_error), \
                        patch.object(bundle, 'grade', return_value={}) as physical:
                    with self.assertRaisesRegex(RuntimeError, 'synthetic reader unavailable'):
                        heldout_bench.grade(root=ROOT, directory=self.directory, lock_root=self.directory)
                    physical.assert_not_called()
                self.assertFalse((self.directory / 'JUDGING.started.json').exists())
                self.assertEqual((self.directory / 'evaluation.json').read_bytes(), self.before)
                self.assertFalse((self.directory / 'scorecard.json').exists())
                self.assertEqual(judge.close.call_count, 0 if fault == 'constructor' else 1)

    def test_preflight_owner_is_reused_after_marker_for_all_six_grades(self):
        judge = Mock()
        def ready():
            self.assertFalse((self.directory / 'JUDGING.started.json').exists())
            self.assertEqual((self.directory / 'evaluation.json').read_bytes(), self.before)
        judge.preflight.side_effect = ready
        def graded(root, path, **kwargs):
            self.assertTrue((self.directory / 'JUDGING.started.json').exists())
            self.assertIs(kwargs['judge'], judge)
            judge.preflight.assert_called_once()
            self.assertEqual(judge.close.call_count, 0)
            return {}
        with patch('bench.judges.Judges', return_value=judge) as factory, \
                patch.object(bundle, 'grade', side_effect=graded) as physical:
            heldout_bench.grade(root=ROOT, directory=self.directory, lock_root=self.directory)
            self.assertEqual(physical.call_count, 6)
            factory.assert_called_once()
        judge.close.assert_called_once()
        self.assertEqual(json.loads((self.directory / 'evaluation.json').read_text())['status'], 'complete')


class HeldoutV2Start(unittest.TestCase):
    """Real temporary Git history; only the physical renderer and UTC clock are fakes."""

    def setUp(self):
        from lock_isolation import install_lock_guard
        install_lock_guard()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.temporary = Path(temporary.name)
        self.base = self.temporary / 'repo'
        self.base.mkdir()
        self.home = self.temporary / 'home'
        self.home.mkdir()
        # The production HOME boundary is isolated outside every synthetic repo.
        # No real host one-shot marker is read, created or removed by these tests.
        for override in (patch.object(Path, 'home', return_value=self.home),
                         patch.dict(os.environ, {'HOME': str(self.home)})):
            override.start()
            self.addCleanup(override.stop)
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
        self.host_marker = self.home / '.local/state/irl-shield' / (
            'fresh-heldout-v2-' + bundle.digest(self.dataset) + '.started')

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
        self.assertFalse(self.host_marker.exists())

    def test_committed_start_survives_lost_state_and_exists_at_first_render(self):
        calls = []
        def physical(*args, **kwargs):
            receipt = json.loads(self.git('show', 'HEAD:' + heldout_bench.V2_STARTED))
            self.assertTrue(self.host_marker.is_file(), 'Host marker must precede the first render')
            host = json.loads(self.host_marker.read_text())
            self.assertEqual(host['dataset_id'], 'fresh-heldout-v2')
            self.assertEqual(host['heldout_freeze'], receipt['heldout_freeze'])
            self.assertEqual(host['started_at_utc'], '2026-11-01T14:00:00+00:00')
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

    def repeat_from_policy_checkout(self, *, linked):
        # Reuse the reviewer's public start() scenario and six-render witness.
        # The linked checkout shares refs with the first synthetic repository.
        with patch.object(bundle, 'render') as physical:
            first = self.start()
        self.assertEqual(physical.call_count, 6)
        receipt_commit = first['started_receipt_commit']
        checkout = self.base
        if linked:
            checkout = self.temporary / 'second-checkout'
            self.git('worktree', 'add', '-q', '--detach', str(checkout), self.commit)
        subprocess.check_output(['git', '-C', str(checkout), 'checkout', '-q', '--detach', self.commit])
        # Prove the refs guard independently: intentionally lose only synthetic
        # host/scratch state. The reachable prior receipt must still refuse.
        self.host_marker.unlink(missing_ok=True)
        shutil.rmtree(self.base / 'out')
        self.assertIn(receipt_commit, subprocess.check_output(
            ['git', '-C', str(checkout), 'rev-list', '--all'], text=True).splitlines())
        from bench import offline_quality
        with patch.object(heldout_bench, 'CODE_ROOT', checkout), \
                patch.object(heldout_bench, '__file__', str(checkout / 'bench/heldout_bench.py')), \
                patch.object(bundle, '__file__', str(checkout / 'bench/quality_bundle.py')), \
                patch.object(offline_quality, 'ROOT', checkout), \
                patch.object(offline_quality, '__file__', str(checkout / 'bench/offline_quality.py')), \
                patch.object(bundle, 'render') as physical:
            with self.assertRaisesRegex(ValueError, 'already spent by committed receipt/result'):
                self.start(root=checkout, dataset=checkout / 'dataset.json', policy=checkout / 'policy.json',
                           directory=checkout / 'out/retry', state_directory=checkout / 'out/retry-state')
            physical.assert_not_called()
            # Also inspect the public guard directly; the host marker is absent.
            with self.assertRaisesRegex(ValueError, 'already spent by committed receipt/result'):
                heldout_bench.committed_v2_spent(bundle.digest(self.dataset))
        self.assertFalse((checkout / 'out').exists())
        self.assertFalse(self.host_marker.exists())
        self.assertEqual(subprocess.check_output(
            ['git', '-C', str(checkout), 'rev-parse', 'HEAD'], text=True).strip(), self.commit)

    def test_second_checkout_at_policy_commit_refuses_reachable_prior_receipt(self):
        self.repeat_from_policy_checkout(linked=True)

    def test_detached_policy_commit_refuses_reachable_prior_receipt(self):
        self.repeat_from_policy_checkout(linked=False)

    def test_host_marker_refuses_after_receipt_is_unreachable_and_scratch_is_lost(self):
        with patch.object(bundle, 'render') as physical:
            first = self.start()
        self.assertEqual(physical.call_count, 6)
        self.assertTrue(self.host_marker.is_file(), 'A committed start must also persist host state')
        saved = self.host_marker.read_bytes()
        # A standalone source clone made from the policy tree has no receipt
        # ref at all. This models loss of repository history on the same host.
        self.git('checkout', '-q', '--detach', self.commit)
        clean = self.temporary / 'policy-only'
        # Use an explicit policy ref so clone cannot copy the spent branch.
        self.git('branch', 'policy-only', self.commit)
        subprocess.check_output(['git', 'clone', '-q', '--no-hardlinks', '--single-branch',
                                 '--branch', 'policy-only', str(self.base), str(clean)])
        for name, value in (('user.name', 'Synthetic heldout test'), ('user.email', 'test@example.invalid'),
                            ('commit.gpgsign', 'false'), ('core.hooksPath', str(clean / '.git/no-hooks'))):
            subprocess.check_output(['git', '-C', str(clean), 'config', name, value])
        reachable = subprocess.check_output(['git', '-C', str(clean), 'rev-list', '--all'], text=True).splitlines()
        self.assertNotIn(first['started_receipt_commit'], reachable)
        shutil.rmtree(self.base / 'out')
        from bench import offline_quality
        with patch.object(heldout_bench, 'CODE_ROOT', clean), \
                patch.object(heldout_bench, '__file__', str(clean / 'bench/heldout_bench.py')), \
                patch.object(bundle, '__file__', str(clean / 'bench/quality_bundle.py')), \
                patch.object(offline_quality, 'ROOT', clean), \
                patch.object(offline_quality, '__file__', str(clean / 'bench/offline_quality.py')), \
                patch.object(bundle, 'render') as physical:
            heldout_bench.committed_v2_spent(bundle.digest(self.dataset))
            with self.assertRaisesRegex(ValueError, 'already spent by host marker'):
                self.start(root=clean, dataset=clean / 'dataset.json', policy=clean / 'policy.json',
                           directory=clean / 'out/retry', state_directory=clean / 'out/retry-state')
            physical.assert_not_called()
        self.assertEqual(self.host_marker.read_bytes(), saved)
        self.assertFalse((clean / 'out').exists())

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux inherited EX lease uses /proc')
    def test_invalid_inherited_lease_refuses_before_any_persistent_change(self):
        from relay import soak
        canonical = self.temporary / 'inherited-perf.lock'
        real_lease = bundle.clip_lease.func
        index = (self.base / '.git/index').read_bytes()
        with patch.object(bundle, 'clip_lease', real_lease), \
                patch.object(soak, 'PERF_LOCK', canonical), \
                patch.dict(os.environ, {'IRL_SHIELD_PERF_QUEUE_LEASE_FD': 'not-an-fd'}), \
                patch.object(bundle, 'render') as physical:
            with self.assertRaisesRegex(RuntimeError, 'inherited canonical queue lease'):
                self.start()
            physical.assert_not_called()
            self.assert_unspent()
            self.assertEqual((self.base / '.git/index').read_bytes(), index)
            self.assertEqual(self.git('status', '--porcelain'), '')
            self.assertFalse((self.base / '.tmp').exists(), 'Invalid FD must precede serial lock creation')

    def test_spent_state_is_rechecked_after_lease_acquisition(self):
        real_lease = bundle.clip_lease
        @contextmanager
        def waiting_lease(*args, **kwargs):
            with real_lease(*args, **kwargs):
                # Another checkout's receipt becomes reachable while waiting.
                receipt = self.base / heldout_bench.V2_STARTED
                receipt.parent.mkdir(parents=True, exist_ok=True)
                bundle.write_json(receipt, {'heldout_freeze': {'dataset_sha256': bundle.digest(self.dataset)}})
                self.git('add', '--', heldout_bench.V2_STARTED)
                prior = self.commit_at('2026-11-01T14:01:00+00:00')
                self.git('branch', 'other-checkout-receipt', prior)
                self.git('checkout', '-q', '--detach', self.commit)
                yield
        with patch.object(bundle, 'clip_lease', waiting_lease), patch.object(bundle, 'render') as physical:
            with self.assertRaisesRegex(ValueError, 'already spent by committed receipt/result'):
                self.start()
            physical.assert_not_called()
        self.assert_unspent()

    def test_standalone_ex_lease_covers_marker_receipt_and_all_six_renders(self):
        import fcntl
        lock = self.base / '.tmp/locks/perf.lock'
        def assert_ex_held():
            self.assertTrue(lock.is_file(), 'EX lease must exist before the first start witness')
            with lock.open('a+') as competitor:
                with self.assertRaises(BlockingIOError, msg='EX lease must cover the whole v2 start'):
                    fcntl.flock(competitor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        real_exclusive = heldout_bench.exclusive_json
        def write_under_lease(path, value):
            assert_ex_held()
            return real_exclusive(path, value)
        with patch.object(heldout_bench, 'exclusive_json', side_effect=write_under_lease), \
                patch.object(bundle, 'render', side_effect=lambda *a, **k: assert_ex_held()) as physical:
            self.start()
        self.assertEqual(physical.call_count, 6)
        with lock.open('a+') as competitor:
            fcntl.flock(competitor, fcntl.LOCK_EX | fcntl.LOCK_NB)

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
        self.assertTrue(self.host_marker.is_file(), 'Failed receipt commits must retain the host spent marker')
        with patch.object(bundle, 'render') as physical:
            with self.assertRaisesRegex(ValueError, 'already spent by tracked result'):
                self.start()
            physical.assert_not_called()


class HeldoutV3Start(unittest.TestCase):
    # Reuse setup, not the v2 test collection. V2 assertions remain intact.
    git = HeldoutV2Start.git
    commit_at = HeldoutV2Start.commit_at

    def setUp(self):
        from bench import heldout_resources
        from test_heldout_resources import ResourceFixture
        HeldoutV2Start.setUp(self)
        override = patch.object(heldout_resources, '__file__', str(self.base / 'bench/heldout_resources.py'))
        override.start()
        self.addCleanup(override.stop)
        self.cache = self.cache.rename(self.cache.with_name('fresh-heldout-v3'))
        manifest = json.loads(self.dataset.read_text())
        manifest.update(dataset_id='fresh-heldout-v3',
            evaluation_marker='fixtures/cache/fresh-heldout-v3/EVALUATION.started.json',
            evaluation_reservation={'maximum_evaluations': 1, 'evaluation_started': False,
                                    'not_before_utc': '2026-11-02T12:00:00Z'})
        for clip in manifest['clips']:
            clip.update(height=64, width=64)
        for row in manifest['inputs']:
            for key in ('source', 'truth'):
                row[key] = row[key].replace('fresh-heldout-v2/', 'fresh-heldout-v3/')
        bundle.write_json(self.dataset, manifest)
        (self.base / '.gitignore').write_text('out/\n.tmp/\nfixtures/cache/\nmodels/cache/\n__pycache__/\n')
        receipts = self.base / 'bench/results'
        receipts.mkdir()
        (receipts / '.gitkeep').write_text('Synthetic tracked receipt destination.\n')
        contract = ResourceFixture.provision_resources(self, self.base)
        config = json.loads(self.policy.read_text())
        config['options']['encoder'] = 'libx264'
        config['resources'] = contract
        bundle.write_json(self.policy, config)
        self.git('add', '.')
        self.commit = self.commit_at('2026-11-02T12:00:00+00:00')
        self.clock.now.return_value = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
        self.host_marker = self.home / '.local/state/irl-shield' / (
            'fresh-heldout-v3-' + bundle.digest(self.dataset) + '.started')
        self.before = self.git_state()

    def start(self, **changes):
        return HeldoutV2Start.start(self, **{'model_cache': self.model_cache, **changes})

    def git_state(self):
        return {'head': self.git('rev-parse', 'HEAD'),
                'index': self._git_operation_path('index').read_bytes(),
                'staged': self.git('ls-files', '--stage'),
                'refs': self.git('for-each-ref', '--format=%(refname) %(objectname)')}

    def assert_git_unchanged(self, *, staged_content=False):
        actual, expected = self.git_state(), dict(self.before)
        if staged_content:
            # Git reset may refresh stat data while restoring the same entries.
            actual.pop('index')
            expected.pop('index')
        self.assertEqual(actual, expected)

    def assert_unspent(self, *, staged_content=False):
        self.assert_git_unchanged(staged_content=staged_content)
        self.assertFalse((self.base / heldout_bench.V3_STARTED).exists())
        self.assertFalse((self.base / heldout_bench.V2_STARTED).exists())
        self.assertFalse(self.state.exists())
        self.assertFalse(self.directory.exists())
        self.assertFalse(self.host_marker.exists())

    def test_commit_preconditions_refuse_before_any_reservation(self):
        hooks = self.base / '.git/no-hooks'
        hooks.mkdir(exist_ok=True)
        objects = self.base / '.git/objects'
        mode = objects.stat().st_mode & 0o777
        for fault in ('hook', 'signing', 'identity', 'objects', 'index-lock'):
            hook = hooks / 'pre-commit'
            try:
                if fault == 'hook':
                    hook.write_text('#!/bin/sh\nexit 73\n')
                    hook.chmod(0o755)
                elif fault == 'signing':
                    self.git('config', 'commit.gpgsign', 'true')
                elif fault == 'identity':
                    self.git('config', 'user.useConfigOnly', 'true')
                    self.git('config', '--unset', 'user.email')
                elif fault == 'objects':
                    objects.chmod(0o555)
                else:
                    (self.base / '.git/index.lock').write_text('synthetic existing lock\n')
                error = None
                with patch.object(bundle, 'render') as render:
                    try:
                        self.start()
                    except (ValueError, FileExistsError, subprocess.CalledProcessError) as caught:
                        error = caught
                    self.assertIsNotNone(error)
                    render.assert_not_called()
                self.assertFalse(self.host_marker.exists(), 'Commit preflight failure spent host marker')
                self.assert_unspent()
            finally:
                if hook.exists():
                    hook.unlink()
                lock = self.base / '.git/index.lock'
                if lock.exists():
                    lock.unlink()
                self.git('config', 'commit.gpgsign', 'false')
                self.git('config', 'user.email', 'test@example.invalid')
                objects.chmod(mode)

    def _git_operation_path(self, name):
        path = Path(self.git('rev-parse', '--git-path', name))
        return path if path.is_absolute() else self.base / path

    def _assert_git_operation_refused(self, name, *, readonly=False):
        path = self._git_operation_path(name)
        if readonly:
            mode = path.stat().st_mode & 0o777
            path.chmod(0o444)
            self.addCleanup(path.chmod, mode)
        elif name.startswith('rebase-'):
            path.mkdir()
            for entry, value in (('head-name', self.git('symbolic-ref', 'HEAD')),
                                 ('orig-head', self.commit), ('onto', self.commit)):
                (path / entry).write_text(value + '\n')
        else:
            path.write_text(self.commit + '\n')
        git_dir = self._git_operation_path('HEAD').parent
        def snapshot():
            return {p.relative_to(git_dir).as_posix(): (p.read_bytes(), p.stat().st_mode & 0o777)
                    for p in git_dir.rglob('*') if p.is_file()}
        before = snapshot()
        error = None
        with patch.object(bundle, 'render') as render:
            try:
                self.start()
            except Exception as caught:
                error = caught
            self.assertIsInstance(error, ValueError, 'Missing pre-reservation refusal: ' + name)
            expected = ('Git reflog is not writable: ' if readonly else 'Git operation in progress: ') + name
            self.assertIn(expected, str(error))
            render.assert_not_called()
        self.assert_unspent()
        self.assertEqual(snapshot(), before, 'Git state changed while refusing ' + name)

    def test_cherry_pick_in_progress_refuses_before_reservation(self):
        self._assert_git_operation_refused('CHERRY_PICK_HEAD')

    def test_merge_in_progress_refuses_before_reservation(self):
        self._assert_git_operation_refused('MERGE_HEAD')

    def test_revert_in_progress_refuses_before_reservation(self):
        self._assert_git_operation_refused('REVERT_HEAD')

    def test_rebase_merge_in_progress_refuses_before_reservation(self):
        self._assert_git_operation_refused('rebase-merge')

    def test_rebase_apply_in_progress_refuses_before_reservation(self):
        self._assert_git_operation_refused('rebase-apply')

    def test_readonly_head_reflog_refuses_before_reservation(self):
        self._assert_git_operation_refused('logs/HEAD', readonly=True)

    def test_readonly_branch_reflog_refuses_before_reservation(self):
        self._assert_git_operation_refused('logs/' + self.git('symbolic-ref', 'HEAD'), readonly=True)

    def _assert_commit_failure_is_retryable(self, fault):
        receipt = self.base / heldout_bench.V3_STARTED
        branch = self.git('symbolic-ref', 'HEAD')
        branch_before = self.git('rev-parse', branch)
        def tree():
            names = self.git('--no-optional-locks', 'ls-files', '-z', '--cached', '--others',
                             '--exclude-standard').split('\0')
            return {name: ((self.base / name).read_bytes(), (self.base / name).stat().st_mode & 0o777)
                    for name in names if name}
        original_tree = tree()
        override = nullcontext()
        injected = (BlockingIOError(11, 'Synthetic commit process launch failure') if fault == 'launch'
                    else subprocess.CalledProcessError(73, ['git', 'synthetic-commit-failure']))
        if fault == 'editmsg':
            path = self._git_operation_path('COMMIT_EDITMSG')
            mode = path.stat().st_mode & 0o777
            path.chmod(0o444)
        elif fault == 'excluded':
            path = self._git_operation_path('info/exclude')
            original = path.read_bytes()
            path.write_bytes(original + ('\n' + heldout_bench.V3_STARTED + '\n').encode())
        else:
            real_git = heldout_bench.git
            def fail_commit(*args):
                if 'commit' in args:
                    raise injected
                return real_git(*args)
            override = patch.object(heldout_bench, 'git', side_effect=fail_commit)
        try:
            error = None
            with override, patch.object(bundle, 'render') as render:
                try:
                    self.start()
                except Exception as caught:
                    error = caught
                self.assertIsInstance(error, OSError if fault == 'launch' else subprocess.CalledProcessError)
                if fault in ('injected', 'launch'):
                    self.assertIs(error, injected, 'Rollback replaced the original Git error')
                render.assert_not_called()
            self.assertFalse(self.host_marker.exists(), 'Failed commit spent the host marker')
            self.assertFalse(receipt.exists(), 'Failed commit left its receipt in the tree')
            self.assert_unspent(staged_content=True)
            self.assertEqual(self.git('rev-parse', branch), branch_before)
            self.assertEqual(tree(), original_tree)
            self.assertEqual(self.git('status', '--porcelain'), '')
            self.assertEqual(self.git('for-each-ref', '--format=%(objectname)',
                                     heldout_bench.started_ref({'dataset_sha256': bundle.digest(self.dataset)})), '')
            heldout_bench.committed_v2_spent(bundle.digest(self.dataset))
        finally:
            if fault == 'editmsg':
                path.chmod(mode)
            elif fault == 'excluded':
                path.write_bytes(original)
        with patch.object(bundle, 'render') as render:
            state = self.start()
        self.assertEqual(render.call_count, 6)
        self.assertEqual(state['status'], 'awaiting-judging')

    def _assert_receipt_write_failure_is_retryable(self, fault):
        receipt = self.base / heldout_bench.V3_STARTED
        injected = OSError(5, 'Synthetic receipt ' + fault + ' failure')
        real_open, real_fsync = Path.open, os.fsync
        @contextmanager
        def partial_writer(path, *args, **kwargs):
            with real_open(path, *args, **kwargs) as stream:
                def write(value):
                    stream.write(value[:8])
                    stream.flush()
                    raise injected
                yield SimpleNamespace(write=write, flush=stream.flush, fileno=stream.fileno)
        def open_file(path, *args, **kwargs):
            if Path(path) == receipt and args == ('x',):
                return partial_writer(path, *args, **kwargs)
            return real_open(path, *args, **kwargs)
        def fsync(fd):
            if receipt.exists():
                opened, current = os.fstat(fd), receipt.stat()
                if (opened.st_dev, opened.st_ino) == (current.st_dev, current.st_ino):
                    raise injected
            return real_fsync(fd)
        override = (patch.object(Path, 'open', open_file) if fault == 'write'
                    else patch.object(os, 'fsync', side_effect=fsync))
        with override, patch.object(bundle, 'render') as render:
            with self.assertRaises(OSError) as caught:
                self.start()
            self.assertIs(caught.exception, injected)
            render.assert_not_called()
        self.assertFalse(receipt.exists(), 'Failed write orphaned its unspent receipt')
        self.assert_unspent()
        with patch.object(bundle, 'render') as render:
            state = self.start()
        self.assertEqual(render.call_count, 6)
        self.assertEqual(state['status'], 'awaiting-judging')

    def test_receipt_write_failure_removes_own_inode_and_can_retry(self):
        self._assert_receipt_write_failure_is_retryable('write')

    def test_receipt_fsync_failure_removes_own_inode_and_can_retry(self):
        self._assert_receipt_write_failure_is_retryable('fsync')

    def test_failed_receipt_write_preserves_replacement_inode(self):
        receipt = self.base / heldout_bench.V3_STARTED
        replacement = b'Synthetic replacement belongs to another caller.\n'
        injected = OSError(5, 'Synthetic fsync failure after receipt replacement')
        real_fsync = os.fsync
        def fsync(fd):
            if receipt.exists():
                opened, current = os.fstat(fd), receipt.stat()
                if (opened.st_dev, opened.st_ino) == (current.st_dev, current.st_ino):
                    receipt.rename(receipt.with_suffix('.other-caller-saved'))
                    receipt.write_bytes(replacement)
                    raise injected
            return real_fsync(fd)
        with patch.object(os, 'fsync', side_effect=fsync), patch.object(bundle, 'render') as render:
            with self.assertRaises(OSError) as caught:
                self.start()
            self.assertIs(caught.exception, injected)
            render.assert_not_called()
        self.assertTrue(receipt.exists(), 'Write cleanup deleted another caller replacement')
        self.assertEqual(receipt.read_bytes(), replacement)
        self.assertTrue(any('replaced' in note for note in caught.exception.__notes__))
        self.assert_git_unchanged()
        self.assertFalse(self.host_marker.exists())
        self.assertFalse(self.directory.exists())
        self.assertFalse(self.state.exists())

    def test_reset_failure_unlinks_receipt_and_refuses_dirty_not_spent(self):
        receipt = self.base / heldout_bench.V3_STARTED
        real_git = heldout_bench.git
        injected = subprocess.CalledProcessError(73, ['git', 'synthetic-commit-failure'])
        def fail_commit_and_reset(*args):
            if 'commit' in args:
                raise injected
            if 'reset' in args:
                raise subprocess.CalledProcessError(128, ['git', 'synthetic-reset-failure'])
            return real_git(*args)
        with patch.object(heldout_bench, 'git', side_effect=fail_commit_and_reset), \
                patch.object(bundle, 'render') as render:
            with self.assertRaises(subprocess.CalledProcessError) as caught:
                self.start()
            self.assertIs(caught.exception, injected)
            self.assertTrue(any('reset' in note for note in caught.exception.__notes__))
            render.assert_not_called()
        self.assertFalse(receipt.exists(), 'Reset failure skipped inode-checked unlink')
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.commit)
        self.assertEqual(self.git('diff', '--cached', '--name-only'), heldout_bench.V3_STARTED)
        self.assertFalse(self.host_marker.exists())
        self.assertFalse(self.directory.exists())
        self.assertFalse(self.state.exists())
        self.assertEqual(self.git('for-each-ref', '--format=%(refname)',
                                 heldout_bench.started_ref({'dataset_sha256': bundle.digest(self.dataset)})), '')
        heldout_bench.committed_v2_spent(bundle.digest(self.dataset))
        with patch.object(bundle, 'render') as render:
            with self.assertRaisesRegex(ValueError, 'requires a clean committed source and policy checkout'):
                self.start()
            render.assert_not_called()
        self.git('reset', '-q', '--', heldout_bench.V3_STARTED)
        self.assert_unspent(staged_content=True)
        with patch.object(bundle, 'render') as render:
            state = self.start()
        self.assertEqual(render.call_count, 6)
        self.assertEqual(state['status'], 'awaiting-judging')

    def test_staged_receipt_is_dirty_checkout_not_committed_spend(self):
        receipt = self.base / heldout_bench.V3_STARTED
        receipt.write_text(json.dumps({'heldout_freeze': {'dataset_sha256': bundle.digest(self.dataset)}}))
        self.git('add', '--', heldout_bench.V3_STARTED)
        staged = self.git_state()
        with patch.object(bundle, 'render') as render:
            with self.assertRaisesRegex(ValueError, 'requires a clean committed source and policy checkout'):
                self.start()
            render.assert_not_called()
        self.assertEqual(self.git_state(), staged, 'Refusal changed the existing staged receipt')
        self.assertFalse(self.host_marker.exists())
        self.assertFalse(self.directory.exists())
        self.assertFalse(self.state.exists())
        self.git('reset', '-q', '--', heldout_bench.V3_STARTED)
        receipt.unlink()
        self.assert_unspent(staged_content=True)
        with patch.object(bundle, 'render') as render:
            state = self.start()
        self.assertEqual(render.call_count, 6)
        self.assertEqual(state['status'], 'awaiting-judging')

    def test_readonly_commit_editmsg_rolls_back_and_can_retry(self):
        self._assert_commit_failure_is_retryable('editmsg')

    def test_ignored_receipt_rolls_back_and_can_retry(self):
        self._assert_commit_failure_is_retryable('excluded')

    def test_arbitrary_commit_failure_rolls_back_and_can_retry(self):
        self._assert_commit_failure_is_retryable('injected')

    def test_commit_launch_error_rolls_back_and_can_retry(self):
        self._assert_commit_failure_is_retryable('launch')

    def test_git_error_after_commit_keeps_spent_history(self):
        real_git = heldout_bench.git
        injected = subprocess.CalledProcessError(73, ['git', 'synthetic-post-commit-failure'])
        def fail_after_commit(*args):
            result = real_git(*args)
            if 'commit' in args:
                raise injected
            return result
        with patch.object(heldout_bench, 'git', side_effect=fail_after_commit), \
                patch.object(bundle, 'render') as render:
            with self.assertRaises(subprocess.CalledProcessError) as caught:
                self.start()
            self.assertIs(caught.exception, injected)
            render.assert_not_called()
        self.assertNotEqual(self.git('rev-parse', 'HEAD'), self.commit)
        self.assertTrue((self.base / heldout_bench.V3_STARTED).is_file())
        self.assertFalse(self.host_marker.exists())
        with self.assertRaisesRegex(ValueError, 'already spent by committed receipt/result'):
            heldout_bench.committed_v2_spent(bundle.digest(self.dataset))

    def test_commit_failure_does_not_unlink_a_replaced_receipt(self):
        real_git = heldout_bench.git
        receipt = self.base / heldout_bench.V3_STARTED
        replacement = b'Synthetic other caller owns this replacement.\n'
        injected = subprocess.CalledProcessError(73, ['git', 'synthetic-replacement-race'])
        def replace_then_fail(*args):
            if 'commit' in args:
                receipt.rename(receipt.with_suffix('.saved-by-other-caller'))
                receipt.write_bytes(replacement)
                raise injected
            return real_git(*args)
        with patch.object(heldout_bench, 'git', side_effect=replace_then_fail), \
                patch.object(bundle, 'render') as render:
            with self.assertRaises(subprocess.CalledProcessError) as caught:
                self.start()
            self.assertIs(caught.exception, injected)
            render.assert_not_called()
        self.assertTrue(receipt.is_file(), 'Rollback deleted another caller replacement')
        self.assertEqual(receipt.read_bytes(), replacement)
        self.assert_git_unchanged(staged_content=True)
        self.assertFalse(self.host_marker.exists())

    def test_bad_selected_resources_leave_head_index_refs_and_markers_unchanged(self):
        from bench import heldout_resources as resources
        tiny = self.model_cache / 'ppocr-v6-tiny.onnx'
        original = tiny.read_bytes()
        for fault, message in (('missing', 'Missing heldout resource'),
                               ('wrong-cache', 'Missing heldout resource'), ('missing-cache', 'models'),
                               ('unbound', 'explicit --model-cache'), ('dependency', 'synthetic dependency missing'),
                               ('native-dependency', 'synthetic native import missing'),
                               ('executable', 'resource payload differs'), ('provider', 'synthetic provider unavailable')):
            with self.subTest(fault=fault):
                changes = {}
                override = nullcontext()
                if fault == 'missing':
                    tiny.unlink()
                elif fault == 'wrong-cache':
                    wrong = self.base / 'out/wrong-cache'
                    wrong.mkdir(parents=True)
                    changes['model_cache'] = wrong
                elif fault == 'missing-cache':
                    changes['model_cache'] = self.base / 'models/missing'
                elif fault == 'unbound':
                    changes['model_cache'] = None
                elif fault == 'dependency':
                    override = patch.object(resources.metadata, 'version', side_effect=RuntimeError('synthetic dependency missing'))
                elif fault == 'native-dependency':
                    override = patch.object(resources, 'import_module', side_effect=ImportError('synthetic native import missing'))
                elif fault == 'executable':
                    executable = Path(self.executables['ffmpeg'])
                    saved_executable = executable.read_bytes()
                    executable.write_bytes(b'x' * len(saved_executable))
                    # Simulate a changed runtime binary outside source control.
                    self.git('update-index', '--assume-unchanged', '--', 'tools/ffmpeg')
                    self.before = self.git_state()
                else:
                    override = patch.object(resources, 'provider_check', side_effect=RuntimeError('synthetic provider unavailable'))
                try:
                    with override, patch.object(bundle, 'render') as physical:
                        with self.assertRaisesRegex((ValueError, FileNotFoundError, RuntimeError, ImportError), message):
                            self.start(**changes)
                        physical.assert_not_called()
                    self.assert_unspent()
                finally:
                    tiny.write_bytes(original)
                    if fault == 'wrong-cache':
                        shutil.rmtree(self.base / 'out')
                    if fault == 'executable':
                        executable.write_bytes(saved_executable)
                        self.git('update-index', '--no-assume-unchanged', '--', 'tools/ffmpeg')
                        self.before = self.git_state()

    def test_same_size_corrupt_model_does_not_spend_attempt(self):
        tiny = self.model_cache / 'ppocr-v6-tiny.onnx'
        original = tiny.read_bytes()
        tiny.write_bytes(b'x' * len(original))
        with patch.object(bundle, 'render') as physical:
            with self.assertRaisesRegex(ValueError, 'Heldout resource payload differs'):
                self.start()
            physical.assert_not_called()
        self.assert_unspent()

    def test_preflight_status_cannot_refresh_index_before_resource_refusal(self):
        source = self.base / 'bench/heldout_resources.py'
        info = source.stat()
        os.utime(source, ns=(info.st_atime_ns, info.st_mtime_ns + 2_000_000_000))
        (self.model_cache / 'ppocr-v6-tiny.onnx').unlink()
        with patch.object(bundle, 'render') as physical:
            with self.assertRaisesRegex(FileNotFoundError, 'Missing heldout resource'):
                self.start()
            physical.assert_not_called()
        self.assert_unspent()

    def test_missing_required_static_artifacts_do_not_spend_attempt(self):
        config = json.loads(self.policy.read_text())
        config['options'].update(static_model=True, fast_width=64, accurate_width=64,
                                 fast_limit_side_len=64, limit_side_len=64)
        self.versions['onnx'] = 'synthetic-onnx'
        config['resources']['distributions'] = dict(self.versions)
        bundle.write_json(self.policy, config)
        self.git('add', 'policy.json')
        self.commit = self.commit_at('2026-11-02T12:00:00+00:00')
        self.before = self.git_state()
        with patch.object(bundle, 'render') as physical:
            with self.assertRaisesRegex(ValueError, 'derived model pins must match selected shapes exactly'):
                self.start()
            physical.assert_not_called()
        self.assert_unspent()

    def test_bad_output_placement_is_checked_before_reservation(self):
        blocked = self.temporary / 'read-only'
        blocked.mkdir()
        blocked.chmod(0o555)
        try:
            with patch.object(bundle, 'render') as physical:
                with self.assertRaisesRegex(ValueError, 'ancestor is not writable'):
                    self.start(directory=blocked / 'evaluation')
                physical.assert_not_called()
            self.assert_unspent()
        finally:
            blocked.chmod(0o755)

    def test_v3_reservation_and_prefix_cannot_rebind_v2(self):
        original = self.dataset.read_bytes()
        for fault, message in (('reservation', 'immutable one-shot reservation'),
                               ('prefix', 'frozen cache prefix'), ('source', 'three distinct source identities')):
            manifest = json.loads(original)
            if fault == 'reservation':
                manifest['evaluation_reservation']['not_before_utc'] = '2026-11-01T14:00:00Z'
            elif fault == 'prefix':
                manifest['inputs'][0]['source'] = 'fixtures/cache/fresh-heldout-v2/unselected.mp4'
            else:
                manifest['clips'][1]['source_sha256'] = manifest['clips'][0]['source_sha256']
            try:
                bundle.write_json(self.dataset, manifest)
                with self.assertRaisesRegex(ValueError, message):
                    bundle.frozen_dataset(self.dataset)
            finally:
                self.dataset.write_bytes(original)
        self.assert_unspent()

    def test_v3_wall_clock_and_policy_commit_must_both_reach_freeze(self):
        self.clock.now.return_value = datetime(2026, 11, 2, 11, 59, 59, tzinfo=timezone.utc)
        with patch.object(bundle, 'render') as physical:
            with self.assertRaisesRegex(ValueError, 'v3 cannot start before 2026-11-02T12:00:00Z'):
                self.start()
            physical.assert_not_called()
        self.assert_unspent()
        self.clock.now.return_value = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
        self.commit = self.commit_at('2026-11-02T11:59:59+00:00')
        self.before = self.git_state()
        with patch.object(bundle, 'render') as physical:
            with self.assertRaisesRegex(ValueError, 'final policy commit after the reservation freeze'):
                self.start()
            physical.assert_not_called()
        self.assert_unspent()

    def test_detached_receipt_is_pinned_at_first_render_and_visible_from_another_worktree(self):
        self.git('checkout', '-q', '--detach', self.commit)
        calls = []
        def physical(*args, **kwargs):
            head = self.git('rev-parse', 'HEAD')
            receipt = json.loads(self.git('show', head + ':' + heldout_bench.V3_STARTED))
            identity = receipt['heldout_freeze']
            ref = heldout_bench.started_ref(identity)
            self.assertEqual(self.git('rev-parse', ref), head)
            self.assertEqual(self.git('rev-parse', 'HEAD^'), self.commit)
            self.assertEqual(identity['policy_commit'], self.commit)
            with self.assertRaisesRegex(ValueError, 'sole committed change after the frozen policy'):
                heldout_bench.verify_started_commit({**identity, 'policy_sha256': '0' * 64}, head, receipt)
            self.assertEqual(self.git('diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD'), heldout_bench.V3_STARTED)
            self.assertEqual(self.git('status', '--porcelain'), '')
            self.assertEqual(kwargs['model_cache'], str(self.model_cache.resolve()))
            self.assertEqual(kwargs['resource_binding'], identity['resource_binding'])
            self.assertEqual(json.loads(self.host_marker.read_text())['heldout_freeze'], identity)
            self.assertTrue((self.state / (bundle.digest(self.dataset) + '.started.json')).is_file())
            calls.append((args[4], args[5]))
            raise RuntimeError('synthetic first render stop')
        with patch.object(bundle, 'render', side_effect=physical):
            with self.assertRaisesRegex(RuntimeError, '^synthetic first render stop$'):
                self.start()
        self.assertEqual(calls, [('v2-a', False)])
        receipt_commit = self.git('rev-parse', 'HEAD')
        state = json.loads((self.directory / 'evaluation.json').read_text())
        self.assertEqual(state['status'], 'partial-failed')
        self.assertEqual(state['policy_commit'], self.commit)
        self.assertEqual(state['started_receipt_commit'], receipt_commit)
        # Move detached HEAD away and lose only synthetic local/host state.
        self.git('reset', '--hard', self.commit)
        self.git('checkout', '-q', '--detach', self.commit)
        self.host_marker.unlink()
        shutil.rmtree(self.base / 'out')
        linked = self.temporary / 'second-v3-checkout'
        self.git('worktree', 'add', '-q', '--detach', str(linked), self.commit)
        self.assertEqual(self.git('rev-parse', state['started_receipt_ref']), receipt_commit)
        with patch.object(heldout_bench, 'CODE_ROOT', linked), patch.object(bundle, 'render') as physical:
            with self.assertRaisesRegex(ValueError, 'already spent by committed receipt/result'):
                self.start(root=linked, dataset=linked / 'dataset.json', policy=linked / 'policy.json',
                           directory=linked / 'out/retry', state_directory=linked / 'out/state')
            physical.assert_not_called()
        self.assertFalse((linked / 'out').exists())
        self.assertFalse(self.host_marker.exists())

    def test_ref_failure_retains_committed_spent_state_and_never_renders(self):
        real_git = heldout_bench.git
        def fail_ref(*args):
            if 'update-ref' in args:
                raise subprocess.CalledProcessError(73, ['git', *args])
            return real_git(*args)
        with patch.object(heldout_bench, 'git', side_effect=fail_ref), patch.object(bundle, 'render') as physical:
            with self.assertRaises(subprocess.CalledProcessError) as failure:
                self.start()
            self.assertEqual(failure.exception.returncode, 73)
            physical.assert_not_called()
        self.assertFalse(self.host_marker.exists())
        self.assertTrue((self.base / heldout_bench.V3_STARTED).is_file())
        self.assertNotEqual(self.git('rev-parse', 'HEAD'), self.commit)
        self.assertEqual(self.git('for-each-ref', '--format=%(refname)',
                                 heldout_bench.started_ref({'dataset_sha256': bundle.digest(self.dataset)})), '')
        self.assertFalse(self.directory.exists())
        self.assertFalse(self.state.exists())
        with patch.object(bundle, 'render') as physical:
            with self.assertRaisesRegex(ValueError, 'already spent by committed receipt/result'):
                self.start()
            physical.assert_not_called()

    def test_existing_ref_is_never_overwritten_or_spent(self):
        identity = {'dataset_sha256': bundle.digest(self.dataset)}
        ref = heldout_bench.started_ref(identity)
        self.git('update-ref', ref, self.commit)
        self.before = self.git_state()
        with patch.object(bundle, 'render') as physical:
            with self.assertRaisesRegex(ValueError, 'started ref already exists'):
                self.start()
            physical.assert_not_called()
        self.assert_unspent()
        self.assertEqual(self.git('rev-parse', ref), self.commit)

    def test_lost_ref_between_receipt_and_render_refuses_all_render_calls(self):
        real_write = bundle.write_json
        def remove_ref_before_render(path, value):
            real_write(path, value)
            if Path(path) == self.directory / 'evaluation.json' and value['status'] == 'rendering':
                self.git('update-ref', '-d', value['started_receipt_ref'])
        with patch.object(bundle, 'write_json', side_effect=remove_ref_before_render), patch.object(bundle, 'render') as physical:
            with self.assertRaises(subprocess.CalledProcessError):
                self.start()
            physical.assert_not_called()
        self.assertTrue(self.host_marker.is_file())
        self.assertEqual(json.loads((self.directory / 'evaluation.json').read_text())['status'], 'partial-failed')

    def test_ref_creation_race_cannot_overwrite_the_other_reservation(self):
        real_git = heldout_bench.git
        ref = heldout_bench.started_ref({'dataset_sha256': bundle.digest(self.dataset)})
        raced = []
        def competing_ref(*args):
            if 'update-ref' in args:
                real_git('update-ref', ref, self.commit)
                raced.append(ref)
            return real_git(*args)
        with patch.object(heldout_bench, 'git', side_effect=competing_ref), patch.object(bundle, 'render') as physical:
            with self.assertRaises(subprocess.CalledProcessError):
                self.start()
            physical.assert_not_called()
        self.assertEqual(raced, [ref])
        self.assertEqual(self.git('rev-parse', ref), self.commit)
        self.assertFalse(self.host_marker.exists())
        self.assertFalse(self.directory.exists())
        self.assertFalse(self.state.exists())

    def test_host_marker_failure_after_ref_keeps_spent_state_without_render(self):
        failure = OSError('Synthetic host marker failure after ref')
        with patch.object(heldout_bench, 'reserve_v2_host', side_effect=failure), \
                patch.object(bundle, 'render') as render:
            with self.assertRaises(OSError) as caught:
                self.start()
            self.assertIs(caught.exception, failure)
            render.assert_not_called()
        head = self.git('rev-parse', 'HEAD')
        self.assertNotEqual(head, self.commit)
        ref = heldout_bench.started_ref({'dataset_sha256': bundle.digest(self.dataset)})
        self.assertEqual(self.git('rev-parse', ref), head)
        self.assertFalse(self.host_marker.exists())
        self.assertFalse(self.directory.exists())
        self.assertFalse(self.state.exists())
        with self.assertRaisesRegex(ValueError, 'already spent by committed receipt/result'):
            heldout_bench.committed_v2_spent(bundle.digest(self.dataset))

    def test_valid_resources_render_six_pairs_with_one_committed_referenced_start(self):
        seen = []
        def physical(*args, **kwargs):
            started = kwargs['started_receipt']
            identity = started['identity']
            heldout_bench.verify_started_commit(identity, started['commit'], started['receipt'])
            self.assertEqual(identity['policy_commit'], self.commit)
            self.assertEqual(self.git('rev-parse', heldout_bench.started_ref(identity)), started['commit'])
            self.assertEqual(kwargs['resource_binding'], identity['resource_binding'])
            self.assertEqual(kwargs['model_cache'], str(self.model_cache.resolve()))
            seen.append((args[4], args[5], started['commit']))
        with patch.object(bundle, 'render', side_effect=physical):
            result = self.start()
        self.assertEqual([(clip, variant) for clip, variant, _ in seen],
                         [(row['clip'], row['synthetic_variant']) for row in self.rows])
        self.assertEqual(len(seen), 6)
        self.assertEqual({commit for _, _, commit in seen}, {result['started_receipt_commit']})
        self.assertEqual(result['policy_commit'], self.commit)
        self.assertEqual(result['status'], 'awaiting-judging')
        self.assertEqual(self.git('rev-parse', result['started_receipt_ref']), result['started_receipt_commit'])

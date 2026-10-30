"""Fresh heldout contracts, with generated pixels and fake detector/judge boundaries."""
import json
from pathlib import Path
import shutil
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
        provider = SimpleNamespace(check_output=lambda *args, **kwargs: self.commit + '\n')
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
        for change in ('missing-third', 'duplicate', 'changed-media', 'absolute-path'):
            with self.subTest(change=change):
                bad = json.loads(json.dumps(self.data))
                if change == 'missing-third':
                    bad['clips'] = bad['clips'][:4]
                elif change == 'duplicate':
                    bad['clips'][-1] = bad['clips'][0]
                elif change == 'changed-media':
                    bad['clips'][0]['source_sha256'] = '0' * 64
                else:
                    bad['clips'][0]['source'] = '/tmp/unsealed.mp4'
                bundle.write_json(self.inputs, bad)
                with self.assertRaisesRegex(ValueError, 'heldout|frozen|escapes'):
                    bundle.entries(self.base, self.inputs, dataset=self.dataset)

    def corpus(self, *, mixed=False):
        directory = self.base / 'corpus'
        for clip in self.ids:
            for variant in (False, True):
                if mixed and clip == 'fresh-c':
                    policy = json.loads(self.fixture.config.read_text())
                    policy['options']['area_ceiling'] = .9
                    bundle.write_json(self.fixture.config, policy)
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

    def test_mixed_heldout_policy_rejects_before_scorecard(self):
        corpus = self.corpus(mixed=True)
        with self.assertRaisesRegex(ValueError, 'different policies'):
            bundle.aggregate(ROOT, corpus, 'mixed', dataset=self.dataset)
        self.assertFalse((corpus / 'scorecard.json').exists())

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

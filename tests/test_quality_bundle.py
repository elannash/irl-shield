"""Encoded quality credit stays bound to frozen inputs and local sealed masks."""
import hashlib
from functools import partial
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from bench import quality_bundle as bundle


ROOT = Path(__file__).resolve().parents[1]


class QualityLease(unittest.TestCase):
    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux inherited EX lease uses /proc')
    def test_queue_lease_is_verified_and_reused_without_relocking(self):
        import fcntl
        from lock_isolation import install_lock_guard
        from relay import soak
        install_lock_guard()
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            canonical = base / 'perf.lock'
            with canonical.open('a+') as lease, patch.object(soak, 'PERF_LOCK', canonical), \
                    patch.dict(os.environ, {'IRL_SHIELD_PERF_QUEUE_LEASE_FD': str(lease.fileno())}):
                fcntl.flock(lease, fcntl.LOCK_EX)
                with bundle.clip_lease(base, 'linux'):
                    self.assertTrue(soak.require_queue_lease()['exclusive'])
                self.assertTrue(soak.require_queue_lease()['exclusive'])
                for mode in (fcntl.LOCK_SH, fcntl.LOCK_UN):
                    fcntl.flock(lease, mode)
                    with self.subTest(mode=mode), self.assertRaisesRegex(RuntimeError, 'no exclusive flock'):
                        with bundle.clip_lease(base, 'linux'):
                            self.fail('A nonexclusive inherited descriptor reached the clip')
                fcntl.flock(lease, fcntl.LOCK_EX)
                with (base / 'other.lock').open('a+') as other:
                    fcntl.flock(other, fcntl.LOCK_EX)
                    with patch.dict(os.environ, {'IRL_SHIELD_PERF_QUEUE_LEASE_FD': str(other.fileno())}):
                        with self.assertRaisesRegex(RuntimeError, 'does not identify the canonical lock'):
                            with bundle.clip_lease(base, 'linux'):
                                self.fail('A different lock reached the clip')
                with patch.dict(os.environ, {'IRL_SHIELD_PERF_QUEUE_LEASE_FD': 'not-an-fd'}):
                    with self.assertRaisesRegex(RuntimeError, 'requires an inherited canonical queue lease'):
                        with bundle.clip_lease(base / 'invalid', 'linux'):
                            self.fail('An invalid descriptor reached the clip')
                    self.assertFalse((base / 'invalid').exists(),
                                     'Invalid inherited descriptors must precede serial lock creation')
                self.assertTrue(soak.require_queue_lease()['exclusive'])


class Detector:
    def detect_quads(self, pixels):
        return [[[8, 8], [24, 8], [24, 16], [8, 16]],
                [[60, 8], [76, 8], [76, 16], [60, 16]]]

    def close(self):
        pass


class Judge:
    names = ['tesseract', 'vision-accurate', 'ppocr-independent']
    calls = 0

    def read(self, pixels):
        self.calls += 1
        readings = []
        for text, box in [('ELM ROAD', [8, 8, 24, 16]), ('42 CEDAR', [60, 8, 76, 16])]:
            x0, y0, x1, y1 = box
            if pixels[y0:y1, x0:x1].mean() > 180:
                readings.extend({'text': text, 'confidence': .99, 'box': box, 'judge': judge}
                                for judge in self.names)
        return readings


class QualityBundle(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        isolated_lease = patch.object(bundle, 'clip_lease', partial(bundle.clip_lease, lock_root=self.base / 'locks'))
        isolated_lease.start()
        self.addCleanup(isolated_lease.stop)
        yy, xx = np.indices((48, 96))
        pixels = np.repeat((80 + ((xx // 4 + yy // 4) % 2) * 50).astype(np.uint8)[..., None], 3, axis=2)
        pixels[8:16, 8:24] = pixels[8:16, 60:76] = 245
        self.source, self.truth = self.base / 'source.mp4', self.base / 'truth.json'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'rawvideo',
                        '-pix_fmt', 'bgr24', '-s', '96x48', '-r', '10', '-i', 'pipe:0', '-an',
                        '-c:v', 'libx264', '-preset', 'ultrafast', '-threads', '2', '-bf', '0',
                        '-pix_fmt', 'yuv420p', str(self.source)], input=pixels.tobytes() * 4, check=True, timeout=20)
        label = {'id': 'house', 'text': '42 CEDAR', 'box': [60, 8, 76, 16], 'visible': True}
        bundle.write_json(self.truth, [[label] for _ in range(4)])
        self.clips = [c['id'] for c in json.loads((ROOT / 'fixtures/manifest.json').read_text())['clips'] if c['split'] == 'tune']
        self.inputs = self.base / 'inputs.json'
        bundle.write_json(self.inputs, {'fixture_manifest_sha256': bundle.digest(ROOT / 'fixtures/manifest.json'),
            'clips': [{'clip': clip, 'synthetic_variant': variant, 'source': str(self.source), 'truth': str(self.truth),
                       'source_sha256': bundle.digest(self.source), 'truth_sha256': bundle.digest(self.truth)}
                      for clip in self.clips for variant in (False, True)]})
        self.config = self.base / 'policy.json'
        bundle.write_json(self.config, {'candidate': 'ppocr-v6-small', 'options': {
            'fast_candidate': 'ppocr-v6-tiny', 'encoder': 'libx264',
            'fast_rate_hz': 10., 'accurate_rate_hz': 10., 'fast_width': 0, 'accurate_width': 0,
            'delay_seconds': .2, 'before': 6, 'after': 2, 'padding': 0.,
            'motion_mode': 'phase', 'area_ceiling': .01,
            'area_ceiling_basis': 'unit:sealed-known-mask-pixels'}})

    def render(self, directory, clip=None, synthetic=False, *, inputs=None):
        with patch('bench.pipeline.detector_for', side_effect=lambda *args: Detector()):
            return bundle.render(ROOT, inputs or self.inputs, self.config, directory,
                                 clip or self.clips[0], synthetic)

    def corpus(self, name, *, mixed_inputs=None):
        directory = self.base / name
        for index, clip in enumerate(self.clips):
            for synthetic in (False, True):
                path = directory / (clip + ('-synthetic' if synthetic else '-natural'))
                self.render(path, clip, synthetic, inputs=mixed_inputs if index == 0 else None)
                bundle.grade(ROOT, path, judge=Judge())
        return directory

    def test_real_encoded_bundle_requires_input_pixels_judging_and_unchanged_masks(self):
        directory = self.base / 'run/one'
        plan = self.render(directory)
        self.assertEqual(plan['status'], 'awaiting-judging')
        self.assertEqual(plan['frames'], 4)
        self.assertTrue((directory / 'masked.mp4').is_file())
        self.assertFalse((directory / 'grade.json').exists())
        self.assertNotIn('natural', plan)
        self.assertNotIn('synthetic', plan)
        with self.assertRaisesRegex(ValueError, 'must be judged'):
            bundle.aggregate(ROOT, self.base / 'run', 'unfinished')
        judge = Judge()
        masks = directory / 'masked.masks.json'
        before = masks.read_bytes()
        masks.write_bytes(before + b' ')
        with self.assertRaisesRegex(ValueError, 'artifact changed: masked.masks.json'):
            bundle.grade(ROOT, directory, judge=judge)
        self.assertEqual(judge.calls, 0)
        masks.write_bytes(before)
        self.assertEqual(bundle.verify(directory)['frames'], 4)
        scored = bundle.grade(ROOT, directory, judge=judge)
        self.assertEqual(scored['natural'], {'hidden': 1, 'total': 1, 'hidden_fraction': 1.})
        self.assertEqual(scored['synthetic'], {'hidden': 1, 'total': 1, 'hidden_fraction': 1.})
        self.assertEqual(scored['synthetic_input_control'], {'total': 1, 'unreadable': 0})
        self.assertEqual(judge.calls, 8)
        self.assertTrue(scored['real_video_pass'])
        self.assertFalse(scored['real_time_verified'])

    def test_relocated_corpus_uses_only_its_verified_local_mask_records(self):
        original = self.corpus('original')
        relocated = self.base / 'relocated'
        shutil.copytree(original, relocated)
        for path in original.glob('*/masked.masks.json'):
            rows = json.loads(path.read_text())
            for row in rows:
                row['mask_fraction'] = 0.
            bundle.write_json(path, rows)
        card = bundle.aggregate(ROOT, relocated, 'relocated')
        self.assertGreater(card['masked_area_fraction']['p50'], .01)
        self.assertFalse(card['quality_checks']['masked_area'])
        self.assertFalse(card['comparison_valid'])
        self.assertTrue(card['real_video_pass'])
        original.rename(self.base / 'retired')
        repeated = bundle.aggregate(ROOT, relocated, 'relocated-again')
        self.assertEqual(repeated['masked_area_fraction'], card['masked_area_fraction'])

    def test_different_frozen_input_manifests_cannot_form_one_experiment(self):
        alternate_truth = self.base / 'alternate.truth.json'
        alternate_truth.write_bytes(self.truth.read_bytes() + b'\n')
        alternate = json.loads(self.inputs.read_text())
        for row in alternate['clips']:
            row.update(truth=str(alternate_truth), truth_sha256=bundle.digest(alternate_truth))
        path = self.base / 'alternate-inputs.json'
        bundle.write_json(path, alternate)
        corpus = self.corpus('mixed', mixed_inputs=path)
        with self.assertRaisesRegex(ValueError, 'different experiment identities'):
            bundle.aggregate(ROOT, corpus, 'mixed')

    def test_different_sealed_area_ceilings_cannot_form_one_policy(self):
        directory = self.base / 'mixed-ceilings'
        policy = json.loads(self.config.read_text())
        first = min(self.clips)
        ceilings = []
        for clip in self.clips:
            for synthetic in (False, True):
                policy['options']['area_ceiling'] = 1. if clip == first and not synthetic else .01
                bundle.write_json(self.config, policy)
                path = directory / (clip + ('-synthetic' if synthetic else '-natural'))
                plan = self.render(path, clip, synthetic)
                ceilings.append(plan['options']['area_ceiling'])
                bundle.grade(ROOT, path, judge=Judge())
        self.assertEqual(sorted(ceilings), [.01] * 13 + [1.])
        with self.assertRaisesRegex(ValueError, 'different policies'):
            bundle.aggregate(ROOT, directory, 'mixed-ceilings')
        self.assertFalse((directory / 'scorecard.json').exists())

    def test_changed_source_or_truth_during_copy_fails_before_models_start(self):
        copy = shutil.copyfile
        for target in (self.source, self.truth):
            with self.subTest(target=target.name):
                original = target.read_bytes()
                def racing_copy(source, destination):
                    if Path(source) == target:
                        target.write_bytes(original + b'\n')
                    return copy(source, destination)
                try:
                    with patch.object(bundle.shutil, 'copyfile', side_effect=racing_copy), \
                         patch('bench.pipeline.detector_for', side_effect=lambda *args: Detector()) as factory:
                        with self.assertRaisesRegex(ValueError, 'copied.*(input|source|truth)|Frozen.*changed'):
                            bundle.render(ROOT, self.inputs, self.config, self.base / target.stem,
                                          self.clips[0], False)
                    self.assertEqual(factory.call_count, 0)
                finally:
                    target.write_bytes(original)

    def test_input_manifest_is_one_snapshot_even_if_the_original_changes(self):
        original = self.inputs.read_bytes()
        changed = json.loads(original)
        changed['scope'] = 'A later manifest revision'
        copy = shutil.copyfile
        def racing_copy(source, destination):
            bundle.write_json(self.inputs, changed)
            return copy(source, destination)
        with patch.object(bundle.shutil, 'copyfile', side_effect=racing_copy):
            plan = self.render(self.base / 'snapshot')
        self.assertEqual(plan['input_manifest_sha256'], hashlib.sha256(original).hexdigest())
        self.assertNotEqual(plan['input_manifest_sha256'], bundle.digest(self.inputs))
        self.assertEqual((self.base / 'snapshot/inputs.json').read_bytes(), original)


    def test_v3_bound_model_cache_reaches_session_and_restores_default_on_failure(self):
        from bench import heldout_bench, heldout_resources, onnx_detectors
        cache = self.base / 'fixtures/cache/fresh-heldout-v3'
        cache.mkdir(parents=True)
        shutil.copyfile(self.source, cache / 'source.mp4')
        shutil.copyfile(self.truth, cache / 'truth.json')
        dataset = self.base / 'dataset.json'
        ids = ['synthetic-a', 'synthetic-b', 'synthetic-c']
        rows = [{'clip': clip, 'synthetic_variant': variant,
                 'source': 'fixtures/cache/fresh-heldout-v3/source.mp4',
                 'truth': 'fixtures/cache/fresh-heldout-v3/truth.json',
                 'source_sha256': bundle.digest(self.source), 'truth_sha256': bundle.digest(self.truth)}
                for clip in ids for variant in (False, True)]
        bundle.write_json(dataset, {'schema_version': 1, 'dataset_id': 'fresh-heldout-v3',
            'status': 'frozen-ungraded', 'split': 'heldout',
            'evaluation_marker': 'fixtures/cache/fresh-heldout-v3/EVALUATION.started.json',
            'evaluation_reservation': {'maximum_evaluations': 1, 'evaluation_started': False,
                                     'not_before_utc': '2026-11-02T12:00:00Z'},
            'clips': [{'id': clip, 'split': 'heldout', 'source_sha256': str(index) * 64,
                       'source_path': f'original-{index}.webm', 'source_url': f'https://example.invalid/{index}'}
                      for index, clip in enumerate(ids)], 'inputs': rows})
        inputs = self.base / 'heldout-inputs.json'
        bundle.write_json(inputs, {'fixture_manifest_sha256': bundle.digest(dataset), 'clips': rows})
        model_cache = self.base / 'separate-model-cache'
        model_cache.mkdir()
        binding = {'model_cache': str(model_cache), 'files': {'ppocr-v6-tiny': {'synthetic': True}}}
        identity = {'dataset_id': 'fresh-heldout-v3', 'dataset_sha256': bundle.digest(dataset),
                    'policy_sha256': bundle.digest(self.config), 'resource_binding': binding,
                    **heldout_bench.source_identity(ROOT)}
        started = {'identity': identity, 'commit': 'a' * 40, 'receipt': {'synthetic': True}}
        previous = onnx_detectors.DEFAULT_CACHE
        seen = []
        def model_path(name, cache_dir):
            seen.append((name, Path(cache_dir)))
            self.assertEqual(Path(cache_dir), model_cache)
            raise RuntimeError('synthetic model-session boundary')
        # Resource validation and Git have their own real-file/temp-Git tests.
        # This encoded fixture owns wiring through the actual lane factory and
        # _session; stop at model payload lookup before constructing a session.
        with patch.object(heldout_resources, 'preflight', return_value=binding), \
                patch.object(heldout_bench, 'verify_started_commit') as receipt_check, \
                patch.object(onnx_detectors, 'verified_path', side_effect=model_path):
            with self.assertRaisesRegex(RuntimeError, '^synthetic model-session boundary$'):
                bundle.render(self.base, inputs, self.config, self.base / 'bound-render', ids[0], False,
                              dataset=dataset, model_cache=model_cache, resource_binding=binding, started_receipt=started)
        self.assertEqual(seen, [('ppocr-v6-tiny', model_cache)])
        receipt_check.assert_called_once_with(identity, 'a' * 40, started['receipt'])
        self.assertEqual(onnx_detectors.DEFAULT_CACHE, previous)
        self.assertFalse((self.base / 'bound-render/bundle.json').exists())


if __name__ == '__main__':
    unittest.main()


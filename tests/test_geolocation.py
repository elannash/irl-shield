"""Synthetic protocol tests; no natural pixels, model import, or hardware."""
import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest

from bench.geolocation.protocol import (aggregate, distance_km, freeze, registration,
                                        sha256, verify_plan)
from bench.geolocation.run import verify_model_assets


class GeolocationProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.reg = self.root / 'registration.json'
        self.pairs = self.root / 'pairs.json'
        self.plan = self.root / 'plan.json'
        self.results = self.root / 'results.json'
        self.data = {'samples': [
            {'id': 'sf-market', 'frame_index': 60, 'source_clip_sha256': 'a' * 64,
             'ground_truth': {'coordinate': [0., 0.], 'uncertainty_km': 5.}}],
            'sample_n': 1, 'top_k': [1, 5], 'thresholds_km': [1, 25, 200, 750, 2500],
            'limitations': ['Synthetic test data'], 'model_manifest_sha256': 'b' * 64}
        self.save(self.reg, self.data)
        artifacts = {}
        for key in ('policy', 'exporter', 'source_receipt'):
            path = self.root / key
            path.write_text('synthetic ' + key)
            artifacts[key] = {'path': key, 'sha256': sha256(path)}
        pair = {'id': 'sf-market', 'frame_index': 60, 'shield_source_index': 60,
                'source_clip_sha256': 'a' * 64, 'slate': False, 'real_video': True}
        for arm in ('raw', 'shielded'):
            path = self.root / (arm + '.png')
            # Only container parsing is under test; no pixel decoder is called.
            path.write_bytes(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' + struct.pack('>II', 1280, 720))
            pair[arm] = {'path': path.name, 'sha256': sha256(path)}
        self.export = {**artifacts, 'pairs': [pair]}
        self.save(self.pairs, self.export)

    def save(self, path, value):
        path.write_text(json.dumps(value))

    def bind(self):
        freeze(self.reg, self.pairs, self.root, self.plan)

    def predictions(self):
        self.bind()
        # Raw's first choice is right. Shielded's fifth choice is right.
        rows = [{'id': 'sf-market', 'arm': 'raw', 'status': 'ok',
                 'frame_sha256': self.export['pairs'][0]['raw']['sha256'],
                 'candidates': [[0., 0.], [30., 30.], [40., 40.], [50., 50.], [60., 60.]]},
                {'id': 'sf-market', 'arm': 'shielded', 'status': 'ok',
                 'frame_sha256': self.export['pairs'][0]['shielded']['sha256'],
                 'candidates': [[30., 30.], [40., 40.], [50., 50.], [60., 60.], [0., 0.]]}]
        result = {'plan_sha256': sha256(self.plan), 'model_manifest_sha256': 'b' * 64, 'rows': rows}
        self.save(self.results, result)
        return result

    def test_haversine_wraps_dateline_and_antipodes(self):
        self.assertAlmostEqual(distance_km([0., 179.9], [0., -179.9]), 22.239016, places=5)
        self.assertAlmostEqual(distance_km([0., 0.], [0., 180.]), 20015.114442, places=5)
        with self.assertRaises(ValueError):
            distance_km([float('nan'), 0.], [0., 0.])

    def test_freeze_rejects_misalignment_slate_and_hash_substitution(self):
        for key, value, message in [('shield_source_index', 61, 'alignment'),
                                    ('slate', True, 'Slate'), ('real_video', False, 'non-video')]:
            with self.subTest(key=key):
                changed = copy.deepcopy(self.export)
                changed['pairs'][0][key] = value
                self.save(self.pairs, changed)
                with self.assertRaisesRegex(ValueError, message):
                    freeze(self.reg, self.pairs, self.root, self.plan)
        self.save(self.pairs, self.export)
        (self.root / 'shielded.png').write_bytes(b'substituted')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            freeze(self.reg, self.pairs, self.root, self.plan)

    def test_registration_rejects_reserved_or_unregistered_clip(self):
        self.data['samples'][0]['id'] = 'reserved-new-clip'
        self.save(self.reg, self.data)
        with self.assertRaisesRegex(ValueError, 'tune samples'):
            registration(self.reg)

    def test_frozen_plan_detects_artifact_drift_and_refuses_overwrite(self):
        self.bind()
        with self.assertRaises(FileExistsError):
            freeze(self.reg, self.pairs, self.root, self.plan)
        (self.root / 'policy').write_text('different actual masking policy')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            verify_plan(self.plan, self.reg, self.root)

    def test_scoring_topk_distance_uncertainty_and_public_redaction(self):
        self.predictions()
        output = aggregate(self.reg, self.plan, self.results)
        self.assertEqual(output['status'], 'complete')
        self.assertEqual(output['primary']['raw'], {'definite': 1., 'possible': 1.})
        self.assertEqual(output['primary']['shielded'], {'definite': 0., 'possible': 0.})
        self.assertEqual(output['arms']['raw']['median_top1_distance_km'], 0.)
        self.assertGreater(output['arms']['shielded']['median_top1_distance_km'], 4000.)
        self.assertEqual(output['arms']['raw']['hit_rate_bounds']['top1_within_1km'],
                         {'definite': 0., 'possible': 1.})
        self.assertEqual(output['arms']['shielded']['hit_rate_bounds']['top5_within_25km'],
                         {'definite': 1., 'possible': 1.})
        public = json.dumps(output)
        for private in ('sf-market', 'candidates', 'coordinate', 'png', str(self.root)):
            self.assertNotIn(private, public)

    def test_failed_attempts_are_retained_and_never_count_as_protection(self):
        result = self.predictions()
        result['rows'][1].update(status='failed', candidates=[])
        self.save(self.results, result)
        output = aggregate(self.reg, self.plan, self.results)
        self.assertEqual(output['status'], 'incomplete')
        self.assertIsNone(output['primary']['shielded'])
        self.assertIsNone(output['arms']['raw']['mean_top1_distance_km'])
        self.assertEqual(output['arms']['shielded']['attempted_n'], 1)
        self.assertEqual(output['arms']['shielded']['failed_n'], 1)
        self.assertEqual(output['arms']['shielded']['hit_rate_bounds']['top1_within_25km'],
                         {'definite': 0., 'possible': 1.})

    def test_scoring_rejects_missing_duplicate_or_substituted_results(self):
        result = self.predictions()
        variants = [result['rows'][:-1], result['rows'] + [result['rows'][0]]]
        for rows in variants:
            with self.subTest(rows=len(rows)):
                self.save(self.results, {**result, 'rows': rows})
                with self.assertRaisesRegex(ValueError, 'paired prediction rows'):
                    aggregate(self.reg, self.plan, self.results)
        self.save(self.results, {**result, 'plan_sha256': '0' * 64})
        with self.assertRaisesRegex(ValueError, 'frozen experiment'):
            aggregate(self.reg, self.plan, self.results)
        result['rows'][0]['frame_sha256'] = '0' * 64
        self.save(self.results, result)
        with self.assertRaisesRegex(ValueError, 'frame hash'):
            aggregate(self.reg, self.plan, self.results)

    def test_model_artifact_substitution_is_rejected_before_import(self):
        path = self.root / 'weights'
        path.write_bytes(b'synthetic weights')
        manifest = {'geoclip': {'artifacts': [{'file': 'weights', 'sha256': sha256(path)}]},
                    'backbone': {'artifacts': []}}
        verify_model_assets(manifest, self.root, self.root)
        path.write_bytes(b'different weights')
        with self.assertRaisesRegex(ValueError, 'differs from license manifest'):
            verify_model_assets(manifest, self.root, self.root)


if __name__ == '__main__':
    unittest.main()

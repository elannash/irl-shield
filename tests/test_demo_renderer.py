"""Public export safety and exact alignment at the archive-reader boundary.

These tests own provenance/identity/deadline rejection, which no production
archive test exercises. CPU media tests use newly generated synthetic pixels.
"""
import copy
from fractions import Fraction
import json
from pathlib import Path
import tempfile
import unittest

import av

from tools.demo_renderer.evidence import EvidenceError, load_evidence, sha256
from tools.demo_renderer.__main__ import export
from tools.demo_renderer.sample import sample


class DemoRenderer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.manifest, cls.archive = sample(cls.root/'fixture', frames=8, width=160, height=90)
        cls.source = json.loads(cls.manifest.read_text())
        cls.sidecar = json.loads((cls.archive/'demo-evidence.json').read_text())
        cls.frame_lines = (cls.archive/'frames.jsonl').read_text()

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def tearDown(self):
        self.manifest.write_text(json.dumps(self.source, indent=2)+'\n')
        (self.archive/'frames.jsonl').write_text(self.frame_lines)
        # Tests mutate evidence rather than bypassing any guard with a mock.
        self.save_sidecar(copy.deepcopy(self.sidecar))

    def save_sidecar(self, sidecar):
        sidecar['source_manifest_sha256'] = sha256(self.manifest)
        sidecar['frames_sha256'] = sha256(self.archive/'frames.jsonl')
        (self.archive/'demo-evidence.json').write_text(json.dumps(sidecar))

    def load(self):
        return load_evidence(self.archive, self.manifest, sha256(self.manifest))

    def test_exact_archive_rebase_and_positive_backward_timeline(self):
        evidence = self.load()
        self.assertEqual([r['index'] for r in evidence.timeline], list(range(100, 108)))
        self.assertEqual([r['source_pts'] for r in evidence.timeline], ['20', '81/4', '41/2', '83/4', '21', '85/4', '43/2', '87/4'])
        self.assertEqual([r['index'] for r in evidence.timeline if r['backward_receipt_ids']], [101, 102, 103, 104, 105])
        self.assertEqual(evidence.timeline[1]['capture_seconds'], .25)
        self.assertEqual(evidence.sidecar['detections'][0]['completed_at_monotonic'], 5001.65)

    def test_rejects_unsafe_or_missing_public_source_provenance(self):
        for changes in ({'origin': 'phone'}, {'origin': 'licensed-street-synthetic-labels'},
                        {'demo_ready': False}, {'public_asset_review': {}}):
            with self.subTest(changes=changes):
                source = copy.deepcopy(self.source)
                source.update(changes)
                self.manifest.write_text(json.dumps(source))
                self.save_sidecar(copy.deepcopy(self.sidecar))
                with self.assertRaises(EvidenceError):
                    self.load()

    def test_archive_source_hash_and_identity_mismatch_are_rejected(self):
        with self.assertRaisesRegex(EvidenceError, 'manifest hash mismatch'):
            load_evidence(self.archive, self.manifest, '0'*64)
        for field, value, message in [('source_manifest_sha256', '0'*64, 'Archive/source mismatch'),
                                      ('frames_sha256', '0'*64, 'Archive frame manifest hash mismatch')]:
            sidecar = copy.deepcopy(self.sidecar)
            sidecar[field] = value
            (self.archive/'demo-evidence.json').write_text(json.dumps(sidecar))
            with self.assertRaisesRegex(EvidenceError, message):
                self.load()
        sidecar = copy.deepcopy(self.sidecar)
        sidecar['frames'][0]['index'] = 600
        self.save_sidecar(sidecar)
        with self.assertRaisesRegex(EvidenceError, 'identity mismatch'):
            self.load()

    def test_bad_capture_origin_or_missing_receipts_fail_closed(self):
        mutations = [
            (lambda s: s.update(capture_origin_monotonic=4999), 'Capture origin mismatch'),
            (lambda s: s['frames'][1].update(applied_receipt_ids=[]), 'lacks detector receipt'),
            (lambda s: s.update(detections=[]), 'Missing detector receipt'),
            (lambda s: s['detections'][0].update(completed_at_monotonic=5010), 'misses frame deadline'),
            (lambda s: s.update(execution_mode='real-time'), 'cannot claim real-time'),
        ]
        for mutate, message in mutations:
            with self.subTest(message=message):
                sidecar = copy.deepcopy(self.sidecar)
                mutate(sidecar)
                self.save_sidecar(sidecar)
                with self.assertRaisesRegex(EvidenceError, message):
                    self.load()

    def test_actual_mask_hash_is_required(self):
        rows = [json.loads(line) for line in self.frame_lines.splitlines()]
        rows[1]['mask_sha256'] = '0'*64
        (self.archive/'frames.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
        self.save_sidecar(copy.deepcopy(self.sidecar))
        with self.assertRaisesRegex(EvidenceError, 'Mask hash mismatch'):
            self.load()

    def test_export_is_silent_and_preserves_relative_source_pts(self):
        output = self.root/'comparison.mp4'
        result = export(self.archive, self.manifest, sha256(self.manifest),
                        sha256(self.archive/'demo-evidence.json'), output)
        self.assertEqual(result['evidence_kind'], 'synthetic-test')
        self.assertIsNone(result['native_performance'])
        self.assertEqual(result['frame_count'], 8)
        with av.open(str(output)) as container:
            self.assertEqual(len(container.streams.audio), 0)
            pts = [f.pts*f.time_base for f in container.decode(video=0)]
        self.assertEqual(pts, [Fraction(i, 4) for i in range(8)])
        self.assertTrue(output.with_suffix('.png').is_file())

    def test_decode_identity_failure_never_publishes_partial_output(self):
        sidecar = copy.deepcopy(self.sidecar)
        sidecar['frames'][0]['encoded_pts'] = '1/8'
        self.save_sidecar(sidecar)
        output = self.root/'bad.mp4'
        with self.assertRaisesRegex(EvidenceError, 'Decoded media/archive PTS mismatch'):
            export(self.archive, self.manifest, sha256(self.manifest),
                   sha256(self.archive/'demo-evidence.json'), output)
        self.assertFalse(output.exists())
        self.assertFalse(output.with_suffix('.png').exists())
        self.assertFalse(output.with_suffix('.json').exists())


if __name__ == '__main__':
    unittest.main()

"""Synthetic sealed-file receipts exercise the public cross-host contract."""
import json
from pathlib import Path
import tempfile
import shutil
import unittest
import hashlib
import zipfile
from unittest.mock import patch

import cv2
import numpy as np

from bench.clocked_pipeline import file_sha256, fingerprint
from bench.cross_host import grade, seal_measurement, verify_measurement


class CrossHostMeasurements(unittest.TestCase):
    def measurement(self, directory):
        source, output, truth = [directory / name for name in ('input.mp4', 'output.mp4', 'input.truth.json')]
        source.write_bytes(b'exact synthetic source bytes')
        output.write_bytes(b'exact synthetic encoded bytes')
        truth.write_text('[[], []]\n')
        for suffix in ('.masks.json', '.egress.json'):
            output.with_suffix(suffix).write_text('[]\n')
        output.with_suffix('.mask-pixels.zip').write_bytes(b'exact synthetic packed masks')
        performance = {'pipeline_sha256': fingerprint(), 'candidate': 'unmasked', 'options': {},
                       'source_sha256': file_sha256(source), 'output_sha256': file_sha256(output),
                       'mask_pixels_sha256': file_sha256(output.with_suffix('.mask-pixels.zip'))}
        output.with_suffix('.performance.json').write_text(json.dumps(performance))
        card = {'pipeline_sha256': fingerprint(), 'candidate': 'unmasked', 'options': {},
                'environment': {'platform': 'original-processing-host'}, 'judges': [],
                'clips': [{'clip': 'unit', 'source': str(source), 'output': str(output),
                           'truth': str(truth), 'performance': performance}], 'sustained': None}
        return card, source, output

    def test_seal_binds_embedded_performance_to_exact_source_output_and_raw_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            card, source, output = self.measurement(directory)
            card['clips'][0]['performance']['source_sha256'] = 'a different source'
            with self.assertRaisesRegex(ValueError, 'performance.*source|raw performance'):
                seal_measurement(card, directory)
            self.assertFalse((directory / 'measurement-plan.json').exists())

    def test_verified_bundle_relocates_without_changing_processing_identity_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            card, source, output = self.measurement(directory)
            plan = seal_measurement(card, directory)
            self.assertEqual(plan['card']['environment'], {'platform': 'original-processing-host'})
            self.assertEqual(verify_measurement(directory / 'measurement-plan.json'), plan)
            self.assertEqual(plan['card']['clips'][0]['source'], 'input.mp4')
            with tempfile.TemporaryDirectory() as moved:
                relocated = Path(moved) / 'bundle'
                shutil.copytree(directory, relocated)
                self.assertEqual(verify_measurement(relocated / 'measurement-plan.json'), plan)
            original = source.read_bytes()
            source.write_bytes(b'changed source bytes')
            with self.assertRaisesRegex(ValueError, 'artifact hash mismatch'):
                verify_measurement(directory / 'measurement-plan.json')
            source.write_bytes(original)
            self.assertEqual(verify_measurement(directory / 'measurement-plan.json'), plan)

    def test_seal_rejects_a_sustained_receipt_from_a_different_processing_run(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            card, source, output = self.measurement(directory)
            card['sustained'] = {**card['clips'][0]['performance'], 'source_sha256': 'different sustained source'}
            with self.assertRaisesRegex(ValueError, 'sustained|performance'):
                seal_measurement(card, directory)

    def test_grade_reads_actual_encoded_frames_after_verification_and_preserves_processing_host(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            directory = root / 'out' / 'bundle'
            directory.mkdir(parents=True)
            card, source, output = self.measurement(directory)
            pixels = np.repeat((np.indices((16, 16)).sum(axis=0) % 2 * 180 + 30).astype(np.uint8)[..., None], 3, axis=2)
            for path, count in ((source, 2), (output, 4)):
                writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), 30., (16, 16))
                self.assertTrue(writer.isOpened())
                try:
                    for _ in range(count):
                        writer.write(pixels)
                finally:
                    writer.release()
            mask = np.zeros((16, 16), np.uint8)
            records = [{'frame': i, 'pts': i / 30, 'emitted_at': 11 + i / 30,
                        'mask_shape': [16, 16], 'mask_sha256': hashlib.sha256(mask.tobytes()).hexdigest(),
                        'mask_fraction': 0., 'state': 'LIVE', 'protected': False, 'slate': False,
                        'coverage': {'ok': True, 'reason': 'covered', 'fast_age': 0, 'accurate_age': 0}}
                       for i in range(4)]
            output.with_suffix('.masks.json').write_text(json.dumps(records))
            with zipfile.ZipFile(output.with_suffix('.mask-pixels.zip'), 'w') as archive:
                for i in range(4):
                    archive.writestr(f'{i:08d}.bin', np.packbits(mask > 0, bitorder='little').tobytes())
            performance = card['clips'][0]['performance']
            performance.update(source_sha256=file_sha256(source), output_sha256=file_sha256(output),
                               mask_pixels_sha256=file_sha256(output.with_suffix('.mask-pixels.zip')),
                               options={'delay_seconds': 1.}, frames=4, warmup_frames=2, source_fps=30.,
                               steady={'start_frame': 2, 'stop_frame_exclusive': 4, 'frames': 2, 'source_duration_seconds': 2 / 30},
                               output_wall_rate_fps=30., realtime_added_latency_seconds={'p50': 1., 'p95': 1.},
                               cpu_percent_one_core_100=12., peak_tree_rss_mb=34., clock_origin=10.,
                               encoded_frames=4, source_frames=4, source_duration_seconds=4 / 30,
                               resolution=[16, 16], output_media={'frames': 4, 'fps': 30., 'resolution': [16, 16], 'pts': [i / 30 for i in range(4)]},
                               first_encoded_at=11 + 2 / 30, last_encoded_at=11.1, output_clock_drift_seconds=0.,
                               seconds=1.2, protected_fraction=0., live_frames=2, performance_valid=False,
                               startup={'first_packet_delay_seconds': 1.})
            output.with_suffix('.performance.json').write_text(json.dumps(performance))
            card.update(run_id='bundle', split='tune', pilot=True, manifest_sha256='synthetic-manifest',
                        options={'delay_seconds': 1.}, area_ceiling=None, area_ceiling_basis=None)
            card['clips'][0]['synthetic_variant'] = False
            plan = seal_measurement(card, directory)
            class Reader:
                names = ['synthetic-reader']
                def __init__(self):
                    self.reads = []
                def read(self, frame):
                    self.reads.append(frame.copy())
                    return [{'text': '12 Elm', 'confidence': 1., 'box': [1, 1, 8, 8]}]
            reader = Reader()
            original = source.read_bytes()
            source.write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'artifact hash mismatch'):
                grade(directory / 'measurement-plan.json', judge=reader)
            self.assertEqual(reader.reads, [])
            source.write_bytes(original)
            with patch('bench.clocked_bench.ROOT', root):
                graded = grade(directory / 'measurement-plan.json', judge=reader)
            self.assertEqual(len(reader.reads), 4)
            self.assertTrue(all(frame.shape == (16, 16, 3) and frame.std() > 20 for frame in reader.reads))
            self.assertEqual(graded['natural'], {'hidden': 0, 'total': 1, 'hidden_fraction': 0.})
            self.assertEqual(graded['environment'], {'platform': 'original-processing-host'})
            self.assertEqual(graded['processing_environment'], plan['processing_environment'])
            self.assertIn('platform', graded['grading_environment'])
            self.assertEqual(graded['judges'], ['synthetic-reader'])
            self.assertEqual(len(json.loads(output.with_suffix('.masks.json').read_text())), 4)
            self.assertEqual(graded['clips'][0]['quality_window']['original_start_frame'], 2)


if __name__ == '__main__':
    unittest.main()

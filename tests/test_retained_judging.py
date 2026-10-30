"""Retained scoring must preserve the detector policy and judge generation."""
import hashlib
import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import cv2
import numpy as np

from bench import clocked_bench, rejudge_retained
from bench.cross_host import seal_measurement
from bench.clocked_pipeline import file_sha256, fingerprint
from bench.independence import DEFAULT_FAST_CANDIDATES


class RetainedJudging(unittest.TestCase):
    def test_rejudge_scope_reports_the_schema_of_the_judge_that_read_the_movie(self):
        class Reader:
            names = ['tesseract']
            metadata = {'cache_identity': {'schema_version': 9}}
            closed = False

            def read(self, pixels):
                return [{'text': 'ELM ROAD', 'box': [1, 1, 12, 8],
                         'confidence': .99, 'judge': 'tesseract'}]

            def close(self):
                self.closed = True

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'out/source'
            source.mkdir(parents=True)
            (root / 'fixtures').mkdir()
            clip_ids = ['one', 'two', 'three', 'four', 'five', 'six', 'seven']
            (root / 'fixtures/manifest.json').write_text(json.dumps(
                {'clips': [{'id': name, 'split': 'tune'} for name in clip_ids]}))
            pixels = np.repeat((np.indices((16, 16)).sum(axis=0) % 2 * 180 + 30)
                               .astype(np.uint8)[..., None], 3, axis=2)
            template = root / 'template.mp4'
            writer = cv2.VideoWriter(str(template), cv2.VideoWriter_fourcc(*'mp4v'), 30., (16, 16))
            self.assertTrue(writer.isOpened())
            try:
                for _ in range(4):
                    writer.write(pixels)
            finally:
                writer.release()
            mask = np.zeros((16, 16), np.uint8)
            records = [{'frame': i, 'pts': i / 30, 'emitted_at': 11 + i / 30,
                        'mask_shape': [16, 16], 'mask_sha256': hashlib.sha256(mask.tobytes()).hexdigest(),
                        'mask_fraction': 0., 'state': 'LIVE', 'protected': False, 'slate': False,
                        'coverage': {'ok': True, 'reason': 'covered', 'fast_age': 0, 'accurate_age': 0}}
                       for i in range(4)]
            card = {'candidate': 'unmasked', 'options': {'delay_seconds': 1.},
                    'pipeline_sha256': fingerprint(), 'clips': [], 'sustained': None,
                    'run_id': 'source', 'split': 'tune', 'pilot': True, 'judges': [],
                    'manifest_sha256': 'synthetic-manifest', 'area_ceiling': None,
                    'area_ceiling_basis': None}
            for clip in clip_ids:
                for synthetic in (False, True):
                    label = clip + ('-synthetic' if synthetic else '-natural')
                    before, after = source / (label + '-input.mp4'), source / (label + '-masked.mp4')
                    for path in (before, after):
                        shutil.copyfile(template, path)
                    truth = source / (label + '-input.truth.json')
                    truth.write_text('[[], []]')
                    after.with_suffix('.masks.json').write_text(json.dumps(records))
                    after.with_suffix('.egress.json').write_text('[]')
                    with zipfile.ZipFile(after.with_suffix('.mask-pixels.zip'), 'w') as archive:
                        for i in range(4):
                            archive.writestr(f'{i:08d}.bin', np.packbits(mask > 0, bitorder='little').tobytes())
                    performance = {'candidate': 'unmasked', 'options': card['options'],
                        'pipeline_sha256': card['pipeline_sha256'], 'source_sha256': file_sha256(before),
                        'output_sha256': file_sha256(after),
                        'mask_pixels_sha256': file_sha256(after.with_suffix('.mask-pixels.zip')),
                        'frames': 4, 'warmup_frames': 2, 'source_fps': 30.,
                        'steady': {'start_frame': 2, 'stop_frame_exclusive': 4, 'frames': 2,
                                   'source_duration_seconds': 2 / 30},
                        'output_wall_rate_fps': 30., 'realtime_added_latency_seconds': {'p50': 1., 'p95': 1.},
                        'cpu_percent_one_core_100': 12., 'peak_tree_rss_mb': 34., 'clock_origin': 10.,
                        'encoded_frames': 4, 'source_frames': 4, 'source_duration_seconds': 4 / 30,
                        'resolution': [16, 16], 'output_media': {'frames': 4, 'fps': 30.,
                            'resolution': [16, 16], 'pts': [i / 30 for i in range(4)]},
                        'first_encoded_at': 11 + 2 / 30, 'last_encoded_at': 11.1,
                        'output_clock_drift_seconds': 0., 'seconds': 1.2, 'protected_fraction': 0.,
                        'live_frames': 2, 'performance_valid': False, 'startup': {'first_packet_delay_seconds': 1.}}
                    after.with_suffix('.performance.json').write_text(json.dumps(performance))
                    card['clips'].append({'clip': clip, 'synthetic_variant': synthetic,
                        'source': str(before), 'output': str(after), 'truth': str(truth), 'performance': performance})
            (source / 'scorecard.json').write_text(json.dumps(card))
            reader = Reader()
            with contextlib.redirect_stdout(io.StringIO()):
                seal_measurement(card, source)
                with patch.object(rejudge_retained, 'ROOT', root), patch.object(clocked_bench, 'ROOT', root), \
                     patch('bench.judges.Judges', return_value=reader), \
                     patch.object(sys, 'argv', ['rejudge', '--source-run', 'source', '--run-id', 'fresh']):
                    rejudge_retained.main()
            result = json.loads((root / 'out/fresh/scorecard.json').read_text())
            self.assertEqual(result['judging']['cache_identity']['schema_version'], 9)
            self.assertIn('cache-v9', result['rejudge']['scope'])
            self.assertNotIn('cache-v2', result['rejudge']['scope'])
            self.assertTrue(reader.closed)

    def test_recorded_fast_lane_cannot_be_replaced_by_a_later_default(self):
        class Reader:
            calls = 0

            def read(self, pixels):
                self.calls += 1
                return [{'text': 'ELM ROAD', 'box': [1, 1, 12, 8],
                         'confidence': .99, 'judge': 'ppocr-independent'}]

        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            source, output = directory / 'input.mp4', directory / 'output.mp4'
            pixels = np.repeat((np.indices((16, 16)).sum(axis=0) % 2 * 180 + 30)
                               .astype(np.uint8)[..., None], 3, axis=2)
            for path, count in ((source, 2), (output, 4)):
                writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), 30., (16, 16))
                self.assertTrue(writer.isOpened())
                try:
                    for _ in range(count):
                        writer.write(pixels)
                finally:
                    writer.release()
            mask = np.zeros((16, 16), np.uint8)
            records = [{'frame': i, 'pts': i / 30, 'mask_shape': [16, 16],
                        'mask_sha256': hashlib.sha256(mask.tobytes()).hexdigest(),
                        'mask_fraction': 0., 'state': 'LIVE', 'protected': False, 'slate': False}
                       for i in range(4)]
            output.with_suffix('.masks.json').write_text(json.dumps(records))
            with zipfile.ZipFile(output.with_suffix('.mask-pixels.zip'), 'w') as archive:
                for i in range(4):
                    archive.writestr(f'{i:08d}.bin', np.packbits(mask > 0, bitorder='little').tobytes())
            performance = {'candidate': 'vision-accurate', 'options': {}, 'frames': 4,
                           'warmup_frames': 2, 'source_fps': 30.,
                           'steady': {'frames': 2, 'start_frame': 2},
                           'loading': {
                               'accurate': {'candidate': 'vision-accurate',
                                            'metadata': {'detector_families': ['apple-vision']}},
                               'fast': {'candidate': 'ppocr-v6-tiny',
                                        'metadata': {'detector_families': ['paddleocr']}}}}
            receipt = output.with_suffix('.performance.json')
            receipt.write_text(json.dumps(performance))
            reader = Reader()
            # The current default has returned to Vision after this mixed run.
            with patch.dict(DEFAULT_FAST_CANDIDATES, {'vision-accurate': 'vision-rectangles'}):
                with self.assertRaisesRegex(ValueError, 'recorded.*fast|fast.*recorded'):
                    clocked_bench.score_video(source, output, reader, [[], []])
            self.assertEqual(reader.calls, 0, 'A conflicting retained policy must fail before OCR')
            with patch.dict(DEFAULT_FAST_CANDIDATES, {'vision-accurate': 'ppocr-v6-tiny'}):
                scored = clocked_bench.score_video(source, output, reader, [[], []])
            self.assertEqual(reader.calls, 4)
            self.assertEqual(scored['natural']['total'], 0)
            self.assertEqual(scored['judge_independence']['truth_judges'], ['tesseract'])
            # Early retained runs recorded model keys before family metadata
            # existed. Their registered model keys still identify both lanes.
            for lane in performance['loading'].values():
                lane['metadata'].pop('detector_families')
            receipt.write_text(json.dumps(performance))
            with patch.dict(DEFAULT_FAST_CANDIDATES, {'vision-accurate': 'ppocr-v6-tiny'}):
                legacy = clocked_bench.score_video(source, output, reader, [[], []])
            self.assertEqual(legacy['judge_independence']['truth_judges'], ['tesseract'])
            self.assertEqual(reader.calls, 8)
            for damaged in ({}, {'accurate': performance['loading']['accurate']}):
                with self.subTest(loading=damaged):
                    receipt.write_text(json.dumps({**performance, 'loading': damaged}))
                    with self.assertRaisesRegex(ValueError, 'recorded.*fast|fast.*recorded'):
                        clocked_bench.score_video(source, output, reader, [[], []])
                    self.assertEqual(reader.calls, 8)


if __name__ == '__main__':
    unittest.main()

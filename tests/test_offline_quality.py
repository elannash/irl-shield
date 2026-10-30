"""Source-clock contracts for ideal/offline quality; synthetic pixels only."""
import unittest
from unittest.mock import patch
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile

import numpy as np

from bench.offline_quality import build_scorecard, render_offline, run_file


class Stationary:
    def __init__(self):
        self.indices = []

    def add(self, index, pixels):
        self.indices.append(index)

    def project_many(self, quads, source, target, deadline=None):
        return quads

    def diagnostics(self, index):
        return {'valid': True, 'confidence': 1., 'burst': False, 'reason': 'synthetic-stationary'}


class IndexedBoxes:
    def __init__(self):
        self.indices = []

    def detect(self, pixels):
        index = int(pixels[0, 0, 0])
        self.indices.append(index)
        x = 8 + index * 7
        return [[x, 12, x + 2, 18]]


class OfflineSampling(unittest.TestCase):
    def test_legacy_composite_is_rejected_before_offline_media_work(self):
        for candidate,options in [('vision-scheduled',{}),('vision-union',{'fast_candidate':'vision-scheduled'})]:
            with self.subTest(candidate=candidate,options=options),self.assertRaisesRegex(ValueError,'legacy'):
                run_file(Path('/nonexistent-irl-shield-source.mp4'),
                         Path('/nonexistent-irl-shield-output.mp4'),candidate,options)

    def test_fixed_source_schedule_has_future_receipts_before_first_presentation(self):
        frames = []
        for index in range(10):
            pixels = np.full((48, 96, 3), 100, np.uint8)
            pixels[0, 0, 0] = index
            frames.append(pixels)
        backends = {name: IndexedBoxes() for name in ('fast', 'accurate')}
        motion = Stationary()
        presented = []
        first_known = []

        def emit(frame):
            if not presented:
                first_known.extend(motion.indices)
            presented.append(frame)

        result = render_offline(iter(frames), 10., backends,
                                {'delay_seconds': .5, 'before': 6, 'after': 5,
                                 'fast_rate_hz': 4., 'accurate_rate_hz': 2., 'padding': 0},
                                emit, motion=motion)
        self.assertEqual([frame.index for frame in presented], list(range(10)))
        self.assertEqual(backends['fast'].indices, [0, 3, 5, 8])
        self.assertEqual(backends['accurate'].indices, [0, 5])
        self.assertEqual(first_known, [0, 1, 2, 3, 4, 5])
        self.assertEqual(presented[0].mask[15, 44], 255)
        self.assertEqual(presented[0].mask[15, 65], 0)
        self.assertTrue(all(frame.state == 'LIVE' for frame in presented))
        self.assertEqual(result['engine']['late_ingest'], 0)
        self.assertEqual(result['engine']['buffer_evictions'], 0)

    def test_scaled_receipts_keep_source_time_when_host_clock_stalls(self):
        host = [500.]

        class RelativeQuad:
            def detect_quads(self, pixels):
                host[0] += 1000.
                height, width = pixels.shape[:2]
                return [[[width / 2, height / 4], [3 * width / 4, height / 4],
                         [3 * width / 4, height / 2], [width / 2, height / 2]]]

        frames = [np.full((48, 96, 3), 100, np.uint8) for _ in range(3)]
        presented = []
        with patch('time.monotonic', side_effect=lambda: host[0]):
            result = render_offline(frames, 10., {name: RelativeQuad() for name in ('fast', 'accurate')},
                                    {'delay_seconds': .1, 'fast_rate_hz': 5., 'accurate_rate_hz': 2.,
                                     'fast_width': 48, 'accurate_width': 96}, presented.append,
                                    motion=Stationary())
        expected = [[48, 12], [72, 12], [72, 24], [48, 24]]
        np.testing.assert_allclose(result['detections']['fast'][0]['quads'][0], expected)
        self.assertEqual([r['source_index'] for r in result['detections']['fast']], [0, 2])
        self.assertEqual([r['completed_at'] for r in result['detections']['fast']], [0., .2])
        self.assertEqual(result.get('mode'), 'offline_quality')
        self.assertIs(result['real_time_verified'], False)
        self.assertIs(result['gate_1']['pass'], False)
        self.assertEqual(result['engine']['late_ingest'], 0)
        self.assertTrue(all(frame.state == 'LIVE' for frame in presented))

    def test_file_adapter_scores_encoded_pixels_with_saved_actual_raster_masks(self):
        class Box:
            def detect(self, pixels):
                return [[20, 12, 26, 18]]

        class PixelJudge:
            names = ['synthetic-pixel-judge']

            def read(self, pixels):
                return [{'text': '1234', 'confidence': 1., 'box': [20, 12, 26, 18]}] if pixels[15, 23].mean() > 180 else []

        yy, xx = np.indices((48, 96))
        pixels = np.repeat((80 + ((xx // 4 + yy // 4) % 2) * 50).astype(np.uint8)[..., None], 3, axis=2)
        pixels[12:19, 20:27] = 240
        with tempfile.TemporaryDirectory() as temporary:
            source, output = Path(temporary) / 'input.mp4', Path(temporary) / 'output.mp4'
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'rawvideo',
                            '-pix_fmt', 'bgr24', '-s', '96x48', '-r', '10', '-i', 'pipe:0', '-an',
                            '-c:v', 'libx264', '-preset', 'ultrafast', '-threads', '2', '-bf', '0',
                            '-pix_fmt', 'yuv420p', str(source)], input=pixels.tobytes() * 4, check=True, timeout=20)
            result = run_file(source, output, 'synthetic',
                              {'encoder': 'libx264', 'detector_families': [], 'fast_rate_hz': 10., 'accurate_rate_hz': 10.,
                               'delay_seconds': .2, 'padding': 0},
                              judge=PixelJudge(), backends={name: Box() for name in ('fast', 'accurate')})
            self.assertTrue(output.is_file())
            self.assertEqual(result['frames'], 4)
            self.assertEqual(result['natural']['hidden'], 1)
            self.assertEqual(result['natural']['total'], 1)
            self.assertTrue(result['real_video_pass'])
            self.assertEqual(result['protected_fraction'], 0.)
            records = json.loads(output.with_suffix('.masks.json').read_text())
            self.assertEqual([r['frame'] for r in records], [0, 1, 2, 3])
            with zipfile.ZipFile(output.with_suffix('.mask-pixels.zip')) as archive:
                self.assertEqual(len(archive.namelist()), 4)
                packed = np.frombuffer(archive.read('00000000.bin'), np.uint8)
                mask = np.unpackbits(packed, bitorder='little', count=48 * 96).reshape(48, 96) * 255
            self.assertEqual(mask[15, 23], 255)
            self.assertEqual(mask[0, 95], 0)
            self.assertEqual(hashlib.sha256(mask.tobytes()).hexdigest(), records[0]['mask_sha256'])
            self.assertFalse(result['gate_1']['pass'])

    def test_corpus_uses_interval_weights_and_rejects_a_protected_frame_win(self):
        with tempfile.TemporaryDirectory() as temporary:
            results = []
            for label, rows, hidden, total in (
                    ('a', [(False, .1), (False, .1), (False, .2), (False, .2)], 1, 2),
                    ('b', [(False, .15)] + [(True, 1.)] * 5, 8, 8)):
                output = Path(temporary) / f'{label}.mp4'
                records = [{'frame': i, 'state': 'PROTECT' if protected else 'LIVE',
                            'protected': protected, 'slate': protected, 'mask_fraction': fraction}
                           for i, (protected, fraction) in enumerate(rows)]
                output.with_suffix('.masks.json').write_text(json.dumps(records))
                results.append({'output': str(output), 'frames': len(rows), 'synthetic_variant': True,
                                'natural': {'hidden': hidden, 'total': total, 'hidden_fraction': hidden / total},
                                'synthetic': {'hidden': 1, 'total': 1, 'hidden_fraction': 1.},
                                'synthetic_input_control': {'total': 1, 'unreadable': 0},
                                'real_video_pass': True})
            card = build_scorecard(results, 'unmasked', {}, run_id='synthetic-offline',
                                   baseline={'natural': {'hidden_fraction': .8},
                                             'synthetic': {'hidden_fraction': 1.}})
            self.assertEqual(card.get('natural'), {'hidden': 9, 'total': 10, 'hidden_fraction': .9})
            self.assertEqual(card['synthetic']['hidden'], 2)
            self.assertEqual(card['protected_fraction'], .5)
            self.assertAlmostEqual(card['masked_area_fraction']['p50'], .6)
            self.assertAlmostEqual(card['live_masked_area_fraction']['p50'], .15)
            self.assertFalse(card['quality_checks']['protected'])
            self.assertFalse(card['comparison_valid'])
            self.assertFalse(card['gate_1']['eligible'])
            self.assertFalse(card['gate_1']['pass'])
            self.assertFalse(card['real_time_verified'])
            self.assertTrue(card['benchmark_only'])
            self.assertFalse(card['demo_ready'])
            self.assertAlmostEqual(card['baseline_deltas_pp']['natural'], 10.)
            self.assertNotIn('minimum_clip_fps', card)
            self.assertNotIn('latency_seconds', card)

        for control in ('unmasked', 'slate'):
            with self.subTest(control=control):
                pixels = np.full((32, 48, 3), 100, np.uint8)
                presented = []
                result = render_offline([pixels] * 3, 10.,
                                        {name: IndexedBoxes() for name in ('fast', 'accurate')},
                                        {'control': control}, presented.append)
                self.assertEqual(len(result['detections']['fast']), 3)
                self.assertEqual(len(result['detections']['accurate']), 3)
                if control == 'unmasked':
                    self.assertTrue(all(np.array_equal(frame.pixels, pixels) for frame in presented))
                    self.assertTrue(all(not frame.mask.any() and not frame.protected for frame in presented))
                else:
                    self.assertTrue(all(not frame.pixels.any() and np.all(frame.mask == 255) for frame in presented))
                    self.assertTrue(all(frame.protected and frame.slate for frame in presented))

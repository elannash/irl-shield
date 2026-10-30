"""Native evidence contracts without a native E2E run or edits to old media."""
import hashlib
import json
from fractions import Fraction
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import av
import numpy as np

from native import capture_alignment, decode, live_share


class HoldWitness(unittest.TestCase):
    def test_one_subframe_startup_step_is_reported_without_excluding_its_pixels(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = []
            with av.open(str(root / 'network.mkv'), 'w', format='matroska') as output:
                stream = output.add_stream('ffv1', rate=30)
                stream.width, stream.height, stream.pix_fmt = 64, 32, 'bgr0'
                stream.time_base = stream.codec_context.time_base = Fraction(1, 1000)
                for index, pts in enumerate((0, 47, 80, 113)):
                    pixels = np.full((32, 64, 3), index * 30, np.uint8)
                    frame = av.VideoFrame.from_ndarray(pixels, format='bgr24')
                    frame.pts, frame.time_base = pts, Fraction(1, 1000)
                    for packet in stream.encode(frame):
                        output.mux(packet)
                    archive.append({'pixels_sha256': hashlib.sha256(pixels.tobytes()).hexdigest(),
                                    'black': index == 0, 'egress_generation': 1, 'engine_index': index})
                for packet in stream.encode():
                    output.mux(packet)
            manifest = [{'index': index, 'pts': 2 + index / 30, 'egress_generation': 1,
                         'encoded_at_monotonic': 10 + index / 30, 'state': 'HOLD'}
                        for index in range(4)]
            # Alignment is separate from the label proxy, whose fixtures are
            # 720p. Every decoded frame, including the startup frame, is checked.
            checked = []
            with patch('native.label_edges', side_effect=lambda pixels: checked.append(pixels.copy()) or 0):
                result = decode(root, [], manifest, archive)
            self.assertEqual(len(checked), 4)
            self.assertTrue(result['exact_pixel_suffix_match'])
            startup = result['startup_alignment']
            self.assertEqual(startup['excluded_leading_frames'], 1)
            self.assertEqual(startup['capture_index'], 0)
            self.assertAlmostEqual(startup['error_seconds'], -.013666666666666667)
            self.assertAlmostEqual(startup['step_to_next_seconds'], .047)
            self.assertLessEqual(result['steady_alignment']['max_absolute_error_seconds'], .002)

    def test_subframe_pulse_uses_first_frame_after_begin_even_after_end(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pixels = np.zeros((32, 64, 3), np.uint8)
            with av.open(str(root / 'network.mkv'), 'w', format='matroska') as output:
                stream = output.add_stream('ffv1', rate=30)
                stream.width, stream.height, stream.pix_fmt = 64, 32, 'bgr0'
                for index in range(2):
                    frame = av.VideoFrame.from_ndarray(pixels, format='bgr24')
                    frame.pts = index
                    for packet in stream.encode(frame):
                        output.mux(packet)
                for packet in stream.encode():
                    output.mux(packet)
            manifest = [
                {'index': 240, 'pts': 0., 'egress_generation': 1,
                 'encoded_at_monotonic': 1.0, 'state': 'HOLD'},
                {'index': 241, 'pts': 1 / 30, 'egress_generation': 2,
                 'encoded_at_monotonic': 1.02, 'state': 'HOLD'},
            ]
            archive = [{'pixels_sha256': hashlib.sha256(pixels.tobytes()).hexdigest(),
                        'black': True, 'egress_generation': row['egress_generation'],
                        'engine_index': row['index']} for row in manifest]
            actions = [{'at': 1.005, 'active': True, 'source': 'shield_mode'},
                       {'at': 1.015, 'active': False, 'source': 'shield_mode'}]
            with patch('native.label_edges', return_value=0):
                result = decode(root, actions, manifest, archive)
            self.assertTrue(result['holds'][0]['pass_'], result['holds'])
            self.assertEqual(result['holds'][0]['first_frame_identity'], [2, 241])

    def test_live_share_counts_automatic_protection_and_excludes_only_scripted_holds(self):
        rows = [{'encoded_at_monotonic': i, 'state': state} for i, state in enumerate(
                ['LIVE', 'PROTECT', 'HOLD', 'LIVE', 'HOLD'])]
        actions = [{'at': 2.5, 'active': True, 'source': 'chat'},
                   {'at': 3.5, 'active': False, 'source': 'chat'},
                   {'at': 0., 'active': True, 'source': 'twitch-connection'}]
        report = live_share(rows, actions)
        self.assertEqual(report['denominator'], 4)
        self.assertEqual(report['live'], 1)
        self.assertFalse(report['pass'])
        rows[1]['state'] = 'LIVE'
        self.assertTrue(live_share(rows, actions)['pass'])


class CaptureAlignment(unittest.TestCase):
    def timeline(self):
        manifest = [{'index': i, 'pts': i / 30, 'egress_generation': 1} for i in range(8)]
        rows = [{'pts': 10 + frame['pts']} for frame in manifest]
        return rows, manifest

    def test_b508_real_rows_pass_only_the_new_startup_rule(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/b508-capture-alignment.json').read_text())
        rows = [{'pts': pts} for pts in fixture['capture_pts']]
        manifest = fixture['matched_manifest']
        old_origin = rows[0]['pts'] - manifest[0]['pts']
        old_errors = [abs(row['pts'] - old_origin - frame['pts']) for row, frame in zip(rows, manifest)]
        self.assertEqual(sum(error > .002 for error in old_errors), 868)
        self.assertEqual(fixture['raw_verdict'], 'FAILED')
        result = capture_alignment(rows, manifest)
        startup = result['startup_alignment']
        self.assertEqual(startup['excluded_leading_frames'], 1)
        self.assertEqual(startup['manifest_identity'], [1, 68])
        self.assertAlmostEqual(startup['error_seconds'], -.013666666666666667)
        self.assertAlmostEqual(startup['step_to_next_seconds'], .047)
        self.assertLessEqual(result['steady_alignment']['max_absolute_error_seconds'], .002)
        self.assertLessEqual(result['steady_alignment']['max_interval_error_seconds'], .002)

    def test_midstream_step_two_bad_startup_frames_and_large_first_error_fail(self):
        for failure in ('midstream', 'two-startup', 'large-first'):
            with self.subTest(failure=failure):
                rows, manifest = self.timeline()
                if failure == 'midstream':
                    for row in rows[3:]:
                        row['pts'] += .013
                elif failure == 'two-startup':
                    for row in rows[:2]:
                        row['pts'] -= .013
                else:
                    rows[0]['pts'] -= .040
                with self.assertRaises(RuntimeError):
                    capture_alignment(rows, manifest)

    def test_interval_jitter_fails_even_inside_absolute_tolerance(self):
        rows, manifest = self.timeline()
        rows[3]['pts'] += .0015
        rows[4]['pts'] -= .0015
        with self.assertRaisesRegex(RuntimeError, 'intervals'):
            capture_alignment(rows, manifest)

    def test_exact_frame_startup_error_is_rejected_despite_float_rounding(self):
        rows, manifest = self.timeline()
        rows[0]['pts'] = rows[1]['pts']
        with self.assertRaisesRegex(RuntimeError, 'one frame period'):
            capture_alignment(rows, manifest)

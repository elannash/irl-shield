"""Native evidence contracts without a native E2E run or edits to old media."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import av
import numpy as np

from native import decode, live_share


class HoldWitness(unittest.TestCase):
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

"""Untimed RTSP startup data needs exact content identity, never a guessed PTS."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import unittest

from bench.keyframe_probe import assess, packet_row


class KeyframeIdentity(unittest.TestCase):
    def test_untimed_packet_keeps_vcl_payload_and_slice_boundaries(self):
        payload = b'\x00\x00\x00\x01\x65\x80\x00\x00\x01\x65\x81'
        class Packet:
            pts = None
            time_base = Fraction(1, 90000)
            size = len(payload)
            def __bytes__(self):
                return payload
        row = packet_row(Packet(), 'annexb')
        self.assertIsNone(row['pts'])
        self.assertEqual(row['vcl_slices'], 2)
        self.assertEqual(row['vcl_bytes'], 4)
        self.assertEqual(row['vcl_sha256'], hashlib.sha256(
            b'\x00\x00\x00\x02\x65\x80\x00\x00\x00\x02\x65\x81').hexdigest())

    def sample(self):
        source = [
            {'index': 0, 'pts': '0', 'idr': True, 'vcl_sha256': '01' * 32,
             'pixels': {'full': '10' * 32, 'lower': '11' * 32}},
            {'index': 1, 'pts': '1/30', 'idr': True, 'vcl_sha256': '02' * 32,
             'pixels': {'full': '20' * 32, 'lower': '21' * 32}},
            {'index': 2, 'pts': '1/15', 'idr': True, 'vcl_sha256': '03' * 32,
             'pixels': {'full': '30' * 32, 'lower': '31' * 32}},
            {'index': 3, 'pts': '1/10', 'idr': True, 'vcl_sha256': '04' * 32,
             'pixels': {'full': '40' * 32, 'lower': '41' * 32}},
        ]
        packets = [{'pts': None, 'vcl_sha256': '01' * 32},
                   {'pts': '71/30', 'vcl_sha256': '02' * 32},
                   {'pts': '12/5', 'vcl_sha256': '03' * 32},
                   {'pts': '73/30', 'vcl_sha256': '04' * 32}]
        frames = [{'pts': packet['pts'], 'pixels': deepcopy(item['pixels'])}
                  for packet, item in zip(packets, source)]
        return source, {'packets': packets, 'frames': frames, 'errors': []}

    def test_untimed_startup_is_identified_by_unique_complete_content(self):
        source, received = self.sample()
        result = assess(source, received)
        self.assertEqual(result['failures'], [])
        self.assertEqual(result['clock_offset'], '7/3')
        self.assertEqual(result['unique_intact_vcl_anchors'], 3)
        self.assertEqual([row['source_index'] for row in result['associated']], [0, 1, 2, 3])
        self.assertIsNone(result['associated'][0]['received_pts'])
        self.assertEqual(result['associated'][0]['association'], 'unique-complete-vcl')

    def test_unmatched_untimed_data_is_unknown_and_cannot_pass(self):
        source, received = self.sample()
        received['packets'][0]['vcl_sha256'] = 'ff' * 32
        received['frames'][0]['pixels']['full'] = 'ff' * 32
        result = assess(source, received)
        self.assertIn('rtsp-packet-unassociated', result['failures'])
        self.assertIn('rtsp-frame-unassociated', result['failures'])
        self.assertEqual([row['source_index'] for row in result['associated']], [1, 2, 3])

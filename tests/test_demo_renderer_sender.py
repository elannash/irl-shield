"""Sender destination guard only. Actual RTMP transport is a root EX packet."""
import unittest
import json
from pathlib import Path
import tempfile
from unittest.mock import Mock

from relay.security import Credentials, RelayAddress
from tools.demo_renderer.sender import Sender, endpoint
from tools.demo_renderer.rehearsal import check_archive


class EndpointBoundary(unittest.TestCase):
    def test_sender_poll_checks_complete_receipt_once_and_rejects_truncated_publication(self):
        with tempfile.TemporaryDirectory() as name:
            receipt = Path(name) / 'sender.jsonl'
            sender = Sender.__new__(Sender)
            sender.process = Mock(exitcode=0)
            sender.receipt = receipt
            sender._complete_checked = False
            receipt.write_text(json.dumps({'kind': 'sender-end', 'complete': False}))
            with self.assertRaisesRegex(RuntimeError, 'before the complete'):
                sender.check()
            receipt.write_text(json.dumps({'kind': 'sender-end', 'complete': True}))
            sender.check()
            receipt.unlink()
            # Once terminal success is checked, loop polling does no disk read.
            sender.check()
            sender.process.exitcode = 2
            with self.assertRaisesRegex(RuntimeError, 'sender failed'):
                sender.check()

    def test_missing_rehearsal_archive_cannot_be_accepted(self):
        with tempfile.TemporaryDirectory() as name:
            with self.assertRaisesRegex(RuntimeError, 'archive missing'):
                check_archive(Path(name) / 'archive', Path(name) / 'sender.jsonl')

    def test_observed_denominator_includes_startup_gaps_and_post_publisher_outputs(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            sender = root / 'sender.jsonl'
            sender.write_text(json.dumps({'kind': 'sender-end', 'complete': True,
                'packets': 6300, 'finished_at_monotonic': 10}))
            (root / 'encoded.flv').write_bytes(b'synthetic-not-native-media')
            runtime = {'status': 'stopped', 'cleanup_errors': [], 'verified_tls': None, 'output_frames': 3}
            (root / 'runtime.json').write_text(json.dumps(runtime))
            frames = [
                {'index': 0, 'egress_generation': 1, 'state': 'HOLD', 'slate': True, 'protected': True,
                 'coverage': {'reason': 'startup'}, 'encoded_at_monotonic': 1},
                {'index': 1, 'egress_generation': 1, 'state': 'PROTECT', 'slate': True, 'protected': True,
                 'coverage': {'reason': 'ingest-gap'}, 'encoded_at_monotonic': 11},
                {'index': 3, 'egress_generation': 1, 'state': 'LIVE', 'slate': False, 'protected': False,
                 'coverage': {'reason': 'covered'}, 'encoded_at_monotonic': 12}]
            (root / 'frames.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in frames))
            report = check_archive(root, sender)
            self.assertEqual(report['archived_outputs'], 3)
            self.assertEqual(report['live_non_slate_outputs'], 1)
            self.assertEqual(report['startup_engine_zero_outputs'], 1)
            self.assertEqual(report['explicit_ingest_gap_outputs'], 1)
            self.assertEqual(report['encoded_after_publisher_finished'], 2)
            self.assertEqual(report['observed_engine_index_window'], [0, 4])
            self.assertEqual(report['unarchived_engine_slots_within_window'], 1)
            self.assertIsNone(report['source_identity'])
            self.assertIsNone(report['native_packet_projection_proof'])
            self.assertEqual(report['status'], 'NOT CLEARED')
            runtime['output_frames'] = 4
            (root / 'runtime.json').write_text(json.dumps(runtime))
            with self.assertRaisesRegex(RuntimeError, 'incomplete'):
                check_archive(root, sender)

    def test_exact_loopback_camera_endpoint_uses_runtime_phone_credentials(self):
        phone = Credentials('synthetic-user', 'SYNTHETIC-PASSWORD')
        self.assertEqual(endpoint(RelayAddress('127.0.0.1'), phone, local_only=True),
            'rtmp://127.0.0.1:19350/camera?user=synthetic-user&pass=SYNTHETIC-PASSWORD')
        for host in ('100.100.100.100', '127.0.0.2'):
            with self.subTest(host=host), self.assertRaisesRegex(ValueError, 'exact loopback'):
                endpoint(RelayAddress(host), phone, local_only=True)


if __name__ == '__main__':
    unittest.main()

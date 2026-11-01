"""Sender boundaries and real worker lifecycle; RTMP remains a root EX packet."""
import fcntl
import multiprocessing
import os
import runpy
import signal
import unittest
import json
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch

from relay.security import Credentials, RelayAddress
from tools.demo_renderer.sender import Sender, endpoint
from tools.demo_renderer.rehearsal import check_archive


def _fake_transport_worker(target, lease, manifest, url, stopped, receipt, ready):
    """Replace transport in the real worker with a condition-controlled source."""
    import tools.demo_renderer.sender as sender_module
    def fake_source(manifest_path, private_url, stop_event, receipt_path):
        config = json.loads(Path(manifest_path).read_text())
        fd = int(os.environ[sender_module.LEASE_ENV])
        launcher = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/walk-linux'))
        launcher['verified_fd'](fd, Path(config['lock']))
        identity = os.fstat(fd)
        if config['stubborn']:
            def retain_terminate(signum, frame):
                with Path(receipt_path).open('a') as output:
                    output.write(json.dumps({'kind': 'fake-source-SIGTERM', 'signal': signum}) + '\n')
            signal.signal(signal.SIGTERM, retain_terminate)
        with Path(receipt_path).open('x') as output:
            output.write(json.dumps({'kind': 'fake-source-start', 'pid': os.getpid(),
                'device': identity.st_dev, 'inode': identity.st_ino}) + '\n')
            output.flush()
            ready.set()
            if config['stubborn']:
                while True:
                    signal.pause()
            if not stop_event.wait(10):
                raise TimeoutError('Synthetic source was not stopped')
            output.write(json.dumps({'kind': 'sender-end', 'complete': True}) + '\n')
    sender_module._send = fake_source
    target(lease, manifest, url, stopped, receipt)


class EndpointBoundary(unittest.TestCase):
    def test_real_sender_hands_off_lease_and_reaps_cooperative_or_stubborn_worker(self):
        context = multiprocessing.get_context('spawn')
        phone = Credentials('synthetic-user', 'SYNTHETIC-PASSWORD')
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            for stubborn in (False, True):
                with self.subTest(stubborn=stubborn):
                    directory = root / str(stubborn)
                    directory.mkdir()
                    lock = directory / 'perf.lock'
                    source = directory / 'fake-source.json'
                    source.write_text(json.dumps({'lock': str(lock), 'stubborn': stubborn}))
                    receipt = directory / 'sender.jsonl'
                    ready = context.Event()
                    class InputContext:
                        def Event(self):
                            return context.Event()
                        def Process(self, *, target, args, name):
                            return context.Process(target=_fake_transport_worker,
                                args=(target, *args, ready), name=name)
                    lease = lock.open('a+')
                    sender = None
                    try:
                        fcntl.flock(lease, fcntl.LOCK_EX)
                        identity = os.fstat(lease.fileno())
                        with patch('tools.demo_renderer.sender.inherited_exclusive', return_value=lease.fileno()), \
                                patch('tools.demo_renderer.sender.multiprocessing.get_context', return_value=InputContext()):
                            sender = Sender(source, RelayAddress('127.0.0.1'), phone, receipt)
                        sender.__enter__()
                        self.assertTrue(ready.wait(5), 'Source did not verify its inherited lease')
                        start = json.loads(receipt.read_text().splitlines()[0])
                        self.assertEqual(start['pid'], sender.process.pid)
                        self.assertEqual((start['device'], start['inode']), (identity.st_dev, identity.st_ino))
                        lease.close()
                        with lock.open('a+') as contender:
                            with self.assertRaises(BlockingIOError):
                                fcntl.flock(contender, fcntl.LOCK_SH | fcntl.LOCK_NB)
                        if stubborn:
                            with self.assertRaisesRegex(RuntimeError, 'sender failed|forced cleanup'):
                                sender.__exit__(None, None, None)
                            self.assertEqual(sender.process.exitcode, -signal.SIGKILL)
                            records = [json.loads(line) for line in receipt.read_text().splitlines()]
                            self.assertEqual([row['signal'] for row in records if row['kind'] == 'fake-source-SIGTERM'],
                                             [signal.SIGTERM])
                        else:
                            sender.__exit__(None, None, None)
                            self.assertEqual(sender.process.exitcode, 0)
                            self.assertTrue(json.loads(receipt.read_text().splitlines()[-1])['complete'])
                        self.assertTrue(sender.stopped.is_set())
                        self.assertFalse(sender.process.is_alive())
                        with lock.open('a+') as contender:
                            fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    finally:
                        if sender is not None and sender.process.pid is not None:
                            if sender.process.is_alive():
                                sender.process.kill()
                            sender.process.join(5)
                        lease.close()

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

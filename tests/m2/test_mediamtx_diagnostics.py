"""MediaMTX's process boundary retains fixed warning codes, never raw logs."""
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from relay.mediamtx import MediaMTX
from relay.security import Credentials, RelayAddress


class Process:
    pid = 123

    def __init__(self, logs, *, failed=False):
        self.stdin = BytesIO()
        self.stdout = BytesIO(logs)
        self.returncode = 1 if failed else None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = 0

    def wait(self, timeout):
        return self.returncode


class MediaMTXDiagnostics(unittest.TestCase):
    def test_warning_receipt_survives_shutdown_without_raw_credentials(self):
        secret = 'SYNTHETIC-PRIVATE-PASSWORD'
        logs = (b"[RTSP] [session abc] is reading from path 'camera'\n" +
                (b"WAR [RTSP] [session abc] reader is too slow, discarding 70 frames " +
                 secret.encode() + b" rtmp://private.invalid/camera\n") * 70 +
                b"WAR [RTMP] [conn def] write queue is full\n" +
                b"WAR unknown upstream warning " + secret.encode() + b"\n" +
                b"2026/11/01 01:00:00 WAR prefixed upstream warning " + secret.encode() + b"\n" +
                b"[RTSP] [session abc] closed: EOF\n")
        address = RelayAddress('127.0.0.1')
        sockets = [{'protocol': protocol, 'host': '127.0.0.1', 'port': port}
                   for protocol, port in (('tcp', address.rtmp_port), ('udp', address.srt_port),
                                          ('tcp', address.rtsp_port))]
        with tempfile.TemporaryDirectory() as directory, \
                patch('relay.mediamtx.subprocess.Popen', return_value=Process(logs)), \
                patch('relay.mediamtx.linux_bound_sockets', return_value=sockets):
            with MediaMTX(address, Credentials('phone', secret), Credentials('internal', secret),
                          binary='/synthetic/mediamtx', archive=directory):
                pass
            text = (Path(directory) / 'mediamtx.json').read_text()
            saved = json.loads(text)
        self.assertEqual(saved['warning_counts'],
                         {'slow-reader': 70, 'write-queue-full': 1, 'other-warning': 2})
        self.assertEqual(len(saved['recent_warnings']), 64)
        self.assertEqual(saved['diagnostic_drops'], 9)
        self.assertTrue(saved['diagnostic_reader_stopped'])
        self.assertEqual(saved['process_returncode'], 0)
        self.assertEqual(saved['recent_warnings'][0]['path'], 'camera')
        self.assertEqual(saved['recent_warnings'][0]['protocol'], 'RTSP')
        self.assertEqual(saved['recent_closes'][0]['code'], 'eof')
        self.assertNotIn(secret, text)
        self.assertNotIn('private.invalid', text)
        self.assertNotIn('abc', text)

    def test_startup_failure_keeps_warning_and_oversize_drop_evidence(self):
        logs = b'WAR ' + b'x' * 9000 + b'\nWAR [RTSP] [session abc] write queue is full\n'
        with tempfile.TemporaryDirectory() as directory, \
                patch('relay.mediamtx.subprocess.Popen', return_value=Process(logs, failed=True)):
            with self.assertRaisesRegex(RuntimeError, 'MediaMTX startup failed'):
                with MediaMTX(RelayAddress('127.0.0.1'), Credentials('phone', 'secret'),
                              Credentials('internal', 'secret'), binary='/synthetic/mediamtx',
                              archive=directory):
                    self.fail('failed MediaMTX became ready')
            saved = json.loads((Path(directory) / 'mediamtx.json').read_text())
        self.assertEqual(saved['warning_counts'], {'write-queue-full': 1})
        self.assertEqual(saved['diagnostic_drops'], 2)
        self.assertTrue(saved['diagnostic_reader_stopped'])
        self.assertEqual(saved['process_returncode'], 1)

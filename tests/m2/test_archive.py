"""Archive opt-in and filesystem exhaustion at the real encoder/transport seam."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import av
import numpy as np

from relay.stream import Egress, _encode_worker
from shield.cli import parser
from test_stream import presented


def low_disk_worker(*args):
    # The child sees an actual filesystem-capacity failure while running the
    # production encoder. No transport or encoder behavior is faked here.
    from collections import namedtuple
    usage = namedtuple('usage', 'total used free')(1024**3, 1024**3, 0)
    with patch('shutil.disk_usage', return_value=usage):
        _encode_worker(*args)


def disk_fills_worker(*args):
    from collections import namedtuple
    usage = namedtuple('usage', 'total used free')
    calls = 0
    def capacity(_):
        nonlocal calls
        calls += 1
        return usage(1024**3, 0, 1024**3 if calls <= 12 else 0)
    with patch('shutil.disk_usage', side_effect=capacity):
        _encode_worker(*args)


class ArchivePolicy(unittest.TestCase):
    def test_default_off_and_explicit_archive_keep_the_real_output(self):
        args = parser().parse_args(['run', '--host', '127.0.0.1', '--local-only'])
        self.assertIsNone(args.archive,
                          'shield run must not archive by default')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for archive in (None, root/'evidence'):
                network = root / ('off.flv' if archive is None else 'on.flv')
                output = Egress(str(network), archive, width=64, height=32, encoder='libx264')
                try:
                    for index in range(12):
                        output.write(presented(index), np.zeros(1600, np.int16))
                finally:
                    output.close()
                with av.open(str(network)) as incoming:
                    self.assertEqual(len(list(incoming.decode(video=0))), 12)
                self.assertEqual(output.count, 12)
                if archive is not None:
                    self.assertTrue((archive/'encoded.flv').stat().st_size > 0)
                    self.assertEqual(len((archive/'frames.jsonl').read_text().splitlines()), 12)
            self.assertEqual(sorted(p.name for p in root.iterdir()), ['evidence', 'off.flv', 'on.flv'])

    def test_low_disk_stops_only_evidence_and_keeps_relay_encoding(self):
        for worker in (low_disk_worker, disk_fills_worker):
            with self.subTest(worker=worker.__name__), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive = root/'evidence'
                with patch('relay.stream._encode_worker', worker):
                    output = Egress(str(root/'network.flv'), archive, width=64, height=32, encoder='libx264')
                try:
                    for index in range(12):
                        output.write(presented(index), np.zeros(1600, np.int16))
                finally:
                    output.close()
                self.assertEqual(output.count, 12)
                self.assertEqual(output.recovery_count, 0, 'disk exhaustion must not spend transport retries')
                if worker is low_disk_worker:
                    self.assertFalse(archive.exists() and any(archive.iterdir()), 'no archive or per-frame log on low disk')
                else:
                    logged = (archive/'frames.jsonl').read_text().splitlines()
                    self.assertGreater(len(logged), 0, 'the archive must start before space runs out')
                    self.assertLess(len(logged), 12, 'evidence must stop when the disk fills')
                with av.open(str(root/'network.flv')) as incoming:
                    self.assertEqual(len(list(incoming.decode(video=0))), 12)

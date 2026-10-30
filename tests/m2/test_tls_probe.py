"""Legacy diagnostic must distinguish a broken fixture from peer rejection."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from relay.mediamtx import verified_binary
import tls_probe


@unittest.skipUnless(sys.platform == 'linux', 'Legacy bundled-FFmpeg probe uses the pinned Linux fixture')
class ProbeFailure(unittest.TestCase):
    def test_dead_server_in_negative_case_is_fixture_error_instead_of_secure_pass(self):
        owned, killed = [], []
        real_spawn, real_publish = subprocess.Popen, tls_probe.publish
        def spawn(*args, **kwargs):
            process = real_spawn(*args, **kwargs)
            argv = args[0] if args else kwargs.get('args', [])
            if argv and Path(argv[0]).name == 'mediamtx':
                owned.append(process)
            return process
        def publish(url, *args, **kwargs):
            if 'pyav-untrusted-options' in url:
                killed.append(True)
                self.assertEqual(len(owned), 1)
                owned[0].terminate()
                owned[0].wait(timeout=3)
            return real_publish(url, *args, **kwargs)
        with tempfile.TemporaryDirectory(prefix='irl-shield-dead-tls-') as temporary:
            argv = ['tls_probe.py', '--mediamtx', str(verified_binary()), '--out', str(Path(temporary) / 'evidence')]
            output = StringIO()
            with patch.object(subprocess, 'Popen', side_effect=spawn), \
                    patch.object(tls_probe, 'publish', side_effect=publish), \
                    patch.object(sys, 'argv', argv), redirect_stdout(output):
                code = tls_probe.main()
            self.assertEqual(killed, [True], 'fixture must reach and kill the negative-case peer')
            self.assertEqual(code, 2, 'a dead fixture cannot earn a peer-verification pass')
        self.assertEqual(len(owned), 1)
        self.assertIsNotNone(owned[0].poll())

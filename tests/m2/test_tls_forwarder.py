"""Forwarder seam: actual loopback TLS, certificates and repeated plain clients."""
from pathlib import Path
import socket
import tempfile
import unittest

from relay.tls_forwarder import TLSForwarder
from tls_fixture import EchoTLS, certificates


class Forwarder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory(prefix='irl-shield-tls-test-')
        cls.root = certificates(Path(cls.scratch.name))

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_verified_bidirectional_bytes_survive_repeated_writer_connections(self):
        with EchoTLS(self.root) as target:
            with TLSForwarder('127.0.0.1', target.port, cafile=self.root / 'peer.crt') as forwarder:
                for payload in (b'first-synthetic-connection', b'second-synthetic-connection'):
                    with socket.create_connection(('127.0.0.1', forwarder.port), timeout=2) as client:
                        client.sendall(payload)
                        actual = bytearray()
                        while len(actual) < len(payload):
                            part = client.recv(1024)
                            self.assertTrue(part)
                            actual.extend(part)
                        self.assertEqual(actual, payload)
            self.assertEqual(b''.join(target.received), b'first-synthetic-connectionsecond-synthetic-connection')
        self.assertEqual(forwarder.stats['failures'], 0)

    def test_untrusted_ca_and_wrong_hostname_close_before_any_plaintext_reaches_peer(self):
        for server, ca in (('peer', 'other'), ('wrong', 'wrong')):
            with self.subTest(server=server, ca=ca), EchoTLS(self.root, server) as target:
                with TLSForwarder('127.0.0.1', target.port, cafile=self.root / (ca + '.crt')) as forwarder:
                    with socket.create_connection(('127.0.0.1', forwarder.port), timeout=2) as client:
                        client.sendall(b'SYNTHETIC-SECRET-MUST-NOT-LEAVE-LOOPBACK')
                        try:
                            data = client.recv(1024)
                        except ConnectionResetError:
                            data = b''
                        self.assertEqual(data, b'')
                    self.assertEqual(forwarder.stats['failures'], 1)
                    self.assertEqual(forwarder.stats['last_error'], 'tls-verification-failed')
                self.assertEqual(target.received, [])

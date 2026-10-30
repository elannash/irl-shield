"""Forwarder seam: actual loopback TLS, certificates and repeated plain clients."""
from pathlib import Path
import socket
import tempfile
import unittest

from relay.tls_forwarder import TLSForwarder
from tls_fixture import EchoTLS, certificates
from wire_fixture import RawPeer


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
            with RawPeer(target.port) as wire, TLSForwarder('127.0.0.1', wire.port, cafile=self.root / 'peer.crt') as forwarder:
                for payload in (b'first-synthetic-connection', b'second-synthetic-connection'):
                    with socket.create_connection(('127.0.0.1', forwarder.port), timeout=2) as client:
                        client.sendall(payload)
                        actual = bytearray()
                        while len(actual) < len(payload):
                            part = client.recv(1024)
                            self.assertTrue(part)
                            actual.extend(part)
                        self.assertEqual(actual, payload)
            observed = wire.rejection(b'first-synthetic-connection')
            self.assertGreater(observed['bytes_received'], 0)
            self.assertTrue(observed['canary_absent'])
            self.assertTrue(any(0x17 in records for records in observed['record_types']), 'Positive control must observe encrypted application records')
            self.assertEqual(b''.join(target.received), b'first-synthetic-connectionsecond-synthetic-connection')
        self.assertEqual(forwarder.stats['failures'], 0)

    def test_untrusted_ca_and_wrong_hostname_close_before_any_plaintext_reaches_peer(self):
        for server, ca in (('peer', 'other'), ('wrong', 'wrong')):
            with self.subTest(server=server, ca=ca), EchoTLS(self.root, server) as target:
                secret = b'SYNTHETIC-SECRET-MUST-NOT-LEAVE-LOOPBACK'
                with RawPeer(target.port) as wire, TLSForwarder('127.0.0.1', wire.port, cafile=self.root / (ca + '.crt')) as forwarder:
                    with socket.create_connection(('127.0.0.1', forwarder.port), timeout=2) as client:
                        client.sendall(secret)
                        try:
                            data = client.recv(1024)
                        except ConnectionResetError:
                            data = b''
                        self.assertEqual(data, b'')
                    self.assertEqual(forwarder.stats['failures'], 1)
                    self.assertEqual(forwarder.stats['last_error'], 'tls-verification-failed')
                observed = wire.rejection(secret)
                self.assertGreater(observed['connections'], 0)
                self.assertGreater(observed['bytes_received'], 0)
                self.assertEqual(observed['capture_errors'], [])
                self.assertTrue(observed['canary_absent'], 'Synthetic secret reached raw TCP peer')
                self.assertTrue(observed['client_hello_and_controls_only'], 'Rejected peer received non-TLS/application bytes')
                self.assertTrue(all(records[0] == 0x16 for records in observed['record_types']))
                self.assertEqual(target.received, [])

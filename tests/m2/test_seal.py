"""Evidence integrity at the seal/verify and licensed-source public interfaces."""
import json
from pathlib import Path
import tempfile
import unittest

from relay.seal import seal, verify
from relay.fixture import describe_source


class EvidenceSeal(unittest.TestCase):
    def test_verification_rejects_mutated_evidence_even_when_seal_is_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            payload = directory / 'capture.flv'
            payload.write_bytes(b'original network packets')
            expected = seal(directory)
            self.assertIn('capture.flv', verify(directory, expected)['files'])
            payload.chmod(0o600)
            payload.write_bytes(b'replacement network data')
            with self.assertRaisesRegex(ValueError, 'Evidence'):
                verify(directory, expected)

    def test_added_deleted_and_symlinked_evidence_cannot_verify(self):
        for change in ('added', 'deleted', 'symlinked'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                payload = directory / 'capture.flv'
                payload.write_bytes(b'network packets')
                expected = seal(directory)
                if change == 'added':
                    (directory / 'late-frame.json').write_text('{}')
                else:
                    payload.unlink()
                    if change == 'symlinked':
                        payload.symlink_to(directory / 'seal.json')
                with self.assertRaisesRegex(ValueError, 'Evidence'):
                    verify(directory, expected)

    def test_replaced_seal_cannot_authorize_a_rewritten_capture(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'capture.flv').write_bytes(b'network packets')
            expected = seal(directory)
            manifest = directory / 'seal.json'
            manifest.chmod(0o600)
            manifest.write_text('{"version":1,"files":{}}')
            with self.assertRaisesRegex(ValueError, 'Seal digest'):
                verify(directory, expected)


class LicensedSource(unittest.TestCase):
    def test_changed_fixture_is_rejected_before_network_or_encoding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'clip.mp4').write_bytes(b'abc')
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps({'clips': [{
                'id': 'tiny', 'split': 'tune', 'path': 'clip.mp4', 'license': 'CC0',
                'sha256': 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
                'source_url': 'https://example.invalid/licensed', 'author': 'Synthetic test',
                'width': 1280, 'height': 720, 'fps': 30, 'duration': 5}]}))
            self.assertEqual(describe_source(manifest, 'tiny', root)['source']['sha256'],
                             'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
            (root / 'clip.mp4').write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'Source bytes'):
                describe_source(manifest, 'tiny', root)

    def test_unlicensed_and_heldout_sources_are_rejected(self):
        for split, license_name in (('heldout', 'CC0'), ('tune', 'All rights reserved')):
            with self.subTest(split=split, license_name=license_name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                manifest = root / 'manifest.json'
                manifest.write_text(json.dumps({'clips': [{'id': 'tiny', 'split': split, 'license': license_name}]}))
                with self.assertRaises(ValueError):
                    describe_source(manifest, 'tiny', root)

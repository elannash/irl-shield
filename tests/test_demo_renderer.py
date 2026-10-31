"""W8 structural inputs: synthetic fixtures establish no native proof."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools.demo_renderer.branding import retain_raw
from tools.demo_renderer.evidence import validate_structure
from tools.demo_renderer.source import camera_box, sha256


def synthetic_document():
    # Literal source-less startup, a real-source slot, and an un-emitted slot.
    return {'schema': 'irl-shield-w8-native-v3', 'producer_kind': 'synthetic-test',
        'source_manifest_sha256': 'a' * 64,
        'window': {'first_engine_index': 0, 'stop_engine_index': 3},
        'sources': [{'id': 'capture-0', 'source_index': 0, 'ingest_generation': 1,
                     'ingest_pts': '0', 'input_vcl_sha256': 'b' * 64}],
        'selections': [
            {'engine_index': 0, 'kind': 'source-less', 'source_id': None, 'reason': 'startup'},
            {'engine_index': 1, 'kind': 'source', 'source_id': 'capture-0', 'reason': None}],
        'detections': [],
        'outputs': [
            {'egress_generation': 1, 'output_index': 0, 'engine_index': 0, 'session_pts': '0',
             'state': 'HOLD', 'slate': True, 'source_id': None, 'applied_detection_ids': [],
             'pixels_sha256': 'c' * 64, 'mask_sha256': 'd' * 64, 'output_vcl_sha256': 'e' * 64},
            {'egress_generation': 1, 'output_index': 1, 'engine_index': 1, 'session_pts': '1/30',
             'state': 'LIVE', 'slate': False, 'source_id': 'capture-0', 'applied_detection_ids': [],
             'pixels_sha256': 'f' * 64, 'mask_sha256': '1' * 64, 'output_vcl_sha256': '2' * 64}],
        'gaps': [{'first_engine_index': 2, 'stop_engine_index': 3, 'source_id': None, 'reason': 'not-emitted'}]}


class NativeStructure(unittest.TestCase):
    def test_source_less_startup_missing_capture_and_output_gaps_remain_honest(self):
        document = synthetic_document()
        original = copy.deepcopy(document)
        report = validate_structure(document)
        self.assertEqual(document, original)
        self.assertEqual((report['source_less_outputs'], report['unemitted_slots']), (1, 1))
        self.assertFalse(report['native_verified'])
        document['selections'][0]['reason'] = 'missing-capture'
        document['outputs'][0]['state'] = 'PROTECT'
        self.assertEqual(validate_structure(document)['source_less_outputs'], 1)

    def test_rejects_fabricated_startup_source_and_live_source_less_pixels(self):
        for field, value in (('source_id', 'capture-0'), ('state', 'LIVE'), ('slate', False),
                             ('applied_detection_ids', ['invented'])):
            with self.subTest(field=field):
                document = synthetic_document()
                document['outputs'][0][field] = value
                with self.assertRaises(ValueError):
                    validate_structure(document)
        document = synthetic_document()
        document['selections'][0]['source_id'] = 'capture-0'
        with self.assertRaisesRegex(ValueError, 'source null'):
            validate_structure(document)

    def test_holes_require_explicit_gaps_and_gaps_cannot_claim_source(self):
        for change in ('omitted', 'overlap', 'fake-source', 'fractional-index'):
            with self.subTest(change=change):
                document = synthetic_document()
                if change == 'omitted':
                    document['gaps'] = []
                elif change == 'overlap':
                    document['gaps'][0]['first_engine_index'] = 1
                elif change == 'fake-source':
                    document['gaps'][0]['source_id'] = 'capture-0'
                else:
                    document['outputs'][0]['engine_index'] = .5
                with self.assertRaises(ValueError):
                    validate_structure(document)

    def test_self_declared_actual_native_never_becomes_verification(self):
        document = synthetic_document()
        document['producer_kind'] = 'actual-native-relay'
        report = validate_structure(document)
        self.assertFalse(report['native_verified'])
        self.assertEqual(report['status'], 'STRUCTURE ONLY / NOT CLEARED')


class SourceMotion(unittest.TestCase):
    def test_source_entry_holds_the_canonical_lease_before_build(self):
        from contextlib import contextmanager
        import sys
        from unittest.mock import patch
        from tools.demo_renderer.run import main
        events = []
        @contextmanager
        def lease():
            events.append('lease-enter')
            try:
                yield
            finally:
                events.append('lease-exit')
        def build():
            self.assertEqual(events, ['lease-enter'])
            events.append('build')
        with patch('tools.demo_renderer.run.runpy.run_path', return_value={'exclusive_lease': lease}), \
                patch('tools.demo_renderer.source.main', side_effect=build), \
                patch.object(sys, 'argv', ['demo', 'source', '--output', 'unused']):
            main()
        self.assertEqual(events, ['lease-enter', 'build', 'lease-exit'])

    def test_camera_keeps_moving_without_a_reset_through_210_seconds(self):
        previous = camera_box(0)
        for index in range(1, 6300):
            box = camera_box(index)
            self.assertGreater(box[0], previous[0])
            self.assertLess(box[2] - box[0], previous[2] - previous[0])
            self.assertTrue(0 <= box[0] < box[2] <= 1920 and 0 <= box[1] < box[3] <= 1080)
            previous = box
        with self.assertRaises(ValueError):
            camera_box(6300)


class RawBranding(unittest.TestCase):
    def test_preserves_low_confidence_unknown_empty_and_error_observations_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / 'source.json'
            manifest.write_text('{"status":"NOT CLEARED"}\n')
            raw = root / 'raw.json'
            payload = {'judge': 'tesseract-5-psm11', 'source_manifest_sha256': sha256(manifest),
                'collection_stage': 'raw-before-filters', 'observations': [
                    {'frame': 0, 'text': 'UNKNOWN', 'confidence': -1, 'unknown': True},
                    {'frame': 1, 'text': '', 'confidence': None},
                    {'frame': 2, 'error': {'class': 'SyntheticJudgeError'}}]}
            raw.write_text(json.dumps(payload, indent=3) + '\n')
            result = retain_raw(root / 'retained', manifest, {'tesseract-5-psm11': raw})
            self.assertEqual((root / 'retained/tesseract-5-psm11.json').read_bytes(), raw.read_bytes())
            self.assertEqual(result['missing_judges'], ['ppocr-independent', 'vision-accurate'])
            self.assertEqual(result['status'], 'NOT CLEARED')
            self.assertIsNone(result['canonical_clearance'])
            self.assertIsNone(result['human_logo_eye'])
            payload['source_manifest_sha256'] = '0' * 64
            raw.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, 'binding'):
                retain_raw(root / 'wrong', manifest, {'tesseract-5-psm11': raw})


if __name__ == '__main__':
    unittest.main()

"""CPU-only metadata/preprocessing checks; no inference, video, OCR or queue."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from bench.q2_recall.prepare import POLICIES, load_policies, prepare_plan, timed_argv


class RecallPolicies(unittest.TestCase):
    def test_baseline_bytes_cannot_silently_change_under_the_prepared_arms(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'policies'
            shutil.copytree(POLICIES, directory)
            path = directory / 'baseline.json'
            path.write_bytes(path.read_bytes() + b'\n')
            with self.assertRaisesRegex(ValueError, 'frozen baseline policy'):
                load_policies(directory)

    def test_combined_arm_is_rejected_before_any_commands_are_prepared(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'policies'
            shutil.copytree(POLICIES, directory)
            path = directory / 'small1280.json'
            policy = json.loads(path.read_text())
            policy['options']['padding'] = .1
            path.write_text(json.dumps(policy))
            with self.assertRaisesRegex(ValueError, 'small1280 must change only limit_side_len'):
                load_policies(directory)

    def test_substituted_manifest_is_rejected_before_any_commands_are_prepared(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'fixtures').mkdir()
            fixture = root / 'fixtures/manifest.json'
            fixture.write_text('{"clips": []}')
            inputs = root / 'inputs.json'
            inputs.write_text(json.dumps({
                'fixture_manifest_sha256': hashlib.sha256(fixture.read_bytes()).hexdigest(),
                'clips': [{'clip': 'synthetic', 'synthetic_variant': False,
                           'source': '/synthetic/never-read.mp4'}],
            }))
            with self.assertRaisesRegex(ValueError, 'exact frozen tune input manifest'):
                prepare_plan(root, inputs)

    def test_1280_arm_changes_actual_detector_tensor_without_changing_fast_tensor(self):
        import numpy as np
        from rapidocr.ch_ppocr_det.utils import DetPreProcess
        policies = load_policies()
        # Known 16:9 lane inputs, no fixture pixels or ONNX sessions.
        accurate = np.zeros((720, 1280, 3), np.uint8)
        fast = np.zeros((360, 640, 3), np.uint8)
        baseline = policies['baseline']['options']
        larger = policies['small1280']['options']
        self.assertEqual(DetPreProcess(baseline['limit_side_len'], 'max')(accurate).shape,
                         (1, 3, 544, 960))
        self.assertEqual(DetPreProcess(larger['limit_side_len'], 'max')(accurate).shape,
                         (1, 3, 704, 1280))
        self.assertEqual(DetPreProcess(larger['fast_limit_side_len'], 'max')(fast).shape,
                         (1, 3, 352, 640))

    def test_clocked_command_preserves_policy_instead_of_using_cli_defaults(self):
        policies = load_policies()
        command = timed_argv(policies['accurate8hz'], '/synthetic/input.mp4', '/synthetic/output.mp4')
        options = dict(zip(command[5:-1:2], command[6:-1:2]))
        self.assertEqual(options['--after'], '30')
        self.assertEqual(options['--fast-rate-hz'], '8.0')
        self.assertEqual(options['--accurate-rate-hz'], '8.0')
        self.assertEqual(options['--motion-min-response'], '0.05')
        self.assertEqual(options['--encoder'], 'h264_nvenc')
        self.assertEqual(command[-1], '--static-model')


if __name__ == '__main__':
    unittest.main()

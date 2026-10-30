"""Runtime detector selection must agree with independent-truth provenance."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from bench.clocked_pipeline import _run_file
from bench.independence import judging_scope, policy_metadata
from bench.offline_quality import _make_backends


class EmptyDetector:
    def __init__(self):
        self.closed = False

    def detect_quads(self, pixels):
        return []

    def close(self):
        self.closed = True


class StopAfterFactory(RuntimeError):
    """End clocked setup after observing both detector selections, before workers."""


class RuntimeFamilies(unittest.TestCase):
    def test_changed_declared_default_reaches_both_runtime_factories_and_truth_scope(self):
        with patch.dict('bench.independence.DEFAULT_FAST_CANDIDATES', {'vision-accurate': 'ppocr-v6-tiny'}):
            metadata = policy_metadata('vision-accurate', {})
            self.assertEqual(metadata['detector_families'], ['apple-vision', 'paddleocr'])
            scope = judging_scope(metadata['detector_families'])
            self.assertEqual(scope['truth_judges'], ['tesseract'])
            self.assertFalse(scope['sufficient_independent_engines'])

            with self.subTest(runtime='offline'), \
                 patch('bench.pipeline.detector_for', side_effect=lambda *args: EmptyDetector()) as factory:
                backends = _make_backends('vision-accurate', {}, [1280, 720])
                try:
                    self.assertEqual([call.args[0] for call in factory.call_args_list],
                                     ['ppocr-v6-tiny', 'vision-accurate'])
                finally:
                    for backend in backends.values():
                        backend.close()

            with self.subTest(runtime='clocked'), tempfile.TemporaryDirectory() as temporary:
                source, output = Path(temporary) / 'source.mp4', Path(temporary) / 'output.mp4'
                source.write_bytes(b'synthetic source; decoder is supplied below')
                backend = EmptyDetector()
                with patch('bench.clocked_pipeline.probe_media',
                           return_value={'fps': 30., 'frames': 2, 'resolution': [1280, 720]}), \
                     patch('bench.clocked_pipeline.subprocess.check_output', return_value='synthetic ffmpeg version\n'), \
                     patch('bench.clocked_pipeline.cv2.VideoCapture') as capture, \
                     patch('bench.pipeline.detector_for', side_effect=[backend, StopAfterFactory()]) as factory:
                    capture.return_value.read.return_value = (True, np.zeros((720, 1280, 3), np.uint8))
                    with self.assertRaises(StopAfterFactory):
                        _run_file(source, output, 'vision-accurate', {}, None, {})
                    self.assertEqual([call.args[0] for call in factory.call_args_list],
                                     ['ppocr-v6-tiny', 'vision-accurate'])
                    self.assertTrue(backend.closed)
                    capture.return_value.release.assert_called_once_with()

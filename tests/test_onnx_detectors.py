"""Synthetic DB probability maps through the real detector adapter; no models."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from rapidocr.ch_ppocr_det import TextDetector
from rapidocr.ch_ppocr_det.utils import DBPostProcess

from bench.detector_options import lane_detector_options
from bench.onnx_detectors import _session, create_detector
from bench.pipeline import detector_for


class CPUProvider(unittest.TestCase):
    def test_cpu_session_is_explicit_and_cannot_fall_back_to_cuda(self):
        artifact = {'sha256': '0' * 64, 'license': 'CC0-1.0', 'license_source': 'synthetic',
                    'source': 'synthetic', 'url': 'not-downloaded'}
        for available, active, succeeds in ((['CPUExecutionProvider', 'CUDAExecutionProvider'], ['CPUExecutionProvider'], True),
                                            (['CUDAExecutionProvider'], [], False),
                                            (['CPUExecutionProvider'], ['CUDAExecutionProvider'], False)):
            with self.subTest(available=available, active=active), \
                    patch('bench.onnx_detectors.verified_path', return_value=('/synthetic/not-read.onnx', artifact)), \
                    patch('bench.onnx_detectors.ort.get_available_providers', return_value=available), \
                    patch('bench.onnx_detectors.ort.InferenceSession') as factory:
                factory.return_value.get_providers.return_value = active
                if succeeds:
                    session, metadata, _ = _session('ppocr-v6-tiny', {'provider': 'cpu'})
                    self.assertIs(session, factory.return_value)
                    self.assertEqual(metadata['execution_provider'], 'CPUExecutionProvider')
                    self.assertEqual(metadata['active_execution_providers'], ['CPUExecutionProvider'])
                    self.assertFalse(metadata['cpu_operator_partition_fallback_allowed'])
                else:
                    with self.assertRaisesRegex(RuntimeError, 'CPUExecutionProvider'):
                        _session('ppocr-v6-tiny', {'provider': 'cpu'})
                if 'CPUExecutionProvider' in available:
                    factory.assert_called_once()
                    self.assertEqual(factory.call_args.kwargs['providers'], ['CPUExecutionProvider'])
                    factory.return_value.disable_fallback.assert_called()
                else:
                    factory.assert_not_called()


class BoxConfidence(unittest.TestCase):
    def setUp(self):
        self.frame = np.zeros((96, 192, 3), np.uint8)
        self.prediction = np.zeros((1, 1, 96, 192), np.float32)
        self.prediction[0, 0, 20:45, 15:55] = .6
        self.prediction[0, 0, 20:45, 110:150] = .9
        artifact = {'preprocess': {'mean': [0., 0., 0.], 'std': [1., 1., 1.]}}
        self.enterContext(patch('bench.onnx_detectors._session',
                                side_effect=lambda *args: (object(), {}, artifact)))
        self.enterContext(patch('bench.onnx_detectors.TextDetector', side_effect=self.text_detector))

    def text_detector(self, cfg):
        postprocess = DBPostProcess(**{key: cfg[key] for key in
                                      ('thresh', 'box_thresh', 'max_candidates', 'unclip_ratio', 'use_dilation', 'score_mode')})

        def detect(frame):
            boxes, scores = postprocess(self.prediction.copy(), frame.shape[:2])
            return SimpleNamespace(boxes=TextDetector.sorted_boxes(boxes), scores=scores)
        return detect

    def test_default_off_geometry_is_exact_through_pipeline_and_adapter(self):
        baseline = create_detector('ppocr-v6-small', {'limit_side_len': 96})
        self.addCleanup(baseline.close)
        expected = baseline.detect_quads(self.frame)
        self.assertEqual(len(expected), 2, 'Both synthetic islands must exercise DBPostProcess')
        self.assertLess(expected[0][0][0], 96)
        self.assertGreater(expected[1][0][0], 96)
        for options in ({}, {'accurate_box_thresh': None}):
            for lane in ('fast', 'accurate'):
                with self.subTest(options=options, lane=lane):
                    backend = detector_for('ppocr-v6-small', lane_detector_options({'limit_side_len': 96, **options}, lane))
                    self.addCleanup(backend.close)
                    self.assertEqual(backend.detect_quads(self.frame), expected)
                    self.assertEqual(backend.detect(self.frame), baseline.detect(self.frame))

    def test_accurate_filters_low_score_island_while_fast_is_exactly_unchanged(self):
        baseline = create_detector('ppocr-v6-small', {'limit_side_len': 96})
        self.addCleanup(baseline.close)
        expected = baseline.detect_quads(self.frame)
        self.assertEqual(len(expected), 2)
        options = {'limit_side_len': 96, 'accurate_box_thresh': .75}
        fast = detector_for('ppocr-v6-small', lane_detector_options(options, 'fast'))
        accurate = detector_for('ppocr-v6-small', lane_detector_options(options, 'accurate'))
        self.addCleanup(fast.close)
        self.addCleanup(accurate.close)
        self.assertEqual(fast.detect_quads(self.frame), expected)
        self.assertEqual(accurate.detect_quads(self.frame), [expected[1]])
        self.assertEqual(fast.metadata['parameters']['box_thresh'], .5)
        self.assertEqual(accurate.metadata['parameters']['box_thresh'], .75)

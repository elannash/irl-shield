"""Synthetic DB probability maps through the real detector adapter; no models."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from rapidocr.ch_ppocr_det import TextDetector
from rapidocr.ch_ppocr_det.utils import DBPostProcess

from bench.detector_options import lane_detector_options
from bench.onnx_detectors import create_detector
from bench.pipeline import detector_for


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

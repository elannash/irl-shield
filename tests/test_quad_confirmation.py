"""Confirmation behavior at the same detect_quads seam used by detector lanes."""
import unittest
from types import SimpleNamespace

import cv2
import numpy as np

from shield.quad_confirmation import QuadConfirmationDetector
from shield.render import Renderer


GIANT = [[0, 0], [95, 0], [95, 63], [0, 63]]
ORDINARY = [[5, 5], [17, 5], [17, 13], [5, 13]]


class ReplayedDetector:
    metadata = {'detector_families': ['paddleocr'], 'name': 'synthetic-replay'}

    def __init__(self, quads):
        self.quads = quads

    def detect_quads(self, pixels):
        return self.quads

    def close(self):
        pass


class PixelConfirmation:
    """Synthetic external recognizer: known ink confirms, blank pavement denies."""
    metadata = {'detector_families': ['paddleocr'], 'name': 'synthetic-pixel-reader'}

    def confirm(self, pixels, quad):
        return bool((pixels < 40).any())

    def close(self):
        pass


class QuadConfirmation(unittest.TestCase):
    def test_false_giant_is_removed_but_equal_size_text_and_ordinary_quads_survive(self):
        # The same geometry for both images makes an area-only rejection fail.
        pavement = np.full((64, 96, 3), 160, np.uint8)
        closeup = pavement.copy()
        cv2.putText(closeup, '824', (3, 47), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 3)
        detector = QuadConfirmationDetector(ReplayedDetector([GIANT, ORDINARY]), PixelConfirmation())
        false_output = detector.detect_quads(pavement)
        positive_output = detector.detect_quads(closeup)
        self.assertEqual(false_output, [ORDINARY])
        self.assertEqual(positive_output, [GIANT, ORDINARY])
        render = Renderer(padding=0)
        self.assertEqual(render.render(pavement, false_output, 'LIVE', 1).mask[40, 70], 0)
        self.assertEqual(render.render(closeup, positive_output, 'LIVE', 2).mask[40, 70], 255)

    def test_uncertain_or_failed_confirmation_retains_original_mask_and_reports_failure(self):
        class Unavailable(PixelConfirmation):
            def confirm(self, pixels, quad):
                raise RuntimeError('synthetic unavailable recognizer')

        class Uncertain(PixelConfirmation):
            def confirm(self, pixels, quad):
                return None

        pixels = np.full((64, 96, 3), 160, np.uint8)
        for confirmer, errors in ((Uncertain(), 0), (Unavailable(), 1)):
            with self.subTest(confirmer=type(confirmer).__name__):
                detector = QuadConfirmationDetector(ReplayedDetector([GIANT]), confirmer)
                self.assertEqual(detector.detect_quads(pixels), [GIANT])
                self.assertEqual(detector.stats['uncertain'], 1)
                self.assertEqual(detector.stats['confirmation_errors'], errors)
                self.assertEqual(detector.stats['rejected'], 0)
                self.assertEqual(detector.metadata['detector_families'], ['paddleocr'])

    def test_crop_recognition_checks_the_quad_pixels_and_low_confidence_cannot_confirm(self):
        from bench.q2_confirmers import PaddleQuadConfirmer

        class ExternalRecognizer:
            def __call__(self, request):
                # Ink elsewhere in the frame must not rescue a blank candidate.
                ink = bool((request.img[0] < 40).any())
                return SimpleNamespace(txts=['824'], scores=[.95 if ink else .1])

        pixels = np.full((64, 96, 3), 180, np.uint8)
        pixels[3:12, 70:90] = 0
        confirmer = PaddleQuadConfirmer(ExternalRecognizer(), {'name': 'synthetic-recognizer'})
        self.assertIs(confirmer.confirm(pixels, ORDINARY), False)
        self.assertIs(confirmer.confirm(pixels, GIANT), True)

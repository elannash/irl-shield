"""Q2 crop-recognition experiment using the already pinned PP English model.

Existing licenses: PP-OCRv5 English mobile and RapidOCR Apache-2.0;
ONNX Runtime MIT; OpenCV Apache-2.0; NumPy BSD-3-Clause. See models/manifest.json
and models/licenses/dependencies.json. No new model or package is downloaded.
"""
import math

import cv2
import numpy as np
from rapidocr.ch_ppocr_rec import TextRecInput, TextRecognizer
from rapidocr.utils.process_img import get_rotate_crop_image


class PaddleQuadConfirmer:
    """Recognize a rectified quad, without running a second text detector.

    Empty/low-confidence recognition denies confirmation. This is experimental:
    a recognizer false negative can suppress real text and must reject the policy
    in the challenge probe or independent quality evaluation.
    """

    def __init__(self, recognizer, metadata, *, confidence=.5):
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError('Recognition confidence must be in [0, 1]')
        self.recognizer = recognizer
        self.metadata = {'name': 'ppocr-v5-english-quad-confirmation',
                         'detector_families': ['paddleocr'], 'recognizer': metadata,
                         'confidence': confidence, 'no_detection_stage': True}
        self.confidence = confidence
        self.last_reading = None

    def confirm(self, pixels, quad):
        if self.recognizer is None:
            raise RuntimeError('Quad recognizer is closed')
        points = np.asarray(quad, np.float32)
        if points.shape != (4, 2) or not np.isfinite(points).all():
            raise ValueError('Expected four finite quad corners')
        hull = cv2.convexHull(points).reshape(-1, 2)
        if len(hull) != 4 or cv2.contourArea(hull) < 1:
            return None
        points = np.roll(hull, -int(np.argmin(hull.sum(axis=1))), axis=0)
        crop = get_rotate_crop_image(pixels, points)
        result = self.recognizer(TextRecInput(img=[crop]))
        if len(result.txts) != 1 or len(result.scores) != 1:
            raise ValueError('Recognizer must return exactly one candidate reading')
        text, score = result.txts[0], float(result.scores[0])
        if not math.isfinite(score):
            raise ValueError('Recognizer confidence must be finite')
        self.last_reading = {'text': text, 'confidence': score, 'crop_shape': list(crop.shape)}
        return any(char.isascii() and char.isalnum() for char in text) and score >= self.confidence

    def close(self):
        self.recognizer = None


def create_confirmer(options=None, *, confidence=.5):
    """Borrow the project's verified session constructor and existing model cache."""
    from bench.onnx_detectors import _session
    from omegaconf import OmegaConf
    from rapidocr.utils.typings import EngineType

    session, metadata, _ = _session('ppocr-v5-english-rec', dict(options or {}))
    if 'character' not in session.get_modelmeta().custom_metadata_map:
        raise RuntimeError('Pinned recognizer is missing its embedded character dictionary')
    cfg = OmegaConf.create({'engine_type': EngineType.ONNXRUNTIME, 'lang_type': 'en',
                           'rec_batch_num': 1, 'rec_img_shape': [3, 48, 320],
                           'rec_keys_path': None, 'font_path': None}, flags={'allow_objects': True})
    cfg.session = session
    return PaddleQuadConfirmer(TextRecognizer(cfg), metadata, confidence=confidence)

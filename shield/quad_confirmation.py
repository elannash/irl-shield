"""Optional detector adapter for confirming large quads at the detector seam.

Uses existing NumPy (BSD-3-Clause) and OpenCV (Apache-2.0). No model is
selected here; injected detectors and confirmers declare their provenance.
"""
from collections import Counter, deque
import hashlib
import math
import time

import cv2
import numpy as np


class QuadConfirmationDetector:
    """Own detector/confirmers; retain the original quad on uncertain confirmation.

    A confirmer implements confirm(pixels, quad) -> bool | None and close().
    Both dependencies declare detector_families in metadata. Confirmation errors
    keep the original privacy mask and are exposed in stats and receipts.
    """

    def __init__(self, detector, confirmer, *, large_fraction=.5):
        if not math.isfinite(large_fraction) or not 0 < large_fraction <= 1:
            raise ValueError('Large-quad trigger must be finite and in (0, 1]')
        families = set()
        for adapter in (detector, confirmer):
            declared = adapter.metadata.get('detector_families')
            if not declared or not all(isinstance(family, str) for family in declared):
                raise ValueError('Confirmation adapters must declare detector families')
            families.update(declared)
        if 'apple-vision' in families:
            raise ValueError('Vision is judge only for quad confirmation')
        self.detector = detector
        self.confirmer = confirmer
        self.large_fraction = large_fraction
        self.metadata = {'name': 'quad-confirmation', 'detector_families': sorted(families),
                         'detector': detector.metadata, 'confirmer': confirmer.metadata,
                         'large_fraction': large_fraction,
                         'uncertain_policy': 'retain-original-quad'}
        self.counts = Counter(calls=0, ordinary=0, giant=0, confirmed=0, rejected=0,
                              uncertain=0, confirmation_errors=0)
        self.receipts = deque(maxlen=256)

    def detect_quads(self, pixels):
        height, width = pixels.shape[:2]
        self.counts['calls'] += 1
        kept = []
        for quad in self.detector.detect_quads(pixels):
            area = cv2.contourArea(cv2.convexHull(np.asarray(quad, np.float32)))
            if area < height * width * self.large_fraction:
                self.counts['ordinary'] += 1
                kept.append(quad)
                continue
            self.counts['giant'] += 1
            began = time.perf_counter()
            error = None
            try:
                decision = self.confirmer.confirm(pixels, quad)
                if decision is not True and decision is not False and decision is not None:
                    raise TypeError('Confirmer must return True, False or None')
            except Exception as failure:
                decision = None
                error = f'{type(failure).__name__}: {failure}'
                self.counts['confirmation_errors'] += 1
            wall = time.perf_counter() - began
            outcome = 'confirmed' if decision is True else 'rejected' if decision is False else 'uncertain'
            self.counts[outcome] += 1
            self.receipts.append({'call': self.counts['calls'], 'quad': np.asarray(quad).tolist(),
                                  'area_fraction': area / (height * width), 'outcome': outcome,
                                  'input_sha256': hashlib.sha256(pixels.tobytes()).hexdigest(),
                                  'diagnostic_wall_seconds': wall, 'error': error})
            if decision is not False:
                kept.append(quad)
        return kept

    @property
    def stats(self):
        return {**self.counts, 'receipt_capacity': self.receipts.maxlen,
                'recent_receipts': list(self.receipts), 'timing_scope': 'untimed confirmation call observations'}

    def close(self):
        try:
            self.detector.close()
        finally:
            self.confirmer.close()

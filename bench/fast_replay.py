"""Checked replay adapters for the FAST content-only comparison."""
import hashlib
import json

import numpy as np


class ReplayDetector:
    """Replay exact v6 detections at their original source sampling indices."""
    def __init__(self, rows, *, source_shape, fps, rate):
        self.rows = rows
        self.position = 0
        self.source_shape = source_shape
        expected = []
        bucket = -1
        for index in range(source_shape[2]):
            current = int(np.floor(index * rate / fps + 1e-9))
            if current > bucket:
                expected.append(index)
                bucket = current
        if [row['source_index'] for row in rows] != expected:
            raise ValueError('Reference v6 source schedule differs from requested policy')
        self.metadata = {'name': 'replayed-best-v6', 'detections_sha256': hashlib.sha256(
            json.dumps(rows, sort_keys=True).encode()).hexdigest(), 'source_indices': expected}

    def detect_quads(self, pixels):
        if self.position >= len(self.rows):
            raise RuntimeError('Reference detector replay exhausted')
        row = self.rows[self.position]
        if list(pixels.shape) != row['detector_input_shape']:
            raise ValueError('Reference detector input shape differs')
        self.position += 1
        scale = pixels.shape[1] / self.source_shape[1]
        return (np.asarray(row['quads'], dtype=float).reshape(-1, 4, 2) * scale).tolist()

    def verify_complete(self):
        if self.position != len(self.rows):
            raise RuntimeError('Reference detector replay did not consume every scheduled call')

    def close(self):
        pass


class UnionDetector:
    def __init__(self, *detectors):
        self.detectors = detectors
        self.metadata = {'name': 'union', 'members': [detector.metadata for detector in detectors]}

    def detect_quads(self, pixels):
        return [quad for detector in self.detectors for quad in detector.detect_quads(pixels)]

    def close(self):
        pass


class ReferenceInputs:
    """Reuse the baseline's three-judge input readings on byte-identical source video.

    run_file's grading seam calls input then output per frame. Verify each input
    pixel digest against an independent decode before reusing its raw reading.
    Output pixels always go to the actual three judges.
    """
    def __init__(self, judge, source, readings):
        self.judge, self.names = judge, judge.names
        self.readings = readings
        self.position = 0
        self.input_next = True
        import cv2
        capture = cv2.VideoCapture(str(source))
        self.hashes = []
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                self.hashes.append(hashlib.sha256(frame.tobytes()).hexdigest())
        finally:
            capture.release()
        if len(self.hashes) != len(readings):
            raise ValueError('Reference input OCR does not account for every source frame')

    def read(self, pixels):
        if self.position >= len(self.hashes):
            raise RuntimeError('Reference input OCR replay exhausted')
        if self.input_next:
            if hashlib.sha256(pixels.tobytes()).hexdigest() != self.hashes[self.position]:
                raise ValueError('Reference input OCR pixel identity mismatch')
            self.input_next = False
            return self.readings[self.position]
        result = self.judge.read(pixels)
        self.input_next = True
        self.position += 1
        return result

    def verify_complete(self):
        if not self.input_next or self.position != len(self.hashes):
            raise RuntimeError('Reference input OCR replay incomplete')


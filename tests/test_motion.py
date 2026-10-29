"""Synthetic geometry contracts at the MotionHistory interface."""
import unittest

import cv2
import numpy as np

from shield.motion import MotionHistory


def scene(seed=7, width=640, height=400):
    random = np.random.default_rng(seed)
    image = np.full((height, width, 3), 35, np.uint8)
    for _ in range(180):
        x, y = random.integers(18, [width - 18, height - 18])
        radius = int(random.integers(3, 9))
        shade = int(random.integers(80, 255))
        cv2.circle(image, (int(x), int(y)), radius, (shade, shade, shade), -1)
    cv2.putText(image, 'SYNTHETIC 1234', (50, height // 2), cv2.FONT_HERSHEY_SIMPLEX, .9, (240, 240, 240), 2)
    return image


class MotionGeometry(unittest.TestCase):
    def test_batch_projects_all_quads_and_empty_receipts_still_require_a_connected_path(self):
        frame = scene()
        moved = cv2.warpAffine(frame, np.float32([[1, 0, 14], [0, 1, -8]]), (640, 400))
        history = MotionHistory(max_frames=3, analysis_width=320)
        history.add(0, frame)
        history.add(1, moved)
        quads = [[[100, 70], [300, 70], [300, 190], [100, 190]],
                 [[-30, 20], [50, 20], [50, 45], [-30, 45]]]
        original = np.asarray(quads).copy()
        expected = original + [14, -8]
        projected = history.project_many(quads, 0, 1)
        np.testing.assert_allclose(projected, expected, atol=1.5)
        np.testing.assert_allclose(history.project_many(projected, 1, 0), original, atol=1e-6)
        np.testing.assert_array_equal(quads, original)
        projected[0][0][0] = -9999
        np.testing.assert_allclose(history.project_many(quads, 0, 1), expected, atol=1.5)
        self.assertEqual(history.project_many([], 0, 1), [])
        self.assertIsNone(history.project_many([], 0, 99))
        history.add(2, scene(seed=777))
        self.assertIsNone(history.project_many([], 0, 2))
        self.assertIsNone(history.project_many(quads, 0, 2))
        history.add(3, scene(seed=777))
        self.assertIsNone(history.project_many([], 0, 3))
        self.assertEqual(history.project_many([], 2, 3), [])
        with self.assertRaises(ValueError):
            history.project_many(quads + [[[0, 0], [1, 0], [float('nan'), 1], [0, 1]]], 2, 3)

    def test_composes_translation_and_projects_back_in_original_pixels(self):
        frame = scene()
        history = MotionHistory(analysis_width=320)
        history.add(0, frame)
        history.add(1, cv2.warpAffine(frame, np.float32([[1, 0, 14], [0, 1, -8]]), (640, 400)))
        history.add(2, cv2.warpAffine(frame, np.float32([[1, 0, 24], [0, 1, -2]]), (640, 400)))
        quad = [[100, 70], [300, 70], [300, 190], [100, 190]]
        expected = [[124, 68], [324, 68], [324, 188], [124, 188]]
        np.testing.assert_allclose(history.project(quad, 0, 2), expected, atol=1.5)
        np.testing.assert_allclose(history.project(expected, 2, 0), quad, atol=1.5)
        self.assertTrue(history.diagnostics(2)['valid'])

    def test_perspective_preserves_vertex_order_across_frame_resolutions(self):
        frame = scene(seed=11, width=800, height=480)
        perspective = np.array([[1.02, .08, 18], [-.035, .97, 14], [.00018, -.00011, 1]])
        ground_truth = np.diag([1.25, 1.25, 1.0]) @ perspective
        target = cv2.warpPerspective(frame, ground_truth, (1000, 600))
        quad = np.array([[150, 100], [470, 100], [470, 300], [150, 300]], dtype=float)
        homogeneous = np.column_stack([quad, np.ones(4)]) @ ground_truth.T
        expected = homogeneous[:, :2] / homogeneous[:, 2:]
        history = MotionHistory(analysis_width=320)
        history.add(10, frame)
        history.add(11, target)
        projected = history.project(quad.tolist(), 10, 11)
        self.assertIsNotNone(projected)
        np.testing.assert_allclose(projected, expected, atol=3.0)
        np.testing.assert_allclose(history.project(expected.tolist(), 11, 10), quad, atol=3.0)

    def test_cut_and_texture_guards_do_not_fabricate_valid_motion(self):
        quad = [[100, 70], [300, 70], [300, 190], [100, 190]]
        history = MotionHistory()
        history.add(0, scene(seed=7))
        replacement = scene(seed=777)
        history.add(1, replacement)
        self.assertIsNone(history.project(quad, 0, 1))
        self.assertFalse(history.diagnostics(1)['valid'])
        self.assertTrue(history.diagnostics(1)['burst'])
        self.assertEqual(history.diagnostics(1)['confidence'], 0.0)
        history.add(2, replacement.copy())
        self.assertIsNone(history.project(quad, 0, 2))
        np.testing.assert_allclose(history.project(quad, 1, 2), quad, atol=1e-6)
        self.assertTrue(history.diagnostics(2)['valid'])

        empty = MotionHistory(mode='phase')
        empty.add(0, np.zeros((400, 640, 3), np.uint8))
        empty.add(1, np.zeros((400, 640, 3), np.uint8))
        self.assertIsNone(empty.project(quad, 0, 1))
        self.assertFalse(empty.diagnostics(1)['valid'])
        self.assertEqual(empty.diagnostics(1)['confidence'], 0.0)
        self.assertEqual(empty.project(quad, 1, 1), quad)

        phase = MotionHistory(mode='phase')
        phase.add(0, replacement)
        phase.add(1, cv2.warpAffine(replacement, np.float32([[1, 0, 8], [0, 1, 2]]), (640, 400)))
        expected = np.asarray(quad) + [8, 2]
        np.testing.assert_allclose(phase.project(quad, 0, 1), expected, atol=1.5)

    def test_configured_phase_threshold_can_track_occlusion_without_accepting_a_cut(self):
        frame = scene()
        moved = cv2.warpAffine(frame, np.float32([[1, 0, 8], [0, 1, 2]]), (640, 400))
        moved[:, :512] = 35
        quad = [[540, 70], [610, 70], [610, 190], [540, 190]]
        strict = MotionHistory(mode='phase')
        strict.add(0, frame)
        strict.add(1, moved)
        self.assertIsNone(strict.project(quad, 0, 1))
        tuned = MotionHistory(mode='phase', phase_min_response=.2)
        tuned.add(0, frame)
        tuned.add(1, moved)
        np.testing.assert_allclose(tuned.project(quad, 0, 1), np.asarray(quad) + [8, 2], atol=1.5)
        tuned.add(2, scene(seed=777))
        self.assertIsNone(tuned.project(quad, 1, 2))
        for value in [float('nan'), -.1, 1.1]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                MotionHistory(mode='phase', phase_min_response=value)

    def test_missing_and_evicted_frames_cannot_reuse_a_transform(self):
        frame = scene()
        quad = [[100, 70], [300, 70], [300, 190], [100, 190]]
        history = MotionHistory(max_frames=3)
        for index in range(5):
            moved = cv2.warpAffine(frame, np.float32([[1, 0, 4 * index], [0, 1, 2 * index]]), (640, 400))
            history.add(index, moved)
        self.assertIsNone(history.project(quad, 0, 4))
        self.assertFalse(history.diagnostics(0)['valid'])
        self.assertIsNone(history.project(quad, 2, 99))
        expected = np.asarray(quad) + [8, 4]
        np.testing.assert_allclose(history.project(quad, 2, 4), expected, atol=1.5)

        gap = MotionHistory()
        gap.add(10, frame)
        gap.add(12, frame.copy())
        self.assertIsNone(gap.project(quad, 10, 12))
        self.assertFalse(gap.diagnostics(12)['valid'])
        gap.add(13, frame.copy())
        self.assertIsNone(gap.project(quad, 10, 13))
        np.testing.assert_allclose(gap.project(quad, 12, 13), quad, atol=1e-6)

"""Synthetic raster contracts; these tests establish no OCR/quality result."""
import unittest

import cv2
import numpy as np

from shield.mask_precision import PaddingBudgetRenderer


class PaddingBudgetRendering(unittest.TestCase):
    def test_budget_counts_overlapping_union_and_tightens_padding_only(self):
        frame = np.full((100, 100, 3), 170, np.uint8)
        # Bare union: [20..50] x [40..60] = 651 pixels. The two padded
        # polygons individually fit 1200 pixels, but their union does not.
        quads = [[[20, 40], [40, 40], [40, 60], [20, 60]],
                 [[30, 40], [50, 40], [50, 60], [30, 60]]]
        renderer = PaddingBudgetRenderer(max_mask_fraction=.12)
        result = renderer.render(frame, iter(quads), 'LIVE', 2)
        self.assertTrue(result.budget.satisfied)
        self.assertLessEqual(np.count_nonzero(result.mask), 1200)
        self.assertGreater(np.count_nonzero(result.mask), 651)
        self.assertTrue((result.mask[40:61, 20:51] == 255).all())
        self.assertGreater(result.budget.padding_scale, 0)
        self.assertLess(result.budget.padding_scale, 1)
        np.testing.assert_array_equal(result.pixels[result.mask == 0], frame[result.mask == 0])
        self.assertTrue((result.pixels[result.mask > 0] == 0).all())
        duplicate = renderer.render(frame, [quads[0]] * 4, 'LIVE', 4)
        self.assertEqual(duplicate.budget.padding_scale, 1)
        self.assertTrue(duplicate.budget.satisfied)
        self.assertEqual(np.count_nonzero(duplicate.mask), 33 * 33)

    def test_bare_union_over_budget_is_retained_and_reported_as_failure(self):
        frame = np.full((100, 100, 3), 190, np.uint8)
        renderer = PaddingBudgetRenderer(max_mask_fraction=.12)
        for quad, covered in [
            ([[20, 30], [80, 30], [80, 50], [20, 50]], 61 * 21),
            ([[0, 0], [99, 0], [99, 99], [0, 99]], 10000),
        ]:
            with self.subTest(quad=quad):
                result = renderer.render(frame, [quad], 'LIVE', 1)
                self.assertFalse(result.budget.satisfied)
                self.assertEqual(result.budget.minimum_pixels, covered)
                self.assertEqual(result.budget.covered_pixels, covered)
                self.assertEqual(np.count_nonzero(result.mask), covered)
                self.assertEqual(result.budget.padding_scale, 0)
                self.assertFalse(result.protected)
                self.assertTrue((result.pixels[result.mask > 0] == 0).all())

    def test_rotated_skewed_and_clipped_quads_keep_every_bare_raster_pixel(self):
        frame = np.full((100, 140, 3), 210, np.uint8)
        quads = [np.array(q, np.int32) for q in [
            [[30, 40], [50, 20], [100, 70], [80, 90]],
            [[20, 30], [100, 45], [80, 65], [25, 50]],
            [[-5, 20], [25, 10], [40, 40], [0, 60]],
        ]]
        for quad in quads:
            with self.subTest(quad=quad.tolist()):
                bare = np.zeros(frame.shape[:2], np.uint8)
                cv2.fillConvexPoly(bare, quad, 255)
                result = PaddingBudgetRenderer(max_mask_fraction=.25).render(frame, [quad], 'LIVE', 1)
                self.assertTrue(result.budget.satisfied)
                self.assertLessEqual(np.count_nonzero(result.mask), 3500)
                self.assertTrue((result.mask[bare > 0] == 255).all())
                self.assertTrue((result.pixels[bare > 0] == 0).all())
                self.assertEqual(int(result.mask[0, 139]), 0)
                retained = result.mask.copy()
                later = PaddingBudgetRenderer(max_mask_fraction=0).render(frame, [], 'LIVE', 0)
                later.mask[:] = 255
                np.testing.assert_array_equal(result.mask, retained)

    def test_budget_never_changes_protection_or_accepts_invalid_geometry(self):
        frame = np.arange(80 * 120 * 3, dtype=np.uint8).reshape(80, 120, 3)
        renderer = PaddingBudgetRenderer(max_mask_fraction=0, slate_after=.5)
        for state, duration, slate in [('PROTECT', .4, False), ('PROTECT', .5, True), ('HOLD', 0, True)]:
            with self.subTest(state=state, duration=duration):
                result = renderer.render(frame, None, state, 0, duration)
                self.assertTrue(result.protected)
                self.assertEqual(result.slate, slate)
                self.assertIsNone(result.budget)
                self.assertTrue((result.mask == 255).all())
                self.assertTrue((np.ptp(result.pixels, axis=(0, 1)) == 0).all())
        with self.assertRaises(ValueError):
            renderer.render(frame, [[[0, 0], [1, 1], [2, 2], [3, 3]]], 'LIVE', 1)
        for fraction in (True, -.1, 1.1, float('nan'), float('inf')):
            with self.subTest(fraction=fraction), self.assertRaises(ValueError):
                PaddingBudgetRenderer(max_mask_fraction=fraction)

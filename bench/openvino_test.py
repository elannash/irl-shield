"""Synthetic checks of the OpenVINO lane's public comparison interface."""
import unittest

from bench.openvino_parity import compare_boxes


class BoxParityTests(unittest.TestCase):
    def test_lost_detection_fails_even_when_remaining_box_is_identical(self):
        result = compare_boxes([[0, 0, 20, 10], [40, 0, 60, 10]], [[0, 0, 20, 10]])
        self.assertFalse(result['pass'])
        self.assertEqual(result['unmatched_reference'], [1])

    def test_reordered_boxes_match_but_shift_and_duplicate_do_not(self):
        reference = [[0, 0, 100, 50], [200, 0, 300, 50]]
        result = compare_boxes(reference, [[201, 0, 301, 50], [0, 0, 100, 50]])
        self.assertTrue(result['pass'])
        self.assertAlmostEqual(result['matches'][0]['iou'], 99 / 101)
        self.assertEqual(result['matches'][0]['max_coordinate_error'], 1)
        self.assertFalse(compare_boxes(reference, [reference[0], reference[0]])['pass'])
        self.assertFalse(compare_boxes(reference, [[3, 0, 103, 50], reference[1]])['pass'])

    def test_empty_results_are_not_nonempty_parity_evidence(self):
        self.assertFalse(compare_boxes([], [])['nonempty_evidence'])

    def test_invalid_geometry_is_an_error(self):
        for box in ([0, 0, 0, 1], [0, float('nan'), 2, 2]):
            with self.assertRaises(ValueError):
                compare_boxes([box], [])


class ModelPreprocessingTests(unittest.TestCase):
    def test_artifact_normalization_is_used_instead_of_rapidocr_defaults(self):
        import numpy as np
        from bench.openvino_detector import preprocess_for
        pixels = np.full((32, 32, 3), [0, 128, 255], dtype=np.uint8)
        tensor = preprocess_for('ppocr-v6-tiny', 32)(pixels)
        self.assertEqual(tensor.shape, (1, 3, 32, 32))
        self.assertEqual(tensor.dtype, np.float32)
        np.testing.assert_allclose(tensor[0, :, 0, 0], [-2.117904, .20518208, 2.64], atol=1e-6)


if __name__ == '__main__':
    unittest.main()

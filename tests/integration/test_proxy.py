"""Synthetic label proxy rejects an unmasked generator label, not mask outlines."""
import unittest
import numpy as np
from native import label_edges
from relay.fixture import decorate


class LabelProxy(unittest.TestCase):
    def test_unmasked_labels_fail_and_masked_label_interior_passes(self):
        for index in (0, 150):
            with self.subTest(index=index):
                pixels = np.full((720, 1280, 3), 150, np.uint8)
                decorate(pixels, index, 0)
                self.assertGreaterEqual(label_edges(pixels), 60)
                pixels[310:390, 300:675] = 0
                self.assertLess(label_edges(pixels), 60)

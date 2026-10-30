import unittest
import numpy as np


class LightingVariants(unittest.TestCase):
    def test_photometric_variants_keep_geometry_and_original_pixels(self):
        from bench.w1.lighting import transform
        pixels=np.tile(np.array([0,30,255],np.uint8)[None,:,None],(3,1,3))
        saved=pixels.copy()
        self.assertEqual(transform(pixels,"dark")[1,:,0].tolist(),[0,5,255])
        self.assertEqual(transform(pixels,"backlit")[1,:,0].tolist(),[30,78,255])
        np.testing.assert_array_equal(pixels,saved)
        impulse=np.zeros((3,11,3),np.uint8);impulse[:,5]=27
        self.assertEqual(transform(impulse,"motion-blur")[1,:,0].tolist(),[0]+[3]*9+[0])
        with self.assertRaises(ValueError): transform(pixels,"unknown")

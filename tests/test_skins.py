import json
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from shield.skins import MaskRegion, SkinPainter, cell_extents
from shield.skins.paint import SKINS


class SkinPrivacy(unittest.TestCase):
    def test_frosted_exact_means_erase_adversarial_text_and_irregular_seams(self):
        source = np.full((160, 320, 3), 230, np.uint8)
        cv2.putText(source, '1842 ALDER', (8, 67), cv2.FONT_HERSHEY_SIMPLEX,
                    1.1, (0, 0, 0), 3, cv2.LINE_8)
        source[80:144, 8:296:2] = 0
        raster = np.zeros((128, 288), np.uint8)
        cv2.fillPoly(raster, [np.array([[0, 0], [287, 10], [235, 82],
                                      [287, 127], [10, 120], [31, 66]])], 255)
        regions = [MaskRegion(8, 8, raster, 24)]
        shuffled = source.copy()
        crop = shuffled[8:136, 8:296]
        cells = cell_extents(288, 128, 24)
        rng = np.random.default_rng(823)
        for left, top, right, bottom in cells:
            before = crop[top:bottom, left:right].copy()
            values = before.reshape(-1, 3)
            crop[top:bottom, left:right] = values[rng.permutation(len(values))].reshape(before.shape)
            np.testing.assert_array_equal(before.sum(axis=(0, 1)), crop[top:bottom, left:right].sum(axis=(0, 1)))
        self.assertFalse(np.array_equal(source, shuffled))
        for amount in (0, .65):
            painter = SkinPainter(desaturation=amount)
            a, b = painter.paint(source, regions), painter.paint(shuffled, regions)
            np.testing.assert_array_equal(a.pixels[a.mask != 0], b.pixels[b.mask != 0])
            self.assertTrue((a.alpha[a.mask != 0] == 255).all())
            np.testing.assert_array_equal(a.mask[8:136, 8:296], raster)
            np.testing.assert_array_equal(a.pixels[a.mask == 0], source[a.mask == 0])
            self.assertGreater(float(a.pixels[a.mask != 0].std()), 0)
        # A change outside all averaging rectangles cannot affect Frosted.
        outside = source.copy()
        outside[:8] = 0
        a, b = SkinPainter().paint(source, regions), SkinPainter().paint(outside, regions)
        np.testing.assert_array_equal(a.pixels[a.mask != 0], b.pixels[b.mask != 0])

    def test_cell_bounds_have_no_terminal_slivers_or_unbounded_read_extent(self):
        self.assertEqual(cell_extents(192, 64, 20),
                         [(0, 0, 48, 64), (48, 0, 96, 64),
                          (96, 0, 144, 64), (144, 0, 192, 64)])
        self.assertEqual(cell_extents(7, 3, 4), [(0, 0, 7, 3)])
        for width, height, text in [(199, 101, 17), (1, 720, 80), (1280, 720, 24)]:
            counts = np.zeros((height, width), np.uint8)
            cells = cell_extents(width, height, text)
            minimum = max(24, int(np.ceil(1.5 * text)), int(np.ceil(max(width, height) / 4)))
            for left, top, right, bottom in cells:
                self.assertGreaterEqual(right - left, min(width, minimum))
                self.assertGreaterEqual(bottom - top, min(height, minimum))
                counts[top:bottom, left:right] += 1
            self.assertTrue((counts == 1).all())
            self.assertLessEqual(len({left for left, _, _, _ in cells}), 4)
            self.assertLessEqual(len({top for _, top, _, _ in cells}), 4)

    def test_every_swap_keeps_exact_union_and_opaque_source_independent_skins(self):
        rng = np.random.default_rng(19)
        source, other = [rng.integers(0, 256, (100, 160, 3), np.uint8) for _ in range(2)]
        raster = np.zeros((56, 96), np.uint8)
        cv2.fillPoly(raster, [np.array([[0, 0], [95, 13], [70, 55], [3, 40]])], 255)
        second = np.full((18, 40), 255, np.uint8)
        regions = [MaskRegion(12, 8, raster, 18), MaskRegion(60, 45, second, 12)]
        expected = np.zeros((100, 160), np.uint8)
        expected[8:64, 12:108] = raster
        expected[45:63, 60:100] = 255
        original = source.copy()
        painter = SkinPainter()
        for skin in (*SKINS, *reversed(SKINS)):
            with self.subTest(skin=skin):
                a, b = painter.paint(source, regions, skin=skin), painter.paint(other, regions, skin=skin)
                self.assertEqual(a.skin, skin)
                self.assertIsNone(a.fallback_reason)
                np.testing.assert_array_equal(a.mask, expected)
                np.testing.assert_array_equal(a.alpha, expected)
                np.testing.assert_array_equal(a.pixels[expected == 0], source[expected == 0])
                if skin != 'frosted':
                    np.testing.assert_array_equal(a.pixels[expected != 0], b.pixels[expected != 0])
        np.testing.assert_array_equal(source, original)

    def test_pattern_cache_survives_file_removal_and_missing_assets_fail_closed(self):
        source = np.full((16, 32, 3), 255, np.uint8)
        region = MaskRegion(0, 0, np.full((16, 32), 255, np.uint8), 6)
        with tempfile.TemporaryDirectory() as directory:
            painter = SkinPainter(assets=directory)
            result = painter.paint(source, [region], skin='petals')
            self.assertEqual(result.skin, 'bar')
            self.assertIsNotNone(result.fallback_reason)
            self.assertTrue((result.pixels == 0).all())
            import hashlib
            path = Path(directory) / 'petals.png'
            cv2.imwrite(str(path), np.full((8, 8, 3), (71, 122, 194), np.uint8))
            manifest = {'assets': [{'name': 'petals', 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}]}
            (Path(directory) / 'attribution.json').write_text(json.dumps(manifest))
            painter = SkinPainter(assets=directory)
            path.unlink()
            result = painter.paint(source, [region], skin='petals')
            self.assertEqual(result.skin, 'petals')
            self.assertTrue((result.pixels == (71, 122, 194)).all())
            path.write_bytes(b'corrupt')
            result = SkinPainter(assets=directory).paint(source, [region], skin='petals')
            self.assertEqual(result.skin, 'bar')
            self.assertTrue((result.pixels == 0).all())

    def test_holds_never_sample_source_and_bad_inputs_raise_before_returning_pixels(self):
        rng = np.random.default_rng(71)
        a, b = [rng.integers(0, 256, (32, 64, 3), np.uint8) for _ in range(2)]
        painter = SkinPainter()
        for state in ('HOLD', 'PROTECT'):
            for skin in SKINS:
                first = painter.paint(a, [object()], state=state, skin=skin)
                second = painter.paint(b, [], state=state, skin=skin)
                np.testing.assert_array_equal(first.pixels, second.pixels)
                self.assertTrue((first.mask == 255).all())
                self.assertTrue((first.alpha == 255).all())
        for region in [MaskRegion(-1, 0, np.full((4, 4), 255, np.uint8), 8),
                       MaskRegion(0, 0, np.full((4, 4), 254, np.uint8), 8),
                       MaskRegion(0, 0, np.ones((40, 4), np.uint8), 8),
                       MaskRegion(0, 0, np.full((4, 4), 255, np.uint8), float('nan'))]:
            with self.assertRaises(ValueError):
                painter.paint(a, [region])
        with self.assertRaises(ValueError):
            painter.paint(a, [], skin='../../secret')


if __name__ == '__main__':
    unittest.main()

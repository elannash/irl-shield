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
            self.assertTrue((a.mask[8:136, 8:296][raster != 0] == 255).all())
            np.testing.assert_array_equal(a.pixels[a.alpha == 0], source[a.alpha == 0])
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

    def test_every_swap_keeps_original_union_and_opaque_source_independent_skins(self):
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
                self.assertTrue((a.mask[expected != 0] == 255).all())
                self.assertTrue((a.alpha[a.mask != 0] == 255).all())
                self.assertTrue(((a.alpha > 0) & (a.alpha < 255)).any())
                np.testing.assert_array_equal(a.pixels[a.alpha == 0], source[a.alpha == 0])
                if skin != 'frosted':
                    np.testing.assert_array_equal(a.pixels[a.mask != 0], b.pixels[a.mask != 0])
        np.testing.assert_array_equal(source, original)

    def test_removed_skins_are_rejected_by_the_paint_boundary(self):
        frame = np.full((24, 48, 3), 211, np.uint8)
        for skin in ('petals', 'ripple', 'confetti', 'cloud'):
            with self.subTest(skin=skin), self.assertRaises(ValueError):
                SkinPainter().paint(frame, [], skin=skin)

    def test_rectangles_round_outward_and_feather_only_beyond_opaque_paint(self):
        source = np.full((140, 200, 3), 255, np.uint8)
        region = MaskRegion(50, 40, np.full((40, 80), 255, np.uint8), 18)
        for skin in SKINS:
            with self.subTest(skin=skin):
                result = SkinPainter().paint(source, [region], skin=skin)
                # r=12, ceil(r*(1-1/sqrt(2)))=4. The half-open
                # expanded box is [46,134) x [36,84), before feather.
                self.assertEqual(result.mask[60, 46], 255)
                self.assertEqual(result.mask[36, 90], 255)
                self.assertEqual(result.mask[36, 46], 0)
                self.assertTrue((result.mask[40:80, 50:130] == 255).all())
                self.assertTrue((result.alpha[result.mask != 0] == 255).all())
                tail = result.alpha[60, 40:47].astype(int)
                self.assertEqual(tail[0], 0)
                self.assertEqual(tail[-1], 255)
                self.assertTrue((np.diff(tail) > 0).all())
                self.assertTrue((result.alpha[result.mask == 0] < 255).all())
                np.testing.assert_array_equal(result.pixels[result.alpha == 0], source[result.alpha == 0])
                if skin == 'bar':
                    self.assertTrue((result.pixels[result.mask != 0] == 0).all())
                    self.assertTrue(((result.pixels[60, 41:46] > 0)
                                     & (result.pixels[60, 41:46] < 255)).all())

        # The optimized uncached corner stencil must match the original
        # full-raster precise EDT, for every radius regime and clipped edge.
        frame = np.full((140, 350, 3), 211, np.uint8)
        for height in range(1, 91):
            width = 3 * height + 1
            left = (0, 13, 350 - width)[height % 3]
            top = (0, 7, 140 - height)[height % 3]
            raster = np.full((height, width), 255, np.uint8)
            radius = min(24., max(6., .3 * height))
            grow = int(np.ceil(max(radius * (1 - 1 / np.sqrt(2)), (2 * radius - height) / 2)))
            l, t = max(0, left-grow-6), max(0, top-grow-6)
            r, b = min(350, left+width+grow+6), min(140, top+height+grow+6)
            x = np.arange(l, r, dtype=np.float32) + .5
            y = np.arange(t, b, dtype=np.float32) + .5
            dx = np.maximum(np.maximum(left-grow+radius-x, x-(left+width+grow-radius)), 0)
            dy = np.maximum(np.maximum(top-grow+radius-y, y-(top+height+grow-radius)), 0)
            expected_mask = ((dy[:, None] ** 2 + dx ** 2) <= radius ** 2).astype(np.uint8) * 255
            expected_mask[top-t:top-t+height, left-l:left-l+width] = 255
            distance = cv2.distanceTransform(255-expected_mask, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
            amount = np.clip(distance / 6, 0, 1)
            expected_alpha = np.rint(255 * (1 - amount * amount * (3 - 2 * amount))).astype(np.uint8)
            result = SkinPainter().paint(frame, [MaskRegion(left, top, raster, 12)], skin='bar')
            with self.subTest(precise_parity_height=height, left=left, top=top):
                np.testing.assert_array_equal(result.mask[t:b, l:r], expected_mask)
                np.testing.assert_array_equal(result.alpha[t:b, l:r], expected_alpha)

    def test_tiny_and_frame_edge_rectangles_keep_every_original_corner_painted(self):
        source = np.full((80, 120, 3), 233, np.uint8)
        for left, top, width, height in [(0, 0, 1, 1), (119, 79, 1, 1),
                                         (0, 13, 2, 35), (40, 0, 45, 2),
                                         (100, 60, 20, 20), (0, 0, 120, 80)]:
            raster = np.full((height, width), 255, np.uint8)
            for skin in SKINS:
                with self.subTest(box=(left, top, width, height), skin=skin):
                    result = SkinPainter().paint(source, [MaskRegion(left, top, raster, 12)], skin=skin)
                    core = np.s_[top:top+height, left:left+width]
                    self.assertTrue((result.mask[core] == 255).all())
                    self.assertTrue((result.alpha[core] == 255).all())
                    self.assertFalse(np.array_equal(result.pixels[core], source[core]))
                    if skin == 'bar':
                        self.assertTrue((result.pixels[result.mask != 0] == 0).all())
        # r=6 cannot fit inside a 1px original plus the usual 2px
        # expansion: grow by 6px per side, then clip at the frame edge.
        result = SkinPainter().paint(source, [MaskRegion(0, 0, np.full((1, 1), 255, np.uint8), 1)], skin='bar')
        self.assertEqual(result.mask[0, 6], 255)
        self.assertEqual(result.alpha[0, 0], 255)

    def test_irregular_dilation_preserves_concavities_islands_and_clipped_pixels(self):
        raster = np.zeros((30, 40), np.uint8)
        raster[0, :] = 255
        raster[:, 0] = 255
        raster[15, 15] = 255
        raster[-1, -1] = 255
        original = raster.copy()
        source = np.full((60, 80, 3), 253, np.uint8)
        for skin in SKINS:
            result = SkinPainter().paint(source, [MaskRegion(0, 0, raster, 10)], skin=skin)
            self.assertTrue((result.mask[:30, :40][raster != 0] == 255).all())
            self.assertTrue((result.alpha[result.mask != 0] == 255).all())
            self.assertEqual(result.mask[15, 17], 255)  # original isolated pixel grows
            self.assertEqual(result.mask[15, 25], 0)    # hole is not a filled bbox
            self.assertEqual(result.mask[29, 39], 255)
            if skin == 'bar':
                self.assertTrue((result.pixels[result.mask != 0] == 0).all())
        np.testing.assert_array_equal(raster, original)
        empty = SkinPainter().paint(source, [MaskRegion(0, 0, np.zeros((3, 5), np.uint8), 1)])
        self.assertFalse(empty.alpha.any())
        np.testing.assert_array_equal(empty.pixels, source)

    def test_overlap_feathers_never_sample_source_under_global_opaque_union(self):
        source = np.full((110, 160, 3), 80, np.uint8)
        regions = [MaskRegion(20, 25, np.full((40, 40), 255, np.uint8), 16),
                   MaskRegion(63, 25, np.full((40, 40), 255, np.uint8), 16)]
        irregular = np.zeros((30, 30), np.uint8)
        irregular[0:4] = 255
        irregular[:, 10:14] = 255
        regions.append(MaskRegion(48, 58, irregular, 12))
        other = np.full_like(source, 240)
        original_union = np.zeros(source.shape[:2], bool)
        for region in regions:
            rh, rw = region.raster.shape
            # All original averaging rectangles must match, including holes.
            other[region.top:region.top+rh, region.left:region.left+rw] = 80
            original_union[region.top:region.top+rh, region.left:region.left+rw] |= region.raster != 0
        for order in (regions, list(reversed(regions))):
            for skin in SKINS:
                with self.subTest(skin=skin, reverse=order is not regions):
                    painter = SkinPainter()
                    a, b = [painter.paint(frame, order, skin=skin) for frame in (source, other)]
                    self.assertTrue((a.mask[original_union] == 255).all())
                    self.assertTrue((a.alpha[a.mask != 0] == 255).all())
                    np.testing.assert_array_equal(a.pixels[a.mask != 0], b.pixels[a.mask != 0])
                    if skin == 'bar':
                        self.assertTrue((a.pixels[a.mask != 0] == 0).all())

    def test_shared_irregular_fields_preserve_exact_individual_geometry(self):
        # Merging dilation/EDT work must retain individual raster boundaries,
        # even across radii, disjoint groups, holes and clipped frame edges.
        frame = np.full((100, 180, 3), 229, np.uint8)
        a = np.zeros((23, 37), np.uint8)
        cv2.fillConvexPoly(a, np.array([[0, 2], [34, 0], [36, 20], [3, 22]], np.int32), 255)
        b = np.zeros((30, 50), np.uint8)
        b[0:3] = 255
        b[:, 0:3] = 255
        b[15, 20] = b[-1, -1] = 255
        c = np.zeros((10, 18), np.uint8)
        c[2:8, 1:5] = 255
        c[7, 4:15] = 255
        regions = [MaskRegion(0, 0, a, 9), MaskRegion(16, 8, a.copy(), 11),
                   MaskRegion(130, 70, b, 14), MaskRegion(21, 43, b, 14),
                   MaskRegion(11, 27, c, 6),
                   MaskRegion(60, 0, np.zeros((4, 7), np.uint8), 2)]
        expected_mask = np.zeros(frame.shape[:2], np.uint8)
        expected_alpha = np.zeros_like(expected_mask)
        for region in regions:
            if not region.raster.any():
                continue
            height, width = region.raster.shape
            radius = min(24., max(6., .3 * min(height, width)))
            grow = int(np.ceil(max(radius * (1 - 1 / np.sqrt(2)),
                                   (2 * radius - min(height, width)) / 2)))
            left, top = max(0, region.left-grow-6), max(0, region.top-grow-6)
            right = min(180, region.left+width+grow+6)
            bottom = min(100, region.top+height+grow+6)
            original = np.zeros((bottom-top, right-left), np.uint8)
            x, y = region.left-left, region.top-top
            original[y:y+height, x:x+width] = region.raster
            dy, dx = np.ogrid[-grow:grow+1, -grow:grow+1]
            kernel = (dx*dx + dy*dy <= grow*grow).astype(np.uint8)
            opaque = cv2.dilate(original, kernel, borderType=cv2.BORDER_CONSTANT, borderValue=0)
            distance = cv2.distanceTransform(255-opaque, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
            amount = np.clip(distance / 6, 0, 1)
            local_alpha = np.rint(255 * (1 - amount*amount*(3-2*amount))).astype(np.uint8)
            area = np.s_[top:bottom, left:right]
            np.maximum(expected_mask[area], opaque, out=expected_mask[area])
            np.maximum(expected_alpha[area], local_alpha, out=expected_alpha[area])
        for order in (regions, list(reversed(regions))):
            for skin in SKINS:
                with self.subTest(skin=skin, reverse=order is not regions):
                    result = SkinPainter().paint(frame, order, skin=skin)
                    np.testing.assert_array_equal(result.mask, expected_mask,
                        err_msg='Shared irregular union must retain every individual dilation pixel')
                    np.testing.assert_array_equal(result.alpha, expected_alpha)
                    self.assertTrue((result.alpha[result.mask != 0] == 255).all())
                    np.testing.assert_array_equal(result.pixels[result.alpha == 0], frame[result.alpha == 0])

    def test_material_ownership_keeps_ties_extensions_and_original_order(self):
        # These worked pixels guard composition, independently of the new
        # owner-map implementation and its material visibility optimization.
        source = np.full((100, 140, 3), 230, np.uint8)
        source[25:65, 20:60] = 60
        source[25:65, 71:111] = 180
        left = MaskRegion(20, 25, np.full((40, 40), 255, np.uint8), 18)
        right = MaskRegion(71, 25, np.full((40, 40), 255, np.uint8), 18)
        # At (65,45), both opaque envelopes are two pixels away: alpha189.
        # Replicated edge material uses grain at local (39,20)/(0,20).
        for order, expected in [([left, right], 191), ([right, left], 105)]:
            with self.subTest(equal_alpha_order=order[0].left):
                result = SkinPainter().paint(source, order)
                self.assertEqual(int(result.alpha[45, 65]), 189)
                np.testing.assert_array_equal(result.pixels[45, 65], [expected] * 3,
                    err_msg='Equal-alpha feather material must follow caller order')

        # Smaller originals B/C replace every original A pixel. A's larger
        # rounded envelope still owns (59,16), so A material cannot be skipped.
        source[:] = 100
        a = MaskRegion(20, 20, np.full((40, 80), 255, np.uint8), 18)
        b = MaskRegion(20, 20, np.full((40, 40), 255, np.uint8), 18)
        c = MaskRegion(60, 20, np.full((40, 40), 255, np.uint8), 18)
        for skin, expected in [('frosted', [101, 101, 101]), ('signed', [24, 21, 18])]:
            with self.subTest(visible_extension=skin):
                result = SkinPainter().paint(source, [a, b, c], skin=skin)
                self.assertEqual(int(result.mask[16, 59]), 255)
                self.assertEqual(int(result.alpha[16, 59]), 255)
                np.testing.assert_array_equal(result.pixels[16, 59], expected,
                    err_msg='Visible extension must retain material when all originals are overwritten')

        # At (60,40), A's Signed symbol overlaps B's original raster at its
        # plain left edge. An irregular B still wins or loses in caller order.
        irregular = np.full((40, 40), 255, np.uint8)
        irregular[:3, :3] = 0
        b = MaskRegion(60, 20, irregular, 18)
        for order, expected in [([a, b], [24, 21, 18]), ([b, a], [151, 148, 143])]:
            with self.subTest(mixed_signed_order=order[0].left):
                result = SkinPainter().paint(source, order, skin='signed')
                self.assertEqual(int(result.alpha[40, 60]), 255)
                np.testing.assert_array_equal(result.pixels[40, 60], expected,
                    err_msg='Mixed original Signed material must follow caller order')

    def test_frosted_original_paint_retains_original_cell_domain_and_grain(self):
        source = np.full((100, 160, 3), 251, np.uint8)
        source[20:60, 30:110] = 100
        region = MaskRegion(30, 20, np.full((40, 80), 255, np.uint8), 18)
        result = SkinPainter().paint(source, [region])
        y, x = np.indices((40, 80), dtype=np.uint32)
        hashed = (x * np.uint32(1664525)) ^ (y * np.uint32(1013904223)) ^ np.uint32(913)
        grain = ((hashed ^ (hashed >> 13)) % 5).astype(int) - 2
        expected = np.repeat((100 + grain)[:, :, None], 3, axis=2).astype(np.uint8)
        np.testing.assert_array_equal(result.pixels[20:60, 30:110], expected)
        # Outward pixels repeat the old paint's edge, not nearby fine source.
        np.testing.assert_array_equal(result.pixels[40, 26], expected[20, 0])
        # A later region's extension reaches the first original's last
        # columns. Its different mean must not replace the original paint.
        source[20:60, 112:152] = 180
        neighbor = MaskRegion(112, 20, np.full((40, 40), 255, np.uint8), 18)
        overlapped = SkinPainter().paint(source, [region, neighbor])
        np.testing.assert_array_equal(overlapped.pixels[20:60, 30:110], expected)

        # Frozen original float64 means / interleaved bicubic path is the
        # pixel oracle, not the optimized implementation under test.
        rng = np.random.default_rng(618)
        for width, height, text_height in [(160, 48, 24), (73, 33, 18),
                                           (192, 64, 20), (121, 89, 16),
                                           (7, 3, 4), (1, 72, 10)]:
            raw = rng.integers(0, 256, (height, width, 3), np.uint8)
            cells = cell_extents(width, height, text_height)
            nx = sum(t == 0 for _, t, _, _ in cells)
            ny = len(cells) // nx
            means = np.array([raw[t:b, l:r].mean(axis=(0, 1), dtype=np.float64)
                              for l, t, r, b in cells], np.float32).reshape(ny, nx, 3)
            y, x = np.indices((height, width), dtype=np.uint32)
            hashed = (x * np.uint32(1664525)) ^ (y * np.uint32(1013904223)) ^ np.uint32(913)
            grain = (((hashed ^ (hashed >> 13)) % 5).astype(np.float32) - 2)[:, :, None]
            for desaturation in (0, .65):
                old_means = means.copy()
                if desaturation:
                    gray = old_means @ np.array([.114, .587, .299], np.float32)
                    old_means = old_means * (1-desaturation) + gray[:, :, None] * desaturation
                smooth = cv2.resize(old_means, (nx*4, ny*4), interpolation=cv2.INTER_CUBIC)
                smooth = cv2.GaussianBlur(smooth, (0, 0), 2, borderType=cv2.BORDER_REPLICATE)
                old_paint = cv2.resize(smooth, (width, height), interpolation=cv2.INTER_CUBIC)
                old_paint = np.clip(np.rint(old_paint + grain), 0, 255).astype(np.uint8)
                region = MaskRegion(0, 0, np.full((height, width), 255, np.uint8), text_height)
                result = SkinPainter(desaturation=desaturation).paint(raw, [region])
                with self.subTest(original_paint_size=(width, height), desaturation=desaturation):
                    np.testing.assert_array_equal(result.pixels, old_paint)

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

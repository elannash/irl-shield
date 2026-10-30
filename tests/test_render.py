import unittest

import numpy as np

from shield.render import Renderer


class PrivacyRendering(unittest.TestCase):
    def test_rotated_quad_padding_covers_edges_without_masking_bounding_box_corners(self):
        frame = np.random.default_rng(5).integers(1, 256, (120, 140, 3), dtype=np.uint8)
        original = frame.copy()
        quad = [[50, 20], [100, 70], [80, 90], [30, 40]]
        renderer = Renderer()
        result = renderer.render(frame, [quad], state='LIVE', clues=1)
        self.assertEqual((result.protected, result.slate), (False, False))
        self.assertEqual(result.mask.dtype, np.uint8)
        self.assertEqual(result.mask.shape, frame.shape[:2])
        self.assertEqual(int(result.mask[55, 65]), 255)
        # The short edge is sqrt(800); 30% padding covers 6px but not 12px
        # along the upper long edge's outward normal.
        self.assertEqual(int(result.mask[41, 79]), 255)
        self.assertEqual(int(result.mask[36, 84]), 0)
        self.assertEqual(int(result.mask[20, 30]), 0)
        self.assertTrue((result.pixels[result.mask > 0] == 0).all())
        np.testing.assert_array_equal(result.pixels[result.mask == 0], frame[result.mask == 0])
        np.testing.assert_array_equal(result.mask > 0, np.any(result.pixels != frame, axis=2))
        np.testing.assert_array_equal(frame, original)
        self.assertFalse(np.shares_memory(result.pixels, frame))
        retained_pixels, retained_mask = result.pixels.copy(), result.mask.copy()
        later = renderer.render(frame, [], state='LIVE', clues=0)
        renderer.render(frame, [], state='HOLD', clues=0)
        later.pixels[:] = 0
        later.mask[:] = 255
        np.testing.assert_array_equal(result.pixels, retained_pixels)
        np.testing.assert_array_equal(result.mask, retained_mask)

    def test_protect_removes_fine_detail_then_slates_and_hold_slates_immediately(self):
        checker = (np.indices((128, 192)).sum(axis=0) % 2 * 255).astype(np.uint8)
        frame = np.repeat(checker[:, :, None], 3, axis=2)
        original = frame.copy()
        renderer = Renderer(slate_after=.5)
        protected = renderer.render(frame, [], state='PROTECT', clues=0, protect_duration=.49)
        self.assertEqual((protected.protected, protected.slate), (True, False))
        self.assertTrue((protected.mask == 255).all())
        self.assertGreater(float(np.abs(protected.pixels.astype(float) - frame).mean()), 80)
        self.assertLess(float(protected.pixels.std()), float(frame.std()) * .1)
        for state, duration in [('PROTECT', .5), ('HOLD', 0)]:
            with self.subTest(state=state):
                result = renderer.render(frame, [], state=state, clues=0, protect_duration=duration)
                self.assertEqual((result.protected, result.slate), (True, True))
                self.assertTrue((result.mask == 255).all())
                self.assertTrue((result.pixels == 0).all())
                self.assertFalse(np.shares_memory(result.pixels, frame))
        live = renderer.render(frame, [], state='LIVE', clues=0)
        np.testing.assert_array_equal(live.pixels, original)
        self.assertTrue((live.mask == 0).all())
        np.testing.assert_array_equal(frame, original)

    def test_uncovered_protection_removes_all_spatial_text_shapes(self):
        import cv2
        source=np.full((720,1280,3),240,np.uint8)
        cv2.putText(source,'1842',(80,530),cv2.FONT_HERSHEY_SIMPLEX,12,(15,25,35),30)
        result=Renderer().render(source,[],'PROTECT',0)
        self.assertTrue(result.protected)
        self.assertFalse(result.slate)
        self.assertTrue((result.mask==255).all())
        self.assertTrue((np.ptp(result.pixels,axis=(0,1))==0).all())
        self.assertFalse(np.shares_memory(result.pixels,source))

    def test_invalid_state_geometry_and_configuration_fail_explicitly(self):
        frame = np.full((80, 120, 3), 160, np.uint8)
        renderer = Renderer()
        with self.assertRaises(ValueError):
            renderer.render(frame, [], state='BROKEN', clues=0)
        for quad in [
            [[10, 10], [40, 10], [float('nan'), 30], [10, 30]],
            [[10, 10], [40, 10], [30, 20], [10, 30], [0, 20]],
            [[10, 10], [20, 10], [30, 10], [40, 10]],
        ]:
            with self.subTest(quad=quad), self.assertRaises(ValueError):
                renderer.render(frame, [quad], state='LIVE', clues=1)
        with self.assertRaises(ValueError):
            renderer.render(frame.astype(float), [], state='LIVE', clues=0)
        for duration in [-1, float('nan')]:
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                renderer.render(frame, [], state='PROTECT', clues=0, protect_duration=duration)
        for options in [{'style': 'not-implemented'}, {'padding': -.1},
                        {'padding': float('nan')}, {'slate_after': float('inf')}]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                Renderer(**options)

    def test_skin_paint_preserves_every_original_polygon_pixel_and_default_geometry(self):
        import cv2
        from shield.skins import MaskRegion, SkinPainter
        checker = (np.indices((120, 160)).sum(axis=0) % 2 * 255).astype(np.uint8)
        frame = np.repeat(checker[:, :, None], 3, axis=2)
        quads = [[[20, 12], [110, 32], [100, 58], [10, 38]],
                 [[-18, 60], [45, 48], [50, 87], [-13, 99]]]
        polygon = np.zeros(frame.shape[:2], np.uint8)
        for quad in quads:
            cv2.fillConvexPoly(polygon, np.asarray(quad, np.int32), 255)
        painter = SkinPainter()
        skin = ['frosted']
        def paint(pixels, regions, state):
            return painter.paint(pixels, [MaskRegion(*r) for r in regions], state=state, skin=skin[0])
        renderer = Renderer(paint=paint)
        baseline = Renderer().render(frame, quads, 'LIVE', 2)
        frosted = renderer.render(frame, quads, 'LIVE', 2)
        np.testing.assert_array_equal(frosted.mask, baseline.mask)
        self.assertTrue((frosted.mask[polygon > 0] == 255).all())
        self.assertTrue(((frosted.pixels[polygon > 0] > 0) & (frosted.pixels[polygon > 0] < 255)).all())
        np.testing.assert_array_equal(frosted.pixels[frosted.mask == 0], frame[frosted.mask == 0])
        skin[0] = 'bar'
        bar = renderer.render(frame, quads, 'LIVE', 2)
        np.testing.assert_array_equal(bar.mask, frosted.mask)
        self.assertTrue((bar.pixels[polygon > 0] == 0).all())
        for state in ('HOLD', 'PROTECT'):
            a = renderer.render(frame, [], state, 0)
            b = renderer.render(255-frame, [], state, 0)
            self.assertTrue((a.mask == 255).all())
            np.testing.assert_array_equal(a.pixels, b.pixels)

    def test_skin_paint_cannot_shrink_coverage_or_supply_transparent_polygons(self):
        from shield.skins import MaskRegion, SkinPainter
        frame = np.full((120, 160, 3), 180, np.uint8)
        quad = [[20, 20], [100, 20], [100, 50], [20, 50]]
        painter = SkinPainter()
        for invalid in ('mask', 'alpha'):
            def damaged(pixels, regions, state):
                result = painter.paint(pixels, [MaskRegion(*r) for r in regions], state=state)
                getattr(result, invalid).fill(0)
                return result
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, 'opaque polygon coverage'):
                Renderer(paint=damaged).render(frame, [quad], 'LIVE', 1)

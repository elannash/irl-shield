import unittest

import numpy as np

from shield.render import Renderer


class PrivacyRendering(unittest.TestCase):
    def test_padding_floor_can_be_removed_without_trimming_bare_quad(self):
        frame = np.full((100, 140, 3), 180, np.uint8)
        quad = [[30, 40], [90, 40], [90, 50], [30, 50]]
        default = Renderer(padding=0).render(frame, [quad], 'LIVE', 1)
        bare = Renderer(padding=0, padding_floor=0).render(frame, [quad], 'LIVE', 1)
        self.assertEqual(int(default.mask[37, 30]), 255)
        self.assertEqual(int(bare.mask[37, 30]), 0)
        self.assertTrue((bare.mask[40:51, 30:91] == 255).all())
        self.assertEqual(np.count_nonzero(bare.mask), 61 * 11)
        self.assertTrue((bare.pixels[40:51, 30:91] == 0).all())
        for floor in (-1, float('nan'), float('inf')):
            with self.subTest(floor=floor), self.assertRaises(ValueError):
                Renderer(padding_floor=floor)

    def test_precision_padding_tracks_height_instead_of_long_word_width(self):
        frame = np.full((100, 160, 3), 180, np.uint8)
        renderer = Renderer(padding=.1, padding_floor=0)
        short = [[20, 40], [120, 40], [120, 50], [20, 50]]
        tall = [[20, 40], [120, 40], [120, 70], [20, 70]]
        a = renderer.render(frame, [short], 'LIVE', 1)
        b = renderer.render(frame, [tall], 'LIVE', 1)
        self.assertEqual(int(a.mask[39, 70]), 255)
        self.assertEqual(int(a.mask[38, 70]), 0)
        self.assertEqual(int(b.mask[37, 70]), 255)
        self.assertEqual(int(b.mask[36, 70]), 0)

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

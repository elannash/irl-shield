import unittest
from unittest.mock import patch

import numpy as np

from shield.presentation import PresentationRenderer, PresentationSnapshot, TrackTally


class PresentationPrivacy(unittest.TestCase):
    def setUp(self):
        self.a = np.random.default_rng(67).integers(0, 256, (180, 320, 3), dtype=np.uint8)
        self.b = np.random.default_rng(89).integers(0, 256, self.a.shape, dtype=np.uint8)
        self.mask = np.zeros(self.a.shape[:2], np.uint8)
        self.renderer = PresentationRenderer(320, 180)

    def test_every_slate_and_reason_swap_is_independent_of_two_random_sources(self):
        previous = None
        for state in ('HOLD', 'SHIELD_MODE', 'PROTECT', 'FAILURE', 'HOLD'):
            with self.subTest(state=state):
                snapshot = PresentationSnapshot(state, clue_count=101, face_count=20)
                a = self.renderer.render(self.a, self.mask, snapshot, source_sequence=3)
                b = self.renderer.render(self.b, self.mask, snapshot, source_sequence=3)
                self.assertTrue(a.slate)
                np.testing.assert_array_equal(a.pixels, b.pixels)
                self.assertTrue((a.mask == 255).all())
                self.assertTrue((a.overlay_mask == 255).all())
                self.assertGreater(np.unique(a.pixels.reshape(-1, 3), axis=0).shape[0], 10)
                self.assertFalse(np.shares_memory(a.pixels, self.a))
                self.assertEqual(a.state, 'FAILURE' if state == 'PROTECT' else state)
                if previous is not None and state not in ('FAILURE',):
                    self.assertFalse(np.array_equal(a.pixels, previous))
                previous = a.pixels

    def test_shield_hold_reason_selects_shield_mode_without_rendering_reason_text(self):
        held = self.renderer.render(self.a, self.mask,
                                    PresentationSnapshot('HOLD', reason_code='shield_mode'),
                                    source_sequence=1)
        explicit = self.renderer.render(self.b, self.mask, PresentationSnapshot('SHIELD_MODE'),
                                        source_sequence=2)
        self.assertEqual(held.state, 'SHIELD_MODE')
        np.testing.assert_array_equal(held.pixels, explicit.pixels)

    def test_release_requires_new_live_capture_even_after_an_accepted_release(self):
        live, hold = PresentationSnapshot('LIVE'), PresentationSnapshot('HOLD')
        self.renderer.render(self.a, self.mask, live, source_sequence=8)
        hidden = self.renderer.render(self.a, self.mask, hold, source_sequence=9)
        for sequence in (9, 8):
            replay = self.renderer.render(self.b, self.mask, live, source_sequence=sequence)
            np.testing.assert_array_equal(replay.pixels, hidden.pixels)
            self.assertTrue(replay.slate)
        fresh = self.renderer.render(self.b, self.mask, live, source_sequence=10)
        self.assertFalse(fresh.slate)
        np.testing.assert_array_equal(fresh.pixels[fresh.overlay_mask == 0],
                                      self.b[fresh.overlay_mask == 0])
        replay = self.renderer.render(self.a, self.mask, live, source_sequence=9)
        self.assertTrue(replay.slate)
        np.testing.assert_array_equal(replay.pixels, hidden.pixels)

    def test_out_of_order_hold_blocks_through_latest_seen_capture(self):
        live = PresentationSnapshot('LIVE')
        self.renderer.render(self.a, self.mask, live, source_sequence=20)
        self.renderer.render(self.a, self.mask, PresentationSnapshot('HOLD'), source_sequence=18)
        self.assertTrue(self.renderer.render(self.b, self.mask, live, source_sequence=20).slate)
        self.assertFalse(self.renderer.render(self.b, self.mask, live, source_sequence=21).slate)

    def test_badge_audit_is_actual_opaque_geometry_and_preserves_existing_mask(self):
        self.mask[3:11, 5:18] = 255
        original_a, original_mask = self.a.copy(), self.mask.copy()
        snapshot = PresentationSnapshot('LIVE', clue_count=101, face_count=999)
        a = self.renderer.render(self.a, self.mask, snapshot, source_sequence=1)
        b = self.renderer.render(self.b, self.mask, snapshot, source_sequence=2)
        overlay = a.overlay_mask > 0
        self.assertTrue(overlay.any())
        self.assertFalse(overlay.all())
        np.testing.assert_array_equal(a.pixels[overlay], b.pixels[overlay])
        np.testing.assert_array_equal(a.pixels[~overlay], self.a[~overlay])
        np.testing.assert_array_equal(a.mask, np.maximum(original_mask, a.overlay_mask))
        np.testing.assert_array_equal(self.a, original_a)
        np.testing.assert_array_equal(self.mask, original_mask)
        # Rendered face totals must never change the clue caption.
        other = self.renderer.render(self.a, self.mask,
                                     PresentationSnapshot('LIVE', clue_count=101, face_count=0),
                                     source_sequence=3)
        np.testing.assert_array_equal(a.pixels, other.pixels)

    def test_mutating_returned_pixels_and_masks_cannot_poison_cached_outputs(self):
        for state in ('LIVE', 'HOLD'):
            snapshot = PresentationSnapshot(state, clue_count=7)
            a = self.renderer.render(self.a, self.mask, snapshot, source_sequence=5)
            expected = a.pixels.copy()
            a.pixels[:] = 99
            a.mask[:] = 17
            a.overlay_mask[:] = 18
            b = self.renderer.render(self.a, self.mask, snapshot, source_sequence=6)
            np.testing.assert_array_equal(b.pixels, expected)
            self.assertFalse((b.mask == 17).any())
            self.assertFalse((b.overlay_mask == 18).any())

    def test_no_font_rasterization_after_setup_including_count_changes_and_state_swaps(self):
        with patch('PIL.ImageDraw.ImageDraw.text', side_effect=AssertionError('hot-path rasterization')):
            outputs = [self.renderer.render(self.a, self.mask,
                       PresentationSnapshot('LIVE', clue_count=count), source_sequence=count + 1)
                       for count in (0, 9, 10, 999_999_999)]
            self.assertFalse(np.array_equal(outputs[0].pixels, outputs[1].pixels))
            self.renderer.render(self.a, self.mask, PresentationSnapshot('HOLD'), source_sequence=2)
            self.renderer.render(self.a, self.mask, PresentationSnapshot('FAILURE'), source_sequence=3)

    def test_badge_off_changes_no_live_pixels_or_coverage(self):
        renderer = PresentationRenderer(320, 180, badge=False)
        result = renderer.render(self.a, self.mask, PresentationSnapshot('LIVE'), source_sequence=0)
        np.testing.assert_array_equal(result.pixels, self.a)
        np.testing.assert_array_equal(result.mask, self.mask)
        self.assertFalse(result.overlay_mask.any())

    def test_snapshot_rejects_private_text_and_invalid_counters(self):
        for kwargs in ({'state': 'https://private.invalid'},
                       {'state': 'HOLD', 'reason_code': 'raw secret error'},
                       {'state': 'LIVE', 'skin_name': '48 Fiction Street'},
                       {'state': 'LIVE', 'clue_count': -1},
                       {'state': 'LIVE', 'clue_count': True},
                       {'state': 'LIVE', 'face_count': 1.2},
                       {'state': 'LIVE', 'clue_count': 1_000_000_000}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                PresentationSnapshot(**kwargs)
        with self.assertRaises(TypeError):
            PresentationSnapshot('LIVE', qr='private')


class PresentationTally(unittest.TestCase):
    def test_session_track_ids_count_once_across_reentry_with_faces_separate(self):
        clues, faces = TrackTally(), TrackTally()
        self.assertEqual(clues.observe([7, 7, 9]), 2)
        self.assertEqual(clues.observe([]), 2)
        self.assertEqual(clues.observe([9, 7, 11]), 3)
        self.assertEqual(faces.observe([7, 9, 13, 15]), 4)
        self.assertEqual(clues.count, 3)
        self.assertEqual(clues.observe(['7']), 4)

    def test_invalid_id_batch_is_atomic(self):
        tally = TrackTally()
        tally.observe([1])
        for bad in (None, True, -1, '', 'x' * 129, [], 1.2):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                tally.observe([2, bad])
            self.assertEqual(tally.count, 1)


if __name__ == '__main__':
    unittest.main()

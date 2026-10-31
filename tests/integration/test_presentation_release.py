"""Presentation release keeps per-frame privacy and control-hold fences separate."""
import unittest
import numpy as np
from shield.app.appearance import Appearance
from shield.types import Coverage, PresentedFrame
from test_expansion import engine_for


class PresentationRelease(unittest.TestCase):
    def frame(self, index, state='LIVE'):
        pixels = np.full((180, 320, 3), 211, np.uint8)
        return PresentedFrame(index, index / 30, pixels, np.zeros((180, 320), np.uint8), [],
            Coverage(0, 0, state == 'LIVE', 'covered' if state == 'LIVE' else 'coverage'),
            state, index / 30, index / 30, state != 'LIVE', state != 'LIVE')

    def test_coverage_gap_then_newer_covered_frame_can_resume_delayed_video(self):
        appearance = Appearance(width=320, height=180)
        engine = engine_for(appearance)
        try:
            for index in (100, 110, 120):
                engine.control.update_coverage(False, 'coverage', index / 30)
                protected = appearance.present(self.frame(index, 'PROTECT'), capture_highwater=index+30)
                self.assertTrue(protected.slate and np.all(protected.mask == 255))
                engine.control.update_coverage(True, 'covered', (index+1) / 30)
                live = appearance.present(self.frame(index+1), capture_highwater=index+31)
                self.assertFalse(live.slate, 'Fresh independently covered frame must not be held behind future ingress')
                self.assertEqual(live.state, 'LIVE')
                np.testing.assert_array_equal(live.pixels, np.full((180,320,3),211,np.uint8))
        finally:
            engine.close()

    def test_every_control_hold_keeps_ingress_replay_fence_across_coverage_checks(self):
        for source in ('local', 'chat', 'shield_mode', 'transport', 'egress'):
            with self.subTest(source=source):
                appearance = Appearance(width=320, height=180)
                engine = engine_for(appearance)
                try:
                    engine.hold(True, source=source, reason='manual')
                    held = appearance.present(self.frame(130), capture_highwater=160)
                    self.assertTrue(held.slate and np.all(held.mask == 255))
                    engine.hold(False, source=source)
                    engine.control.update_coverage(False, 'coverage', 5)
                    appearance.present(self.frame(131, 'PROTECT'), capture_highwater=200)
                    engine.control.update_coverage(True, 'covered', 5.1)
                    replay = appearance.present(self.frame(159), capture_highwater=201)
                    self.assertTrue(replay.slate and np.all(replay.mask == 255), 'Coverage must not lower an actual HOLD fence')
                    fresh = appearance.present(self.frame(161), capture_highwater=202)
                    self.assertFalse(fresh.slate, 'Actual HOLD fences captured-before-release frames, not later ingress')
                finally:
                    engine.close()

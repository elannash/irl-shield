"""The persistent transport seam: startup/drop/hold, PTS, audio and queue bounds."""
import unittest

import numpy as np

from relay.live import RelaySession
from relay.bridge import NoOpDetector
from shield.engine import MaskingEngine
from shield.lanes import DetectorLane


class LiveSession(unittest.TestCase):
    def test_cold_start_drop_reconnect_and_control_hold_use_engine_pixels(self):
        lanes = {n: DetectorLane(n, NoOpDetector(), 30) for n in ('fast', 'accurate')}
        engine = MaskingEngine(lanes, {'fps': 30, 'delay_seconds': .1})
        outputs = []
        session = RelaySession(engine, lambda frame, pcm: outputs.append((frame, pcm)),
                               width=32, height=32, fps=30, start=10)
        try:
            session.tick(10.11)
            self.assertGreater(len(outputs), 0)
            self.assertTrue(outputs[0][0].slate)
            self.assertFalse(outputs[0][0].pixels.any())
            pixels = np.full((32, 32, 3), 231, np.uint8)
            session.video(3, pixels, generation=1, now=10.2)
            session.audio(3, np.full(1600, 123, np.int16), generation=1)
            session.control.hold(True, source='twitch-chat', reason='synthetic hold')
            session.tick(10.31)
            session.tick(10.31)
            self.assertTrue(all(frame.protected for frame, _ in outputs))
            self.assertFalse(any(frame.pixels.any() for frame, _ in outputs))
            self.assertEqual(outputs[-1][0].index, 6)
            self.assertFalse(outputs[-1][1].any(), 'Moderator HOLD must silence audio')
            session.audio(3.3, np.full(1600, 999, np.int16), generation=1)
            session.disconnected()
            session.video(0, pixels, generation=2, now=10.5)
            for _ in range(3):
                session.tick(10.61)
            self.assertEqual(outputs[-1][0].index, 15)
            self.assertEqual(outputs[-1][0].pts, .5)
            self.assertEqual(outputs[-1][0].state, 'HOLD')
            self.assertFalse(outputs[-1][0].pixels.any())
            self.assertFalse(outputs[-1][1].any(), 'Reconnect must not emit queued audio from a previous source generation')
            self.assertEqual(session.stats['sessions'], 2)
            self.assertLessEqual(session.stats['audio_buffer_samples'], session.stats['audio_capacity_samples'])
        finally:
            engine.close()


if __name__ == '__main__':
    unittest.main()

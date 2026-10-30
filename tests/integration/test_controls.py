"""M2/M3 adapter contract; deterministic clocks, actual engine and emitted pixels."""
import unittest

import numpy as np

from relay.bridge import NoOpDetector
from relay.live import RelaySession
from shield.engine import MaskingEngine
from shield.lanes import DetectorLane
from shield.twitch.events import ShieldEvents
from test_events import START, notification


class IntegratedControls(unittest.TestCase):
    def test_eventsub_and_manual_holds_remain_independent_through_sender_reconnect(self):
        engine = MaskingEngine({n: DetectorLane(n, NoOpDetector(), 30) for n in ('fast', 'accurate')},
                               {'fps': 30, 'delay_seconds': .1})
        frames = []
        relay = RelaySession(engine, lambda result, pcm: frames.append(result),
                             width=32, height=32, start=10)
        try:
            events = ShieldEvents('1', relay.control.hold, started_at=START,
                                  clock=lambda: START + 10, control_clock=lambda: 10.1)
            generation = events.connection_started()
            self.assertTrue(events.welcome('first', generation=generation))
            token = events.begin_reconcile(generation=generation, session_id='first')
            self.assertTrue(events.reconciled(False, token))
            relay.video(0, np.full((32, 32, 3), 231, np.uint8), 1, now=10.2)
            self.assertEqual(events.accept(notification('mod'), generation=generation), 'chat-hold')
            relay.tick(10.31)
            self.assertGreater(len(frames), 0)
            self.assertTrue(all(f.slate and not f.pixels.any() for f in frames))
            relay.control.hold(True)
            events.accept(notification('shield', topic='channel.shield_mode.begin'), generation=generation)
            events.accept(notification('owner', '!shield resume', actor='1', at=START + 2), generation=generation)
            relay.disconnected()
            relay.video(0, np.full((32, 32, 3), 199, np.uint8), 2, now=10.4)
            events.accept(notification('end', topic='channel.shield_mode.end', at=START + 3), generation=generation)
            self.assertEqual(engine.control.state, 'HOLD')
            relay.control.hold(False)
            self.assertNotEqual(engine.control.state, 'HOLD')
            relay.control.hold(True)
            events.fault()
            generation = events.connection_started()
            self.assertTrue(events.welcome('second', generation=generation))
            token = events.begin_reconcile(generation=generation, session_id='second')
            self.assertTrue(events.reconciled(False, token))
            self.assertEqual(engine.control.state, 'HOLD')
            self.assertEqual(events.accept(notification('owner', '!shield resume', actor='1', at=START + 2),
                                           generation=generation), 'duplicate')
            relay.tick(10.51)
            self.assertTrue(all(f.slate and not f.pixels.any() for f in frames))
        finally:
            engine.close()

    def test_hold_between_poll_and_writer_replaces_stale_live_frame_and_next_frame(self):
        from unittest.mock import patch
        from shield.types import Coverage, PresentedFrame
        engine = MaskingEngine({n: DetectorLane(n, NoOpDetector(), 30) for n in ('fast', 'accurate')},
                               {'fps': 30, 'delay_seconds': .1})
        written = []
        relay = RelaySession(engine, lambda frame, pcm: written.append(frame), width=32, height=32, start=10)
        raw = np.full((32, 32, 3), 231, np.uint8)
        polled_frames = []
        def polled(index):
            return PresentedFrame(index, index / 30, raw.copy(), np.zeros((32,32), np.uint8), [],
                                  Coverage(0, 0, True, 'covered'), 'LIVE', 10 + index / 30,
                                  10 + index / 30, False, False)
        try:
            engine.hold(False, source='transport')
            engine.control.update_coverage(True, 'covered', 10)
            def hold_after_poll(*args, **kwargs):
                result = polled(0)
                polled_frames.append(result)
                relay.control.hold(True, source='chat', reason='moderator')
                return [result]
            with patch.object(engine, 'poll', side_effect=hold_after_poll):
                relay.tick(10.1)
            with patch.object(engine, 'poll', return_value=[polled(1)]):
                relay.tick(10.2)
            self.assertEqual(len(written), 2)
            self.assertIs(written[0], polled_frames[0], 'writer must retain the engine poll object')
            for frame in written:
                self.assertEqual(frame.state, 'HOLD')
                self.assertTrue(frame.slate and frame.protected)
                self.assertFalse(frame.pixels.any())
                self.assertTrue(np.all(frame.mask == 255))
            self.assertTrue(np.all(raw == 231), 'late hold mutated source pixels')
        finally:
            engine.close()

    def test_egress_recovery_guard_does_not_clear_manual_hold_or_replace_poll_objects(self):
        from unittest.mock import patch
        from shield.types import Coverage, PresentedFrame
        engine = MaskingEngine({n: DetectorLane(n, NoOpDetector(), 30) for n in ('fast', 'accurate')},
                               {'fps': 30, 'delay_seconds': .1})
        written = []
        replies = iter((False, None, True))
        def sink(frame, pcm):
            written.append(frame)
            return next(replies)
        relay = RelaySession(engine, sink, width=32, height=32, start=10)
        try:
            engine.hold(False, source='transport')
            relay.control.hold(True)
            for index in range(3):
                result = PresentedFrame(index, index / 30, np.full((32,32,3), 231, np.uint8),
                                        np.zeros((32,32), np.uint8), [], Coverage(0,0,True,'covered'),
                                        'LIVE', 10 + index / 30, 10 + index / 30, False, False)
                with patch.object(engine, 'poll', return_value=[result]):
                    relay.tick(10 + index / 30)
                self.assertIs(written[-1], result)
                self.assertTrue(result.slate and not result.pixels.any())
                if index == 0:
                    relay.control.hold(False)
                    self.assertEqual(engine.control.state, 'HOLD', 'egress hold was not asserted')
                if index == 1:
                    relay.control.hold(True)
            self.assertEqual(relay.stats['egress_interruptions'], 1)
            self.assertEqual(engine.control.state, 'HOLD', 'network readiness cleared manual hold')
            relay.control.hold(False)
            self.assertNotEqual(engine.control.state, 'HOLD', 'egress hold survived ready acknowledgment')
        finally:
            engine.close()

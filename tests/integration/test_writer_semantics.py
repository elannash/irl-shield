"""Writer/session contract with original CC0 pixels and PCM; no external assets."""
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from relay.egress import EgressWriter
from relay.live import RelaySession
from shield.control import Control
from shield.types import Coverage, PresentedFrame


def frame(index, presented_at=10.):
    return PresentedFrame(index, index / 30, np.full((32, 32, 3), 231, np.uint8),
                          np.zeros((32, 32), np.uint8), [], Coverage(0, 0, True, 'covered'),
                          'LIVE', presented_at, presented_at, False, False)


class PresentedEngine:
    """Controlled engine adapter: session and writer remain the production modules."""
    delay = .1

    def __init__(self):
        self.lock = threading.RLock()
        self.control = Control()
        self.control.update_coverage(True, 'covered', 0)
        self.results = []

    def hold(self, active, source='local', reason='manual', now=None):
        self.control.set_hold(active, source, reason, now or 0)

    def submit(self, value, now=None):
        pass

    def poll(self, now=None):
        results, self.results = self.results, []
        return results


class ControlledOutput:
    def __init__(self):
        self.entered, self.release = threading.Event(), threading.Event()
        self.condition = threading.Condition()
        self.rows = []
        self.outcome = True

    def write(self, result, pcm):
        if not self.entered.is_set():
            self.entered.set()
            if not self.release.wait(2):
                raise RuntimeError('fixture-release-timeout')
        with self.condition:
            self.rows.append((result, pcm.copy()))
            self.condition.notify_all()
        return self.outcome

    def wait_frame(self, test, index):
        with self.condition:
            test.assertTrue(self.condition.wait_for(lambda: any(row[0].index == index for row in self.rows), 2),
                            'destination did not receive the requested session frame')
            return next(row for row in self.rows if row[0].index == index)

    def close(self):
        pass


class WriterSession(unittest.TestCase):
    def session(self, writer):
        engine = PresentedEngine()
        session = RelaySession(engine, writer.write, width=32, height=32, start=0)
        session.video(0, np.full((32, 32, 3), 231, np.uint8), 1, now=0)
        session.audio(0, np.repeat(np.array([111, 222, 333], np.int16), 1600), 1)
        return engine, session

    def wait_status(self, writer, expected, presented_at):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            status = writer.write(frame(10000, presented_at), np.zeros(1600, np.int16))
            if status is expected:
                return
            threading.Event().wait(.001)
        self.fail('writer did not publish the expected completion status')

    def assert_healthy(self, engine, session, buffered):
        self.assertEqual(session.stats['egress_interruptions'], 0)
        self.assertEqual(engine.control.state, 'LIVE')
        self.assertEqual(session.stats['audio_dropped_samples'], 0)
        self.assertEqual(session.stats['audio_buffer_samples'], buffered)

    def test_startup_pending_does_not_hold_or_discard_buffered_audio(self):
        output = ControlledOutput()
        writer = EgressWriter(output, lambda: engine.control.state == 'HOLD')
        engine, session = self.session(writer)
        try:
            engine.results = [frame(1)]
            session.tick()
            self.assertTrue(output.entered.wait(2), 'the first write must remain in flight')
            self.assert_healthy(engine, session, 3200)
            engine.results = [frame(2)]
            session.tick()
            self.assert_healthy(engine, session, 1600)
            output.release.set()
            self.wait_status(writer, True, time.monotonic())
            engine.results = [frame(3, time.monotonic())]
            session.tick()
            delivered, pcm = output.wait_frame(self, 3)
            self.assertFalse(delivered.slate)
            self.assertTrue(delivered.pixels.any())
            np.testing.assert_array_equal(pcm, np.full(1600, 333, np.int16))
            self.assert_healthy(engine, session, 0)
        finally:
            output.release.set()
            writer.close()
        self.assertFalse(writer.thread.is_alive())

    def test_stale_result_after_slow_success_preserves_health_and_audio(self):
        output = ControlledOutput()
        clock = [10.]
        engine = PresentedEngine()
        with patch('relay.egress.time', SimpleNamespace(monotonic=lambda: clock[0])):
            writer = EgressWriter(output, lambda: engine.control.state == 'HOLD')
            try:
                writer.write(frame(0), np.zeros(1600, np.int16))
                self.assertTrue(output.entered.wait(2))
                stale = frame(1, 10.5)
                clock[0] = 11.  # Successful native write took longer than the freshness budget.
                output.release.set()
                self.wait_status(writer, True, 11.)
                engine, session = self.session(writer)
                engine.results = [stale, frame(2, 11.)]
                dropped = writer.dropped
                session.tick()
                self.assertGreater(writer.dropped, dropped, 'the old result must actually be skipped')
                self.assert_healthy(engine, session, 1600)
                delivered, pcm = output.wait_frame(self, 2)
                self.assertFalse(delivered.slate)
                np.testing.assert_array_equal(pcm, np.full(1600, 222, np.int16))
                engine.results = [frame(3, 11.)]
                session.tick()
                delivered, pcm = output.wait_frame(self, 3)
                self.assertFalse(delivered.slate)
                np.testing.assert_array_equal(pcm, np.full(1600, 333, np.int16))
                self.assert_healthy(engine, session, 0)
            finally:
                output.release.set()
                writer.close()
        self.assertFalse(writer.thread.is_alive())

    def test_real_outage_holds_through_pending_ack_then_recovers_with_fresh_audio(self):
        output = ControlledOutput()
        output.outcome = False
        engine = PresentedEngine()
        writer = EgressWriter(output, lambda: engine.control.state == 'HOLD')
        try:
            writer.write(frame(0), np.zeros(1600, np.int16))
            self.assertTrue(output.entered.wait(2))
            output.release.set()
            self.wait_status(writer, False, time.monotonic())
            engine, session = self.session(writer)
            engine.results = [frame(1, time.monotonic())]
            session.tick()
            self.assertEqual(session.stats['egress_interruptions'], 1)
            self.assertEqual(engine.control.state, 'HOLD')
            self.assertEqual(session.stats['audio_buffer_samples'], 0)
            self.assertEqual(session.stats['audio_dropped_samples'], 3200)
            output.wait_frame(self, 1)

            output.outcome = None  # Native recovery has not acknowledged network readiness.
            engine.results = [frame(2, time.monotonic())]
            session.tick()
            delivered, _ = output.wait_frame(self, 2)
            self.assertTrue(delivered.slate)
            self.assertFalse(delivered.pixels.any())
            # Starting a later write proves the preceding None completion was collected.
            writer.write(frame(10001, time.monotonic()), np.zeros(1600, np.int16))
            output.wait_frame(self, 10001)
            self.assertIs(writer.write(frame(10002, time.monotonic()), np.zeros(1600, np.int16)), False)
            self.assertEqual(engine.control.state, 'HOLD')

            output.outcome = True
            self.wait_status(writer, True, time.monotonic())
            engine.results = [frame(3, time.monotonic())]
            session.tick()
            delivered, _ = output.wait_frame(self, 3)
            self.assertTrue(delivered.slate, 'readiness must not unmask the recovery handoff')
            self.assertEqual(engine.control.state, 'LIVE')
            interruptions = session.stats['egress_interruptions']
            session.audio(.1, np.full(1600, 444, np.int16), 1)
            engine.results = [frame(4, time.monotonic())]
            session.tick()
            delivered, pcm = output.wait_frame(self, 4)
            self.assertFalse(delivered.slate)
            self.assertTrue(delivered.pixels.any())
            np.testing.assert_array_equal(pcm, np.full(1600, 444, np.int16))
            self.assertEqual(session.stats['egress_interruptions'], interruptions)
        finally:
            output.release.set()
            writer.close()
        self.assertFalse(writer.thread.is_alive())

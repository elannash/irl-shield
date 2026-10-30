"""Operator holds silence real session PCM without coupling it to video coverage."""
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np

from relay.bridge import NoOpDetector
from relay.live import RelayControl, RelaySession
from relay.egress import EgressWriter
from relay.stream import Egress, enforce_hold
from shield.engine import MaskingEngine
from shield.lanes import DetectorLane


class HoldAudio(unittest.TestCase):
    def setUp(self):
        self.new_session()

    def new_session(self):
        lanes = {name: DetectorLane(name, NoOpDetector(), 30) for name in ('fast', 'accurate')}
        self.engine = MaskingEngine(lanes, {'fps': 30, 'delay_seconds': .1})
        self.addCleanup(self.engine.close)
        self.outputs = []
        # Runtime supplies the control before constructing the session too.
        self.control = RelayControl(self.engine)
        self.session = RelaySession(self.engine, lambda frame, pcm: self.outputs.append((frame, pcm)),
                                    width=32, height=32, start=10, control=self.control)
        self.session.video(0, np.full((32, 32, 3), 180, np.uint8), generation=1, now=10)

    def emit(self, index, value=723):
        pts = index / 30
        self.session.audio(pts - 1 / 30, np.full(1600, value, np.int16), generation=1)
        self.session.tick(10 + pts + .1001)
        frame, pcm = self.outputs[-1]
        self.assertEqual(frame.index, index)
        return frame, pcm

    def test_operator_sources_mute_exact_pcm_and_release_independently(self):
        for source in ('local', 'chat', 'shield_mode', 'twitch-chat', 'eventsub'):
            with self.subTest(source=source):
                self.control.hold(True, source=source)
                _, pcm = self.emit(self.engine.next_index)
                np.testing.assert_array_equal(pcm, np.zeros(1600, np.int16))
                self.control.hold(True, source=source)
                self.control.hold(True, source='local' if source != 'local' else 'chat')
                self.control.hold(False, source=source)
                frame, pcm = self.emit(self.engine.next_index)
                self.assertEqual(frame.state, 'HOLD')
                np.testing.assert_array_equal(pcm, np.zeros(1600, np.int16))
                self.control.hold(False, source='local' if source != 'local' else 'chat')
                self.control.hold(False, source=source)
                _, pcm = self.emit(self.engine.next_index)
                np.testing.assert_array_equal(pcm, np.full(1600, 723, np.int16))

    def test_protect_and_safety_holds_keep_audio(self):
        for source in (None, 'transport', 'egress', 'twitch-connection', 'twitch-reconcile'):
            with self.subTest(source=source):
                if source:
                    self.engine.hold(True, source=source)
                frame, pcm = self.emit(self.engine.next_index)
                self.assertEqual(frame.state, 'HOLD' if source else 'PROTECT')
                np.testing.assert_array_equal(pcm, np.full(1600, 723, np.int16))
                if source:
                    self.engine.hold(False, source=source)

    def test_hold_and_release_between_ticks_discard_buffered_and_held_input(self):
        self.session.audio(0, np.full(4800, 111, np.int16), generation=1)
        self.control.hold(True, source='chat')
        self.session.audio(.1, np.full(1600, 222, np.int16), generation=1)
        self.control.hold(False, source='chat')
        self.session.tick(10.234)
        self.assertEqual([frame.index for frame, _ in self.outputs], [0, 1, 2, 3])
        for _, pcm in self.outputs:
            np.testing.assert_array_equal(pcm, np.zeros(1600, np.int16))
        _, pcm = self.emit(4, value=333)
        np.testing.assert_array_equal(pcm, np.full(1600, 333, np.int16))

    def test_hold_after_poll_is_checked_from_actual_control_before_sink(self):
        original = self.engine.poll
        def held_poll(now=None):
            frames = original(now)
            self.control.hold(True, source='shield_mode')
            return frames
        with patch.object(self.engine, 'poll', side_effect=held_poll):
            frame, pcm = self.emit(1)
        self.assertEqual(frame.state, 'HOLD')
        self.assertFalse(frame.pixels.any())
        np.testing.assert_array_equal(pcm, np.zeros(1600, np.int16))

    def test_blocking_sink_releases_engine_for_actual_control_and_ingest(self):
        entered, release = threading.Event(), threading.Event()
        errors = []
        def blocked_sink(frame, pcm):
            entered.set()
            if not release.wait(2):
                raise RuntimeError('test sink gate did not release')
        self.session.sink = blocked_sink
        def tick():
            try:
                self.session.tick(10.1001)
            except Exception as error:
                errors.append(error)
        worker = threading.Thread(target=tick, name='test-blocking-session-sink')
        worker.start()
        available = False
        try:
            self.assertTrue(entered.wait(2), 'real Session.tick must enter the blocking sink')
            available = self.engine.lock.acquire(blocking=False)
            if available:
                try:
                    # Actual public control and source submit must still work
                    # while the sink remains blocked in the other thread.
                    self.control.hold(True, source='chat')
                    self.session.video(.1, np.full((32, 32, 3), 180, np.uint8), 1, now=10.1)
                    self.assertEqual(self.engine.control.state, 'HOLD')
                    self.assertEqual(self.engine.last_index, 4)
                finally:
                    self.engine.lock.release()
        finally:
            release.set()
            worker.join(2)
        self.assertFalse(worker.is_alive(), 'owned tick thread must be reaped')
        self.assertEqual(errors, [])
        self.assertTrue(available, 'blocking sink must not retain the engine lock needed by control and ingest')

    def test_runtime_retains_selection_guard_across_hold_release_before_writer(self):
        from relay.runtime import run
        from relay.security import Credentials, RelayAddress
        lanes = {name: DetectorLane(name, NoOpDetector(), 30) for name in ('fast', 'accurate')}
        engine = MaskingEngine(lanes, {'fps': 30, 'delay_seconds': .1, 'max_poll_frames': 1})
        stopped = threading.Event()
        captured, changed = [], []
        class Output:
            error_code = error_details = None
            count = max_write_seconds = recovery_count = 0
            recovery_events = ()
            def __init__(inner, *args):
                pass
            def write(inner, frame, pcm):
                captured.append(pcm.copy())
                stopped.set()
                return True
            def close(inner):
                pass
        class Source:
            error_code = last_failure = None
            high_water = active_generation = 0
            timestamp_issues = {}
            def __init__(inner, *args):
                pass
            def drain(inner):
                return []
            def close(inner):
                pass
        def session_factory(engine, sink, **kwargs):
            def adversarial_handoff(frame, pcm):
                session.control.hold(True, source='chat')
                session.control.hold(False, source='chat')
                # This advances buffer synchronization but must not replace the
                # guard for PCM already selected by the presentation clock.
                session.audio(0, np.full(1600, 999, np.int16), generation=1)
                changed.append(True)
                return sink(frame, pcm)
            session = RelaySession(engine, adversarial_handoff, start=time.monotonic() - .2, **kwargs)
            session.video(0, np.full((32, 32, 3), 180, np.uint8), 1, now=session.start)
            session.audio(-1 / 30, np.full(1600, 723, np.int16), generation=1)
            engine.end(0)
            return session
        with patch('relay.runtime.Egress', Output), patch('relay.runtime.NetworkInput', Source), \
                patch('relay.runtime.RelaySession', side_effect=session_factory):
            run(engine, RelayAddress('127.0.0.1'), Credentials.generate(), Credentials.generate(),
                None, stopped, seconds=2, width=32, height=32, encoder='libx264')
        self.assertTrue(stopped.is_set(), 'real runtime writer must deliver the selected PCM')
        self.assertEqual(changed, [True])
        self.assertEqual(len(captured), 1)
        np.testing.assert_array_equal(captured[0], np.zeros(1600, np.int16))

    def test_real_writer_pending_pcm_is_rechecked_after_hold_and_after_release(self):
        for release in (False, True):
            with self.subTest(release=release):
                self.new_session()
                blocked, resume, delivered = threading.Event(), threading.Event(), threading.Event()
                captured = []
                class Output:
                    def write(inner, frame, pcm):
                        captured.append((frame, pcm.copy()))
                        if frame.index == 1:
                            delivered.set()
                        return True
                    def close(inner):
                        pass
                first = [True]
                def gated_hold(frame, active):
                    if first[0]:
                        first[0] = False
                        blocked.set()
                        if not resume.wait(2):
                            raise RuntimeError('test writer gate did not release')
                    return enforce_hold(frame, active)
                with patch('relay.egress.enforce_hold', side_effect=gated_hold):
                    writer = EgressWriter(Output(), lambda: self.engine.control.state == 'HOLD',
                                          audio_guard=self.control.audio_guard)
                    try:
                        def sink(frame, pcm):
                            self.outputs.append((frame, pcm))
                            return writer.write(frame, pcm)
                        self.session.sink = sink
                        self.emit(0, value=500)
                        self.assertTrue(blocked.wait(2), 'real worker must dequeue first output')
                        self.emit(1, value=723)
                        self.control.hold(True, source='chat')
                        if release:
                            self.control.hold(False, source='chat')
                        resume.set()
                        self.assertTrue(delivered.wait(2), 'queued output must reach sink')
                        writer.raise_if_failed()
                        queued = next(pcm for frame, pcm in captured if frame.index == 1)
                        np.testing.assert_array_equal(queued, np.zeros(1600, np.int16))
                    finally:
                        resume.set()
                        writer.close()
                    self.assertFalse(writer.thread.is_alive())

    def test_final_egress_ipc_rechecks_original_guard_after_worker_selection(self):
        for source, release in (('chat', False), ('shield_mode', True), ('transport', False), (None, False)):
            with self.subTest(source=source, release=release):
                self.new_session()
                delivered = threading.Event()
                captured = []
                control = self.control
                class Channel:
                    def settimeout(inner, timeout):
                        # After the writer's check, before Egress sends its IPC.
                        if source:
                            if source == 'transport':
                                self.engine.hold(True, source=source)
                            else:
                                control.hold(True, source=source)
                            if release:
                                control.hold(False, source=source)
                def message(channel, packet):
                    captured.append(packet)
                def reply(operation):
                    delivered.set()
                with patch.object(Egress, '_start'), patch.object(Egress, 'close'), \
                        patch.object(Egress, '_reply', side_effect=reply), \
                        patch('relay.stream._message', side_effect=message):
                    output = Egress('unused-synthetic-boundary', None, width=32, height=32, encoder='libx264')
                    output._channel = Channel()
                    writer = EgressWriter(output, lambda: self.engine.control.state == 'HOLD',
                                          audio_guard=control.audio_guard)
                    try:
                        frame, pcm = self.emit(0)
                        writer.write(frame, pcm)
                        self.assertTrue(delivered.wait(2), 'real Egress.write must reach IPC')
                        writer.raise_if_failed()
                        self.assertEqual(len(captured), 1)
                        operation, (_, sent_pcm) = captured[0]
                        self.assertEqual(operation, 'write')
                        np.testing.assert_array_equal(sent_pcm, np.full(1600, 723 if source in (None, 'transport') else 0, np.int16))
                    finally:
                        writer.close()
                    self.assertFalse(writer.thread.is_alive())


if __name__ == '__main__':
    unittest.main()

"""Actual NetworkInput reader across a six-second destination stall (synthetic CC0)."""
from fractions import Fraction
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import av
import numpy as np

from relay.runtime import run
from relay.security import Credentials, RelayAddress
from relay.stream import NetworkInput
from recovery_fixture import engine


class IngestDuringStall(unittest.TestCase):
    def test_destination_stall_keeps_real_reader_connected_and_resumes_fresh_hold(self):
        stopped, blocked = threading.Event(), threading.Event()
        writes, inputs, controls = [], [], []
        times = {}
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(2)
        producer_errors = []

        def publish():
            try:
                connection, _ = listener.accept()
                with connection, connection.makefile('wb', buffering=0) as wire:
                    with av.open(wire, 'w', format='nut') as output:
                        video = output.add_stream('rawvideo', rate=30)
                        video.width, video.height, video.pix_fmt = 64, 32, 'bgr24'
                        start = time.monotonic()
                        index = 0
                        while not stopped.is_set():
                            if stopped.wait(max(0, start + index / 30 - time.monotonic())):
                                break
                            frame = av.VideoFrame.from_ndarray(np.full((32, 64, 3), 231, np.uint8), format='bgr24')
                            frame.pts, frame.time_base = index, Fraction(1, 30)
                            for packet in video.encode(frame):
                                output.mux(packet)
                            index += 1
            except (BrokenPipeError, ConnectionResetError):
                pass  # The test owns and closes its reader before the publisher.
            except Exception as error:
                if not inputs or not inputs[0].stopped.is_set():
                    producer_errors.append(type(error).__name__)

        class Output:
            error_code = error_details = None
            count = max_write_seconds = recovery_count = 0
            recovery_events = ()
            def __init__(self, *args):
                pass
            def write(self, frame, pcm):
                if len(writes) >= 10 and not blocked.is_set():
                    times['blocked'] = time.monotonic()
                    blocked.set()
                    time.sleep(6)
                    times['resumed'] = time.monotonic()
                writes.append((frame.index, frame.presented_at, frame.state, bool(frame.pixels.any()), time.monotonic()))
                self.count += 1
                return True
            def close(self):
                pass

        def incoming(_):
            source = NetworkInput(f'tcp://127.0.0.1:{listener.getsockname()[1]}')
            inputs.append(source)
            return source

        def moderate():
            if blocked.wait(5):
                controls[0].hold(True, source='twitch-chat', reason='moderator')
                times['hold'] = time.monotonic()

        publisher = threading.Thread(target=publish, name='pr5-synthetic-publisher')
        moderator = threading.Thread(target=moderate, name='pr5-synthetic-moderator')
        publisher.start()
        moderator.start()
        source_engine = engine(delay=.05)
        try:
            with tempfile.TemporaryDirectory() as directory, patch('relay.runtime.Egress', Output), patch('relay.runtime.NetworkInput', incoming):
                summary = run(source_engine, RelayAddress('127.0.0.1'), Credentials.generate(), Credentials.generate(),
                              directory, stopped, seconds=9, width=64, height=32, encoder='libx264',
                              control_ready=controls.append)
        finally:
            stopped.set()
            publisher.join(3)
            moderator.join(2)
            listener.close()
        self.assertFalse(publisher.is_alive() or moderator.is_alive())
        self.assertTrue(blocked.is_set(), 'the actual destination must stall')
        self.assertGreaterEqual(times['resumed'] - times['blocked'], 6)
        self.assertEqual(inputs[0].failures, 0, 'egress must never backpressure the real reader')
        self.assertEqual(producer_errors, [])
        self.assertEqual(inputs[0].active_generation, 1, 'ingest must stay connected')
        self.assertEqual(summary['session']['disconnections'], 0)
        self.assertLessEqual(summary['input_queue_high_water'], 8)
        self.assertTrue(any(row[2] == 'LIVE' and row[3] for row in writes[:10]), 'fixture must exercise actual LIVE pixels before HOLD')
        fresh = [row for row in writes if row[4] > times['resumed'] + .05]
        self.assertGreater(len(fresh), 5)
        self.assertTrue(all(row[1] >= times['resumed'] and row[2] == 'HOLD' and not row[3] for row in fresh), fresh)
        self.assertEqual([row[0] for row in writes], sorted(set(row[0] for row in writes)))

    def test_real_reader_drops_oldest_burst_without_reconnecting(self):
        stopped = threading.Event()
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(2)
        def publish():
            try:
                connection, _ = listener.accept()
                with connection, connection.makefile('wb', buffering=0) as wire:
                    with av.open(wire, 'w', format='nut') as output:
                        stream = output.add_stream('rawvideo', rate=30)
                        stream.width, stream.height, stream.pix_fmt = 64, 32, 'bgr24'
                        for index in range(90):
                            frame = av.VideoFrame.from_ndarray(np.full((32,64,3), index, np.uint8), format='bgr24')
                            frame.pts, frame.time_base = index, Fraction(1,30)
                            for packet in stream.encode(frame):
                                output.mux(packet)
                        stopped.wait(4)
            except (OSError, av.error.PyAVCallbackError):
                pass  # Closing the test-owned reader releases a blocked publisher.
        publisher = threading.Thread(target=publish, name='pr5-burst-publisher')
        publisher.start()
        source = NetworkInput(f'tcp://127.0.0.1:{listener.getsockname()[1]}')
        try:
            deadline = time.monotonic()+2
            while source.dropped < 60 and time.monotonic()<deadline:
                stopped.wait(.005)
            self.assertGreater(source.dropped, 0, 'fixture must overflow the bounded media queue')
            self.assertEqual(source.failures, 0, 'a decode burst must not tear down healthy ingest')
            rows = source.drain()
            self.assertTrue(rows)
            self.assertTrue(all(row[0]=='video' for row in rows))
            self.assertGreater(max(row[1] for row in rows), 1., 'retain fresh frames rather than the old queue head')
            self.assertLessEqual(source.high_water, 8)
            self.assertEqual(source.active_generation, 1)
        finally:
            stopped.set()
            source.close()
            publisher.join(3)
            listener.close()
        self.assertFalse(publisher.is_alive())

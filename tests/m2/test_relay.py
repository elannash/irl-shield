"""Exercise real NUT media at the engine/transport boundary, without sockets."""
from fractions import Fraction
from io import BytesIO, StringIO
import json
import os
import threading
import unittest

import av
import numpy as np

from relay.bridge import NoOpDetector, bridge_nut
from relay.media import local_url
from shield.engine import MaskingEngine
from shield.lanes import DetectorLane
from shield.types import Coverage, PresentedFrame


class DeadlineAdapter:
    """Deterministic adapter at the same engine interface as the live engine."""
    def __init__(self, source_waiting, release_eof):
        self.source_waiting = source_waiting
        self.release_eof = release_eof
        self.frames = {}
        self.ended = self.closed = self.presented_before_end = False
        self.last_index = None
        self.next_index = 0

    def submit(self, frame, now=None):
        self.frames[frame.index] = frame

    def poll(self, now=None):
        if not self.frames or (not self.ended and not self.source_waiting.is_set()):
            return []
        if not self.ended and self.next_index:
            return []
        index = self.next_index
        if self.ended and index > self.last_index:
            return []
        self.next_index += 1
        self.presented_before_end |= not self.ended
        self.release_eof.set()
        frame = self.frames.get(index)
        first = self.frames[0]
        pts = frame.pts if frame else first.pts + index / 30
        pixels = np.zeros_like(first.pixels)
        return [PresentedFrame(index, pts, pixels, np.full(pixels.shape[:2], 255, np.uint8), [],
                               Coverage(None, None, False, 'fixture protection'), 'PROTECT',
                               10 + pts, 10 + pts, True, True)]

    def end(self, last_index=None):
        self.ended = True
        self.last_index = last_index

    @property
    def drained(self):
        return self.ended and self.next_index > self.last_index

    @property
    def stats(self):
        return {}

    def hold(self, active=True):
        pass

    def close(self):
        self.closed = True


class RelayBoundary(unittest.TestCase):
    def test_polls_stalled_input_emits_only_engine_pixels_and_drains_exact_timestamps(self):
        source = BytesIO()
        pcm_parts = []
        with av.open(source, "w", format="nut") as fixture:
            video = fixture.add_stream("rawvideo", rate=30)
            video.width, video.height, video.pix_fmt = 16, 8, "bgr24"
            video.time_base = video.codec_context.time_base = Fraction(1, 90)
            audio = fixture.add_stream("pcm_s16le", rate=48000)
            audio.layout = "mono"
            audio.time_base = audio.codec_context.time_base = Fraction(1, 48000)
            for index in range(6):
                samples = (np.arange(1600, dtype=np.int16) + index * 1600).reshape(1, -1)
                pcm_parts.append(samples.tobytes())
                sound = av.AudioFrame.from_ndarray(samples, format="s16", layout="mono")
                sound.sample_rate = 48000
                source_index = index if index == 0 else index + 1
                sound.pts, sound.time_base = 48000 + source_index * 1600, Fraction(1, 48000)
                for packet in audio.encode(sound):
                    fixture.mux(packet)
                frame = av.VideoFrame.from_ndarray(np.full((8, 16, 3), 20 + index, np.uint8), format="bgr24")
                frame.pts, frame.time_base = 90 + source_index * 3, Fraction(1, 90)
                for packet in video.encode(frame):
                    fixture.mux(packet)
            for stream in (video, audio):
                for packet in stream.encode():
                    fixture.mux(packet)
        output = BytesIO()
        events = StringIO()
        source_waiting, release_eof = threading.Event(), threading.Event()
        engine = DeadlineAdapter(source_waiting, release_eof)
        read_fd, write_fd = os.pipe()
        writer_errors = []

        def write_fixture():
            try:
                with os.fdopen(write_fd, 'wb', buffering=0) as writer:
                    writer.write(source.getvalue())
                    source_waiting.set()
                    if not release_eof.wait(timeout=2):
                        raise RuntimeError('Engine was never polled while source waited at EOF')
            except Exception as error:
                writer_errors.append(error)

        writer = threading.Thread(target=write_fixture)
        writer.start()
        try:
            with os.fdopen(read_fd, 'rb', buffering=0) as incoming:
                bridge_nut(incoming, output, engine, events)
        finally:
            release_eof.set()
            writer.join(timeout=3)
        self.assertFalse(writer.is_alive())
        self.assertEqual(writer_errors, [])
        self.assertTrue(engine.presented_before_end)
        self.assertEqual(engine.last_index, 6)
        self.assertTrue(engine.drained)
        self.assertTrue(engine.closed)
        output.seek(0)
        pixels, video_times, audio_times, pcm = [], [], [], []
        with av.open(output, format="nut") as result:
            for packet in result.demux():
                for frame in packet.decode():
                    if isinstance(frame, av.VideoFrame):
                        pixels.append(int(frame.to_ndarray(format="bgr24")[0, 0, 0]))
                        video_times.append(frame.pts * frame.time_base)
                    else:
                        audio_times.append(frame.pts * frame.time_base)
                        pcm.append(frame.to_ndarray().tobytes())
        self.assertEqual(pixels, [0] * 7)
        expected_times = [Fraction(1) + Fraction(index, 30) for index in range(7)]
        self.assertEqual(video_times, expected_times)
        self.assertEqual(audio_times, [expected_times[index] for index in (0, 2, 3, 4, 5, 6)])
        self.assertEqual(b"".join(pcm), b"".join(pcm_parts))
        presentations = [json.loads(line) for line in events.getvalue().splitlines()
                         if json.loads(line)['event'] == 'video']
        self.assertEqual([row['state'] for row in presentations], ['PROTECT'] * 7)
        self.assertTrue(all(row['coverage']['reason'] == 'fixture protection' for row in presentations))
        self.assertTrue(all(row['protected'] and row['slate'] for row in presentations))
        self.assertEqual([row['deadline'] for row in presentations], [11 + index / 30 for index in range(7)])

    def test_actual_deadline_engine_hold_is_preserved_through_nut(self):
        source = BytesIO()
        with av.open(source, 'w', format='nut') as fixture:
            video = fixture.add_stream('rawvideo', rate=30)
            video.width, video.height, video.pix_fmt = 16, 8, 'bgr24'
            video.time_base = video.codec_context.time_base = Fraction(1, 90)
            frame = av.VideoFrame.from_ndarray(np.full((8, 16, 3), 91, np.uint8), format='bgr24')
            frame.pts, frame.time_base = 90, Fraction(1, 90)
            for packet in video.encode(frame):
                fixture.mux(packet)
            for packet in video.encode():
                fixture.mux(packet)
        source.seek(0)
        before_threads = set(threading.enumerate())
        lanes = {name: DetectorLane(name, NoOpDetector(), 30) for name in ('fast', 'accurate')}
        engine = MaskingEngine(lanes, {'fps': 30, 'delay_seconds': .1})
        engine.hold(True, reason='fixture hold')
        output, events = BytesIO(), StringIO()
        bridge_nut(source, output, engine, events)
        output.seek(0)
        with av.open(output, format='nut') as result:
            frames = list(result.decode(video=0))
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].pts * frames[0].time_base, Fraction(1))
        self.assertFalse(frames[0].to_ndarray(format='bgr24').any())
        presentations = [json.loads(line) for line in events.getvalue().splitlines()
                         if json.loads(line)['event'] == 'video']
        self.assertEqual(len(presentations), 1)
        self.assertEqual(presentations[0]['state'], 'HOLD')
        self.assertTrue(presentations[0]['protected'])
        self.assertTrue(presentations[0]['slate'])
        self.assertGreaterEqual(presentations[0]['presented_at'], presentations[0]['deadline'])
        self.assertTrue(engine.drained)
        self.assertEqual(set(threading.enumerate()) - before_threads, set())

    def test_transport_boundary_rejects_public_hosts_and_embedded_credentials(self):
        for value in ("rtmp://8.8.8.8:1935/live/test", "srt://example.com:9999",
                      "rtmp://user:password@127.0.0.1:1935/live/test", "http://127.0.0.1:80"):
            with self.subTest(url=value), self.assertRaises(ValueError):
                local_url(value)
        self.assertEqual(local_url("rtmp://127.0.0.1:19460/live/m2"), "rtmp")
        self.assertEqual(local_url("srt://100.80.90.100:19460?mode=listener"), "srt")


if __name__ == "__main__":
    unittest.main()

"""CPU media checks at the live transport interfaces; no GPU or live service."""
from fractions import Fraction
import hashlib
import multiprocessing
import json
from pathlib import Path
import secrets
import socket
import tempfile
import threading
import time
import traceback
import unittest

import av
import numpy as np

from relay.stream import Egress, NetworkInput
from shield.types import Coverage, PresentedFrame


def presented(index):
    pixels = np.full((32, 64, 3), 240 if index == 15 else 24, np.uint8)
    return PresentedFrame(index, index / 30, pixels, np.full((32, 64), 255, np.uint8), [],
                          Coverage(None, None, False, 'synthetic hold'), 'HOLD',
                          index / 30 + 1, index / 30 + 1, True, True)


def packets(source):
    with av.open(source) as incoming:
        extra = {stream.type: stream.codec_context.extradata for stream in incoming.streams}
        rows = [(p.stream.type, p.pts, p.dts, p.duration, p.time_base, p.is_keyframe, bytes(p))
                for p in incoming.demux() if p.size]
    return extra, rows


class EgressMedia(unittest.TestCase):
    def test_packets_headers_keyframes_and_flash_beep_survive_fanout_and_flush(self):
        with tempfile.TemporaryDirectory() as directory:
            network = str(Path(directory) / 'network.flv')
            output = Egress(network, directory, width=64, height=32, encoder='libx264')
            try:
                for index in range(30):
                    pcm = np.zeros(1600, np.int16)
                    if index == 15:
                        pcm[:] = (12000 * np.sin(2 * np.pi * 1000 * np.arange(1600) / 48000)).astype(np.int16)
                    output.write(presented(index), pcm)
                self.assertEqual(output.count, 30)
            finally:
                output.close()
            output.close()
            archive = Path(directory) / 'encoded.flv'
            network_extra, network_packets = packets(network)
            archive_extra, archive_packets = packets(str(archive))
            self.assertTrue(network_extra['video'])
            self.assertTrue(network_extra['audio'])
            self.assertEqual(archive_extra, network_extra)
            self.assertEqual(archive_packets, network_packets)
            self.assertTrue(next(row for row in archive_packets if row[0] == 'video')[5])
            with av.open(str(archive)) as incoming:
                video = list(incoming.decode(video=0))
            self.assertEqual(len(video), 30)
            flash_time = max(video, key=lambda frame: frame.to_ndarray().mean()).pts * video[0].time_base
            self.assertEqual([frame.pts * frame.time_base - video[0].pts * video[0].time_base
                              for frame in video[:4]],
                             [Fraction(0), Fraction(33, 1000), Fraction(67, 1000), Fraction(1, 10)])
            with av.open(str(archive)) as incoming:
                audio = list(incoming.decode(audio=0))
            self.assertGreaterEqual(sum(frame.samples for frame in audio), 48000)
            beep = max(audio, key=lambda frame: np.abs(frame.to_ndarray()).max())
            self.assertLess(abs(float(beep.pts * beep.time_base - flash_time)), 1 / 30)
            rows = [json.loads(line) for line in (Path(directory) / 'frames.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows), 30)
            self.assertTrue(all(row['protected'] and row['slate'] for row in rows))
            self.assertEqual(rows[15]['pixels_sha256'], hashlib.sha256(presented(15).pixels.tobytes()).hexdigest())

    def test_current_hold_overrides_precomputed_live_frame_at_native_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            network = str(Path(directory) / 'network.flv')
            output = Egress(network, directory, width=64, height=32, encoder='libx264')
            try:
                output.hold_active = lambda: True
                for index in range(6):
                    frame = presented(index)
                    frame.state, frame.slate, frame.protected = 'LIVE', False, False
                    frame.pixels[:] = 231
                    frame.mask[:] = 0
                    output.write(frame, np.zeros(1600, np.int16))
            finally:
                output.close()
            with av.open(network) as incoming:
                decoded = list(incoming.decode(video=0))
            self.assertEqual(len(decoded), 6)
            self.assertTrue(all(frame.to_ndarray(format='bgr24').max() <= 2 for frame in decoded),
                            'a precomputed LIVE result crossed the native seam after HOLD')
            rows = [json.loads(line) for line in (Path(directory)/'frames.jsonl').read_text().splitlines()]
            self.assertTrue(all(row['state'] == 'HOLD' and row['slate'] for row in rows))

    def test_rejects_raw_frames_bad_audio_and_replayed_timestamps_without_encoding(self):
        before = set(multiprocessing.active_children())
        with tempfile.TemporaryDirectory() as directory:
            output = Egress(str(Path(directory) / 'network.flv'), directory,
                            width=64, height=32, encoder='libx264')
            pcm = np.zeros(1600, np.int16)
            try:
                for result, sound in ((presented(0).pixels, pcm), (presented(0), pcm[:100])):
                    with self.assertRaisesRegex(RuntimeError, '^egress-frame-contract$'):
                        output.write(result, sound)
                self.assertEqual(output.count, 0)
                output.write(presented(0), pcm)
                with self.assertRaisesRegex(RuntimeError, '^egress-frame-contract$'):
                    output.write(presented(0), pcm)
                self.assertEqual(output.count, 1)
            finally:
                output.close()
            output.close()
            with self.assertRaisesRegex(RuntimeError, '^egress-closed$'):
                output.write(presented(1), pcm)
            self.assertEqual(set(multiprocessing.active_children()), before)

    def test_native_rtmp_handshake_stall_fails_safely_and_reaps_worker(self):
        before = set(multiprocessing.active_children())
        stopped, accepted = threading.Event(), threading.Event()
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(.1)

        def stall():
            while not stopped.is_set():
                try:
                    connection, _ = listener.accept()
                except socket.timeout:
                    continue
                with connection:
                    accepted.set()
                    stopped.wait(10)
                return

        server = threading.Thread(target=stall, name='synthetic-rtmp-stall')
        server.start()
        credential = secrets.token_urlsafe(24)
        output = None
        try:
            with tempfile.TemporaryDirectory() as directory:
                url = f'rtmp://127.0.0.1:{listener.getsockname()[1]}/shielded?user=synthetic&pass={credential}'
                output = Egress(url, directory, width=64, height=32, encoder='libx264')
                output.write(presented(0), np.zeros(1600, np.int16))
                try:
                    output.close()
                except RuntimeError as error:
                    diagnostic = ''.join(traceback.format_exception(error))
                    self.assertTrue(credential not in diagnostic, 'credential appeared in a safe exception')
                    self.assertTrue(url not in diagnostic, 'credentialed URL appeared in a safe exception')
                    self.assertEqual(str(error), 'egress-cleanup-timeout')
                else:
                    self.fail('a stalled native RTMP handshake was reported as success')
                self.assertTrue(accepted.is_set())
                self.assertEqual(output.error_code, 'egress-cleanup-timeout')
                self.assertEqual(output.error_details['operation'], 'network-startup')
                self.assertEqual(set(multiprocessing.active_children()), before)
                output.close()
        finally:
            if output is not None:
                output.close()
            stopped.set()
            server.join(timeout=2)
            listener.close()
        self.assertFalse(server.is_alive())


class InputMedia(unittest.TestCase):
    def test_nonfull_eof_rejects_invalid_generation_until_new_reader_media(self):
        from io import BytesIO
        from relay.live import RelaySession
        from recovery_fixture import engine

        # Real demux/EOF owns invalidation. The existing full-queue EOF case
        # discards the queue and cannot catch DROP followed by old media.
        for queued in (1, 4, 7):
            with self.subTest(queued=queued):
                payload = BytesIO()
                with av.open(payload, 'w', format='nut') as movie:
                    stream = movie.add_stream('rawvideo', rate=30)
                    stream.width, stream.height, stream.pix_fmt = 64, 32, 'bgr24'
                    for index in range(queued):
                        frame = av.VideoFrame.from_ndarray(np.full((32, 64, 3), 64, np.uint8), format='bgr24')
                        frame.pts, frame.time_base = index, Fraction(1, 30)
                        for packet in stream.encode(frame):
                            movie.mux(packet)
                    for packet in stream.encode():
                        movie.mux(packet)
                stopped, release_new = threading.Event(), threading.Event()
                reconnected = threading.Event()
                listener = socket.socket()
                listener.bind(('127.0.0.1', 0))
                listener.listen(2)
                listener.settimeout(.1)
                errors = []

                def accept():
                    while not stopped.is_set():
                        try:
                            return listener.accept()[0]
                        except socket.timeout:
                            continue
                    return None

                def publish():
                    try:
                        first = accept()
                        if first is None:
                            return
                        with first:
                            first.sendall(payload.getvalue())
                        second = accept()
                        if second is None:
                            return
                        with second:
                            reconnected.set()
                            while not release_new.wait(.05):
                                if stopped.is_set():
                                    return
                            if stopped.is_set():
                                return
                            with second.makefile('wb', buffering=0) as wire, av.open(
                                    wire, 'w', format='nut', options={'flush_packets': '1'}) as movie:
                                stream = movie.add_stream('rawvideo', rate=30)
                                stream.width, stream.height, stream.pix_fmt = 64, 32, 'bgr24'
                                index = 0
                                while not stopped.is_set():
                                    frame = av.VideoFrame.from_ndarray(np.full((32, 64, 3), 180, np.uint8), format='bgr24')
                                    frame.pts, frame.time_base = index, Fraction(1, 30)
                                    for packet in stream.encode(frame):
                                        movie.mux(packet)
                                    index += 1
                                    stopped.wait(1 / 30)
                    except Exception as error:
                        if not stopped.is_set():
                            errors.append(type(error).__name__)

                publisher = threading.Thread(target=publish, name='eof-generation-publisher')
                publisher.start()
                source = NetworkInput(f'tcp://127.0.0.1:{listener.getsockname()[1]}')
                model = engine(delay=.01)
                written = []
                session = RelaySession(model, lambda frame, pcm: written.append(frame), width=64, height=32)
                try:
                    # error_code precedes DROP publication. A real second accept
                    # proves the EOF reader finished that handoff before drain.
                    self.assertTrue(reconnected.wait(5), errors)
                    self.assertEqual(source.error_code, 'input-eof', errors)
                    self.assertEqual(source.high_water, queued, 'exercise exactly the non-full queue size')
                    rows = source.drain()
                    self.assertTrue(rows)
                    self.assertEqual(rows[0][0], 'drop')
                    invalid = rows[0][3]
                    for kind, pts, value, generation, arrived in rows:
                        if kind == 'video':
                            session.video(pts, value, generation, now=arrived)
                        elif kind == 'audio':
                            session.audio(pts, value, generation)
                        else:
                            session.disconnected()
                    session.tick(now=session.start + .12)
                    self.assertTrue(written, 'the interval must contain actual presented frames')
                    self.assertEqual(model.control.state, 'HOLD', 'old generation must not clear the drop HOLD')
                    self.assertTrue(all(frame.state == 'HOLD' and frame.slate and not frame.pixels.any()
                                        for frame in written))
                    self.assertFalse(any(row[0] in ('video', 'audio') and row[3] <= invalid for row in rows),
                                     'invalidated media must not follow the DROP row')
                    self.assertEqual(session.stats['disconnections'], 1)
                    release_new.set()
                    newer = []
                    deadline = time.monotonic() + 5
                    while not newer and time.monotonic() < deadline:
                        batch = source.drain()
                        self.assertFalse(any(row[0] in ('video', 'audio') and row[3] <= invalid for row in batch))
                        newer = [row for row in batch if row[0] == 'video']
                        if not newer:
                            stopped.wait(.005)
                    self.assertTrue(newer, errors)
                    first = newer[0]
                    self.assertGreater(first[3], invalid)
                    session.video(first[1], first[2], first[3], now=first[4])
                    self.assertEqual(session.generation, first[3])
                    self.assertEqual(session.source_origin, first[1], 'new generation must be re-anchored')
                    self.assertNotEqual(model.control.state, 'HOLD', 'only the newer first frame clears transport HOLD')
                finally:
                    stopped.set()
                    release_new.set()
                    source.close()
                    model.close()
                    publisher.join(3)
                    listener.close()
                self.assertFalse(publisher.is_alive())
                self.assertEqual(errors, [])

    def test_file_eof_invalidates_generation_and_close_discards_owned_frames(self):
        before = set(threading.enumerate())
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'camera.nut')
            with av.open(path, 'w', format='nut') as fixture:
                video = fixture.add_stream('rawvideo', rate=30)
                video.width, video.height, video.pix_fmt = 64, 32, 'bgr24'
                for index in range(30):
                    frame = av.VideoFrame.from_ndarray(presented(index).pixels, format='bgr24')
                    frame.pts, frame.time_base = index, Fraction(1, 30)
                    for packet in video.encode(frame):
                        fixture.mux(packet)
                for packet in video.encode():
                    fixture.mux(packet)
            eof_published, release_eof = threading.Event(), threading.Event()

            class SettledFileInput(NetworkInput):
                def _send(self, item):
                    super()._send(item)
                    if item[0] == 'drop' and item[2] == 'input-eof':
                        # Keep the real EOF boundary stable until it is inspected.
                        eof_published.set()
                        release_eof.wait()

            source = SettledFileInput(path)
            try:
                self.assertTrue(eof_published.wait(2), 'reader did not publish EOF invalidation')
                rows = source.drain()
                self.assertGreater(source.dropped, 0, 'producer may not wait forever on a full event queue')
                self.assertLessEqual(source.high_water, 8)
                self.assertLessEqual(len(rows), 8)
                self.assertEqual(rows[0][0], 'drop', 'no stale pixels may precede an invalidated generation')
                self.assertEqual(rows[0][2], 'input-eof')
            finally:
                release_eof.set()
                source.close()
            source.close()
            self.assertEqual(source.drain(), [])
            self.assertEqual(set(threading.enumerate()), before)


if __name__ == '__main__':
    unittest.main()

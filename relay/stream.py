"""Bounded decoder and sole encoder for the persistent engine transport."""
import base64
from dataclasses import asdict
from fractions import Fraction
import hashlib
from io import BytesIO
import json
import math
import multiprocessing
import pickle
import resource
import socket
import struct
from pathlib import Path
from queue import Empty, Full, Queue
import threading
import time
import zlib

import av
import numpy as np

from shield.types import PresentedFrame


class NetworkInput:
    """Reconnect the loopback MediaMTX RTSP/TCP reader; credentials stay in memory."""
    def __init__(self, url):
        av.logging.set_level(None)
        self.url = url
        self.messages = Queue(maxsize=8)
        self.stopped = threading.Event()
        self.dropped = self.high_water = 0
        self.failures = 0
        self.error_code = None
        self.thread = threading.Thread(target=self._read, name='m2-input', daemon=True)
        self.thread.start()

    def _send(self, item):
        if self.stopped.is_set():
            return
        self.messages.put_nowait(item)
        self.high_water = max(self.high_water, self.messages.qsize())

    def _discard(self):
        while True:
            try:
                self.messages.get_nowait()
                self.dropped += 1
            except Empty:
                return

    def _read(self):
        generation = 0
        while not self.stopped.is_set():
            generation += 1
            reason = 'input-open'
            try:
                with av.open(self.url, timeout=(2., 1.), container_options={
                        'rtsp_transport': 'tcp', 'probesize': '32768',
                        'analyzeduration': '100000', 'rw_timeout': '1000000'}) as incoming:
                    for stream in incoming.streams:
                        stream.codec_context.thread_count = 2
                    resampler = av.AudioResampler(format='s16', layout='mono', rate=48000)
                    reason = 'input-decode'
                    for packet in incoming.demux():
                        if self.stopped.is_set():
                            break
                        for frame in packet.decode():
                            if frame.pts is None or frame.time_base is None:
                                reason = 'input-timestamp'
                                raise ValueError
                            if isinstance(frame, av.VideoFrame):
                                self._send(('video', float(frame.pts * frame.time_base),
                                            frame.to_ndarray(format='bgr24'), generation, time.monotonic()))
                            elif isinstance(frame, av.AudioFrame):
                                for sound in resampler.resample(frame):
                                    if sound.pts is None or sound.time_base is None:
                                        reason = 'input-timestamp'
                                        raise ValueError
                                    self._send(('audio', float(sound.pts * sound.time_base),
                                                sound.to_ndarray().reshape(-1), generation, time.monotonic()))
                    for sound in resampler.resample(None):
                        if sound.pts is None or sound.time_base is None:
                            reason = 'input-timestamp'
                            raise ValueError
                        self._send(('audio', float(sound.pts * sound.time_base),
                                    sound.to_ndarray().reshape(-1), generation, time.monotonic()))
                    reason = 'input-eof'
            except Full:
                # A socket timeout cannot unblock a producer waiting on Queue.
                # Invalidate this generation rather than presenting stale video.
                reason = 'input-backpressure'
                self.failures += 1
            except Exception:
                # Retain the fixed phase, never a libav diagnostic or URL.
                self.failures += 1
            if self.stopped.is_set():
                break
            self.error_code = reason
            if reason != 'input-eof' or self.messages.full():
                self._discard()
            self._send(('drop', None, reason, generation, time.monotonic()))
            self.stopped.wait(.2)

    def drain(self, limit=16):
        rows = []
        for _ in range(limit):
            try:
                rows.append(self.messages.get_nowait())
            except Empty:
                break
        return rows

    def close(self):
        self.stopped.set()
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            raise RuntimeError('input-close-timeout')
        self._discard()
        self.url = None


class EgressError(RuntimeError):
    """Only fixed codes cross the transport seam, never libav URLs/errors."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _message(channel, value):
    data = pickle.dumps(value, protocol=5)
    channel.sendall(struct.pack('!I', len(data)) + data)


def _receive(channel, timeout=None):
    # This socketpair is private to our parent/child, never a network listener.
    deadline = None if timeout is None else time.monotonic() + timeout

    def read(size):
        data = bytearray()
        while len(data) < size:
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                channel.settimeout(remaining)
            chunk = channel.recv(size - len(data))
            if not chunk:
                raise EOFError
            data.extend(chunk)
        return data

    size, = struct.unpack('!I', read(4))
    if size > 64 * 1024 * 1024:
        raise ValueError('egress-message-size')
    return pickle.loads(read(size))


class _EncodedOutput:
    """Owned by the killable worker; only write() accepts encoder pixels."""
    def __init__(self, url, directory, width, height, encoder):
        self.phase = 'encoder-startup'
        self.out = self.archive = self.manifest = None
        self.ready = False
        self.pending = []
        self.packet_types = set()
        self.url = url
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            archive_path = self.directory / 'encoded.flv'
            self.archive = av.open(str(archive_path), 'w', format='flv', options={
                'flvflags': 'no_duration_filesize', 'flush_packets': '1'})
            self.video = self.archive.add_stream(encoder, rate=30)
            self.video.width, self.video.height, self.video.pix_fmt = width, height, 'yuv420p'
            self.video.bit_rate = 2_500_000
            self.video.codec_context.max_b_frames = 0
            self.video.codec_context.gop_size = 30
            self.video.codec_context.thread_count = 2
            self.video.time_base = self.video.codec_context.time_base = Fraction(1, 30)
            self.video.options = ({'preset': 'p4', 'tune': 'ull', 'zerolatency': '1'}
                                  if encoder == 'h264_nvenc' else
                                  {'realtime': '1', 'allow_sw': '0'} if encoder == 'h264_videotoolbox' else
                                  {'preset': 'ultrafast', 'tune': 'zerolatency'})
            self.audio = self.archive.add_stream('aac', rate=48000)
            self.audio.layout = 'mono'
            self.audio.bit_rate = 128000
            self.audio.codec_context.thread_count = 2
            self.audio.time_base = self.audio.codec_context.time_base = Fraction(1, 48000)
            self.archive.start_encoding()
            self.manifest = (self.directory / 'frames.jsonl').open('w')
            self.ready = True
        except BaseException:
            self.close(flush=False)
            raise

    def _mux(self, packet):
        clone = av.Packet(bytes(packet))
        clone.pts, clone.dts = packet.pts, packet.dts
        clone.duration, clone.time_base = packet.duration, packet.time_base
        clone.is_keyframe, clone.is_corrupt = packet.is_keyframe, packet.is_corrupt
        for side in packet.iter_sidedata():
            clone.set_sidedata(side)
        kind = packet.stream.type
        self.phase = 'archive-mux'
        self.archive.mux(packet)
        if self.out is not None:
            clone.stream = self.streams[kind]
            self.phase = 'network-mux'
            self.out.mux(clone)
            return
        self.pending.append((kind, clone))
        self.packet_types.add(kind)
        if len(self.pending) > 16:
            raise EgressError('egress-encoder-delay')
        if self.packet_types != {'video', 'audio'}:
            return
        # PyAV templates from encoders open another encoder and regenerate
        # extradata. Parse our first packets to get decoder templates instead.
        # Header-only FLV probing crashes this bundled libav; wait for both
        # streams, bounded above by 16 packets, without submitting dummy pixels.
        self.phase = 'network-startup'
        self.out = av.open(self.url, 'w', format='flv', options={'flvflags': 'no_duration_filesize'})
        with av.open(BytesIO((self.directory / 'encoded.flv').read_bytes()), format='flv') as header:
            self.streams = {}
            for stream in header.streams:
                copied = self.out.add_stream_from_template(stream, opaque=True)
                # add_stream_from_template does not copy the stream time base.
                copied.time_base = stream.time_base
                if stream.type == 'video':
                    # The startup fragment has SPS/PPS but no decoded picture.
                    # Its decoder template can have 0x0 dimensions; the sole
                    # encoder already owns the negotiated immutable shape.
                    copied.width, copied.height = self.video.width, self.video.height
                    # The encoded packets are still Annex B. Both FLV muxers
                    # must see the encoder's original extradata to perform the
                    # same Annex-B -> length-prefixed packet conversion.
                    copied.codec_context.extradata = self.video.codec_context.extradata
                self.streams[stream.type] = copied
        if set(self.streams) != {'video', 'audio'}:
            raise EgressError('egress-header')
        if any(stream.codec_context.is_encoder for stream in self.streams.values()):
            raise EgressError('egress-duplicate-encoder')
        self.out.start_encoding()
        for kind, pending in self.pending:
            pending.stream = self.streams[kind]
            self.phase = 'network-mux'
            self.out.mux(pending)
        self.pending.clear()

    def write(self, result, pcm):
        frame = av.VideoFrame.from_ndarray(result.pixels, format='bgr24')
        frame.pts, frame.time_base = result.index, Fraction(1, 30)
        sound = av.AudioFrame.from_ndarray(pcm.reshape(1, -1), format='s16', layout='mono')
        sound.sample_rate = 48000
        sound.pts, sound.time_base = result.index * 1600, Fraction(1, 48000)
        self.phase = 'video-encode'
        for packet in self.video.encode(frame):
            self._mux(packet)
        self.phase = 'audio-encode'
        for packet in self.audio.encode(sound):
            self._mux(packet)
        row = {'index': result.index, 'pts': result.pts, 'state': result.state,
               'protected': result.protected, 'slate': result.slate, 'coverage': asdict(result.coverage),
               'deadline': result.deadline, 'presented_at': result.presented_at,
               'encoded_at_monotonic': time.monotonic(),
               'pixels_sha256': hashlib.sha256(result.pixels.tobytes()).hexdigest(),
               'mask_sha256': hashlib.sha256(result.mask.tobytes()).hexdigest(),
               'mask_shape': list(result.mask.shape),
               'mask_packbits_zlib_base64': base64.b64encode(zlib.compress(np.packbits(result.mask != 0).tobytes())).decode(),
               'audio_pcm_sha256': hashlib.sha256(pcm.tobytes()).hexdigest(),
               'audio_pts_samples': result.index * 1600, 'audio_samples': 1600}
        self.phase = 'manifest-write'
        self.manifest.write(json.dumps(row) + '\n')
        self.manifest.flush()

    def close(self, flush=True):
        failed = False
        if flush and self.ready:
            # Flush each independently: failure in one cannot skip the other.
            for stream in (self.video, self.audio):
                try:
                    for packet in stream.encode():
                        self._mux(packet)
                except Exception:
                    failed = True
        for resource in (self.out, self.archive, self.manifest):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    failed = True
        self.out = self.archive = self.manifest = None
        self.ready = False
        if failed:
            raise EgressError('egress-cleanup') from None


def _encode_worker(channel, url, directory, width, height, encoder):
    # A native crash must not persist runtime URL credentials in a core dump.
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    av.logging.set_level(None)
    output = None
    phase = 'egress-startup'
    try:
        output = _EncodedOutput(url, directory, width, height, encoder)
        _message(channel, ('ok', None))
        while True:
            command, value = _receive(channel)
            if command == 'close':
                phase = 'egress-cleanup'
                output.close()
                output = None
                _message(channel, ('ok', None))
                return
            phase = 'egress-write'
            output.write(*value)
            _message(channel, ('ok', None))
    except BaseException as error:
        try:
            number = getattr(error, 'errno', None)
            _message(channel, ('error', {
                'phase': phase, 'operation': output.phase if output is not None else 'encoder-startup',
                'error_class': type(error).__name__, 'errno': number if type(number) is int else None,
                'message': 'Encoder operation failed; upstream text suppressed'}))
        except Exception:
            pass  # Parent disappeared; there is no remaining diagnostic sink.
    finally:
        if output is not None:
            try:
                output.close(flush=False)
            except Exception:
                pass  # An error reply already failed the parent's operation.
        channel.close()


class Egress:
    """One encoder accepts PresentedFrame + 1600 mono int16 samples at 30fps.

    The worker owns native muxing: PyAV 16 output AVIO has no interrupt
    callback, so only process isolation bounds a stalled RTMP open/write/close.
    URLs travel in multiprocessing's private spawn pipe, never child argv.
    libx264 is an explicit CPU transport-check adapter; hardware stays default.
    Calls are synchronous with at most one in-flight frame and no frame queue.
    """
    def __init__(self, url, directory, width=1280, height=720, encoder='h264_nvenc'):
        if encoder not in ('h264_nvenc', 'h264_videotoolbox', 'libx264'):
            raise ValueError('Unsupported egress encoder')
        if any(type(n) is not int or n < 2 or n % 2 for n in (width, height)):
            raise ValueError('Expected even egress dimensions')
        self.width, self.height = width, height
        self.directory = Path(directory)
        self.count = 0
        self.error_code = None
        self.error_details = None
        self.max_write_seconds = 0.
        self._last_index = None
        self._closed = False
        self._channel, worker_channel = socket.socketpair()
        self._channel.settimeout(5)
        self._process = multiprocessing.get_context('spawn').Process(
            target=_encode_worker, args=(worker_channel, url, str(directory), width, height, encoder),
            name='m2-egress')
        try:
            self._process.start()
        except BaseException:
            self._channel.close()
            self._process.close()
            raise EgressError('egress-startup') from None
        finally:
            worker_channel.close()
        self._reply('egress-startup')

    def _stop(self):
        self._closed = True
        self._channel.close()
        self._process.join(timeout=.5)
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=2)
        if self._process.is_alive():
            self._process.kill()
            self._process.join(timeout=2)
        if self._process.is_alive():
            raise EgressError('egress-worker-survived') from None
        self._process.close()

    def _fail(self, code, details=None):
        self.error_code = code
        self.error_details = details
        self._stop()
        raise EgressError(code) from None

    def _reply(self, phase):
        try:
            status, details = _receive(self._channel, timeout=5)
        except TimeoutError:
            self._fail(phase + '-timeout', {'phase': phase, 'error_class': 'TimeoutError',
                                          'message': 'Encoder reply deadline exceeded'})
        except Exception as error:
            self._fail(phase, {'phase': phase, 'error_class': type(error).__name__,
                               'message': 'Encoder channel failed; upstream text suppressed'})
        if status != 'ok':
            self._fail(phase, details)

    def write(self, result, pcm):
        began = time.monotonic()
        if self._closed:
            raise EgressError('egress-closed')
        if (not isinstance(result, PresentedFrame)
                or type(result.index) is not int or result.index < 0
                or not math.isfinite(result.pts) or abs(result.pts - result.index / 30) > 1e-7
                or (self._last_index is not None and result.index != self._last_index + 1)
                or not isinstance(result.pixels, np.ndarray) or result.pixels.dtype != np.uint8
                or result.pixels.shape != (self.height, self.width, 3)
                or not isinstance(result.mask, np.ndarray) or result.mask.shape != (self.height, self.width)
                or not isinstance(pcm, np.ndarray) or pcm.dtype != np.int16 or pcm.shape != (1600,)):
            raise EgressError('egress-frame-contract')
        try:
            self._channel.settimeout(5)
            _message(self._channel, ('write', (result, pcm)))
        except TimeoutError:
            self._fail('egress-write-timeout')
        except Exception:
            self._fail('egress-write')
        try:
            self._reply('egress-write')
        finally:
            self.max_write_seconds = max(self.max_write_seconds, time.monotonic() - began)
        self._last_index = result.index
        self.count += 1

    def close(self):
        if self._closed:
            return
        try:
            self._channel.settimeout(5)
            _message(self._channel, ('close', None))
        except TimeoutError:
            self._fail('egress-cleanup-timeout')
        except Exception:
            self._fail('egress-cleanup')
        self._reply('egress-cleanup')
        self._stop()



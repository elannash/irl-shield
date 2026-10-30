"""Bounded decoder and sole encoder for the persistent engine transport."""
import base64
from collections import Counter, deque
from dataclasses import asdict, replace
from fractions import Fraction
import hashlib
from io import BytesIO
import json
import math
import multiprocessing
import pickle
import resource
import random
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
from relay.archive import Archive, MuxSink

_OPERATIONS = ('unknown', 'encoder-startup', 'archive-mux', 'network-mux',
               'network-startup', 'video-encode', 'audio-encode', 'manifest-write')


class NetworkInput:
    """Reconnect the loopback MediaMTX RTSP/TCP reader; credentials stay in memory."""
    def __init__(self, url):
        av.logging.set_level(None)
        self.url = url
        self.messages = Queue(maxsize=8)
        self._drop_lock = threading.Lock()
        self._pending_drop = None
        self._invalid_generation = 0
        self.stopped = threading.Event()
        self.dropped = self.high_water = 0
        self.failures = 0
        self.failure_counts = Counter()
        self.drop_events = deque(maxlen=64)
        self.error_code = None
        self.last_failure = None
        self.active_generation = 0
        self.timestamp_issues = {'missing': 0, 'nonincreasing': 0, 'last': None}
        self._previous_pts = {}
        self.thread = threading.Thread(target=self._read, name='m2-input', daemon=True)
        self.thread.start()

    def _send(self, item):
        if self.stopped.is_set():
            return
        if item[0] == 'drop':
            # Media replacement must never evict the transport HOLD signal.
            # Multiple failures coalesce; aggregate counts preserve their causes.
            with self._drop_lock:
                self._invalid_generation = max(self._invalid_generation, item[3])
                self._pending_drop = item
            return
        while not self.stopped.is_set():
            try:
                self.messages.put_nowait(item)
                self.high_water = max(self.high_water, self.messages.qsize())
                return
            except Full:
                # A decode burst is not a broken connection. Keep the newest
                # media; the engine protects honest gaps and audio becomes silence.
                try:
                    self.messages.get_nowait()
                    self.dropped += 1
                except Empty:
                    continue

    def _discard(self):
        while True:
            try:
                self.messages.get_nowait()
                self.dropped += 1
            except Empty:
                return

    def _timestamp(self, frame, kind, generation):
        previous = self._previous_pts.get(kind)
        missing = frame.pts is None or frame.time_base is None
        pts = None if missing else float(frame.pts * frame.time_base)
        if missing or previous is not None and pts <= previous:
            self.timestamp_issues['missing' if missing else 'nonincreasing'] += 1
            self.timestamp_issues['last'] = {'kind': kind, 'generation': generation,
                                             'pts': pts, 'previous_pts': previous,
                                             'at_monotonic': time.monotonic()}
        if missing:
            raise ValueError
        self._previous_pts[kind] = pts
        return pts

    def _read(self):
        generation = 0
        while not self.stopped.is_set():
            generation += 1
            self._previous_pts.clear()
            reason = 'input-open'
            error_class = None
            try:
                with av.open(self.url, timeout=(2., 1.), container_options={
                        'rtsp_transport': 'tcp', 'probesize': '32768',
                        'analyzeduration': '100000', 'rw_timeout': '1000000'}) as incoming:
                    self.active_generation = generation
                    for stream in incoming.streams:
                        stream.codec_context.thread_count = 2
                    resampler = av.AudioResampler(format='s16', layout='mono', rate=48000)
                    reason = 'input-decode'
                    for packet in incoming.demux():
                        if self.stopped.is_set():
                            break
                        for frame in packet.decode():
                            if isinstance(frame, av.VideoFrame):
                                reason = 'input-timestamp'
                                pts = self._timestamp(frame, 'video', generation)
                                reason = 'input-decode'
                                self._send(('video', pts,
                                            frame.to_ndarray(format='bgr24'), generation, time.monotonic()))
                            elif isinstance(frame, av.AudioFrame):
                                reason = 'input-timestamp'
                                self._timestamp(frame, 'decoded-audio', generation)
                                reason = 'input-decode'
                                for sound in resampler.resample(frame):
                                    reason = 'input-timestamp'
                                    pts = self._timestamp(sound, 'audio', generation)
                                    reason = 'input-decode'
                                    self._send(('audio', pts,
                                                sound.to_ndarray().reshape(-1), generation, time.monotonic()))
                    for sound in resampler.resample(None):
                        reason = 'input-timestamp'
                        pts = self._timestamp(sound, 'audio', generation)
                        reason = 'input-decode'
                        self._send(('audio', pts,
                                    sound.to_ndarray().reshape(-1), generation, time.monotonic()))
                    reason = 'input-eof'
            except Exception as error:
                # Retain the fixed phase, never a libav diagnostic or URL.
                error_class = type(error).__name__
                self.failures += 1
            if self.stopped.is_set():
                break
            self.failure_counts[reason] += 1
            self.drop_events.append({'code': reason, 'generation': generation,
                                     'at_monotonic': time.monotonic(), 'initiator': 'reader'})
            self.error_code = reason
            self.last_failure = {'code': reason, 'error_class': error_class,
                                 'generation': generation, 'at_monotonic': time.monotonic()}
            if reason != 'input-eof' or self.messages.full():
                self._discard()
            self._send(('drop', None, reason, generation, time.monotonic()))
            self.stopped.wait(.2)

    def drain(self, limit=16):
        rows = []
        # Publish invalidation and media as one ordered reader boundary. A
        # buffered frame cannot release transport HOLD after its DROP, even
        # when EOF left fewer than eight items in the media queue.
        with self._drop_lock:
            if limit > 0:
                if self._pending_drop is not None:
                    rows.append(self._pending_drop)
                    self._pending_drop = None
            for _ in range(limit - len(rows)):
                try:
                    item = self.messages.get_nowait()
                except Empty:
                    break
                if item[3] <= self._invalid_generation:
                    self.dropped += 1
                    continue
                rows.append(item)
        return rows

    def close(self):
        self.stopped.set()
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            raise RuntimeError('input-close-timeout')
        self._discard()
        with self._drop_lock:
            self._pending_drop = None
        self.url = None


def enforce_hold(result, active):
    if active and not result.slate:
        return replace(result, pixels=np.zeros_like(result.pixels), mask=np.full_like(result.mask, 255),
                       quads=[], state='HOLD', protected=True, slate=True)
    return result


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
    @property
    def phase(self):
        return self._phase

    @phase.setter
    def phase(self, value):
        self._phase = value
        self._progress[0] = _OPERATIONS.index(value)
        self._progress[1] = time.monotonic()

    def __init__(self, url, directory, width, height, encoder, progress, generation, recoveries):
        self._progress = progress
        self.generation = generation
        self.phase = 'encoder-startup'
        self.out = self.archive = None
        self.ready = False
        self.pending = []
        self.packet_types = set()
        self.urls = (url,) if isinstance(url, str) else tuple(url)
        if not 1 <= len(self.urls) <= 2 or not all(isinstance(u, str) and u for u in self.urls):
            raise EgressError('egress-destinations')
        self.outputs = []
        self.evidence = Archive(directory)
        self.directory = self.evidence.directory
        try:
            if recoveries:
                self.evidence.text('egress-recovery.jsonl', ''.join(json.dumps(e) + '\n' for e in recoveries))
            name = 'encoded.flv' if generation == 1 else f'encoded-g{generation:04d}.flv'
            self._mux_sink = MuxSink(self.evidence, name)
            self.archive = av.open(self._mux_sink, 'w', format='flv', options={
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
            if self.evidence.check():
                manifest_path = self.directory / 'frames.jsonl'
                try:
                    if generation > 1 and manifest_path.exists() and manifest_path.stat().st_size:
                        with manifest_path.open('rb+') as previous:
                            previous.seek(-1, 2)
                            if previous.read(1) != b'\n':
                                previous.write(b'\n')
                    self.evidence.text('frames.jsonl', '', 'w' if generation == 1 else 'a')
                except OSError:
                    self.evidence.enabled = False
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
            self._network_mux(kind, clone)
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
        for url in self.urls:
            self.out = av.open(url, 'w', format='flv', options={'flvflags': 'no_duration_filesize'})
            with av.open(BytesIO(bytes(self._mux_sink.prefix)), format='flv') as header:
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
            self.outputs.append((self.out, self.streams))
        for kind, pending in self.pending:
            self._network_mux(kind, pending)
        self.pending.clear()
        self._mux_sink.prefix = None

    def _network_mux(self, kind, packet):
        for output, streams in self.outputs:
            clone = av.Packet(bytes(packet))
            clone.pts, clone.dts = packet.pts, packet.dts
            clone.duration, clone.time_base = packet.duration, packet.time_base
            clone.is_keyframe, clone.is_corrupt = packet.is_keyframe, packet.is_corrupt
            for side in packet.iter_sidedata():
                clone.set_sidedata(side)
            clone.stream = streams[kind]
            self.phase = 'network-mux'
            output.mux(clone)

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
        if not self.evidence.check():
            return
        row = {'index': result.index, 'pts': result.pts, 'state': result.state,
               'egress_generation': self.generation,
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
        self.evidence.text('frames.jsonl', json.dumps(row) + '\n')

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
        networks = [output for output, _ in self.outputs]
        if self.out is not None and self.out not in networks:
            networks.append(self.out)
        for resource in (*networks, self.archive):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    failed = True
        self.out = self.archive = None
        self.outputs.clear()
        self.evidence.close()
        self.urls = ()
        self.ready = False
        if failed:
            raise EgressError('egress-cleanup') from None


def _encode_worker(channel, url, directory, width, height, encoder, progress, generation, recoveries):
    # A native crash must not persist runtime URL credentials in a core dump.
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    av.logging.set_level(None)
    output = None
    phase = 'egress-startup'
    try:
        output = _EncodedOutput(url, directory, width, height, encoder, progress, generation, recoveries)
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
            progress[2] = value[0].index
            output.write(*value)
            progress[3] = value[0].index
            _message(channel, ('ok', {'network_ready': output.out is not None}))
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
    """One encoder and at most one in-flight frame, with bounded transport recovery.

    write() returns False to discard a precomputed batch, None for an accepted
    recovery frame awaiting network readiness, and True when ready. The next
    writer receives a fresh engine result, never the failed frame.
    Credentials remain in memory and the private spawn pipe, never argv/logs.
    """
    def __init__(self, url, directory, width=1280, height=720, encoder='h264_nvenc'):
        if encoder not in ('h264_nvenc', 'h264_videotoolbox', 'libx264'):
            raise ValueError('Unsupported egress encoder')
        if any(type(n) is not int or n < 2 or n % 2 for n in (width, height)):
            raise ValueError('Expected even egress dimensions')
        self.width, self.height = width, height
        self.directory = Path(directory) if directory is not None else None
        self._url, self._encoder = url, encoder
        self.hold_active = lambda: False
        self.count = self.recovery_count = 0
        self.error_code = self.error_details = None
        self.max_write_seconds = 0.
        self.generation = 1
        self.recovery_events = deque(maxlen=64)
        self._outage_started = None
        self._retry_attempts = 0
        self._pending_events = deque(maxlen=64)
        self._last_index = None
        self._last_attempted = -1
        self._closed = self._terminal = self._recovering = False
        self._worker_reaped = True
        self._fresh_after = self._retry_at = 0.
        self._network_ready = False
        self._start()

    def _start(self):
        if not self._worker_reaped:
            raise EgressError('egress-worker-survived')
        self._channel, worker_channel = socket.socketpair()
        self._channel.settimeout(5)
        context = multiprocessing.get_context('spawn')
        self._progress = context.Array('d', [0., time.monotonic(), -1., -1.], lock=False)
        self._process = context.Process(target=_encode_worker,
            args=(worker_channel, self._url, str(self.directory) if self.directory is not None else None, self.width, self.height,
                  self._encoder, self._progress, self.generation, list(self._pending_events)),
            name='m2-egress')
        self._worker_reaped = self._closed = False
        self._network_ready = False
        try:
            self._process.start()
        except BaseException as error:
            self._channel.close()
            self._process.close()
            self._worker_reaped = self._closed = True
            self.error_code = 'egress-startup'
            self.error_details = {'phase': 'egress-startup', 'operation': 'encoder-startup',
                                  'error_class': type(error).__name__,
                                  'message': 'Encoder process could not start'}
            raise EgressError('egress-startup') from None
        finally:
            worker_channel.close()
        self._reply('egress-startup')
        self._pending_events.clear()

    def _stop(self):
        self._closed = True
        if self._worker_reaped:
            return
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
        self._worker_reaped = True

    def _fail(self, code, details=None):
        self.error_code, self.error_details = code, details
        self._stop()
        raise EgressError(code) from None

    def _reply(self, phase):
        try:
            status, details = _receive(self._channel, timeout=5)
        except TimeoutError:
            self._fail(phase + '-timeout', {'phase': phase, 'error_class': 'TimeoutError',
                'operation': _OPERATIONS[int(self._progress[0])],
                'operation_started_at': self._progress[1],
                'operation_age_seconds': time.monotonic() - self._progress[1],
                'active_frame_index': int(self._progress[2]),
                'completed_frame_index': int(self._progress[3]),
                'message': 'Encoder reply deadline exceeded'})
        except Exception as error:
            self._fail(phase, {'phase': phase, 'error_class': type(error).__name__,
                              'message': 'Encoder channel failed; upstream text suppressed'})
        if status != 'ok':
            self._fail(phase, details)
        if isinstance(details, dict):
            self._network_ready = details['network_ready']

    def _recover(self, error, index):
        if not self._worker_reaped:
            raise EgressError('egress-worker-survived') from None
        now = time.monotonic()
        if self._outage_started is None:
            self._outage_started = now
        if self._retry_attempts >= 5 and now - self._outage_started >= 60:
            self._terminal = True
            self.error_code = 'egress-recovery-limit'
            self.error_details = {'phase': 'egress-recovery',
                                  'operation': (self.error_details or {}).get('operation', 'unknown'),
                                  'error_class': 'EgressError', 'minimum_failures': 5, 'budget_seconds': 60,
                                  'message': 'Egress outage time budget exhausted'}
            raise EgressError(self.error_code) from None
        self._retry_attempts += 1
        self.recovery_count += 1
        event = {'event': 'egress-recovery', 'code': error.code,
                 'operation': (self.error_details or {}).get('operation', 'unknown'),
                 'at_monotonic': now, 'failed_index': index,
                 'generation': self.generation, 'next_generation': self.generation + 1,
                 'attempt_in_outage': self._retry_attempts,
                 'budget_seconds': 60, 'minimum_failures': 5, 'old_worker_reaped': True}
        self.recovery_events.append(event)
        self._pending_events.append(event)
        self._recovering = True
        delay = min(8., .5 * 2 ** min(self._retry_attempts - 1, 4))
        self._fresh_after = now
        self._retry_at = now + delay + random.uniform(0., delay * .2)
        self._last_attempted = max(self._last_attempted, index)

    def write(self, result, pcm):
        began = time.monotonic()
        if self._terminal or self._closed and not self._recovering:
            raise EgressError('egress-closed')
        if (not isinstance(result, PresentedFrame)
                or type(result.index) is not int or result.index < 0
                or not math.isfinite(result.pts) or abs(result.pts - result.index / 30) > 1e-7
                or (not self._recovering and self._last_index is not None
                    and result.index <= self._last_index)
                or not isinstance(result.pixels, np.ndarray) or result.pixels.dtype != np.uint8
                or result.pixels.shape != (self.height, self.width, 3)
                or not isinstance(result.mask, np.ndarray) or result.mask.shape != (self.height, self.width)
                or not isinstance(pcm, np.ndarray) or pcm.dtype != np.int16 or pcm.shape != (1600,)):
            raise EgressError('egress-frame-contract')
        if self._recovering and (result.index <= self._last_attempted
                                 or result.presented_at < self._fresh_after):
            return False
        try:
            if self._closed:
                if time.monotonic() < self._retry_at:
                    return False
                self.generation += 1
                try:
                    self._start()
                except EgressError as error:
                    if error.code == 'egress-worker-survived':
                        raise
                    self._recover(error, result.index)
                    return False
                # A control can change while hardware/startup is blocked. Do
                # not send the result computed before that startup completed.
                self._fresh_after = time.monotonic()
                self._last_attempted = result.index
                return False
            self._last_attempted = result.index
            try:
                self._channel.settimeout(5)
                # Re-read control after startup and queue waits, at the native handoff.
                result = enforce_hold(result, self.hold_active())
                guard = getattr(self, 'audio_guard', None)
                if guard is not None:
                    pcm = guard(pcm)
                _message(self._channel, ('write', (result, pcm)))
            except TimeoutError:
                self._fail('egress-write-timeout')
            except Exception:
                self._fail('egress-write')
            self._reply('egress-write')
        except EgressError as error:
            if not error.code.startswith('egress-write'):
                raise
            self._recover(error, result.index)
            return False
        finally:
            self.max_write_seconds = max(self.max_write_seconds, time.monotonic() - began)
        self._last_index = result.index
        self.count += 1
        if self._recovering:
            if not self._network_ready:
                return None
            self._recovering = False
            self._outage_started = None
            self._retry_attempts = 0
            self.error_code = self.error_details = None
        return True

    def close(self):
        if self._terminal or self._closed:
            self._terminal = True
            if not self._worker_reaped:
                self._stop()
            return
        self._terminal = True
        try:
            self._channel.settimeout(5)
            _message(self._channel, ('close', None))
        except TimeoutError:
            self._fail('egress-cleanup-timeout')
        except Exception:
            self._fail('egress-cleanup')
        self._reply('egress-cleanup')
        self._stop()



"""GStreamer transport adapters for the unchanged clocked source/engine/sink seam."""
from collections import OrderedDict, deque
from dataclasses import replace
from fractions import Fraction
import json
import math
from pathlib import Path
import queue
import threading
import time
import zipfile

import numpy as np

from relay.gst_native import Pipeline, SECOND
from relay.media import local_url
from shield.types import Frame


def quoted(value):
    return json.dumps(str(value))


class DetectorCopies:
    """Bounded source-indexed resized pixels; absence is an explicit ingest error."""
    def __init__(self, capacity):
        self.capacity = capacity
        self.frames = OrderedDict()
        self.lock = threading.Lock()

    def put(self, index, resolution, pixels):
        for value in pixels.values():
            value.setflags(write=False)
        with self.lock:
            self.frames[index] = pixels
            while len(self.frames) > self.capacity:
                self.frames.popitem(last=False)

    def get(self, index, width):
        with self.lock:
            try:
                return self.frames[index][width]
            except KeyError as error:
                raise RuntimeError(f'Missing GStreamer detector copy for frame {index}, width {width}') from error


class CopyLane:
    """Offer GStreamer-scaled copies to an existing newest-frame DetectorLane."""
    def __init__(self, lane, copies, width, resolution):
        self.lane, self.copies, self.width = lane, copies, width
        self.resolution = resolution

    def offer(self, frame):
        pixels = self.copies.get(frame.index, self.width)
        self.lane.offer(Frame(frame.index, frame.pts, pixels))

    def drain(self):
        width, height = self.resolution
        scaled_height = round(height * self.width / width)
        return [replace(result, quads=[[[x * width / self.width, y * height / scaled_height]
                                       for x, y in quad] for quad in result.quads])
                for result in self.lane.drain()]

    @property
    def stats(self):
        return self.lane.stats

    def close(self):
        self.lane.close()


class GstSource:
    """Paced H.264 source with bounded full-frame and PTS-matched detector copies.

    File cycles reopen the decoder; their startup cost is intentionally measured.
    A live URL runs for a declared duration so EOF/loss cannot invent a long tail.
    input_chain accepts a trusted local GStreamer raw source for synthetic checks.
    """
    def __init__(self, path, media, *, total_frames=None, detector_widths=(),
                 decoder='nvh264dec', delay_seconds=1., audio=False, input_chain=None):
        if decoder not in ('nvh264dec', 'vtdec', 'avdec_h264'):
            raise ValueError('Unsupported GStreamer decoder')
        self.path, self.media, self.decoder = path, media, decoder
        self.fps = media['fps']
        self.total_frames = media['frames'] if total_frames is None else total_frames
        if not math.isfinite(self.fps) or self.fps <= 0 or self.total_frames < 1:
            raise ValueError('A positive finite source clock is required')
        if not math.isfinite(delay_seconds) or not 0 <= delay_seconds <= 1:
            raise ValueError('Presentation delay must be between zero and one second')
        self.duration = self.total_frames / self.fps
        self.audio_enabled, self.input_chain = audio, input_chain
        self.widths = sorted(set(detector_widths))
        if any(not isinstance(w, int) or w < 32 for w in self.widths):
            raise ValueError('Detector copy widths must be integers at least 32')
        self.buffer_capacity_frames = max(2, math.ceil(self.fps * (delay_seconds + 1)))
        self.frames = queue.Queue(self.buffer_capacity_frames)
        self.copies = DetectorCopies(self.buffer_capacity_frames + 4)
        self.arrivals, self.decoded_at = {}, {}
        self.queue_drops, self.injected_drops = [], []
        self.audio = deque()
        self.audio_lock = threading.Lock()
        self.audio_bytes = 0
        self.stop, self.finished = threading.Event(), threading.Event()
        self.thread, self.pipeline, self.error = None, None, None
        self.descriptions = []
        self.copy_seconds = []
        self.full_copy_seconds, self.full_copy_cpu_seconds = [], []
        self.reduced_copy_seconds, self.reduced_copy_cpu_seconds = [], []
        self.live = path is not None and str(path).startswith(('srt:', 'rtmp:'))
        self.protocol = local_url(str(path)) if self.live else 'file'
        # MPEG-TS is a 90kHz clock; FLV timestamps have millisecond resolution.
        self.clock_tolerance = {'srt': 1/90000 + 1e-9, 'rtmp': .001 + 1e-9}.get(self.protocol, 1e-5)
        self.original_timestamps = {}

    def description(self):
        width, height = self.media['resolution']
        decoder = self.decoder + (' max-threads=2' if self.decoder == 'avdec_h264' else '')
        if self.input_chain:
            chain = self.input_chain
            demux = None
        elif self.live:
            if local_url(str(self.path)) == 'srt':
                chain = f'srtsrc uri={quoted(self.path)} auto-reconnect=false keep-listening=false poll-timeout=100 ! tsdemux name=demux ignore-pcr=true demux. ! queue ! h264parse ! {decoder}'
            else:
                chain = f'rtmp2src location={quoted(self.path)} ! flvdemux name=demux demux.video ! queue ! h264parse ! {decoder}'
            demux = 'demux.' if str(self.path).startswith('srt:') else 'demux.audio'
        else:
            chain = f'filesrc location={quoted(self.path)} ! qtdemux name=demux demux.video_0 ! queue ! h264parse ! {decoder}'
            demux = 'demux.audio_0'
        chain += (f' ! video/x-raw,width={width},height={height}'
                  ' ! tee name=raw ')
        for name, w in [('frames', width), *[(f'copy{w}', w) for w in self.widths if w != width]]:
            h = round(height * w / width)
            chain += (f'raw. ! queue max-size-buffers=2 max-size-bytes=0 max-size-time=0 ! '
                      f'videoscale n-threads=2 method=bilinear ! video/x-raw,width={w},height={h} ! '
                      f'videoconvert n-threads=2 ! video/x-raw,format=BGR ! '
                      f'appsink name={name} sync=false max-buffers=2 wait-on-eos=false ')
        if self.audio_enabled:
            if demux is None:
                raise ValueError('Synthetic raw input_chain does not carry audio')
            chain += (f'{demux} ! queue max-size-time=3000000000 max-size-bytes=0 max-size-buffers=0 ! '
                      'aacparse ! avdec_aac ! audioconvert ! audioresample ! '
                      'audio/x-raw,format=S16LE,rate=48000,channels=1,layout=interleaved ! '
                      'appsink name=audio sync=false max-buffers=128 wait-on-eos=false')
        return chain

    def start(self, origin):
        self.origin = origin
        self.thread = threading.Thread(target=self._produce, name='gst-source', daemon=True)
        self.thread.start()

    def _audio(self, pipeline, offset_ns, start_ns, end_ns):
        if not self.audio_enabled:
            return
        while (sample := pipeline.pull('audio', 0., video=False)) is not None:
            pts = sample.pts_ns + offset_ns
            first = max(0, round((start_ns - pts) * 48000 / SECOND))
            last = len(sample.data) // 2 if end_ns is None else min(
                len(sample.data) // 2, round((end_ns - pts) * 48000 / SECOND))
            if last <= first:
                continue
            sample = replace(sample, pts_ns=pts + round(first * SECOND / 48000),
                             duration_ns=round((last - first) * SECOND / 48000),
                             data=sample.data[first * 2:last * 2])
            with self.audio_lock:
                self.audio_bytes += len(sample.data)
                if self.audio_bytes > 48000 * 2 * 5:
                    raise RuntimeError('GStreamer audio exceeded five-second bounded queue')
                self.audio.append(sample)

    def poll_audio(self):
        with self.audio_lock:
            result = list(self.audio)
            self.audio.clear()
            self.audio_bytes = 0
            return result

    def _produce(self):
        index = 0
        try:
            while index < self.total_frames and not self.stop.is_set():
                first_pts, count = None, 0
                stream_end, eos_sent = None, False
                description = self.description()
                self.descriptions.append(description)
                with Pipeline(description) as pipeline:
                    self.pipeline = pipeline
                    cycle_start = index
                    cycle_start_ns = round(cycle_start / self.fps * SECOND)
                    cycle_end_ns = None if self.live else round((cycle_start + self.media['frames']) / self.fps * SECOND)
                    deadline = time.monotonic() + 10
                    while index < self.total_frames and not self.stop.is_set():
                        sample = pipeline.pull('frames', .1)
                        if sample is None:
                            if self.live and stream_end is not None and not eos_sent and time.monotonic() >= stream_end:
                                pipeline.signal_eos()
                                eos_sent = True
                            if first_pts is not None:
                                self._audio(pipeline, cycle_start_ns - first_pts, cycle_start_ns, cycle_end_ns)
                            if pipeline.eos('frames'):
                                break
                            if time.monotonic() > deadline:
                                raise TimeoutError('GStreamer source supplied no video for ten seconds')
                            continue
                        began = time.monotonic()
                        if first_pts is None:
                            first_pts = sample.pts_ns
                            stream_end = time.monotonic() + self.duration
                        relative = (sample.pts_ns - first_pts) / SECOND
                        expected = count / self.fps
                        self.original_timestamps[index] = {'pts_ns': sample.pts_ns, 'duration_ns': sample.duration_ns,
                                                           'cfr_error_ns': round((relative-expected)*SECOND)}
                        if not math.isclose(relative, expected, rel_tol=0., abs_tol=self.clock_tolerance):
                            raise RuntimeError('GStreamer input is not the declared constant-rate PTS clock: '
                                               f'frame={count} error_ns={round((relative-expected)*SECOND)} '
                                               f'tolerance_ns={round(self.clock_tolerance*SECOND)}')
                        self.full_copy_seconds.append(sample.copy_seconds)
                        self.full_copy_cpu_seconds.append(sample.copy_cpu_seconds)
                        copies = {}
                        for w in self.widths:
                            if w == self.media['resolution'][0]:
                                copies[w] = sample.pixels
                                continue
                            reduced = pipeline.pull(f'copy{w}', 2.)
                            if reduced is None or reduced.pts_ns != sample.pts_ns:
                                raise RuntimeError('GStreamer detector copy PTS differs from full frame')
                            copies[w] = reduced.pixels
                            self.reduced_copy_seconds.append(reduced.copy_seconds)
                            self.reduced_copy_cpu_seconds.append(reduced.copy_cpu_seconds)
                        decoded = time.monotonic()
                        self.copy_seconds.append(decoded - began)
                        pts = index / self.fps
                        if not self.live and self.stop.wait(max(0., self.origin + pts - time.monotonic())):
                            return
                        self.arrivals[index] = max(self.origin + pts, began) if not self.live else began
                        self.decoded_at[index] = decoded
                        self.copies.put(index, self.media['resolution'], copies)
                        self._audio(pipeline, cycle_start_ns - first_pts, cycle_start_ns, cycle_end_ns)
                        try:
                            self.frames.put_nowait(Frame(index, pts, sample.pixels))
                        except queue.Full:
                            try:
                                dropped = self.frames.get_nowait()
                                self.queue_drops.append(dropped.index)
                            except queue.Empty:
                                pass
                            self.frames.put_nowait(Frame(index, pts, sample.pixels))
                        index += 1
                        count += 1
                        deadline = time.monotonic() + 10
                    self._audio(pipeline, cycle_start_ns - (first_pts or 0), cycle_start_ns, cycle_end_ns)
                self.pipeline = None
                if index < self.total_frames and not self.live and count != self.media['frames']:
                    raise RuntimeError(f'GStreamer source cycle truncated: {count} of {self.media["frames"]} frames')
                if self.live and index < self.total_frames:
                    raise RuntimeError('Live GStreamer input ended before declared duration')
                if not count:
                    raise RuntimeError('GStreamer source decoded no frames')
        except Exception as error:
            self.error = error
        finally:
            self.finished.set()

    def poll(self):
        if self.error is not None:
            raise RuntimeError(f'GStreamer source failed: {self.error}') from self.error
        result = []
        while True:
            try:
                result.append(self.frames.get_nowait())
            except queue.Empty:
                return result

    @property
    def ended(self):
        if self.error is not None:
            raise RuntimeError(f'GStreamer source failed: {self.error}') from self.error
        return self.finished.is_set() and self.frames.empty()

    def close(self):
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=12)
            if self.thread.is_alive():
                raise RuntimeError('GStreamer source did not stop')


class GstSink:
    """Encode only PresentedFrame pixels; observe encoded access units before mux.

    File output retains actual mask bytes for the existing guarded quality scorer.
    Network output is restricted to credential-free literal localhost/Tailscale.
    """
    def __init__(self, path, resolution, fps, *, encoder='nvh264enc', audio_source=None, audio=False,
                 artifacts=None, bitrate_kbps=10000):
        if encoder not in ('nvh264enc', 'vtenc_h264', 'x264enc'):
            raise ValueError('Unsupported GStreamer encoder')
        self.path, self.resolution, self.fps, self.codec = path, resolution, fps, encoder
        self.audio_source, self.audio_enabled = audio_source, audio
        self.live = str(path).startswith(('rtmp:', 'srt:'))
        if self.live:
            local_url(str(path))
            if artifacts is None:
                raise ValueError('Live egress requires a local artifacts path')
        self.artifact = Path(artifacts) if artifacts else Path(path)
        self.artifact.parent.mkdir(parents=True, exist_ok=True)
        self.pipeline, self.masks = None, None
        self.completions, self.progress = [], []
        self.packet_origin = None
        self.submitted = 0
        self.finished = False
        self.write_seconds, self.write_cpu_seconds = [], []
        self.bitrate_kbps = bitrate_kbps
        self.command = self.description()

    def description(self):
        width, height = self.resolution
        rate = Fraction(str(self.fps)).limit_denominator(100000)
        caps = f'video/x-raw,format=BGR,width={width},height={height},framerate={rate.numerator}/{rate.denominator}'
        if self.codec == 'nvh264enc':
            encoder = (f'nvh264enc preset=p4 tune=ultra-low-latency rc-mode=cbr bitrate={self.bitrate_kbps} '
                       f'gop-size={round(self.fps)} bframes=0 rc-lookahead=0 zerolatency=true')
        elif self.codec == 'vtenc_h264':
            encoder = f'vtenc_h264 realtime=true allow-frame-reordering=false bitrate={self.bitrate_kbps} max-keyframe-interval={round(self.fps)}'
        else:
            encoder = (f'x264enc speed-preset=ultrafast tune=zerolatency threads=2 bitrate={self.bitrate_kbps} '
                       f'key-int-max={round(self.fps)} bframes=0 rc-lookahead=0')
        if self.live and local_url(str(self.path)) == 'srt':
            mux_sink = f'mpegtsmux name=mux alignment=7 ! srtsink uri={quoted(self.path)} sync=false'
            video_pad, audio_pad = 'mux.', 'mux.'
        elif self.live:
            mux_sink = f'flvmux name=mux streamable=true ! rtmp2sink location={quoted(self.path)} sync=false'
            video_pad, audio_pad = 'mux.video', 'mux.audio'
        else:
            mux_sink = f'mp4mux name=mux ! filesink location={quoted(self.path)} sync=false'
            video_pad, audio_pad = 'mux.video_0', 'mux.audio_0'
        chain = (f'appsrc name=video is-live=true format=time block=true max-bytes={width * height * 3 * 2} '
                 f'caps={quoted(caps)} ! queue max-size-buffers=2 max-size-bytes=0 max-size-time=0 ! '
                 f'videoconvert n-threads=2 ! video/x-raw,format=NV12 ! {encoder} ! '
                 'h264parse ! video/x-h264,alignment=au ! identity name=egress signal-handoffs=true ! '
                 f'{video_pad} {mux_sink}')
        if self.audio_enabled:
            chain += (f' appsrc name=audio is-live=true format=time block=true max-bytes=192000 '
                      'caps="audio/x-raw,format=S16LE,rate=48000,channels=1,layout=interleaved" ! '
                      'queue max-size-time=2000000000 max-size-bytes=0 max-size-buffers=0 ! '
                      f'audioconvert ! avenc_aac bitrate=128000 ! aacparse ! {audio_pad}')
        return chain

    def start(self):
        self.masks = zipfile.ZipFile(self.artifact.with_suffix('.mask-pixels.zip'), 'w',
                                    compression=zipfile.ZIP_DEFLATED, compresslevel=1)
        self.pipeline = Pipeline(self.command)
        self.pipeline.on_buffer('egress', self._packet)
        self.pipeline.start()
        if self.audio_enabled:
            self.audio_gate = AudioGate(self.pipeline, self.audio_source)

    def _packet(self, pts_ns):
        observed = time.monotonic()
        if self.packet_origin is None:
            self.packet_origin = pts_ns
        normalized = pts_ns - self.packet_origin
        expected = len(self.completions) / self.fps * SECOND
        if abs(normalized - expected) > 10000:
            raise RuntimeError('Encoded access-unit PTS/count differs from submitted frame clock')
        self.progress.append({'packets_written': len(self.completions) + 1, 'observed_at': observed,
                              'pts_ns': normalized, 'codec_pts_ns': pts_ns})
        self.completions.append(observed)

    def write(self, frame):
        began, cpu = time.monotonic(), time.thread_time()
        width, height = self.resolution
        if (frame.index != self.submitted or frame.pixels.dtype != np.uint8 or
                frame.pixels.shape != (height, width, 3) or frame.mask.shape != (height, width) or
                not math.isclose(frame.pts, frame.index / self.fps, abs_tol=1e-5)):
            raise ValueError('Presented frame shape, index or source PTS changed')
        # BGR caps require four-byte aligned rows even for an odd source width.
        stride = (width * 3 + 3) // 4 * 4
        if stride != width * 3:
            pixels = np.zeros((height, stride), np.uint8)
            pixels[:, :width * 3] = frame.pixels.reshape(height, width * 3)
        else:
            pixels = frame.pixels
        pts = round(frame.pts * SECOND)
        duration = round((frame.index + 1) / self.fps * SECOND) - pts
        self.pipeline.push('video', pixels, pts, duration)
        self.masks.writestr(f'{frame.index:08d}.bin', np.packbits(frame.mask > 0, bitorder='little').tobytes())
        self.submitted += 1
        if self.audio_enabled:
            self.audio_gate.release(pts + duration)
        self.write_seconds.append(time.monotonic() - began)
        self.write_cpu_seconds.append(time.thread_time() - cpu)

    def finish(self):
        if self.audio_enabled:
            self.audio_gate.release(round(self.submitted / self.fps * SECOND))
        self.pipeline.end(['video', 'audio'] if self.audio_enabled else ['video'])
        self.pipeline.close()
        self.masks.close()
        self.finished = True
        if len(self.completions) != self.submitted:
            raise RuntimeError('Encoded access-unit count differs from submitted frame count')
        return list(self.completions)

    def abort(self):
        if self.pipeline is not None:
            self.pipeline.close()
        if self.masks is not None:
            self.masks.close()


class AudioGate:
    """Release mono S16LE only up to emitted video PTS; D is wall-clock gating.

    Splitting at sample boundaries prevents a large PCM packet from escaping
    ahead of its matching video. Original relative timestamps survive encoding.
    """
    def __init__(self, pipeline, source):
        self.pipeline, self.source = pipeline, source
        self.pending = deque()
        self.bytes_released = 0
        self.last_end_ns = 0

    def release(self, video_end_ns):
        self.pending.extend(self.source.poll_audio())
        while self.pending:
            sample = self.pending[0]
            if len(sample.data) % 2:
                raise ValueError('Audio contains an incomplete S16LE sample')
            pts, data = sample.pts_ns, sample.data
            if pts < 0:
                trim = min(len(data) // 2, math.ceil(-pts * 48000 / SECOND))
                data = data[trim * 2:]
                pts += round(trim * SECOND / 48000)
            if pts >= video_end_ns:
                return
            samples = min(len(data) // 2, max(0, round((video_end_ns - pts) * 48000 / SECOND)))
            if not samples:
                if not data:
                    self.pending.popleft()
                    continue
                return
            if pts < self.last_end_ns - 25000:
                raise ValueError('Audio source PTS overlaps previously released PCM')
            duration = round(samples * SECOND / 48000)
            self.pipeline.push('audio', data[:samples * 2], pts, duration)
            self.bytes_released += samples * 2
            self.last_end_ns = pts + duration
            self.pending.popleft()
            if len(data) > samples * 2:
                self.pending.appendleft(replace(sample, pts_ns=pts + duration, data=data[samples * 2:]))

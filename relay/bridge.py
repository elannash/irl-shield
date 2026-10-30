"""Adapt timestamped NUT media to the transport-free deadline engine."""
from collections import deque
from dataclasses import asdict
from fractions import Fraction
import io
import json
import os
from queue import Empty, Full, Queue
import select
import threading
import time

import av

from shield.types import Frame


class NoOpDetector:
    def detect(self, frame):
        return []

    def close(self):
        pass


class _InterruptibleInput:
    """A pipe read must yield to shutdown even if its writer never sends EOF."""
    def __init__(self, source, stopped):
        self.source, self.stopped = source, stopped
        try:
            self.fd = source.fileno()
        except (AttributeError, io.UnsupportedOperation):
            self.fd = None

    def read(self, size):
        if self.fd is None:
            return self.source.read(size)
        while not self.stopped.is_set():
            if select.select([self.fd], [], [], .01)[0]:
                return os.read(self.fd, size)
        return b''


def _produce(source, messages, stopped):
    def send(kind, value):
        while not stopped.is_set():
            try:
                messages.put((kind, value), timeout=.01)
                return
            except Full:
                continue

    try:
        reader = _InterruptibleInput(source, stopped)
        with av.open(reader, format='nut', buffer_size=4096,
                     options={'probesize': '32768', 'analyzeduration': '1000'}) as incoming:
            video = incoming.streams.video[0]
            rate = video.average_rate or video.guessed_rate
            if rate is None:
                raise ValueError('Video frame rate is required')
            audio = incoming.streams.audio[0] if incoming.streams.audio else None
            if audio and audio.codec_context.name != 'pcm_s16le':
                raise ValueError('The bridge expects timestamped pcm_s16le audio')
            send('metadata', {'width': video.width, 'height': video.height, 'rate': rate,
                              'time_base': video.time_base,
                              'audio': {'rate': audio.codec_context.sample_rate,
                                        'layout': audio.codec_context.layout.name,
                                        'time_base': audio.time_base} if audio else None})
            for packet in incoming.demux():
                if stopped.is_set():
                    return
                if packet.size == 0:
                    continue
                if packet.stream.type == 'audio':
                    if packet.pts is None or packet.time_base is None:
                        raise ValueError('Audio packet has no timestamp')
                    send('audio', packet)
                elif packet.stream.type == 'video':
                    for frame in packet.decode():
                        if frame.pts is None or frame.time_base is None:
                            raise ValueError('Video frame has no timestamp')
                        send('video', (frame.pts, frame.time_base,
                                       frame.to_ndarray(format='bgr24'), time.monotonic_ns()))
        send('eof', None)
    except Exception as error:
        send('error', error)


def bridge_nut(source, destination, engine, events):
    """Poll independently of demux; mux only engine-presented pixels and gated PCM.

    Engine lifetime belongs to this call. Source and destination remain owned
    by the caller. A bounded producer queue decouples blocking demux from the
    presentation clock; EOF bounds and drains that clock before closing NUT.
    """
    messages, stopped = Queue(maxsize=32), threading.Event()
    producer = threading.Thread(target=_produce, args=(source, messages, stopped),
                                name='shield-demux', daemon=True)
    producer.start()
    timings, audio = {}, deque()
    received = emitted = audio_packets = audio_bytes = 0
    first_pts = video_end = None
    last_source = last_presented = -1

    def event(kind, **fields):
        events.write(json.dumps({'event': kind, **fields}) + '\n')
        events.flush()

    try:
        while True:
            try:
                kind, metadata = messages.get(timeout=.005)
            except Empty:
                continue
            if kind == 'error':
                raise metadata
            if kind != 'metadata':
                raise RuntimeError('NUT producer did not supply stream metadata')
            break
        rate = metadata['rate']
        with av.open(destination, 'w', format='nut', buffer_size=4096,
                     options={'flush_packets': '1', 'max_interleave_delta': '0'}) as outgoing:
            video_out = outgoing.add_stream('rawvideo', rate=rate)
            video_out.width, video_out.height = metadata['width'], metadata['height']
            video_out.pix_fmt = 'bgr24'
            video_out.time_base = video_out.codec_context.time_base = metadata['time_base']
            audio_out = None
            if metadata['audio']:
                info = metadata['audio']
                audio_out = outgoing.add_stream('pcm_s16le', rate=info['rate'])
                audio_out.layout = info['layout']
                audio_out.time_base = info['time_base']
                audio_out.codec_context.time_base = Fraction(1, info['rate'])

            def release_audio(final=False):
                nonlocal audio_packets, audio_bytes
                while audio and (final or (video_end is not None and
                                           audio[0].pts * audio[0].time_base < video_end)):
                    packet = audio.popleft()
                    pts, base, size = packet.pts, packet.time_base, packet.size
                    packet.stream = audio_out
                    outgoing.mux(packet)
                    audio_packets += 1
                    audio_bytes += size
                    event('audio', pts=pts, time_base=str(base), bytes=size)

            def emit(result):
                nonlocal emitted, video_end, last_presented
                original = timings.pop(result.index, None)
                if original is None:
                    base = metadata['time_base']
                    pts = round(Fraction(str(result.pts)) / base)
                    arrived_ns = None
                else:
                    pts, base, arrived_ns = original
                frame = av.VideoFrame.from_ndarray(result.pixels, format='bgr24')
                frame.pts, frame.time_base = pts, base
                for packet in video_out.encode(frame):
                    outgoing.mux(packet)
                emitted += 1
                last_presented = result.index
                video_end = pts * base + Fraction(1, 1) / rate
                release_audio()
                event('video', index=result.index, pts=pts, time_base=str(base),
                      source_frame=original is not None, state=result.state,
                      coverage=asdict(result.coverage), deadline=result.deadline,
                      presented_at=result.presented_at, protected=result.protected, slate=result.slate,
                      stage_ms=(time.monotonic_ns() - arrived_ns) / 1e6 if arrived_ns is not None else None)

            ended = False
            while not (ended and engine.drained):
                try:
                    kind, value = messages.get(timeout=.005)
                except Empty:
                    kind, value = None, None
                if kind == 'error':
                    raise value
                if kind == 'audio':
                    audio.append(value)
                    release_audio()
                elif kind == 'video':
                    pts, base, pixels, arrived_ns = value
                    source_pts = pts * base
                    if first_pts is None:
                        first_pts = source_pts
                    index = round((source_pts - first_pts) * rate)
                    if index > last_presented:
                        timings[index] = (pts, base, arrived_ns)
                    engine.submit(Frame(index, float(source_pts), pixels))
                    received += 1
                    last_source = max(last_source, index)
                elif kind == 'eof':
                    engine.end(last_source)
                    ended = True
                for result in engine.poll():
                    emit(result)
            release_audio(final=True)
            for packet in video_out.encode():
                outgoing.mux(packet)
        if not received or not emitted:
            raise RuntimeError(f'Incomplete video: received={received}, emitted={emitted}')
        event('complete', video_received=received, video_emitted=emitted,
              audio_packets=audio_packets, audio_bytes=audio_bytes, engine=engine.stats)
    finally:
        stopped.set()
        producer.join(timeout=1)
        try:
            engine.close()
        finally:
            if producer.is_alive():
                raise RuntimeError('NUT demux producer did not stop')

"""CC0 synthetic H.264 B-frame/AAC fixture; no text, logos or music."""
from fractions import Fraction
from io import BytesIO

import av
import numpy as np


def mpegts(origin=0, frames=90, width=64, height=64, timing=False):
    payload = BytesIO()
    with av.open(payload, 'w', format='mpegts', options={'mpegts_copyts': '1', 'flush_packets': '1'}) as movie:
        video = movie.add_stream('libx264', rate=30)
        video.width, video.height = width, height
        video.pix_fmt = 'yuv420p'
        video.codec_context.thread_count = 2
        video.codec_context.max_b_frames = 2
        video.codec_context.gop_size = 15
        video.options = {'preset': 'ultrafast', 'bf': '2', 'sc_threshold': '0'}
        audio = movie.add_stream('aac', rate=48000)
        audio.layout = 'mono'
        audio.codec_context.thread_count = 2
        rng = np.random.default_rng(42)
        for index in range(frames):
            if timing:
                from relay.fixture import decorate
                y, x = np.indices((height, width))
                pixels = np.repeat((((x // 32 + y // 32 + index // 15) % 2) * 100 + 50).astype(np.uint8)[:, :, None], 3, axis=2)
                decorate(pixels, index, 1700000000000)
            else:
                pixels = rng.integers(30, 200, (height, width, 3), dtype=np.uint8)
                pixels[:16] = 240 if index % 30 < 3 else 30
            frame = av.VideoFrame.from_ndarray(pixels, format='bgr24')
            frame.pts, frame.time_base = origin * 30 + index, Fraction(1, 30)
            sample = np.arange(1600) + index * 1600
            pcm = (8000 * np.sin(2 * np.pi * (1000 + 100 * ((index // 30) % 16)) * sample / 48000) * (index % 30 < 3)).astype(np.int16)
            sound = av.AudioFrame.from_ndarray(pcm.reshape(1, -1), format='s16', layout='mono')
            sound.sample_rate = 48000
            sound.pts, sound.time_base = origin * 48000 + index * 1600, Fraction(1, 48000)
            for stream, value in ((video, frame), (audio, sound)):
                for packet in stream.encode(value):
                    movie.mux(packet)
        for stream in (video, audio):
            for packet in stream.encode():
                movie.mux(packet)
    return payload.getvalue()


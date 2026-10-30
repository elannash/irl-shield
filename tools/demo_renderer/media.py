"""CPU-only media operations using the existing PyAV and Pillow dependencies."""
from fractions import Fraction
import hashlib
from contextlib import ExitStack, closing

import av
import numpy as np

from .evidence import require, rational


def decode(path, expected):
    """Match exact decoded PTS, never a guessed frame number from a mux clock."""
    remaining = set(expected)
    require(len(remaining) == len(expected), 'Duplicate expected media PTS')
    with av.open(str(path)) as container:
        require(len(container.streams.video) == 1, 'Expected one video stream')
        container.streams.video[0].codec_context.thread_count = 2
        for frame in container.decode(video=0):
            require(frame.pts is not None and frame.time_base is not None, 'Missing decoded PTS')
            pts = Fraction(frame.pts) * frame.time_base
            require(pts in remaining, 'Decoded media/archive PTS mismatch')
            remaining.remove(pts)
            pixels = frame.to_ndarray(format='rgb24')
            digest = expected[pts]
            if digest is not None:
                require(hashlib.sha256(pixels.tobytes()).hexdigest() == digest, 'Decoded source pixels mismatch')
            yield pts, pixels
    require(not remaining, 'Missing decoded media frame')


def pictures(evidence):
    source = evidence.provenance
    expected = {rational(f['pts']): f['pixels_sha256'] for f in source['frames']}
    require(len(source['frames']) == len(evidence.rows), 'Source/archive frame count mismatch')
    with ExitStack() as stack:
        raw = stack.enter_context(closing(decode(evidence.source_root / source['video']['file'], expected)))
        shielded = {}
        for name in evidence.sidecar['encoded_files']:
            expected = {rational(f['encoded_pts']): None for f in evidence.sidecar['frames'] if f['encoded_file'] == name}
            shielded[name] = stack.enter_context(closing(decode(evidence.archive / name, expected)))
        for source_frame, frame, shape in zip(source['frames'], evidence.sidecar['frames'], evidence.mask_shapes, strict=True):
            require(source_frame['index'] == frame['source_index'], 'Source/archive order mismatch')
            raw_pts, before = next(raw, (None, None))
            encoded_pts, after = next(shielded[frame['encoded_file']], (None, None))
            require(raw_pts == rational(source_frame['pts']), 'Raw media frame identity mismatch')
            require(encoded_pts == rational(frame['encoded_pts']), 'Encoded media frame identity mismatch')
            require(before.shape == after.shape and before.shape[:2] == shape, 'Media/mask dimensions disagree')
            yield before, after
        require(next(raw, None) is None, 'Extra raw frame')
        for decoder in shielded.values():
            require(next(decoder, None) is None, 'Extra archive frame')


def encode(path, images, timestamps, fps):
    """No audio is ever copied into a public demo export."""
    timestamps = [rational(t) for t in timestamps]
    origin = timestamps[0]
    # A 90 kHz output clock represents ordinary camera rates exactly. Reject other
    # rates rather than silently round away source identity.
    offsets = [(t-origin)*90000 for t in timestamps]
    require(all(t.denominator == 1 for t in offsets), 'Source PTS cannot be represented at 90 kHz')
    with av.open(str(path), 'w', format='mp4', options={'movflags': '+faststart'}) as container:
        stream = None
        for image, pts in zip(images, offsets, strict=True):
            if stream is None:
                stream = container.add_stream('libx264', rate=Fraction(fps))
                stream.width, stream.height = image.size
                stream.pix_fmt = 'yuv420p'
                stream.codec_context.thread_count = 2
                stream.codec_context.max_b_frames = 0
                stream.time_base = stream.codec_context.time_base = Fraction(1, 90000)
                stream.options = {'preset': 'ultrafast', 'crf': '18', 'tune': 'zerolatency'}
            frame = av.VideoFrame.from_ndarray(np.asarray(image), format='rgb24')
            frame.pts, frame.time_base = int(pts), Fraction(1, 90000)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)

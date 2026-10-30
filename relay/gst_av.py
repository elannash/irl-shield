"""Synthetic flash/beep A/V check (authored CC0; no music, text or logos).

This exercises the unchanged engine with empty control detectors. It measures
transport A/V alignment, never detector privacy. Timings are kept separate from
the 30-second sustained quality/performance receipt.
"""
import json
from pathlib import Path
import subprocess

import cv2
import numpy as np

from bench.clocked_pipeline import probe_media, file_sha256, perf_health
from relay.gst import GstSink
from relay.gst_bench import run_file
from relay.gst_native import Sample, SECOND
from shield.types import Coverage, PresentedFrame


class SyntheticAudio:
    def __init__(self, pcm):
        self.pcm = pcm

    def poll_audio(self):
        data, self.pcm = self.pcm, b''
        return [Sample(0, round(len(data) / 2 / 48000 * SECOND), data=data)] if data else []


def observe(path):
    """Find white-patch video onsets and beep audio onsets in decoded media."""
    media = probe_media(path)
    capture = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 2])
    flashes, previous = [], False
    try:
        index = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            active = float(frame[32:96, 32:128].mean()) > 220
            if active and not previous:
                flashes.append(index / media['fps'])
            previous = active
            index += 1
    finally:
        capture.release()
    command = ['ffmpeg', '-v', 'error', '-threads', '2', '-i', str(path), '-vn',
               '-ac', '1', '-ar', '48000', '-f', 's16le', 'pipe:1']
    pcm = np.frombuffer(subprocess.check_output(command, timeout=30), '<i2')
    # A short envelope closes the sine wave's zero crossings without merging events.
    block = 48
    envelope = np.max(np.abs(pcm[:len(pcm) // block * block].astype(np.int32)).reshape(-1, block), axis=1)
    active = envelope > 4000
    starts = np.flatnonzero(active & ~np.r_[False, active[:-1]]) / 1000
    if len(flashes) != 2 or len(starts) != 2:
        raise RuntimeError(f'A/V event accounting failed: {len(flashes)} flashes, {len(starts)} beeps')
    return {'flashes_seconds': flashes, 'beeps_seconds': starts.tolist(),
            'audio_minus_video_seconds': (starts - np.asarray(flashes)).tolist(),
            'audio_decode_command': command, 'media': media, 'sha256': file_sha256(path),
            'resolution': 'video frame period plus 1ms audio envelope bins'}


def run(directory, encoder, decoder, *, contended=False):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    health = perf_health()
    (directory / 'av-preflight.json').write_text(json.dumps(health, indent=2) + '\n')
    if health['pressure_state'] != 'normal' and not contended:
        raise RuntimeError('Reject A/V generation: memory pressure is ' + health['pressure_state'])
    fps, seconds, rate = 30, 4, 48000
    rng = np.random.default_rng(20261029)
    background = rng.integers(24, 160, (720, 1280, 3), np.uint8)
    t = np.arange(rate * seconds) / rate
    beep = ((t >= 1) & (t < 1.04)) | ((t >= 3) & (t < 3.04))
    pcm = (np.sin(t * 2 * np.pi * 1000) * 12000 * beep).astype('<i2').tobytes()
    source = directory / 'flash-beep.mp4'
    sink = GstSink(source, [1280, 720], fps, encoder=encoder, audio=True, audio_source=SyntheticAudio(pcm))
    try:
        sink.start()
        for index in range(seconds * fps):
            pixels = background.copy()
            if index in (30, 31, 90, 91):
                pixels[32:96, 32:128] = 255
            sink.write(PresentedFrame(index, index / fps, pixels, np.zeros((720, 1280), np.uint8), [],
                                      Coverage(0, 0, True, 'synthetic-source'), 'LIVE', 0., 0., False, False))
        sink.finish()
    finally:
        sink.abort()
    before = observe(source)
    output = directory / 'flash-beep-engine.mp4'
    options = {'transport': 'gst', 'encoder': encoder, 'decoder': decoder, 'audio': True,
               'delay_seconds': 1., 'warmup_seconds': 0., 'fast_width': 640, 'accurate_width': 1280,
               'fast_rate_hz': 30., 'accurate_rate_hz': 30., 'motion_mode': 'phase',
               'contended': contended, 'before': 0, 'after': 2, 'fast_max_age': 2, 'accurate_max_age': 2}
    performance = run_file(source, output, 'unmasked', options)
    after = observe(output)
    offsets = np.asarray(after['audio_minus_video_seconds']) - before['audio_minus_video_seconds']
    receipt = {'source': before, 'output': after, 'introduced_av_offset_seconds': offsets.tolist(),
               'max_absolute_introduced_offset_seconds': float(np.max(np.abs(offsets))),
               'configured_video_delay_seconds': 1., 'protected_fraction': performance['protected_fraction'],
               'audio': performance.get('audio'), 'perf_health': performance['perf_health'],
               'scope': '4s synthetic A/V control only; not a sustained performance or privacy score',
               'license': 'CC0-1.0; authored synthetic noise, white flashes and sine beeps; no music, text or logos'}
    (directory / 'av-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt), flush=True)
    return receipt

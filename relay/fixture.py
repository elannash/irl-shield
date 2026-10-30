"""Verified tune footage with original synthetic labels, optical stamps and tone.

The generated overlays/tone are dedicated to CC0-1.0 by the IRL Shield authors.
This does not change the underlying footage's license or benchmark-only scope.
No source audio is ever decoded or forwarded.
"""
from pathlib import Path
import json

from relay.seal import sha256_file

FPS = 30
SAMPLE_RATE = 48000


def describe_source(manifest_path, clip_id, fixture_root):
    manifest_path, fixture_root = Path(manifest_path), Path(fixture_root)
    manifest = json.loads(manifest_path.read_text())
    matches = [clip for clip in manifest['clips'] if clip['id'] == clip_id]
    if len(matches) != 1:
        raise ValueError('Source must identify one licensed fixture')
    clip = matches[0]
    if clip['split'] != 'tune':
        raise ValueError('Soak uses tune sources only')
    if clip['license'] not in ('CC0', 'CC BY 3.0', 'CC BY 4.0', 'Public domain'):
        raise ValueError('Source license not permitted')
    path = fixture_root / clip['path']
    if not path.resolve().is_relative_to(fixture_root.resolve()):
        raise ValueError('Source path escapes fixture root')
    if sha256_file(path) != clip['sha256']:
        raise ValueError('Source bytes do not match licensed fixture manifest')
    if clip['fps'] != FPS or clip['width'] < 640 or clip['height'] < 128 or clip['duration'] <= 0:
        raise ValueError('Source requires 30fps prepared video')
    return {'schema_version': 1, 'scope': 'BENCHMARK-ONLY; not demo-ready',
            'source': dict(clip, absolute_path=str(path.resolve())),
            'manifest_sha256': sha256_file(manifest_path),
            'audio': 'Original audio discarded; generated frequency-coded timing tones only; no music',
            'synthetic': {'license': 'CC0-1.0', 'author': 'IRL Shield authors',
                          'declaration': 'Original label, flash, optical-stamp and tone generator dedicated to CC0',
                          'labels': ['742 CEDAR LANE', '19 ORCHARD WAY'],
                          'font': 'OpenCV Hershey Simplex', 'flash_bbox': [0, 40, 64, 104],
                          'flash_period_frames': 30, 'flash_duration_frames': 3,
                          'tone_hz': '1000 + 100 * (source pulse index modulo 16)',
                          'tone_period_samples': 48000,
                          'tone_duration_samples': 4800, 'tone_peak': 16000}}


def decorate(pixels, index, epoch_ms):
    """Mutate this source frame; return labels in source pixel coordinates."""
    import cv2
    height, width = pixels.shape[:2]
    text = ('742 CEDAR LANE', '19 ORCHARD WAY')[(index // 150) % 2]
    scale, thickness = max(.5, width / 1100), 2
    (tw, th), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
    x, y = width // 4, height // 2
    cv2.rectangle(pixels, (x - 8, y - th - 8), (x + tw + 8, y + baseline + 8), (255, 255, 255), -1)
    cv2.putText(pixels, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thickness)
    # 48 epoch-millisecond bits, then 16 frame-index bits; < 65536 frames/run.
    value = (epoch_ms << 16) | index
    for bit in range(64):
        pixels[:24, bit * 8:(bit + 1) * 8] = 255 if value & (1 << (63 - bit)) else 0
    pixels[40:104, :64] = 255 if index % FPS < 3 else 0
    return [{'text': text, 'bbox': [x, y - th, x + tw, y + baseline],
             'start_pts': index / FPS, 'end_pts': (index + 1) / FPS}]


def read_stamp(pixels):
    value = 0
    for bit in range(64):
        value = (value << 1) | int(pixels[6:18, bit * 8 + 2:bit * 8 + 6].mean() > 127)
    return value & 65535, value >> 16


def tone(index):
    import numpy as np
    samples = np.arange(index * 1600, (index + 1) * 1600)
    frequency = 1000 + 100 * ((index // FPS) % 16)
    return np.where(samples % SAMPLE_RATE < 4800,
                    16000 * np.sin(2 * np.pi * frequency * samples / SAMPLE_RATE), 0).astype(np.int16)

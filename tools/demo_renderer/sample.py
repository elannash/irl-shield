"""Build an explicitly illustrative archive. No detector or native evidence is claimed."""
import argparse
import base64
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import zlib

import av
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .evidence import sha256, require
from .layout import ROOT, FONT


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n')


def sample(directory, background=None, frames=16, width=640, height=360):
    if background is not None:
        approved = json.loads((ROOT/'fixtures/demo-renderer/ATTRIBUTION.json').read_text())['assets'][0]
        require(sha256(background) == approved['sha256'], 'Unapproved synthetic background')
    directory = Path(directory)
    require(not directory.exists(), 'Refusing to overwrite synthetic test fixture')
    directory.mkdir(parents=True)
    archive = directory / 'archive'
    archive.mkdir()
    if background is None:
        scene = Image.new('RGB', (width, height), '#aab2b5')
        draw = ImageDraw.Draw(scene)
        draw.rectangle((0, height//3, width, height), fill='#bbb3a1')
        draw.polygon([(0, height), (width//2, height//2), (width, height)], fill='#60666b')
    else:
        scene = Image.open(background).convert('RGB').resize((width, height), Image.Resampling.LANCZOS)
    font = ImageFont.truetype(str(FONT), max(12, width//29))
    x, y = width//9, height//3
    box = (x-8, y-6, x+int(width*.50), y+int(height*.17))
    fps, first, pts_origin, clock = 4, 100, Fraction(20), 5000.0
    rows, mapping, originals = [], [], []
    raw_path, encoded_path = directory/'fictional-source.mkv', archive/'encoded.flv'
    with av.open(str(raw_path), 'w', format='matroska') as raw, av.open(str(encoded_path), 'w', format='flv') as encoded:
        raw_stream = raw.add_stream('ffv1', rate=fps)
        raw_stream.width, raw_stream.height, raw_stream.pix_fmt = width, height, 'bgr0'
        raw_stream.codec_context.thread_count = 2
        raw_stream.time_base = raw_stream.codec_context.time_base = Fraction(1, 1000)
        stream = encoded.add_stream('libx264', rate=fps)
        stream.width, stream.height, stream.pix_fmt = width, height, 'yuv420p'
        stream.codec_context.thread_count = 2
        stream.codec_context.max_b_frames = 0
        stream.time_base = stream.codec_context.time_base = Fraction(1, 1000)
        stream.options = {'preset': 'ultrafast', 'tune': 'zerolatency', 'crf': '18'}
        for n in range(frames):
            image = scene.copy()
            draw = ImageDraw.Draw(image)
            draw.rectangle(box, fill='#183c34', outline='#ffffff', width=2)
            draw.text((x, y), 'Cedar Vale', font=font, fill='white')
            draw.text((x, y+height//13), '142', font=font, fill='white')
            pixels = np.asarray(image).copy()
            pts = pts_origin + Fraction(n, fps)
            originals.append({'index': first+n, 'pts': str(pts),
                              'pixels_sha256': hashlib.sha256(pixels.tobytes()).hexdigest()})
            frame = av.VideoFrame.from_ndarray(pixels, format='rgb24')
            frame.pts, frame.time_base = int(pts*1000), Fraction(1, 1000)
            for packet in raw_stream.encode(frame):
                raw.mux(packet)
            mask = np.zeros((height, width), np.uint8)
            applied = n > 0
            if applied:
                mask[box[1]:box[3]+1, box[0]:box[2]+1] = 255
                pixels[mask != 0] = 0
            frame = av.VideoFrame.from_ndarray(pixels, format='rgb24')
            frame.pts, frame.time_base = n*250, Fraction(1, 1000)
            for packet in stream.encode(frame):
                encoded.mux(packet)
            rows.append({'index': first+n, 'pts': float(pts), 'egress_generation': 1, 'state': 'LIVE',
                         'protected': False, 'slate': False, 'coverage': {'ok': True, 'reason': 'synthetic-test'},
                         'deadline': clock+n/fps+2, 'presented_at': clock+n/fps+2,
                         'pixels_sha256': hashlib.sha256(pixels[:, :, ::-1].tobytes()).hexdigest(),
                         'mask_sha256': hashlib.sha256(mask.tobytes()).hexdigest(), 'mask_shape': list(mask.shape),
                         'mask_packbits_zlib_base64': base64.b64encode(zlib.compress(np.packbits(mask != 0).tobytes())).decode()})
            mapping.append({'index': first+n, 'egress_generation': 1, 'source_index': first+n,
                            'captured_at_monotonic': clock+n/fps, 'encoded_file': 'encoded.flv',
                            'encoded_pts': str(Fraction(n, fps)), 'applied_receipt_ids': ['illustration-1'] if applied else []})
        for owner, encoder in ((raw, raw_stream), (encoded, stream)):
            for packet in encoder.encode():
                owner.mux(packet)
    (archive/'frames.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
    manifest = {'schema': 'irl-shield-demo-source-v1', 'origin': 'wholly-synthetic', 'demo_ready': True,
                'license': 'CC0-1.0', 'fps': str(fps), 'video': {'file': raw_path.name, 'sha256': sha256(raw_path)},
                'public_asset_review': {'reviewer': 'W8 Codex author, generated scene and fictional labels inspected',
                    'no_real_people': True, 'no_brands_or_logos': True, 'no_music': True, 'fictional_text_only': True},
                'frames': originals}
    write_json(directory/'source.json', manifest)
    source_hash = sha256(directory/'source.json')
    sidecar = {'schema': 'irl-shield-demo-evidence-v1', 'source_manifest_sha256': source_hash,
               'evidence_kind': 'synthetic-test', 'execution_mode': 'offline', 'capture_origin_monotonic': clock,
               'frames_sha256': sha256(archive/'frames.jsonl'), 'encoded_files': {'encoded.flv': sha256(encoded_path)},
               'frames': mapping, 'detections': [{'id': 'illustration-1', 'lane': 'accurate', 'source_index': first+min(6, frames-1),
                   'completed_at_monotonic': clock+min(6, frames-1)/fps+.15, 'status': 'ok',
                   'quads': [[[box[0], box[1]], [box[2], box[1]], [box[2], box[3]], [box[0], box[3]]]]}]}
    write_json(archive/'demo-evidence.json', sidecar)
    write_json(directory/'pins.json', {'manifest_sha256': source_hash, 'evidence_sha256': sha256(archive/'demo-evidence.json')})
    return directory/'source.json', archive


def main():
    parser = argparse.ArgumentParser(description='Create SYNTHETIC TEST evidence, never measured native receipts.')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sample(args.output, ROOT/'fixtures/demo-renderer/fictional-street.png')
    print((args.output/'pins.json').read_text())


if __name__ == '__main__':
    main()

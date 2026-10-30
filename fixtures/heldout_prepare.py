#!/usr/bin/env python3
"""Prepare and freeze benchmark-only fresh heldouts, without OCR or masking.

Existing FFmpeg/NVENC, OpenCV, NumPy and Pillow; licenses already recorded by
this project. Media licenses and immutable Commons revisions are in the plan.
Run one `prepare --clip ID` per root q-run lease, then `freeze` without pixels.
"""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fixtures.prepare import download, sha256

CACHE = Path('fixtures/cache/fresh-heldout')


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def probe(path, *, count=False):
    return json.loads(subprocess.check_output(['ffprobe', '-v', 'error',
        *(['-count_frames'] if count else []), '-show_streams', '-show_format', '-of', 'json', str(path)], text=True))


def check_video(path):
    data = probe(path, count=True)
    streams = data['streams']
    if len(streams) != 1 or streams[0]['codec_type'] != 'video':
        raise ValueError('Derived heldout must contain only one video stream')
    v = streams[0]
    if (v['width'], v['height'], Fraction(v['avg_frame_rate']), int(v['nb_read_frames'])) != (1280, 720, Fraction(30), 150):
        raise ValueError('Derived heldout must be exactly 150 frames at 1280x720 and 30fps')
    if abs(float(v.get('start_time', '0'))) > 1e-6:
        raise ValueError('Derived heldout must start at zero PTS')
    if abs(float(data['format']['duration']) - 5.) > 1/30:
        raise ValueError('Derived heldout duration differs')
    return data


def prepare(clip):
    code_hash = sha256(Path(__file__))
    import cv2
    import numpy as np
    from bench.synthetic import overlay
    cv2.setNumThreads(1)
    source = ROOT / clip['source_path']
    source.parent.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        download(clip['download_url'], source)
    with source.open('rb') as stream:
        original_sha1 = hashlib.file_digest(stream, 'sha1').hexdigest()
    if (source.stat().st_size != clip['source_size_bytes'] or original_sha1 != clip['source_sha1']
            or sha256(source) != clip['source_sha256']):
        raise ValueError('Original differs from Commons advertised bytes/SHA1 or frozen SHA256')
    original_probe = probe(source)
    v = next(v for v in original_probe['streams'] if v['codec_type'] == 'video')
    if (v['width'], v['height']) != (clip['source_width'], clip['source_height']):
        raise ValueError('Original dimensions differ from Commons')
    if float(original_probe['format']['duration']) < 7:
        raise ValueError('Original too short for fixed 2–7s excerpt')
    base = ROOT / CACHE
    natural = base / (clip['id'] + '-natural.mp4')
    synthetic = base / (clip['id'] + '-synthetic.mp4')
    receipt = base / (clip['id'] + '.prepared.json')
    if receipt.exists() or natural.exists() or synthetic.exists():
        raise FileExistsError('Fresh preparation refuses to overwrite derived pixels')
    command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-n', '-threads', '2',
        '-filter_threads', '1', '-ss', '2.0', '-i', str(source), '-map', '0:v:0', '-an', '-sn', '-dn',
        '-t', '5.0', '-vf', 'scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=30:start_time=0,setsar=1',
        '-frames:v', '150', '-c:v', 'h264_nvenc', '-preset', 'p4', '-b:v', '10M', '-pix_fmt', 'yuv420p',
        '-map_metadata', '-1', '-map_chapters', '-1', '-metadata', 'encoder=', '-metadata:s:v', 'encoder=',
        '-movflags', '+faststart', str(natural)]
    subprocess.run(command, check=True)
    natural_probe = check_video(natural)
    synthetic_command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-n',
        '-filter_threads', '1', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', '1280x720', '-r', '30',
        '-i', 'pipe:0', '-an', '-c:v', 'h264_nvenc', '-preset', 'p4', '-b:v', '10M',
        '-pix_fmt', 'yuv420p', '-map_metadata', '-1', '-map_chapters', '-1',
        '-metadata', 'encoder=', '-metadata:s:v', 'encoder=', '-movflags', '+faststart', str(synthetic)]
    cap = cv2.VideoCapture(str(natural))
    process = None
    truth, previous, camera = [], None, np.zeros(2, dtype=float)
    try:
        with (base / (clip['id'] + '.encode.log')).open('w') as log:
            process = subprocess.Popen(synthetic_command, stdin=subprocess.PIPE, stderr=log)
            for index in range(150):
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError('Natural source truncated during synthetic preparation')
                # Same deterministic camera tracking recipe as bench.run.variant.
                gray = cv2.cvtColor(cv2.resize(frame, (320, 180)), cv2.COLOR_BGR2GRAY)
                if previous is not None:
                    points = cv2.goodFeaturesToTrack(previous, 100, .02, 8)
                    if points is not None:
                        moved, status, _ = cv2.calcOpticalFlowPyrLK(previous, gray, points, None)
                        valid = status.ravel() == 1
                        if valid.sum() >= 8:
                            motion = np.median((moved - points).reshape(-1, 2)[valid], axis=0)
                            camera += motion * np.array([4., 4.])
                previous = gray
                frame, labels = overlay(frame, index, 30., clip['seed'], camera_offset=tuple(camera))
                for label in labels:
                    quad = np.array(label['quad'])
                    label['box'] = [float(quad[:, 0].min()), float(quad[:, 1].min()),
                                    float(quad[:, 0].max()), float(quad[:, 1].max())]
                truth.append(labels)
                process.stdin.write(frame.tobytes())
            if cap.read()[0]:
                raise RuntimeError('Natural source has extra frames')
            process.stdin.close()
            if process.wait(timeout=60):
                raise RuntimeError('Synthetic encoder failed; see encode log')
    finally:
        cap.release()
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=3)
    synthetic_probe = check_video(synthetic)
    rows = []
    for variant, path, labels in ((False, natural, [[] for _ in range(150)]), (True, synthetic, truth)):
        truth_path = path.with_suffix('.truth.json')
        write(truth_path, labels)
        rows.append({'clip': clip['id'], 'synthetic_variant': variant,
                     'source': str(path.relative_to(ROOT)), 'truth': str(truth_path.relative_to(ROOT)),
                     'source_sha256': sha256(path), 'truth_sha256': sha256(truth_path)})
    if sha256(Path(__file__)) != code_hash:
        raise ValueError('Preparation source changed during execution')
    metadata_path = base / (clip['id'] + '.commons.json')
    write(receipt, {'clip': clip, 'inputs': rows, 'source_probe': original_probe,
        'natural_probe': natural_probe, 'synthetic_probe': synthetic_probe,
        'commons_metadata_path': str(metadata_path.relative_to(ROOT)),
        'commons_metadata_sha256': sha256(metadata_path),
        'commands': [command, synthetic_command], 'prepare_sha256': code_hash,
        'synthetic_sha256': sha256(ROOT / 'bench/synthetic.py'),
        'fonts': {p.name: sha256(p) for p in sorted((ROOT / 'fixtures/fonts').glob('*.ttf'))},
        'ffmpeg_version': subprocess.check_output(['ffmpeg', '-version'], text=True).splitlines()[0],
        'opencv_version': cv2.__version__, 'numpy_version': np.__version__})
    print('PREPARED UNGRADED', clip['id'], flush=True)


def freeze(plan, output):
    clips, inputs, receipts, metadata = [], [], {}, {}
    for clip in plan['clips']:
        path = ROOT / CACHE / (clip['id'] + '.prepared.json')
        receipt = json.loads(path.read_text())
        if receipt['clip'] != clip:
            raise ValueError('Preparation receipt differs from fixed plan')
        for row in receipt['inputs']:
            for key, digest_key in (('source', 'source_sha256'), ('truth', 'truth_sha256')):
                if sha256(ROOT / row[key]) != row[digest_key]:
                    raise ValueError('Prepared input changed before freeze')
        metadata[clip['id']] = json.loads((ROOT / receipt['commons_metadata_path']).read_text())
        clips.append(clip)
        inputs.extend(receipt['inputs'])
        receipts[str(path.relative_to(ROOT))] = sha256(path)
        receipts[receipt['commons_metadata_path']] = receipt['commons_metadata_sha256']
    manifest = {'schema_version': 1, 'dataset_id': 'fresh-heldout-v1', 'split': 'heldout',
        'status': 'frozen-ungraded', 'benchmark_only': True, 'demo_ready': False,
        'evaluation_marker': str(CACHE / 'EVALUATION.started.json'),
        'selection': 'Preferred three; fixed 2.000–7.000s from metadata before pixels/scores. No substitution.',
        'seed_recipe': 'big-endian uint32 of first four SHA256 bytes of UTF8(fresh-heldout-v1: + clip ID)',
        'recipe': 'NVENC p4 10M yuv420p; 1280x720 crop/scale, CFR30 start_time=0 with a 150-frame cap; no audio/source metadata; bench.synthetic.overlay with tune camera tracking',
        'natural_truth': 'Empty per-frame synthetic truth; natural truth must come from independent judges later.',
        'clips': clips, 'inputs': inputs, 'receipts': receipts, 'commons_metadata': metadata}
    from bench.quality_bundle import frozen_dataset
    with Path(output).open('x') as stream:
        stream.write(json.dumps(manifest, indent=2) + '\n')
    frozen_dataset(output)
    print('FROZEN UNGRADED', output, sha256(output), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'freeze'))
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--clip')
    parser.add_argument('--output', type=Path, default=ROOT / 'fixtures/fresh-heldout/manifest.json')
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    if args.action == 'prepare':
        selected = [c for c in plan['clips'] if c['id'] == args.clip]
        if len(selected) != 1:
            parser.error('--clip must name one fixed plan clip')
        metadata_path = ROOT / CACHE / (selected[0]['id'] + '.commons.json')
        if not metadata_path.exists() and 'commons_metadata' in plan:
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            write(metadata_path, plan['commons_metadata'][selected[0]['id']])
        prepare(selected[0])
        if plan.get('status') == 'frozen-ungraded':
            receipt = json.loads((ROOT / CACHE / (selected[0]['id'] + '.prepared.json')).read_text())
            expected = [r for r in plan['inputs'] if r['clip'] == args.clip]
            if receipt['inputs'] != expected:
                raise ValueError('New encoding differs from frozen pixels; transfer the sealed cache, never rebind the manifest')
    else:
        freeze(plan, args.output)


if __name__ == '__main__':
    main()

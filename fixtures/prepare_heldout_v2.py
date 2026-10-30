#!/usr/bin/env python3
"""Prepare and freeze fresh-heldout-v2; never invoke a detector or judge.

Uses the existing FFmpeg/NVENC, OpenCV, NumPy, Pillow and bundled fonts.
Commons author/license/revision snapshots live beside the sealed selection.
CPU actions: download, plan, freeze, verify. NVENC prepare runs only in root's EX queue.
"""
import argparse
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fixtures.prepare import sha256

DATASET = 'fresh-heldout-v2'
CACHE = Path('fixtures/cache/fresh-heldout-v2')
SELECTION = Path('fixtures/fresh-heldout-v2/selection.json')
SELECTION_SHA256 = '8d70354743f64dcbfb5305c67c8a4b1ab4a98f12d456dc773e2b64178d81cb0e'
RECIPE = ('NVENC p4 10M yuv420p; 1280x720 crop/scale, CFR30 start_time=0 with a '
          '150-frame cap; no audio/source metadata; bench.synthetic.overlay with tune camera tracking')


def exclusive_write(path, data):
    with Path(path).open('x') as stream:
        stream.write(json.dumps(data, indent=2) + '\n')


def validate_selection(selection):
    clips = selection['clips']
    if (selection.get('dataset_id') != DATASET or selection.get('status') != 'source-selection-sealed'
            or len(clips) != 3 or not selection.get('benchmark_only') or selection.get('demo_ready') is not False):
        raise ValueError('V2 requires three sealed benchmark-only sources')
    for key in ('id', 'title', 'source_url', 'download_url', 'source_sha1'):
        if len({c[key] for c in clips}) != 3:
            raise ValueError('V2 source identities must be unique')
    for clip in clips:
        seed = int.from_bytes(hashlib.sha256((DATASET + ':' + clip['id']).encode()).digest()[:4], 'big')
        if (clip['source_path'] != str(CACHE / (clip['id'] + '.webm'))
                or '/' in clip['id'] or '\\' in clip['id'] or clip['id'] in ('.', '..')
                or clip['seed'] != seed or clip['split'] != 'heldout'
                or (clip['excerpt_start'], clip['duration'], clip['width'], clip['height'], clip['fps'])
                   != (2., 5., 1280, 720, 30)
                or clip['source_width'] < 1280 or clip['source_height'] < 720
                or clip['source_duration_seconds'] < 7 or clip['license'] != 'CC BY 3.0'):
            raise ValueError('V2 source, seed or technical recipe differs from the sealed contract')
    return clips


def selection():
    path = ROOT / SELECTION
    if sha256(path) != SELECTION_SHA256:
        raise ValueError('Source selection changed after sealing')
    data = json.loads(path.read_text())
    validate_selection(data)
    if sha256(ROOT / 'fixtures/fresh-heldout-v2/nonreuse.json') != data['nonreuse_sha256']:
        raise ValueError('Nonreuse receipt changed')
    for meta in data['commons_metadata'].values():
        if sha256(ROOT / meta['path']) != meta['sha256']:
            raise ValueError('Commons snapshot changed')
    return data


def original(clip, *, expected_sha256=None):
    path = ROOT / clip['source_path']
    with path.open('rb') as stream:
        sha1 = hashlib.file_digest(stream, 'sha1').hexdigest()
    digest = sha256(path)
    if (path.stat().st_size != clip['source_size_bytes'] or sha1 != clip['source_sha1']
            or expected_sha256 is not None and digest != expected_sha256):
        raise ValueError('Original differs from sealed Commons bytes/SHA1/SHA256')
    return digest


def download_originals():
    """Fetch serially at <=3 MiB/s; retain partials for HTTP Range resumption."""
    for clip in selection()['clips']:
        destination = ROOT / clip['source_path']
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            original(clip)
            continue
        partial = destination.with_suffix('.part')
        offset = partial.stat().st_size if partial.exists() else 0
        if offset > clip['source_size_bytes']:
            raise ValueError('Partial original exceeds advertised byte count')
        row = {'url': clip['download_url'], 'path': clip['source_path'], 'resume_offset': offset,
               'rate_limit_bytes_per_second': 3 * 1024 * 1024}
        try:
            if offset < clip['source_size_bytes']:
                headers = {'User-Agent': 'IRLShieldBench/1.0 (Commons licensed benchmark research)'}
                if offset:
                    headers['Range'] = f'bytes={offset}-'
                request = urllib.request.Request(clip['download_url'], headers=headers)
                print('FETCH', clip['id'], 'offset', offset, flush=True)
                began = time.monotonic()
                fetched = 0
                with urllib.request.urlopen(request, timeout=120) as response:
                    row['http_status'] = response.status
                    if offset and (response.status != 206 or
                                   not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-')):
                        raise ValueError('Server did not honor exact partial range; partial retained')
                    with partial.open('ab' if offset else 'xb') as output:
                        while chunk := response.read(1024 * 1024):
                            output.write(chunk)
                            fetched += len(chunk)
                            time.sleep(max(0., fetched / row['rate_limit_bytes_per_second'] - (time.monotonic() - began)))
            with partial.open('rb') as stream:
                sha1 = hashlib.file_digest(stream, 'sha1').hexdigest()
            if partial.stat().st_size != clip['source_size_bytes'] or sha1 != clip['source_sha1']:
                raise ValueError('Downloaded original differs from Commons bytes/SHA1; partial retained')
            partial.rename(destination)
            row.update(size_bytes=destination.stat().st_size, sha1=sha1, sha256=original(clip))
            print('VERIFIED_ORIGINAL', clip['id'], row['sha256'], flush=True)
        except BaseException as error:
            row['error'] = str(error)
            raise
        finally:
            with (ROOT / CACHE / 'downloads.jsonl').open('a') as output:
                output.write(json.dumps(row) + '\n')


def make_plan(output):
    data = selection()
    clips = [dict(c, source_sha256=original(c)) for c in data['clips']]
    exclusive_write(output, {'schema_version': 1, 'dataset_id': DATASET, 'status': 'planned-ungraded',
                            'selection_sha256': SELECTION_SHA256, 'clips': clips})
    print('V2_PLAN', output, sha256(output), flush=True)


def load_plan(path):
    plan = json.loads(Path(path).read_text())
    selected = selection()
    if plan.get('dataset_id') != DATASET or plan.get('selection_sha256') != SELECTION_SHA256:
        raise ValueError('Plan does not bind the sealed v2 selection')
    stripped = [{k: v for k, v in c.items() if k != 'source_sha256'} for c in plan['clips']]
    if stripped != selected['clips']:
        raise ValueError('Plan differs from metadata-selected sources')
    return plan


def queue_lease():
    """Validate the inherited descriptor without acquiring a second lock."""
    fd = int(os.environ['IRL_SHIELD_PERF_QUEUE_LEASE_FD'])
    actual = os.fstat(fd)
    expected = Path('/tmp/agents/irl-shield/perf.lock').stat()
    if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
        raise RuntimeError('Preparation needs the canonical inherited queue lease')
    receipt = Path(os.environ['IRL_SHIELD_PERF_QUEUE_RECEIPT'])
    if not receipt.is_file():
        raise RuntimeError('Preparation needs a real root queue attempt receipt')
    return {'receipt': str(receipt), 'attempt': os.environ['IRL_SHIELD_PERF_QUEUE_ATTEMPT']}


def probe(path, *, frames=False):
    command = ['ffprobe', '-v', 'error', '-threads', '2', '-show_streams', '-show_format']
    if frames:
        command += ['-count_frames', '-show_frames', '-show_entries', 'frame=best_effort_timestamp_time']
    command += ['-of', 'json', str(path)]
    return json.loads(subprocess.check_output(command, text=True))


def check_video(path):
    data = probe(path, frames=True)
    streams = data['streams']
    if len(streams) != 1 or streams[0]['codec_type'] != 'video':
        raise ValueError('Derived v2 must contain only one video stream, no audio')
    v = streams[0]
    if (v['width'], v['height'], Fraction(v['avg_frame_rate']), int(v['nb_read_frames'])) != (1280, 720, Fraction(30), 150):
        raise ValueError('Derived v2 must be 150 frames at 1280x720 CFR30')
    times = [float(f['best_effort_timestamp_time']) for f in data['frames']]
    if (len(times) != 150 or any(abs(t - i/30) > 2e-6 for i, t in enumerate(times))
            or abs(float(v['start_time'])) > 1e-6 or abs(float(data['format']['duration']) - 5.) > 1/30):
        raise ValueError('Derived v2 frame timestamps must start at zero and advance at 30fps')
    return data


def code_identity():
    paths = ['fixtures/prepare_heldout_v2.py', 'fixtures/heldout_prepare.py', 'fixtures/prepare.py', 'bench/synthetic.py']
    paths += [str(p.relative_to(ROOT)) for p in sorted((ROOT / 'fixtures/fonts').glob('*.ttf'))]
    return {p: sha256(ROOT / p) for p in paths}


def prepare(plan_path, clip_id):
    lease = queue_lease()
    plan = load_plan(plan_path)
    clip = next(c for c in plan['clips'] if c['id'] == clip_id)
    identity = code_identity()
    plan_hash = sha256(plan_path)
    import cv2
    import numpy as np
    from bench.synthetic import overlay
    cv2.setNumThreads(1)
    cv2.ocl.setUseOpenCL(False)
    source = ROOT / clip['source_path']
    original(clip, expected_sha256=clip['source_sha256'])
    source_probe = probe(source)
    v = next(v for v in source_probe['streams'] if v['codec_type'] == 'video')
    if ((v['width'], v['height']) != (clip['source_width'], clip['source_height'])
            or float(source_probe['format']['duration']) < 7):
        raise ValueError('Decoded original dimensions/duration differ from selection metadata')
    base = ROOT / CACHE
    natural, synthetic = [base / (clip_id + '-' + variant + '.mp4') for variant in ('natural', 'synthetic')]
    receipt = base / (clip_id + '.prepared.json')
    if any(p.exists() for p in (natural, synthetic, receipt, natural.with_suffix('.truth.json'), synthetic.with_suffix('.truth.json'))):
        raise FileExistsError('V2 preparation refuses to overwrite existing derived assets or receipts')
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
    # Explicit OpenCV FFmpeg decoder limit, supported by the pinned OpenCV build.
    cap = cv2.VideoCapture(str(natural), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 2])
    if not cap.isOpened():
        raise RuntimeError('Could not open natural v2 video with two-thread CPU decode')
    process = None
    truth, previous, camera = [], None, np.zeros(2, dtype=float)
    try:
        with (base / (clip_id + '.encode.log')).open('x') as log:
            process = subprocess.Popen(synthetic_command, stdin=subprocess.PIPE, stderr=log)
            for index in range(150):
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError('Natural v2 source truncated during synthetic preparation')
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
                raise RuntimeError('Natural v2 source has extra frames')
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
                process.kill()
                process.wait(timeout=3)
    synthetic_probe = check_video(synthetic)
    rows = []
    for variant, path, labels in ((False, natural, [[] for _ in range(150)]), (True, synthetic, truth)):
        truth_path = path.with_suffix('.truth.json')
        exclusive_write(truth_path, labels)
        rows.append({'clip': clip_id, 'synthetic_variant': variant,
                     'source': str(path.relative_to(ROOT)), 'truth': str(truth_path.relative_to(ROOT)),
                     'source_sha256': sha256(path), 'truth_sha256': sha256(truth_path)})
    if code_identity() != identity or sha256(plan_path) != plan_hash:
        raise ValueError('Preparation source or plan changed during execution')
    exclusive_write(receipt, {'clip': clip, 'inputs': rows, 'source_probe': source_probe,
        'natural_probe': natural_probe, 'synthetic_probe': synthetic_probe, 'commands': [command, synthetic_command],
        'code_identity': identity, 'plan_sha256': plan_hash, 'queue': lease,
        'ffmpeg_version': subprocess.check_output(['ffmpeg', '-version'], text=True).splitlines()[0],
        'opencv_version': cv2.__version__, 'numpy_version': np.__version__})
    print('V2_PREPARED_UNGRADED', clip_id, sha256(receipt), flush=True)


def verify_inputs(plan, *, decode=False):
    clips, rows, receipts = plan['clips'], [], {}
    for clip in clips:
        original(clip, expected_sha256=clip['source_sha256'])
        path = ROOT / CACHE / (clip['id'] + '.prepared.json')
        receipt = json.loads(path.read_text())
        if (receipt['clip'] != clip or receipt['code_identity'] != code_identity()
                or receipt['plan_sha256'] != sha256(ROOT / 'fixtures/fresh-heldout-v2/plan.json')):
            raise ValueError('Preparation receipt differs from sealed plan or current source')
        expected = [str(CACHE / (clip['id'] + '-' + v + '.mp4')) for v in ('natural', 'synthetic')]
        if len(receipt['inputs']) != 2 or [r['source'] for r in receipt['inputs']] != expected:
            raise ValueError('Preparation receipt must contain both distinct v2 variants')
        for index, row in enumerate(receipt['inputs']):
            if (row['clip'] != clip['id'] or type(row['synthetic_variant']) is not bool
                    or row['synthetic_variant'] != bool(index)
                    or row['truth'] != str(Path(row['source']).with_suffix('.truth.json'))):
                raise ValueError('Preparation pair identity differs')
            for key, digest in (('source', 'source_sha256'), ('truth', 'truth_sha256')):
                if sha256(ROOT / row[key]) != row[digest]:
                    raise ValueError('Prepared asset changed before freeze')
            truth = json.loads((ROOT / row['truth']).read_text())
            if len(truth) != 150 or any(len(labels) != (4 if index else 0) for labels in truth):
                raise ValueError('Truth must describe every one of 150 frames')
            if index:
                for labels in truth:
                    for label in labels:
                        if (not isinstance(label['text'], str) or not label['text']
                                or len(label['quad']) != 4 or any(len(p) != 2 for p in label['quad'])
                                or not label['id'].startswith(str(clip['seed']) + ':')):
                            raise ValueError('Synthetic truth lacks exact strings/quads/stable IDs')
            if decode:
                check_video(ROOT / row['source'])
            rows.append(row)
        receipts[str(path.relative_to(ROOT))] = sha256(path)
    return rows, receipts


def freeze(plan_path, output):
    plan = load_plan(plan_path)
    rows, receipts = verify_inputs(plan)
    selected = selection()
    metadata = {id: json.loads((ROOT / meta['path']).read_text()) for id, meta in selected['commons_metadata'].items()}
    manifest = {'schema_version': 1, 'dataset_id': DATASET, 'split': 'heldout',
        'status': 'frozen-ungraded', 'benchmark_only': True, 'demo_ready': False,
        'evaluation_marker': str(CACHE / 'EVALUATION.started.json'),
        'evaluation_reservation': {'maximum_evaluations': 1, 'policy': 'Final policy after Sunday 06:00 PT freeze; never Saturday v1 walk policy', 'not_before_utc': '2026-11-01T14:00:00Z', 'evaluation_started': False},
        'selection_sha256': SELECTION_SHA256, 'plan_sha256': sha256(plan_path),
        'selection': selected['selection'], 'seed_recipe': selected['seed_recipe'], 'recipe': RECIPE,
        'natural_truth': '150 empty arrays of synthetic truth only; no natural OCR truth generated during preparation',
        'clips': plan['clips'], 'inputs': rows, 'receipts': receipts, 'code_identity': code_identity(),
        'commons_metadata': metadata, 'nonreuse_sha256': selected['nonreuse_sha256']}
    exclusive_write(output, manifest)
    print('V2_FROZEN', sha256(output), output, flush=True)


def verify(manifest_path):
    manifest = load_plan(manifest_path)
    if manifest.get('status') != 'frozen-ungraded':
        raise ValueError('V2 manifest is not frozen-ungraded')
    rows, receipts = verify_inputs(manifest, decode=True)
    if rows != manifest['inputs'] or receipts != manifest['receipts']:
        raise ValueError('V2 manifest differs from sealed assets')
    print('V2_VERIFIED_UNGRADED', sha256(manifest_path), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('download', 'plan', 'prepare', 'freeze', 'verify'))
    parser.add_argument('--plan', type=Path, default=ROOT / 'fixtures/fresh-heldout-v2/plan.json')
    parser.add_argument('--clip', choices=[c['id'] for c in selection()['clips']])
    parser.add_argument('--output', type=Path, default=ROOT / 'fixtures/fresh-heldout-v2/manifest.json')
    args = parser.parse_args()
    if args.action == 'download':
        download_originals()
    elif args.action == 'plan':
        make_plan(args.plan)
    elif args.action == 'prepare':
        if args.clip is None:
            parser.error('prepare requires --clip')
        prepare(args.plan, args.clip)
    elif args.action == 'freeze':
        freeze(args.plan, args.output)
    else:
        verify(args.output)


if __name__ == '__main__':
    main()

"""Offline CUDA rendering and deferred Mac OCR on the same sealed tune pixels.

Uses existing fixture/model licenses, NumPy, OpenCV and FFmpeg dependencies.
This script can run from a lane's cwd without copying or changing its engine.
It records no performance qualification and never creates unjudged scores.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def modules(root):
    sys.path.insert(0, str(Path(root).resolve()))
    from bench import offline_quality
    return offline_quality


def entries(root, inputs):
    manifest = json.loads((Path(root) / 'fixtures/manifest.json').read_text())
    expected = {(c['id'], synthetic) for c in manifest['clips'] if c['split'] == 'tune'
                for synthetic in (False, True)}
    snapshot = Path(inputs).read_bytes()
    data = json.loads(snapshot)
    actual = [(r['clip'], r['synthetic_variant']) for r in data['clips']]
    if len(expected) != 14 or len(actual) != 14 or set(actual) != expected:
        raise ValueError('Quality input manifest must contain exactly all seven tune clip pairs')
    if data['fixture_manifest_sha256'] != digest(Path(root) / 'fixtures/manifest.json'):
        raise ValueError('Quality fixture manifest changed')
    return data, snapshot


def checked_file(directory, name):
    path = Path(directory) / name
    if Path(name).is_absolute() or not path.resolve().is_relative_to(Path(directory).resolve()):
        raise ValueError('Quality artifact escapes its sealed directory')
    return path


def verify(directory):
    directory = Path(directory)
    path = directory / 'bundle.json'
    if digest(path) != (directory / 'bundle.sha256').read_text().strip():
        raise ValueError('Quality bundle manifest changed')
    plan = json.loads(path.read_text())
    if plan['status'] != 'awaiting-judging' or plan['schema_version'] != 2:
        raise ValueError('Unsupported quality bundle')
    for name, identity in plan['artifacts'].items():
        artifact = checked_file(directory, name)
        if artifact.stat().st_size != identity['bytes'] or digest(artifact) != identity['sha256']:
            raise ValueError('Quality artifact changed: ' + name)
    if digest(directory / 'inputs.json') != plan['input_manifest_sha256']:
        raise ValueError('Quality frozen input manifest changed')
    data = json.loads((directory / 'inputs.json').read_bytes())
    rows = [row for row in data['clips'] if (row['clip'], row['synthetic_variant']) ==
            (plan['clip'], plan['synthetic_variant'])]
    if len(rows) != 1:
        raise ValueError('Quality bundle is missing its unique frozen input row')
    for name, key in (('input.mp4', 'source_sha256'), ('input.truth.json', 'truth_sha256')):
        if digest(directory / name) != rows[0][key]:
            raise ValueError('Quality copied input differs from its frozen manifest: ' + name)
    return plan


@contextmanager
def clip_lease(root, host):
    """One short clip per shared host lease; serialize heavy quality on each host."""
    import fcntl
    # Task-local serialization adds no daemon, global setting or alternate perf lock.
    serial = Path(root) / '.tmp/q' / ('quality-' + host + '.lock')
    serial.parent.mkdir(parents=True, exist_ok=True)
    with serial.open('a+') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        canonical = Path('/tmp/agents/irl-shield/perf.lock')
        canonical.parent.mkdir(parents=True, exist_ok=True)
        with canonical.open('a+') as perf:
            fcntl.flock(perf, fcntl.LOCK_SH)
            yield


def render(root, inputs, config, directory, clip, synthetic):
    """Write one encoded clip and actual masks; privacy remains ungraded."""
    quality = modules(root)
    import cv2
    import numpy as np
    cv2.setNumThreads(1)
    data, input_snapshot = entries(root, inputs)
    row = next(r for r in data['clips'] if (r['clip'], r['synthetic_variant']) == (clip, synthetic))
    config = json.loads(Path(config).read_text())
    candidate, options = config['candidate'], dict(config['options'])
    from bench.independence import policy_metadata
    policy_metadata(candidate, options)
    source_original, truth_original = Path(row['source']), Path(row['truth'])
    for key, path in [('source_sha256', source_original), ('truth_sha256', truth_original)]:
        if digest(path) != row[key]:
            raise ValueError('Frozen quality input changed: ' + key)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    source, output = directory / 'input.mp4', directory / 'masked.mp4'
    shutil.copyfile(source_original, source)
    shutil.copyfile(truth_original, directory / 'input.truth.json')
    (directory / 'inputs.json').write_bytes(input_snapshot)
    for name, key in (('input.mp4', 'source_sha256'), ('input.truth.json', 'truth_sha256')):
        if digest(directory / name) != row[key]:
            raise ValueError('Frozen copied input changed: ' + name)
    media = quality._media(source)
    truth = json.loads((directory / 'input.truth.json').read_text())
    if len(truth) != media['frames']:
        raise ValueError('Quality truth omits source frames')
    code = quality._fingerprint()
    orchestrator = digest(__file__)
    backends, capture, process = {}, None, None
    try:
        backends = quality._make_backends(candidate, options, media['resolution'])
        if set(backends) != {'fast', 'accurate'}:
            raise ValueError('Quality policy must construct both detector lanes')
        width, height = media['resolution']
        encoder = options.get('encoder', 'h264_nvenc')
        flags = {'h264_nvenc': ['-preset', 'p4', '-tune', 'ull', '-rc-lookahead', '0'],
                 'h264_videotoolbox': ['-realtime', '1'],
                 'libx264': ['-preset', 'ultrafast', '-tune', 'zerolatency', '-threads', '2']}
        if encoder not in flags:
            raise ValueError('Unsupported quality encoder')
        command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                   '-filter_threads', '1', '-f', 'rawvideo', '-pix_fmt', 'bgr24',
                   '-s', f'{width}x{height}', '-r', str(media['fps']), '-i', 'pipe:0',
                   '-an', '-c:v', encoder, *flags[encoder], '-bf', '0', '-b:v', '10M',
                   '-pix_fmt', 'yuv420p', str(output)]
        capture = cv2.VideoCapture(str(source))
        if not capture.isOpened():
            raise RuntimeError('Cannot decode quality source')
        def frames():
            for _ in range(media['frames']):
                ok, pixels = capture.read()
                if not ok:
                    raise RuntimeError('Quality source truncated')
                yield pixels
            if capture.read()[0]:
                raise RuntimeError('Quality source has extra frames')
        with (directory / 'encoder.log').open('w') as log, zipfile.ZipFile(
                output.with_suffix('.mask-pixels.zip'), 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as masks:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=log)
            def emit(frame):
                process.stdin.write(frame.pixels.tobytes())
                masks.writestr(f'{frame.index:08d}.bin', np.packbits(frame.mask > 0, bitorder='little').tobytes())
            rendered = quality.render_offline(frames(), media['fps'], backends, options, emit)
            process.stdin.close()
            if process.wait(timeout=60):
                raise RuntimeError('Quality encoder failed')
        if (quality._media(output) != media or quality._fingerprint() != code or
                digest(__file__) != orchestrator):
            raise RuntimeError('Quality media accounting or source changed')
        for name, suffix in [('records', '.masks.json'), ('motion', '.motion.json'), ('detections', '.detections.json')]:
            write_json(output.with_suffix(suffix), rendered[name])
        write_json(directory / 'engine.json', {k: v for k, v in rendered.items() if k not in ('records', 'motion', 'detections')})
        artifacts = {p.name: {'sha256': digest(p), 'bytes': p.stat().st_size}
                     for p in directory.iterdir() if p.is_file()}
        plan = {'schema_version': 2, 'status': 'awaiting-judging', 'clip': clip, 'synthetic_variant': synthetic,
                'candidate': candidate, 'options': options, 'frames': media['frames'], 'source_fps': media['fps'],
                'pipeline_sha256': code, 'orchestrator_sha256': orchestrator,
                'input_manifest_sha256': hashlib.sha256(input_snapshot).hexdigest(), 'artifacts': artifacts,
                'scope': 'Untimed ideal/offline Linux output; no OCR score or realtime qualification exists yet.'}
        write_json(directory / 'bundle.json', plan)
        (directory / 'bundle.sha256').write_text(digest(directory / 'bundle.json') + '\n')
        verify(directory)
        return plan
    finally:
        if capture is not None:
            capture.release()
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=3)
        for backend in backends.values():
            backend.close()


def grade(root, directory, *, judge=None, cache=None):
    quality = modules(root)
    import cv2
    cv2.setNumThreads(1)
    from bench.independence import policy_metadata
    directory = Path(directory)
    plan = verify(directory)
    if quality._fingerprint() != plan['pipeline_sha256'] or digest(__file__) != plan['orchestrator_sha256']:
        raise ValueError('Quality grading source differs from sealed render source')
    if (directory / 'grade.json').exists():
        raise FileExistsError(directory / 'grade.json')
    owned = judge is None
    if owned:
        from bench.judges import Judges
        judge = Judges(plan['candidate'], cache or directory.parent / 'judge-cache')
    try:
        records = json.loads((directory / 'masked.masks.json').read_text())
        truth = json.loads((directory / 'input.truth.json').read_text())
        scored = quality._score_saved(directory / 'input.mp4', directory / 'masked.mp4', judge, truth, records,
                    detector_families=policy_metadata(plan['candidate'], plan['options'])['detector_families'])
        result = {k: plan[k] for k in ('clip', 'synthetic_variant', 'candidate', 'options', 'frames', 'source_fps')}
        result.update({'mode': 'offline_quality', 'real_time_verified': False,
                       'benchmark_only': True, 'demo_ready': False,
                       'source': str(directory / 'input.mp4'), 'output': str(directory / 'masked.mp4'),
                       'judges': list(judge.names), 'pipeline_sha256': plan['pipeline_sha256'],
                       'bundle_sha256': digest(directory / 'bundle.json'),
                       'evidence_sha256': digest(directory / 'masked.evidence.json'), **scored})
        verify(directory)
        if quality._fingerprint() != plan['pipeline_sha256'] or digest(__file__) != plan['orchestrator_sha256']:
            raise ValueError('Quality grading source changed during OCR')
        write_json(directory / 'grade.json', result)
        (directory / 'grade.sha256').write_text(digest(directory / 'grade.json') + '\n')
        return result
    finally:
        if owned:
            judge.close()


def aggregate(root, directory, run_id):
    quality = modules(root)
    directory = Path(directory)
    manifest = json.loads((Path(root) / 'fixtures/manifest.json').read_text())
    expected = {(c['id'], synthetic) for c in manifest['clips'] if c['split'] == 'tune' for synthetic in (False, True)}
    paths = sorted(directory.glob('*/grade.json'))
    results = [json.loads(p.read_text()) for p in paths]
    if len(results) != 14 or {(r['clip'], r['synthetic_variant']) for r in results} != expected:
        raise ValueError('All seven tune clip pairs must be judged before aggregation')
    first = results[0]
    run_identity = None
    for path, result in zip(paths, results):
        plan = verify(path.parent)
        identity = {key: plan[key] for key in ('input_manifest_sha256', 'pipeline_sha256',
                                              'orchestrator_sha256')}
        if run_identity is None:
            run_identity = identity
        elif identity != run_identity:
            raise ValueError('Quality bundles have different experiment identities')
        if (identity['pipeline_sha256'] != quality._fingerprint() or
                identity['orchestrator_sha256'] != digest(__file__)):
            raise ValueError('Quality aggregation source differs from the sealed run identity')
        if digest(path) != path.with_suffix('.sha256').read_text().strip():
            raise ValueError('Quality grade changed')
        if digest(path.parent / 'masked.evidence.json') != result['evidence_sha256']:
            raise ValueError('Quality evidence changed')
        if any(result[k] != first[k] for k in ('candidate', 'options', 'pipeline_sha256')):
            raise ValueError('Quality clips use different policies or source')
        if result['bundle_sha256'] != digest(path.parent / 'bundle.json'):
            raise ValueError('Quality grade refers to a different render')
        entries(root, path.parent / 'inputs.json')
        if any(result[key] != plan[key] for key in ('clip', 'synthetic_variant', 'candidate', 'options',
                                                    'frames', 'source_fps', 'pipeline_sha256')):
            raise ValueError('Quality grade differs from its sealed render policy')
        # Stored grading paths describe the old host. Reducers may read only
        # the artifacts beside this verified grade, including after relocation.
        result['source'] = str(path.parent / 'input.mp4')
        result['output'] = str(path.parent / 'masked.mp4')
    card = quality.build_scorecard(results, first['candidate'], first['options'], run_id=run_id,
                                  split='tune', baseline=json.loads((Path(root) / 'bench/baseline.json').read_text()))
    card['pipeline_sha256'] = first['pipeline_sha256']
    card['quality_run_identity'] = run_identity
    card['grading_scope'] = 'Independent truth/input controls, ALL output judges, exact sealed CUDA/NVENC frames; ideal/offline, never a performance gate.'
    write_json(directory / 'scorecard.json', card)
    return card


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--lock-root', type=Path, help='Canonical root checkout for quality serialization; CLI only')
    actions = parser.add_subparsers(dest='action', required=True)
    make = actions.add_parser('render')
    make.add_argument('--inputs', type=Path, required=True); make.add_argument('--config', type=Path, required=True)
    make.add_argument('--directory', type=Path, required=True); make.add_argument('--clip', required=True)
    make.add_argument('--synthetic', action='store_true')
    read = actions.add_parser('grade'); read.add_argument('--directory', type=Path, required=True)
    read.add_argument('--cache', type=Path)
    join = actions.add_parser('aggregate'); join.add_argument('--directory', type=Path, required=True); join.add_argument('--run-id', required=True)
    check = actions.add_parser('verify'); check.add_argument('--directory', type=Path, required=True)
    probe = actions.add_parser('exec'); probe.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.action in ('render', 'grade', 'exec') and args.lock_root is None:
        parser.error('Render/grade require --lock-root to serialize a single clip under the shared host lease')
    if args.action == 'render':
        with clip_lease(args.lock_root, 'linux'):
            result = render(args.root, args.inputs, args.config, args.directory, args.clip, args.synthetic)
    elif args.action == 'grade':
        with clip_lease(args.lock_root, 'mac'):
            result = grade(args.root, args.directory, cache=args.cache)
    elif args.action == 'aggregate':
        result = aggregate(args.root, args.directory, args.run_id)
    elif args.action == 'exec':
        command = args.command[1:] if args.command[:1] == ['--'] else args.command
        if not command:
            parser.error('exec requires a literal foreground command')
        with clip_lease(args.lock_root, 'mac' if platform.system() == 'Darwin' else 'linux'):
            raise SystemExit(subprocess.run(command, cwd=args.root).returncode)
    else:
        result = verify(args.directory)
    print(json.dumps({'action': args.action, 'directory': str(args.directory),
                      'status': result.get('status', 'graded'),
                      **{k: result[k] for k in ('natural', 'synthetic', 'real_video_pass', 'masked_area_fraction', 'protected_fraction') if k in result}}, indent=2))


if __name__ == '__main__':
    main()

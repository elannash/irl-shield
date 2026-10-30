"""Lane-local commands: guarded measurement, deferred grading, and local relay.

Heavy commands require the root receipt marker and hold the common host lock.
No command downloads a model or opens an unapproved network endpoint.
"""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MARKER = Path('/tmp/agents/irl-shield/m1-20261029-ready.json')
LOCK = Path('/tmp/agents/irl-shield/perf.lock')


def queue_context():
    """Verify the inherited queue lease without a second lock acquisition."""
    prefix = 'IRL_SHIELD_PERF_QUEUE_'
    try:
        forced = os.environ[prefix + 'FORCED']
        attempt = int(os.environ[prefix + 'ATTEMPT'])
        receipt = Path(os.environ[prefix + 'RECEIPT'])
        descriptor = int(os.environ[prefix + 'LEASE_FD'])
        expected, actual = LOCK.stat(), os.fstat(descriptor)
    except (KeyError, ValueError, OSError) as error:
        raise RuntimeError('Missing or invalid inherited performance queue context') from error
    if forced not in ('0', '1') or attempt not in (1, 2, 3) or not receipt.is_absolute():
        raise RuntimeError('Invalid performance queue forced/attempt/receipt context')
    if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
        raise RuntimeError('Inherited descriptor does not identify the canonical performance lock')
    return {'forced': forced == '1', 'attempt': attempt, 'attempt_receipt': str(receipt),
            'lease_fd': descriptor, 'lease_device': actual.st_dev, 'lease_inode': actual.st_ino}


@contextmanager
def queued_lease(args):
    args.queue_context = queue_context()
    if not MARKER.exists() or json.loads(MARKER.read_text()).get('complete') is not True:
        raise RuntimeError(f'Root sustained receipt has not completed: {MARKER}')
    args.contended = args.contended or args.queue_context['forced']
    try:
        yield
    finally:
        if args.out.is_dir():
            (args.out / 'queue-context.json').write_text(json.dumps(args.queue_context, indent=2) + '\n')


@contextmanager
def host_lease(mode):
    if not MARKER.exists() or json.loads(MARKER.read_text()).get('complete') is not True:
        raise RuntimeError(f'Root sustained receipt has not completed: {MARKER}')
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX if mode == 'exclusive' else fcntl.LOCK_SH)
        os.set_inheritable(stream.fileno(), True)
        ready = json.loads(MARKER.read_text())
        if ready.get('complete') is not True:
            raise RuntimeError(f'Root sustained receipt has not completed: {MARKER}')
        yield ready


def runtime_receipt(directory):
    from bench.clocked_pipeline import host_environment
    from relay.gst_bench import transport_fingerprint
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    names = ['appsrc', 'appsink', 'videoconvert', 'videoscale', 'qtdemux', 'h264parse', 'mp4mux',
             'flvmux', 'mpegtsmux', 'srtsrc', 'srtsink', 'rtmp2src', 'rtmp2sink', 'avenc_aac', 'avdec_aac',
             *(['vtdec', 'vtenc_h264'] if platform.system() == 'Darwin' else ['nvh264dec', 'nvh264enc'])]
    plugins = {}
    for name in names:
        result = subprocess.run(['gst-inspect-1.0', name], text=True, capture_output=True, timeout=20)
        plugins[name] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
    receipt = {'environment': host_environment(), 'plugins': plugins,
               'gstreamer': subprocess.check_output(['gst-inspect-1.0', '--version'], text=True),
               'transport_sha256': transport_fingerprint(),
               'license_scope': 'Installed dynamically linked libraries; no GStreamer binary or vendor SDK bundled',
               'source_files': {str(p.relative_to(ROOT)): p.read_text() for p in sorted((ROOT / 'relay').glob('gst*.py'))}}
    (directory / 'gst-runtime.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def measure(args):
    from bench.clocked_pipeline import file_sha256, fingerprint
    from bench.cross_host import seal_measurement
    from relay.gst_bench import run_file
    options = json.loads(args.options.read_text()) if args.options else {}
    defaults = {'delay_seconds': 1., 'static_model': True, 'fast_candidate': 'ppocr-v6-tiny',
                'fast_rate_hz': 30., 'accurate_rate_hz': 4., 'fast_width': 640, 'accurate_width': 1280,
                'limit_side_len': 960, 'fast_limit_side_len': 640, 'warmup_seconds': 10.,
                'provider': 'cpu', 'fast_provider': 'cpu', 'padding': .3, 'style': 'opaque'}
    options = {**defaults, **options, 'transport': args.transport}
    if args.queued:
        options['perf_queue'] = args.queue_context
    if args.contended:
        options['contended'] = True
    darwin = platform.system() == 'Darwin'
    options.setdefault('encoder', ('vtenc_h264' if darwin else 'nvh264enc') if args.transport == 'gst'
                       else ('h264_videotoolbox' if darwin else 'h264_nvenc'))
    options.setdefault('decoder', 'vtdec' if darwin else 'nvh264dec')
    directory = args.out.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    runtime_receipt(directory)
    manifest = json.loads((ROOT / 'fixtures/manifest.json').read_text())
    clips = [c for c in manifest['clips'] if c['split'] == 'tune' and (args.clip is None or c['id'] == args.clip)]
    if not clips:
        raise ValueError('No tune fixtures selected')
    results = []
    for clip in clips:
        for synthetic in (False, True):
            label = clip['id'] + ('-synthetic' if synthetic else '-natural')
            source = directory / f'{label}-input.mp4'
            prepared = args.source_dir / source.name
            truth = prepared.with_suffix('.truth.json')
            if not prepared.is_file() or not truth.is_file():
                raise FileNotFoundError(f'Missing prepared tune input/truth: {prepared}')
            shutil.copyfile(prepared, source)
            shutil.copyfile(truth, source.with_suffix('.truth.json'))
            # The prepared input is an existing variant, not the canonical cache.
            # Record its exact bytes; root provenance/truth remain in the input bundle.
            print(f'{label}: {args.transport}', flush=True)
            output = directory / f'{label}-masked.mp4'
            performance = run_file(source, output, args.candidate, options)
            results.append({'clip': clip['id'], 'synthetic_variant': synthetic,
                            'source': str(source), 'output': str(output),
                            'truth': str(source.with_suffix('.truth.json')), 'performance': performance,
                            'prepared_source': {'path': str(prepared.resolve()), 'sha256': file_sha256(prepared),
                                                'truth_sha256': file_sha256(truth)}})
    selected = next(r for r in results if not r['synthetic_variant'])
    sustained = run_file(selected['source'], directory / 'sustained-masked.mp4', args.candidate,
                         {**options, 'repeat_seconds': args.steady_seconds})
    card = {'schema_version': 2, 'run_id': directory.name, 'candidate': args.candidate, 'split': 'tune',
            'options': options, 'pipeline_sha256': fingerprint(),
            'manifest_sha256': file_sha256(ROOT / 'fixtures/manifest.json'), 'clips': results,
            'sustained': sustained, 'pilot': args.clip is not None, 'performance_only': False,
            'natural_only': False, 'benchmark_only': True, 'demo_ready': False, 'judges': [],
            'area_ceiling': args.area_ceiling, 'area_ceiling_basis': args.area_ceiling_basis,
            'scope': 'Same common sustained/quality schema; tune only; quality pending independent Mac OCR',
            'judge_memory_isolation': {'isolated': True, 'mode': 'no-judge'},
            'licenses': ['fixtures/ATTRIBUTION.md', 'models/manifest.json', 'models/licenses/dependencies.json', 'docs/GSTREAMER.md']}
    return seal_measurement(card, directory)


def relay(args):
    import numpy as np
    from contextlib import ExitStack
    from bench.clocked_pipeline import drive, perf_health
    from relay.gst import GstSource, GstSink
    from relay.gst_bench import engine_for
    from relay.media import local_url
    local_url(args.input)
    local_url(args.output)
    options = json.loads(args.options.read_text()) if args.options else {}
    options = {'delay_seconds': 1., 'static_model': True, 'fast_width': 640, 'accurate_width': args.width,
               'fast_rate_hz': 30., 'accurate_rate_hz': 4., **options}
    media = {'fps': args.fps, 'frames': round(args.seconds * args.fps), 'resolution': [args.width, args.height]}
    source = GstSource(args.input, media, detector_widths=(options['fast_width'], options['accurate_width']),
                       decoder=args.decoder, delay_seconds=options['delay_seconds'], audio=args.audio)
    args.out.mkdir(parents=True, exist_ok=False)
    runtime_receipt(args.out)
    sink = GstSink(args.output, media['resolution'], args.fps, encoder=args.encoder,
                   audio=args.audio, audio_source=source, artifacts=args.out / 'live.mp4')
    warm = np.zeros((args.height, args.width, 3), np.uint8)
    copies = {w: np.zeros((round(args.height * w / args.width), w, 3), np.uint8) for w in source.widths}
    with ExitStack() as stack:
        engine, loading = engine_for(source, args.candidate, options, warm, copies, stack)
    start = perf_health()
    try:
        result = drive(source, engine, sink)
    finally:
        end = perf_health()
    result.update(loading=loading, perf_health={'start': start, 'end': end},
                  scope='Finite local/Tailscale relay; received network output still requires independent grading')
    (args.out / 'relay.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main(argv=None):
    def deadline(signum, frame):
        raise TimeoutError('Lane process deadline reached; unwinding owned adapters')
    signal.signal(signal.SIGALRM, deadline)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--queued', action='store_true', help='External perf-queue owns EX; do not reacquire perf.lock')
    parser.add_argument('--contended', action='store_true', help='Explicit diagnostic only; never qualifies performance')
    commands = parser.add_subparsers(dest='action', required=True)
    measurement = commands.add_parser('measure')
    measurement.add_argument('--source-dir', type=Path, required=True)
    measurement.add_argument('--out', type=Path, required=True)
    measurement.add_argument('--candidate', default='ppocr-v6-small')
    measurement.add_argument('--transport', choices=('gst', 'ffmpeg', 'nut'), default='gst')
    measurement.add_argument('--options', type=Path)
    measurement.add_argument('--clip')
    measurement.add_argument('--steady-seconds', type=float, default=30.)
    measurement.add_argument('--area-ceiling', type=float)
    measurement.add_argument('--area-ceiling-basis')
    grading = commands.add_parser('grade')
    grading.add_argument('--plan', type=Path, required=True)
    installation = commands.add_parser('mac-install')
    installation.add_argument('--out', type=Path, required=True)
    versions = commands.add_parser('inspect')
    versions.add_argument('--out', type=Path, required=True)
    av = commands.add_parser('av')
    av.add_argument('--out', type=Path, required=True)
    av.add_argument('--encoder', default='vtenc_h264' if platform.system() == 'Darwin' else 'nvh264enc')
    av.add_argument('--decoder', default='vtdec' if platform.system() == 'Darwin' else 'nvh264dec')
    network = commands.add_parser('network')
    network.add_argument('--source', type=Path, required=True)
    network.add_argument('--out', type=Path, required=True)
    network.add_argument('--encoder', default='vtenc_h264' if platform.system() == 'Darwin' else 'nvh264enc')
    network.add_argument('--decoder', default='vtdec' if platform.system() == 'Darwin' else 'nvh264dec')
    live = commands.add_parser('relay')
    for flag in ('input', 'output'):
        live.add_argument('--' + flag, required=True)
    live.add_argument('--out', type=Path, required=True)
    live.add_argument('--options', type=Path)
    live.add_argument('--candidate', default='ppocr-v6-small')
    live.add_argument('--fps', type=float, default=30.)
    live.add_argument('--width', type=int, default=1280)
    live.add_argument('--height', type=int, default=720)
    live.add_argument('--seconds', type=float, default=40.)
    live.add_argument('--audio', action='store_true')
    live.add_argument('--encoder', default='vtenc_h264' if platform.system() == 'Darwin' else 'nvh264enc')
    live.add_argument('--decoder', default='vtdec' if platform.system() == 'Darwin' else 'nvh264dec')
    args = parser.parse_args(argv)
    if args.queued:
        if args.action not in ('measure', 'av', 'network', 'relay'):
            parser.error('--queued is only for timed jobs under the external EX lease')
    lease = queued_lease(args) if args.queued else host_lease('shared' if args.action in ('inspect', 'grade', 'mac-install') else 'exclusive')
    with lease:
        if args.action == 'mac-install':
            if platform.system() != 'Darwin':
                raise RuntimeError('mac-install is only supported on macOS')
            from bench.clocked_pipeline import perf_health
            args.out.mkdir(parents=True, exist_ok=False)
            receipt = {'start': perf_health()}
            if receipt['start']['pressure_state'] != 'normal':
                raise RuntimeError('Reject install under non-normal memory pressure')
            try:
                result = subprocess.run(['brew', 'install', 'gstreamer'], text=True, capture_output=True,
                                        env={**os.environ, 'HOMEBREW_NO_AUTO_UPDATE': '1'}, timeout=1800)
                receipt.update(command=['brew', 'install', 'gstreamer'], returncode=result.returncode,
                               stdout=result.stdout, stderr=result.stderr)
            finally:
                receipt['end'] = perf_health()
                (args.out / 'install.json').write_text(json.dumps(receipt, indent=2) + '\n')
            if result.returncode:
                raise RuntimeError('GStreamer install failed; see install.json')
            return runtime_receipt(args.out)
        if args.action == 'measure':
            if args.steady_seconds < 30:
                parser.error('Sustained measurements require at least 30 steady seconds')
            return measure(args)
        if args.action == 'grade':
            from bench.cross_host import grade
            return grade(args.plan)
        if args.action == 'inspect':
            return runtime_receipt(args.out)
        if args.action == 'av':
            from relay.gst_av import run
            return run(args.out, args.encoder, args.decoder, contended=args.contended)
        if args.action == 'network':
            from relay.gst_network import run
            return run(args.source, args.out, args.encoder, args.decoder, contended=args.contended)
        return relay(args)


if __name__ == '__main__':
    main()

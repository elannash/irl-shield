"""Queue-only Q2 execution, fail closed before media/model/GPU work.

Never enqueue here. The conductor supplies an already active exclusive queue
lease and both release receipts. This module never reacquires the host lock.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from bench.q2_execution.adapters import sha256, factories_for
from bench.q2_execution.events import summarize, EVENT_SCOPE

ROOT = Path(__file__).resolve().parents[2]
PERF_LOCK = Path('/tmp/agents/irl-shield/perf.lock')


def require_release(release, frozen_sha, queue_dir, *, env=None):
    env = os.environ if env is None else env
    barrier = json.loads(Path(release).read_bytes())
    if barrier.get('GPU_RELEASED') is not True:
        raise ValueError('GPU release requires GPU_RELEASED')
    if not re.fullmatch('[a-f0-9]{64}', frozen_sha) or barrier.get('V2_FROZEN') != frozen_sha:
        raise ValueError('V2 frozen manifest SHA must match exactly')
    keys = ('IRL_SHIELD_PERF_QUEUE_LEASE_FD', 'IRL_SHIELD_PERF_QUEUE_ATTEMPT',
            'IRL_SHIELD_PERF_QUEUE_RECEIPT', 'IRL_SHIELD_PERF_QUEUE_FORCED')
    if any(key not in env for key in keys):
        raise ValueError('Q2 execution requires an active inherited exclusive queue lease')
    fd = int(env[keys[0]])
    actual, canonical = os.fstat(fd), PERF_LOCK.stat()
    if (actual.st_dev, actual.st_ino) != (canonical.st_dev, canonical.st_ino):
        raise ValueError('Inherited queue lease differs from canonical performance lock')
    info = Path(f'/proc/self/fdinfo/{fd}').read_text()
    if not any('FLOCK' in line and 'WRITE' in line for line in info.splitlines() if line.startswith('lock:')):
        raise ValueError('Inherited performance lease must be exclusive')
    receipt = Path(env[keys[2]]).resolve()
    if not receipt.is_relative_to(Path(queue_dir).resolve() / 'linux/jobs'):
        raise ValueError('Queue receipt is outside the selected active Linux queue')
    attempt = json.loads(receipt.read_bytes())
    if (attempt.get('phase') != 'prepared' or attempt.get('host') != 'linux'
            or attempt.get('execution_started') is not True
            or attempt.get('queue_environment') != {key: env[key] for key in keys}
            or Path(attempt['lease_path']).resolve() != PERF_LOCK.resolve()
            or attempt.get('lease_identity') != {'device': actual.st_dev, 'inode': actual.st_ino}):
        raise ValueError('Queue attempt does not identify the inherited active exclusive lease')
    return {'release_sha256': sha256(release), 'v2_manifest_sha256': frozen_sha,
            'queue_receipt': str(receipt), 'attempt': env[keys[1]],
            'forced': env[keys[3]] == '1', 'lease_identity': attempt['lease_identity']}


def local_path(name):
    path = ROOT / name
    if Path(name).is_absolute() or not path.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError('Q2 output/config/input must be relative to the integration root')
    return path


def gpu_cost(source, directory, candidate, options, factories, cudart, repetitions, *, diagnostic_delay=False):
    from bench.clocked_pipeline import run, probe_media, fingerprint
    from bench.clocked_bench import clock_guards
    from bench.q2_execution.measured import MeasuredBackends
    if repetitions < 5:
        raise ValueError('GPU cost requires at least five independent cost repetitions')
    media = probe_media(source)
    if media['resolution'] != [1280, 720] or media['fps'] != 30.:
        raise ValueError('Q2 timing requires the prepared720p30 source')
    gpu = subprocess.check_output(['nvidia-smi', '--query-gpu=index,name,uuid,driver_version',
                                   '--format=csv,noheader'], text=True, timeout=15)
    if not any(line.strip().startswith('0,') and '1080 Ti' in line for line in gpu.splitlines()):
        raise ValueError('GPU0 must identify the requested1080Ti')
    package_receipts = installed_licenses()
    identity = {'pipeline_sha256': fingerprint(), 'source_sha256': sha256(source),
                'cudart_sha256': sha256(cudart), 'nvidia_smi': gpu, 'packages': package_receipts}
    trials = []
    for repetition in range(repetitions):
        from bench.w1.measured import LayeredMeasuredBackends
        backends = LayeredMeasuredBackends(cudart) if candidate.startswith('w1-') else MeasuredBackends(cudart)
        trial = {'repetition': repetition + 1, 'valid': False}
        trials.append(trial)
        try:
            result = run(source, directory / f'cost-{repetition + 1}.mp4', candidate, options,
                         backend_factory=backends, factories=factories, diagnostic_delay=diagnostic_delay)
            guards = clock_guards(result, required_resolution=(1280, 720))
            origin = result['clock_origin']
            start = origin + result['warmup_frames'] / 30.
            stop = start + result['steady_frames'] / 30.
            lanes = {}
            for lane, backend in backends.backends.items():
                rows = [r for r in backend.timer.rows if start <= r['host_started_at'] < stop]
                calls = [r for r in backend.calls if start <= r['host_started_at'] < stop]
                lanes[lane] = {'cost': summarize(rows, source_frames=result['steady_frames']),
                               'all_event_rows': backend.timer.rows, 'all_detector_calls': backend.calls,
                               'steady_detector_calls': len(calls), 'metadata': backend.metadata}
                if len(calls) != len(rows) or any(r['error'] for r in calls):
                    lanes[lane]['cost']['valid'] = False
                    lanes[lane]['cost']['gpu_ms_per_source_frame'] = None
                    lanes[lane]['cost']['gpu_ms_per_inference'] = None
            trial.update({'lanes': lanes, 'source_frames': result['steady_frames'],
                          'clock_guards': guards,
                          'warmup_frames': result['warmup_frames'], 'performance_receipt': f'cost-{repetition + 1}.performance.json',
                          'steady_fps': result['fps'], 'steady_p95_latency_seconds': result['realtime_added_latency_seconds']['p95'],
                          'steady_protected_fraction': result['protected_fraction'],
                          'valid': result['performance_valid'] and {key.split('/')[0] for key in lanes} == {'fast', 'accurate'}
                                   and all(lane['cost']['valid'] for lane in lanes.values())})
        except BaseException as error:
            trial['error'] = f'{type(error).__name__}: {error}'
            raise
        finally:
            try:
                backends.close()
            except BaseException as error:
                trial['valid'] = False
                trial['cleanup_error'] = f'{type(error).__name__}: {error}'
                raise
            finally:
                trial['raw_events'] = {lane: b.timer.rows for lane, b in backends.backends.items()}
                trial['raw_detector_calls'] = {lane: b.calls for lane, b in backends.backends.items()}
                trial['backend_metadata'] = {lane: b.metadata for lane, b in backends.backends.items()}
                write_json(directory / 'gpu-cost.json', {'identity': identity, 'trials': trials,
                    'candidate': candidate, 'options': options, 'source_media': media,
                    'event_scope': EVENT_SCOPE, 'acceptance_eligible': False,
                    'parity_status': 'unverified; paired normal-provider/output parity required',
                    'window_scope': 'Host inference-start in post-warmup30fps source window; cost denominator is every steady presented source frame; skipped inference offers remain in denominator. Lane sums may overlap.',
                    'scheduling_changes': 'Explicit ORT stream, pre-start stream synchronization and post-run event wait; NVENC runs concurrently in the clocked path.'})
                (directory / 'gpu-cost.sha256').write_text(sha256(directory / 'gpu-cost.json') + '\n')
    if fingerprint() != identity['pipeline_sha256'] or sha256(source) != identity['source_sha256']:
        raise ValueError('GPU cost source changed during measurement')
    return {'status': 'diagnostic-cost-only', 'all_trials_valid': all(t['valid'] for t in trials)}


def installed_licenses():
    from importlib.metadata import distributions
    rows = []
    for package in distributions():
        name = package.metadata['Name']
        if name.lower().startswith('nvidia-') or name.lower() in {'onnxruntime-gpu', 'rapidocr', 'numpy', 'opencv-python'}:
            files = []
            for path in package.files or []:
                if path.name.lower().startswith(('license', 'copying')) and '.dist-info' in str(path):
                    files.append({'name': str(path), 'sha256': sha256(package.locate_file(path))})
            if not files:
                raise ValueError('Missing installed license receipt for ' + name)
            rows.append({'name': name, 'version': package.version,
                         'license': package.metadata.get('License'), 'license_files': files})
    if not any(row['name'] == 'nvidia-cuda-runtime-cu12' for row in rows):
        raise ValueError('CUDA12 runtime package/license is required')
    return rows


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('render', 'clocked', 'gpu-cost'))
    parser.add_argument('--release', required=True, type=Path)
    parser.add_argument('--v2-manifest-sha256', required=True)
    parser.add_argument('--queue-dir', required=True, type=Path)
    parser.add_argument('--source-freeze', type=Path)
    parser.add_argument('--gate-receipt', type=Path)
    parser.add_argument('--parity', type=Path)
    parser.add_argument('--config', required=True)
    parser.add_argument('--directory', required=True)
    parser.add_argument('--input')
    parser.add_argument('--inputs')
    parser.add_argument('--clip')
    parser.add_argument('--synthetic', action='store_true')
    parser.add_argument('--cudart', type=Path)
    parser.add_argument('--repetitions', type=int, default=5)
    args = parser.parse_args(argv)
    release = require_release(args.release, args.v2_manifest_sha256, args.queue_dir)
    if any(value is not None for value in (args.source_freeze,args.gate_receipt,args.parity)):
        if not all(value is not None for value in (args.source_freeze,args.gate_receipt,args.parity)):
            parser.error('W1 execution requires all three source/gate/parity receipts')
        from bench.w1.identity import verify_metric_barriers
        verify_metric_barriers(args.source_freeze,args.gate_receipt,args.parity)
    config_path, directory = local_path(args.config), local_path(args.directory)
    config_snapshot = config_path.read_bytes()
    config = json.loads(config_snapshot)
    candidate, options = config['candidate'], dict(config['options'])
    if candidate.startswith('w1-') or config_path.is_relative_to(ROOT/'bench/w1'):
        if not all(value is not None for value in (args.source_freeze,args.gate_receipt,args.parity)):
            raise ValueError('W1 arm execution requires frozen source, full SH gate0 and CUDA parity0')
        from bench.w1.cards import validate_policy
        validate_policy(config)
    from bench.independence import policy_metadata
    from bench.metrics import validate_area_ceiling
    policy_metadata(candidate, options)
    validate_area_ceiling(options.get('area_ceiling'), options.get('area_ceiling_basis'), required=True)
    factories = factories_for(config.get('execution', {}), options)
    if args.action == 'render':
        if not args.inputs or not args.clip:
            parser.error('render requires frozen tune --inputs and --clip')
        from bench.quality_bundle import render
        result = render(ROOT, local_path(args.inputs), config_path, directory, args.clip, args.synthetic)
    else:
        if not args.input:
            parser.error('timing requires the prepared720p30 --input')
        source = local_path(args.input)
        if directory.exists():
            raise FileExistsError(directory)
        diagnostic_delay=config.get('execution', {}).get('diagnostic_delay',False)
        delay=options.get('delay_seconds',1.)
        if (options.get('encoder') != 'h264_nvenc' or type(diagnostic_delay) is not bool
                or delay not in ((1.,2.,3.) if diagnostic_delay else (1.,))):
            raise ValueError('Q2 timing requires NVENC and D1 or explicit diagnostic D2/D3')
        options.update({'repeat_seconds': 30., 'warmup_seconds': 10.})
        if args.action == 'gpu-cost' and (args.cudart is None or args.repetitions < 5):
            parser.error('GPU cost requires --cudart and at least5 repetitions')
        from bench.clocked_pipeline import run, probe_media
        media = probe_media(source)
        if media['resolution'] != [1280, 720] or media['fps'] != 30.:
            raise ValueError('Q2 timing requires the prepared720p30 source')
        directory.mkdir(parents=True)
        if args.action == 'gpu-cost':
            result = gpu_cost(source, directory, candidate, options, factories, args.cudart, args.repetitions, diagnostic_delay=diagnostic_delay)
        else:
            result = run(source, directory / 'clocked.mp4', candidate, options, factories=factories, diagnostic_delay=diagnostic_delay)
    if config_path.read_bytes() != config_snapshot:
        raise ValueError('Q2 execution config changed during execution')
    artifacts = {str(path.relative_to(directory)): {'sha256': sha256(path), 'bytes': path.stat().st_size}
                 for path in directory.rglob('*') if path.is_file()}
    plan = {'action': args.action, 'release': release, 'candidate': candidate, 'options': options,
            'config_sha256': sha256(config_path), 'artifacts': artifacts, 'result': result,
            'execution_adapters': factories.identity(ROOT) if factories else None}
    write_json(directory / 'execution.json', plan)
    (directory / 'execution.sha256').write_text(sha256(directory / 'execution.json') + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

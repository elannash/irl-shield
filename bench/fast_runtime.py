"""FAST inference cost receipts; each measured call includes preprocess/postprocess.

This is detector cost, not a clocked stream throughput benchmark.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import time

import cv2
import numpy as np

from bench.fast import FastDetector, PROVIDERS
from bench.fast_lease import require_complete, read_queue_context
from bench.clocked_pipeline import perf_health
from models.prepare import sha256_file

READY = Path('/tmp/agents/irl-shield/m1-20261029-ready.json')


def require_ready():
    marker = require_complete(READY)
    return {'path': str(READY), 'sha256': sha256_file(READY), 'receipt': marker}


def source_fingerprint():
    from bench.offline_quality import _fingerprint
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256(_fingerprint().encode())
    for path in sorted(list((root / 'bench').glob('fast*.py')) + [root / 'models/manifest.json']):
        digest.update(str(path.relative_to(root)).encode() + b'\0' + path.read_bytes())
    return digest.hexdigest()


def finish_health(health, directory):
    health['end'] = perf_health()
    (Path(directory) / 'perf-health.json').write_text(json.dumps(health, indent=2) + '\n')


def health_valid(health):
    return all(row['pressure_state'] == 'normal' for row in health.values())


def cost_trust(health, *, contended, provider_executed, forced):
    reasons = []
    if forced:
        reasons.append('forced-contended')
    if contended:
        reasons.append('contended-host-load')
    if not provider_executed:
        reasons.append('requested-provider-not-executed')
    for phase in ('start', 'end'):
        state = health.get(phase, {}).get('pressure_state', 'unknown')
        if state != 'normal':
            reasons.append(f'{phase}-memory-pressure-{state}')
    return {'valid': not reasons, 'reasons': reasons}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cache-dir', type=Path, required=True)
    parser.add_argument('--provider', choices=tuple(PROVIDERS), required=True)
    parser.add_argument('--side', type=int, default=1024)
    parser.add_argument('--seconds', type=float, default=30)
    parser.add_argument('--warmup', type=int, default=3)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    if not np.isfinite(args.seconds) or args.seconds < 30 or args.warmup < 1:
        parser.error('At least 30 steady seconds and one warmup call are required')
    ready = require_ready()
    queue_context = read_queue_context()
    forced = bool(queue_context and queue_context['forced'])
    args.out.mkdir(parents=True, exist_ok=False)
    health = {'start': perf_health()}
    if not health_valid(health) and not forced:
        (args.out / 'rejected-health.json').write_text(json.dumps(health, indent=2))
        raise RuntimeError('FAST timing rejected: memory pressure is not normal')
    cv2.setNumThreads(2)
    capture = cv2.VideoCapture(str(args.source))
    frames, hashes = [], []
    try:
        count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        for index in np.linspace(0, count - 1, 10, dtype=int):
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = capture.read()
            if not ok:
                raise RuntimeError(f'Cannot decode inference source frame {index}')
            frames.append(frame)
            hashes.append({'source_index': int(index), 'shape': list(frame.shape),
                           'sha256': hashlib.sha256(frame.tobytes()).hexdigest()})
    finally:
        capture.release()
    detector = None
    began = time.perf_counter()
    try:
        detector = FastDetector(cache_dir=args.cache_dir, provider=args.provider, side=args.side)
        startup = time.perf_counter() - began
        warmup = []
        for index in range(args.warmup):
            began = time.perf_counter()
            detector.detect_quads(frames[index % len(frames)])
            warmup.append(time.perf_counter() - began)
        rows = []
        began, cpu_start = time.perf_counter(), time.process_time()
        while time.perf_counter() - began < args.seconds:
            index = len(rows) % len(frames)
            call_start = time.perf_counter()
            quads = detector.detect_quads(frames[index])
            rows.append({'sample': index, 'wall_seconds': time.perf_counter() - call_start,
                         'quads': quads})
        elapsed, cpu = time.perf_counter() - began, time.process_time() - cpu_start
        metadata = detector.metadata
    finally:
        if detector is not None:
            detector.close()
        finish_health(health, args.out)
    # Partition evidence is collected separately, so profiling overhead does not enter steady cost.
    profile_detector = FastDetector(cache_dir=args.cache_dir, provider=args.provider, side=args.side,
                                    profile_prefix=args.out / 'ort-profile')
    try:
        profile_detector.detect_quads(frames[0])
        profile_path = Path(profile_detector.end_profile())
    finally:
        profile_detector.close()
    events = json.loads(profile_path.read_text())
    partitions = {}
    for event in events:
        provider = event.get('args', {}).get('provider')
        if provider:
            row = partitions.setdefault(provider, {'events': 0, 'duration_microseconds': 0})
            row['events'] += 1
            row['duration_microseconds'] += event.get('dur', 0)
    requested_executed = partitions.get(PROVIDERS[args.provider], {}).get('events', 0) > 0
    durations = [row['wall_seconds'] for row in rows]
    load_contended = any(row['load_per_cpu'] is None or row['load_per_cpu'] > 1 for row in health.values())
    contended = forced or load_contended
    trust = cost_trust(health, contended=load_contended, provider_executed=requested_executed, forced=forced)
    result = {'mode': 'detector-inference-cost', 'stream_throughput_verified': False,
              'ready': ready, 'queue_context': queue_context, 'forced_contended': forced, 'source': str(args.source), 'source_sha256': sha256_file(args.source),
              'pipeline_sha256': source_fingerprint(), 'platform': platform.platform(),
              'source_frames': hashes, 'detector': metadata, 'startup_seconds': startup,
              'warmup_seconds_per_call': warmup, 'steady_seconds': elapsed, 'steady_calls': len(rows),
              'steady_wall_seconds': {key: float(np.percentile(durations, value))
                                      for key, value in [('p50', 50), ('p95', 95)]},
              'steady_calls_per_second': len(rows) / elapsed, 'steady_process_cpu_seconds': cpu,
              'steady_cpu_core_equivalents': cpu / elapsed, 'perf_health': health,
              'contended_diagnostic': contended, 'profile': str(profile_path),
              'profile_sha256': sha256_file(profile_path), 'provider_kernel_events': partitions,
              'requested_provider_executed': requested_executed,
              'valid': trust['valid'], 'measurement_trust': trust,
              'scope': 'Static batch1, threads2; startup and warmup excluded from >=30s steady '
                       'wall time; process CPU includes native worker threads; no stream fps claim.',
              'calls': rows}
    (args.out / 'runtime.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'calls'}, indent=2))
    if not requested_executed:
        raise RuntimeError('Requested provider had no profiled execution events; CPU fallback cannot be credited')
    return result


if __name__ == '__main__':
    main()

"""Frozen-source, queue-only 120s native RTMP/CUDA/NVENC diagnostic job."""
import argparse
from contextlib import ExitStack
from fractions import Fraction
from functools import partial
import hashlib
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import signal
import socket
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]


class PreflightError(RuntimeError):
    """Fixed, credential-free launch errors safe to retain verbatim."""


def preflight_runtime():
    if not os.environ.get('LD_LIBRARY_PATH'):
        raise PreflightError('missing-required-env: LD_LIBRARY_PATH')
    if os.environ.get('PYTHONPATH'):
        raise PreflightError('forbidden-overlay-env: PYTHONPATH')
    if sys.version_info[:2] != (3, 11):
        raise PreflightError('runtime-requires-pinned-Python-3.11')
    from importlib import import_module, metadata
    names = {d.metadata['Name'].lower().replace('_', '-') for d in metadata.distributions()}
    if 'onnxruntime-gpu' not in names or 'onnxruntime' in names:
        raise PreflightError('runtime-requires-single-onnxruntime-gpu-distribution')
    receipt = {}
    for name in ('av', 'cv2', 'numpy', 'onnxruntime', 'rapidocr', 'psutil', 'aiohttp', 'twitchAPI', 'pytesseract'):
        try:
            module = import_module(name)
        except ImportError:
            raise PreflightError('runtime-missing-module: ' + name) from None
        path = Path(module.__file__).absolute()
        if not path.is_relative_to(Path(sys.prefix).absolute()):
            raise PreflightError('runtime-mixed-site-module: ' + name)
        receipt[name] = {'path': str(path), 'sha256': sha256(path)}
    if 'CUDAExecutionProvider' not in import_module('onnxruntime').get_available_providers():
        raise PreflightError('runtime-missing-CUDAExecutionProvider')
    return {'executable': sys.executable, 'prefix': sys.prefix, 'modules': receipt,
            'cuda_dynamic_libs_validated': False,
            'note': 'Provider listing is not a successful CUDA session. Engine construction must succeed.'}


def check_ports():
    with ExitStack() as stack:
        for kind, port in ((socket.SOCK_STREAM, 29351), (socket.SOCK_DGRAM, 28891), (socket.SOCK_STREAM, 28555)):
            listener = stack.enter_context(socket.socket(socket.AF_INET, kind))
            try:
                listener.bind(('127.0.0.1', port))
            except OSError:
                raise PreflightError('loopback-port-unavailable: ' + str(port)) from None
    # This is availability, not a reservation; MediaMTX still fails on a race.


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def verify_sources(root, manifest):
    for name, expected in json.loads(Path(manifest).read_text()).items():
        path = Path(root) / name
        if not path.is_file():
            raise RuntimeError('source-missing: ' + name)
        if sha256(path) != expected:
            raise RuntimeError('source-drift: ' + name)


def sender(url, directory, stopped, end):
    """Generated silent phone-like H.264. No fixture/media reads or credentials in argv."""
    import av
    import cv2
    import numpy as np
    av.logging.set_level(None)
    cv2.setNumThreads(1)
    frames = []
    status = 'failed'
    try:
        with av.open(url, 'w', format='flv', options={'flvflags': 'no_duration_filesize', 'flush_packets': '1'}) as output:
            video = output.add_stream('libx264', rate=30)
            video.width, video.height, video.pix_fmt = 1280, 720, 'yuv420p'
            video.bit_rate = 3_000_000
            video.codec_context.thread_count = 2
            video.codec_context.max_b_frames, video.codec_context.gop_size = 0, 30
            video.time_base = video.codec_context.time_base = Fraction(1, 30)
            video.options = {'preset': 'ultrafast', 'tune': 'zerolatency'}
            audio = output.add_stream('aac', rate=48000)
            audio.layout, audio.bit_rate = 'mono', 128000
            audio.codec_context.thread_count = 2
            audio.time_base = audio.codec_context.time_base = Fraction(1, 48000)
            yy, xx = np.indices((720, 1280), dtype=np.uint16)
            pattern = np.stack((xx % 180 + 30, yy % 180 + 30, (xx // 7 + yy // 7) % 180 + 30), axis=2).astype(np.uint8)
            origin, index = time.monotonic(), 0
            while not stopped.is_set() and time.monotonic() < end:
                if stopped.wait(max(0., origin + index / 30 - time.monotonic())):
                    break
                # Elapsed slots stay gaps, rather than becoming a catch-up burst.
                index = max(index, int((time.monotonic() - origin) * 30))
                pixels = np.roll(pattern, index * 2, axis=1)
                cv2.rectangle(pixels, (130, 210), (680, 295), (245, 245, 245), -1)
                cv2.putText(pixels, 'CEDAR WAY 417', (150, 270), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (10, 10, 10), 3)
                frame = av.VideoFrame.from_ndarray(pixels, format='bgr24')
                frame.pts, frame.time_base = index, Fraction(1, 30)
                sound = av.AudioFrame.from_ndarray(np.zeros((1, 1600), np.int16), format='s16', layout='mono')
                sound.sample_rate, sound.pts, sound.time_base = 48000, index * 1600, Fraction(1, 48000)
                for stream, value in ((video, frame), (audio, sound)):
                    for packet in stream.encode(value):
                        output.mux(packet)
                frames.append({'index': index, 'at': time.monotonic()})
                index += 1
            for stream in (video, audio):
                for packet in stream.encode():
                    output.mux(packet)
        status = 'closed'
    finally:
        write(Path(directory) / 'sender.json', {'status': status, 'frames': frames,
            'generator': 'bench.efficiency.job.sender', 'license': 'CC0-1.0', 'music': False,
            'sender_cpu_is_relay_cpu': False})


def observer(url, stopped, directory, first_decoded):
    """Independent private loopback decode; bounded scalar evidence, no saved video."""
    import av
    import numpy as np
    av.logging.set_level(None)
    rows, errors = [], []
    while not stopped.is_set():
        try:
            with av.open(url, timeout=(2., 1.), container_options={'rtsp_transport': 'tcp', 'rw_timeout': '1000000'}) as source:
                source.streams.video[0].codec_context.thread_count = 2
                for frame in source.decode(video=0):
                    if stopped.is_set():
                        break
                    pixels = frame.to_ndarray(format='bgr24')
                    if first_decoded.value == 0.:
                        first_decoded.value = time.monotonic()
                    rows.append({'at': time.monotonic(), 'pts': float(frame.pts * frame.time_base),
                                 'spatial_std': float(np.std(pixels)), 'all_dark': bool(pixels.max() < 12)})
                break
        except Exception as error:
            if len(errors) < 10:
                errors.append(type(error).__name__)
            stopped.wait(.1)
    write(Path(directory) / 'observer.json', {'status': 'closed' if stopped.is_set() else 'eof', 'finished_at': time.monotonic(), 'frames': rows, 'errors': errors,
          'quality_scorecard': None, 'scope': 'Decoded output liveness only; spatial variance does not prove protection or real-video score'})


def stop(process, event, name, receipts):
    event.set()
    process.join(5)
    forced = process.is_alive()
    if process.is_alive():
        process.terminate()
        process.join(3)
    if process.is_alive():
        process.kill()
        process.join(2)
    receipts.append({'role': name, 'pid': process.pid, 'exitcode': process.exitcode, 'alive': process.is_alive(), 'forced': forced})
    if process.is_alive():
        raise RuntimeError('owned-process-survived')
    process.close()


def require_root_launcher(args):
    """Validate supplied receipts; root, not JSON declarations, enforces one launch."""
    from datetime import datetime, timezone
    path = getattr(args, 'launcher_receipt', None)
    expected = getattr(args, 'launcher_sha256', None)
    if path is None or not expected:
        raise PreflightError('blocked-required-verified-root-launcher')
    receipt = json.loads(Path(path).read_text())
    launcher = Path(receipt['launcher_path'])
    if sha256(launcher) != expected or receipt['launcher_sha256'] != expected:
        raise PreflightError('root-launcher-hash-mismatch')
    if receipt['source_manifest_sha256'] != sha256(args.sources):
        raise PreflightError('root-launcher-source-mismatch')
    # These receipts must come from actual enforcement and an inherited-FD test.
    for name in ('one_physical_execution', 'ex_fd_through_py_spy', 'queue_deadlines'):
        proof = receipt.get(name)
        if not proof or sha256(Path(proof['path'])) != proof['sha256']:
            raise PreflightError('missing-root-proof: ' + name)
    deadlines = json.loads(Path(receipt['queue_deadlines']['path']).read_text())
    now = datetime.now(timezone.utc)
    forced = datetime.fromisoformat(deadlines['forced_utc'].replace('Z', '+00:00'))
    hard = datetime.fromisoformat(deadlines['hard_stop_utc'].replace('Z', '+00:00'))
    if not now < forced < hard or deadlines.get('expired_defaults_used') is not False:
        raise PreflightError('root-queue-deadlines-not-current')
    if receipt.get('execution_ordinal') != 1 or not receipt.get('job_identity'):
        raise PreflightError('root-launcher-execution-identity-missing')
    return receipt


class CollectionWindow:
    """Event adapter used by the real relay's foreground is_set/wait boundary."""
    def __init__(self, cancellation, first_observer, shared_window, warmup, startup_timeout):
        self.cancellation = cancellation
        self.first_observer = first_observer
        self.shared_window = shared_window
        self.warmup = warmup
        self.startup_deadline = time.monotonic() + startup_timeout
        self.ready = self.completed = None
        self.events = []
        self.failures = []
        self.first = {}
        self.lock = threading.RLock()

    def observe(self, row):
        with self.lock:
            self.events.append(row)
            kind = row['kind']
            if kind in ('source', 'encoded'):
                self.first.setdefault(kind, row['at'])
            if kind == 'detector' and row.get('inference_completed'):
                self.first.setdefault('detector-' + row['lane'], row['at'])

    def set(self):
        self.failures.append('external-cancellation')
        self.cancellation.set()

    def is_set(self):
        if self.cancellation.is_set():
            return True
        now = time.monotonic()
        with self.lock:
            if self.first_observer.value > 0:
                self.first.setdefault('observer', self.first_observer.value)
            keys = ('source', 'detector-fast', 'detector-accurate', 'encoded', 'observer')
            if self.ready is None and all(key in self.first for key in keys):
                self.ready = max(self.first[key] for key in keys)
                self.shared_window[0] = self.ready + self.warmup
                self.shared_window[1] = self.shared_window[0] + 120.
            if self.ready is None and now >= self.startup_deadline:
                self.failures.append('pipeline-readiness-timeout')
                self.cancellation.set()
            elif self.ready is not None and now >= self.shared_window[1]:
                self.completed = now
                self.cancellation.set()
        return self.cancellation.is_set()

    def wait(self, timeout=None):
        # The production runtime asks for 5ms; cap any caller's wait for fuse checks.
        self.cancellation.wait(.05 if timeout is None else min(timeout, .05))
        return self.is_set()


def population(rows):
    """Describe observed populations and gaps without grading privacy or FPS."""
    ordered = sorted(rows, key=lambda row: row['at'])
    last = {}
    gaps = []
    for row in ordered:
        pts = row.get('pts')
        generation = row.get('generation')
        if pts is not None:
            if not math.isfinite(pts):
                raise ValueError('nonfinite-population-PTS')
            if generation in last and pts - last[generation] > 1 / 30 + 1e-7:
                gaps.append({'generation': generation, 'after_pts': last[generation], 'before_pts': pts,
                             'gap_seconds': pts - last[generation] - 1 / 30})
            last[generation] = pts
    return {'count': len(ordered), 'first_at': ordered[0]['at'] if ordered else None,
            'last_at': ordered[-1]['at'] if ordered else None, 'pts': [r.get('pts') for r in ordered],
            'indices': [r.get('index') for r in ordered],
            'generations': sorted({r['generation'] for r in ordered if r.get('generation') is not None}),
            'pts_gaps': gaps}


def run_job(args):
    phases = {'job_started': time.monotonic()}
    from relay.soak import require_queue_lease
    lease = require_queue_lease()
    verify_sources(ROOT, args.sources)
    launcher_receipt = require_root_launcher(args)
    runtime_receipt = preflight_runtime()
    check_ports()
    args.output.mkdir(parents=True, exist_ok=False)
    from importlib import metadata
    import cv2
    import psutil
    import relay.stream as stream
    from relay.mediamtx import MediaMTX, verified_binary
    from relay.runtime import make_engine, run
    from relay.security import Credentials, RelayAddress
    from bench.efficiency.profile import Profiler, encode_worker_profiled, summarize
    from bench.efficiency.telemetry import HostSamples
    cv2.setNumThreads(1)
    address = RelayAddress('127.0.0.1', 29351, 28891, 28555)
    phone, internal = Credentials.generate(), Credentials.generate()
    binary = verified_binary(args.mediamtx_dir)
    from models.prepare import verified_path
    model_receipts = {name: verified_path(name, args.model_cache)[1]
                      for name in ('ppocr-v6-tiny', 'ppocr-v6-small')}
    context = mp.get_context('spawn')
    sender_stop, observer_stop = context.Event(), context.Event()
    shared_window = context.Array('d', [float('inf'), float('inf')], lock=False)
    first_observer = context.Value('d', 0.)
    window = CollectionWindow(threading.Event(), first_observer, shared_window,
                              args.warmup, args.startup_timeout)
    previous_signals = {}
    for sig in (signal.SIGTERM, signal.SIGINT):
        previous_signals[sig] = signal.signal(sig, lambda *_: window.set())
    summary, process_receipts, failure = None, [], None
    profiler = server = None
    phases['imports_and_hashes_ready'] = time.monotonic()
    samples = HostSamples()
    samples.start()
    try:
        with ExitStack() as stack:
            server = stack.enter_context(MediaMTX(address, phone, internal, binary))
            phases['mediamtx_ready'] = time.monotonic()
            # Evidence hooks are required even for the uninstrumented control.
            # Install before detector/motion workers inherit their thread hook.
            profiler = Profiler(float('inf'), float('inf'), window=shared_window,
                                observe=window.observe, instrument=args.instrument)
            profiler.start()
            engine = make_engine(args.model_cache, provider='cuda')
            engine_owned = True
            try:
                phases['engine_ready'] = time.monotonic()
                # Fuses bound cancellation; neither defines a measurement window.
                window.startup_deadline = time.monotonic() + args.startup_timeout
                source_fuse = window.startup_deadline + args.warmup + 120. + 30.
                publisher = context.Process(target=sender,
                    args=(address.rtmp('camera', phone), args.output, sender_stop, source_fuse), name='w11-sender')
                publisher.start()
                stack.callback(stop, publisher, sender_stop, 'sender', process_receipts)
                subscriber = context.Process(target=observer,
                    args=(address.rtsp('shielded'), observer_stop, args.output, first_observer), name='w11-observer')
                subscriber.start()
                stack.callback(stop, subscriber, observer_stop, 'observer', process_receipts)
                original = stream._encode_worker
                stream._encode_worker = partial(encode_worker_profiled, window=shared_window,
                    directory=args.output, instrument=args.instrument)
                stack.callback(setattr, stream, '_encode_worker', original)
                engine_owned = False
                phases['runtime_started'] = time.monotonic()
                summary = run(engine, address, phone, internal, None, window, seconds=None, encoder='h264_nvenc')
                phases['runtime_returned'] = time.monotonic()
            finally:
                phases.setdefault('runtime_returned', time.monotonic())
                if engine_owned:
                    engine.close()
                profiler.close(args.output, 'relay')
    except Exception as error:
        failure = {'error_class': type(error).__name__, 'message': 'Profile failed; upstream diagnostics suppressed'}
    finally:
        if profiler and sys.getprofile() is not None:
            profiler.close(args.output, 'relay')
        for sig, previous in previous_signals.items():
            signal.signal(sig, previous)
        if server is not None:
            process_receipts.append({'role': 'mediamtx', 'pid': server.process.pid,
                'exitcode': server.process.returncode, 'alive': server.process.poll() is None})
        samples.close(args.output / 'host-samples.json')
        phases['job_finished'] = time.monotonic()
        start = shared_window[0] if window.ready is not None else None
        planned_end = shared_window[1] if start is not None else None
        returned = phases.get('runtime_returned', phases['job_finished'])
        actual_end = max(start, min(returned, planned_end)) if start is not None else None
        elapsed = actual_end - start if start is not None else 0.
        phases.update(pipeline_ready=window.ready, steady_start=start, steady_end=actual_end,
                      steady_planned_end=planned_end, window_completed_at=window.completed)
        reasons = list(window.failures)
        if failure or not summary or summary.get('status') != 'stopped' or summary.get('cleanup_errors'):
            reasons.append('runtime-failed-or-cleanup-errors')
        if window.completed is None or start is None or elapsed < 120.:
            reasons.append('steady-window-incomplete')
        steady = lambda row: start is not None and start <= row['at'] < actual_end
        events = list(window.events)
        encoded = [row for row in events if row['kind'] == 'encoded' and steady(row)]
        source = [row for row in events if row['kind'] == 'source' and steady(row)]
        detectors = {lane: [row for row in events if row['kind'] == 'detector'
                     and row.get('lane') == lane and row.get('inference_completed') and steady(row)]
                     for lane in ('fast', 'accurate')}
        live = [row for row in encoded if row.get('state') == 'LIVE' and row.get('slate') is False]
        captures, span_files, errors, unfinished = {}, [], [], 0
        def capture(name):
            try:
                data = json.loads((args.output / name).read_text())
                if not isinstance(data, dict):
                    raise ValueError('capture-object-required')
                if name.startswith('spans-'):
                    if (data.get('role') not in ('relay', 'encoder') or not isinstance(data.get('rows'), list)
                            or not isinstance(data.get('errors'), list) or type(data.get('unfinished_spans')) is not int
                            or data['unfinished_spans'] < 0):
                        raise ValueError('invalid-span-capture')
                    for row in data['rows']:
                        if not isinstance(row, dict) or any(type(row.get(key)) not in (int, float)
                                or not math.isfinite(row[key]) for key in ('start', 'end', 'wall_seconds', 'caller_cpu_seconds')):
                            raise ValueError('invalid-span-row')
                elif name in ('sender.json', 'observer.json'):
                    if not isinstance(data.get('frames'), list) or not isinstance(data.get('status'), str):
                        raise ValueError('invalid-media-capture')
                    for row in data['frames']:
                        if not isinstance(row, dict) or type(row.get('at')) not in (int, float) or not math.isfinite(row['at']):
                            raise ValueError('invalid-media-row')
                elif name == 'host-samples.json' and not isinstance(data.get('rows'), list):
                    raise ValueError('invalid-host-capture')
                captures[name] = sha256(args.output / name)
                return data
            except (OSError, ValueError):
                reasons.append('missing-or-invalid-capture:' + name)
                return {}
        sent = capture('sender.json')
        observed = capture('observer.json')
        host = capture('host-samples.json')
        if sent.get('status') != 'closed' or not any(steady(row) for row in sent.get('frames', [])):
            reasons.append('sender-no-steady-or-failed')
        expected_eof = (observed.get('status') == 'eof' and planned_end is not None
                        and isinstance(observed.get('finished_at'), (int, float))
                        and observed['finished_at'] >= planned_end)
        if observed.get('status') != 'closed' and not expected_eof:
            reasons.append('observer-failed-or-ended-before-stop')
        observed_frames = [row for row in observed.get('frames', []) if steady(row)]
        if not observed_frames or not any(row.get('all_dark') is False for row in observed_frames):
            reasons.append('no-decoded-nonblack-observer-population')
        if not host.get('rows'):
            reasons.append('host-capture-empty')
        spans = []
        for path in sorted(args.output.glob('spans-*.json')):
            blob = capture(path.name)
            spans.append(blob)
            span_files.append(path.name)
            errors.extend(blob.get('errors', []))
            unfinished += blob.get('unfinished_spans', 0)
        for role in ('relay', 'encoder'):
            if not any(blob.get('role') == role for blob in spans):
                reasons.append('missing-critical-span-capture:' + role)
        if errors or unfinished:
            reasons.append('instrumentation-errors-or-unfinished-spans')
        for role in ('sender', 'observer'):
            matching = [row for row in process_receipts if row['role'] == role]
            if not matching or any(row['alive'] or row['exitcode'] != 0 or row.get('forced') for row in matching):
                reasons.append('process-not-clean:' + role)
        servers = [row for row in process_receipts if row['role'] == 'mediamtx']
        if not servers or any(row['alive'] or row['exitcode'] not in (0, -signal.SIGTERM) for row in servers):
            reasons.append('process-not-clean:mediamtx')
        exits = [row for row in events if row['kind'] == 'encoder-exit']
        if not exits or any(row.get('alive') is not False or row.get('exitcode') != 0 for row in exits):
            reasons.append('encoder-exit-not-observed-clean')
        process_receipts.extend({'role': 'encoder', **row} for row in exits)
        if not source:
            reasons.append('no-steady-source')
        if not encoded:
            reasons.append('no-steady-encoded-output')
        if not live:
            reasons.append('no-steady-LIVE-nonslate-output')
        for lane, calls in detectors.items():
            if not calls:
                reasons.append('no-steady-completed-inference:' + lane)
        from multiprocessing import resource_tracker
        tracker_pid = resource_tracker._resource_tracker._pid
        descendants = [{'pid': p.pid, 'name': p.name(), 'auxiliary_tracker': p.pid == tracker_pid}
                       for p in psutil.Process().children(recursive=True) if p.is_running()]
        if any(not row['auxiliary_tracker'] for row in descendants):
            reasons.append('owned-process-survived-at-return')
        write(args.output / 'processes.json', {'children': process_receipts, 'survivors_at_job_return': descendants,
            'final_queue_process_audit_required': True, 'resource_tracker_exits_with_job': tracker_pid})
        write(args.output / 'collection-events.json', {'events': events, 'readiness': window.first})
        for name in ('processes.json', 'collection-events.json'):
            captures[name] = sha256(args.output / name)
        rows = [row for blob in spans for row in blob.get('rows', [])]
        for row in rows:
            row['window'] = 'steady' if start is not None and start <= row['start'] <= row['end'] <= actual_end else 'outside-steady'
        table = summarize(rows, len(source), elapsed)
        populations = {'source': population(source), 'encoded': population(encoded), 'encoded_live': population(live),
                       'decoded_observer': population(observed_frames),
                       'sender': population([row for row in sent.get('frames', []) if steady(row)])}
        populations.update({'detector-' + lane: population(calls) for lane, calls in detectors.items()})
        report = {'schema': 2, 'status': 'failed' if reasons else 'collected-ungraded',
            'failure': failure, 'collection_failures': sorted(set(reasons)), 'lease': lease,
            'forced': os.environ.get('IRL_SHIELD_PERF_QUEUE_FORCED') == '1',
            'queue_receipt': os.environ.get('IRL_SHIELD_PERF_QUEUE_RECEIPT'), 'queue_trust': 'unassessed',
            'launcher_receipt': launcher_receipt, 'source_manifest_sha256': sha256(args.sources),
            'phases': phases, 'readiness_evidence': window.first, 'steady_completed': window.completed is not None,
            'measurement_seconds': elapsed, 'planned_measurement_seconds': 120.,
            'actual_warmup_seconds': max(0., min(returned, start) - window.ready) if start is not None else 0.,
            'source_frames': len(source), 'populations': populations,
            'denominator': 'Decoded source timestamps within the observed [steady_start, steady_end) interval, before queue drops',
            'table': table, 'instrumentation_errors': errors, 'unfinished_spans': unfinished,
            'missing_stage_spans': [name for name, row in table.items() if row['evidence_kind'] == 'unknown'],
            'profile_complete': False, 'span_files': span_files, 'capture_sha256': captures,
            'runtime': summary, 'archive_enabled': False, 'encoder': 'h264_nvenc', 'detector_provider': 'cuda',
            'runtime_sdk': runtime_receipt, 'models': model_receipts, 'mediamtx_sha256': sha256(binary),
            'versions': {name: metadata.version(name) for name in ('av', 'onnxruntime-gpu', 'rapidocr', 'psutil')},
            'quality_scorecard': None, 'before_after': None, 'performance_claim': None,
            'gpu_kernel_ms': None, 'gpu_transfer_counts_and_bytes': None, 'live_decode_pairing_verified': False,
            'limitations': ['Collection readiness is not a privacy, quality or 30fps grade.',
                'Observer PTS has no measured source-generation association; raw ingest/output generations remain separate.',
                'GPU kernel/copy metrics require a supported root-queued GPU profiler; step1 remains incomplete.',
                'Callable wall spans overlap across threads/processes and caller CPU excludes native worker CPU.',
                'Sender/observer process CPU is separate from relay; queue contamination includes the entire job tree.',
                'Missing stage selectors and profiling overhead remain explicit; IPC bytes are serialized endpoints, not PCIe copies.']}
        write(args.output / 'profile.json', report)
    if report['collection_failures']:
        raise RuntimeError('Profile incomplete; inspect retained receipt')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model-cache', type=Path, required=True)
    parser.add_argument('--mediamtx-dir', type=Path, required=True)
    parser.add_argument('--warmup', type=float, default=15.)
    parser.add_argument('--instrument', action='store_true')
    parser.add_argument('--startup-timeout', type=float, default=180.)
    parser.add_argument('--launcher-receipt', type=Path, required=True)
    parser.add_argument('--launcher-sha256', required=True)
    args = parser.parse_args()
    if not 5 <= args.warmup <= 30:
        parser.error('Warmup must be between 5 and 30 seconds')
    if not 30 <= args.startup_timeout <= 300:
        parser.error('Startup fuse must be finite and between 30 and 300 seconds')
    run_job(args)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        detail = str(error) if isinstance(error, PreflightError) else type(error).__name__
        print('W11 profile failed: ' + detail, file=sys.stderr)
        raise SystemExit(1) from None

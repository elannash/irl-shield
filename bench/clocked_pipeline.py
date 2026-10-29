"""Clocked benchmark file adapter; all generated media is benchmark-only.

Existing dependencies: NumPy (BSD-3-Clause), OpenCV (Apache-2.0), psutil
(BSD-3-Clause); notices are in models/licenses/dependencies.json. The installed
FFmpeg is LGPL-2.1-or-later, or GPL-2.0-or-later with GPL features such as libx264:
https://ffmpeg.org/legal.html . Hardware codecs use the existing vendor runtime.
No binary, model, dataset or external asset is introduced or bundled here.
"""
from dataclasses import asdict
from fractions import Fraction
import hashlib
import argparse
from importlib.metadata import version, PackageNotFoundError
import json
import math
import os
from pathlib import Path
import platform
import queue
import subprocess
import threading
import time
import zipfile

import cv2
import numpy as np

from shield.types import Frame


ROOT = Path(__file__).resolve().parents[1]


def quantiles(values):
    return {key: float(np.percentile(values, percentile)) if values else None
            for key, percentile in (('p50', 50), ('p95', 95))}


def coverage_distribution(records):
    """Frame-weighted nearest-lane ages, with missing coverage kept explicit."""
    count=len(records)
    result={'frames':count,
            'ok_fraction':sum(row['coverage']['ok'] for row in records)/count if count else None,
            'reasons':{reason:sum(row['coverage']['reason']==reason for row in records)
                       for reason in sorted({row['coverage']['reason'] for row in records})}}
    for lane in ('fast','accurate'):
        ages=[row['coverage'][lane+'_age'] for row in records]
        result[lane]={'age_frames':quantiles([age for age in ages if age is not None]),
                      'missing_fraction':sum(age is None for age in ages)/count if count else None}
    return result


def measurement_windows(records, *, source_fps, origin, ended_at, warmup_frames):
    """Keep full/startup receipts and select the post-warmup steady metrics."""
    if (not math.isfinite(source_fps) or source_fps <= 0 or not records
            or not isinstance(warmup_frames, int) or not 0 <= warmup_frames < len(records)):
        raise ValueError('A nonempty steady window after warmup is required')

    def summarize(rows):
        count = len(rows)
        span = rows[-1]['encoded_at'] - rows[0]['encoded_at'] if count > 1 else None
        rate = (count - 1) / span if span is not None and span > 0 else None
        protected = sum(row['protected'] or row['state'] != 'LIVE' for row in rows)
        return {
            'frames': count, 'encoded_frames': count,
            'start_frame': rows[0]['frame'] if rows else None,
            'stop_frame_exclusive': rows[-1]['frame'] + 1 if rows else None,
            'start_pts': rows[0]['pts'] if rows else None,
            'source_duration_seconds': count / source_fps,
            'first_encoded_at': rows[0]['encoded_at'] if rows else None,
            'last_encoded_at': rows[-1]['encoded_at'] if rows else None,
            'egress_span_seconds': span, 'fps': rate, 'output_wall_rate_fps': rate,
            'output_clock_drift_seconds': span - (count - 1) / source_fps if span is not None else None,
            'realtime_added_latency_seconds': quantiles([row['encoded_source_clock_latency'] for row in rows]),
            'source_arrival_latency_seconds': quantiles([row['encoded_source_arrival_latency'] for row in rows
                                                        if row['encoded_source_arrival_latency'] is not None]),
            'presentation_lateness_seconds': quantiles([row['presentation_lateness'] for row in rows]),
            'presentation_delay_seconds': quantiles([row['emitted_at']-(origin+row['pts']) for row in rows]),
            'coverage':coverage_distribution(rows),
            'deadline_miss_count': sum(row['presentation_lateness'] > 1e-6 for row in rows),
            'deadline_miss_over_frame_period_count': sum(row['presentation_lateness'] > 1 / source_fps for row in rows),
            'protected_frames': protected, 'protected_fraction': protected / count if count else None,
            'live_frames': count - protected,
        }

    full = summarize(records)
    full['seconds'] = ended_at - origin
    full['full_pipeline_fps'] = len(records) / full['seconds']
    startup = summarize(records[:warmup_frames])
    startup['first_packet_delay_seconds'] = records[0]['encoded_at'] - origin
    startup['seconds'] = records[warmup_frames - 1]['encoded_at'] - origin if warmup_frames else None
    steady = summarize(records[warmup_frames:])
    steady['seconds'] = ended_at - (origin + steady['start_pts'])
    return {'full': full, 'startup': startup, 'steady': steady}


def perf_health():
    """Read-only host pressure, swap and load receipt; never simulate pressure."""
    system = platform.system()
    load = list(os.getloadavg())
    cpus = os.cpu_count()
    receipt = {'platform': system, 'observed_at': time.monotonic(),
               'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
               'load_average': load, 'cpu_count': cpus,
               'load_per_cpu': load[0] / cpus if cpus else None,
               'pressure_state': 'unknown', 'pressure_level': None, 'raw': {}}
    if system == 'Linux':
        receipt['health_adapter'] = 'linux-psi-memavailable-v1'
        paths = {'memory_psi': '/proc/pressure/memory', 'cpu_psi': '/proc/pressure/cpu',
                 'io_psi': '/proc/pressure/io', 'meminfo': '/proc/meminfo', 'vmstat': '/proc/vmstat'}
        for name, path in paths.items():
            try:
                row = {'path': path, 'returncode': 0, 'stdout': Path(path).read_text(), 'stderr': ''}
            except OSError as error:
                row = {'path': path, 'returncode': 1, 'stdout': '', 'stderr': str(error)}
            receipt['raw'][name] = row
        receipt['thresholds'] = {'normal_memory_some_avg10_below_percent': 1.,
                                 'normal_memory_full_avg10_below_percent': .1,
                                 'normal_available_at_least_bytes': 2 * 1024**3,
                                 'normal_available_at_least_fraction': .1,
                                 'critical_memory_full_avg10_at_least_percent': 1.,
                                 'critical_available_below_bytes': 1024**3,
                                 'critical_available_below_fraction': .05}
        receipt['policy_source'] = 'docs/LINUX_BENCH.md; benchmark policy, not a kernel pressure classification'
        receipt['kernel_source'] = 'https://docs.kernel.org/accounting/psi.html'
        try:
            if any(receipt['raw'][key]['returncode'] for key in ('memory_psi', 'meminfo', 'vmstat')):
                raise ValueError('Required Linux health file is unavailable')
            memory = {line.split(':', 1)[0]: int(line.split()[1]) * 1024
                      for line in receipt['raw']['meminfo']['stdout'].splitlines() if ':' in line}
            psi = {line.split()[0]: {key: float(value) if key != 'total' else int(value)
                                    for key, value in (part.split('=') for part in line.split()[1:])}
                   for line in receipt['raw']['memory_psi']['stdout'].splitlines()}
            for kind in ('some', 'full'):
                if any(not math.isfinite(psi[kind][key]) or not 0 <= psi[kind][key] <= 100
                       for key in ('avg10', 'avg60', 'avg300')) or psi[kind]['total'] < 0:
                    raise ValueError('Invalid memory PSI value')
            total, available = memory['MemTotal'], memory['MemAvailable']
            if not 0 < total or not 0 <= available <= total or not 0 <= memory['SwapFree'] <= memory['SwapTotal']:
                raise ValueError('Invalid Linux memory counters')
            vmstat = {line.split()[0]: int(line.split()[1]) for line in receipt['raw']['vmstat']['stdout'].splitlines()}
            receipt.update(memory_psi=psi, mem_available_bytes=available, mem_total_bytes=total,
                           mem_available_fraction=available / total, swap_total_bytes=memory['SwapTotal'],
                           swap_used_bytes=memory['SwapTotal'] - memory['SwapFree'],
                           swap_pages_in=vmstat['pswpin'], swap_pages_out=vmstat['pswpout'])
            critical = psi['full']['avg10'] >= 1. or available < 1024**3 or available / total < .05
            normal = (psi['some']['avg10'] < 1. and psi['full']['avg10'] < .1
                      and available >= 2 * 1024**3 and available / total >= .1)
            receipt['pressure_state'] = 'critical' if critical else 'normal' if normal else 'warn'
        except (ValueError, KeyError, IndexError) as error:
            receipt['reason'] = str(error)
        return receipt
    if system != 'Darwin':
        receipt['reason'] = 'macOS pressure/swap queries are unavailable on this platform'
        return receipt
    # With no -l/-p allocation request, Apple's tool prints statistics and exits:
    # https://github.com/apple-oss-distributions/system_cmds/blob/system_cmds-880.120.1/memory_pressure.tproj/memory_pressure.c#L643
    commands = {'memory_pressure': ['memory_pressure', '-Q'],
                'swapusage': ['sysctl', 'vm.swapusage'],
                'pressure_level': ['sysctl', 'kern.memorystatus_vm_pressure_level']}
    for name, command in commands.items():
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
            row = {'command': command, 'returncode': result.returncode,
                   'stdout': result.stdout, 'stderr': result.stderr}
        except (OSError, subprocess.TimeoutExpired) as error:
            row = {'command': command, 'returncode': None, 'stdout': '', 'stderr': str(error)}
        receipt['raw'][name] = row
    level_row = receipt['raw']['pressure_level']
    if all(row['returncode'] == 0 for row in receipt['raw'].values()):
        try:
            level = int(level_row['stdout'].rsplit(':', 1)[-1].strip())
        except ValueError:
            level = None
        receipt['pressure_level'] = level
        # The sysctl returns dispatch flags, not the kernel's internal0-based enum.
        # https://github.com/apple-oss-distributions/xnu/blob/main/bsd/kern/kern_memorystatus_notify.c#L1766
        receipt['pressure_state'] = {1: 'normal', 2: 'warn', 4: 'critical'}.get(level, 'unknown')
    return receipt


def source_window(media, options, max_frames=None):
    """Plan repeated source frames as warmup plus the requested steady duration."""
    fps = media['fps']
    warmup_seconds = float(options.get('warmup_seconds', 10.))
    steady_seconds = float(options.get('repeat_seconds', media['frames'] / fps))
    if not math.isfinite(warmup_seconds) or warmup_seconds < 0 or not math.isfinite(steady_seconds) or steady_seconds <= 0:
        raise ValueError('Warmup must be nonnegative and steady duration must be positive')
    warmup = round(warmup_seconds * fps)
    steady = round(steady_seconds * fps)
    if max_frames is not None:
        steady = min(steady, max_frames)
    if steady < 1:
        raise ValueError('A nonempty steady source window is required')
    return {'warmup_frames': warmup, 'steady_frames': steady, 'total_frames': warmup + steady,
            'warmup_seconds': warmup / fps, 'steady_seconds': steady / fps}


def performance_trust(performance):
    """Separate measurement validity from whether measured speed/privacy meets a target."""
    reasons = []
    steady = performance.get('steady', {})
    if steady.get('frames', 0) < 900 or steady.get('source_duration_seconds', 0) < 30:
        reasons.append('steady-window-shorter-than-30s')
    if performance.get('warmup_frames', 0) < 1:
        reasons.append('no-warmup-window')
    if performance.get('options', {}).get('contended', False):
        reasons.append('contended-diagnostic-trial')
    for phase in ('start', 'end'):
        snapshot = performance.get('perf_health', {}).get(phase, {})
        linux = snapshot.get('platform') == 'Linux'
        if snapshot.get('pressure_state') != 'normal' or (not linux and snapshot.get('pressure_level') != 1):
            reasons.append(f'{phase}-memory-pressure-{snapshot.get("pressure_state", "unknown")}')
        raw = snapshot.get('raw', {})
        required = ('memory_psi', 'meminfo', 'vmstat') if linux else ('memory_pressure', 'swapusage', 'pressure_level')
        if (linux and snapshot.get('health_adapter') != 'linux-psi-memavailable-v1') or any(raw.get(key, {}).get('returncode') != 0 for key in required):
            reasons.append(f'{phase}-health-query-incomplete')
        load = snapshot.get('load_average', [])
        if len(load) != 3 or not all(math.isfinite(value) for value in load) or not snapshot.get('cpu_count'):
            reasons.append(f'{phase}-load-query-incomplete')
    return {'valid': not reasons, 'reasons': reasons}


def fingerprint():
    paths = set((ROOT / 'shield').glob('*.py'))
    paths.update(ROOT / name for name in (
        'bench/clocked_pipeline.py', 'bench/clocked_bench.py', 'bench/cross_host.py', 'bench/scoring.py',
        'bench/metrics.py', 'bench/pipeline.py', 'bench/onnx_detectors.py',
        'bench/run.py', 'bench/synthetic.py', 'bench/judges.py', 'bench/scheduled.py', 'fixtures/prepare.py',
        'bench/vision.py', 'bench/static_model.py', 'models/manifest.json',
        'fixtures/manifest.json', 'requirements.txt', 'requirements-models.txt',
        'Sources/VisionBridge/main.swift'))
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path.relative_to(ROOT)).encode() + b'\0' + path.read_bytes())
    return digest.hexdigest()


def host_environment():
    """Keep processing and grading runtimes distinct from host-neutral source identity."""
    packages = {}
    for name in ('onnxruntime', 'onnxruntime-gpu', 'rapidocr', 'numpy', 'psutil'):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            continue
    bridge = ROOT / '.build/vision-bridge'
    return {'platform': platform.platform(), 'system': platform.system(), 'host': platform.node(),
            'python': platform.python_version(), 'opencv': cv2.__version__, 'cpu_count': os.cpu_count(),
            'packages': packages, 'ffmpeg': subprocess.check_output(['ffmpeg', '-version'], text=True).splitlines()[0],
            'apple_vision_bridge_sha256': file_sha256(bridge) if bridge.exists() else None}


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def probe_media(path):
    """Read actual decoded media PTS; container frame-count metadata is insufficient."""
    command = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_frames',
               '-show_entries', 'stream=width,height,avg_frame_rate:frame=best_effort_timestamp_time',
               '-of', 'json', str(path)]
    data = json.loads(subprocess.check_output(command, text=True, timeout=120))
    stream = data['streams'][0]
    pts = [float(frame['best_effort_timestamp_time']) for frame in data['frames']]
    fps = float(Fraction(stream['avg_frame_rate']))
    if not pts or fps <= 0 or not math.isfinite(fps):
        raise ValueError('Media has no valid video frame clock')
    if any(not math.isfinite(value) or not math.isclose(value, index / fps, abs_tol=1e-5)
           for index, value in enumerate(pts)):
        raise ValueError('Media PTS is not a zero-origin constant-rate frame clock')
    return {'frames': len(pts), 'fps': fps, 'resolution': [stream['width'], stream['height']],
            'pts': pts, 'duration': len(pts) / fps}


class VideoSource:
    """A paced decode producer; a bounded queue isolates an obstructed encoder pipe.

    Queue overflow is an explicit ingest drop, so the engine must emit a protected
    placeholder. It cannot silently turn a slow transport into an unbounded buffer.
    """
    def __init__(self, path, media, max_frames=None, repeat_seconds=None, skip_ranges=(), delay_seconds=1.):
        self.path = Path(path)
        self.media = media
        self.fps = media['fps']
        total = max(media['frames'], round(repeat_seconds * self.fps)) if repeat_seconds else media['frames']
        self.total_frames = min(total, max_frames) if max_frames is not None else total
        if self.total_frames < 1:
            raise ValueError('A nonempty source is required')
        if any(not 0 < start < end for start, end in skip_ranges):
            raise ValueError('Ingest skip ranges must start after the initial clock-anchor frame')
        self.duration = self.total_frames / self.fps
        self.skip_ranges = skip_ranges
        self.arrivals = {}
        self.decoded_at = {}
        self.injected_drops = []
        self.queue_drops = []
        if not math.isfinite(delay_seconds) or not 0 <= delay_seconds <= 1:
            raise ValueError('Source buffering requires a delay between zero and one second')
        self.buffer_capacity_frames = max(1, math.ceil(self.fps * (delay_seconds + 1)))
        self.frames = queue.Queue(maxsize=self.buffer_capacity_frames)
        self.stop = threading.Event()
        self.finished = threading.Event()
        self.error = None
        self.thread = None

    def start(self, origin):
        self.origin = origin
        self.thread = threading.Thread(target=self._produce, name='clocked-source', daemon=True)
        self.thread.start()

    def _produce(self):
        capture = None
        try:
            capture = cv2.VideoCapture(str(self.path), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 2])
            if not capture.isOpened():
                raise RuntimeError(f'Cannot decode {self.path}')
            for index in range(self.total_frames):
                pts = index / self.fps
                if self.stop.wait(max(0., self.origin + pts - time.monotonic())):
                    return
                if index and index % self.media['frames'] == 0:
                    if not capture.set(cv2.CAP_PROP_POS_FRAMES, 0):
                        raise RuntimeError('Cannot rewind repeated source fixture')
                self.arrivals[index] = time.monotonic()
                ok, pixels = capture.read()
                if not ok:
                    raise RuntimeError(f'Source decode truncated at frame {index}')
                self.decoded_at[index] = time.monotonic()
                if any(start <= pts < end for start, end in self.skip_ranges):
                    self.injected_drops.append(index)
                    continue
                frame = Frame(index, pts, pixels)
                try:
                    self.frames.put_nowait(frame)
                except queue.Full:
                    try:
                        dropped = self.frames.get_nowait()
                        self.queue_drops.append(dropped.index)
                    except queue.Empty:
                        pass
                    self.frames.put_nowait(frame)
        except Exception as error:
            self.error = error
        finally:
            if capture is not None:
                capture.release()
            self.finished.set()

    @property
    def ended(self):
        if self.error is not None:
            raise RuntimeError(f'Source producer failed: {self.error}') from self.error
        return self.finished.is_set() and self.frames.empty()

    def poll(self):
        if self.error is not None:
            raise RuntimeError(f'Source producer failed: {self.error}') from self.error
        frames = []
        while True:
            try:
                frames.append(self.frames.get_nowait())
            except queue.Empty:
                return frames

    def close(self):
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                raise RuntimeError('Source producer did not stop')


class FFmpegSink:
    """Observe mux packet counters on progress stdout, with actual mask pixels.

    FFmpeg 8's progress `frame` is ost->packets_written, rather than an ingest
    timer: https://github.com/FFmpeg/FFmpeg/blob/n8.0/fftools/ffmpeg.c#L557
    Its mux counter increments immediately before mux submission. Observation
    times include progress batching and pipe-reader scheduling; decoded media
    count/PTS verification after drain independently confirms the actual file.
    """
    def __init__(self, path, resolution, fps, codec):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.resolution, self.fps, self.codec = resolution, fps, codec
        if codec not in ('h264_videotoolbox', 'h264_nvenc', 'libx264'):
            raise ValueError('Unsupported benchmark encoder')
        self.completions = []
        self.progress = []
        self.error = None
        self.process = self.reader = self.log = self.masks = None
        width, height = resolution
        codec_options = (['-realtime', '1','-flags','+low_delay'] if codec == 'h264_videotoolbox'
                         else ['-preset', 'p4', '-tune', 'ull', '-rc-lookahead', '0'] if codec == 'h264_nvenc'
                         else ['-preset', 'ultrafast', '-tune', 'zerolatency', '-threads', '2'])
        self.command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostats', '-y',
                        '-filter_threads','1','-threads','2','-probesize','32','-analyzeduration','0',
                        '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{width}x{height}',
                        '-r', str(fps), '-i', 'pipe:0', '-an', '-c:v', codec, *codec_options,
                        '-bf', '0', '-b:v', '10M', '-pix_fmt', 'yuv420p', '-flush_packets', '1',
                        '-stats_period', '0.01', '-progress', 'pipe:1', str(self.path)]

    def start(self):
        self.log = self.path.with_suffix('.ffmpeg.log').open('w')
        self.masks = zipfile.ZipFile(self.path.with_suffix('.mask-pixels.zip'), 'w',
                                     compression=zipfile.ZIP_DEFLATED, compresslevel=1)
        self.process = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.log, bufsize=0)
        self.reader = threading.Thread(target=self._progress, name='clocked-egress', daemon=True)
        self.reader.start()

    def _progress(self):
        try:
            for line in iter(self.process.stdout.readline, b''):
                key, _, value = line.decode().strip().partition('=')
                if key != 'frame':
                    continue
                count = int(value)
                at = time.monotonic()
                if count < len(self.completions):
                    raise RuntimeError('Encoder packet counter regressed')
                self.progress.append({'packets_written': count, 'observed_at': at})
                self.completions.extend([at] * (count - len(self.completions)))
        except Exception as error:
            self.error = error

    def write(self, frame):
        height, width = frame.pixels.shape[:2]
        if [width, height] != self.resolution or frame.mask.shape != (height, width):
            raise ValueError('Encoder resolution or actual mask shape changed')
        pixels = memoryview(np.ascontiguousarray(frame.pixels)).cast('B')
        while pixels:
            written = self.process.stdin.write(pixels)
            if not written:
                raise BrokenPipeError('Encoder accepted zero input bytes')
            pixels = pixels[written:]
        packed = np.packbits(frame.mask > 0, bitorder='little')
        self.masks.writestr(f'{frame.index:08d}.bin', packed.tobytes())

    def finish(self):
        self.process.stdin.close()
        try:
            code = self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.abort()
            raise RuntimeError('Encoder did not drain within 30 seconds')
        self.reader.join(timeout=5)
        self.process.stdout.close()
        self.log.close()
        self.masks.close()
        if self.reader.is_alive():
            raise RuntimeError('Encoder progress reader did not stop')
        if code:
            raise RuntimeError(f'Encoder failed exit {code}: {self.path.with_suffix(".ffmpeg.log").read_text()}')
        if self.error is not None:
            raise RuntimeError(f'Encoder progress failed: {self.error}') from self.error
        return list(self.completions)

    def abort(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
            for stream in (self.process.stdin, self.process.stdout):
                if stream is not None and not stream.closed:
                    stream.close()
        if self.reader is not None:
            self.reader.join(timeout=5)
            if self.reader.is_alive():
                raise RuntimeError('Encoder progress reader survived abort')
        if self.log is not None:
            self.log.close()
        if self.masks is not None:
            self.masks.close()


def drive(source, engine, sink, *, clock=time.monotonic, sleep=time.sleep, poll_seconds=.002):
    """Drive a paced source and independent presentation clock through public adapters.

    Source exposes fps/total_frames/duration/arrivals/ended and start/poll/close.
    Sink exposes start/write/finish/abort; finish returns observed packet times.
    A dedicated ingest worker submits decoded source frames while the caller
    polls and writes output. Only the engine's own lock serializes these paths.
    Runtime ends after encoder drain; every owned worker is joined on exit.
    """
    origin = clock()
    records = []
    finished = False
    ingest = None
    ingest_started = False
    ingest_stop = threading.Event()
    ingest_done = threading.Event()
    ingest_errors = queue.SimpleQueue()

    def consume():
        try:
            while not ingest_stop.is_set():
                for frame in source.poll():
                    if ingest_stop.is_set():
                        return
                    engine.submit(frame, now=clock())
                if source.ended:
                    engine.end(source.total_frames - 1)
                    return
                ingest_stop.wait(poll_seconds)
        except Exception as error:
            ingest_errors.put(error)
        finally:
            ingest_done.set()

    def check_ingest():
        try:
            error = ingest_errors.get_nowait()
        except queue.Empty:
            return
        raise RuntimeError(f'Source ingest failed: {error}') from error

    try:
        if not math.isfinite(source.fps) or source.fps <= 0 or source.total_frames < 1 or poll_seconds <= 0:
            raise ValueError('A positive source frame clock and poll interval are required')
        sink.start()
        source.start(origin)
        ingest = threading.Thread(target=consume, name='clocked-ingest', daemon=True)
        ingest.start()
        ingest_started = True
        while True:
            check_ingest()
            for frame in engine.poll(now=clock()):
                if (frame.index != len(records) or frame.index >= source.total_frames or not math.isfinite(frame.pts)
                        or not math.isclose(frame.pts, frame.index / source.fps, abs_tol=1e-5)):
                    raise RuntimeError('Frame accounting: output index or PTS differs from source clock')
                emitted_at = clock()
                if not math.isfinite(frame.deadline) or emitted_at + 1e-6 < frame.deadline:
                    raise RuntimeError('Frame accounting: output preceded its presentation deadline')
                record = {
                    'frame': frame.index, 'pts': frame.pts,
                    'quads': np.asarray(frame.quads).tolist(),
                    'mask_fraction': float((frame.mask > 0).mean()),
                    'mask_sha256': hashlib.sha256(frame.mask.tobytes()).hexdigest(),
                    'coverage': asdict(frame.coverage), 'state': frame.state,
                    'deadline': frame.deadline, 'presented_at': frame.presented_at,
                    'emitted_at': emitted_at,
                    'presentation_lateness': max(0., emitted_at - frame.deadline),
                    'protected': frame.protected, 'slate': frame.slate,
                }
                sink.write(frame)
                record['encoder_submitted_at'] = clock()
                records.append(record)
                check_ingest()
            if ingest_done.is_set() and engine.drained:
                check_ingest()
                break
            if clock() - origin > source.duration + 30:
                raise TimeoutError('Clocked adapter did not drain within source duration plus 30 seconds')
            sleep(poll_seconds)
        completions = sink.finish()
        end = clock()
        finished = True
        if len(records) != source.total_frames or len(completions) != source.total_frames:
            raise RuntimeError(f'Frame accounting: source={source.total_frames}, presented={len(records)}, packets={len(completions)}')
        if any(not math.isfinite(at) or at < records[i]['presented_at']
               or (i > 0 and at < completions[i - 1]) for i, at in enumerate(completions)):
            raise RuntimeError('Frame accounting: invalid or nonmonotonic packet observation')
        for record, completed in zip(records, completions):
            arrival = source.arrivals.get(record['frame'])
            record.update({
                'source_arrived_at': arrival, 'encoded_at': completed,
                'encoded_source_clock_latency': completed - (origin + record['pts']),
                'encoded_source_arrival_latency': completed - arrival if arrival is not None else None,
            })
        latencies = [r['encoded_source_clock_latency'] for r in records if 'encoded_at' in r]
        span = completions[-1] - completions[0] if len(completions) > 1 else 0.
        return {
            'frames': len(records), 'encoded_frames': len(completions),
            'source_frames': source.total_frames, 'source_fps': source.fps,
            'source_duration_seconds': source.duration, 'clock_origin': origin,
            'seconds': end - origin, 'fps': len(records) / (end - origin),
            'first_encoded_at': completions[0], 'last_encoded_at': completions[-1],
            'egress_span_seconds': span,
            'output_clock_drift_seconds': span - (len(completions) - 1) / source.fps,
            'output_wall_rate_fps': (len(completions) - 1) / span if span > 0 else None,
            'realtime_added_latency_seconds': quantiles(latencies),
            'source_arrival_latency_seconds': quantiles([r['encoded_source_arrival_latency'] for r in records
                                                        if r.get('encoded_source_arrival_latency') is not None]),
            'presentation_lateness_seconds': quantiles([r['presentation_lateness'] for r in records]),
            'deadline_miss_count': sum(r['presentation_lateness'] > 1e-6 for r in records),
            'deadline_miss_over_frame_period_count': sum(r['presentation_lateness'] > 1 / source.fps for r in records),
            'protected_frames': sum(r['protected'] for r in records),
            'protected_fraction': sum(r['protected'] for r in records) / len(records) if records else 1.,
            'live_frames': sum(r['state'] == 'LIVE' for r in records),
            'records': records, 'engine': engine.stats,
        }
    finally:
        ingest_stop.set()
        try:
            source.close()
        finally:
            try:
                if ingest_started:
                    ingest.join(timeout=5)
                    if ingest.is_alive():
                        raise RuntimeError('Source ingest worker did not stop')
            finally:
                try:
                    if not finished:
                        sink.abort()
                finally:
                    engine.close()


class ResourceSampler:
    def __init__(self):
        import psutil
        self.psutil = psutil
        self.process = psutil.Process()
        self.stop = threading.Event()
        self.samples = []
        self.cpu = {}
        self.thread = None
        self.error = None

    def sample(self):
        rss = 0
        for process in [self.process, *self.process.children(recursive=True)]:
            try:
                key = (process.pid, process.create_time())
                times = process.cpu_times()
                value = times.user + times.system
                if key not in self.cpu:
                    self.cpu[key] = [value if not self.samples else 0., value]
                self.cpu[key][1] = value
                rss += process.memory_info().rss
            except (self.psutil.NoSuchProcess, self.psutil.AccessDenied):
                continue
        self.samples.append(rss)

    def start(self):
        self.started = time.monotonic()
        self.sample()
        def collect():
            try:
                while not self.stop.wait(.01):
                    self.sample()
            except Exception as error:
                self.error = error
        self.thread = threading.Thread(target=collect, name='clocked-resources', daemon=True)
        self.thread.start()

    def finish(self):
        self.stop.set()
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            raise RuntimeError('Resource sampler did not stop')
        if self.error is not None:
            raise RuntimeError(f'Resource sampler failed: {self.error}') from self.error
        self.sample()
        elapsed = time.monotonic() - self.started
        return {'cpu_percent_one_core_100': 100 * sum(end - start for start, end in self.cpu.values()) / elapsed,
                'peak_tree_rss_mb': max(self.samples) / 1024**2,
                'resource_sampling_seconds': elapsed,
                'resource_sampling_scope': '10ms process-tree samples, including source, encoder drain and engine close'}


def run(input_path, output_path, candidate, options, max_frames=None):
    """Run after a confirmed quiet window; contended trials remain diagnostic.

    `repeat_seconds` is the steady duration, preceded by warmup_seconds(default10).
    Every success/failure receipt includes raw START/END pressure, swap and load.
    """
    if candidate == 'vision-scheduled' or options.get('fast_candidate') == 'vision-scheduled':
        raise ValueError('legacy vision-scheduled cannot be used by the two-lane clocked pipeline')
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    options = dict(options)
    start = perf_health()
    health = {'preflight': start, 'start': start}
    failure = None
    try:
        if start['pressure_state'] != 'normal' and not options.get('contended', False):
            raise RuntimeError(f'Performance trial rejected before loading: memory pressure is {start["pressure_state"]}')
        result = _run_file(input_path, output_path, candidate, options, max_frames, health)
    except BaseException as error:
        failure = error
        result = {'candidate': candidate, 'options': options, 'phase': 'failed-or-preflight-rejected',
                  'error': f'{type(error).__name__}: {error}', 'performance_valid': False}
    finally:
        end = perf_health()
    health['end'] = end
    result['perf_health'] = health
    result['perf_health_scope'] = 'Preflight before loading; START immediately before source clock; END after drain, cleanup and media verification'
    trust = performance_trust(result)
    result['performance_valid'] = failure is None and trust['valid']
    result['performance_rejection_reasons'] = trust['reasons']
    if failure is not None:
        result['performance_rejection_reasons'].append('runtime-failure-or-preflight-rejection')
    output_path.with_suffix('.performance.json').write_text(json.dumps(result, indent=2) + '\n')
    if failure is not None:
        raise failure
    return result


def _run_file(input_path, output_path, candidate, options, max_frames, health):
    """Run a real paced file → asynchronous lanes → frame clock → encoder adapter.

    Writes .masks.json, actual .mask-pixels.zip, .egress.json and .performance.json.
    Models load and warm before the source clock; OCR judging never runs here.
    All source pixels/masks/movie frames are retained; primary metrics are steady-only.
    """
    if candidate == 'vision-scheduled' or options.get('fast_candidate') == 'vision-scheduled':
        raise ValueError('legacy vision-scheduled cannot be used by the two-lane clocked pipeline')
    from bench.pipeline import detector_for
    from shield.engine import MaskingEngine
    from shield.lanes import DetectorLane
    from shield.render import Renderer

    input_path, output_path = Path(input_path), Path(output_path)
    options = dict(options)
    # Detector lanes already own their concurrency; nested OpenCV pools contend.
    cv2.setNumThreads(1)
    delay = float(options.get('delay_seconds', 1.))
    if not math.isfinite(delay) or not 0 <= delay <= 1:
        raise ValueError('Presentation delay must be between zero and one second')
    source_fingerprint = fingerprint()
    preflight = time.monotonic()
    media = probe_media(input_path)
    if not math.isclose(media['fps'], 30., abs_tol=1e-6):
        raise ValueError('Clocked benchmark requires a 30fps source')
    width, height = media['resolution']
    if min(width, height) < 720:
        raise ValueError('Clocked benchmark requires at least 720p source pixels')
    source_sha = file_sha256(input_path)
    ffmpeg_version = subprocess.check_output(['ffmpeg', '-version'], text=True).splitlines()
    window = source_window(media, options, max_frames)
    source = VideoSource(input_path, media, window['total_frames'], window['total_frames'] / media['fps'],
                         options.get('source_skip_ranges', ()), delay_seconds=delay)
    sink = FFmpegSink(output_path, media['resolution'], media['fps'], options.get('encoder', 'h264_videotoolbox'))
    sampler = ResourceSampler()
    capture = cv2.VideoCapture(str(input_path), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 2])
    try:
        ok, warm = capture.read()
        if not ok:
            raise RuntimeError('No decoded frame available for model warmup')
    finally:
        capture.release()
    backends, lanes = {}, {}
    engine = None
    fast_name = (candidate if candidate in ('unmasked', 'slate') else
                 options.get('fast_candidate', 'vision-rectangles' if candidate.startswith('vision') else 'ppocr-v6-tiny'))
    lane_specs = {
        'fast': (fast_name, float(options.get('fast_rate_hz', 30)), int(options.get('fast_width', 640)),
                 int(options.get('fast_limit_side_len', 640)), options.get('fast_provider', 'cpu')),
        'accurate': (candidate, float(options.get('accurate_rate_hz', 4)), int(options.get('accurate_width', 1280)),
                     int(options.get('limit_side_len', 960)), options.get('provider', 'cpu')),
    }
    loading = {}
    try:
        for name, (model, rate, lane_width, side, provider) in lane_specs.items():
            began = time.monotonic()
            backend = detector_for(model, {**options, 'input_size': [height, width],
                                          'detect_width': lane_width, 'limit_side_len': side,
                                          'provider': provider, 'threads': 2})
            backends[name] = backend
            pixels = cv2.resize(warm, (lane_width, round(height * lane_width / width))) if lane_width and lane_width != width else warm
            if hasattr(backend, 'detect_quads'):
                backend.detect_quads(pixels)
            else:
                backend.detect(pixels)
            loading[name] = {'seconds': time.monotonic() - began, 'candidate': model,
                             'rate_hz': rate, 'width': lane_width,
                             'metadata': getattr(backend, 'metadata', {})}
        for name, (_, rate, lane_width, _, _) in lane_specs.items():
            lanes[name] = DetectorLane(name, backends[name], rate, lane_width,
                                       fault_intervals=options.get(name + '_faults', ()))
        engine = MaskingEngine(lanes, {**options, 'fps': media['fps'], 'delay_seconds': delay},
                               renderer=Renderer(style=options.get('style', 'opaque'),
                                                 padding=options.get('padding', .3), badge=options.get('badge', False)))
    except Exception as cause:
        errors = []
        for lane in lanes.values():
            try:
                lane.close()
            except Exception as error:
                errors.append(error)
        for name, backend in backends.items():
            if name not in lanes:
                try:
                    backend.close()
                except Exception as error:
                    errors.append(error)
        if errors:
            raise ExceptionGroup('Clocked setup and cleanup failed', [cause, *errors])
        raise
    preflight_seconds = time.monotonic() - preflight
    health['start'] = perf_health()
    if health['start']['pressure_state'] != 'normal' and not options.get('contended', False):
        engine.close()
        raise RuntimeError(f'Performance trial rejected before source clock: memory pressure is {health["start"]["pressure_state"]}')
    try:
        sampler.start()
    except Exception:
        engine.close()
        raise
    try:
        result = drive(source, engine, sink)
    finally:
        resources = sampler.finish()
    output_media = probe_media(output_path)
    if (output_media['frames'] != result['frames'] or output_media['resolution'] != media['resolution']
            or not math.isclose(output_media['fps'], media['fps'], abs_tol=1e-6)):
        raise RuntimeError('Frame accounting: decoded output count, resolution or PTS differs from source clock')
    if fingerprint() != source_fingerprint:
        raise RuntimeError('Clocked pipeline source changed during measurement')
    for row in result['records']:
        row['mask_shape'] = [height, width]
        row['decoded_at'] = source.decoded_at.get(row['frame'])
    windows = measurement_windows(result['records'], source_fps=media['fps'], origin=result['clock_origin'],
                                   ended_at=result['clock_origin'] + result['seconds'], warmup_frames=window['warmup_frames'])
    result.update(windows)
    for key in ('fps', 'first_encoded_at', 'last_encoded_at', 'egress_span_seconds', 'output_clock_drift_seconds',
                'output_wall_rate_fps', 'realtime_added_latency_seconds', 'source_arrival_latency_seconds',
                'presentation_lateness_seconds', 'presentation_delay_seconds', 'coverage', 'deadline_miss_count', 'deadline_miss_over_frame_period_count',
                'protected_frames', 'protected_fraction', 'live_frames'):
        result[key] = windows['steady'][key]
    result.update({'warmup_frames': window['warmup_frames'], 'warmup_seconds': window['warmup_seconds'],
                   'steady_frames': window['steady_frames'],
                   'metric_scope': 'Primary latency/protection/fps use steady frames only; full counts/PTS remain retained',
                   'steady_duration_seconds': window['steady_seconds']})
    for name, stats in result['engine']['lanes'].items():
        stats['actual_hz'] = stats['completed'] / source.duration
        stats['actual_hz_denominator'] = 'full source duration including warmup and injected ingest gaps'
        stats['service_quantiles_seconds'] = quantiles(stats['service_seconds'])
    result.update({**resources, 'candidate': candidate, 'options': options,
                   'processing_environment': host_environment(),
                   'pipeline_sha256': source_fingerprint, 'source_sha256': source_sha,
                   'output_sha256': file_sha256(output_path), 'encoder': sink.codec,
                   'encoder_command': sink.command, 'source_media': media, 'output_media': output_media,
                   'ffmpeg_build': ffmpeg_version[:3], 'ffmpeg_license_source': 'https://ffmpeg.org/legal.html',
                   'resolution': media['resolution'], 'pace': True, 'delay_seconds': delay,
                   'preflight_and_model_warmup_seconds': preflight_seconds, 'loading': loading,
                   'ingest': {'injected_drops': source.injected_drops, 'queue_drops': source.queue_drops,
                              'buffer_capacity_frames': source.buffer_capacity_frames},
                   'egress_clock': 'FFmpeg progress frame=packets_written; timestamps are observed mux-counter upper bounds',
                   'egress_source': 'https://github.com/FFmpeg/FFmpeg/blob/n8.0/fftools/ffmpeg.c#L557',
                   'scope': 'benchmark-only file output; no audio, OCR, network or demo-ready asset claim'})
    output_path.with_suffix('.masks.json').write_text(json.dumps(result.pop('records'), indent=2) + '\n')
    output_path.with_suffix('.egress.json').write_text(json.dumps(sink.progress, indent=2) + '\n')
    result['mask_pixels_sha256'] = file_sha256(output_path.with_suffix('.mask-pixels.zip'))
    return result


def main(argv=None):
    """One-command720/1080p30 performance receipt; no OCR in the timed path."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clip', default='sf-market', help='Licensed fixture ID from fixtures/manifest.json')
    parser.add_argument('--input', type=Path, help='Reuse an exact prepared derivative of the selected licensed fixture')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--candidate', default='ppocr-v5-mobile')
    parser.add_argument('--height',type=int,choices=(720,1080),default=720)
    parser.add_argument('--steady-seconds', type=float, default=30.)
    parser.add_argument('--warmup-seconds', type=float, default=10.)
    parser.add_argument('--D', '--delay-seconds', dest='delay_seconds', type=float, default=1.)
    parser.add_argument('--before', type=int, default=6)
    parser.add_argument('--after', type=int, default=18)
    parser.add_argument('--fast-max-age', type=int, default=6)
    parser.add_argument('--accurate-max-age', type=int, default=12)
    parser.add_argument('--fast-rate-hz', type=float, default=30.)
    parser.add_argument('--accurate-rate-hz', type=float, default=4.)
    parser.add_argument('--fast-width', type=int, default=640)
    parser.add_argument('--accurate-width', type=int, default=1280)
    parser.add_argument('--fast-candidate')
    parser.add_argument('--fast-provider', choices=('cpu', 'coreml', 'cuda'), default='cpu')
    parser.add_argument('--provider', choices=('cpu', 'coreml', 'cuda'), default='cpu')
    parser.add_argument('--det-thresh', dest='thresh', type=float, default=.3)
    parser.add_argument('--box-thresh', type=float, default=.5)
    parser.add_argument('--unclip-ratio', type=float, default=1.6)
    parser.add_argument('--static-model', action='store_true')
    parser.add_argument('--limit-side-len', type=int, default=960)
    parser.add_argument('--fast-limit-side-len',type=int,default=640)
    parser.add_argument('--encoder', choices=('h264_videotoolbox', 'h264_nvenc', 'libx264'), default='h264_videotoolbox')
    parser.add_argument('--motion-mode', choices=('orb', 'phase'), default='phase')
    parser.add_argument('--motion-width', type=int, default=320)
    parser.add_argument('--motion-min-response', type=float, default=.5)
    parser.add_argument('--padding', type=float, default=.3)
    parser.add_argument('--badge', action='store_true')
    parser.add_argument('--contended', action='store_true', help='Explicit diagnostic only; cannot establish accepted performance')
    args = parser.parse_args(argv)
    if not math.isfinite(args.steady_seconds) or args.steady_seconds < 30:
        parser.error('A performance trial requires at least30 steady seconds after warmup')
    manifest = json.loads((ROOT / 'fixtures/manifest.json').read_text())
    matches = [clip for clip in manifest['clips'] if clip['id'] == args.clip]
    if len(matches) != 1:
        parser.error('Choose one licensed fixture ID from the manifest')
    clip = matches[0]
    from fixtures.prepare import verify_cached
    source = ROOT / clip['path']
    verify_cached(source, clip)
    options = {key: value for key, value in vars(args).items()
               if key not in ('clip', 'input', 'output', 'candidate', 'steady_seconds','height') and value is not None}
    options['repeat_seconds'] = args.steady_seconds
    if args.input is not None:
        options['source_derivation'] = {'base_source_sha256': file_sha256(source),
                                        'prepared_input_sha256': file_sha256(args.input),
                                        'license': clip['license'], 'attribution': 'fixtures/ATTRIBUTION.md',
                                        'scope': 'Exact existing prepared input bytes, reused without encoding'}
        source = args.input
    if args.height==1080:
        derived=args.output.with_name(args.output.stem+'-1080-input.mp4')
        derived.parent.mkdir(parents=True,exist_ok=True)
        if derived.exists():
            raise FileExistsError(derived)
        prep_codec=(['-preset','p4'] if args.encoder=='h264_nvenc' else
                    ['-preset','ultrafast','-threads','2'] if args.encoder=='libx264' else ['-realtime','1'])
        command=['ffmpeg','-hide_banner','-loglevel','error','-y','-filter_threads','1',
                 '-i',str(source),'-an','-vf','scale=1920:1080,fps=30,setsar=1',
                 '-c:v',args.encoder,*prep_codec,'-bf','0','-b:v','15M','-pix_fmt','yuv420p',
                 '-map_metadata','-1',str(derived)]
        subprocess.run(command,check=True,timeout=120)
        prepared=probe_media(derived)
        if prepared['resolution']!=[1920,1080] or prepared['frames']!=150 or prepared['fps']!=30:
            raise ValueError('1080p performance source preparation changed the fixture clock')
        options['source_derivation']={'base_source_sha256':file_sha256(source),
                                      'license':clip['license'],'attribution':'fixtures/ATTRIBUTION.md',
                                      'command':command,'scope':'Upscaled runtime cost; native1080p recognition unproven'}
        source=derived
    result = run(source, args.output, args.candidate, options)
    from bench.clocked_bench import clock_guards
    guards = clock_guards(result,required_resolution=(args.height*16//9,args.height))
    print(json.dumps({'receipt': str(args.output.with_suffix('.performance.json')),
                      'performance_valid': result['performance_valid'],
                      'performance_rejection_reasons': result['performance_rejection_reasons'],
                      'full_frames': result['frames'], 'warmup_frames': result['warmup_frames'],
                      'steady_frames': result['steady']['frames'], 'startup': result['startup'],
                      'steady_fps': result['fps'], 'steady_latency_seconds': result['realtime_added_latency_seconds'],
                      'steady_protected_fraction': result['protected_fraction'], 'clock_guards': guards}), flush=True)
    return 0 if result['performance_valid'] and all(guards.values()) else 2


if __name__ == '__main__':
    raise SystemExit(main())

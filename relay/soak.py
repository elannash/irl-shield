"""Native MediaMTX functional/20-minute evidence harness; privacy grading is pending.

All credentialed networking uses PyAV in memory. Sender children receive their
arguments through multiprocessing's private spawn pipe, never process argv.
"""
import argparse
from fractions import Fraction
import hashlib
from importlib.metadata import version
import json
import math
import multiprocessing
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

from relay.fixture import FPS, SAMPLE_RATE, decorate, describe_source, read_stamp, tone
from relay.seal import seal, sha256_file, verify

ROOT = Path(__file__).resolve().parents[1]
PERF_LOCK = Path('/tmp/agents/irl-shield/perf.lock')
POLICY = 'Tiny8Hz640Small4Hz960D1phase320floor.05pad.3B6/A30'


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def row(output, value):
    output.write(json.dumps(value, separators=(',', ':')) + '\n')


def _lease_identity(fd):
    actual, expected = os.fstat(fd), PERF_LOCK.stat()
    if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
        raise RuntimeError('Inherited queue lease does not identify the canonical lock')
    identity = f'{os.major(actual.st_dev):02x}:{os.minor(actual.st_dev):02x}:{actual.st_ino}'
    locks = Path(f'/proc/self/fdinfo/{fd}').read_text().splitlines()
    if not any('FLOCK' in line and 'WRITE' in line and identity in line for line in locks):
        raise RuntimeError('Inherited canonical descriptor has no exclusive flock')
    return {'path': str(PERF_LOCK), 'device': actual.st_dev, 'inode': actual.st_ino,
            'exclusive': True, 'nested_flock': False}


def require_queue_lease():
    """Validate the inherited canonical lease without acquiring a nested flock."""
    try:
        fd = int(os.environ['IRL_SHIELD_PERF_QUEUE_LEASE_FD'])
        return _lease_identity(fd)
    except (KeyError, ValueError, OSError):
        raise RuntimeError('Timed soak requires an inherited canonical queue lease') from None


def require_functional_lease():
    # scripts/host-lock preserves its descriptor without adding an env variable.
    # Inspect only inherited descriptors, never acquire or release another lock.
    for path in Path('/proc/self/fd').iterdir():
        try:
            return _lease_identity(int(path.name))
        except (OSError, RuntimeError):
            continue
    raise RuntimeError('Functional mode requires canonical exclusive scripts/host-lock')


def _sender(url, source, directory, generation, origin, end_at, stopped):
    """Owned, killable native publisher. No exception strings cross this seam."""
    import av
    import cv2
    av.logging.set_level(-8)
    cv2.setNumThreads(2)
    sent = 0
    output = None
    status = 'failed'
    try:
        with av.open(source['source']['absolute_path']) as clip, \
                (Path(directory) / f'sender-{generation:02d}.jsonl').open('w', buffering=1) as events:
            clip.streams.video[0].codec_context.thread_count = 2
            output = av.open(url, 'w', format='flv', timeout=3,
                             options={'rw_timeout': '3000000', 'flvflags': 'no_duration_filesize'})
            video = output.add_stream('h264_nvenc', rate=FPS)
            video.width, video.height = source['source']['width'], source['source']['height']
            video.pix_fmt, video.bit_rate = 'yuv420p', 3_000_000
            video.codec_context.thread_count = 2
            video.codec_context.max_b_frames, video.codec_context.gop_size = 0, FPS
            video.time_base = video.codec_context.time_base = Fraction(1, FPS)
            video.options = {'preset': 'p4', 'tune': 'ull', 'zerolatency': '1'}
            audio = output.add_stream('aac', rate=SAMPLE_RATE)
            audio.layout, audio.bit_rate = 'mono', 128000
            audio.codec_context.thread_count = 2
            audio.time_base = audio.codec_context.time_base = Fraction(1, SAMPLE_RATE)
            output.start_encoding()
            frames = iter(clip.decode(video=0))
            first = round((time.monotonic() - origin) * FPS)
            while not stopped.is_set() and time.monotonic() < end_at:
                index = first + sent
                if index >= 65536:
                    raise ValueError('Optical source index exhausted')
                try:
                    decoded = next(frames)
                except StopIteration:
                    clip.seek(0, stream=clip.streams.video[0])
                    frames = iter(clip.decode(video=0))
                    decoded = next(frames)
                pixels = decoded.to_ndarray(format='bgr24')
                if stopped.wait(max(0, origin + index / FPS - time.monotonic())):
                    break
                epoch_ms = time.time_ns() // 1_000_000
                labels = decorate(pixels, index, epoch_ms)
                frame = av.VideoFrame.from_ndarray(pixels, format='bgr24')
                frame.pts, frame.time_base = sent, Fraction(1, FPS)
                pcm = tone(index)
                sound = av.AudioFrame.from_ndarray(pcm.reshape(1, -1), format='s16', layout='mono')
                sound.sample_rate, sound.pts, sound.time_base = SAMPLE_RATE, sent * 1600, Fraction(1, SAMPLE_RATE)
                for stream, value in ((video, frame), (audio, sound)):
                    for packet in stream.encode(value):
                        output.mux(packet)
                row(events, {'index': index, 'generation': generation, 'generation_pts': sent / FPS,
                             'pts': index / FPS, 'epoch_ms': epoch_ms, 'labels': labels,
                             'source_frame': sent % round(source['source']['duration'] * FPS),
                             'source_video_pts': decoded.pts, 'source_video_time_base': str(decoded.time_base),
                             'flash': index % FPS < 3, 'beep': index % FPS < 3,
                             'pixels_sha256': hashlib.sha256(pixels.tobytes()).hexdigest(),
                             'audio_pcm_sha256': hashlib.sha256(pcm.tobytes()).hexdigest(),
                             'late_ms': (time.monotonic() - origin - index / FPS) * 1000})
                sent += 1
            for stream in (video, audio):
                for packet in stream.encode():
                    output.mux(packet)
            status = 'stopped'
    except BaseException:
        # libav exceptions can include the URL. Even synthetic credentials stay
        # out of tracebacks, multiprocessing diagnostics and saved receipts.
        status = 'failed'
    finally:
        if output is not None:
            try:
                output.close()
            except Exception:
                status = 'failed'
        try:
            write_json(Path(directory) / f'sender-{generation:02d}-exit.json',
                       {'status': status, 'frames': sent})
        except Exception:
            status = 'failed'
    if status == 'failed':
        raise SystemExit(2)


class Capture:
    """Independent network subscriber: remux encoded packets, no engine access."""
    def __init__(self, url, directory):
        self.url, self.directory = url, Path(directory)
        self.directory.mkdir()
        self.stopped = threading.Event()
        self.stats = {'opened': False, 'packets': 0, 'startup_retries': 0, 'status': 'pending'}
        self.thread = threading.Thread(target=self._read, name='m2-capture', daemon=True)
        self.thread.start()

    def _read(self):
        import av
        av.logging.set_level(-8)
        incoming = None
        try:
            while not self.stopped.is_set():
                try:
                    incoming = av.open(self.url, timeout=(3., 2.), options={
                        'rw_timeout': '2000000', 'probesize': '32768', 'analyzeduration': '100000'})
                    break
                except Exception:
                    self.stats['startup_retries'] += 1
                    self.stopped.wait(.1)
            if incoming is None:
                self.stats['status'] = 'never-opened'
                return
            self.stats.update(opened=True, connected_monotonic=time.monotonic())
            with av.open(str(self.directory / 'network.mkv'), 'w', format='matroska') as output, \
                    (self.directory / 'packets.jsonl').open('w') as packets:
                streams = {stream.index: output.add_stream_from_template(stream)
                           for stream in incoming.streams if stream.type in ('video', 'audio')}
                for packet in incoming.demux():
                    if not packet.size or packet.stream.index not in streams:
                        continue
                    row(packets, {'stream': packet.stream.type, 'pts': packet.pts, 'dts': packet.dts,
                                  'time_base': str(packet.time_base), 'bytes': packet.size,
                                  'sha256': hashlib.sha256(bytes(packet)).hexdigest(),
                                  'received_monotonic': time.monotonic()})
                    clone = av.Packet(bytes(packet))
                    clone.pts, clone.dts = packet.pts, packet.dts
                    clone.duration, clone.time_base = packet.duration, packet.time_base
                    clone.stream = streams[packet.stream.index]
                    output.mux(clone)
                    self.stats['packets'] += 1
            self.stats['status'] = 'eof'
        except Exception:
            self.stats['status'] = 'read-ended' if self.stats['opened'] else 'failed'
        finally:
            if incoming is not None:
                try:
                    incoming.close()
                except Exception:
                    self.stats['close_failed'] = True
            self.stats['finished_monotonic'] = time.monotonic()

    def close(self):
        self.stopped.set()
        self.thread.join(timeout=7)
        if self.thread.is_alive():
            raise RuntimeError('Independent capture did not stop within socket timeout')
        write_json(self.directory / 'transport.json', self.stats)


def resources(pids):
    entries = []
    for pid in pids:
        try:
            values = {}
            for line in Path(f'/proc/{pid}/status').read_text().splitlines():
                name, _, value = line.partition(':')
                if name in ('VmRSS', 'VmHWM', 'Threads'):
                    values[name] = int(value.split()[0])
            values.update(pid=pid, fd_count=len(list(Path(f'/proc/{pid}/fd').iterdir())))
            entries.append(values)
        except FileNotFoundError:
            continue
    return {'monotonic': time.monotonic(), 'processes': entries}


class Scenario:
    """Fault controller; HOLD is independent of the transport reconnect source."""
    def __init__(self, source, address, phone, directory, seconds, mtx_pid):
        self.source, self.address, self.phone = source, address, phone
        self.directory, self.seconds, self.mtx_pid = directory, seconds, mtx_pid
        self.stopped = threading.Event()
        self.processes = []
        self.exits = []
        self.error = False
        self.thread = None
        self.context = multiprocessing.get_context('spawn')
        self.actual = {}
        start = 4 + seconds * .55
        self.plan = {'hold_start': start, 'sender_kill': start + 1,
                     'sender_reconnect': start + 4, 'hold_release': start + 7,
                     'accurate_stall_pts': [4 + seconds * .3, 4 + seconds * .3 + 5]}

    def ready(self, control):
        self.origin = time.monotonic()
        self.thread = threading.Thread(target=self._run, args=(control,), name='m2-faults', daemon=True)
        self.thread.start()

    def _start(self, generation):
        stopped = self.context.Event()
        process = self.context.Process(target=_sender, name=f'm2-sender-{generation}', args=(
            self.address.rtmp('camera', self.phone), self.source, str(self.directory), generation,
            self.origin, self.origin + self.seconds + 8, stopped))
        process.start()
        item = (process, stopped, generation)
        self.processes.append(item)
        return item

    def _stop(self, item, kill=False):
        process, stopped, generation = item
        if kill and process.is_alive():
            process.kill()
        else:
            stopped.set()
        process.join(timeout=5)
        if process.is_alive():
            process.kill()
            process.join(timeout=3)
        if process.is_alive():
            raise RuntimeError('Owned sender failed to exit')
        self.exits.append({'pid': process.pid, 'generation': generation, 'exitcode': process.exitcode,
                           'intentional_kill': kill, 'stopped': True})

    def _run(self, control):
        active = None
        try:
            with (self.directory / 'events.jsonl').open('w', buffering=1) as events, \
                    (self.directory / 'resources.jsonl').open('w', buffering=1) as samples:
                active = self._start(1)
                row(events, {'event': 'sender-start', 'at': time.monotonic() - self.origin, 'generation': 1})
                actions = iter(sorted((at, action) for action, at in self.plan.items() if action != 'accurate_stall_pts'))
                upcoming = next(actions, None)
                sampled = -1
                while not self.stopped.is_set():
                    now = time.monotonic() - self.origin
                    if math.floor(now) > sampled:
                        sampled = math.floor(now)
                        row(samples, resources([os.getpid(), self.mtx_pid,
                                                *[p.pid for p, _, _ in self.processes if p.is_alive()]]))
                    if upcoming and now >= upcoming[0]:
                        _, action = upcoming
                        if action == 'hold_start':
                            control.hold(True, source='local', reason='synthetic hold')
                        elif action == 'hold_release':
                            control.hold(False, source='local', reason='synthetic hold')
                        elif action == 'sender_kill':
                            self._stop(active, kill=True)
                            active = None
                        elif action == 'sender_reconnect':
                            active = self._start(2)
                        self.actual[action] = time.monotonic()
                        row(events, {'event': action, 'at': self.actual[action] - self.origin,
                                     'monotonic': self.actual[action]})
                        upcoming = next(actions, None)
                    self.stopped.wait(.02)
        except BaseException:
            self.error = True
        finally:
            if active is not None:
                try:
                    self._stop(active)
                except Exception:
                    self.error = True

    def close(self):
        self.stopped.set()
        if self.thread:
            self.thread.join(timeout=10)
            if self.thread.is_alive():
                raise RuntimeError('Scenario controller did not stop')
        write_json(self.directory / 'sender-processes.json', {'exits': self.exits, 'failed': self.error,
                                                             'actual_events': self.actual})


def json_lines(path):
    with Path(path).open() as source:
        for line in source:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # SIGKILL may interrupt the last sender row. Preserve the raw
                # artifact but never invent metadata for an incomplete write.
                if source.read():
                    raise ValueError('Malformed evidence before final line') from None
                return


def analyze_capture(directory, source_rows):
    """Decode actual received bytes; optical matches do not establish privacy."""
    import av
    import numpy as np
    directory = Path(directory)
    first = last = previous = None
    count = regressions = optical = spatial = 0
    max_video_gap = 0.
    flashes, beeps = [], []
    audio_samples, last_active = 0, -math.inf
    burst = None

    def finish_burst():
        if burst is None or burst['samples'] < 2048:
            return
        pcm = np.concatenate(burst['pieces'])[:2048].astype(np.float64)
        spectrum = np.abs(np.fft.rfft(pcm * np.hanning(len(pcm))))
        frequency = int(np.argmax(spectrum)) * SAMPLE_RATE / len(pcm)
        code = round((frequency - 1000) / 100)
        if 0 <= code < 16 and abs(frequency - (1000 + code * 100)) < 40:
            beeps.append({'pts': burst['pts'], 'pulse_mod16': code, 'measured_hz': frequency})
    with av.open(str(directory / 'network.mkv')) as clip, \
            (directory / 'decoded.jsonl').open('w') as manifest:
        for stream in clip.streams:
            stream.codec_context.thread_count = 2
        resampler = av.AudioResampler(format='s16', layout='mono', rate=SAMPLE_RATE)
        for frame in clip.decode():
            if frame.pts is None or frame.time_base is None:
                raise ValueError('Independent capture has missing decoded timestamp')
            pts = float(frame.pts * frame.time_base)
            if isinstance(frame, av.VideoFrame):
                pixels = frame.to_ndarray(format='bgr24')
                # Neutral PROTECT frames and black HOLD frames are excluded.
                is_spatial = float(pixels.std()) > 3 and int(pixels.max()) - int(pixels.min()) > 12
                spatial += int(is_spatial)
                index, epoch_ms = read_stamp(pixels)
                source = source_rows.get(index)
                valid = source is not None and abs(epoch_ms - source['epoch_ms']) <= 2
                optical += int(valid)
                flash = bool(valid and source['flash'] and pixels[48:96, 8:56].mean() > 200)
                if flash and (not flashes or index // FPS != flashes[-1]['pulse']):
                    flashes.append({'pulse': index // FPS, 'pts': pts, 'source_index': index,
                                    'partial_flash': index % FPS != 0})
                regressions += int(previous is not None and pts <= previous)
                if previous is not None:
                    max_video_gap = max(max_video_gap, pts - previous)
                first = pts if first is None else first
                last = previous = pts
                row(manifest, {'kind': 'video', 'pts': frame.pts, 'time_base': str(frame.time_base),
                               'seconds': pts, 'index': count, 'width': frame.width, 'height': frame.height,
                               'pixels_sha256': hashlib.sha256(pixels.tobytes()).hexdigest(),
                               'spatial_content': is_spatial, 'optical_match': valid,
                               'source_index': index if valid else None, 'flash': flash})
                count += 1
            else:
                for sound in resampler.resample(frame):
                    pcm = sound.to_ndarray().reshape(-1)
                    active = np.flatnonzero(np.abs(pcm.astype(np.int32)) > 4000)
                    sound_pts = float(sound.pts * sound.time_base)
                    onset = sound_pts + int(active[0]) / SAMPLE_RATE if active.size else None
                    if onset is not None:
                        if onset - last_active > .3:
                            finish_burst()
                            burst = {'pts': onset, 'pieces': [], 'samples': 0}
                        if burst is not None and burst['samples'] < 2048:
                            part = pcm[int(active[0]):int(active[-1]) + 1].copy()
                            burst['pieces'].append(part)
                            burst['samples'] += len(part)
                        last_active = sound_pts + int(active[-1]) / SAMPLE_RATE
                    row(manifest, {'kind': 'audio', 'pts': sound.pts, 'time_base': str(sound.time_base),
                                   'seconds': sound_pts, 'samples': sound.samples,
                                   'first_active_seconds': onset,
                                   'pcm_sha256': hashlib.sha256(pcm.tobytes()).hexdigest()})
                    audio_samples += sound.samples
    finish_burst()
    pairs = []
    used = set()
    for flash in flashes:
        # An optical onset hidden by protection cannot be measured as zero skew.
        if flash['partial_flash']:
            continue
        nearest = min((b for b in beeps if b['pts'] not in used and b['pulse_mod16'] == flash['pulse'] % 16),
                      key=lambda b: abs(b['pts'] - flash['pts']), default=None)
        if nearest is not None and abs(nearest['pts'] - flash['pts']) < 8:
            used.add(nearest['pts'])
            pairs.append({**flash, 'beep_pts': nearest['pts'], 'tone_hz': nearest['measured_hz'],
                          'offset_ms': (nearest['pts'] - flash['pts']) * 1000})
    offsets = [p['offset_ms'] for p in pairs]
    result = {'decoded_frames': count, 'audio_samples': audio_samples, 'video_first_pts': first,
              'video_last_pts': last, 'video_span_seconds': last - first if count else 0,
              'max_video_gap_seconds': max_video_gap, 'spatial_content_frames': spatial,
              'nonincreasing_video_pts': regressions, 'optical_matches': optical,
              'flash_beep_pairs': pairs, 'unpaired_flash_count': len(flashes) - len(pairs),
              'unpaired_beep_count': len(beeps) - len(pairs),
              'av_offset_ms_median': float(np.median(offsets)) if offsets else None,
              'av_offset_ms_p95_absolute': float(np.percentile(np.abs(offsets), 95)) if offsets else None,
              'av_measurement': 'decoded optical onsets paired to frequency-coded tone; unambiguous within +/-8s' if pairs else 'unmeasured',
              'privacy_grade': 'PENDING corrected independent OCR; Q not qualified'}
    write_json(directory / 'decoded-summary.json', result)
    return result


def provenance(args, engine, lease, binary):
    tracked = subprocess.check_output(['git', 'ls-files', '-co', '--exclude-standard'], cwd=ROOT, text=True).splitlines()
    paths = sorted(set(p for p in tracked if (
        p.endswith('.py') and p.split('/')[0] in ('relay', 'shield', 'bench')
        or p in ('scripts/m2-soak', 'requirements-relay.txt', 'requirements-linux-gpu.txt',
                 'models/manifest.json', 'fixtures/manifest.json', 'fixtures/ATTRIBUTION.md'))))
    return {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'branch': subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip(),
            'source_sha256': {path: sha256_file(ROOT / path) for path in paths},
            'argv': list(sys.orig_argv),
            'argv_scope': 'Exact interpreter argv; outer queue/slice launcher is in the queue receipt',
            'resolved_config': {name: str(value) if isinstance(value, Path) else value
                                for name, value in vars(args).items()},
            'credentials': 'Generated per run; memory and private spawn pipe only; never recorded',
            'queue_lease': lease, 'policy': POLICY, 'engine_options': engine.options,
            'lanes': {name: lane.stats['backend'] for name, lane in engine.lanes.items()},
            'dependencies': {name: version(name) for name in ('av', 'numpy', 'opencv-python-headless', 'onnxruntime-gpu')},
            'mediamtx': {'version': 'v1.21.3', 'binary_sha256': sha256_file(binary), 'license': 'MIT',
                         'source': 'https://github.com/bluenviron/mediamtx/releases/tag/v1.21.3'},
            'encoder': 'h264_nvenc', 'twitch': 'stub only; no connection; bandwidthtest=true mandatory',
            'declared_bounds': {'input_queue_capacity': 8, 'decoder_threads': 2, 'encoder_threads': 2,
                                'engine_buffer_frames': engine.max_buffer_frames,
                                'engine_max_poll_frames': engine.max_poll_frames,
                                'lane_sample_capacity': 4096, 'sender_processes_concurrent': 1,
                                'capture_queue': 'none; packets remuxed synchronously'}}


def summarize(directory, requested, runtime, scenario, captures):
    source_rows = {}
    for path in sorted(directory.glob('sender-*.jsonl')):
        for entry in json_lines(path):
            if entry['index'] in source_rows:
                raise ValueError('Duplicate synthetic source index')
            source_rows[entry['index']] = entry
    decoded = {}
    for name, capture in captures.items():
        if capture.stats['opened'] and (directory / name / 'network.mkv').exists():
            decoded[name] = analyze_capture(directory / name, source_rows)
    states, slates, live, total = {}, 0, 0, 0
    stall_frames = hold_frames = hold_violations = 0
    start, end = scenario.plan['accurate_stall_pts']
    with (directory / 'protection.jsonl').open('w') as protection:
        for entry in json_lines(directory / 'frames.jsonl'):
            total += 1
            states[entry['state']] = states.get(entry['state'], 0) + 1
            slates += int(entry['slate'])
            live += int(entry['state'] == 'LIVE' and not entry['slate'])
            if start + 1 <= entry['pts'] < end:
                stall_frames += int(entry['protected'])
            inside = (scenario.actual.get('hold_start', math.inf) + .25 <= entry['presented_at']
                      < scenario.actual.get('hold_release', -math.inf))
            if inside:
                hold_frames += 1
                hold_violations += int(not entry['slate'] or not entry['protected'])
            row(protection, {key: entry[key] for key in ('index', 'pts', 'state', 'protected', 'slate',
                                                         'coverage', 'mask_sha256', 'deadline', 'presented_at')})
    errors = []
    rtmp = decoded.get('rtmp', {})
    if rtmp.get('decoded_frames', 0) < 2 or rtmp.get('audio_samples', 0) == 0:
        errors.append('independent RTMP capture lacks decoded A/V')
    if rtmp.get('video_span_seconds', 0) + 1 / FPS < requested:
        errors.append('independent RTMP span shorter than requested observation')
    if rtmp.get('decoded_frames', 0) < math.ceil(requested * FPS):
        errors.append('independent RTMP has fewer frames than requested native observation')
    if rtmp.get('max_video_gap_seconds', math.inf) > 2 / FPS:
        errors.append('independent RTMP frame continuity gap exceeds two frame periods')
    if rtmp.get('nonincreasing_video_pts', 1):
        errors.append('nonincreasing decoded RTMP PTS')
    if not rtmp.get('flash_beep_pairs'):
        errors.append('no measurable decoded flash/beep pair')
    if runtime['session']['sessions'] < 2 or runtime['session']['disconnections'] < 1:
        errors.append('sender reconnect not observed at runtime')
    if not hold_frames or hold_violations:
        errors.append('HOLD protection missing or violated')
    if not stall_frames:
        errors.append('accurate-stall protection not observed')
    if not live or not rtmp.get('spatial_content_frames', 0):
        errors.append('no LIVE spatial video; all-neutral output cannot qualify')
    if runtime['input_queue_high_water'] > runtime['input_queue_capacity']:
        errors.append('input queue bound exceeded')
    if scenario.error or any(e['exitcode'] != 0 and not e['intentional_kill'] for e in scenario.exits):
        errors.append('sender/controller failure')
    for name in captures:
        if name not in decoded:
            errors.append(name + ' capture unavailable')
    if set(scenario.actual) != {'hold_start', 'sender_kill', 'sender_reconnect', 'hold_release'}:
        errors.append('fault schedule did not complete')
    result = {'status': 'functional-evidence-complete' if not errors else 'incomplete',
              'requested_seconds': requested, 'native_20min_executed': requested >= 1200 and not errors,
              'privacy_grade': 'PENDING corrected independent OCR; Q not qualified',
              'gate2_privacy_pass': False, 'source_scope': 'BENCHMARK-ONLY; not demo-ready',
              'errors': errors, 'output_frames': total, 'live_frames': live, 'slate_frames': slates,
              'states': states, 'accurate_stall_protected_frames': stall_frames,
              'hold_frames': hold_frames, 'hold_violations': hold_violations,
              'capture': decoded, 'runtime': runtime, 'fault_plan': scenario.plan,
              'resources': 'resources.jsonl; measured RSS KiB, threads and FDs for owned PIDs only'}
    write_json(directory / 'summary.json', result)
    return result


def close_workers(scenario, captures):
    errors = []
    for name, resource in [('scenario', scenario), *captures.items()]:
        if resource is not None:
            try:
                resource.close()
            except Exception:
                errors.append(name)
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=float, default=1200)
    parser.add_argument('--output', type=Path, required=True, help='New, unique directory; use attempt-{attempt} in queue')
    parser.add_argument('--model-cache', type=Path, required=True)
    parser.add_argument('--fixture-root', type=Path, default=ROOT,
                        help='Repository root containing the licensed fixtures directory')
    parser.add_argument('--fixture-id', default='sf-market')
    parser.add_argument('--host', choices=('127.0.0.1', '100.109.49.77'), default='127.0.0.1')
    parser.add_argument('--srt-capture', action='store_true', help='Also independently read SRT egress')
    parser.add_argument('--functional', action='store_true',
                        help='20–120 seconds only; parent must wrap canonical exclusive scripts/host-lock')
    args = parser.parse_args(argv)
    if not math.isfinite(args.seconds) or not 20 <= args.seconds <= 1800:
        parser.error('--seconds must be finite and between 20 and 1800')
    if args.functional and args.seconds > 120:
        parser.error('--functional is limited to 120 seconds')
    lease = require_functional_lease() if args.functional else require_queue_lease()
    if 'app-t3code-agents.slice' not in Path('/proc/self/cgroup').read_text():
        raise RuntimeError('Native harness must run within app-t3code-agents.slice')
    if os.getpriority(os.PRIO_PROCESS, 0) < 10:
        os.setpriority(os.PRIO_PROCESS, 0, 10)
    for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        os.environ[name] = '2'
    source = describe_source(args.fixture_root / 'fixtures/manifest.json', args.fixture_id, args.fixture_root)
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / 'source.json', source)
    # Import the parent's shared engine/transport only after help and safety guards.
    import av
    import cv2
    av.logging.set_level(-8)
    cv2.setNumThreads(2)
    from relay.mediamtx import MediaMTX, linux_bound_sockets, verified_binary
    from relay.runtime import make_engine, run
    from relay.security import Credentials, RelayAddress
    binary = verified_binary()
    address = RelayAddress(args.host, rtmp_port=19550, srt_port=19050)
    phone, internal = Credentials.generate(), Credentials.generate()
    stopped = threading.Event()
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    for sig in previous:
        signal.signal(sig, lambda *_: stopped.set())
    captures, scenario, engine, runtime = {}, None, None, None
    error, runtime_owns_engine = False, False
    phase = 'mediamtx-start'
    mtx = None
    cleanup_errors = []
    workers_closed = False
    try:
        with MediaMTX(address, phone, internal, binary=binary) as mtx:
            phase = 'listener-verification'
            sockets = linux_bound_sockets(mtx.process.pid)
            if any(s['host'] not in (args.host, '127.0.0.1') or s['port'] not in (19550, 19050) for s in sockets):
                raise RuntimeError('Unexpected MediaMTX listener')
            write_json(args.output / 'listeners.json', sockets)
            scenario = Scenario(source, address, phone, args.output, args.seconds, mtx.process.pid)
            phase = 'engine-start'
            engine = make_engine(args.model_cache, provider='cuda', faults=(scenario.plan['accurate_stall_pts'],))
            write_json(args.output / 'provenance.json', provenance(args, engine, lease, binary))
            captures['rtmp'] = Capture(address.rtmp('shielded'), args.output / 'rtmp')
            if args.srt_capture:
                captures['srt'] = Capture(address.srt('read', 'shielded'), args.output / 'srt')
            phase = 'runtime'
            runtime_owns_engine = True
            try:
                runtime = run(engine, address, phone, internal, args.output, stopped,
                              seconds=args.seconds + 8, width=source['source']['width'],
                              height=source['source']['height'], encoder='h264_nvenc', control_ready=scenario.ready)
            finally:
                cleanup_errors.extend(close_workers(scenario, captures))
                workers_closed = True
    except Exception:
        error = True
        write_json(args.output / 'failure.json', {'status': 'incomplete', 'phase': phase,
                                                 'diagnostics': 'Suppressed to protect runtime credentials',
                                                 'privacy_grade': 'PENDING; no gate pass'})
    finally:
        # Try every owned resource even when another close fails. Never seal
        # evidence while a worker can still append to it.
        if not workers_closed:
            cleanup_errors.extend(close_workers(scenario, captures))
        if engine is not None and not runtime_owns_engine:
            try:
                engine.close()
            except Exception:
                cleanup_errors.append('engine')
        if mtx is not None and mtx.process is not None:
            write_json(args.output / 'mediamtx-exit.json', {'pid': mtx.process.pid, 'exitcode': mtx.process.returncode,
                                                           'stopped': mtx.process.poll() is not None})
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    if cleanup_errors:
        write_json(args.output / 'cleanup-failure.json', {'resources': cleanup_errors, 'sealed': False})
        raise RuntimeError('Owned cleanup failed; evidence left unsealed')
    if not error:
        try:
            summary = summarize(args.output, args.seconds, runtime, scenario, captures)
            error = bool(summary['errors'])
        except Exception:
            error = True
            write_json(args.output / 'failure.json', {'status': 'incomplete', 'phase': 'decoded-analysis',
                                                     'diagnostics': 'Suppressed; inspect sealed transport/runtime receipts',
                                                     'privacy_grade': 'PENDING; no gate pass'})
    digest = seal(args.output)
    verify(args.output, digest)
    print(json.dumps({'output': str(args.output), 'seal_sha256': digest,
                      'status': 'incomplete' if error else 'functional-evidence-complete',
                      'privacy_grade': 'PENDING corrected independent OCR; Q not qualified'}), flush=True)
    return 2 if error else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit('Soak failed; credentialed diagnostics suppressed') from None

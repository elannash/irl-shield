"""Ideal source-scheduled content quality, never a realtime or gate measurement.

Reuses existing NumPy (BSD-3-Clause), OpenCV (Apache-2.0), shield policy and
fixture/model licenses. All generated footage is benchmark-only, with no audio.
The existing FFmpeg build supplies encoding; its LGPL/GPL terms are described
at https://ffmpeg.org/legal.html . No codec binary or new asset is bundled.
"""
from dataclasses import asdict
import argparse
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import platform
import time
import zipfile

import cv2
import numpy as np

from shield.engine import MaskingEngine
from shield.motion import MotionHistory
from shield.types import Detection, Frame
from bench.metrics import fidelity, quantiles, validate_area_ceiling, masked_area_pass
from bench.scoring import score_records
from bench.independence import policy_metadata, annotate_card, resolve_fast_candidate


ROOT = Path(__file__).resolve().parents[1]
SCOPE = ('IDEAL/OFFLINE intended-sampling content quality: detector completions occur at source PTS, '
         'irrespective of host wall time. Natural truth is OCR-observed Latin text/digits at confidence>=.9 '
         'on at least2 frames; output threshold>=.5; every annotated visible synthetic label remains truth. '
         'Judges: Tesseract eng, Apple Vision accurate en-US, PP-OCRv5 English-mobile. '
         'Non-Latin coverage is unproven. No realtime throughput, latency, CPU budget or gate eligibility is established. '
         'Benchmark-only, no audio.')


class _Noop:
    def detect_quads(self, pixels):
        return []

    def close(self):
        pass


def _validate_models(candidate,options):
    if candidate=='vision-scheduled' or options.get('fast_candidate')=='vision-scheduled':
        raise ValueError('legacy vision-scheduled cannot preserve offline source-index receipts')


class _ScheduledLane:
    def __init__(self, name, backend, fps, rate, width=0):
        if not math.isfinite(rate) or not 0 < rate <= fps:
            raise ValueError('Lane rate must be finite, positive and no greater than source fps')
        self.name, self.backend, self.fps, self.rate = name, backend, fps, rate
        if not isinstance(width, int) or width < 0:
            raise ValueError('Lane width must be a nonnegative integer')
        self.width = width
        self.bucket = -1
        self.results = []
        self.receipts = []
        self.offered = 0

    def offer(self, frame):
        self.offered += 1
        bucket = math.floor(frame.index * self.rate / self.fps + 1e-9)
        if bucket <= self.bucket:
            return
        self.bucket = bucket
        began, cpu = time.perf_counter(), time.thread_time()
        height, width = frame.pixels.shape[:2]
        scale = self.width / width if self.width else 1.
        pixels = cv2.resize(frame.pixels, (self.width, round(height * scale))) if scale != 1 else frame.pixels
        if hasattr(self.backend, 'detect_quads'):
            quads = self.backend.detect_quads(pixels)
        else:
            quads = [[[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
                     for x0, y0, x1, y1 in self.backend.detect(pixels)]
        points = np.asarray(quads, dtype=float).reshape(-1, 4, 2) / scale
        if not np.isfinite(points).all():
            raise ValueError('Detector returned nonfinite geometry')
        quads = points.tolist()
        self.results.append(Detection(self.name, frame.index, quads, frame.pts))
        self.receipts.append({'lane': self.name, 'source_index': frame.index, 'source_pts': frame.pts,
                              'completed_at': frame.pts, 'quads': quads,
                              'detector_input_shape': list(pixels.shape),
                              'diagnostic_wall_seconds': time.perf_counter() - began,
                              'diagnostic_caller_thread_cpu_seconds': time.thread_time() - cpu})

    def drain(self):
        results, self.results = self.results, []
        return results

    def close(self):
        pass

    @property
    def stats(self):
        return {'offered': self.offered, 'completed': len(self.receipts), 'failed': 0,
                'rate_hz': self.rate, 'backend': getattr(self.backend, 'metadata', {})}


def render_offline(frames, fps, backends, options, emit, *, motion=None, renderer=None):
    """Consume every source pixel array, presenting on virtual PTS rather than wall time.

    Backends are borrowed and remain owned by the caller. All detector calls
    block, complete at their source PTS in this ideal simulation, and retain
    diagnostic wall/caller-thread CPU durations without a realtime claim.
    """
    options = {'delay_seconds': 1., 'before': 6, 'after': 30, 'fast_rate_hz': 8.,
               'accurate_rate_hz': 4., 'motion_width': 320, 'motion_mode': 'phase', **options}
    delay = float(options['delay_seconds'])
    if not math.isfinite(fps) or fps <= 0 or not math.isfinite(delay) or not 0 <= delay <= 1:
        raise ValueError('Offline quality requires positive fps and a delay between zero and one second')
    control = options.get('control')
    if control not in (None, 'unmasked', 'slate'):
        raise ValueError('Unknown offline control')
    if control:
        backends = {name: _Noop() for name in ('fast', 'accurate')}
        options.update({'fast_rate_hz': fps, 'accurate_rate_hz': fps, 'fast_width': 0, 'accurate_width': 0})
    if set(backends) != {'fast', 'accurate'}:
        raise ValueError('Both fast and accurate backends are required')
    lanes = {name: _ScheduledLane(name, backends[name], fps, float(options[name + '_rate_hz']),
                                 int(options.get(name + '_width', 0)))
             for name in ('fast', 'accurate')}
    motion = motion or MotionHistory(max_frames=max(120, math.ceil(fps * delay) + options['before'] + 4),
                                     analysis_width=options['motion_width'], mode=options['motion_mode'],
                                     phase_min_response=options.get('motion_min_response',.5))
    engine = MaskingEngine(lanes, {**options, 'fps': fps}, motion=motion, renderer=renderer)
    if control == 'slate':
        engine.hold(True, source='offline-control', reason='slate-control', now=0.)
    records, motion_rows = [], []
    seen = 0

    def present(until, inclusive):
        while len(records) < seen:
            deadline = len(records) / fps + delay
            if deadline > until or (not inclusive and deadline == until):
                break
            batch = engine.poll(now=deadline)
            if not batch:
                raise RuntimeError('Virtual presentation failed at its exact source deadline')
            for frame in batch:
                if frame.index != len(records):
                    raise RuntimeError('Offline presentation skipped or reordered a source frame')
                emit(frame)
                records.append({'frame': frame.index, 'pts': frame.pts, 'quads': frame.quads,
                                'state': frame.state, 'protected': frame.protected, 'slate': frame.slate,
                                'coverage': asdict(frame.coverage), 'deadline': frame.deadline,
                                'presented_at': frame.presented_at,
                                'mask_shape': list(frame.mask.shape),
                                'mask_fraction': float((frame.mask > 0).mean()),
                                'mask_sha256': hashlib.sha256(frame.mask.tobytes()).hexdigest()})

    try:
        for index, pixels in enumerate(frames):
            pts = index / fps
            present(pts, False)
            engine.submit(Frame(index, pts, pixels), now=pts)
            seen += 1
            motion_rows.append({'frame': index, 'pts': pts, **motion.diagnostics(index)})
            present(pts, True)
        if not seen:
            raise ValueError('Offline quality requires at least one decoded frame')
        engine.end(seen - 1)
        while not engine.drained:
            present(len(records) / fps + delay, True)
        stats = engine.stats
        if len(records) != seen or stats['late_ingest'] or stats['buffer_evictions']:
            raise RuntimeError('Offline quality failed complete source-frame accounting')
        return {'mode': 'offline_quality', 'real_time_verified': False,
                'gate_1': {'eligible': False, 'pass': False}, 'clock_domain': 'virtual-source-pts', 'control': control,
                'frames': seen, 'records': records, 'motion': motion_rows,
                'detections': {name: lane.receipts for name, lane in lanes.items()}, 'engine': stats}
    finally:
        engine.close()


def _media(path):
    data = json.loads(subprocess.check_output(
        ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_frames', '-show_streams',
         '-show_entries', 'stream=width,height,avg_frame_rate:frame=best_effort_timestamp_time',
         '-of', 'json', str(path)], text=True, timeout=120))
    stream = data['streams'][0]
    fps = float(Fraction(stream['avg_frame_rate']))
    pts = [float(frame['best_effort_timestamp_time']) for frame in data['frames']]
    if not pts or not math.isfinite(fps) or fps <= 0 or any(
            not math.isfinite(value) or not math.isclose(value, index / fps, abs_tol=1e-5)
            for index, value in enumerate(pts)):
        raise ValueError('Offline quality requires a nonempty zero-origin CFR video')
    return {'fps': fps, 'frames': len(pts), 'resolution': [stream['width'], stream['height']]}


def _make_backends(candidate, options, resolution):
    _validate_models(candidate,options)
    fast = resolve_fast_candidate(candidate, options)
    if fast is None:
        return {name: _Noop() for name in ('fast', 'accurate')}
    from bench.pipeline import detector_for
    width, height = resolution
    backends = {}
    try:
        for lane, model in (('fast', fast), ('accurate', candidate)):
            lane_width = options.get(lane + '_width', 640 if lane == 'fast' else 1280) or width
            backend = detector_for(model, {**options, 'input_size': [height, width], 'detect_width': lane_width,
                                           'limit_side_len': options.get('fast_limit_side_len', 640) if lane == 'fast' else options.get('limit_side_len', 960),
                                           'provider': options.get('fast_provider', 'cpu') if lane == 'fast' else options.get('provider', 'cpu'),
                                           'threads': 2})
            if backend is None:
                raise ValueError('Offline quality requires actual detector backends')
            backends[lane] = backend
        return backends
    except Exception:
        for backend in backends.values():
            backend.close()
        raise


def _score_saved(source, output, judge, truth, records, *, detector_families):
    before, after = cv2.VideoCapture(str(source)), cv2.VideoCapture(str(output))
    inputs, outputs, guards = [], [], []
    try:
        with zipfile.ZipFile(output.with_suffix('.mask-pixels.zip')) as archive:
            if len(archive.namelist()) != len(records):
                raise RuntimeError('Saved raster mask count differs from presented frames')
            for index, row in enumerate(records):
                ok, original = before.read()
                good, masked = after.read()
                if not ok or not good or row['frame'] != index or original.shape != masked.shape:
                    raise RuntimeError(f'Offline quality frame accounting failed at {index}')
                shape = row['mask_shape']
                if list(original.shape[:2]) != shape:
                    raise RuntimeError('Saved raster mask dimensions differ')
                packed = np.frombuffer(archive.read(f'{index:08d}.bin'), np.uint8)
                if len(packed) != (shape[0] * shape[1] + 7) // 8:
                    raise RuntimeError('Saved raster mask byte count differs')
                mask = np.unpackbits(packed, bitorder='little', count=shape[0] * shape[1]).reshape(shape) * 255
                if hashlib.sha256(mask.tobytes()).hexdigest() != row['mask_sha256']:
                    raise RuntimeError('Saved raster mask SHA-256 differs')
                inputs.append(judge.read(original))
                outputs.append([reading for reading in judge.read(masked) if reading['confidence'] >= .5])
                live = row['state'] == 'LIVE' and not row['protected']
                guards.append(fidelity(original, masked, mask) if live else None)
                if index % 30 == 0:
                    print(f'  offline judge frame {index}/{len(records)}', flush=True)
            if before.read()[0] or after.read()[0]:
                raise RuntimeError('Offline quality found extra decoded frames')
    finally:
        before.release()
        after.release()
    if len(truth) != len(records):
        raise ValueError('Synthetic truth must retain every source frame and label')
    quality, details = score_records(inputs, outputs, truth, [g for g in guards if g is not None], detector_families=detector_families)
    quality['judging']=details['judging']=getattr(judge,'metadata',None)
    protected = sum(row['protected'] or row['state'] != 'LIVE' for row in records)
    quality.update({'live_frames': len(records) - protected, 'protected_frames': protected,
                    'protected_fraction': protected / len(records), 'protected_guard': protected / len(records) < .02,
                    'slate_frames': sum(r['slate'] for r in records),
                    'masked_area_fraction': quantiles([r['mask_fraction'] for r in records]),
                    'live_masked_area_fraction': quantiles([r['mask_fraction'] for r in records
                                                          if r['state'] == 'LIVE' and not r['protected']])})
    details.update({'frame_guards': guards, 'presentation': records})
    output.with_suffix('.evidence.json').write_text(json.dumps(details) + '\n')
    return quality


def run_file(input_path, output_path, candidate, options=None, *, judge=None, backends=None,
             synthetic_truth=None):
    """Render and score one file, borrowing injected judge/backends when supplied.

    A sibling .truth.json supplies annotations when no explicit truth is passed.
    Actual raster masks, raw source-index detections and motion verdicts are saved.
    Encoding blocks freely; its speed does not alter the virtual source clock.
    """
    _validate_models(candidate,options or {})
    metadata = policy_metadata(candidate, options or {})
    source, output = Path(input_path), Path(output_path)
    if output.exists():
        raise FileExistsError(output)
    options = {'delay_seconds': 1., 'before': 6, 'after': 30, 'fast_rate_hz': 8.,
               'accurate_rate_hz': 4., 'motion_mode': 'phase', 'motion_width': 320, **(options or {})}
    media = _media(source)
    options['control'] = candidate if candidate in ('unmasked', 'slate') else None
    if options['control']:
        options.update({'fast_rate_hz': media['fps'], 'accurate_rate_hz': media['fps'],
                        'fast_width': 0, 'accurate_width': 0})
        if backends is None:
            backends = {name: _Noop() for name in ('fast', 'accurate')}
    owned_backends, owned_judge = backends is None, judge is None
    output.parent.mkdir(parents=True, exist_ok=True)
    capture = None
    process = None
    completed = False
    try:
        if owned_backends:
            backends = _make_backends(candidate, options, media['resolution'])
            options.setdefault('fast_width', 640)
            options.setdefault('accurate_width', 1280)
        if owned_judge:
            from bench.judges import Judges
            judge = Judges(candidate, output.parent / 'judge-cache')
        if synthetic_truth is None:
            truth_path = source.with_suffix('.truth.json')
            synthetic_truth = json.loads(truth_path.read_text()) if truth_path.exists() else [[] for _ in range(media['frames'])]
        if len(synthetic_truth) != media['frames']:
            raise ValueError('Synthetic annotations must account for every source frame')
        width, height = media['resolution']
        codec = options.get('encoder', 'h264_videotoolbox')
        encoders = {'h264_videotoolbox': ['-realtime', '1'],
                    'h264_nvenc': ['-preset', 'p4', '-tune', 'ull', '-rc-lookahead', '0'],
                    'libx264': ['-preset', 'ultrafast', '-tune', 'zerolatency', '-threads', '2']}
        if codec not in encoders:
            raise ValueError('Unsupported offline encoder')
        command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-filter_threads', '1',
                   '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{width}x{height}', '-r', str(media['fps']),
                   '-i', 'pipe:0', '-an', '-c:v', codec, *encoders[codec], '-bf', '0', '-b:v', '10M',
                   '-pix_fmt', 'yuv420p', str(output)]
        capture = cv2.VideoCapture(str(source))
        if not capture.isOpened():
            raise RuntimeError(f'Cannot decode {source}')

        def frames():
            for _ in range(media['frames']):
                ok, pixels = capture.read()
                if not ok:
                    raise RuntimeError('Offline source decode was truncated')
                yield pixels
            if capture.read()[0]:
                raise RuntimeError('Offline source has unexpected extra frames')

        with output.with_suffix('.ffmpeg.log').open('w') as log, zipfile.ZipFile(
                output.with_suffix('.mask-pixels.zip'), 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as masks:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=log)

            def emit(frame):
                if frame.pixels.shape != (height, width, 3) or frame.mask.shape != (height, width):
                    raise RuntimeError('Offline raster output dimensions changed')
                process.stdin.write(frame.pixels.tobytes())
                masks.writestr(f'{frame.index:08d}.bin', np.packbits(frame.mask > 0, bitorder='little').tobytes())

            rendered = render_offline(frames(), media['fps'], backends, options, emit)
            process.stdin.close()
            code = process.wait(timeout=60)
            if code:
                raise RuntimeError(f'Offline encoder failed exit {code}')
        completed = True
        decoded = _media(output)
        if decoded != media or rendered['frames'] != media['frames']:
            raise RuntimeError('Offline encoded output changed frame count, dimensions or source clock')
        for key, suffix in (('records', '.masks.json'), ('detections', '.detections.json'), ('motion', '.motion.json')):
            output.with_suffix(suffix).write_text(json.dumps(rendered[key]) + '\n')
        diagnostics = {key: value for key, value in rendered.items() if key not in {'records', 'detections', 'motion'}}
        output.with_suffix('.offline.json').write_text(json.dumps(diagnostics, indent=2) + '\n')
        quality = _score_saved(source, output, judge, synthetic_truth, rendered['records'],
                               detector_families=metadata['detector_families'])
        result = {'mode': 'offline_quality', 'real_time_verified': False, 'gate_1': {'eligible': False, 'pass': False},
                  'benchmark_only': True, 'demo_ready': False, 'candidate': candidate, 'options': options,
                  'source': str(source), 'output': str(output), 'frames': media['frames'], 'source_fps': media['fps'],
                  'judges': list(judge.names), 'encoder_command': command, **quality}
        output.with_suffix('.quality.json').write_text(json.dumps(result, indent=2) + '\n')
        return result
    finally:
        if capture is not None:
            capture.release()
        if process is not None and not completed:
            if process.stdin is not None and not process.stdin.closed:
                try:
                    process.stdin.close()
                except BrokenPipeError:
                    pass
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        errors = []
        if owned_judge and judge is not None:
            try:
                judge.close()
            except Exception as error:
                errors.append(error)
        if owned_backends and backends is not None:
            for backend in backends.values():
                try:
                    backend.close()
                except Exception as error:
                    errors.append(error)
        if errors:
            raise ExceptionGroup('Offline adapter cleanup failed', errors)


def build_scorecard(results, candidate, options, *, run_id='offline-quality', split='tune', baseline=None):
    """Aggregate counts over intervals and area over actual raster-frame records."""
    if not results:
        raise ValueError('An offline quality card needs nonempty clip evidence')
    records, clip_protected = [], []
    for result in results:
        rows = json.loads(Path(result['output']).with_suffix('.masks.json').read_text())
        if not rows or len(rows) != result['frames']:
            raise ValueError('Clip evidence does not account for its source frames')
        fraction = sum(row['protected'] or row['state'] != 'LIVE' for row in rows) / len(rows)
        clip_protected.append({'output': result['output'], 'protected_fraction': fraction, 'pass': fraction < .02})
        records.extend(rows)
    live = [row for row in records if row['state'] == 'LIVE' and not row['protected']]
    protected = (len(records) - len(live)) / len(records)
    card = {'schema_version': 1, 'mode': 'offline_quality', 'real_time_verified': False,
            'benchmark_only': True, 'demo_ready': False, 'run_id': run_id, 'split': split,
            'candidate': candidate, 'scope': SCOPE, 'options': options, 'clips': results,
            'gate_1': {'eligible': False, 'pass': False}, 'frames': len(records),
            'protected_fraction': protected, 'protected_frames': len(records) - len(live),
            'per_clip_protected': clip_protected,
            'live_frames': len(live), 'slate_frames': sum(row['slate'] for row in records),
            'masked_area_fraction': quantiles([row['mask_fraction'] for row in records]),
            'live_masked_area_fraction': quantiles([row['mask_fraction'] for row in live]),
            'real_video_pass': bool(live) and all(result['real_video_pass'] for result in results),
            'performance_ignored_for_quality': True,
            'diagnostic_timing_scope': 'Per-call wall and caller-thread CPU observations only; native worker CPU is not summed.',
            'licenses': ['fixtures/ATTRIBUTION.md', 'models/manifest.json', 'models/licenses/dependencies.json',
                         'https://ffmpeg.org/legal.html']}
    for kind in ('natural', 'synthetic'):
        hidden = sum(result[kind]['hidden'] for result in results)
        total = sum(result[kind]['total'] for result in results)
        card[kind] = {'hidden': hidden, 'total': total, 'hidden_fraction': hidden / total if total else None}
    independence=annotate_card(card)
    controls = [result['synthetic_input_control'] for result in results if result.get('synthetic_variant')]
    control = {'total': sum(row['total'] for row in controls), 'unreadable': sum(row['unreadable'] for row in controls)}
    card['synthetic_input_control'] = control
    ceiling = validate_area_ceiling(options.get('area_ceiling'), options.get('area_ceiling_basis'))
    card['area_ceiling'] = ceiling
    card['area_ceiling_basis'] = options.get('area_ceiling_basis') if ceiling is not None else None
    card['quality_checks'] = {
        'independent_judges': independence['sufficient_independent_engines'], 'judge_discrimination': control['total'] > 0 and control['unreadable'] == 0,
        'natural': card['natural']['hidden_fraction'] is not None and card['natural']['hidden_fraction'] >= .9,
        'synthetic': card['synthetic']['total'] > 0 and card['synthetic']['hidden_fraction'] == 1.,
        'protected': protected < .02 and all(row['pass'] for row in clip_protected),
        'protected_aggregate': protected < .02,
        'protected_each_clip': all(row['pass'] for row in clip_protected),
        'real_video': card['real_video_pass'],
        'masked_area': masked_area_pass(card)}
    card['comparison_valid'] = (card['quality_checks']['independent_judges'] and card['quality_checks']['judge_discrimination']
                                and card['quality_checks']['protected'] and card['real_video_pass']
                                and card['quality_checks']['masked_area'] is True)
    card['comparison_notes'] = ('Protected frames must remain below2% both per clip and in aggregate; a protected/slate-heavy result cannot win. '
                                'Area is reported over ALL raster masks; no tune-derived ceiling is invented.')
    baseline = baseline or {}
    card['baseline_deltas_pp'] = {}
    for kind in ('natural', 'synthetic'):
        current = card[kind]['hidden_fraction']
        reference = baseline.get(kind, {}).get('hidden_fraction')
        card['baseline_deltas_pp'][kind] = 100 * (current - reference) if current is not None and reference is not None else None
    card['baseline_comparison'] = 'Descriptive interval-fraction deltas only; the baseline may use another corpus/mode.'
    return card


def _fingerprint():
    paths = set((ROOT / 'shield').glob('*.py'))
    paths.update(ROOT / name for name in (
        'bench/offline_quality.py', 'bench/independence.py', 'bench/scoring.py', 'bench/metrics.py', 'bench/pipeline.py',
        'bench/onnx_detectors.py', 'bench/static_model.py', 'bench/judges.py', 'bench/vision.py',
        'bench/run.py', 'bench/synthetic.py', 'fixtures/prepare.py', 'fixtures/manifest.json',
        'models/manifest.json', 'requirements.txt', 'requirements-models.txt', 'Sources/VisionBridge/main.swift'))
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path.relative_to(ROOT)).encode() + b'\0' + path.read_bytes())
    return digest.hexdigest()


def main(argv=None, judge=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', default='ppocr-v5-mobile')
    parser.add_argument('--split', choices=('tune', 'heldout'), default='tune')
    parser.add_argument('--clip')
    parser.add_argument('--seconds', type=float, default=5.)
    parser.add_argument('--run-id', default=time.strftime('offline-%Y%m%d-%H%M%S'))
    parser.add_argument('--D', '--delay-seconds', dest='delay_seconds', type=float, default=1.)
    parser.add_argument('--B', '--before', dest='before', type=int, default=6)
    parser.add_argument('--A', '--after', dest='after', type=int, default=30)
    parser.add_argument('--padding', type=float, default=.3)
    parser.add_argument('--fast-candidate')
    parser.add_argument('--fast-rate-hz', type=float, default=8.)
    parser.add_argument('--accurate-rate-hz', type=float, default=4.)
    parser.add_argument('--fast-width', type=int, default=640)
    parser.add_argument('--accurate-width', type=int, default=1280)
    parser.add_argument('--fast-max-age', type=int, default=6)
    parser.add_argument('--accurate-max-age', type=int, default=12)
    parser.add_argument('--fast-provider', choices=('cpu', 'coreml', 'cuda'), default='cpu')
    parser.add_argument('--provider', choices=('cpu', 'coreml', 'cuda'), default='cpu')
    parser.add_argument('--limit-side-len', type=int, default=960)
    parser.add_argument('--fast-limit-side-len', type=int, default=640)
    parser.add_argument('--det-thresh', dest='thresh', type=float, default=.3)
    parser.add_argument('--box-thresh', type=float, default=.5)
    parser.add_argument('--unclip-ratio', type=float, default=1.6)
    parser.add_argument('--static-model', action='store_true')
    parser.add_argument('--motion-mode', choices=('phase', 'orb'), default='phase')
    parser.add_argument('--motion-width', type=int, default=320)
    parser.add_argument('--motion-min-response', type=float, default=.5)
    parser.add_argument('--encoder', choices=('h264_videotoolbox', 'h264_nvenc', 'libx264'), default='h264_videotoolbox')
    parser.add_argument('--area-ceiling', type=float)
    parser.add_argument('--area-ceiling-basis')
    args = parser.parse_args(argv)
    if (not math.isfinite(args.seconds) or args.seconds < 2 / 30 or not 0 <= args.delay_seconds <= 1
            or args.before < 0 or args.after < 0 or Path(args.run_id).name != args.run_id
            or args.run_id in ('.', '..')):
        parser.error('Invalid duration, source window, delay or run ID')
    try:
        validate_area_ceiling(args.area_ceiling, args.area_ceiling_basis,
                              required=args.area_ceiling is not None)
    except ValueError as error:
        parser.error(str(error))
    excluded = {'candidate', 'split', 'clip', 'seconds', 'run_id'}
    options = {key: value for key, value in vars(args).items() if key not in excluded and value is not None}
    _validate_models(args.candidate,options)
    manifest_path = ROOT / 'fixtures/manifest.json'
    clips = [clip for clip in json.loads(manifest_path.read_text())['clips'] if clip['split'] == args.split
             and (args.clip is None or clip['id'] == args.clip)]
    if not clips:
        raise ValueError('Empty licensed fixture selection')
    directory = ROOT / 'out' / args.run_id
    directory.mkdir(parents=True, exist_ok=False)
    snapshot = _fingerprint()
    owned_judge = judge is None
    backends, resolution, results = None, None, []
    try:
        if owned_judge:
            from bench.judges import Judges
            judge = Judges(args.candidate, ROOT / 'out/judge-cache')
        from bench.run import variant
        from fixtures.prepare import verify_cached
        for clip in clips:
            verify_cached(ROOT / clip['path'], clip)
            for synthetic in (False, True):
                label = clip['id'] + ('-synthetic' if synthetic else '-natural')
                print(f'{label}: {args.candidate} IDEAL/OFFLINE, D={args.delay_seconds}', flush=True)
                source = directory / f'{label}-input.mp4'
                truth = variant(clip, source, synthetic, args.seconds)
                current = _media(source)['resolution']
                if args.candidate not in ('unmasked', 'slate') and current != resolution:
                    if backends is not None:
                        for backend in backends.values():
                            backend.close()
                    backends = _make_backends(args.candidate, options, current)
                    resolution = current
                result = run_file(source, directory / f'{label}-masked.mp4', args.candidate, options,
                                  judge=judge, backends=backends, synthetic_truth=truth)
                results.append({'clip': clip['id'], 'synthetic_variant': synthetic, **result})
                (directory / 'progress.json').write_text(json.dumps(results, indent=2) + '\n')
    finally:
        errors = []
        if backends is not None:
            for backend in backends.values():
                try:
                    backend.close()
                except Exception as error:
                    errors.append(error)
        if owned_judge and judge is not None:
            try:
                judge.close()
            except Exception as error:
                errors.append(error)
        if errors:
            raise ExceptionGroup('Offline corpus cleanup failed', errors)
    if _fingerprint() != snapshot:
        raise RuntimeError('Offline quality source changed during evaluation')
    baseline_path = ROOT / 'bench/baseline.json'
    baseline = json.loads(baseline_path.read_text()) if baseline_path.exists() else {}
    card = build_scorecard(results, args.candidate, options, run_id=args.run_id, split=args.split, baseline=baseline)
    card.update({'pipeline_sha256': snapshot, 'manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                 'seconds_per_clip': args.seconds, 'pilot': bool(args.clip) or args.seconds < 5,
                 'environment': {'platform': platform.platform(), 'python': platform.python_version(),
                                 'opencv': cv2.__version__, 'cpu_count': os.cpu_count()},
                 'baseline_reference': {'run_id': baseline.get('run_id'), 'path': str(baseline_path)}})
    (directory / 'scorecard.json').write_text(json.dumps(card, indent=2) + '\n')
    print(json.dumps({'scorecard': str(directory / 'scorecard.json'), 'mode': card['mode'],
                      'natural': card['natural'], 'synthetic': card['synthetic'],
                      'protected_fraction': card['protected_fraction'], 'comparison_valid': card['comparison_valid'],
                      'quality_checks': card['quality_checks'], 'gate_1': card['gate_1']}), flush=True)
    return card


if __name__ == '__main__':
    main()

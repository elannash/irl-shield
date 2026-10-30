"""Isolated CPU comparison/clocked/quality entry points; never edits common factories.

Run with a private venv. The caller must hold the host EX perf lease for compare
and clocked, SH for quality/grade, after the root readiness marker is complete.
All outputs are benchmark-only, muted, and not demo-ready.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
import math
from pathlib import Path
import platform
import shutil
import time

from bench.openvino_parity import compare_boxes

ROOT = Path(__file__).resolve().parents[1]
MARKER = Path('/tmp/agents/irl-shield/m1-20261029-ready.json')


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def source_identity():
    from bench.clocked_pipeline import fingerprint, file_sha256
    return {'common_pipeline_sha256': fingerprint(),
            'lane_sources': {str(p.relative_to(ROOT)): file_sha256(p)
                             for p in sorted((ROOT / 'bench').glob('openvino*')) if p.is_file()}}


def readiness():
    marker = json.loads(MARKER.read_text())
    if marker.get('complete') is not True:
        raise RuntimeError('Root readiness marker is not complete')
    return marker


class HostPressureError(RuntimeError):
    def __init__(self, snapshot):
        self.snapshot = snapshot
        super().__init__(f'Host memory pressure is {snapshot["pressure_state"]}')


def healthy(allow_warn=False):
    from bench.clocked_pipeline import perf_health
    value = perf_health()
    if value['pressure_state'] != 'normal' and not (allow_warn and value['pressure_state'] == 'warn'):
        raise HostPressureError(value)
    return value


def cache_models(source, destination):
    from models.prepare import verified_path
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or source in destination.parents:
        raise ValueError('Derived model cache must be separate from the read-only source cache')
    destination.mkdir(parents=True, exist_ok=True)
    for name in ('ppocr-v6-tiny', 'ppocr-v6-small'):
        path, _ = verified_path(name, source)
        target = destination / path.name
        if not target.exists():
            shutil.copyfile(path, target)
        verified_path(name, destination)
    return destination


def detector(name, width, side, cache, precision):
    import numpy as np
    from bench.openvino_detector import OpenVINODetector, preprocess_for
    tensor = preprocess_for(name, side)(np.zeros((round(720 * width / 1280), width, 3), np.uint8))
    return OpenVINODetector(name, cache_dir=cache, static_shape=list(tensor.shape[2:]),
                           precision=precision, limit_side_len=side)


def tune_frames(fixture_root, count):
    import cv2
    import numpy as np
    from models.prepare import sha256_file
    manifest = json.loads((ROOT / 'fixtures/manifest.json').read_text())
    frames, receipts = [], []
    for clip in manifest['clips']:
        if clip['split'] != 'tune':
            continue
        path = Path(fixture_root) / Path(clip['path']).name
        if sha256_file(path) != clip['sha256']:
            raise ValueError(f'Fixture hash mismatch: {path}')
        cap = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 2])
        try:
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            indices = np.linspace(15, total - 16, count, dtype=int).tolist()
            for index in indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, index)
                ok, frame = cap.read()
                if not ok or frame.std() < 5:
                    raise RuntimeError(f'Real video decode failed: {path} frame {index}')
                receipt = {'clip': clip['id'], 'frame': index, 'source_sha256': clip['sha256'],
                           'pixels_sha256': hashlib.sha256(frame.tobytes()).hexdigest()}
                frames.append((receipt, frame))
            receipts.append({'clip': clip['id'], 'source': str(path), 'sha256': clip['sha256'], 'indices': indices})
        finally:
            cap.release()
    if len(receipts) != 7:
        raise ValueError('Comparison requires all seven tune clips')
    return frames, receipts


def distribution(values):
    import numpy as np
    return {'count': len(values), 'median': float(np.median(values)), 'p95': float(np.percentile(values, 95))}


def compare(args):
    import gc
    import cv2
    import numpy as np
    from bench.openvino_detector import preprocess_for
    from bench.onnx_detectors import create_detector
    from bench.clocked_pipeline import host_environment, perf_health
    cv2.setNumThreads(1)
    marker, preflight = readiness(), healthy(args.contended)
    cache = cache_models(args.model_cache, args.cache)
    frames, fixtures = tune_frames(args.fixtures, args.samples)
    identity = source_identity()
    card = {'schema_version': 2, 'status': 'running', 'mode': 'inference-comparison', 'benchmark_only': True, 'demo_ready': False,
            'scope': 'All seven tune clips; identical FP32 source ONNX/static shapes/preprocessing/postprocessing, batch1; call latency is not wall-clock stream fps',
            'measurement': 'One active runtime session at a time; full calls use public detect; map inference measured separately; hashing outside timed regions',
            'environment': host_environment(), 'root_readiness': marker, 'source_identity': identity,
            'fixtures': fixtures, 'warmup_calls_per_runtime': 3, 'repetitions': args.repetitions,
            'precision': args.precision, 'variants': [], 'preflight_health': preflight}
    for name in ('ppocr-v6-tiny', 'ppocr-v6-small'):
        for side in args.sides:
            preprocess = preprocess_for(name, side)
            shape = list(preprocess(frames[0][1]).shape[2:])
            row = {'name': name, 'side': side, 'runtime_phases': {}, 'contended': args.contended, 'calls': [], 'parity': []}
            outputs = {}
            for runtime in ('ort', 'openvino'):
                start = healthy(args.contended)
                backend = (create_detector(name, {'cache_dir': cache, 'provider': 'cpu', 'threads': 2,
                                                   'static_shape': shape, 'limit_side_len': side})
                           if runtime == 'ort' else detector(name, 1280, side, cache, args.precision))
                try:
                    for _ in range(3):
                        backend.detect(frames[0][1])
                    row[runtime] = backend.metadata
                    raw_outputs = []
                    for repetition in range(args.repetitions):
                        for receipt, frame in frames:
                            # Public call timing excludes receipt hashing and the separate map probe.
                            began, cpu = time.perf_counter(), time.process_time()
                            boxes = backend.detect(frame)
                            wall_ms, cpu_ms = (time.perf_counter() - began) * 1000, (time.process_time() - cpu) * 1000
                            tensor = preprocess(frame)
                            before = time.perf_counter()
                            # RapidOCR3.10.0 exposes its map session only through the wrapped detector.
                            # This inspection stays in the benchmark, never the engine/adapter interface.
                            prediction = (backend._detector.session(tensor) if runtime == 'ort' else backend.infer(tensor))
                            inference_ms = (time.perf_counter() - before) * 1000
                            if not np.isfinite(prediction).all():
                                raise RuntimeError('Runtime map contains nonfinite values')
                            row['calls'].append({**receipt, 'repetition': repetition, 'runtime': runtime,
                                                 'inference_ms': inference_ms, 'total_call_ms': wall_ms,
                                                 'process_cpu_ms': cpu_ms})
                            if repetition == 0:
                                raw_outputs.append((boxes, prediction.copy(), hashlib.sha256(tensor.tobytes()).hexdigest()))
                    outputs[runtime] = raw_outputs
                    row['runtime_phases'][runtime] = {'health_start': start, 'health_end': perf_health(),
                                                     'active_model_sessions': 1}
                finally:
                    backend.close()
                    del backend
                    gc.collect()
            for (receipt, frame), reference, candidate in zip(frames, outputs['ort'], outputs['openvino'], strict=True):
                ort_boxes, ort_map, ort_tensor = reference
                ov_boxes, ov_map, ov_tensor = candidate
                if ort_tensor != ov_tensor or ort_map.shape != ov_map.shape:
                    raise RuntimeError('Runtime tensors or output shapes differ')
                delta = np.abs(ort_map - ov_map)
                row['parity'].append({**receipt, 'tensor_sha256': ort_tensor, 'reference_boxes': ort_boxes,
                                       'openvino_boxes': ov_boxes, 'boxes': compare_boxes(ort_boxes, ov_boxes),
                                       'map_max_abs': float(delta.max()), 'map_mean_abs': float(delta.mean()),
                                       'reference_map_sha256': hashlib.sha256(ort_map.tobytes()).hexdigest(),
                                       'openvino_map_sha256': hashlib.sha256(ov_map.tobytes()).hexdigest()})
            row['timing_valid'] = not args.contended and all(
                phase[key]['pressure_state'] == 'normal' for phase in row['runtime_phases'].values()
                for key in ('health_start', 'health_end'))
            row['summary'] = {runtime: {key: distribution([c[key] for c in row['calls'] if c['runtime'] == runtime])
                                        for key in ('inference_ms', 'total_call_ms', 'process_cpu_ms')} for runtime in outputs}
            row['parity_pass'] = all(p['boxes']['pass'] for p in row['parity']) and any(p['boxes']['nonempty_evidence'] for p in row['parity'])
            row['total_reference_boxes'] = sum(p['boxes']['reference_count'] for p in row['parity'])
            card['variants'].append(row)
            save(args.out, card)
            print(json.dumps({k: row[k] for k in ('name', 'side', 'summary', 'parity_pass', 'timing_valid', 'total_reference_boxes')}), flush=True)
    card['health_end'] = perf_health()
    card['source_unchanged'] = identity == source_identity()
    if not card['source_unchanged']:
        raise RuntimeError('Source changed during inference comparison')
    card['status'] = 'complete'
    save(args.out, card)
    return card


def clocked(args):
    import cv2
    from bench.clocked_pipeline import (VideoSource, FFmpegSink, ResourceSampler, drive, probe_media,
        source_window, measurement_windows, file_sha256, fingerprint, host_environment, perf_health, performance_trust, quantiles)
    from shield.engine import MaskingEngine
    from shield.lanes import DetectorLane
    from shield.render import Renderer
    cv2.setNumThreads(1)
    marker, preflight = readiness(), healthy(args.contended)
    cache = cache_models(args.model_cache, args.cache)
    identity = source_identity()
    media = probe_media(args.source)
    if media['resolution'] != [1280, 720] or not math.isclose(media['fps'], 30):
        raise ValueError('Sustained comparison requires 720p30 source')
    options = {'delay_seconds': 1., 'before': 6, 'after': 30, 'fast_rate_hz': args.fast_rate,
               'accurate_rate_hz': args.accurate_rate, 'fast_width': 640, 'accurate_width': 1280,
               'fast_limit_side_len': 640, 'limit_side_len': 960, 'fast_candidate': 'ppocr-v6-tiny',
               'static_model': True, 'provider': 'openvino-cpu', 'fast_provider': 'openvino-cpu',
               'precision': args.precision, 'threads': 2, 'contended': args.contended, 'warmup_seconds': 10., 'repeat_seconds': args.seconds,
               'encoder': args.encoder, 'padding': .3, 'motion_mode': 'phase', 'motion_width': 320, 'motion_min_response': .05}
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    window = source_window(media, options)
    source = VideoSource(args.source, media, window['total_frames'], window['total_frames'] / media['fps'])
    sink = FFmpegSink(output, media['resolution'], media['fps'], args.encoder)
    capture = cv2.VideoCapture(str(args.source), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 2])
    try:
        ok, warm = capture.read()
        if not ok:
            raise RuntimeError('Warmup decode failed')
    finally:
        capture.release()
    loading, lanes = {}, {}
    with ExitStack() as cleanup:
        for lane, name, width, side, rate in (('fast', 'ppocr-v6-tiny', 640, 640, args.fast_rate),
                                              ('accurate', args.candidate, 1280, 960, args.accurate_rate)):
            began = time.monotonic()
            backend = detector(name, width, side, cache, args.precision)
            cleanup.callback(backend.close)
            pixels = cv2.resize(warm, (width, round(720 * width / 1280))) if width != 1280 else warm
            backend.detect_quads(pixels)
            loading[lane] = {'seconds': time.monotonic() - began, 'metadata': backend.metadata}
            lanes[lane] = DetectorLane(lane, backend, rate, width)
            cleanup.callback(lanes[lane].close)
        engine = MaskingEngine(lanes, {**options, 'fps': 30}, renderer=Renderer(padding=.3))
        cleanup.callback(engine.close)
        start = healthy(args.contended)
        sampler = ResourceSampler()
        sampler.start()
        try:
            result = drive(source, engine, sink)
        finally:
            resources = sampler.finish()
    for record in result['records']:
        record['mask_shape'] = [720, 1280]
        record['decoded_at'] = source.decoded_at.get(record['frame'])
    windows = measurement_windows(result['records'], source_fps=30, origin=result['clock_origin'],
                                   ended_at=result['clock_origin'] + result['seconds'], warmup_frames=window['warmup_frames'])
    result.update(windows)
    # Preserve primary names consumed by the existing clock guards and scorer.
    result.update({k: v for k, v in windows['steady'].items() if k not in ('frames', 'seconds', 'encoded_frames', 'source_duration_seconds')})
    for stats in result['engine']['lanes'].values():
        stats['actual_hz'] = stats['completed'] / source.duration
        stats['service_quantiles_seconds'] = quantiles(stats['service_seconds'])
    output_media = probe_media(output)
    if output_media['frames'] != result['frames'] or output_media['resolution'] != media['resolution'] or output_media['fps'] != media['fps']:
        raise RuntimeError('Encoded frame count/resolution/PTS differs from source')
    result.update({**resources, 'warmup_frames': window['warmup_frames'], 'steady_frames': window['steady_frames'],
                   'warmup_seconds': 10., 'steady_duration_seconds': args.seconds,
                   'source_media': media, 'output_media': output_media, 'resolution': media['resolution'],
                   'source_sha256': file_sha256(args.source), 'output_sha256': file_sha256(output),
                   'mask_pixels_sha256': file_sha256(output.with_suffix('.mask-pixels.zip')),
                   'pipeline_sha256': fingerprint(), 'source_identity': identity,
                   'candidate': args.candidate, 'options': options, 'processing_environment': host_environment(),
                   'loading': loading, 'encoder': sink.codec, 'encoder_command': sink.command, 'pace': True,
                   'delay_seconds': 1., 'detector_cpu_only': True, 'all_cpu_encode': args.encoder == 'libx264',
                   'perf_health': {'preflight': preflight, 'start': start, 'end': perf_health()},
                   'root_readiness': marker, 'benchmark_only': True, 'demo_ready': False,
                   'ingest': {'queue_drops': source.queue_drops, 'injected_drops': source.injected_drops},
                   'cpu_scope': 'Process tree including native detector workers, decode, motion, renderer and FFmpeg; one core=100%; hardware encoder cost not attributed'})
    if identity != source_identity():
        raise RuntimeError('Source changed during clocked measurement')
    trust = performance_trust(result)
    result.update(performance_valid=trust['valid'], performance_rejection_reasons=trust['reasons'])
    save(output.with_suffix('.masks.json'), result.pop('records'))
    save(output.with_suffix('.egress.json'), sink.progress)
    save(output.with_suffix('.performance.json'), result)
    print(json.dumps({k: result[k] for k in ('performance_valid', 'output_wall_rate_fps', 'realtime_added_latency_seconds', 'protected_fraction', 'cpu_percent_one_core_100')}), flush=True)
    return result


def quality(args):
    import cv2
    from bench.offline_quality import run_file, build_scorecard
    from bench.judges import Judges
    from bench.run import variant
    readiness()
    healthy()
    cv2.setNumThreads(1)
    cache = cache_models(args.model_cache, args.cache)
    directory = Path(args.out)
    directory.mkdir(parents=True, exist_ok=True)
    options = {'delay_seconds': 1., 'before': 6, 'after': 30, 'fast_rate_hz': args.fast_rate,
               'accurate_rate_hz': args.accurate_rate, 'fast_width': 640, 'accurate_width': 1280,
               'padding': .3, 'motion_mode': 'phase', 'motion_width': 320, 'encoder': args.encoder, 'motion_min_response': .05}
    manifest = json.loads((ROOT / 'fixtures/manifest.json').read_text())
    results = []
    with ExitStack() as cleanup:
        judge = Judges(args.candidate, directory / 'judge-cache')
        cleanup.callback(judge.close)
        backends = {}
        for lane, name, width, side in (('fast', 'ppocr-v6-tiny', 640, 640),
                                         ('accurate', args.candidate, 1280, 960)):
            backends[lane] = detector(name, width, side, cache, args.precision)
            cleanup.callback(backends[lane].close)
        for clip in manifest['clips']:
            if clip['split'] != 'tune':
                continue
            source = Path(args.fixtures) / Path(clip['path']).name
            from models.prepare import sha256_file
            if sha256_file(source) != clip['sha256']:
                raise ValueError(f'Fixture hash mismatch: {source}')
            for synthetic in (False, True):
                selected = source
                if synthetic:
                    selected = directory / (clip['id'] + '-synthetic.mp4')
                    variant({**clip, 'path': str(source)}, selected, True, 5.)
                output = directory / (clip['id'] + ('-synthetic' if synthetic else '') + '-masked.mp4')
                result = run_file(selected, output, args.candidate, options, judge=judge, backends=backends)
                result.update(clip=clip['id'], synthetic_variant=synthetic)
                results.append(result)
                save(directory / 'partial.json', results)
        card = build_scorecard(results, args.candidate, options)
        card.update(source_identity=source_identity(), detectors={k: v.metadata for k, v in backends.items()})
        save(directory / 'scorecard.json', card)
    return card


def grade_clocked(args):
    from bench.clocked_bench import score_video, clock_guards
    from bench.judges import Judges
    from bench.clocked_pipeline import file_sha256, host_environment, probe_media
    readiness()
    healthy()
    movie = Path(args.out)
    perf = json.loads(movie.with_suffix('.performance.json').read_text())
    if perf['source_sha256'] != file_sha256(args.source) or perf['output_sha256'] != file_sha256(movie):
        raise ValueError('Clocked source/output hash mismatch before grading')
    if perf['source_identity'] != source_identity():
        raise ValueError('Clocked source identity changed before grading')
    judge = Judges(args.candidate, movie.parent / 'judge-cache')
    try:
        media = probe_media(args.source)
        truth_path = args.source.with_suffix('.truth.json')
        truth = json.loads(truth_path.read_text()) if truth_path.exists() else [[] for _ in range(media['frames'])]
        quality = score_video(args.source, movie, judge, truth)
        card = {'schema_version': 2, 'mode': 'single-sustained-clocked-quality', 'split': 'tune',
                'benchmark_only': True, 'demo_ready': False, 'gate_1': {'eligible': False, 'pass': False},
                'scope': 'One tune clip final steady source cycle; no synthetic claim without truth; no full-corpus gate',
                'judges': judge.names, 'grading_environment': host_environment(), 'quality': quality,
                'performance': perf, 'clock_guards': clock_guards(perf)}
        save(movie.with_suffix('.scorecard.json'), card)
        print(json.dumps({'quality': {k: quality[k] for k in ('natural', 'synthetic', 'real_video_pass')},
                          'clock_guards': card['clock_guards']}), flush=True)
        return card
    finally:
        judge.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('compare', 'clocked', 'quality', 'grade-clocked'))
    parser.add_argument('--model-cache', type=Path, required=True, help='Read-only source model cache')
    parser.add_argument('--cache', type=Path, default=ROOT / '.tmp/openvino/models')
    parser.add_argument('--fixtures', type=Path, default=ROOT / 'fixtures/cache')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--contended', action='store_true', help='Warn-pressure diagnostic only; never valid timing; critical/unknown still rejected')
    parser.add_argument('--precision', choices=('fp32', 'fp16', 'bf16'), default='fp32')
    parser.add_argument('--samples', type=int, default=3, help='Identical samples per each of seven tune clips')
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--sides', type=int, nargs='+', default=[640, 960])
    parser.add_argument('--source', type=Path)
    parser.add_argument('--seconds', type=int, default=30)
    parser.add_argument('--candidate', choices=('ppocr-v6-tiny', 'ppocr-v6-small'), default='ppocr-v6-tiny')
    parser.add_argument('--fast-rate', type=float, default=8.)
    parser.add_argument('--accurate-rate', type=float, default=4.)
    parser.add_argument('--encoder', choices=('h264_nvenc', 'h264_videotoolbox', 'libx264'), default='h264_nvenc')
    args = parser.parse_args(argv)
    if args.samples < 2 or args.repetitions < 2 or any(side < 32 for side in args.sides):
        parser.error('At least 2 samples/clip and repetitions; sides >=32 required')
    if args.mode == 'grade-clocked' and not args.source:
        parser.error('grade-clocked requires --source')
    if args.mode in ('quality', 'grade-clocked') and platform.system() != 'Darwin':
        parser.error('Three-judge grading requires native macOS Vision')
    if not all(math.isfinite(rate) and 0 < rate <= 30 for rate in (args.fast_rate, args.accurate_rate)):
        parser.error('Lane rates must be finite and in (0,30]')
    if args.mode == 'clocked' and (not args.source or args.seconds < 30):
        parser.error('Clocked requires --source and >=30 steady seconds')
    readiness()
    try:
        return {'compare': compare, 'clocked': clocked, 'quality': quality, 'grade-clocked': grade_clocked}[args.mode](args)
    except HostPressureError as error:
        rejected = args.out.with_name(args.out.stem + f'.rejected-{time.time_ns()}.json')
        save(rejected, {'status': 'rejected-before-or-between-measurement-phases',
                        'performance_valid': False, 'error': str(error), 'health': error.snapshot,
                        'source_identity': source_identity(),
                        'options': {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}})
        raise


if __name__ == '__main__':
    main()

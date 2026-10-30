"""Quality evaluation after the clocked pipeline; footage is benchmark-only.

Uses the existing licensed fixture/model inventory and existing NumPy/OpenCV
dependencies. No models, datasets, codecs or external assets are introduced.
"""
import hashlib
import json
import math
import argparse
import os
from pathlib import Path
import platform
import subprocess
import time
import shutil
import zipfile

import cv2
import numpy as np

from bench.metrics import fidelity, quantiles, validate_area_ceiling, masked_area_pass
from bench.scoring import score_records
from bench.independence import policy_metadata, resolve_fast_candidate, annotate_card
from bench.clocked_pipeline import performance_trust, coverage_distribution


ROOT = Path(__file__).resolve().parents[1]
SCOPE = ('Latin-script text and Arabic digits; natural input truth requires confidence>=0.9 on '
         'at least 2 frames per interval; every visible synthetic label remains truth; output OCR '
         'confidence>=0.5. Judges: Tesseract eng, Apple Vision accurate en-US, PP-OCRv5 English-mobile. '
         'Benchmark-only footage, no audio; non-Latin coverage and demo readiness unproven.')


def score_observations(input_readings, outputs, synthetic_truth, guards, records, *, detector_families):
    """Keep OCR interval semantics while applying outside-pixel guards to LIVE."""
    count = len(records)
    if not count or any(len(values) != count for values in (input_readings, outputs, synthetic_truth, guards)):
        raise ValueError('Quality evidence must account for every emitted source-clock frame')
    live = [i for i, row in enumerate(records) if row['state'] == 'LIVE' and not row['protected']]
    if any(guards[index] is None for index in live):
        raise ValueError('A LIVE frame is missing its actual outside-mask pixel guard')
    output_readings = [[reading for reading in frame if reading['confidence'] >= .5] for frame in outputs]
    quality, details = score_records(input_readings, output_readings, synthetic_truth,
                                     [guards[index] for index in live], detector_families=detector_families)
    quality.update({'live_frames': len(live), 'protected_frames': count - len(live),
                    'protected_fraction': (count - len(live)) / count,
                    'slate_frames': sum(row['slate'] for row in records)})
    details['frame_guards'] = guards
    details['presentation'] = records
    return quality, details


def quality_window(records, performance, synthetic_truth):
    """Select one final fixture cycle after warmup, retaining original frame IDs."""
    source_count = len(synthetic_truth)
    warmup = performance['warmup_frames']
    steady = performance['steady']
    start = len(records) - source_count
    if (not source_count or len(records) != performance['frames'] or steady['frames'] < source_count
            or start < warmup or start < steady['start_frame']):
        raise ValueError('Quality requires one complete source cycle in the steady window')
    selected, truth = [], []
    for local, row in enumerate(records[start:]):
        original = start + local
        if row['frame'] != original:
            raise ValueError('Quality steady frame accounting differs from the full artifact')
        source_frame = original % source_count
        selected.append({**row, 'frame': local, 'pts': local / performance['source_fps'],
                         'original_frame': original, 'original_pts': row['pts'], 'source_frame': source_frame})
        truth.append(synthetic_truth[source_frame])
    return selected, truth


def recorded_policy_metadata(performance):
    """Require retained lanes to agree with the policy before any OCR credit.

    Old options may omit a resolved default. A changed default must reject that
    receipt rather than silently changing its denominator or aggregate scope.
    """
    candidate, options = performance['candidate'], performance['options']
    declared_fast = resolve_fast_candidate(candidate, options)
    if declared_fast is None:
        return policy_metadata(candidate, options)
    loading = performance.get('loading', {})
    recorded_fast = loading.get('fast', {}).get('candidate')
    if recorded_fast is None:
        raise ValueError('Retained performance is missing its recorded fast lane candidate')
    recorded = policy_metadata(candidate, {**options, 'fast_candidate': recorded_fast})
    if declared_fast != recorded_fast:
        raise ValueError('Current policy differs from the recorded fast lane; use the frozen recorded policy')
    for lane, model in (('accurate', candidate), ('fast', recorded_fast)):
        receipt = loading.get(lane, {})
        families = receipt.get('metadata', {}).get('detector_families')
        if (receipt.get('candidate') != model or
                (families is not None and families != recorded['lanes'][lane]['detector_families'])):
            raise ValueError(f'Retained performance has inconsistent recorded {lane} lane provenance')
    return recorded


def score_video(input_path, output_path, judge, synthetic_truth):
    """Decode and judge after timing, using saved actual mask pixels, never rebuilt quads."""
    input_path, output_path = Path(input_path), Path(output_path)
    full_records = json.loads(output_path.with_suffix('.masks.json').read_text())
    performance = json.loads(output_path.with_suffix('.performance.json').read_text())
    detector_metadata = recorded_policy_metadata(performance)
    records, selected_truth = quality_window(full_records, performance, synthetic_truth)
    before_capture = cv2.VideoCapture(str(input_path), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 2])
    after_capture = cv2.VideoCapture(str(output_path), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 2])
    inputs, outputs, guards = [], [], []
    try:
        if not after_capture.set(cv2.CAP_PROP_POS_FRAMES, records[0]['original_frame']):
            raise RuntimeError('Cannot seek to the steady quality output window')
        next_source_frame = None
        with zipfile.ZipFile(output_path.with_suffix('.mask-pixels.zip')) as masks:
            if len(masks.namelist()) != len(full_records):
                raise RuntimeError('Actual mask archive has a different emitted frame count')
            for index, record in enumerate(records):
                source_frame = record['source_frame']
                if next_source_frame != source_frame:
                    if not before_capture.set(cv2.CAP_PROP_POS_FRAMES, source_frame):
                        raise RuntimeError(f'Cannot seek repeated input frame {source_frame}')
                ok, before = before_capture.read()
                next_source_frame = source_frame + 1
                good, after = after_capture.read()
                if not ok or not good or record['frame'] != index or before.shape != after.shape:
                    raise RuntimeError(f'Quality decode frame accounting failed at {index}')
                shape = record['mask_shape']
                if list(before.shape[:2]) != shape:
                    raise RuntimeError(f'Actual mask dimensions differ at {index}')
                packed = np.frombuffer(masks.read(f'{record["original_frame"]:08d}.bin'), dtype=np.uint8)
                expected_bytes = (shape[0] * shape[1] + 7) // 8
                if len(packed) != expected_bytes:
                    raise RuntimeError(f'Actual mask byte count differs at {index}')
                mask = np.unpackbits(packed, bitorder='little', count=shape[0] * shape[1]).reshape(shape) * 255
                if hashlib.sha256(mask.tobytes()).hexdigest() != record['mask_sha256']:
                    raise RuntimeError(f'Actual mask SHA-256 differs at {index}')
                inputs.append(judge.read(before))
                outputs.append(judge.read(after))
                live = record['state'] == 'LIVE' and not record['protected']
                guards.append(fidelity(before, after, mask) if live else None)
                if index % 30 == 0:
                    print(f'  judge frame {index}/{len(records)}', flush=True)
            if after_capture.read()[0]:
                raise RuntimeError('Quality decode found unexpected extra frames')
    finally:
        before_capture.release()
        after_capture.release()
    quality, details = score_observations(inputs, outputs, selected_truth, guards, records,
        detector_families=detector_metadata['detector_families'])
    quality['judging']=details['judging']=getattr(judge,'metadata',None)
    window = {'judged_frames': len(records), 'original_start_frame': records[0]['original_frame'],
              'original_stop_frame_exclusive': records[-1]['original_frame'] + 1,
              'source_frame_count': len(synthetic_truth), 'warmup_frames': performance['warmup_frames']}
    quality['quality_window'] = details['quality_window'] = window
    areas = [row['mask_fraction'] for row in records]
    live_areas = [row['mask_fraction'] for row in records if row['state'] == 'LIVE' and not row['protected']]
    quality.update({'masked_area_fraction': quantiles(areas), 'live_masked_area_fraction': quantiles(live_areas),
                    'outside_mae_p95': quantiles([guard['outside_mae'] for guard in guards
                                                if guard is not None and guard['outside_mae'] is not None])['p95']})
    output_path.with_suffix('.evidence.json').write_text(json.dumps(details, indent=2) + '\n')
    return quality


def clock_guards(performance, *, required_resolution=(1280,720)):
    """Accept only healthy30s steady trials; short quality timings are diagnostic."""
    full_count = performance['frames']
    fps = performance['source_fps']
    media = performance['output_media']
    steady = performance.get('steady', {})
    count = steady.get('frames', 0)
    trusted = performance_trust(performance)['valid'] and performance.get('performance_valid', False)
    span = performance['last_encoded_at'] - performance['first_encoded_at']
    rate = (count - 1) / span if span > 0 else 0.
    expected_span = (count - 1) / fps if fps > 0 else float('inf')
    drift = span - expected_span
    valid_pts = (len(media['pts']) == full_count and all(math.isfinite(value)
                 and math.isclose(value, index / fps, abs_tol=1e-5)
                 for index, value in enumerate(media['pts']))) if fps > 0 else False
    throughput = (
        trusted and count > 1 and full_count == performance['encoded_frames'] == performance['source_frames'] == media['frames']
        and count == full_count - performance['warmup_frames']
        and steady['start_frame'] == performance['warmup_frames'] and steady['stop_frame_exclusive'] == full_count
        and performance['resolution'] == media['resolution'] == list(required_resolution)
        and math.isclose(fps, 30., abs_tol=1e-6) and math.isclose(media['fps'], fps, abs_tol=1e-6)
        and valid_pts and math.isfinite(rate) and rate > 0
        and math.isclose(rate, performance['output_wall_rate_fps'], rel_tol=1e-6)
        and math.isclose(drift, performance['output_clock_drift_seconds'], abs_tol=1e-6)
        and drift <= 1 / fps
        and math.isclose(performance['source_duration_seconds'], full_count / fps, abs_tol=1e-5)
        and math.isclose(steady['source_duration_seconds'], count / fps, abs_tol=1e-5)
        and performance['seconds'] >= expected_span
        and count >= 900 and steady['source_duration_seconds'] >= 30)
    latency = performance['realtime_added_latency_seconds']['p95']
    protected = performance['protected_fraction']
    return {'throughput': bool(throughput),
            'latency': trusted and latency is not None and math.isfinite(latency) and 0 <= latency <= 1.3,
            'protected': math.isfinite(protected) and 0 <= protected < .02 and performance['live_frames'] > 0}


def fault_range(value):
    try:
        start, end = map(float, value.split(':'))
    except ValueError as error:
        raise argparse.ArgumentTypeError('Expected START:END seconds') from error
    if not math.isfinite(start) or not math.isfinite(end) or not 0 <= start < end:
        raise argparse.ArgumentTypeError('Expected finite 0<=START<END seconds')
    return (start, end)


def baseline_deltas(card, baseline):
    """Return percentage-point differences only where both metrics are known."""
    deltas = {}
    for kind in ('natural', 'synthetic'):
        measured, reference = card.get(kind), baseline.get(kind)
        current = measured.get('hidden_fraction') if measured is not None else None
        previous = reference.get('hidden_fraction') if reference is not None else None
        if current is None or previous is None:
            deltas[kind] = None
            continue
        if not math.isfinite(current) or not math.isfinite(previous):
            raise ValueError('Baseline comparison requires finite fractions or null')
        deltas[kind] = 100 * (current - previous)
    return deltas


def main(argv=None, judge=None):
    """CLI entry point; callers may inject an existing/frozen public judge adapter.

    Clean-checkout mode uses bench.judges.Judges. Injected judges remain owned by
    the caller; the bench never changes OCR thresholds or cached evidence.
    Fixture preparation currently reuses bench.run.variant, which uses the Mac
    VideoToolbox preparation path. The lower-level file adapter is codec-selectable.
    """
    from bench.clocked_pipeline import fingerprint, run

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', default='ppocr-v5-mobile')
    parser.add_argument('--split', choices=('tune', 'heldout'), default='tune')
    parser.add_argument('--clip')
    parser.add_argument('--seconds', type=float, default=5.)
    parser.add_argument('--warmup-seconds', type=float, default=10.)
    parser.add_argument('--contended', action='store_true', help='Run a diagnostic under contention; never accepted performance')
    parser.add_argument('--run-id', default=time.strftime('clocked-%Y%m%d-%H%M%S'))
    parser.add_argument('--D', '--delay-seconds', dest='delay_seconds', type=float, default=1.)
    parser.add_argument('--B', '--before', dest='before', type=int, default=6)
    parser.add_argument('--A', '--after', dest='after', type=int, default=18)
    parser.add_argument('--fast-max-age', type=int, default=6)
    parser.add_argument('--accurate-max-age', type=int, default=12)
    parser.add_argument('--fast-rate-hz', type=float, default=30.)
    parser.add_argument('--accurate-rate-hz', type=float, default=4.)
    parser.add_argument('--fast-width', type=int, default=640)
    parser.add_argument('--accurate-width', type=int, default=1280)
    parser.add_argument('--fast-candidate')
    parser.add_argument('--fast-provider', choices=('cpu', 'coreml', 'cuda'), default='cpu')
    parser.add_argument('--provider', choices=('cpu', 'coreml', 'cuda'), default='cpu')
    parser.add_argument('--limit-side-len', type=int, default=960)
    parser.add_argument('--fast-limit-side-len', type=int, default=640)
    parser.add_argument('--det-thresh', dest='thresh', type=float, default=.3)
    parser.add_argument('--box-thresh', type=float, default=.5)
    parser.add_argument('--unclip-ratio', type=float, default=1.6)
    parser.add_argument('--static-model', action='store_true')
    parser.add_argument('--encoder', choices=('h264_videotoolbox', 'h264_nvenc', 'libx264'), default='h264_videotoolbox')
    parser.add_argument('--padding', type=float, default=.3)
    parser.add_argument('--badge', action='store_true')
    parser.add_argument('--style', choices=('opaque',), default='opaque')
    parser.add_argument('--motion-width', type=int, default=320)
    parser.add_argument('--motion-min-response', type=float, default=.5)
    parser.add_argument('--motion-mode',choices=('orb','phase'),default='phase')
    parser.add_argument('--fast-fault', type=fault_range, action='append', default=[])
    parser.add_argument('--accurate-fault', type=fault_range, action='append', default=[])
    parser.add_argument('--source-skip', type=fault_range, action='append', default=[],
                        help='Drop source input during START:END seconds; START must be >0')
    parser.add_argument('--natural-only', action='store_true')
    parser.add_argument('--performance-only', action='store_true')
    parser.add_argument('--prepared-dir', type=Path, help='Reuse exact prepared input movies and truth; copy bytes into the bundle')
    parser.add_argument('--defer-score', action='store_true', help='Seal measurements for later grading; construct no OCR judge')
    parser.add_argument('--sustained-seconds', type=float, default=0.,
                        help='Repeat the slowest measured quality source for at least30 seconds')
    parser.add_argument('--sustained-source-clip', help='Use this selected natural clip for sustained timing instead of the slowest clip')
    parser.add_argument('--area-ceiling', type=float,
                        help='Tune-derived median ceiling over ALL masks, including protected masks; no default is invented')
    parser.add_argument('--area-ceiling-basis', help='Receipt pointer behind the configured area ceiling')
    args = parser.parse_args(argv)
    if os.environ.get('IRL_SHIELD_PERF_QUEUE_FORCED') == '1':
        args.contended = True
    if (not math.isfinite(args.seconds) or args.seconds < 2 / 30
            or not math.isfinite(args.delay_seconds) or not 0 <= args.delay_seconds <= 1):
        parser.error('At least two source frames are required, and D must be between zero and one second')
    if not math.isfinite(args.warmup_seconds) or args.warmup_seconds < 0:
        parser.error('Warmup seconds must be finite and nonnegative')
    if args.sustained_seconds and (not math.isfinite(args.sustained_seconds) or args.sustained_seconds < 30):
        parser.error('Sustained source duration must be at least30 seconds')
    try:
        validate_area_ceiling(args.area_ceiling, args.area_ceiling_basis,
                              required=args.area_ceiling is not None)
    except ValueError as error:
        parser.error(str(error))
    if Path(args.run_id).name != args.run_id or args.run_id in ('.', '..'):
        parser.error('Run ID must be a single directory name')
    options = {key: getattr(args, key) for key in (
        'delay_seconds', 'before', 'after', 'fast_max_age', 'accurate_max_age', 'fast_rate_hz',
        'accurate_rate_hz', 'fast_width', 'accurate_width', 'fast_provider', 'provider',
        'limit_side_len', 'fast_limit_side_len', 'thresh', 'box_thresh', 'unclip_ratio', 'static_model', 'encoder', 'padding', 'badge',
        'style', 'motion_width','motion_mode','motion_min_response', 'warmup_seconds', 'contended')}
    if args.fast_candidate:
        options['fast_candidate'] = args.fast_candidate
    options.update({'fast_faults': args.fast_fault, 'accurate_faults': args.accurate_fault,
                    'source_skip_ranges': args.source_skip})
    manifest = json.loads((ROOT / 'fixtures/manifest.json').read_text())
    clips = [clip for clip in manifest['clips'] if clip['split'] == args.split
             and (args.clip is None or clip['id'] == args.clip)]
    if not clips:
        raise ValueError('Empty licensed fixture selection')
    directory = ROOT / 'out' / args.run_id
    directory.mkdir(parents=True, exist_ok=False)
    source_fingerprint = fingerprint()
    owned_judge = judge is None and not args.performance_only and not args.defer_score
    judge_memory_isolation = {
        'isolated': judge is None,
        'mode': 'borrowed-resident' if judge is not None else 'owned-deferred' if owned_judge else 'no-judge',
        'scope': 'Judges supplied to or owned by this invocation',
        'reason': ('A caller-supplied judge may already occupy memory during every measurement'
                   if judge is not None else 'No judge is constructed before all measurements finish'),
    }
    results = []
    pending_quality = []
    sustained = None
    try:
        if args.prepared_dir is None:
            from bench.run import variant
        from fixtures.prepare import verify_cached
        for clip in clips:
            verify_cached(ROOT / clip['path'], clip)
            for synthetic in ([False] if args.natural_only else [False, True]):
                label = clip['id'] + ('-synthetic' if synthetic else '-natural')
                print(f'{label}: {args.candidate}, fixed D={args.delay_seconds}s; warmup={args.warmup_seconds}s', flush=True)
                source = directory / f'{label}-input.mp4'
                if args.prepared_dir is None:
                    truth = variant(clip, source, synthetic, args.seconds)
                else:
                    prepared = args.prepared_dir / source.name
                    prepared_truth = prepared.with_suffix('.truth.json')
                    shutil.copyfile(prepared, source)
                    shutil.copyfile(prepared_truth, source.with_suffix('.truth.json'))
                    truth = json.loads(source.with_suffix('.truth.json').read_text())
                    if len(truth) != round(args.seconds * 30):
                        raise ValueError('Prepared truth count must match the requested source seconds')
                output = directory / f'{label}-masked.mp4'
                performance = run(source, output, args.candidate, options)
                result = {'clip': clip['id'], 'synthetic_variant': synthetic,
                          'source': str(source), 'output': str(output), 'performance': performance}
                if args.prepared_dir is not None:
                    result['prepared_source'] = {'path': str(prepared.resolve()),
                                                 'sha256': hashlib.sha256(prepared.read_bytes()).hexdigest(),
                                                 'truth_sha256': hashlib.sha256(prepared_truth.read_bytes()).hexdigest()}
                results.append(result)
                if args.defer_score:
                    result['truth'] = str(source.with_suffix('.truth.json'))
                if not args.performance_only and not args.defer_score:
                    pending_quality.append((result, truth))
        if args.sustained_seconds:
            if args.sustained_source_clip:
                matches = [result for result in results if result['clip'] == args.sustained_source_clip and not result['synthetic_variant']]
                if len(matches) != 1:
                    raise ValueError('Choose one selected natural clip for sustained timing')
                slowest = matches[0]
            else:
                slowest = max(results, key=lambda result: result['performance']['realtime_added_latency_seconds']['p95'])
            sustained = run(slowest['source'], directory / 'sustained-masked.mp4', args.candidate,
                             {**options, 'repeat_seconds': args.sustained_seconds})
        receipts = [(Path(result['output']), result['performance']) for result in results]
        if sustained is not None:
            receipts.append((directory / 'sustained-masked.mp4', sustained))
        for output, performance in receipts:
            performance['judge_memory_isolation'] = judge_memory_isolation
            output.with_suffix('.performance.json').write_text(json.dumps(performance, indent=2) + '\n')
        if owned_judge:
            from bench.judges import Judges
            judge = Judges(args.candidate, ROOT / 'out/judge-cache')
        for result, truth in pending_quality:
            result.update(score_video(result['source'], result['output'], judge, truth))
    finally:
        if owned_judge and judge is not None:
            judge.close()
    if fingerprint() != source_fingerprint:
        raise RuntimeError('Clocked benchmark source changed during measurement or judging')
    card = {'schema_version': 2, 'run_id': args.run_id, 'candidate': args.candidate,
            'split': args.split, 'scope': SCOPE + ' Quality judges one final fixture cycle after warmup; indices are normalized only in scoring evidence.',
            'benchmark_only': True, 'demo_ready': False,
            'options': options, 'seconds_per_clip': args.seconds, 'pilot': bool(args.clip) or args.seconds < 5,
            'pipeline_sha256': source_fingerprint,
            'manifest_sha256': hashlib.sha256((ROOT / 'fixtures/manifest.json').read_bytes()).hexdigest(),
            'environment': {'platform': platform.platform(), 'python': platform.python_version(),
                            'opencv': cv2.__version__, 'cpu_count': os.cpu_count(),
                            'ffmpeg': subprocess.check_output(['ffmpeg', '-version'], text=True).splitlines()[0]},
            'judges': list(judge.names) if judge is not None and not args.performance_only and not args.defer_score else [],
            'performance_only': args.performance_only, 'natural_only': args.natural_only,
            'judge_memory_isolation': judge_memory_isolation, 'clips': results, 'sustained': sustained,
            'licenses': ['fixtures/ATTRIBUTION.md', 'models/manifest.json', 'models/licenses/dependencies.json'],
            'area_ceiling': args.area_ceiling, 'area_ceiling_basis': args.area_ceiling_basis}
    if args.defer_score:
        from bench.cross_host import seal_measurement
        return seal_measurement(card, directory)
    return aggregate_card(card, directory, root=ROOT)


def aggregate_card(card, directory, *, root=None):
    """One aggregation contract for same-host and deferred cross-host grading."""
    root = ROOT if root is None else Path(root)
    directory = Path(directory)
    results, sustained = card['clips'], card['sustained']
    for kind in ('natural', 'synthetic'):
        hidden = sum(result.get(kind, {}).get('hidden', 0) for result in results)
        total = sum(result.get(kind, {}).get('total', 0) for result in results)
        card[kind] = {'hidden': hidden, 'total': total, 'hidden_fraction': hidden / total if total else None}
    all_records = []
    presentation_delays = []
    for result in results:
        records = json.loads(Path(result['output']).with_suffix('.masks.json').read_text())
        start = result.get('quality_window', {}).get('original_start_frame', result['performance']['steady']['start_frame'])
        all_records.extend(records[start:])
        presentation_delays.extend(row['emitted_at']-(result['performance']['clock_origin']+row['pts'])
                                   for row in records[start:])
    live_records = [row for row in all_records if row['state'] == 'LIVE' and not row['protected']]
    card['coverage']=coverage_distribution(all_records)
    card['presentation_delay_seconds']=quantiles(presentation_delays)
    card['presentation_delay_scope']='Frame-weighted steady emission minus original paced source PTS, before encoding'
    card['masked_area_fraction'] = quantiles([row['mask_fraction'] for row in all_records])
    card['live_masked_area_fraction'] = quantiles([row['mask_fraction'] for row in live_records])
    card['protected_fraction'] = (len(all_records) - len(live_records)) / len(all_records)
    card['minimum_clip_fps'] = min(result['performance']['output_wall_rate_fps'] for result in results)
    card['throughput_measurement'] = 'Steady-only observed mux packet rate; full decoded frame count/PTS retained; quality timings diagnostic only'
    card['latency_seconds'] = {q: max(result['performance']['realtime_added_latency_seconds'][q] for result in results)
                               for q in ('p50', 'p95')}
    card['real_video_pass'] = all(result.get('real_video_pass', False) for result in results) and bool(live_records)
    card['cpu_percent_one_core_100'] = quantiles([result['performance']['cpu_percent_one_core_100'] for result in results])
    card['peak_tree_rss_mb'] = max(result['performance']['peak_tree_rss_mb'] for result in results)
    controls = [result['synthetic_input_control'] for result in results
                if result['synthetic_variant'] and 'synthetic_input_control' in result]
    control = {'total': sum(value['total'] for value in controls),
               'unreadable': sum(value['unreadable'] for value in controls)}
    card['synthetic_input_control'] = control
    short_guards = [clock_guards(result['performance']) for result in results]
    sustained_guards = clock_guards(sustained) if sustained else {'throughput': False, 'latency': False, 'protected': False}
    ceiling = validate_area_ceiling(card.get('area_ceiling'), card.get('area_ceiling_basis'))
    area_configured = ceiling is not None
    area = card['masked_area_fraction']['p50']
    independence=annotate_card(card)
    card['gate_1'] = {
        'independent_judges': independence['sufficient_independent_engines'],
        'judge_discrimination': control['total'] > 0 and control['unreadable'] == 0,
        'natural': card['natural']['hidden_fraction'] is not None and card['natural']['hidden_fraction'] >= .9,
        'synthetic': card['synthetic']['total'] > 0 and card['synthetic']['hidden_fraction'] == 1.,
        'masked_area': masked_area_pass(card),
        'throughput': sustained_guards['throughput'],
        'latency': sustained_guards['latency'],
        'protected': sustained_guards['protected'] and all(guard['protected'] for guard in short_guards),
        'real_video': card['real_video_pass'],
        'queue_environment': card.get('queue_measurement_trust', {}).get('clean') is True,
        'eligible': card['split'] == 'heldout' and not card['pilot'] and len({result['clip'] for result in results}) >= 3
                    and not card.get('performance_only', False) and not card.get('natural_only', False) and sustained is not None and area_configured,
    }
    card['gate_1']['pass'] = all(card['gate_1'].values())
    card['performance_scope'] = 'Only the separate healthy30s steady trial can establish accepted performance; short warmed quality runs are diagnostic'
    card['startup'] = {result['output']: result['performance']['startup'] for result in results}
    card['gate_notes'] = {'protected': 'Strictly below2%; PROTECT blur and HOLD both count.',
                          'queue_environment': 'Requires a closed, clean queue measurement receipt. Direct/deferred raw cards retain endpoint memory checks only; the final joined card applies the recorded contamination policy.',
                          'throughput': 'Healthy30s steady window after warmup,900+ steadyframes,720p30 CFR full media; observed steady span at source rate. Short timings are diagnostic only.',
                          'latency': 'Healthy30s steady-only encoded added latency p95<=1.3s; startup and first-packet latency retained separately.',
                          'masked_area': 'Median over ALL scored steady masks, including protected masks; requires an explicit tune-derived value and receipt basis, otherwise fails unconfigured. Full warmup artifacts and both all-mask/LIVE p95 remain reported.'}
    baseline_path = root / 'bench/baseline.json'
    baseline = json.loads(baseline_path.read_text()) if baseline_path.exists() else {}
    card['baseline_reference'] = ({'path': 'bench/baseline.json', 'run_id': baseline.get('run_id'),
                                   'sha256': hashlib.sha256(baseline_path.read_bytes()).hexdigest(),
                                   'natural': baseline.get('natural'), 'synthetic': baseline.get('synthetic')}
                                  if baseline else None)
    same_flags = all(baseline.get(key) == card[key] for key in ('manifest_sha256', 'split', 'pilot'))
    card['baseline_comparison'] = ('Same manifest/split/pilot flags; clip selection may differ'
                                   if baseline and same_flags else 'Reference corpus or selection differs; deltas are descriptive'
                                   if baseline else 'Baseline unavailable')
    card['baseline_deltas_pp'] = baseline_deltas(card, baseline)
    text = json.dumps(card, indent=2) + '\n'
    (directory / 'scorecard.json').write_text(text)
    (root / 'out/scorecard.json').write_text(text)
    sustained_summary=None
    if sustained is not None:
        sustained_summary={
            'performance_valid':sustained['performance_valid'],
            'emitted_fps':sustained['output_wall_rate_fps'],
            'source_fps':sustained['source_fps'],
            'encoded_added_latency_seconds':sustained['realtime_added_latency_seconds'],
            'presentation_delay_seconds':sustained['presentation_delay_seconds'],
            'protected_fraction':sustained['protected_fraction'],
            'lane_hz_full_source':{name:stats['actual_hz'] for name,stats in sustained['engine']['lanes'].items()},
            'cpu_percent_one_core_100':sustained['cpu_percent_one_core_100'],
            'peak_tree_rss_mb':sustained['peak_tree_rss_mb'],
            'startup_first_packet_seconds':sustained['startup']['first_packet_delay_seconds']}
    print(json.dumps({'scorecard':str(directory/'scorecard.json'),
                      'scope':'Latin-script/digits; Tesseract eng + Vision accurate en-US + PP-OCRv5 English-mobile',
                      'natural':card['natural'],'synthetic':card['synthetic'],
                      'D_seconds':card['options']['delay_seconds'],'protected_fraction':card['protected_fraction'],
                      'masked_area_fraction':card['masked_area_fraction'],'real_video_pass':card['real_video_pass'],
                      'sustained':sustained_summary,'baseline_deltas_pp':card['baseline_deltas_pp'],
                      'gate_1':card['gate_1']}),flush=True)
    return card


if __name__ == '__main__':
    main()

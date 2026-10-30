"""All-seven tune comparison of FAST alone and best-v6 + FAST.

Borrows run_file/backends and the unchanged interval scorer. Inputs and the v6
reference are retained from an existing full tune receipt, never regenerated.
All media are benchmark-only, silent, and not demo-ready.
"""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import shutil

import cv2
import numpy as np

from bench.fast import FastDetector
from bench.fast_replay import ReplayDetector, UnionDetector, ReferenceInputs
from bench.fast_compare import interval_complementarity
from bench.fast_runtime import require_ready, source_fingerprint, health_valid, finish_health
from bench.clocked_pipeline import perf_health
from bench.offline_quality import run_file, build_scorecard
from bench.scoring import score_records
from models.prepare import sha256_file

ROOT = Path(__file__).resolve().parents[1]


def _reference(root, record):
    label = record['clip'] + ('-synthetic' if record['synthetic_variant'] else '-natural')
    source = root / f'{label}-input.mp4'
    truth = json.loads(source.with_suffix('.truth.json').read_text())
    output = root / f'{label}-masked.mp4'
    evidence = json.loads(output.with_suffix('.evidence.json').read_text())
    if 'raw_input_readings' not in evidence:
        raise ValueError('Reference lacks unfiltered three-judge input OCR evidence')
    quality, rescored = score_records(evidence['raw_input_readings'], evidence['output_readings'],
                                      truth, evidence['guards'])
    rescored['presentation'] = json.loads(output.with_suffix('.masks.json').read_text())
    return label, source, truth, evidence, quality, rescored, output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True,
                        help='Full all7 offline best-v6 run, read-only')
    parser.add_argument('--cache-dir', type=Path, required=True)
    parser.add_argument('--provider', choices=('cpu', 'coreml', 'cuda'), required=True)
    parser.add_argument('--side', type=int, default=1024)
    parser.add_argument('--fast-side', type=int, default=640)
    parser.add_argument('--mode', choices=('alone', 'union'), required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--encoder', choices=('h264_videotoolbox', 'h264_nvenc'), required=True)
    args = parser.parse_args(argv)
    if Path(args.run_id).name != args.run_id or args.run_id in ('.', '..'):
        parser.error('run-id must be one safe path component')
    ready = require_ready()
    reference_path = args.reference / 'scorecard.json'
    reference_sha256 = sha256_file(reference_path)
    reference = json.loads(reference_path.read_text())
    tune = {clip['id'] for clip in json.loads((ROOT / 'fixtures/manifest.json').read_text())['clips']
            if clip['split'] == 'tune'}
    expected = {(clip, synthetic) for clip in tune for synthetic in (False, True)}
    actual = [(row['clip'], row['synthetic_variant']) for row in reference['clips']]
    if reference['mode'] != 'offline_quality' or reference['split'] != 'tune' or set(actual) != expected or len(actual) != len(expected):
        raise ValueError('Reference must contain all seven tune clips and both variants exactly once')
    if reference['candidate'] != 'ppocr-v6-small':
        raise ValueError('This comparison requires the selected best-v6 small reference')
    directory = ROOT / 'out' / args.run_id
    directory.mkdir(parents=True, exist_ok=False)
    health = {'start': perf_health()}
    if not health_valid(health):
        (directory / 'rejected-health.json').write_text(json.dumps(health, indent=2))
        raise RuntimeError('FAST quality rejected: memory pressure is not normal')
    (directory / 'reference-scorecard.json').write_bytes(reference_path.read_bytes())
    if sha256_file(directory / 'reference-scorecard.json') != reference_sha256:
        raise RuntimeError('Reference scorecard changed while reading')
    snapshot = source_fingerprint()
    options = {**reference['options'], 'encoder': args.encoder, 'provider': args.provider}
    if args.mode == 'alone':
        options.update(fast_candidate='fast-tiny', fast_provider=args.provider)
    candidate = 'fast-tiny-alone' if args.mode == 'alone' else 'best-v6-plus-fast-tiny'
    results, comparisons, baseline_results = [], [], []
    with ExitStack() as cleanup:
        cleanup.callback(finish_health, health, directory)
        from bench.judges import Judges
        judge = Judges(candidate, directory / 'judge-cache')
        cleanup.callback(judge.close)
        expected_judges = ['tesseract-5-psm11', 'vision-accurate', 'ppocr-independent']
        if judge.names != expected_judges:
            raise ValueError('All three independent English OCR judges are required')
        accurate = FastDetector(cache_dir=args.cache_dir, provider=args.provider, side=args.side)
        cleanup.callback(accurate.close)
        fast = None
        if args.mode == 'alone':
            fast = FastDetector(cache_dir=args.cache_dir, provider=args.provider, side=args.fast_side)
            cleanup.callback(fast.close)
        for record in reference['clips']:
            label, source, truth, evidence, baseline_quality, rescored, output = _reference(args.reference, record)
            print(f'{label}: {candidate} IDEAL/OFFLINE', flush=True)
            source_sha = sha256_file(source)
            own_source = directory / source.name
            shutil.copyfile(source, own_source)
            own_source.with_suffix('.truth.json').write_text(json.dumps(truth) + '\n')
            if sha256_file(own_source) != source_sha:
                raise ValueError('Source copy SHA-256 mismatch')
            wrapped_judge = ReferenceInputs(judge, source, evidence['raw_input_readings'])
            replay = []
            if args.mode == 'union':
                detections = json.loads(output.with_suffix('.detections.json').read_text())
                cap = cv2.VideoCapture(str(source))
                try:
                    shape = (int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)), int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                             record['frames'])
                finally:
                    cap.release()
                for lane in ('fast', 'accurate'):
                    replay.append(ReplayDetector(detections[lane], source_shape=shape,
                                                 fps=record['source_fps'], rate=options[lane + '_rate_hz']))
                backends = {'fast': replay[0], 'accurate': UnionDetector(replay[1], accurate)}
            else:
                backends = {'fast': fast, 'accurate': accurate}
            masked = directory / f'{label}-masked.mp4'
            result = run_file(own_source, masked, candidate, options, judge=wrapped_judge,
                              backends=backends, synthetic_truth=truth)
            wrapped_judge.verify_complete()
            for detector in replay:
                detector.verify_complete()
            results.append({'clip': record['clip'], 'synthetic_variant': record['synthetic_variant'],
                            'source_sha256': source_sha, **result})
            # Rescore both using the current unchanged scorer and identical raw input truth.
            current = json.loads(masked.with_suffix('.evidence.json').read_text())
            current['presentation'] = json.loads(masked.with_suffix('.masks.json').read_text())
            comparisons.append({'clip': record['clip'], 'synthetic_variant': record['synthetic_variant'],
                                'source_sha256': source_sha,
                                'baseline_real_video_pass': baseline_quality['real_video_pass'],
                                'baseline_guard_zeroed_raw_hidden_intervals': (
                                    sum(not track['leaked'] for track in rescored['natural'])
                                    if not baseline_quality['real_video_pass'] else 0),
                                **interval_complementarity(rescored, current)})
            (directory / f'{label}-baseline-rescored.evidence.json').write_text(json.dumps(rescored) + '\n')
            baseline_results.append({'clip': record['clip'], 'synthetic_variant': record['synthetic_variant'],
                                     **baseline_quality})
            (directory / 'progress.json').write_text(json.dumps(results, indent=2) + '\n')
        metadata = {'accurate': accurate.metadata, 'fast': fast.metadata if fast else 'replayed best-v6 tiny'}
    if sha256_file(reference_path) != reference_sha256:
        raise RuntimeError('Reference scorecard changed during evaluation')
    if source_fingerprint() != snapshot:
        raise RuntimeError('FAST evaluation source changed during quality run')
    card = build_scorecard(results, candidate, options, run_id=args.run_id, split='tune')
    total = sum(row['baseline_leaked_intervals'] for row in comparisons)
    guarded = sum(row['guarded_recovered_intervals'] for row in comparisons)
    raw = sum(row['raw_recovered_intervals'] for row in comparisons)
    card.update({'ready': ready, 'pipeline_sha256': snapshot, 'detectors': metadata,
                 'reference': {'path': str(reference_path), 'sha256': reference_sha256},
                 'perf_health': health, 'quality_health_valid': health_valid(health),
                 'baseline_rescored': baseline_results,
                 'complementarity': {'baseline_leaked_intervals': total,
                                     'baseline_guard_zeroed_raw_hidden_intervals': sum(
                                         row['baseline_guard_zeroed_raw_hidden_intervals'] for row in comparisons),
                                     'raw_recovered_intervals': raw,
                                     'new_raw_leaked_intervals': sum(row['new_raw_leaked_intervals'] for row in comparisons),
                                     'raw_net_hidden_interval_change': sum(row['raw_net_hidden_interval_change'] for row in comparisons),
                                     'guarded_recovered_intervals': guarded,
                                     'rejected_protected_intervals': sum(row['rejected_protected_intervals'] for row in comparisons),
                                     'rejected_fidelity_intervals': sum(row['rejected_fidelity_intervals'] for row in comparisons),
                                     'raw_recovered_fraction': raw / total if total else None,
                                     'guarded_recovered_fraction': guarded / total if total else None,
                                     'clips': comparisons}})
    card['comparison_valid'] = card['comparison_valid'] and health_valid(health)
    card['input_ocr_provenance'] = 'Reused baseline raw three-judge input readings only after verifying every decoded input pixel digest; every output judged anew.'
    (directory / 'scorecard.json').write_text(json.dumps(card, indent=2) + '\n')
    print(json.dumps({key: card[key] for key in ('natural', 'synthetic', 'masked_area_fraction',
                                                'protected_fraction', 'comparison_valid', 'quality_checks')}, indent=2))
    return card


if __name__ == '__main__':
    main()

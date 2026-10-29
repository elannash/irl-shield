"""Explain retained OCR leaks without changing truth or rerunning detectors/OCR.

Original project code. NumPy is BSD-3-Clause; OpenCV is Apache-2.0 (existing
dependencies, notices in models/licenses/dependencies.json). Input footage
licenses remain in fixtures/ATTRIBUTION.md. Crops are benchmark evidence only,
may show third-party names, and are not demo-ready assets.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import zipfile

import cv2
import numpy as np

from shield.masking import masked_frame


def box_at(track, index):
    observations = track['observations']
    frames = np.array([item[0] for item in observations])
    boxes = np.array([item[1] for item in observations])
    return [float(np.interp(index, frames, boxes[:, axis])) for axis in range(4)]


def region(box, width, height):
    return [max(0, min(width, math.floor(box[0]))), max(0, min(height, math.floor(box[1]))),
            max(0, min(width, math.ceil(box[2]))), max(0, min(height, math.ceil(box[3])))]


def target_speed(track, index):
    observations = track['observations']
    if len(observations) < 2:
        return 0.
    frames = [item[0] for item in observations]
    right = min(len(frames) - 1, max(1, int(np.searchsorted(frames, index))))
    left_index, left = observations[right - 1]
    right_index, right_box = observations[right]
    left_center = (np.array(left[:2]) + left[2:]) / 2
    right_center = (np.array(right_box[:2]) + right_box[2:]) / 2
    return float(np.linalg.norm(right_center - left_center) / max(1, right_index - left_index))


class Masks:
    def __init__(self, output, records, shape, options):
        self.records, self.shape, self.options = records, shape, options
        path = output.with_suffix('.mask-pixels.zip')
        self.archive = zipfile.ZipFile(path) if path.exists() else None
        self.origin = 'saved-mask-pixels' if self.archive else (
            'frozen-AABB-reconstruction' if all('boxes' in row for row in records) else 'quad-reconstruction')

    def get(self, index):
        row = self.records[index]
        if self.archive:
            packed = np.frombuffer(self.archive.read(f'{index:08d}.bin'), np.uint8)
            if len(packed) != (int(np.prod(self.shape)) + 7) // 8:
                raise ValueError(f'Saved mask byte count differs at frame {index}')
            mask = np.unpackbits(packed, bitorder='little', count=int(np.prod(self.shape))).reshape(self.shape) * 255
            if row.get('mask_sha256') and hashlib.sha256(mask.tobytes()).hexdigest() != row['mask_sha256']:
                raise ValueError(f'Saved mask hash differs at frame {index}')
        elif 'boxes' in row:
            _, mask = masked_frame(np.zeros(self.shape, np.uint8), row['boxes'], self.options.get('padding', .3))
        else:
            from shield.render import Renderer
            frame = np.zeros((*self.shape, 3), np.uint8)
            mask = Renderer(padding=self.options.get('padding', .3), badge=self.options.get('badge', False)).render(
                frame, row['quads'], row.get('state', 'LIVE'), len(row['quads'])).mask
        if not math.isclose(float((mask > 0).mean()), row['mask_fraction'], abs_tol=1e-9):
            raise ValueError(f'Reconstructed mask area differs at frame {index}')
        return mask

    def close(self):
        if self.archive:
            self.archive.close()


def summarize(items):
    primary = Counter(item['primary_cause'] for item in items)
    attributes = Counter(attribute for item in items for attribute in item['attributes'])
    heights = [frame['height_px'] for item in items for frame in item['frames']]
    bins = Counter('<=12' if value <= 12 else '12-24' if value <= 24 else '24-48' if value <= 48 else '>48'
                   for value in heights)
    interval_heights = [float(np.median([frame['height_px'] for frame in item['frames']])) for item in items]
    interval_bins = Counter('<=12' if value <= 12 else '12-24' if value <= 24 else '24-48' if value <= 48 else '>48'
                            for value in interval_heights)
    if any('input_roi_laplacian_variance' in frame for item in items for frame in item['frames']):
        for name in ['low-sharpness/blur-candidate', 'fast-pan-candidate', 'motion-blur-candidate']:
            attributes.setdefault(name, 0)
    return {'failed_intervals': len(items), 'primary_causes': dict(primary.most_common()),
            'nonexclusive_attributes': dict(attributes.most_common()), 'leak_frame_height_bins': dict(bins),
            'interval_median_height_bins': dict(interval_bins),
            'observed_zero_overlap_intervals': sum(any(frame['covered_pixels'] == 0 and frame['observed_geometry']
                                                      for frame in item['frames']) for item in items),
            'observed_geometry_leak_frames': sum(frame['observed_geometry'] for item in items for frame in item['frames']),
            'leak_frames': len(heights)}


def observed_coverage(items, tracks, masks, width, height):
    """Distinguish always-poor masks from intermittent coverage using observed boxes."""
    by_frame = defaultdict(list)
    for item, track in zip(items, tracks, strict=True):
        item['maximum_observed_mask_coverage'] = 0.
        for index, box in track['observations']:
            by_frame[index].append((item, box))
    for index, targets in by_frame.items():
        mask = masks.get(index)
        for item, box in targets:
            x0, y0, x1, y1 = region(box, width, height)
            area = max(0, x1 - x0) * max(0, y1 - y0)
            if area:
                coverage = float(np.count_nonzero(mask[y0:y1, x0:x1]) / area)
                item['maximum_observed_mask_coverage'] = max(item['maximum_observed_mask_coverage'], coverage)
    for item in items:
        if item['primary_cause'] == 'detector-miss' and item['maximum_observed_mask_coverage'] >= .95:
            item['attributes'] = sorted([*item['attributes'], 'intermittent-mask-coverage'])


def classify_geometry(track, records, masks, width, height, options, small_height):
    measurements = []
    observed = {item[0] for item in track['observations']}
    attributes = set()
    for index in track['leak_frames']:
        box = box_at(track, index)
        x0, y0, x1, y1 = region(box, width, height)
        area = max(0, x1 - x0) * max(0, y1 - y0)
        if not area:
            raise ValueError(f'Leaking target is entirely offscreen at {index}')
        covered = int(np.count_nonzero(masks.get(index)[y0:y1, x0:x1]))
        target_height = box[3] - box[1]
        speed = target_speed(track, index)
        near_edge = min(box[0] / width, box[1] / height, (width - box[2]) / width,
                        (height - box[3]) / height) <= .02
        if target_height <= small_height:
            attributes.add('small-text/distance-unproven')
        if near_edge:
            attributes.add('near-edge')
            if index <= track['first'] + 3:
                attributes.add('edge-entry-candidate')
        if speed >= max(8., .5 * target_height):
            attributes.add('target-motion-or-OCR-box-jitter')
        if index not in observed:
            attributes.add('interpolated-leak-geometry')
        measurements.append({'frame': index, 'box': box, 'raster_roi': [x0, y0, x1, y1],
                             'covered_pixels': covered, 'visible_box_pixels': area,
                             'coverage_fraction': covered / area, 'height_px': target_height,
                             'target_speed_px_per_frame': speed, 'observed_geometry': index in observed})
    if any(0 < item['covered_pixels'] < item['visible_box_pixels'] for item in measurements):
        attributes.add('partial-coverage-on-some-leak-frame')
    worst = min(measurements, key=lambda item: (item['coverage_fraction'], not item['observed_geometry'], item['frame']))
    zero = worst['covered_pixels'] == 0
    partial = worst['covered_pixels'] < worst['visible_box_pixels']
    synchronous = options.get('stride', 1) == 1 and all('boxes' in row and 'coverage' not in row for row in records)
    row = records[worst['frame']]
    coverage_failure = 'coverage' in row and not row['coverage']['ok'] and not row.get('protected', False)
    if coverage_failure:
        cause = 'unprotected-coverage/timing-failure'
    elif zero:
        cause = 'detector-miss' if synchronous else 'zero-mask-overlap/cause-unresolved'
    elif partial:
        cause = 'partial-mask-coverage'
    else:
        cause = 'fully-covered-box/output-match-or-truth-uncertainty'
    return {'primary_cause': cause, 'attributes': sorted(attributes), 'frames': measurements,
            'representative_frame': worst['frame'], 'minimum_coverage_fraction': worst['coverage_fraction'],
            'timing_assessment': 'No known scheduling omission: synchronous stride1; zero overlap is detector miss'
            if synchronous else 'Timing cause requires recorded coverage/availability evidence',
            'confidence': {'primary': 'measured mask geometry against OCR-inferred/interpolated truth',
                           'attributes': 'heuristic, nonexclusive; not manually established causes',
                           'visual_review': 'pending'}}


def annotate_video(source, items, width, height, blur_threshold):
    by_frame = defaultdict(list)
    for item in items:
        for measurement in item['frames']:
            by_frame[measurement['frame']].append((item, measurement))
    capture = cv2.VideoCapture(str(source), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 2])
    if not capture.isOpened():
        raise ValueError(f'Cannot decode source {source}')
    previous = None
    try:
        for index in range(max(by_frame, default=-1) + 1):
            ok, frame = capture.read()
            if not ok:
                raise ValueError(f'Source truncated at {index}: {source}')
            if frame.shape[:2] != (height, width):
                raise ValueError(f'Source resolution differs from scorecard: {source}')
            gray = cv2.cvtColor(cv2.resize(frame, (320, max(2, round(320 * height / width)))), cv2.COLOR_BGR2GRAY)
            shift, response = (0., 0.), 0.
            if previous is not None and index in by_frame:
                shift, response = cv2.phaseCorrelate(previous.astype(np.float32), gray.astype(np.float32))
            pan = float(np.hypot(shift[0] * width / gray.shape[1], shift[1] * height / gray.shape[0]))
            for item, measurement in by_frame[index]:
                x0, y0, x1, y1 = measurement['raster_roi']
                roi = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
                variance = float(cv2.Laplacian(roi, cv2.CV_64F).var())
                measurement.update({'input_roi_laplacian_variance': variance,
                                    'phase_translation_px': pan, 'phase_response': float(response)})
                attributes = set(item['attributes'])
                if variance < blur_threshold:
                    attributes.add('low-sharpness/blur-candidate')
                if response >= .5 and pan >= 8:
                    attributes.add('fast-pan-candidate')
                if variance < blur_threshold and (response >= .5 and pan >= 8 or
                        measurement['target_speed_px_per_frame'] >= max(8., .5 * measurement['height_px'])):
                    attributes.add('motion-blur-candidate')
                item['attributes'] = sorted(attributes)
            previous = gray
    finally:
        capture.release()


def choose_representatives(items, limit):
    selected, seen = [], set()
    for clip in dict.fromkeys(item['clip'] for item in items):
        candidates = [item for item in items if item['clip'] == clip]
        selected.append(min(candidates, key=lambda item: item['minimum_coverage_fraction']))
    for cause in dict.fromkeys(item['primary_cause'] for item in items):
        candidates = [item for item in items if item['primary_cause'] == cause and item not in selected]
        if candidates:
            selected.append(candidates[0])
    for attribute in ['small-text/distance-unproven', 'edge-entry-candidate', 'motion-blur-candidate', 'fast-pan-candidate']:
        candidates = [item for item in items if attribute in item['attributes'] and item not in selected]
        if candidates:
            selected.append(candidates[0])
    result = []
    for item in selected:
        key = (item['clip'], item['text'])
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result[:limit]


def make_images(items, contexts, directory, limit):
    tiles, representatives = [], []
    for number, item in enumerate(choose_representatives(items, limit)):
        context = contexts[item['variant']]
        index = item['representative_frame']
        images = []
        for path in [context['source'], context['output']]:
            capture = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 2])
            try:
                if not capture.set(cv2.CAP_PROP_POS_FRAMES, index):
                    raise ValueError(f'Cannot seek representative frame {index}: {path}')
                ok, frame = capture.read()
                if not ok:
                    raise ValueError(f'Cannot read representative frame {index}: {path}')
                images.append(frame)
            finally:
                capture.release()
        mask = context['masks'].get(index)
        measurement = next(value for value in item['frames'] if value['frame'] == index)
        box = measurement['box']
        margin = max(12., (box[3] - box[1]) * 2, (box[2] - box[0]) * .2)
        x0, y0, x1, y1 = region([box[0] - margin, box[1] - margin, box[2] + margin, box[3] + margin],
                                images[0].shape[1], images[0].shape[0])
        panel = np.full((220, 960, 3), 235, np.uint8)
        title = f'{number:02d} {item["variant"]} track{item["track_id"]} frame{index} h={measurement["height_px"]:.1f} cover={measurement["coverage_fraction"]:.3f}'
        cv2.putText(panel, title[:130], (6, 15), cv2.FONT_HERSHEY_SIMPLEX, .39, (0, 0, 0), 1)
        cv2.putText(panel, item['primary_cause'] + ' | ' + item['text'][:70], (6, 33), cv2.FONT_HERSHEY_SIMPLEX, .36, (0, 0, 0), 1)
        for column, image in enumerate([*images, cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)]):
            crop = image[y0:y1, x0:x1].copy()
            cv2.rectangle(crop, (round(box[0] - x0), round(box[1] - y0)),
                          (round(box[2] - x0), round(box[3] - y0)), (0, 180, 255), 1)
            panel[40:220, column * 320:(column + 1) * 320] = cv2.resize(crop, (320, 180), interpolation=cv2.INTER_NEAREST)
        path = directory / f'representative-{number:02d}.png'
        if not cv2.imwrite(str(path), panel):
            raise RuntimeError(f'Cannot save {path}')
        tiles.append(panel)
        representatives.append({'id': item['id'], 'image': str(path), 'frame': index,
                                'columns': ['input', 'encoded output', 'actual/reconstructed mask']})
    if tiles:
        if len(tiles) % 2:
            tiles.append(np.full_like(tiles[0], 235))
        sheet = np.vstack([np.hstack(tiles[index:index + 2]) for index in range(0, len(tiles), 2)])
        if not cv2.imwrite(str(directory / 'contact-sheet.png'), sheet):
            raise RuntimeError('Cannot save contact sheet')
    return representatives


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scorecard', type=Path)
    parser.add_argument('--media-root', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--geometry-only', action='store_true', help='Fast mask/box counts; omit photometric attributes and images')
    parser.add_argument('--small-height', type=float, default=16.)
    parser.add_argument('--blur-threshold', type=float, default=80.)
    parser.add_argument('--representatives', type=int, default=10)
    args = parser.parse_args(argv)
    if (not math.isfinite(args.small_height) or args.small_height <= 0
            or not math.isfinite(args.blur_threshold) or args.blur_threshold < 0 or args.representatives < 0):
        parser.error('Height must be positive, blur threshold nonnegative, and all thresholds finite')
    cv2.setNumThreads(2)
    card = json.loads(args.scorecard.read_text())
    media = args.media_root or Path(card.get('evidence_base', args.scorecard.parent))
    args.out.mkdir(parents=True, exist_ok=True)
    items, contexts, counts = [], {}, []
    try:
        for row in card['clips']:
            label = row['clip'] + ('-synthetic' if row['synthetic_variant'] else '-natural')
            if label in contexts:
                raise ValueError(f'Duplicate clip variant: {label}')
            evidence_path = args.scorecard.parent / f'{label}-masked.evidence.json'
            evidence = json.loads(evidence_path.read_text())
            output = media / f'{label}-masked.mp4'
            source = media / f'{label}-input.mp4'
            records = json.loads(output.with_suffix('.masks.json').read_text())
            width, height = row['performance']['resolution']
            if len(records) != len(evidence['output_readings']) or any(record['frame'] != index for index, record in enumerate(records)):
                raise ValueError(f'Frame accounting differs for {label}')
            tracks = evidence['natural']
            failed = [track for track in tracks if track['leaked']]
            if (len(tracks) != row['natural']['total'] or len(tracks) - len(failed) != row['natural']['hidden']
                    or not row['real_video_pass']):
                raise ValueError(f'Interval/guard accounting differs for {label}; this tool requires real-video-pass runs')
            masks = Masks(output, records, (height, width), card['options'])
            context = {'source': source, 'output': output, 'masks': masks}
            contexts[label] = context
            variant_items = []
            for track in failed:
                analysis = classify_geometry(track, records, masks, width, height, card['options'], args.small_height)
                item = {'id': f'{label}:{track["id"]}', 'clip': row['clip'], 'variant': label,
                        'synthetic_variant': row['synthetic_variant'], 'track_id': track['id'],
                        'text': track['text'], 'first': track['first'], 'last': track['last'],
                        'observations': len(track['observations']), 'mask_origin': masks.origin,
                        'evidence': str(evidence_path), **analysis}
                items.append(item)
                variant_items.append(item)
            observed_coverage(variant_items, failed, masks, width, height)
            counts.append({'clip': row['clip'], 'variant': label, 'natural': row['natural'],
                           'excluded_unstable_natural': len(evidence.get('excluded_unstable_natural', [])),
                           'synthetic': row['synthetic'], 'geometry_summary': summarize(variant_items)})
        expected = card['natural']['total'] - card['natural']['hidden']
        if len(items) != expected or sum(row['natural']['total'] for row in counts) != card['natural']['total']:
            raise ValueError('Aggregate natural counts do not reconcile with the scorecard')
        print(json.dumps({'stage': 'geometry', 'natural': card['natural'], 'overall': summarize(items)}, indent=2), flush=True)
        if not args.geometry_only:
            for label, context in contexts.items():
                subset = [item for item in items if item['variant'] == label]
                if subset:
                    width, height = next(row['performance']['resolution'] for row in card['clips']
                                         if row['clip'] + ('-synthetic' if row['synthetic_variant'] else '-natural') == label)
                    annotate_video(context['source'], subset, width, height, args.blur_threshold)
                    print(json.dumps({'stage': 'photometric', 'variant': label,
                                      'failed_intervals': len(subset)}), flush=True)
        by_clip = []
        for clip in dict.fromkeys(row['clip'] for row in counts):
            clip_rows = [row for row in counts if row['clip'] == clip]
            by_clip.append({'clip': clip, 'natural_total': sum(row['natural']['total'] for row in clip_rows),
                            'natural_hidden': sum(row['natural']['hidden'] for row in clip_rows),
                            **summarize([item for item in items if item['clip'] == clip])})
        representatives = [] if args.geometry_only else make_images(items, contexts, args.out, args.representatives)
        report = {'schema_version': 1, 'benchmark_only': True, 'demo_ready': False,
                  'scorecard': str(args.scorecard), 'scorecard_sha256': hashlib.sha256(args.scorecard.read_bytes()).hexdigest(),
                  'options': card['options'], 'mode': 'geometry-only' if args.geometry_only else 'geometry-and-photometric',
                  'natural': card['natural'], 'synthetic': card['synthetic'], 'overall': summarize(items),
                  'per_clip': by_clip, 'per_variant': counts, 'intervals': items, 'representatives': representatives,
                  'thresholds': {'small_height_px': args.small_height, 'edge_fraction': .02,
                                 'entry_frames_from_first_OCR': 3, 'target_motion_px_per_frame': 'max(8, .5*height)',
                                 'Laplacian_variance': args.blur_threshold, 'phase_response': .5, 'fast_pan_px_per_frame': 8},
                  'confidence': {'primary': 'automatic mask/box geometry; OCR truth and interpolation can be wrong',
                                 'attributes': 'nonexclusive heuristics, not causal/manual ground truth'},
                  'limits': ['Natural content repeats across natural/synthetic variants; intervals are not unique physical signs.',
                             'Distance, motion blur, physical entry, and target motion are hypotheses; OCR boxes can jitter.',
                             'No new OCR/detection; no timing miss inferred from a synchronous stride1 detector miss.',
                             'Historical AABB masks are reconstructed exactly and checked against saved mask area.',
                             'Whole-box coverage is not glyph coverage; full coverage with an OCR leak needs manual review.']}
        (args.out / 'taxonomy.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'report': str(args.out / 'taxonomy.json'), 'overall': report['overall'], 'per_clip': by_clip}, indent=2), flush=True)
        return report
    finally:
        for context in contexts.values():
            context['masks'].close()


if __name__ == '__main__':
    main()

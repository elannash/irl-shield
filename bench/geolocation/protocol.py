"""Preregistration, exact paired inputs, and aggregate-only scoring."""
import hashlib
import json
import math
from pathlib import Path
import statistics
import struct


TUNE_IDS = frozenset(('sf-market', 'ljubljana-walk', 'ljubljana-traffic',
                      'london-croydon', 'london-bus-pov', 'illinois-night',
                      'mazatlan-aquiles'))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def coordinate(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError('Expected [latitude, longitude]')
    if any(type(x) not in (float, int) or not math.isfinite(x) for x in value):
        raise ValueError('Coordinates must be finite numbers')
    if not -90 <= value[0] <= 90 or not -180 <= value[1] <= 180:
        raise ValueError('Coordinates outside geographic range')
    return value


def distance_km(first, second):
    lat1, lon1 = map(math.radians, coordinate(first))
    lat2, lon2 = map(math.radians, coordinate(second))
    a = math.sin((lat2 - lat1) / 2) ** 2
    a += math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1., max(0., a))))


def registration(path):
    data = read_json(path)
    samples = data['samples']
    ids = [sample['id'] for sample in samples]
    if not ids or len(set(ids)) != len(ids) or set(ids) - TUNE_IDS:
        raise ValueError('Only unique preregistered tune samples are allowed')
    if data['sample_n'] != len(samples):
        raise ValueError('Preregistered sample denominator does not match')
    if data['top_k'] != [1, 5] or data['thresholds_km'] != [1, 25, 200, 750, 2500]:
        raise ValueError('Unexpected preregistered metric definition')
    for sample in samples:
        coordinate(sample['ground_truth']['coordinate'])
        uncertainty = sample['ground_truth']['uncertainty_km']
        if type(uncertainty) not in (int, float) or not math.isfinite(uncertainty) or uncertainty < 0:
            raise ValueError('Invalid ground-truth uncertainty')
        if type(sample['frame_index']) is not int or sample['frame_index'] < 0:
            raise ValueError('Invalid source-frame index')
    return data


def verify_artifact(root, artifact):
    path = root / artifact['path']
    if sha256(path) != artifact['sha256']:
        raise ValueError('Artifact hash mismatch: ' + artifact['path'])
    return path


def png_size(path):
    # This checks the container only; it neither decodes nor displays pixels.
    with path.open('rb') as stream:
        header = stream.read(24)
    if len(header) != 24 or header[:16] != b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR':
        raise ValueError('Paired frames must be lossless PNGs')
    return struct.unpack('>II', header[16:24])


def freeze(preregistration_path, pairs_path, root, output):
    """Bind exporter evidence before predictions; never manufacture a mask."""
    data = registration(preregistration_path)
    pairs = read_json(pairs_path)
    root = Path(root)
    for key in ('policy', 'exporter', 'source_receipt'):
        verify_artifact(root, pairs[key])
    actual = pairs['pairs']
    if len(actual) != len(data['samples']) or len({p['id'] for p in actual}) != len(actual):
        raise ValueError('Exactly one raw/shielded pair per registered sample is required')
    actual = {pair['id']: pair for pair in actual}
    if set(actual) != {s['id'] for s in data['samples']}:
        raise ValueError('Pair selection differs from preregistration')
    for sample in data['samples']:
        pair = actual[sample['id']]
        if (pair['frame_index'] != sample['frame_index']
                or pair['source_clip_sha256'] != sample['source_clip_sha256']
                or pair['shield_source_index'] != sample['frame_index']):
            raise ValueError('Raw/shielded source alignment differs from preregistration')
        if pair['slate'] is not False or pair['real_video'] is not True:
            raise ValueError('Slate/non-video output cannot establish geolocation protection')
        raw = verify_artifact(root, pair['raw'])
        shielded = verify_artifact(root, pair['shielded'])
        if png_size(raw) != (1280, 720) or png_size(raw) != png_size(shielded):
            raise ValueError('Paired frame geometry differs from prepared tune clips')
    plan = {'schema_version': 1, 'preregistration_sha256': sha256(preregistration_path),
            'pairs_sha256': sha256(pairs_path), 'pairs': pairs,
            'notice': 'Exporter provenance is asserted by its producer; hashes bind bytes, not correctness.'}
    write_new(output, plan)
    return plan


def verify_plan(plan_path, preregistration_path, root):
    plan = read_json(plan_path)
    if plan['preregistration_sha256'] != sha256(preregistration_path):
        raise ValueError('Preregistration changed after input freeze')
    pairs = plan['pairs']
    for key in ('policy', 'exporter', 'source_receipt'):
        verify_artifact(Path(root), pairs[key])
    for pair in pairs['pairs']:
        for arm in ('raw', 'shielded'):
            verify_artifact(Path(root), pair[arm])
    return plan


def aggregate(preregistration_path, plan_path, results_path):
    """Publish no sample IDs, paths, coordinates, candidate names, or scores."""
    data = registration(preregistration_path)
    plan = read_json(plan_path)
    result = read_json(results_path)
    if (plan['preregistration_sha256'] != sha256(preregistration_path)
            or result['plan_sha256'] != sha256(plan_path)
            or result['model_manifest_sha256'] != data['model_manifest_sha256']):
        raise ValueError('Results do not bind to the frozen experiment')
    rows = result['rows']
    expected = {(s['id'], arm) for s in data['samples'] for arm in ('raw', 'shielded')}
    observed = [(r['id'], r['arm']) for r in rows]
    if len(set(observed)) != len(observed) or set(observed) != expected:
        raise ValueError('Missing, extra, or duplicate paired prediction rows')
    pairs = {p['id']: p for p in plan['pairs']['pairs']}
    for row in rows:
        if row['frame_sha256'] != pairs[row['id']][row['arm']]['sha256']:
            raise ValueError('Prediction frame hash differs from the frozen pair')
    lookup = {(r['id'], r['arm']): r for r in rows}
    complete = all(r['status'] == 'ok' for r in rows)
    arms = {}
    for arm in ('raw', 'shielded'):
        errors = []
        hits = {f'top{k}_within_{threshold}km': [0, 0]
                for k in data['top_k'] for threshold in data['thresholds_km']}
        failures = 0
        for sample in data['samples']:
            row = lookup[sample['id'], arm]
            if row['status'] == 'failed':
                failures += 1
                for counts in hits.values():
                    counts[1] += 1
                continue
            if row['status'] != 'ok' or len(row['candidates']) != max(data['top_k']):
                raise ValueError('Invalid prediction status or top-k truncation')
            candidates = row['candidates']
            if len({tuple(coordinate(p)) for p in candidates}) != len(candidates):
                raise ValueError('Duplicate geographic candidates in ranked result')
            distances = [distance_km(sample['ground_truth']['coordinate'], p) for p in candidates]
            errors.append(distances[0])
            uncertainty = sample['ground_truth']['uncertainty_km']
            for k in data['top_k']:
                nearest = min(distances[:k])
                for threshold in data['thresholds_km']:
                    counts = hits[f'top{k}_within_{threshold}km']
                    counts[0] += int(nearest + uncertainty <= threshold)
                    counts[1] += int(max(0., nearest - uncertainty) <= threshold)
        n = data['sample_n']
        arms[arm] = {'attempted_n': n, 'successful_n': len(errors), 'failed_n': failures,
                     'median_top1_distance_km': statistics.median(errors) if complete else None,
                     'mean_top1_distance_km': statistics.mean(errors) if complete else None,
                     'hit_rate_bounds': {key: {'definite': low / n, 'possible': high / n}
                                         for key, (low, high) in hits.items()}}
    return {'schema_version': 1, 'status': 'complete' if complete else 'incomplete',
            'sample_n': data['sample_n'], 'split': 'tune', 'arms': arms,
            'primary': {'metric': 'top1_within_25km',
                        'raw': arms['raw']['hit_rate_bounds']['top1_within_25km'] if complete else None,
                        'shielded': arms['shielded']['hit_rate_bounds']['top1_within_25km'] if complete else None},
            'limitations': data['limitations'],
            'plan_sha256': sha256(plan_path), 'results_sha256': sha256(results_path)}

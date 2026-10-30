"""Validate archive identities before opening any public BEFORE pixels."""
import base64
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import zlib

import numpy as np


class EvidenceError(ValueError):
    """Evidence is incomplete, inconsistent, or unsafe for a public comparison."""


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def require(condition, message):
    if not condition:
        raise EvidenceError(message)


def number(value, name):
    require(type(value) in (int, float) and math.isfinite(value), f'Invalid {name}')
    return float(value)


def integer(value, name):
    require(type(value) is int and value >= 0, f'Invalid {name}')
    return value


def rational(value):
    require(isinstance(value, str), 'PTS must be an exact rational string')
    try:
        result = Fraction(value)
    except (ValueError, ZeroDivisionError):
        raise EvidenceError('Invalid rational PTS') from None
    require(result >= 0, 'Negative PTS')
    return result


def local_file(root, name):
    require(isinstance(name, str) and name and not Path(name).is_absolute(), 'Expected relative file path')
    path = (root / name).resolve()
    require(path.is_relative_to(root.resolve()) and path.is_file(), 'File is missing or escapes evidence directory')
    return path


def identity(row):
    return (integer(row['egress_generation'], 'egress generation'), integer(row['index'], 'frame index'))


def json_file(path):
    try:
        return json.loads(path.read_text())
    except (ValueError, UnicodeError):
        raise EvidenceError('Invalid evidence JSON') from None


def unpack_mask(row):
    shape = row['mask_shape']
    require(isinstance(shape, list) and len(shape) == 2, 'Invalid mask shape')
    h, w = (integer(n, 'mask dimension') for n in shape)
    require(0 < h <= 4320 and 0 < w <= 7680, 'Unsupported mask dimensions')
    size = (h * w + 7) // 8
    try:
        compressed = base64.b64decode(row['mask_packbits_zlib_base64'], validate=True)
        decoder = zlib.decompressobj()
        data = decoder.decompress(compressed, size + 1)
        require(decoder.eof and not decoder.unused_data and len(data) == size, 'Invalid packed mask length')
    except (ValueError, zlib.error):
        raise EvidenceError('Invalid packed mask') from None
    mask = np.unpackbits(np.frombuffer(data, np.uint8))[:h*w].reshape(h, w) * np.uint8(255)
    require(hashlib.sha256(mask.tobytes()).hexdigest() == row['mask_sha256'], 'Mask hash mismatch')
    return mask


@dataclass
class Evidence:
    archive: Path
    source_root: Path
    manifest_hash: str
    provenance: dict
    sidecar: dict
    rows: list
    mask_shapes: list
    timeline: list


def load_evidence(archive, manifest, manifest_hash):
    """Hashes are an integrity pin, not a substitute for provenance review."""
    try:
        return _load(Path(archive), Path(manifest), manifest_hash)
    except (KeyError, TypeError, IndexError) as error:
        raise EvidenceError(f'Missing or malformed evidence field: {error}') from None


def _load(archive, manifest, manifest_hash):
    require(sha256(manifest) == manifest_hash, 'Synthetic source manifest hash mismatch')
    provenance = json_file(manifest)
    require(provenance['schema'] == 'irl-shield-demo-source-v1', 'Unsupported source schema')
    require(provenance['origin'] == 'wholly-synthetic' and provenance['demo_ready'] is True,
            'Public BEFORE requires wholly-synthetic demo_ready provenance')
    require(provenance['license'] in ('CC0-1.0', 'CC-BY-4.0', 'public-domain'), 'Unsupported source license')
    review = provenance['public_asset_review']
    require(all(review[key] is True for key in ('no_real_people', 'no_brands_or_logos', 'no_music', 'fictional_text_only')),
            'Public asset review is incomplete')
    require(isinstance(review['reviewer'], str) and review['reviewer'].strip(), 'Missing asset reviewer')
    source_root = manifest.parent
    raw = local_file(source_root, provenance['video']['file'])
    require(sha256(raw) == provenance['video']['sha256'], 'Raw video hash mismatch')
    sidecar = json_file(archive / 'demo-evidence.json')
    require(sidecar['schema'] == 'irl-shield-demo-evidence-v1', 'Unsupported sidecar schema')
    require(sidecar['source_manifest_sha256'] == manifest_hash, 'Archive/source mismatch')
    require(sidecar['evidence_kind'] in ('synthetic-test', 'measured-native'), 'Unknown evidence kind')
    require(sidecar['execution_mode'] in ('offline', 'real-time'), 'Unknown execution mode')
    require(sidecar['evidence_kind'] != 'synthetic-test' or sidecar['execution_mode'] == 'offline',
            'Synthetic test cannot claim real-time execution')
    require(sha256(archive / 'frames.jsonl') == sidecar['frames_sha256'], 'Archive frame manifest hash mismatch')
    require(sidecar['encoded_files'], 'Missing encoded media pins')
    for name, digest in sidecar['encoded_files'].items():
        require(sha256(local_file(archive, name)) == digest, 'Encoded archive hash mismatch')
    rows = [json.loads(line) for line in (archive / 'frames.jsonl').read_text().splitlines()]
    frames = sidecar['frames']
    sources = provenance['frames']
    require(rows and len(rows) == len(frames), 'Archive/frame map count mismatch')
    fps = rational(provenance['fps'])
    require(0 < fps <= 120, 'Unsupported source frame rate')
    source_by_index = {integer(f['index'], 'source index'): f for f in sources}
    require(len(source_by_index) == len(sources), 'Duplicate source index')
    receipts = {r['id']: r for r in sidecar['detections']}
    require(len(receipts) == len(sidecar['detections']), 'Duplicate detector receipt')
    origin = number(sidecar['capture_origin_monotonic'], 'capture origin')
    require(sources, 'Missing source frames')
    # Original source PTS can start at any offset. They never define engine indices.
    captures = {f['source_index']: number(f['captured_at_monotonic'], 'capture time') for f in frames}
    require(len(captures) == len(frames), 'Duplicate source capture identity')
    require(sources[0]['index'] in captures and abs(captures[sources[0]['index']] - origin) <= 1e-6,
            'Capture origin mismatch')
    previous_source = None
    for source in sources:
        pair = (integer(source['index'], 'source index'), rational(source['pts']))
        require(previous_source is None or (pair[0] > previous_source[0] and pair[1] > previous_source[1]),
                'Source frame order is not strictly increasing')
        previous_source = pair
    for receipt in receipts.values():
        require(isinstance(receipt['id'], str) and receipt['id'], 'Invalid detector receipt ID')
        require(receipt['lane'] in ('fast', 'accurate'), 'Unknown detector lane')
        require(receipt['status'] == 'ok', 'Failed detector receipt')
        require(receipt['source_index'] in source_by_index and receipt['source_index'] in captures,
                'Detector source frame missing')
        require(isinstance(receipt['quads'], list), 'Missing detector geometry')
        for quad in receipt['quads']:
            points = np.asarray(quad, dtype=float)
            require(points.shape == (4, 2) and np.isfinite(points).all(), 'Invalid detector geometry')
        completed = number(receipt['completed_at_monotonic'], 'detector confirmation')
        require(completed >= captures[receipt['source_index']],
                'Detector confirmation precedes its source capture')
    mask_shapes, timeline, seen, encoded_seen = [], [], set(), set()
    previous_capture = previous_pts = None
    for row, frame in zip(rows, frames, strict=True):
        key = identity(row)
        require(key not in seen, 'Duplicate archive identity')
        seen.add(key)
        require(key == identity(frame), 'Archive frame identity mismatch')
        require(frame['source_index'] == row['index'], 'Source/engine index mismatch')
        source = source_by_index[frame['source_index']]
        pts = rational(source['pts'])
        require(abs(number(row['pts'], 'archive source PTS') - float(pts)) <= 1e-9, 'Source PTS mismatch')
        capture = number(frame['captured_at_monotonic'], 'capture time')
        require(capture >= origin, 'Capture precedes origin')
        require(previous_capture is None or capture > previous_capture, 'Capture time regression')
        require(previous_pts is None or pts > previous_pts, 'Source PTS regression')
        previous_capture, previous_pts = capture, pts
        deadline = number(row['deadline'], 'presentation deadline')
        presented = number(row['presented_at'], 'presentation time')
        require(capture <= deadline <= presented, 'Invalid capture/deadline/presentation ordering')
        encoded_name = 'encoded.flv' if key[0] == 1 else f'encoded-g{key[0]:04d}.flv'
        require(frame['encoded_file'] == encoded_name and encoded_name in sidecar['encoded_files'],
                'Archive generation media mismatch')
        encoded_key = (encoded_name, rational(frame['encoded_pts']))
        require(encoded_key not in encoded_seen, 'Duplicate encoded PTS identity')
        encoded_seen.add(encoded_key)
        mask = unpack_mask(row)
        mask_shapes.append(mask.shape)
        applied = frame['applied_receipt_ids']
        require(isinstance(applied, list) and len(applied) == len(set(applied)), 'Invalid applied receipts')
        require(all(r in receipts for r in applied), 'Missing detector receipt')
        require(row['state'] in ('LIVE', 'PROTECT', 'HOLD'), 'Unknown archive state')
        require(type(row['slate']) is bool and type(row['protected']) is bool, 'Invalid protection flags')
        active = bool(mask.any())
        if active and row['state'] == 'LIVE':
            require(applied and any(receipts[r]['quads'] for r in applied), 'Masked LIVE frame lacks detector receipt')
        require(not applied or active, 'Detector paint has no actual mask')
        for receipt_id in applied:
            receipt = receipts[receipt_id]
            require(receipt['quads'], 'Applied detector receipt has no geometry')
            require(receipt['completed_at_monotonic'] <= deadline, 'Detector confirmation misses frame deadline')
        backward = [r for r in applied if receipts[r]['source_index'] > frame['source_index']]
        timeline.append({'index': key[1], 'egress_generation': key[0], 'source_pts': str(pts),
                         'capture_seconds': capture-origin, 'deadline_seconds': deadline-origin,
                         'presented_seconds': presented-origin, 'masked': active,
                         'backward_receipt_ids': backward, 'applied_receipt_ids': applied,
                         'state': row['state'], 'slate': row['slate']})
    return Evidence(archive, source_root, manifest_hash, provenance, sidecar, rows, mask_shapes, timeline)

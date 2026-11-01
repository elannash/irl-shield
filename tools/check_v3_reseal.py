#!/usr/bin/env python3
"""Assert that v3's re-seal changes only code identity and its dependent hash.

This is a metadata/hash check. It never decodes media or imports native code.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_PLAN = '81a12ac87818497a1fd3b2a0928bf7610b0200b256bfee4296fde95816e4db9d'
ORIGINAL_MANIFEST = '700a7730111cf6e2b87a46ef0fac9721c3410dba10ee85dd38b75b96d036ff2b'
SELECTION = '0dbb14bb2da57364c6b1ca131c29619e9270297298abb4222aa277d633c5f1df'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check(cache_root=None):
    directory = ROOT / 'fixtures/fresh-heldout-v3'
    original_path = directory / 'preparation-plan.json'
    if digest(original_path) != ORIGINAL_PLAN or digest(directory / 'selection.json') != SELECTION:
        raise ValueError('Original v3 plan or selection differs from 738b738')
    original = json.loads(original_path.read_text())
    plan = json.loads((directory / 'plan.json').read_text())
    manifest = json.loads((directory / 'manifest.json').read_text())
    if dict(plan, code_identity=original['code_identity']) != original:
        raise ValueError('V3 plan changed outside code_identity')
    if manifest['code_identity'] != plan['code_identity'] or manifest['plan_sha256'] != digest(directory / 'plan.json'):
        raise ValueError('V3 re-seal identity or dependent hash differs')
    prior = dict(manifest, code_identity=original['code_identity'], plan_sha256=ORIGINAL_PLAN)
    prior_bytes = (json.dumps(prior, indent=2, allow_nan=False) + '\n').encode()
    if hashlib.sha256(prior_bytes).hexdigest() != ORIGINAL_MANIFEST:
        raise ValueError('V3 manifest changed outside code_identity and dependent hashes')
    rows = manifest['inputs']
    if len(rows) != 6 or len({row['source_sha256'] for row in rows}) != 6:
        raise ValueError('V3 re-seal requires the six original distinct inputs')
    checked = []
    if cache_root is not None:
        base = Path(cache_root).resolve(strict=True)
        prefix = 'fixtures/cache/fresh-heldout-v3/'
        for row in rows:
            relative = row['source'].removeprefix(prefix)
            if not row['source'].startswith(prefix) or Path(relative).name != relative:
                raise ValueError('Invalid v3 input path')
            path = base / relative
            if path.is_symlink() or not path.is_file() or digest(path) != row['source_sha256']:
                raise ValueError('V3 input bytes differ: ' + relative)
            checked.append({'source': row['source'], 'sha256': row['source_sha256'], 'bytes': path.stat().st_size})
    return {'original_seal_commit': '738b738', 'selection_sha256': SELECTION,
            'selection_unchanged': True, 'input_hashes_unchanged': 6,
            'all_other_manifest_fields_unchanged': True,
            'original_plan_sha256': ORIGINAL_PLAN, 'original_manifest_sha256': ORIGINAL_MANIFEST,
            'new_plan_sha256': digest(directory / 'plan.json'),
            'new_manifest_sha256': digest(directory / 'manifest.json'),
            'reservation': manifest['evaluation_reservation'],
            'payloads_hash_checked': checked, 'decoded_frames': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-root', type=Path, help='Optional explicit cache; hash six inputs without decoding')
    args = parser.parse_args()
    print(json.dumps(check(args.cache_root), indent=2))

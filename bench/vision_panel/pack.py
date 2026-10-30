"""Trusted event-card sealing, with no detector, renderer or external dispatch."""
from collections import Counter
from pathlib import Path
import random
import shutil

from .media import normalize_check
from .protocol import (VERSION, code_hash, digest, document_digest, keys,
                       load, number, require, text, token, verify_card, write_once)

SPENT_V1_SHA256 = '46a4461ca50ac54a4cac564ad81e1bba5c2d990b0cb9976eb473a82e5fcc3cad'
LICENSES = ('CC0', 'CC BY 3.0', 'CC BY 4.0', 'Public domain')
CONTROLS = ('readable_leak', 'removed_target', 'utility_failure', 'generic_context')
TUNE_CLIPS = ('sf-market', 'ljubljana-walk', 'ljubljana-traffic', 'london-croydon',
              'london-bus-pov', 'illinois-night', 'mazatlan-aquiles')


def receipt(ref):
    keys(ref, ('path', 'sha256'))
    p = Path(ref['path'])
    require(p.is_absolute() and p.is_file() and not p.is_symlink(), 'absolute regular receipt required')
    require(digest(p) == ref['sha256'], 'source/hash drift: ' + str(p))
    return p


def strings(value):
    if isinstance(value, dict):
        for k, v in value.items():
            yield str(k)
            yield from strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)
    elif isinstance(value, str):
        yield value


def access_policy(plan):
    """Pure first pass. No receipt/media hash or open precedes these checks."""
    values = [s.lower().replace('_', '-') for s in strings(plan)]
    require(not any('owner-real' in s or 'owner-derived' in s for s in values), 'owner alias forbidden before media/hash access')
    for item in plan.get('items', []):
        s = item['source']
        require(s['origin'] in ('licensed_fixture', 'synthetic_context'), 'owner/unknown origin forbidden before media/hash access')
        require(s['license'] in LICENSES, 'unlicensed source')
        require(s['media_role'] in ('processed', 'raw'), 'media role')
        require(s['media_role'] != 'raw' or item['control'] == 'readable_leak' and
                s['origin'] == 'licensed_fixture' and s['variant'] == 'natural', 'raw traps require natural licensed frames before receipts')
        require(s['variant'] == 'natural' or item['control'] == 'generic_context' and
                s['origin'] == 'synthetic_context', 'synthetic overlays excluded from effectiveness/controls')
        kind = s['dataset_kind']
        if kind == 'spent-v1':
            require(s['dataset_sha256'] == SPENT_V1_SHA256 and plan['phase'] == 'locked', 'spent-v1 exact reserved dev dataset required')
        elif kind == 'fresh-v2':
            auth = plan.get('one_shot')
            require(plan['phase'] == 'final' and isinstance(auth, dict) and
                    auth.get('status') == 'FINAL_FROZEN_ONE_SHOT' and auth.get('root_authorized') is True and
                    auth.get('policy_sha256') == s['policy_sha256'] and
                    auth.get('dataset_sha256') == s['dataset_sha256'] and auth.get('receipt') is not None,
                    'fresh-v2 forbidden without frozen ONE_SHOT/root/policy binding')
        else:
            require(kind == 'tune' or kind == 'synthetic-control' and item['control'] == 'generic_context', 'unknown dataset')
        source_paths = [v.lower() for v in strings(item) if '/' in v]
        require(not any(('fresh-v2' in p and kind != 'fresh-v2') or ('fresh-heldout' in p and kind != 'fresh-v2' and not (kind == 'spent-v1' and s['dataset_sha256'] == SPENT_V1_SHA256 and plan['phase'] == 'locked')) for p in source_paths), 'fresh source path cannot bypass dataset binding')


def qualify(item):
    s = item['source']
    provenance = load(receipt(s['receipt']))
    for k in ('origin', 'clip', 'event', 'dataset_kind', 'dataset_sha256', 'license', 'variant',
              'media_role', 'source_sha256', 'policy_sha256', 'output_sha256'):
        require(provenance[k] == s[k], 'source provenance differs: ' + k)
    require(provenance['license_verified'] is True and provenance['source_allocation_verified'] is True, 'license/split not verified')
    if item['control'] is None:
        q = load(receipt(item['qualification']))
        require(q['status'] == 'LOCALLY_QUALIFIED' and q['policy_sha256'] == s['policy_sha256'] and
                q['output_sha256'] == s['output_sha256'] and q['source_sha256'] == s['source_sha256'], 'MISSING_INPUTS: exact locally qualified W1 bindings')
        require(q['ocr_pass'] is True and q['runtime_pass'] is True and q['real_video_pass'] is True and
                q['geoclip_frozen'] is True and q['geoclip_no_new_success'] is True, 'local guard failure')
        number(q['area_ceiling'], 0, .15)
        require(q['area_guard_pass'] is True and isinstance(q['area_aggregation'], str) and bool(q['area_aggregation']), 'area aggregation missing')
        number(q['delay_seconds'], 1, 3)
        require(q['runtime_receipt'] is not None and q['ocr_receipt'] is not None and q['geoclip_receipt'] is not None, 'missing local instrument receipts')
        for name in ('runtime_receipt', 'ocr_receipt', 'geoclip_receipt'):
            receipt(q[name])
    output = load(receipt(item['extraction']))
    require(output['output_sha256'] == s['output_sha256'], 'extraction/output binding')
    require(output['fps'] == item['fps'] and output['frame_start'] == item['frame_start'] and
            output['frame_count'] == item['frame_count'], 'extraction frame extent differs')
    require(output['frames'] == [{k: f[k] for k in ('timestamp', 'sha256')} for f in item['frames']] and
            output['crops'] == [{k: f[k] for k in ('timestamp', 'bbox', 'sha256')} for f in item['crops']], 'extraction receipt differs')


def validate_plan(plan):
    keys(plan, ('version', 'phase', 'status', 'items', 'events', 'controls', 'one_shot', 'local_before', 'selection_rules'))
    require(plan['version'] == VERSION and plan['phase'] in ('pilot', 'extension', 'locked', 'checkpoints', 'final'), 'plan version/phase')
    access_policy(plan)
    if plan['status'] == 'MISSING_INPUTS':
        return {'status': 'MISSING_INPUTS', 'missing': ['root-qualified incumbent/challenger policy and rendered output receipts',
                '12 exact source-event/timestamp/crop bindings across seven tune clips', 'four locally validated control receipts',
                'frozen OCR/area/runtime/GeoCLIP before-decision record'], 'cards_generated': 0}
    require(plan['status'] == 'READY', 'plan status')
    require(isinstance(plan['selection_rules'], str) and bool(plan['selection_rules']), 'frozen event selection rules required')
    require(isinstance(plan['items'], list) and 1 <= len(plan['items']) <= 44, 'item count')
    items = {}
    for i in plan['items']:
        keys(i, ('key', 'event', 'role', 'source', 'qualification', 'extraction', 'frames', 'crops',
                 'fps', 'frame_start', 'frame_count', 'control'))
        text(i['key'], 100); require(i['key'] not in items, 'duplicate item key')
        require(i['role'] in ('incumbent', 'challenger', 'control', 'single'), 'item role')
        require(i['control'] is None or i['control'] in CONTROLS, 'control kind')
        require((i['role'] == 'control') == (i['control'] is not None), 'control role mismatch')
        number(i['fps'], 1, 120)
        require(type(i['frame_count']) is int and i['frame_count'] == round(2 * i['fps']) and
                type(i['frame_start']) is int and i['frame_start'] >= 0, 'two-second actual frame extent')
        require(isinstance(i['frames'], list) and 1 <= len(i['frames']) <= 8 and
                isinstance(i['crops'], list) and len(i['crops']) <= 2, 'bounded event evidence')
        times = [f['timestamp'] for f in i['frames']]
        require(times == sorted(set(times)), 'ordered fixed timestamps')
        for f in i['frames'] + i['crops']:
            number(f['timestamp'], 0, 2); require(f['timestamp'] < 2, 'timestamp outside event')
            require(isinstance(f['path'], str) and Path(f['path']).is_absolute(), 'absolute frame path')
        for c in i['crops']:
            from .protocol import box
            box(c['bbox']); require(c['timestamp'] in times, 'crop fixed timestamp')
        require(i['control'] is not None or i['source']['dataset_kind'] != 'tune' or i['source']['clip'] in TUNE_CLIPS, 'unknown tune clip')
        items[i['key']] = i
    controls = plan['controls']
    require(isinstance(controls, list) and len(controls) == 4 and {c['type'] for c in controls} == set(CONTROLS), 'four fixed controls required')
    for c in controls:
        keys(c, ('type', 'item', 'category', 'reference'))
        require(c['item'] in items and items[c['item']]['control'] == c['type'], 'control item binding')
    require(len({c['item'] for c in controls}) == 4 and sum(i['control'] is not None for i in items.values()) == 4, 'control population')
    if plan['phase'] in ('pilot', 'extension', 'checkpoints'):
        expected = 4 if plan['phase'] == 'extension' else 12
        require(len(plan['events']) == expected and len(items) == expected * 2 + 4, 'matched event population')
        seen_events, clips = set(), Counter()
        for e in plan['events']:
            keys(e, ('event', 'clip', 'incumbent', 'challenger'))
            require(e['event'] not in seen_events and e['incumbent'] in items and e['challenger'] in items, 'duplicate/unknown event')
            a, b = items[e['incumbent']], items[e['challenger']]
            require(a['role'] == 'incumbent' and b['role'] == 'challenger' and a['event'] == b['event'] == e['event'], 'matched item roles')
            require(a['source']['policy_sha256'] != b['source']['policy_sha256'] and
                    all(a['source'][k] == b['source'][k] for k in ('source_sha256', 'event', 'clip', 'dataset_sha256', 'variant')), 'matched source/policy mismatch')
            require(a['source']['clip'] == e['clip'] and a['source']['dataset_kind'] == b['source']['dataset_kind'] == 'tune', 'natural tune comparisons only')
            require(all(a[k] == b[k] for k in ('fps', 'frame_start', 'frame_count')) and
                    [f['timestamp'] for f in a['frames']] == [f['timestamp'] for f in b['frames']] and
                    [(f['timestamp'], f['bbox']) for f in a['crops']] == [(f['timestamp'], f['bbox']) for f in b['crops']], 'matched times/crop rules differ')
            seen_events.add(e['event']); clips[e['clip']] += 1
        if plan['phase'] == 'pilot':
            require(set(clips) == set(TUNE_CLIPS) and max(clips.values()) <= 2, '12 events across seven clips, max two per clip')
    elif plan['phase'] == 'locked':
        require(len(items) == 44 and len({i['event'] for i in items.values() if i['control'] is None}) == 40, 'locked check needs 40 distinct events plus controls')
        require(all(i['source']['dataset_kind'] == 'spent-v1' for i in items.values() if i['control'] is None), 'locked sources must be reserved spent-v1')
    else:
        require(len(items) <= 24 and all(i['source']['dataset_kind'] == 'fresh-v2' for i in items.values() if i['control'] is None), 'final licensed event cap')
    if plan['one_shot'] is not None:
        auth = load(receipt(plan['one_shot']['receipt']))
        require(all(auth[k] == plan['one_shot'][k] for k in ('status', 'root_authorized', 'policy_sha256', 'dataset_sha256')), 'ONE_SHOT receipt differs')
    for item in items.values():
        qualify(item)
    refs = {c['type']: load(receipt(c['reference'])) for c in controls}
    require(refs['readable_leak']['known_readable'] is True and refs['removed_target']['genuinely_removed'] is True and
            refs['readable_leak']['target_id'] == refs['removed_target']['target_id'], 'readable/removed same-target local validation required')
    require(refs['utility_failure']['known_utility_failure'] is True and
            refs['generic_context']['no_grounded_specific_location'] is True, 'uninterpretable controls')
    before = load(receipt(plan['local_before']))
    require(before['status'] == 'LOCAL_DECISION_BEFORE_REVEAL' and before['event_ids'] == [e['event'] for e in plan['events']], 'before-decision population differs')
    # This is the first image-byte access; all source fences and metadata
    # checks above apply to the entire plan before any image is touched.
    for i in items.values():
        for f in i['frames'] + i['crops']:
            receipt({'path': f['path'], 'sha256': f['sha256']})
    return {'status': 'READY', 'items': len(items)}


def seal(plan, public, private):
    result = validate_plan(plan)
    require(result['status'] == 'READY', 'MISSING_INPUTS: no pilot/card generation permitted')
    public, private = Path(public).resolve(), Path(private).resolve()
    require(public != private and public not in private.parents and private not in public.parents, 'private/public overlap')
    require(not public.exists() and not private.exists(), 'seal destination exists')
    public.mkdir(parents=True); private.mkdir(parents=True, mode=0o700)
    mapping = {}
    here = Path(__file__).parent
    for i in plan['items']:
        identity = token(); directory = public / identity; directory.mkdir()
        card = {'version': VERSION, 'item_id': identity, 'frames': [], 'crops': [], 'files': {}}
        frame_map = {}
        for kind in ('frames', 'crops'):
            for f in i[kind]:
                frame_id = token(); name = frame_id + '.png'
                normalize_check(f['path'])
                shutil.copyfile(f['path'], directory / name)
                row = {'id': frame_id, 'file': name, 'timestamp': f['timestamp']}
                if kind == 'crops':
                    row['bbox'] = f['bbox']
                card[kind].append(row); frame_map[frame_id] = f['timestamp']
        for name in ('rubric.md', 'response.schema.json'):
            shutil.copyfile(here / name, directory / name)
        card['files'] = {f.name: digest(f) for f in directory.iterdir()}
        card['card_digest'] = document_digest(card)
        write_once(directory / 'items.json', card)
        for f in directory.iterdir():
            f.chmod(0o444)
        verify_card(directory)
        mapping[identity] = {'item': i, 'card_digest': card['card_digest'], 'frame_map': frame_map}
    validate_plan(plan)
    order = list(mapping); random.SystemRandom().shuffle(order)
    sealed = {'version': VERSION, 'status': 'SEALED', 'implementation_sha256': code_hash(),
              'plan': plan, 'items': mapping, 'dispatch_order': order}
    write_once(private / 'SEALED.json', sealed)
    seal_hash = digest(private / 'SEALED.json')
    write_once(private / 'seal.json', {'map_sha256': seal_hash})
    return {'status': 'SEALED_UNGRADED', 'map_sha256': seal_hash, 'items': len(mapping)}


def skeleton():
    allocation = list(TUNE_CLIPS[:5]) * 2 + list(TUNE_CLIPS[5:])
    return {'version': VERSION, 'phase': 'pilot', 'status': 'MISSING_INPUTS', 'items': [],
            'events': [{'event': None, 'clip': clip, 'incumbent': None, 'challenger': None} for clip in allocation],
            'controls': [], 'one_shot': None, 'local_before': None,
            'selection_rules': 'ROOT REQUIRED: freeze source-event selection, ordered times <=8 over2s and <=2 processed crops with identical rules; no actual cards yet'}

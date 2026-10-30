"""Bounded data protocol for a fresh context receiving one visual event card."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets

VERSION = 2
CATEGORIES = ('text_sign', 'logo_storefront_landmark', 'house_number_address', 'plate', 'bystander_face')
STATES = ('present', 'absent_in_sample', 'uncertain')
MODELS = {'opus': ('opus-5.5', 'high'), 'sol': ('gpt-6.1-sol', 'xhigh'), 'luna': ('gpt-6-luna', 'medium')}


class PanelError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise PanelError(message)


def keys(value, expected):
    require(isinstance(value, dict) and set(value) == set(expected), 'unknown/missing fields: ' + ','.join(expected))


def text(value, limit=500):
    require(isinstance(value, str) and len(value) <= limit, 'invalid bounded text')


def number(value, low, high):
    require(type(value) in (int, float) and math.isfinite(value) and low <= value <= high, 'invalid finite number')


def identity(value):
    require(isinstance(value, str) and re.fullmatch('[a-f0-9]{32}', value), 'invalid blind ID')


def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(',', ':')) + '\n').encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def load(path):
    p = Path(path)
    require(p.is_file() and p.stat().st_size <= 8 * 1024 * 1024, 'missing/oversize JSON')
    def unique(pairs):
        result = {}
        for k, v in pairs:
            require(k not in result, 'duplicate JSON key')
            result[k] = v
        return result
    def invalid(value):
        raise PanelError('nonfinite JSON')
    return json.loads(p.read_text(), object_pairs_hook=unique, parse_constant=invalid)


def write_once(path, value):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(canonical(value)); f.flush(); os.fsync(f.fileno())
    p.chmod(0o444)


def token():
    return secrets.token_hex(16)


def code_hash():
    return sha(canonical({p.name: digest(p) for p in sorted(Path(__file__).parent.iterdir())
                          if p.suffix in ('.py', '.json', '.md')}))


def document_digest(document):
    return sha(canonical({k: v for k, v in document.items() if k != 'card_digest'}))


def verify_card(directory):
    d = Path(directory)
    require(not d.is_symlink(), 'card symlink')
    card = load(d / 'items.json')
    keys(card, ('version', 'item_id', 'card_digest', 'frames', 'crops', 'files'))
    identity(card['item_id'])
    require(card['version'] == VERSION and card['card_digest'] == document_digest(card), 'wrong card digest')
    require(isinstance(card['frames'], list) and 1 <= len(card['frames']) <= 8, 'frame count')
    require(isinstance(card['crops'], list) and len(card['crops']) <= 2, 'crop count')
    ids, times, names = set(), [], set()
    for f in card['frames'] + card['crops']:
        crop = f in card['crops']
        keys(f, ('id', 'file', 'timestamp', 'bbox') if crop else ('id', 'file', 'timestamp'))
        identity(f['id']); number(f['timestamp'], 0, 2)
        require(f['timestamp'] < 2 and f['id'] not in ids and f['file'] == f['id'] + '.png', 'frame ID/time/filename')
        ids.add(f['id']); names.add(f['file'])
        if crop:
            box(f['bbox'])
            require(f['timestamp'] in times, 'crop must use a sampled timestamp')
        else:
            times.append(f['timestamp'])
    require(times == sorted(set(times)), 'frames must be time ordered and distinct')
    expected = names | {'rubric.md', 'response.schema.json'}
    require(isinstance(card['files'], dict) and set(card['files']) == expected, 'card file allowlist')
    require({p.name for p in d.iterdir()} == expected | {'items.json'}, 'extra card files')
    for name, value in card['files'].items():
        p = d / name
        require(p.is_file() and not p.is_symlink() and digest(p) == value, 'public card hash drift')
    return card


def box(value):
    require(isinstance(value, list) and len(value) == 4, 'bbox must have four normalized coordinates')
    for n in value:
        number(n, 0, 1)
    require(value[0] < value[2] and value[1] < value[3], 'empty bbox')


def evidence(value, card, face=False):
    keys(value, ('frame_id', 'timestamp', 'bbox', 'exact_string', 'cue'))
    frames = {f['id']: f for f in card['frames'] + card['crops']}
    require(isinstance(value['frame_id'], str) and value['frame_id'] in frames, 'unknown evidence frame')
    number(value['timestamp'], 0, 2)
    require(value['timestamp'] == frames[value['frame_id']]['timestamp'], 'evidence timestamp differs')
    box(value['bbox'])
    text(value['exact_string'], 150); text(value['cue'], 200)
    require(bool(value['exact_string'].strip() or value['cue'].strip()), 'ungrounded finding')
    require(not face or value['exact_string'] == '', 'person identification forbidden; count exposed faces only')


def visible_words(value):
    if isinstance(value, dict):
        return sum(visible_words(v) for v in value.values())
    if isinstance(value, list):
        return sum(visible_words(v) for v in value)
    return len(value.split()) if isinstance(value, str) else 0


def validate_response(value, card, start):
    keys(value, ('version', 'item_id', 'card_digest', 'grader_identity', 'start_id', 'status', 'complete',
                 'findings', 'utility', 'location', 'exposed_faces_count', 'notes'))
    require(value['version'] == VERSION and type(value['version']) is int, 'response version')
    require(value['item_id'] == card['item_id'] and value['card_digest'] == card['card_digest'], 'wrong item/digest')
    require(value['grader_identity'] == start['grader_identity'] and value['start_id'] == start['start_id'], 'grader/start mismatch')
    require(value['status'] in ('completed', 'missing', 'timeout'), 'completion status')
    require(type(value['complete']) is bool and value['complete'] == (value['status'] == 'completed'), 'completion mismatch')
    require(isinstance(value['findings'], list) and len(value['findings']) == len(CATEGORIES), 'category population')
    seen = set()
    for finding in value['findings']:
        keys(finding, ('category', 'leak', 'severity', 'evidence'))
        c = finding['category']
        require(isinstance(c, str) and c in CATEGORIES and c not in seen, 'unknown/duplicate category')
        seen.add(c)
        require(finding['leak'] in STATES and type(finding['severity']) is int and 0 <= finding['severity'] <= 3, 'category state/severity')
        require(isinstance(finding['evidence'], list) and len(finding['evidence']) <= 3, 'evidence count')
        for e in finding['evidence']:
            evidence(e, card, c == 'bystander_face')
        if finding['leak'] == 'present':
            require(finding['severity'] >= 2 and bool(finding['evidence']), 'present requires grounded protected cue')
        elif finding['leak'] == 'absent_in_sample':
            require(finding['severity'] <= 1 and not finding['evidence'], 'absence cannot contain a recovered cue')
    keys(value['utility'], ('state', 'defects'))
    require(value['utility']['state'] in ('acceptable', 'unacceptable', 'uncertain') and
            isinstance(value['utility']['defects'], list) and len(value['utility']['defects']) <= 3, 'utility triad')
    for e in value['utility']['defects']:
        evidence(e, card)
    require(value['utility']['state'] != 'unacceptable' or bool(value['utility']['defects']), 'utility failure needs evidence')
    keys(value['location'], ('state', 'evidence'))
    require(value['location']['state'] in ('grounded_specific', 'generic', 'uncertain', 'not_observed') and
            isinstance(value['location']['evidence'], list) and len(value['location']['evidence']) <= 3, 'location state')
    for e in value['location']['evidence']:
        evidence(e, card)
    require(value['location']['state'] != 'grounded_specific' or bool(value['location']['evidence']), 'place guess without supporting cue')
    count = value['exposed_faces_count']
    require(count is None or type(count) is int and 0 <= count <= 100, 'exposed face count only')
    face = next(f for f in value['findings'] if f['category'] == 'bystander_face')
    require(face['leak'] != 'present' or count is not None and count > 0, 'face finding needs exposed count')
    text(value['notes'], 500)
    if value['status'] != 'completed':
        require(all(f['leak'] == 'uncertain' for f in value['findings']) and value['utility']['state'] == 'uncertain' and
                value['location']['state'] == 'uncertain' and count is None, 'missing/timeout must stay uncertain')
    require(visible_words(value) <= 250, 'visible output exceeds 250 words')
    return value


def validate_comparison(value, start, item_ids):
    keys(value, ('version', 'start_id', 'grader_identity', 'items', 'utility', 'evidence'))
    require(value['version'] == VERSION and value['start_id'] == start['start_id'] and
            value['grader_identity'] == start['grader_identity'] and value['items'] == item_ids, 'comparison identity')
    require(value['utility'] in ('A', 'B', 'tie', 'uncertain'), 'comparison utility')
    require(isinstance(value['evidence'], list) and len(value['evidence']) <= 4 and
            all(isinstance(i, str) and i in item_ids for i in value['evidence']), 'comparison cited items')
    require(value['utility'] not in ('A', 'B') or bool(value['evidence']), 'winner needs cited evidence')
    require(visible_words(value) <= 250, 'visible output exceeds 250 words')
    return value

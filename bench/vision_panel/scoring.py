"""First-pass findings and local decision records; no scalar privacy reward."""
from datetime import datetime, timezone
from pathlib import Path
import math

from .pack import CONTROLS, receipt, validate_plan
from .protocol import (CATEGORIES, MODELS, VERSION, code_hash, digest, keys, load,
                       require, token, validate_comparison, validate_response,
                       verify_card, write_once)


def now():
    return datetime.now(timezone.utc).isoformat()


def source_frame(frame_start, fps, frame_count, timestamp):
    require(type(frame_start) is int and frame_start >= 0 and type(frame_count) is int and frame_count > 0, 'actual frame extent required')
    require(type(timestamp) in (int, float) and math.isfinite(timestamp) and 0 <= timestamp < 2, 'event timestamp')
    return frame_start + min(math.floor(timestamp * fps), frame_count - 1)


def record_before(path, decisions, selection_rules_sha256):
    require(len(decisions) in (4, 12, 20, 40) and len({d['event'] for d in decisions}) == len(decisions), 'before-decision event population')
    for d in decisions:
        keys(d, ('event', 'clip', 'decision', 'known_issue_ids', 'ocr', 'area', 'runtime', 'geoclip'))
        require(d['decision'] in ('promote', 'veto', 'keep', 'utility_tie'), 'local decision')
        require(isinstance(d['known_issue_ids'], list), 'known local failures')
        for k in ('ocr', 'area', 'runtime', 'geoclip'):
            receipt(d[k])
    write_once(path, {'version': VERSION, 'status': 'LOCAL_DECISION_BEFORE_REVEAL', 'created_at': now(),
                     'event_ids': [d['event'] for d in decisions], 'decisions': decisions,
                     'selection_rules_sha256': selection_rules_sha256})


def begin(public, round_dir, assignments, before_ref):
    """Create local start tokens only; the caller owns authorized dispatch."""
    public, d = Path(public), Path(round_dir)
    cards = {p.name: verify_card(p) for p in public.iterdir()}
    before = load(receipt(before_ref))
    require(before['status'] == 'LOCAL_DECISION_BEFORE_REVEAL', 'local decision must precede panel reveal')
    require(not d.exists(), 'round exists; no replay')
    require(isinstance(assignments, list) and 1 <= len(assignments) <= 132, 'assignments')
    seen, identities, provider_items = set(), set(), {}
    rows = []
    for a in assignments:
        keys(a, ('item_id', 'provider', 'grader_identity', 'model', 'effort'))
        require(a['item_id'] in cards and a['provider'] in MODELS and
                (a['model'], a['effort']) == MODELS[a['provider']], 'model/card assignment')
        require(isinstance(a['grader_identity'], str) and 0 < len(a['grader_identity']) <= 200, 'grader identity')
        pair = (a['item_id'], a['provider'])
        require(pair not in seen and a['grader_identity'].casefold() not in identities, 'duplicate grader/context/item assignment')
        seen.add(pair); identities.add(a['grader_identity'].casefold())
        provider_items.setdefault(a['provider'], set()).add(a['item_id'])
        rows.append({**a, 'entry_id': token(), 'start_id': token(), 'started_at': now(),
                     'card_digest': cards[a['item_id']]['card_digest']})
    require(all(provider_items.get(p) == set(cards) for p in ('opus', 'sol')), 'both strong first passes required for every card')
    require('luna' not in provider_items or provider_items['luna'] == set(cards), 'all actual shadow first passes must be registered')
    d.mkdir(parents=True, mode=0o700)
    write_once(d / 'round.json', {'version': VERSION, 'round_id': token(), 'created_at': now(),
               'implementation_sha256': code_hash(), 'before': before_ref, 'entries': rows})
    for row in rows:
        write_once(d / ('start-' + row['entry_id'] + '.json'), {**row, 'round_sha256': digest(d / 'round.json')})
    return rows


def finish(public, round_dir, entry_id, response_path, attachment_receipt):
    d = Path(round_dir); roster = load(d / 'round.json')
    require(roster['implementation_sha256'] == code_hash(), 'implementation drift since start')
    row = next((r for r in roster['entries'] if r['entry_id'] == entry_id), None)
    require(row is not None, 'unknown start entry')
    start_path = d / ('start-' + entry_id + '.json')
    start = load(start_path)
    require(start == {**row, 'round_sha256': digest(d / 'round.json')}, 'immutable start drift')
    card = verify_card(Path(public) / row['item_id'])
    require(card['card_digest'] == row['card_digest'], 'card drift')
    value = validate_response(load(response_path), card, start)
    if value['status'] == 'completed':
        require(isinstance(attachment_receipt, dict) and attachment_receipt.get('received') is True and
                set(attachment_receipt.get('image_sha256s', [])) == {card['files'][f['file']] for f in card['frames'] + card['crops']},
                'actual image attachment receipt required; text-only capability unavailable')
    else:
        require(attachment_receipt is None or isinstance(attachment_receipt, dict), 'missing attachment receipt')
    write_once(d / ('output-' + entry_id + '.json'), value)
    write_once(d / ('finish-' + entry_id + '.json'), {'entry_id': entry_id, 'start_sha256': digest(start_path),
               'output_sha256': digest(d / ('output-' + entry_id + '.json')), 'finished_at': now(),
               'attachment_receipt': attachment_receipt})


def first_pass_seals(public, round_dir):
    d = Path(round_dir); roster = load(d / 'round.json')
    require(roster['implementation_sha256'] == code_hash(), 'implementation drift')
    require(all((d / ('finish-' + r['entry_id'] + '.json')).is_file() for r in roster['entries']),
            'all actual first-pass answers must be sealed before unblind/reference checking')
    results = []
    for row in roster['entries']:
        entry = row['entry_id']; start_path = d / ('start-' + entry + '.json')
        output_path = d / ('output-' + entry + '.json')
        start, end = load(start_path), load(d / ('finish-' + entry + '.json'))
        require(start == {**row, 'round_sha256': digest(d / 'round.json')} and
                end['entry_id'] == entry and end['start_sha256'] == digest(start_path) and
                end['output_sha256'] == digest(output_path) and
                datetime.fromisoformat(end['finished_at']) >= datetime.fromisoformat(start['started_at']), 'start/finish/output drift')
        card = verify_card(Path(public) / row['item_id'])
        require(card['card_digest'] == row['card_digest'], 'card drift')
        response = validate_response(load(output_path), card, start)
        require(response['status'] != 'completed' or end['attachment_receipt'] is not None and end['attachment_receipt'].get('received') is True and
                set(end['attachment_receipt'].get('image_sha256s', [])) == {card['files'][f['file']] for f in card['frames'] + card['crops']}, 'attachment state drift')
        results.append({'start': row, 'answer': response, 'finish': end})
    receipt(roster['before'])
    return roster, results


def control_pass(kind, category, reference, answer):
    if answer['status'] != 'completed':
        return False
    if kind == 'generic_context':
        return answer['location']['state'] != 'grounded_specific'
    if kind == 'utility_failure':
        return answer['utility']['state'] == 'unacceptable'
    finding = next(f for f in answer['findings'] if f['category'] == category)
    if kind == 'removed_target':
        return finding['leak'] == 'absent_in_sample'
    expected = ' '.join(reference['exact_string'].casefold().split())
    return finding['leak'] == 'present' and any(expected == ' '.join(e['exact_string'].casefold().split()) for e in finding['evidence'])


def reveal(public, private, round_dir, expected_map_sha256):
    # This barrier is intentionally before ANY private-map access.
    roster, results = first_pass_seals(public, round_dir)
    private, d = Path(private), Path(round_dir)
    require(digest(private / 'SEALED.json') == expected_map_sha256 == load(private / 'seal.json')['map_sha256'], 'private map drift')
    sealed = load(private / 'SEALED.json')
    require(sealed['implementation_sha256'] == code_hash() and sealed['status'] == 'SEALED', 'sealed protocol drift')
    validate_plan(sealed['plan'])
    require(sealed['plan']['local_before'] == roster['before'], 'before-decision binding drift')
    require({r['start']['item_id'] for r in results} == set(sealed['items']), 'unblind population drift')
    write_once(d / 'UNBLINDED.json', {'at': now(), 'map_sha256': expected_map_sha256,
               'round_sha256': digest(d / 'round.json'),
               'finish_sha256s': {r['start']['entry_id']: digest(d / ('finish-' + r['start']['entry_id'] + '.json')) for r in results}})
    checks, work = {}, []
    by_key = {v['item']['key']: k for k, v in sealed['items'].items()}
    for r in results:
        row, answer = r['start'], r['answer']; m = sealed['items'][row['item_id']]; item = m['item']
        provider = row['provider']
        for f in answer['findings']:
            for e in f['evidence']:
                work.append({'provider': provider, 'item_id': row['item_id'], 'event': item['event'],
                             'clip': item['source']['clip'], 'policy_sha256': item['source']['policy_sha256'],
                             'source_sha256': item['source']['source_sha256'], 'output_sha256': item['source']['output_sha256'],
                             'source_frame': source_frame(item['frame_start'], item['fps'], item['frame_count'], e['timestamp']),
                             'category': f['category'], 'leak': f['leak'], 'severity': f['severity'], 'evidence': e,
                             'verification': 'UNVERIFIED_FIRST_PASS', 'control': item['control']})
        if item['control'] is not None:
            c = next(c for c in sealed['plan']['controls'] if c['item'] == item['key'])
            passed = control_pass(c['type'], c['category'], load(receipt(c['reference'])), answer)
            checks.setdefault(provider, []).append({'item_id': row['item_id'], 'type': c['type'], 'passed': passed})
    controls = {p: {'checks': rows, 'passed': sum(r['passed'] for r in rows), 'denominator': 4,
                    'automatic_use_stopped': len(rows) != 4 or not all(r['passed'] for r in rows)} for p, rows in checks.items()}
    report = {'version': VERSION, 'status': 'FIRST_PASS_SEALED_LOCAL_VERIFICATION_REQUIRED', 'controls': controls,
              'readable_and_cue_work_items': work, 'answers': results, 'unblind_barrier_sha256': digest(d / 'UNBLINDED.json'),
              'before': roster['before'], 'map_sha256': expected_map_sha256, 'event_denominator': len(sealed['plan']['events']),
              'source_clip_denominator': len({e['clip'] for e in sealed['plan']['events']}),
              'privacy_score': None, 'utility_acceptance': 'OWNER_EYE', 'production_promotion': False,
              'luna_authority': 'TRIAGE_ONLY_NO_CLEARANCE_NO_VETO', 'continuous_privacy_or_flicker_claim': None,
              'deployment_reliability': None, 'capability_claims': None}
    write_once(d / 'findings.json', report)
    return report


def comparison_consistency(original, reversed_answer, original_items, reversed_items, identical=False):
    require(reversed_items == list(reversed(original_items)), 'comparison not actually reversed')
    def winner(answer, items):
        return answer['utility'] if answer['utility'] in ('tie', 'uncertain') else items[0 if answer['utility'] == 'A' else 1]
    if identical:
        return original['utility'] == reversed_answer['utility'] == 'tie'
    return winner(original, original_items) == winner(reversed_answer, reversed_items) and original['utility'] != 'uncertain'


def record_after(round_dir, contributions, local_verification_ref, owner_utility_ref=None):
    d = Path(round_dir); findings = load(d / 'findings.json')
    require(digest(d / 'UNBLINDED.json') == findings['unblind_barrier_sha256'], 'reveal barrier drift')
    verification = load(receipt(local_verification_ref))
    require(verification['unblind_barrier_sha256'] == findings['unblind_barrier_sha256'] and
            verification['map_sha256'] == findings['map_sha256'], 'local verification before seals or wrong map')
    before = load(receipt(findings['before']))
    by_event = {r['event']: r for r in before['decisions']}
    qualified = []
    for c in contributions:
        keys(c, ('event', 'clip', 'kind', 'before', 'after', 'evidence_id', 'verified', 'strong_confirmed', 'new_evidence'))
        require(c['event'] in by_event and c['before'] == by_event[c['event']]['decision'] and c['clip'] == by_event[c['event']]['clip'], 'before/after event mismatch')
        require(c['kind'] in ('promotion_change', 'veto_change', 'actual_utility_tie', 'known_failure_description'), 'contribution type')
        local = next((r for r in verification['checks'] if r['evidence_id'] == c['evidence_id']), None)
        require(local is not None and local['verified'] == c['verified'] and local['event'] == c['event'], 'unverified contribution')
        strong_ok = all(not findings['controls'][p]['automatic_use_stopped'] for p in ('opus', 'sol')) and local['confirmed_by'] == ['opus', 'sol']
        require(c['strong_confirmed'] is strong_ok, 'Luna cannot confirm/veto/clear a consequence')
        is_new = c['evidence_id'] not in by_event[c['event']]['known_issue_ids']
        require(c['new_evidence'] is is_new, 'known OCR/GeoCLIP failure is not new contribution')
        if c['kind'] == 'actual_utility_tie':
            require(c['before'] == 'utility_tie' and owner_utility_ref is not None and local.get('pairwise_controls_pass') is True, 'actual utility tie/owner eye/control receipt required')
            owner = load(receipt(owner_utility_ref))
            require(owner['accepted'] is True and c['event'] in owner['events'], 'owner utility verdict missing')
        contributes = c['verified'] is True and strong_ok and is_new and c['kind'] != 'known_failure_description' and c['before'] != c['after']
        qualified.append({**c, 'counts_as_contribution': contributes})
    report = {'version': VERSION, 'status': 'LOCAL_AFTER_DECISION', 'contributions': qualified,
              'verified_changes': sum(c['counts_as_contribution'] for c in qualified),
              'different_clip_count': len({c['clip'] for c in qualified if c['counts_as_contribution']}),
              'local_verification': local_verification_ref, 'owner_utility': owner_utility_ref,
              'all_findings_preserved': True, 'production_promotion': False}
    write_once(d / 'after.json', report)
    return report

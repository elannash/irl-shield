"""Pure budget transitions. They authorize no dispatch and invoke no models."""
import copy

from .protocol import MODELS, number, require
from .pack import receipt
from .protocol import load
from .pack import SPENT_V1_SHA256

POOLS = {'pilot': (56, 28), 'extension': (16, 0), 'revision': (0, 28),
         'locked': (80, 40), 'checkpoints': (0, 48), 'special': (20, 0),
         'technical': (0, 6), 'final': (48, 0)}
PHASE_SECONDS = {'pilot': 7200, 'conditional': 3600, 'checkpoints': 1800, 'final': 7200}


def initial():
    historical = [{'attempt_id': 'pre-consensus-inspection-' + str(i + 1), 'provider': 'sol', 'pool': 'special',
                   'units': 1, 'status': 'historical_inspection', 'model': 'gpt-6.1-sol', 'effort': 'ultra',
                   'valid_reference': False, 'actual_attachment_receipt': None, 'latency_seconds': None,
                   'usage': None, 'started_at': None, 'finished_at': None} for i in range(6)]
    return {'version': 2, 'attempts': historical, 'active': {}, 'clean': dict.fromkeys(MODELS, 0),
            'capability': dict.fromkeys(MODELS), 'disabled': [], 'phase': None, 'phase_started': None,
            'elapsed': dict.fromkeys(PHASE_SECONDS, 0), 'value_gate': 'pending', 'stopped': None,
            'revision_started': False, 'locked_started': False, 'locked_result': None,
            'checkpoint_ids': [], 'final_started': False, 'final_freeze_sha256': None,
            'codex_quota': None, 'phase_deadline': None, 'final_reserve_seconds': 7200,
            'findings_retained': True, 'historical_elapsed_seconds': None}


def counts(state):
    by_provider = {p: sum(a['units'] for a in state['attempts'] if a['provider'] == p) for p in MODELS}
    strong = by_provider['opus'] + by_provider['sol']
    special = sum(a['units'] for a in state['attempts'] if a['pool'] == 'special' and a['provider'] != 'luna')
    return {'strong_used': strong, 'strong_remaining': 220 - strong, 'provider_used': by_provider,
            'luna_remaining': 150 - by_provider['luna'], 'special_remaining': 20 - special,
            'final_strong_reserved': max(0, 48 - sum(a['units'] for a in state['attempts'] if a['pool'] == 'final'))}


def elapsed(state, now):
    number(now, 0, 10**12)
    values = dict(state['elapsed'])
    if state['phase'] is not None:
        require(state['phase_started'] is not None and now >= state['phase_started'], 'clock drift')
        values[state['phase']] += now - state['phase_started']
    return values


def stop_reason(state, now, quota_ok, controls_interpretable, projected_finish, freeze_at):
    if state['stopped']:
        return state['stopped']
    if quota_ok is not True:
        return 'quota_failure_or_unavailable'
    if controls_interpretable is not True:
        return 'uninterpretable_controls'
    values = elapsed(state, now)
    historical = state['historical_elapsed_seconds']
    if historical is None:
        return 'historical_time_unreconciled'
    number(historical, 0, 19800)
    if sum(values.values()) + historical >= 19800:
        return 'total_5_5h_cap'
    if state['phase'] and values[state['phase']] >= PHASE_SECONDS[state['phase']]:
        return state['phase'] + '_time_cap'
    if state['phase'] != 'final' and sum(values.values()) + historical >= 12600:
        return 'final_2h_reserved'
    if projected_finish is None or freeze_at is None:
        return 'projection_or_freeze_unavailable'
    if projected_finish > freeze_at:
        return 'missed_freeze'
    return None


def project(state, providers_and_remaining, now):
    """Only observed successful attachment completions; no invented latency."""
    estimates = {}
    for provider, remaining in providers_and_remaining.items():
        require(provider in MODELS and type(remaining) is int and remaining >= 0, 'projection request')
        if not remaining:
            continue
        observations = [a['latency_seconds'] for a in state['attempts'] if a['provider'] == provider and
                        a['status'] == 'completed' and a['actual_attachment_receipt'] is not None and a['latency_seconds'] is not None]
        if not observations:
            return None
        # Conservative serial projection; unlocking concurrency never creates a
        # latency assumption or separate Codex quota for Sol and Luna.
        estimates[provider] = remaining * sum(observations) / len(observations) * 2
    return now + max(estimates.get('opus', 0), estimates.get('sol', 0) + estimates.get('luna', 0))


def start_phase(state, phase, now, freeze_at, final_freeze_sha256=None):
    s = copy.deepcopy(state)
    require(phase in PHASE_SECONDS and s['phase'] is None and not s['active'], 'phase already active')
    require(s['stopped'] is None or phase == 'final', 'recurring panel stopped; final audit retained')
    number(now, 0, 10**12); number(freeze_at, now, 10**12)
    if phase in ('conditional', 'checkpoints'):
        require(s['value_gate'] == 'conditional', 'value gate not passed')
    if phase == 'checkpoints':
        require(s['locked_result'] == 'PASS', 'locked Luna check not passed')
    if phase == 'final':
        require(not s['final_started'] and isinstance(final_freeze_sha256, str) and len(final_freeze_sha256) == 64, 'final frozen one-shot binding required')
        s['final_started'] = True; s['final_freeze_sha256'] = final_freeze_sha256
        s['stopped'] = None
    require(s['historical_elapsed_seconds'] is not None, 'historical elapsed time must be reconciled by root')
    number(s['historical_elapsed_seconds'], 0, 19800)
    require(s['elapsed'][phase] < PHASE_SECONDS[phase], 'phase time exhausted')
    s['phase'] = phase; s['phase_started'] = now; s['phase_deadline'] = freeze_at
    return s


def end_phase(state, now):
    s = copy.deepcopy(state)
    require(s['phase'] is not None and not s['active'], 'phase missing or requests still active')
    s['elapsed'] = elapsed(s, now); s['phase'] = None; s['phase_started'] = None
    return s


def reserve_attempt(state, provider, pool, attempt_id, items, now, *, model, effort,
                    quota_ok, controls_interpretable, projected_finish, attachment_control=False,
                    checkpoint_id=None, item_ids=None):
    """Charge every requested logical item, including failed/retried bundles."""
    s = copy.deepcopy(state)
    require(provider in MODELS and (model, effort) == MODELS[provider], 'no model/effort substitution')
    require(pool in POOLS and type(items) is int and 1 <= items <= 44, 'logical item charge')
    require(isinstance(item_ids, list) and len(item_ids) == items and len(set(item_ids)) == items and all(isinstance(i, str) and i for i in item_ids), 'logical item IDs required')
    require(attempt_id not in {a['attempt_id'] for a in s['attempts']}, 'attempt replay')
    require(s['phase'] is not None and provider not in s['disabled'], 'phase missing or grader disabled')
    bootstrap = attachment_control and s['capability'][provider] is None and s['clean'][provider] == 0
    require(stop_reason(s, now, quota_ok, controls_interpretable, now if bootstrap and projected_finish is None else projected_finish, s['phase_deadline']) is None, 'budget/time/quota stop')
    require(provider != 'luna' or s['phase'] != 'final', 'Luna has no final clearance role')
    require(s['capability'][provider] is not None or attachment_control, 'actual image control capability receipt required')
    active = [a for a in s['active'].values() if a['provider'] == provider]
    require(len(active) < (2 if s['clean'][provider] >= 10 else 1), 'provider concurrency cap')
    phase_pools = {'pilot': ('pilot', 'extension', 'special', 'technical'),
                   'conditional': ('revision', 'locked', 'special', 'technical'),
                   'checkpoints': ('checkpoints', 'special', 'technical'), 'final': ('final',)}
    require(pool in phase_pools[s['phase']], 'pool/phase mismatch')
    if pool == 'extension':
        require(s['value_gate'] == 'extend_four', 'only exactly one useful pilot result permits extension')
    if pool in ('revision', 'locked', 'checkpoints'):
        require(s['value_gate'] == 'conditional', 'conditional work not earned')
    require(pool != 'revision' or s['revision_started'], 'one prompt revision must be frozen before revision calls')
    require(pool != 'locked' or s['locked_started'] and s['locked_result'] is None, 'locked check must be frozen and not completed')
    require(pool != 'checkpoints' or s['locked_result'] == 'PASS', 'failed/skipped locked check ends tuning')
    if pool == 'checkpoints':
        require(checkpoint_id is not None, 'checkpoint identity')
        if checkpoint_id not in s['checkpoint_ids']:
            require(len(s['checkpoint_ids']) < 2, 'at most two finalist checkpoints')
            s['checkpoint_ids'].append(checkpoint_id)
    side = 1 if provider == 'luna' else 0
    used_pool = sum(a['units'] for a in s['attempts'] if a['pool'] == pool and (a['provider'] == 'luna') == (provider == 'luna'))
    require(used_pool + items <= POOLS[pool][side], 'phase call pool exhausted')
    # Split each combined strong pool evenly, preserving 24 final calls/provider.
    if provider != 'luna':
        own_pool = sum(a['units'] for a in s['attempts'] if a['pool'] == pool and a['provider'] == provider)
        require(own_pool + items <= POOLS[pool][0] // 2, 'per-provider phase pool exhausted')
    c = counts(s)
    if provider == 'luna':
        require(c['provider_used'][provider] + items <= 150, 'Luna hard cap')
    else:
        limit = 110 if pool == 'final' else 86
        require(c['provider_used'][provider] + items <= limit and c['strong_used'] + items <= (220 if pool == 'final' else 172), 'strong cap/final reserve')
    row = {'attempt_id': attempt_id, 'provider': provider, 'pool': pool, 'units': items, 'status': 'started',
           'model': model, 'effort': effort, 'valid_reference': provider != 'luna', 'actual_attachment_receipt': None,
           'latency_seconds': None, 'usage': None, 'started_at': now, 'finished_at': None,
           'checkpoint_id': checkpoint_id, 'attachment_control': attachment_control, 'projected_finish': projected_finish, 'item_ids': item_ids}
    s['attempts'].append(row); s['active'][attempt_id] = row
    return s


def complete_attempt(state, attempt_id, now, *, status, attachment_receipt, controls_pass, usage=None):
    s = copy.deepcopy(state)
    require(attempt_id in s['active'], 'unknown/completed attempt')
    require(status in ('completed', 'missing', 'timeout', 'quota_failure'), 'attempt status')
    row = next(a for a in s['attempts'] if a['attempt_id'] == attempt_id)
    number(now, row['started_at'], 10**12)
    row.update(status=status, finished_at=now, latency_seconds=now - row['started_at'],
               actual_attachment_receipt=attachment_receipt, usage=usage)
    provider = row['provider']
    require(attachment_receipt is None or isinstance(attachment_receipt, dict) and
            attachment_receipt.get('image_sha256') and attachment_receipt.get('received') is True, 'actual attachment receipt')
    if status == 'completed' and attachment_receipt is not None and controls_pass is True:
        s['clean'][provider] += 1
        if row['attachment_control']:
            s['capability'][provider] = attachment_receipt
    else:
        s['clean'][provider] = 0
    if controls_pass is False and provider not in s['disabled']:
        s['disabled'].append(provider)
    if status == 'quota_failure':
        s['stopped'] = 'quota_failure'
    del s['active'][attempt_id]
    return s


def pilot_value(changes, comparisons, extension=False, *, all_comparisons_interpretable=False):
    require(comparisons == (16 if extension else 12), 'incomplete pilot remains uncertain')
    if not all_comparisons_interpretable:
        return 'STOP_INCOMPLETE_KEEP_FINAL'
    useful = [c for c in changes if c.get('counts_as_contribution') is True and c.get('verified') is True and c.get('strong_confirmed') is True and
              c.get('kind') in ('promotion_change', 'veto_change', 'actual_utility_tie') and c.get('new_evidence') is True]
    useful = list({c['event']: c for c in useful}.values())
    clips = {c['clip'] for c in useful}
    if len(useful) >= 2 and len(clips) >= 2:
        return 'conditional'
    if len(useful) == 1 and not extension:
        return 'extend_four'
    return 'STOP_RECURRING_KEEP_FINAL'


def begin_locked(state, labels, prompt_sha256):
    s = copy.deepcopy(state)
    require(s['value_gate'] == 'conditional' and not s['locked_started'], 'locked run not earned or already attempted')
    require(s['revision_started'] and prompt_sha256 == s['prompt_sha256'], 'one frozen prompt revision required')
    events = [r['event'] for r in labels]
    if len(labels) != 40 or len(set(events)) != 40 or sum(r['label'] == 'present' for r in labels) != 20 or sum(r['label'] == 'absent_in_sample' for r in labels) != 20:
        s['locked_result'] = 'SKIP_MISSING_DATA'; s['locked_started'] = True
        return s
    require(all(r['dataset_sha256'] == SPENT_V1_SHA256 and
                r['strong_verified'] is True and r['variant'] == 'natural' for r in labels), 'locked verified distinct spent-v1 events required')
    s['locked_started'] = True; s['locked_labels'] = labels; s['prompt_sha256'] = prompt_sha256
    return s


def revise_prompt(state, prompt_sha256):
    s = copy.deepcopy(state)
    require(s['value_gate'] == 'conditional' and not s['revision_started'] and not s['locked_started'], 'only one earned prompt revision')
    require(isinstance(prompt_sha256, str) and len(prompt_sha256) == 64, 'prompt hash')
    s['revision_started'] = True; s['prompt_sha256'] = prompt_sha256
    return s


def locked_result(state, answers, controls_pass):
    s = copy.deepcopy(state)
    require(s['locked_started'] and s['locked_result'] is None and 'locked_labels' in s, 'no rescue draw/retry')
    require(set(answers) == {r['event'] for r in s['locked_labels']} and all(v in ('present', 'absent_in_sample', 'uncertain') for v in answers.values()), 'locked answer population')
    positives = [r['event'] for r in s['locked_labels'] if r['label'] == 'present']
    negatives = [r['event'] for r in s['locked_labels'] if r['label'] == 'absent_in_sample']
    misses = sum(answers[e] == 'absent_in_sample' for e in positives)
    escalated = sum(answers[e] != 'absent_in_sample' for e in negatives)
    passed = misses == 0 and controls_pass is True and escalated <= 8
    s['locked_result'] = 'PASS' if passed else 'FAIL_END_TUNING'
    s['locked_metrics'] = {'false_clears': misses, 'positive_events': 20, 'negative_escalations': escalated,
                           'negative_events': 20, 'controls_pass': controls_pass,
                           'deployment_reliability': None, 'independence_claim': False}
    return s


def close_checkpoints(state, decision_changes, random_clear_confirmations):
    s = copy.deepcopy(state)
    require(len(s['checkpoint_ids']) == 2 and not s['active'], 'two completed checkpoints required')
    require(len(random_clear_confirmations) == 4 and len({r['event'] for r in random_clear_confirmations}) == 4, 'four random-clear strong audits required')
    used_attempts = set()
    for r in random_clear_confirmations:
        audit = load(receipt(r['receipt']))
        require(audit['event'] == r['event'] and audit['strong_confirmed'] is True and len(audit['attempt_ids']) == 2, 'unverified random-clear audit')
        providers = set()
        for identity in audit['attempt_ids']:
            a = next((a for a in s['attempts'] if a['attempt_id'] == identity), None)
            require(a is not None and identity not in used_attempts and a['pool'] == 'special' and a['status'] == 'completed' and a['units'] == 1 and a['actual_attachment_receipt'] is not None and r['event'] in a.get('item_ids', []), 'random-clear audit must consume shared special pool')
            used_attempts.add(identity); providers.add(a['provider'])
        require(providers == {'opus', 'sol'}, 'dual strong audit required')
    require(all(c['verified'] is True and c['strong_confirmed'] is True for c in decision_changes), 'consequential Luna leads need strong confirmation')
    s['checkpoint_summary'] = {'confirmed_decision_changes': len(decision_changes),
                               'random_clear_confirmations': random_clear_confirmations}
    if not decision_changes:
        s['stopped'] = 'STOP_CHECKPOINTS_NO_NEW_VALUE_KEEP_FINAL'
    return s

"""Compare full leaked intervals on identical OCR truth, never box recall."""
import hashlib
import json


def _identity(track):
    return json.dumps({key: track[key] for key in ('text', 'texts', 'first', 'last', 'observations')},
                      sort_keys=True, separators=(',', ':'))


def interval_complementarity(baseline, candidate, kind='natural'):
    before = {_identity(track): track for track in baseline[kind]}
    after = {_identity(track): track for track in candidate[kind]}
    if len(before) != len(baseline[kind]) or len(after) != len(candidate[kind]) or before.keys() != after.keys():
        raise ValueError('Complementarity requires identical, unique interval truth')
    rows = candidate['presentation']
    guards = candidate['frame_guards']
    if len(rows) != len(guards):
        raise ValueError('Candidate frame guards do not account for presentation')
    details = []
    for key, track in before.items():
        if not track['leaked']:
            continue
        current = after[key]
        protected = any(row['protected'] or row['state'] != 'LIVE' or row['slate']
                        for row in rows[track['first']:track['last'] + 1])
        fidelity_failed = any(guard is None or not guard['pass']
                              for guard in guards[track['first']:track['last'] + 1])
        if track['last'] >= len(rows):
            raise ValueError('Interval extends past candidate presentation evidence')
        details.append({'interval_sha256': hashlib.sha256(key.encode()).hexdigest(),
                        'text': track['text'], 'first': track['first'], 'last': track['last'],
                        'baseline_leak_frames': track['leak_frames'],
                        'candidate_leak_frames': current['leak_frames'],
                        'raw_recovered': not current['leaked'],
                        'protected_in_interval': protected,
                        'fidelity_failed_in_interval': fidelity_failed,
                        'guarded_recovered': not current['leaked'] and not protected and not fidelity_failed})
    newly_leaked = sum(not track['leaked'] and after[key]['leaked'] for key, track in before.items())
    total = len(details)
    raw = sum(row['raw_recovered'] for row in details)
    guarded = sum(row['guarded_recovered'] for row in details)
    return {'kind': kind, 'baseline_leaked_intervals': total,
            'raw_recovered_intervals': raw, 'raw_recovered_fraction': raw / total if total else None,
            'guarded_recovered_intervals': guarded,
            'new_raw_leaked_intervals': newly_leaked, 'raw_net_hidden_interval_change': raw - newly_leaked,
            'guarded_recovered_fraction': guarded / total if total else None,
            'rejected_protected_intervals': sum(row['raw_recovered'] and row['protected_in_interval'] for row in details),
            'rejected_fidelity_intervals': sum(row['raw_recovered'] and row['fidelity_failed_in_interval'] for row in details), 'intervals': details,
            'scope': 'Complete baseline leaked intervals made unreadable to all three output judges; '
                     'guarded credit requires every frame of the interval to remain LIVE with passing real-video fidelity guards.'}

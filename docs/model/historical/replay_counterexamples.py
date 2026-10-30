"""Replay TLC mutation traces through unmodified, public Python interfaces."""
import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def traces(path):
    text = path.read_text()
    states = []
    for match in re.finditer(r'^State (\d+): <([^\n]+)>\n(.*?)(?=^State \d+:|^\d+ states generated|\Z)', text, re.M | re.S):
        values = {}
        for key, raw in re.findall(r'^/\\ (\w+) = (.*)$', match[3], re.M):
            if raw in ('TRUE', 'FALSE'):
                value = raw == 'TRUE'
            elif raw.startswith('"'):
                value = json.loads(raw)
            elif raw.startswith('<<') or raw.startswith('{'):
                value = re.findall(r'"([^\"]+)"', raw)
            else:
                value = int(raw)
            values[key] = value
        states.append((int(match[1]) - 1, match[2].split()[0], values))
    assert states, f'No TLC trace in {path}'
    return states


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.source))
    from shield.control import Control
    from shield.twitch.events import ShieldEvents
    expected_source = args.source / 'shield/twitch/events.py'
    assert Path(sys.modules['shield.twitch.events'].__file__).resolve() == expected_source.resolve()
    print('Imported parent public interfaces:', args.source)
    for relative in ('shield/control.py', 'shield/twitch/events.py'):
        path = args.source / relative
        print('SHA256', relative, hashlib.sha256(path.read_bytes()).hexdigest())
    start = datetime(2026, 10, 29, tzinfo=timezone.utc).timestamp()
    stamp = {'hold': 1, 'ownerResume': 2, 'modResume': 3,
             'shieldBegin': 2, 'shieldEnd': 3, 'viewerHold': 3}

    def envelope(mid):
        topic = {'shieldBegin': 'channel.shield_mode.begin',
                 'shieldEnd': 'channel.shield_mode.end'}.get(mid, 'channel.chat.message')
        actor = '1' if mid == 'ownerResume' else '3' if mid == 'viewerHold' else '2'
        text = '!shield resume' if mid.endswith('Resume') else '!shield hold'
        return {'metadata': {'message_id': mid, 'message_type': 'notification',
                'message_timestamp': datetime.fromtimestamp(start + stamp[mid] - 1, timezone.utc).isoformat(),
                'subscription_type': topic, 'subscription_version': '1'},
                'payload': {'subscription': {'type': topic, 'version': '1', 'status': 'enabled',
                    'condition': {'broadcaster_user_id': '1'}},
                    'event': {'broadcaster_user_id': '1', 'chatter_user_id': actor,
                              'badges': [{'set_id': 'moderator', 'id': '1'}] if actor == '2' else [],
                              'message': {'text': text}}}}

    for case in ('authority', 'replay', 'coverage'):
        states = traces(args.evidence / case / 'tlc.out')
        clock = [start]
        control = Control()
        calls = []
        current = [None]
        command_counts = Counter()

        def hold(active, source, reason, now):
            calls.append({'active': active, 'source': source, 'reason': reason, 'at': now})
            if source in ('chat', 'shield-mode'):
                command_counts[current[0]] += 1
            return control.set_hold(active, source, reason, now)

        events = ShieldEvents('1', hold, started_at=start, clock=lambda: clock[0], capacity=1, max_age=2)
        print('\nCASE', case, 'steps', len(states) - 1)
        print(json.dumps({'step': 0, 'action': 'Init', 'phase': events.phase, 'mode': control.state}))
        final_result = None
        for index, action, state in states[1:]:
            before = len(calls)
            if action == 'Welcome':
                result = events.welcome('synthetic-' + str(index))
            elif action == 'Ready':
                result = events.ready()
            elif action == 'Tick':
                clock[0] = start + state['now'] - 1
                result = None
            elif action == 'Coverage':
                result = control.update_coverage(state['coverage'], 'synthetic-coverage', clock[0])
            elif action == 'LocalHold':
                result = control.set_hold(state['local'], 'local', 'synthetic-local', clock[0])
            elif action == 'Reconnect':
                result = events.reconnect('wss://eventsub.wss.twitch.tv/ws?session=synthetic')
            elif action == 'Fault':
                result = events.fault('synthetic-fault', revoked=state['revoked'])
            elif action == 'Deliver':
                # Each shortest mutation path admits one ID in the destination.
                assert len(state['seen']) == 1
                current[0] = state['seen'][0]
                result = events.accept(envelope(current[0]))
            else:
                raise AssertionError(f'Unmapped TLC action: {action}')
            final_result = result
            print(json.dumps({'step': index, 'action': action, 'id': current[0] if action == 'Deliver' else None,
                              'return': result, 'phase': events.phase, 'mode': control.state,
                              'remembered': events.remembered, 'new_callbacks': calls[before:]}))
            assert events.phase == state['phase'], (case, index, 'phase')
            assert events.remembered <= 1
            if case != 'coverage' or index != states[-1][0]:
                assert control.state == state['mode'], (case, index, 'mode')
            # The replay mutant clears the cache at step 4; restored Python
            # must diverge there by retaining it, before rejecting step 7.
            if case == 'replay' and action == 'Reconnect':
                assert len(state['seen']) == 0 and events.remembered == 1
            if index != states[-1][0] and not (case == 'replay' and index >= 4):
                assert events.remembered == len(state['seen']), (case, index, 'remembered')
        if case == 'authority':
            assert final_result == 'ignored'
            assert command_counts['modResume'] == 0
            print('PASS: restored Python correctly rejects moderator resume; no release callback.')
        elif case == 'replay':
            assert final_result in ('duplicate', 'invalid', 'expired')
            assert sum(command_counts.values()) == 1, command_counts
            assert max(command_counts.values()) == 1, command_counts
            print('PASS: restored Python correctly rejects repeated command after reconnect:', final_result)
        else:
            assert states[-1][2]['mode'] == 'LIVE' and not states[-1][2]['coverage']
            assert control.state == 'PROTECT'
            print('PASS: restored Python correctly retains PROTECT with coverage missing.')
    print('\nRESULT: 3/3 mutation-counterexample replays rejected correctly by restored Python.')


if __name__ == '__main__':
    main()

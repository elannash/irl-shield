"""Replay R1 counterexamples through unmodified public Control/ShieldEvents APIs.

Inputs are source snapshots, not imported test helpers. There are no sockets,
threads, production writes, private state reads/writes, or mutant flags.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

SCRATCH = Path('/tmp/agents/irl-shield/m3-r1-model')
EXPECTED = {
    'old': 'c632045a328442afd25ac4103878d1bd067cf0f3d19bb8641eb9e0ee0280c40f',
    'fixed': '907a17f84498b08c9c99ba882d85c3f08db8d173517a3a73ba38e16e8c384bdd',
    'control': '806c51102caea5ba06985831412c89452fd0a000fd5b0343f1535cc5674b244d',
}
START = datetime(2026, 10, 29, tzinfo=timezone.utc).timestamp()


def load(name, path):
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual == EXPECTED[name], (name, actual)
    spec = importlib.util.spec_from_file_location('r1_' + name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    print(json.dumps({'source': name, 'sha256': actual, 'path': str(path)}))
    return module


Control = load('control', SCRATCH / 'source-pre/control.py').Control
Old = load('old', SCRATCH / 'source-pre/events.py').ShieldEvents
Fixed = load('fixed', SCRATCH / 'events-fixed.py').ShieldEvents


def notification(mid, *, topic='channel.chat.message', at=9, text='!shield hold', actor='2'):
    return {'metadata': {'message_id': mid, 'message_type': 'notification',
                        'message_timestamp': datetime.fromtimestamp(START + at, timezone.utc).isoformat(),
                        'subscription_type': topic, 'subscription_version': '1'},
            'payload': {'subscription': {'type': topic, 'version': '1', 'status': 'enabled',
                        'condition': {'broadcaster_user_id': '1'}},
                        'event': {'broadcaster_user_id': '1', 'chatter_user_id': actor,
                        'message': {'text': text}, 'badges': [{'set_id': 'moderator', 'id': '1'}]}}}


class Harness:
    def __init__(self, fixed):
        self.fixed = fixed
        self.control = Control()
        self.control.update_coverage(True, 'synthetic-covered', 0)
        self.events = (Fixed if fixed else Old)('1', self.hold, started_at=START,
                        clock=lambda: START + 10, control_clock=lambda: 0)
        self.origin = self.events.connection_started() if fixed else 1
        # Environment facts are never derived from policy or Control flags.
        self.socket_live = True
        self.socket_session = None
        self.enabled = set()

    def hold(self, active, source, reason, now):
        return self.control.set_hold(active, source, reason, now)

    def welcome(self):
        return self.events.welcome('session-1', **({'generation': self.origin} if self.fixed else {}))

    def begin(self):
        return self.events.begin_reconcile(**({'generation': self.origin, 'session_id': 'session-1'}
                                             if self.fixed else {}))

    def accept(self, envelope, generation=None):
        return self.events.accept(envelope, **({'generation': self.origin if generation is None else generation}
                                               if self.fixed else {}))

    def fault(self):
        self.socket_live = False
        self.socket_session = None
        self.enabled.clear()
        return self.events.fault('synthetic-observed-disconnect')

    def step(self, label):
        print(json.dumps({'version': 'fixed' if self.fixed else 'old', 'step': label,
                          'phase': self.events.phase, 'output': self.control.state,
                          'socket_live': self.socket_live, 'enabled_topics': sorted(self.enabled)}))

    def environment_welcome_and_subscribe(self):
        self.step('TLC state 1: opened socket; awaiting welcome')
        self.socket_session = 'session-1'
        self.step('TLC state 2: queue welcome from origin 1')
        for number, topic in enumerate(('chat', 'begin', 'end'), 3):
            self.enabled.add(topic)
            self.step(f'TLC state {number}: enable {topic} on actual session')

    def ready(self):
        self.socket_session = 'session-1'
        self.enabled = {'chat', 'begin', 'end'}
        self.welcome()
        assert self.events.reconciled(False, self.begin()) is True
        assert self.control.state == 'LIVE'


def stale_callback(fixed, fault_before_welcome=False):
    h = Harness(fixed)
    h.environment_welcome_and_subscribe()
    if fault_before_welcome:
        h.fault()
        h.welcome()
    else:
        h.welcome()
        h.step('TLC state 6: deliver welcome to policy')
        h.fault()
        h.step('TLC state 7: observe socket fault; subscriptions die')
    token = h.begin()
    h.step('TLC state 8: callback begins reconciliation after fault')
    result = h.events.reconciled(False, token)
    h.step('TLC state 9: inactive status completes')
    assert h.socket_live is False and h.enabled == set()
    assert h.control.state == ('HOLD' if fixed else 'LIVE')
    assert result is (not fixed)
    print(json.dumps({'case': 'stale callback', 'fault_before_welcome': fault_before_welcome,
                      'fixed': fixed, 'expected_counterexample': not fixed, 'observed': h.control.state}))


def skew_and_phase(fixed, source, subscribing=False):
    h = Harness(fixed)
    if subscribing:
        h.socket_session = 'session-1'
        h.enabled = {'chat', 'begin', 'end'}
        h.welcome()
    else:
        h.environment_welcome_and_subscribe()
        h.welcome()
        h.step('TLC state 6: deliver welcome to policy')
        token = h.begin()
        h.step('TLC state 7: begin reconciliation')
        assert h.events.reconciled(False, token) is True
        h.step('TLC state 8: inactive status completes; LIVE')
    topic = 'channel.chat.message' if source == 'chat' else 'channel.shield_mode.begin'
    result = h.accept(notification('authorized-hold', topic=topic, at=9 if subscribing else 11))
    h.step('TLC state 9: authorized protective event delivered')
    if subscribing:
        assert h.events.reconciled(source == 'shield', h.begin()) is True
    assert h.control.state == ('HOLD' if fixed else 'LIVE')
    assert result == (('chat-hold' if source == 'chat' else 'shield-begin') if fixed
                      else 'inactive' if subscribing else 'invalid')
    # A fresh broadcaster release is necessary to discharge a fixed chat hold.
    if fixed and source == 'chat':
        assert h.accept(notification('fresh-release', at=11, text='!shield resume', actor='1')) == 'chat-resume'
        assert h.control.state == 'LIVE'
    print(json.dumps({'case': 'phase' if subscribing else 'clock skew', 'source': source,
                      'fixed': fixed, 'admission': result, 'contract': 'HOLD after delivery'}))


def callback_fault(fixed, reason):
    h = Harness(fixed)
    h.ready()
    token = h.begin()
    observed = []

    def hold(active, source, reason=reason, now=0):
        if reason == target:
            h.fault()
            observed.append(len(h.control.transitions))
        return h.control.set_hold(active, source, reason, now)

    target = reason
    h.events.hold = hold
    result = h.events.reconciled(False, token)
    assert len(observed) == 1
    suffix = [transition['to'] for transition in h.control.transitions[observed[0]:]]
    assert h.control.state == ('HOLD' if fixed else 'LIVE')
    assert ('LIVE' not in suffix) is fixed
    assert result is (not fixed)
    print(json.dumps({'case': 'fault before callback effect', 'reason': reason, 'fixed': fixed,
                      'output_after_fault': h.control.state, 'transitions_after_fault': suffix}))


def callback_shield_begin(fixed):
    h = Harness(fixed)
    h.ready()
    token = h.begin()
    observed = []

    def hold(active, source, reason, now):
        if reason == 'twitch-shield-status':
            observed.append(h.accept(notification('callback-begin', topic='channel.shield_mode.begin')))
        return h.control.set_hold(active, source, reason, now)

    h.events.hold = hold
    assert h.events.reconciled(False, token) is True
    assert observed == ['shield-begin']
    assert h.control.state == ('HOLD' if fixed else 'LIVE')
    print(json.dumps({'case': 'Shield begin during inactive-status callback', 'fixed': fixed,
                      'output': h.control.state}))


for fixed in (False, True):
    stale_callback(fixed)
    stale_callback(fixed, fault_before_welcome=True)
    for source in ('shield', 'chat'):
        skew_and_phase(fixed, source)
    skew_and_phase(fixed, 'chat', subscribing=True)
    for reason in ('twitch-shield-status', 'twitch-reconciled'):
        callback_fault(fixed, reason)
    callback_shield_begin(fixed)
callback_fault(True, 'twitch-reconciliation-complete')
print('PASS: both TLC paths replayed old RED/fixed GREEN; phase, callback fault and Shield reentry controls passed')

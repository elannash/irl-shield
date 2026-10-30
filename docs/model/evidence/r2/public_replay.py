"""R2 public-API replay on hash-pinned, unmodified old and frozen source copies.

Only caller-owned synthetic time/environment and public methods are driven.
No sockets, private fields, test helpers, source mutations or production seams.
"""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

SCRATCH = Path('/tmp/agents/irl-shield/m3-r2-model')
EXPECTED = {
    'old': '907a17f84498b08c9c99ba882d85c3f08db8d173517a3a73ba38e16e8c384bdd',
    'fixed': 'aa359f9b70a580b768b755febea8433d77ff1402ee6c70771e1967348c92c082',
    'control': '806c51102caea5ba06985831412c89452fd0a000fd5b0343f1535cc5674b244d',
}
START = datetime(2026, 10, 29, tzinfo=timezone.utc).timestamp()


def load(name, path):
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual == EXPECTED[name], (name, actual)
    spec = importlib.util.spec_from_file_location('r2_' + name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    print(json.dumps({'source': name, 'path': str(path), 'sha256': actual}))
    return module


Control = load('control', SCRATCH / 'source-pre/control.py').Control
Policies = {
    'old': load('old', SCRATCH / 'source-pre/events.py').ShieldEvents,
    'fixed': load('fixed', SCRATCH / 'events-fixed.py').ShieldEvents,
}


def notification(mid, source, active, stamp):
    topic = ('channel.chat.message' if source == 'chat' else
             'channel.shield_mode.begin' if active else 'channel.shield_mode.end')
    metadata = {'message_id': mid, 'message_type': 'notification',
                'subscription_type': topic, 'subscription_version': '1'}
    if isinstance(stamp, (int, float)):
        metadata['message_timestamp'] = datetime.fromtimestamp(START + stamp, timezone.utc).isoformat()
    elif stamp != 'missing':
        metadata['message_timestamp'] = stamp
    return {'metadata': metadata, 'payload': {
        'subscription': {'type': topic, 'version': '1', 'status': 'enabled',
                         'condition': {'broadcaster_user_id': '1'}},
        'event': {'broadcaster_user_id': '1', 'chatter_user_id': '2' if active else '1',
                  'badges': [{'set_id': 'moderator', 'id': '1'}],
                  'message': {'text': '!shield hold' if active else '!shield resume'}}}}


class Harness:
    def __init__(self, version):
        self.version = version
        self.now = 10
        self.control = Control()
        self.control.update_coverage(True, 'synthetic-covered', 0)
        self.socket_live, self.socket_session, self.enabled = True, None, set()
        self.tracing = False
        # Model time 1 is session start; other model values shift by START.
        self.events = Policies[version]('1', self.hold, started_at=START + 1,
            clock=lambda: START + self.now, control_clock=lambda: self.now)
        self.generation = self.events.connection_started()

    def hold(self, active, source, reason, now):
        if self.tracing and reason == 'twitch-reconciliation-complete':
            self.step(13, 'CheckConnection: ready before guard callback', 'HOLD')
        result = self.control.set_hold(active, source, reason, now)
        if self.tracing and reason == 'twitch-reconciled':
            self.step(12, 'ApplyConnectionRelease: connection FALSE; protective hold persists', 'HOLD')
        if self.tracing and reason == 'twitch-reconciliation-complete':
            self.step(14, 'ApplyGuardRelease: separate guard FALSE; protective hold persists', 'HOLD')
        return result

    def accept(self, mid, source, active, stamp):
        return self.events.accept(notification(mid, source, active, stamp), generation=self.generation)

    def step(self, number, action, expected):
        assert self.control.state == expected, (self.version, number, self.control.state, expected)
        print(json.dumps({'version': self.version, 'TLC_state': number, 'action': action,
            'local_receipt_time': self.now, 'phase': self.events.phase,
            'output': self.control.state, 'socket_live': self.socket_live,
            'enabled_topics': sorted(self.enabled)}))

    def subscribe(self, trace=False):
        if trace:
            self.step(1, 'Init: socket opened; awaiting welcome', 'HOLD')
        self.socket_session = 'session-1'
        if trace:
            self.step(2, 'QueueWelcome: environment queues origin 1', 'HOLD')
        # Matches the actual TLC trace: chat, end, begin.
        for number, topic in enumerate(('chat', 'end', 'begin'), 3):
            self.enabled.add(topic)
            if trace:
                self.step(number, 'EnableSubscription: ' + topic, 'HOLD')
        assert self.events.welcome('session-1', generation=self.generation) is True
        if trace:
            self.step(6, 'Welcome: origin 1 callback delivered', 'HOLD')

    def begin(self):
        token = self.events.begin_reconcile(generation=self.generation, session_id='session-1')
        assert token is not None
        return token

    def ready(self):
        self.subscribe()
        assert self.events.reconciled(False, self.begin()) is True
        assert self.control.state == 'LIVE'


def tlc_trace(version):
    h = Harness(version)
    h.subscribe(trace=True)
    token = h.begin()
    h.step(7, 'BeginReconcile: truthful inactive snapshot, revision 0', 'HOLD')
    assert h.accept('trace-hold', 'shield', True, 20) == 'shield-begin'
    h.step(8, 'DeliverHold: raw Twitch 20; local receipt 10; obligation TRUE', 'HOLD')
    h.tracing = True
    # These three TLC microsteps have no public callback effect in this trace:
    # the changed revision skips inactive status. They map to one public branch,
    # not three independently observable API operations.
    for number, action in ((9, 'StartCompletion: revision changed; applyStatus FALSE'),
                           (10, 'ApplyStatus: inactive callback skipped'),
                           (11, 'CheckStatus: current token; no repair needed')):
        h.step(number, action + ' [source-mapped stuttering microstep]', 'HOLD')
    assert h.events.reconciled(False, token) is True
    h.tracing = False
    h.step(15, 'FinishCompletion: public reconciled returned TRUE', 'HOLD')
    h.now = 11
    h.step(16, 'ClockAdvance: local receipt time 10 -> 11', 'HOLD')
    result = h.accept('trace-older-end', 'shield', False, 19)
    assert result == ('shield-end' if version == 'old' else 'expired')
    # The obligation is decided by literal remote order 19 < 20, independently
    # of the implementation's callback or timestamp storage.
    independent_obligation = 19 <= 20
    assert independent_obligation
    h.step(17, 'ReleaseReceived: raw 19 older than held raw 20; obligation stays TRUE',
           'LIVE' if version == 'old' else 'HOLD')
    print(json.dumps({'case': 'exact TLC trace', 'version': version,
        'release_result': result, 'independent_obligation': independent_obligation,
        'AuthorizedShieldBeginPersists': 'RED' if version == 'old' else 'GREEN'}))


def ordering_table(version):
    for source in ('chat', 'shield'):
        for skew in (10, 29):
            hold_stamp = 10 + skew
            for relation, release_stamp in (('older', hold_stamp - 1), ('equal', hold_stamp)):
                h = Harness(version)
                h.ready()
                assert h.accept('hold', source, True, hold_stamp) == (
                    'chat-hold' if source == 'chat' else 'shield-begin')
                assert h.control.state == 'HOLD'
                h.now = 11
                outcome = h.accept('release', source, False, release_stamp)
                released = 'chat-resume' if source == 'chat' else 'shield-end'
                assert outcome == (released if version == 'old' else 'expired')
                assert h.control.state == ('LIVE' if version == 'old' else 'HOLD')
                assert h.accept('strictly-newer', source, False, hold_stamp + 1) == released
                assert h.control.state == 'LIVE'
                print(json.dumps({'case': 'bounded Twitch ordering', 'version': version,
                    'source': source, 'hold_stamp': hold_stamp, 'hold_receipt': 10,
                    'release_stamp': release_stamp, 'release_receipt': 11,
                    'relation': relation, 'release_result': outcome,
                    'safety': 'RED' if version == 'old' else 'GREEN',
                    'strictly_newer_release': 'LIVE'}))


def separate_classes(version):
    for source in ('chat', 'shield'):
        released = 'chat-resume' if source == 'chat' else 'shield-end'
        for raw in ('missing', 'not-a-timestamp', '2026-10-29T00:00:01', 0):
            h = Harness(version)
            h.ready()
            assert h.accept('unusable-hold', source, True, raw) in ('chat-hold', 'shield-begin')
            assert h.control.state == 'HOLD'
            h.now = 11
            assert h.accept('receipt-tie', source, False, 10) == 'expired'
            assert h.control.state == 'HOLD'
            assert h.accept('newer-than-receipt', source, False, 11) == released
            assert h.control.state == 'LIVE'
            print(json.dumps({'case': 'unusable raw stamp; receipt fallback', 'version': version,
                'source': source, 'raw_class': raw, 'receipt_tie': 'HOLD', 'newer': 'LIVE'}))
        h = Harness(version)
        h.ready()
        assert h.accept('extreme-hold', source, True, 100000) in ('chat-hold', 'shield-begin')
        assert h.control.state == 'HOLD'
        h.now = 11
        early = h.accept('early-end', source, False, 11)
        assert early == (released if version == 'old' else 'expired')
        assert h.control.state == ('LIVE' if version == 'old' else 'HOLD')
        tie = h.accept('cap-tie', source, False, 40)
        assert tie == (released if version == 'old' else 'expired')
        assert h.control.state == ('LIVE' if version == 'old' else 'HOLD')
        h.now = 40
        assert h.accept('after-capped-window', source, False, 41) == released
        assert h.control.state == 'LIVE'
        print(json.dumps({'case': 'pathological future; bounded fail-closed delay',
            'version': version, 'source': source, 'raw_hold': 100000, 'hold_receipt': 10,
            'early_result': early, 'cap_tie_result': tie, 'release_at_receipt_40_stamp_41': 'LIVE'}))


for version in ('old', 'fixed'):
    tlc_trace(version)
    ordering_table(version)
    separate_classes(version)
print('PASS: exact TLC path old RED/fixed GREEN; chat+Shield +10/+29 older/equal protected; newer releases succeed; unusable and capped future classes checked')

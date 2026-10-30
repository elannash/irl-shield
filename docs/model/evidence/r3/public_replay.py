"""Stronger R3 bootstrap replay candidate; NOT RUN under the exhausted budget.

All clocks, envelopes and subscription facts are caller-owned synthetic data.
No private state, test helpers, mutations, network or production seams are used.
"""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

SCRATCH = Path('/tmp/agents/irl-shield/m3-r3-model')
EXPECTED = {
    'old': 'aa359f9b70a580b768b755febea8433d77ff1402ee6c70771e1967348c92c082',
    'fixed': '0e90e43f52b3bd9444925469baf96b40d29480ecefd22c4eeb5afdd68bb630fd',
    'control': '806c51102caea5ba06985831412c89452fd0a000fd5b0343f1535cc5674b244d',
}
START = datetime(2026, 10, 29, tzinfo=timezone.utc).timestamp()


def load(name, path):
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual == EXPECTED[name], (name, actual)
    spec = importlib.util.spec_from_file_location('r3_' + name, path)
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


def released(source):
    return 'chat-resume' if source == 'chat' else 'shield-end'


def held(source):
    return 'chat-hold' if source == 'chat' else 'shield-begin'


class Harness:
    def __init__(self, version):
        self.version, self.now = version, 10
        self.control = Control()
        self.control.update_coverage(True, 'synthetic-covered', 0)
        self.enabled, self.socket_session = set(), None
        self.trace = False
        self.events = Policies[version]('1', self.hold, started_at=START + 1,
            clock=lambda: START + self.now, control_clock=lambda: self.now)
        self.generation = self.events.connection_started()

    def hold(self, active, source, reason, now):
        if self.trace and reason == 'twitch-reconciliation-complete':
            self.step(13, 'current token checked; ready before guard callback', 'HOLD')
        if self.trace and reason == 'twitch-reconciled':
            self.step(11, 'status current/revision check [source-mapped microstep]', 'HOLD')
        result = self.control.set_hold(active, source, reason, now)
        if self.trace and reason == 'twitch-shield-status':
            self.step(10, 'truthful active status applied through public callback', 'HOLD')
        if self.trace and reason == 'twitch-reconciled':
            self.step(12, 'connection callback clears its hold', 'HOLD')
        if self.trace and reason == 'twitch-reconciliation-complete':
            self.step(14, 'guard callback clears its hold', 'HOLD')
        return result

    def accept(self, mid, source, active, stamp):
        return self.events.accept(notification(mid, source, active, stamp), generation=self.generation)

    def ordinary(self, mid, stamp):
        envelope = notification(mid, 'chat', True, stamp)
        envelope['payload']['event']['message']['text'] = 'ordinary synthetic message'
        return self.events.accept(envelope, generation=self.generation)

    def step(self, number, action, expected):
        assert self.control.state == expected, (self.version, number, self.control.state, expected)
        print(json.dumps({'version': self.version, 'TLC_state': number, 'action': action,
            'local_receipt_time': self.now, 'phase': self.events.phase,
            'output': self.control.state, 'enabled_topics': sorted(self.enabled)}))

    def observe(self, stamp, kind):
        metadata = notification('metadata-only', 'chat', True, stamp)['metadata']
        metadata['message_type'] = kind
        if self.version == 'fixed':
            self.events.observe_timestamp(metadata)

    def ready(self, active=False):
        self.socket_session = 'session-1'
        self.enabled.update(('chat', 'begin', 'end'))
        assert self.events.welcome(self.socket_session, generation=self.generation) is True
        token = self.events.begin_reconcile(generation=self.generation, session_id=self.socket_session)
        assert token is not None
        assert self.events.reconciled(active, token) is True
        assert self.control.state == ('HOLD' if active else 'LIVE')


def check(h, result, expected_result, expected_state):
    assert result == expected_result, (h.version, result, expected_result)
    assert h.control.state == expected_state, (h.version, h.control.state, expected_state)


def emit(h, case, **facts):
    print(json.dumps({'version': h.version, 'case': case, **facts, 'output': h.control.state}))


def tlc_trace(version):
    h = Harness(version)
    h.step(1, 'socket opened; awaiting welcome', 'HOLD')
    h.socket_session = 'session-1'
    h.step(2, 'welcome queued in caller environment', 'HOLD')
    for number, topic in ((3, 'begin'), (4, 'chat')):
        h.enabled.add(topic)
        h.step(number, topic + ' enabled in caller environment', 'HOLD')
    assert h.events.welcome(h.socket_session, generation=h.generation) is True
    h.step(5, 'queued welcome callback delivered', 'HOLD')
    check(h, h.accept('trace-begin', 'shield', True, 41), 'shield-begin', 'HOLD')
    h.step(6, 'raw begin 41 received at 10; independent obligation TRUE', 'HOLD')
    h.enabled.add('end')
    h.step(7, 'end enabled in caller environment', 'HOLD')
    token = h.events.begin_reconcile(generation=h.generation, session_id=h.socket_session)
    assert token is not None
    h.step(8, 'truthful active status read starts after begin', 'HOLD')
    h.step(9, 'completion selects status callback [source-mapped microstep]', 'HOLD')
    h.trace = True
    # CheckStatus has no public effect on this path; it is inside reconciled.
    # The callback for connection release is its next observable boundary.
    assert h.events.reconciled(True, token) is True
    h.trace = False
    h.step(15, 'public reconciled returned TRUE', 'HOLD')
    h.now = 11
    h.step(16, 'local receipt clock advances from 10 to 11', 'HOLD')
    result = h.accept('trace-older-end', 'shield', False, 40.5)
    check(h, result, 'shield-end' if version == 'old' else 'expired',
          'LIVE' if version == 'old' else 'HOLD')
    h.step(17, 'raw end 40.5 is older than raw begin 41; obligation stays TRUE',
           'LIVE' if version == 'old' else 'HOLD')
    emit(h, 'direct TLC counterexample replay', raw_hold=41, hold_receipt=10,
         raw_release=40.5, release_receipt=11, independent_obligation=True,
         result=result, invariant='RED' if version == 'old' else 'GREEN')


def ordering_boundaries(version):
    for source in ('chat', 'shield'):
        for skew in (29.9, 30, 30.001, 31, 41, 100000):
            raw = 10 + skew
            for relation, stamp in (('older', raw - 0.0005), ('equal', raw)):
                h = Harness(version)
                h.ready()
                check(h, h.accept('hold', source, True, raw), held(source), 'HOLD')
                # Both candidate and immediately newer release fit the +30 rule.
                h.now = max(11, raw - 30 + 0.01)
                result = h.accept('candidate', source, False, stamp)
                old_violates = version == 'old' and skew > 30
                check(h, result, released(source) if old_violates else 'expired',
                      'LIVE' if old_violates else 'HOLD')
                candidate_output = h.control.state
                check(h, h.accept('newer', source, False, raw + 0.001), released(source), 'LIVE')
                emit(h, 'raw ordering boundary', source=source, skew=skew,
                     hold_stamp=raw, hold_receipt=10, release_stamp=stamp,
                     release_receipt=h.now, relation=relation, candidate_result=result,
                     candidate_output=candidate_output, strictly_newer='LIVE')


def unusable_and_old_raw(version):
    for source in ('chat', 'shield'):
        for raw in ('missing', 'unparseable', '2026-10-29T00:00:01', 0, -1000):
            h = Harness(version)
            h.ready()
            check(h, h.accept('hold', source, True, raw), held(source), 'HOLD')
            h.now = 11
            result = h.accept('fresh-raw-9', source, False, 9)
            missing = isinstance(raw, str)
            stays = version == 'old' or missing
            check(h, result, 'expired' if stays else released(source), 'HOLD' if stays else 'LIVE')
            if missing:
                second = h.accept('strictly-after-first', source, False, 9.001)
                check(h, second, 'expired' if version == 'old' else released(source),
                      'HOLD' if version == 'old' else 'LIVE')
            emit(h, 'finite raw retained; missing first release only anchors pending barrier',
                 source=source, raw_class=raw, release_stamp=9, result=result)


def missing_after_high_water(version):
    for source in ('chat', 'shield'):
        for origin in ('ordinary-chat', 'cross-source-release', 'cross-source-hold-and-release'):
            for relation, stamp in (('older', 38.5), ('equal', 39)):
                h = Harness(version)
                h.ready()
                other = 'shield' if source == 'chat' else 'chat'
                if origin == 'ordinary-chat':
                    assert h.ordinary('observed', 39) == 'ignored'
                else:
                    if origin == 'cross-source-hold-and-release':
                        check(h, h.accept('other-hold', other, True, 38), held(other), 'HOLD')
                    check(h, h.accept('other-release', other, False, 39), released(other), 'LIVE')
                check(h, h.accept('missing-hold', source, True, 'missing'), held(source), 'HOLD')
                h.now = 11
                result = h.accept('candidate', source, False, stamp)
                check(h, result, released(source) if version == 'old' else 'expired',
                      'LIVE' if version == 'old' else 'HOLD')
                candidate_output = h.control.state
                check(h, h.accept('newer', source, False, 39.001), released(source), 'LIVE')
                emit(h, 'missing snapshots prior independent global raw high water',
                     source=source, high_water_origin=origin, prior_raw_high_water=39,
                     relation=relation, release_stamp=stamp, candidate_result=result,
                     candidate_output=candidate_output, strictly_newer='LIVE')


def rejected_future_does_not_move_held_barrier(version):
    for source in ('chat', 'shield'):
        h = Harness(version)
        h.ready()
        assert h.ordinary('observed-39', 39) == 'ignored'
        check(h, h.accept('missing-at-39', source, True, 'missing'), held(source), 'HOLD')
        h.now = 11
        check(h, h.accept('rejected-future', source, False, 100000), 'invalid', 'HOLD')
        check(h, h.accept('newer-than-held-39', source, False, 40), released(source), 'LIVE')
        check(h, h.accept('missing-after-future', source, True, 'missing'), held(source), 'HOLD')
        candidate = h.accept('older-than-seen-future', source, False, 41)
        check(h, candidate, released(source) if version == 'old' else 'expired',
              'LIVE' if version == 'old' else 'HOLD')
        candidate_output = h.control.state
        h.now = 99970.01
        tie = h.accept('equal-to-seen-future', source, False, 100000)
        check(h, tie, released(source) if version == 'old' else 'expired',
              'LIVE' if version == 'old' else 'HOLD')
        check(h, h.accept('newer-than-seen-future', source, False, 100000.001), released(source), 'LIVE')
        emit(h, 'future release updates global evidence, never existing source barrier',
             source=source, rejected_future=100000, first_newer_40='LIVE',
             next_missing_candidate_41=candidate, candidate_output=candidate_output,
             equal_to_new_barrier=tie, final_strictly_newer='LIVE')


def invalid_envelope_does_not_contaminate(version):
    for source in ('chat', 'shield'):
        for invalid in ('event-broadcaster', 'condition-broadcaster', 'subscription-status'):
            h = Harness(version)
            h.ready()
            envelope = notification('invalid-high-stamp', 'chat', True, 100000)
            if invalid == 'event-broadcaster':
                envelope['payload']['event']['broadcaster_user_id'] = 'foreign'
            elif invalid == 'condition-broadcaster':
                envelope['payload']['subscription']['condition']['broadcaster_user_id'] = 'foreign'
            else:
                envelope['payload']['subscription']['status'] = 'disabled'
            assert h.events.accept(envelope, generation=h.generation) == 'invalid'
            check(h, h.accept('missing-first-valid', source, True, 'missing'), held(source), 'HOLD')
            h.now = 11
            result = h.accept('fresh-9', source, False, 9)
            check(h, result, 'expired', 'HOLD')
            second = h.accept('strictly-after-9', source, False, 9.001)
            check(h, second, 'expired' if version == 'old' else released(source),
                  'HOLD' if version == 'old' else 'LIVE')
            emit(h, 'invalid envelope excluded from raw high water', source=source,
                 invalid=invalid, invalid_stamp=100000, first_release_stamp=9,
                 first_result=result, later_release_stamp=9.001, later_result=second)


def socket_metadata_and_pending(version):
    for source in ('chat', 'shield'):
        for kind in ('session_welcome', 'session_keepalive', 'session_reconnect', 'handover_welcome'):
            h = Harness(version)
            if kind == 'handover_welcome':
                h.ready()
                assert h.events.reconnect('wss://eventsub.wss.twitch.tv/ws', generation=h.generation) is True
                h.observe(29, 'session_welcome')
                assert h.events.handed_over('session-2', generation=h.generation) is True
            else:
                h.observe(29, kind)
                h.ready()
            check(h, h.accept('missing-after-frame', source, True, 'missing'), held(source), 'HOLD')
            h.now = 11
            result = h.accept('older-than-frame', source, False, 25)
            check(h, result, released(source) if version == 'old' else 'expired',
                  'LIVE' if version == 'old' else 'HOLD')
            check(h, h.accept('strictly-newer-than-frame', source, False, 29.001), released(source), 'LIVE')
            emit(h, 'socket metadata seeds missing hold', source=source, kind=kind,
                 observed_stamp=29, older_result=result, strictly_newer='LIVE')
        for anchor in ('first-release', 'keepalive'):
            h = Harness(version)
            h.ready()
            check(h, h.accept('unseeded-missing', source, True, 'missing'), held(source), 'HOLD')
            h.now = 11
            if anchor == 'keepalive':
                h.observe(25, 'session_keepalive')
            result = h.accept('first-or-equal-release', source, False, 25)
            check(h, result, released(source) if version == 'old' else 'expired',
                  'LIVE' if version == 'old' else 'HOLD')
            check(h, h.accept('strictly-after-anchor', source, False, 26), released(source), 'LIVE')
            emit(h, 'pending missing hold anchors first stamp and keeps HOLD', source=source,
                 anchor=anchor, anchor_stamp=25, first_or_equal_result=result, strictly_newer='LIVE')


def helix_active_is_missing_hold(version):
    for seeded in (False, True):
        h = Harness(version)
        if seeded:
            h.observe(29, 'session_welcome')
        h.ready(active=True)
        h.now = 11
        result = h.accept('helix-first-release', 'shield', False, 25)
        check(h, result, 'shield-end' if version == 'old' else 'expired',
              'LIVE' if version == 'old' else 'HOLD')
        if seeded:
            tie = h.accept('helix-equal-known', 'shield', False, 29)
            check(h, tie, 'shield-end' if version == 'old' else 'expired',
                  'LIVE' if version == 'old' else 'HOLD')
        newer = 29.001 if seeded else 26
        check(h, h.accept('helix-strictly-newer', 'shield', False, newer), 'shield-end', 'LIVE')
        emit(h, 'Helix active reconciliation asserts missing-stamp Shield barrier',
             seeded=seeded, first_release=25, first_result=result, later_stamp=newer, later='LIVE')


for version in ('old', 'fixed'):
    tlc_trace(version)
    ordering_boundaries(version)
    unusable_and_old_raw(version)
    missing_after_high_water(version)
    rejected_future_does_not_move_held_barrier(version)
    invalid_envelope_does_not_contaminate(version)
    socket_metadata_and_pending(version)
    helix_active_is_missing_hold(version)
print('PASS: actual old RED/fixed GREEN; raw boundaries, pending bootstrap, socket metadata, Helix active, prior high water, future isolation and fresh newer releases')

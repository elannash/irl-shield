"""Public-call replay instructions for the conductor; not executed by this child.

No transport imports, sockets, user data, or production mutations. The functions
are separate so existing final tests can replay the same calls without launching
an additional standalone harness. Each constructor starts a fresh policy instance.
"""
from datetime import datetime, timezone

from shield.control import Control
from shield.twitch.events import ShieldEvents


START = datetime(2026, 10, 29, tzinfo=timezone.utc).timestamp()


def session():
    control = Control()
    calls = []

    def hold(active, source, reason, now):
        calls.append((active, source))
        return control.set_hold(active, source, reason, now)

    events = ShieldEvents('1', hold, started_at=START, clock=lambda: START,
                          capacity=1, max_age=2, control_clock=lambda: 0)
    return control, events, calls


def notification(mid, *, topic='channel.chat.message', text='!shield hold',
                 actor='2', at=START):
    return {
        'metadata': {'message_id': mid, 'message_type': 'notification',
                     'message_timestamp': datetime.fromtimestamp(at, timezone.utc).isoformat(),
                     'subscription_type': topic, 'subscription_version': '1'},
        'payload': {
            'subscription': {'type': topic, 'version': '1', 'status': 'enabled',
                             'condition': {'broadcaster_user_id': '1'}},
            'event': {'broadcaster_user_id': '1', 'chatter_user_id': actor,
                      'message': {'text': text}, 'badges': [{'set_id': 'moderator', 'id': '1'}]},
        },
    }


def shortest_counterexample():
    control, events, calls = session()  # TLC state 1 / transition 0: Init.
    assert control.state == 'HOLD'
    token = events.begin_reconcile()  # TLC state 2 / transition 1.
    assert token == (0, 0) and events.phase == 'reconciling'
    assert events.reconciled(True, token) is True  # TLC state 3 / transition 2.
    assert events.phase == 'ready'
    assert control.state == 'HOLD'  # Mutant instead reaches PROTECT.
    assert calls[-2:] == [(True, 'shield_mode'), (False, 'twitch-connection')]


def inactive_status_races_new_shield_and_preserves_other_sources():
    control, events, _ = session()
    control.update_coverage(True, 'synthetic-fresh', 0)
    events.welcome('synthetic-startup')
    token = events.begin_reconcile()
    assert events.accept(notification('chat')) == 'chat-hold'
    events.clock = lambda: START + 1
    assert events.accept(notification('begin', topic='channel.shield_mode.begin',
                                      at=START + 1)) == 'shield-begin'
    control.set_hold(True, source='local')
    assert events.reconciled(False, token) is True
    assert control.state == 'HOLD'
    control.set_hold(False, source='local')
    assert control.state == 'HOLD'
    events.clock = lambda: START + 2
    assert events.accept(notification('resume', text='!shield resume', actor='1',
                                      at=START + 2)) == 'chat-resume'
    assert control.state == 'HOLD'  # Newer Shield begin survived inactive status.
    events.clock = lambda: START + 3
    assert events.accept(notification('end', topic='channel.shield_mode.end',
                                      at=START + 3)) == 'shield-end'
    assert control.state == 'LIVE'


def independent_chat_and_local_sources():
    # Hold removal order must not hide a lost source behind another active hold.
    for source in ('chat', 'local'):
        control, events, _ = session()
        control.update_coverage(True, 'synthetic-fresh', 0)
        token = events.begin_reconcile()
        if source == 'chat':
            assert events.accept(notification('chat')) == 'chat-hold'
        else:
            control.set_hold(True, source='local')
        assert events.reconciled(False, token) is True
        assert control.state == 'HOLD'


def stale_completion_failure_and_planned_handover():
    control, events, calls = session()
    control.update_coverage(True, 'synthetic-fresh', 0)
    events.welcome('synthetic-startup')
    token = events.begin_reconcile()
    assert events.reconciled('false', token) is False
    assert events.phase == 'reconciling' and control.state == 'HOLD'
    assert events.reconciled(False, token) is True
    assert control.state == 'LIVE'
    transitions, before_calls = control.transitions, len(calls)
    assert events.reconnect('wss://eventsub.wss.twitch.tv/ws?session=synthetic') is True
    assert events.phase == 'handover' and control.state == 'LIVE'
    events.handed_over('synthetic-migrated')
    assert events.phase == 'ready' and control.state == 'LIVE'
    assert control.transitions == transitions and len(calls) == before_calls
    stale = events.begin_reconcile()
    events.fault('synthetic-outage')
    assert control.state == 'HOLD' and not events.reconciliation_current(stale)
    events.welcome('synthetic-recovery')
    fresh = events.begin_reconcile()
    assert events.reconciled(False, stale) is False
    assert events.phase == 'reconciling' and control.state == 'HOLD'
    assert events.reconciled(False, fresh) is True
    assert control.state == 'LIVE'
    revoked = events.begin_reconcile()
    events.fault('synthetic-revoked', revoked=True)
    assert events.begin_reconcile() is None
    assert events.reconciled(False, revoked) is False
    assert events.phase == 'revoked' and control.state == 'HOLD'


if __name__ == '__main__':
    shortest_counterexample()
    inactive_status_races_new_shield_and_preserves_other_sources()
    independent_chat_and_local_sources()
    stale_completion_failure_and_planned_handover()

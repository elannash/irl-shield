"""Authorization, hold isolation and replay protection through the adapter interface."""
from datetime import datetime, timezone
import unittest

from shield.control import Control
from shield.twitch.events import ShieldEvents

START = datetime(2026, 10, 29, tzinfo=timezone.utc).timestamp()


def notification(mid='one', text='!shield hold', actor='2', badge='moderator',
                 topic='channel.chat.message', at=START + 1):
    event = {'broadcaster_user_id': '1', 'chatter_user_id': actor,
             'chatter_user_name': 'Broadcaster', 'message': {'text': text},
             'badges': [{'set_id': badge, 'id': '1', 'info': ''}] if badge else []}
    return {'metadata': {'message_id': mid, 'message_type': 'notification',
                         'message_timestamp': datetime.fromtimestamp(at, timezone.utc).isoformat(),
                         'subscription_type': topic, 'subscription_version': '1'},
            'payload': {'subscription': {'type': topic, 'version': '1', 'status': 'enabled',
                                         'condition': {'broadcaster_user_id': '1'}}, 'event': event}}


def adapter(**kwargs):
    control = Control()
    control.update_coverage(True, 'fresh', 0)
    def hold(active, source, reason, now):
        return control.set_hold(active, source, reason, now)
    events = ShieldEvents('1', hold, started_at=START, clock=lambda: START + 10, **kwargs)
    events.welcome('session')
    events.reconciled(False, events.begin_reconcile())
    return control, events


class ChatControl(unittest.TestCase):
    def test_tlc_release_clobber_shortest_path_retains_active_shield(self):
        control = Control()
        def hold(active, source, reason, now):
            return control.set_hold(active, source, reason, now)
        events = ShieldEvents('1', hold, started_at=0, clock=lambda: 0,
                              capacity=1, max_age=2, control_clock=lambda: 0)
        self.assertEqual(control.state, 'HOLD')
        snapshot = events.begin_reconcile()
        self.assertEqual(snapshot, (0, 0))
        self.assertTrue(events.reconciled(True, snapshot))
        self.assertEqual(events.phase, 'ready')
        self.assertEqual(control.state, 'HOLD')

    def test_reconciliation_release_preserves_newer_shield_chat_and_local_holds(self):
        for source in ('local', 'chat'):
            single, policy = adapter()
            token = policy.begin_reconcile()
            if source == 'local':
                single.set_hold(True, source='local')
            else:
                policy.accept(notification('single-chat'))
            self.assertTrue(policy.reconciled(False, token))
            self.assertEqual(single.state, 'HOLD', source + ' was cleared by reconciliation')
        control, events = adapter()
        snapshot = events.begin_reconcile()
        events.accept(notification('chat-during-query'))
        events.accept(notification('shield-during-query', topic='channel.shield_mode.begin', at=START + 2))
        control.set_hold(True, source='local')
        self.assertTrue(events.reconciled(False, snapshot))
        self.assertEqual(control.state, 'HOLD')
        control.set_hold(False, source='local')
        events.accept(notification('owner-after-query', '!shield resume', actor='1', at=START + 3))
        self.assertEqual(control.state, 'HOLD')
        events.accept(notification('shield-after-query', topic='channel.shield_mode.end', at=START + 4))
        self.assertEqual(control.state, 'LIVE')
        stale = events.begin_reconcile()
        events.fault('another-outage')
        self.assertFalse(events.reconciled(False, stale))
        self.assertEqual(control.state, 'HOLD')

    def test_only_broadcaster_resumes_and_cannot_release_other_holds(self):
        control, events = adapter()
        self.assertEqual(events.accept(notification()), 'chat-hold')
        self.assertEqual(control.state, 'HOLD')
        self.assertEqual(events.accept(notification('mod-resume', '!shield resume', at=START + 2)), 'ignored')
        control.set_hold(True, source='local')
        events.accept(notification('shield-on', topic='channel.shield_mode.begin'))
        self.assertEqual(events.accept(notification('owner-resume', '!shield resume', actor='1', at=START + 3)), 'chat-resume')
        self.assertEqual(control.state, 'HOLD')
        events.accept(notification('shield-off', topic='channel.shield_mode.end', at=START + 4))
        self.assertEqual(control.state, 'HOLD')
        self.assertEqual(control.set_hold(False, source='local'), 'LIVE')
        events.accept(notification('fake-owner', actor='3', badge='broadcaster'))
        self.assertEqual(control.state, 'LIVE')

    def test_replay_floor_survives_reconnect_capacity_and_expiry(self):
        control, events = adapter(capacity=1)
        hold = notification()
        events.accept(hold)
        events.accept(notification('resume', '!shield resume', actor='1', at=START + 2))
        self.assertEqual(control.state, 'LIVE')
        self.assertTrue(events.reconnect('wss://eventsub.wss.twitch.tv/ws?session=synthetic'))
        self.assertEqual(control.state, 'LIVE')
        events.handed_over('new-session')
        self.assertEqual(events.accept(hold), 'invalid')
        self.assertEqual(events.accept(notification('resume', '!shield resume', actor='1', at=START + 2)), 'duplicate')
        self.assertEqual(control.state, 'LIVE')
        self.assertEqual(events.remembered, 1)
        events.clock = lambda: START + 1000
        self.assertEqual(events.accept(hold), 'invalid')
        self.assertEqual(events.remembered, 0)
        self.assertEqual(events.accept(notification('old', at=START - 1)), 'invalid')

    def test_revocation_latches_and_foreign_reconnect_never_connects(self):
        control, events = adapter()
        for url in ['wss://eventsub.wss.twitch.tv.evil/ws', 'ws://eventsub.wss.twitch.tv/ws',
                    'wss://user@eventsub.wss.twitch.tv/ws', 'wss://eventsub.wss.twitch.tv:443/ws',
                    'ws://127.0.0.1:9876/ws']:
            self.assertFalse(events.reconnect(url))
            self.assertEqual(control.state, 'HOLD')
        events.fault('authorization-revoked', revoked=True)
        events.welcome('replacement')
        self.assertFalse(events.reconciled(False, events.begin_reconcile()))
        self.assertEqual(events.phase, 'revoked')
        self.assertEqual(events.accept(notification('resume', '!shield resume', actor='1')), 'inactive')
        self.assertEqual(control.state, 'HOLD')

    def test_untrusted_chat_fields_and_out_of_order_releases_cannot_resume(self):
        control, events = adapter()
        for key, value in [('source_broadcaster_user_id', '9'), ('broadcaster_user_id', '9'),
                           ('chatter_user_id', '9')]:
            msg = notification(key, badge='broadcaster')
            msg['payload']['event'][key] = value
            events.accept(msg)
            self.assertEqual(control.state, 'LIVE')
        events.accept(notification('new-hold', actor='1', at=START + 4))
        events.accept(notification('old-resume', '!shield resume', actor='1', at=START + 3))
        self.assertEqual(control.state, 'HOLD')
        events.accept(notification('shield-new', topic='channel.shield_mode.begin', at=START + 5))
        events.accept(notification('shield-old', topic='channel.shield_mode.end', at=START + 4))
        events.accept(notification('owner', '!shield resume', actor='1', at=START + 6))
        self.assertEqual(control.state, 'HOLD')


"""Authorization, hold isolation and replay protection through the adapter interface."""
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Event
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
    events.connection_started()
    events.welcome('session', generation=events.generation)
    events.reconciled(False, events.begin_reconcile(generation=events.generation, session_id=events.session_id))
    return control, events


class ChatControl(unittest.TestCase):
    def test_authorized_holds_survive_clock_skew_and_unparseable_timestamps(self):
        for topic, outcome in [('channel.chat.message', 'chat-hold'),
                               ('channel.shield_mode.begin', 'shield-begin')]:
            for stamp in (START + 10.2, START + 20, START + 100000,
                          START - 100000, 'host-ahead', 'malformed', 'naive', 'missing'):
                with self.subTest(topic=topic, stamp=stamp):
                    control, events = adapter()
                    msg = notification(topic=topic, at=stamp if isinstance(stamp, float) else START + 1)
                    if stamp == 'host-ahead':
                        events.clock = lambda: START + 1000
                    elif stamp == 'malformed':
                        msg['metadata']['message_timestamp'] = 'not-a-timestamp'
                    elif stamp == 'naive':
                        msg['metadata']['message_timestamp'] = '2026-10-29T00:00:01'
                    elif stamp == 'missing':
                        del msg['metadata']['message_timestamp']
                    self.assertEqual(events.accept(msg, generation=events.generation), outcome)
                    self.assertEqual(control.state, 'HOLD')

    def test_authorized_holds_apply_in_every_connection_phase(self):
        for phase in ('connecting', 'subscribing', 'reconciling', 'ready',
                      'handover', 'disconnected', 'revoked'):
            for topic, outcome in [('channel.chat.message', 'chat-hold'),
                                   ('channel.shield_mode.begin', 'shield-begin')]:
                with self.subTest(phase=phase, topic=topic):
                    control, events = adapter()
                    if phase == 'connecting':
                        events = ShieldEvents('1', lambda active, source, reason, now:
                            control.set_hold(active, source, reason, now),
                            started_at=START, clock=lambda: START + 10)
                    elif phase == 'subscribing':
                        events.connection_started()
                        events.welcome('next-session', generation=events.generation)
                    elif phase == 'reconciling':
                        events.begin_reconcile(generation=events.generation, session_id=events.session_id)
                    elif phase == 'handover':
                        events.reconnect('wss://eventsub.wss.twitch.tv/ws', generation=events.generation)
                    elif phase in ('disconnected', 'revoked'):
                        events.fault(revoked=phase == 'revoked')
                    self.assertEqual(events.phase, phase)
                    self.assertEqual(events.accept(notification(topic=topic), generation=events.generation - 1), outcome)
                    if phase in ('connecting', 'subscribing', 'disconnected'):
                        events.connection_started()
                        events.welcome('recovered', generation=events.generation)
                    if phase not in ('ready', 'handover', 'revoked'):
                        events.reconciled(topic == 'channel.shield_mode.begin',
                            events.begin_reconcile(generation=events.generation, session_id=events.session_id))
                    self.assertEqual(control.state, 'HOLD')

    def test_fault_before_welcome_or_before_query_never_releases_connection(self):
        for fault_before_welcome in (True, False):
            with self.subTest(fault_before_welcome=fault_before_welcome):
                control, events = adapter()
                generation = events.connection_started()
                if fault_before_welcome:
                    events.fault('disconnect')
                    self.assertFalse(events.welcome('dead-session', generation=generation))
                else:
                    self.assertTrue(events.welcome('dead-session', generation=generation))
                    events.fault('disconnect')
                snapshot = events.begin_reconcile(generation=generation, session_id='dead-session')
                self.assertIsNone(snapshot)
                self.assertFalse(events.reconciled(False, snapshot))
                self.assertEqual(control.state, 'HOLD')
                self.assertEqual(events.phase, 'disconnected')

    def test_callback_reentrant_fault_during_status_cannot_release_connection(self):
        for revoked in (False, True):
            with self.subTest(revoked=revoked):
                control, events = adapter()
                snapshot = events.begin_reconcile(generation=events.generation, session_id=events.session_id)
                def hold(active, source, reason, now):
                    if reason == 'twitch-shield-status':
                        events.fault('callback-fault', revoked=revoked)
                    return control.set_hold(active, source, reason, now)
                events.hold = hold
                self.assertFalse(events.reconciled(False, snapshot))
                self.assertEqual(control.state, 'HOLD')
                self.assertEqual(events.phase, 'revoked' if revoked else 'disconnected')

    def test_concurrent_fault_and_status_are_serialized(self):
        control, events = adapter()
        snapshot = events.begin_reconcile(generation=events.generation, session_id=events.session_id)
        status_entered, fault_started, fault_done = Event(), Event(), Event()
        release_status = Event()
        def hold(active, source, reason, now):
            if reason == 'twitch-shield-status':
                status_entered.set()
                if not release_status.wait(2):
                    raise TimeoutError('status callback was not released')
            return control.set_hold(active, source, reason, now)
        events.hold = hold
        def disconnect():
            fault_started.set()
            events.fault('concurrent-fault')
            fault_done.set()
        with ThreadPoolExecutor(max_workers=2) as workers:
            status = workers.submit(events.reconciled, False, snapshot)
            try:
                self.assertTrue(status_entered.wait(2))
                fault = workers.submit(disconnect)
                self.assertTrue(fault_started.wait(2))
                fault_done.wait(.1)
            finally:
                release_status.set()
            status.result(timeout=2)
            fault.result(timeout=2)
        self.assertTrue(fault_done.is_set())
        self.assertEqual(events.phase, 'disconnected')
        self.assertEqual(control.state, 'HOLD')

    def test_callback_fault_before_connection_release_effect_never_exposes_live(self):
        for during in ('twitch-reconciled', 'twitch-reconciliation-complete'):
            for revoked in (False, True):
                with self.subTest(during=during, revoked=revoked):
                    control, events = adapter()
                    snapshot = events.begin_reconcile(generation=events.generation, session_id=events.session_id)
                    observed = []
                    def hold(active, source, reason, now):
                        if reason == during:
                            events.fault('release-callback-fault', revoked=revoked)
                            observed.append(len(control.transitions))
                        return control.set_hold(active, source, reason, now)
                    events.hold = hold
                    self.assertFalse(events.reconciled(False, snapshot))
                    self.assertEqual(len(observed), 1)
                    self.assertEqual(control.state, 'HOLD')
                    self.assertEqual(events.phase, 'revoked' if revoked else 'disconnected')
                    self.assertNotIn('LIVE', [item['to'] for item in control.transitions[observed[0]:]])

    def test_callback_shield_begin_before_status_effect_remains_held(self):
        control, events = adapter()
        snapshot = events.begin_reconcile(generation=events.generation, session_id=events.session_id)
        accepted = []
        def hold(active, source, reason, now):
            if reason == 'twitch-shield-status':
                accepted.append(events.accept(notification('callback-begin', topic='channel.shield_mode.begin'),
                                              generation=events.generation))
            return control.set_hold(active, source, reason, now)
        events.hold = hold
        self.assertTrue(events.reconciled(False, snapshot))
        self.assertEqual(accepted, ['shield-begin'])
        self.assertEqual(control.state, 'HOLD')
        self.assertEqual(events.accept(notification('later-end', topic='channel.shield_mode.end', at=START + 2),
                                       generation=events.generation), 'shield-end')
        self.assertEqual(control.state, 'LIVE')

    def test_generation_and_session_fence_all_unsafe_lifecycle_calls(self):
        control, events = adapter()
        previous = events.generation
        current = events.connection_started()
        self.assertGreater(current, previous)
        self.assertFalse(events.welcome('stale', generation=previous))
        self.assertEqual(events.phase, 'connecting')
        self.assertTrue(events.welcome('current', generation=current))
        self.assertIsNone(events.begin_reconcile(generation=previous, session_id='current'))
        self.assertIsNone(events.begin_reconcile(generation=current, session_id='stale'))
        snapshot = events.begin_reconcile(generation=current, session_id='current')
        self.assertTrue(events.reconciled(False, snapshot))
        self.assertEqual(control.state, 'LIVE')
        self.assertFalse(events.reconnect('wss://foreign.invalid/ws', generation=previous))
        self.assertFalse(events.handed_over('stale', generation=previous))
        self.assertEqual((events.phase, events.session_id), ('ready', 'current'))
        self.assertTrue(events.reconnect('wss://eventsub.wss.twitch.tv/ws', generation=current))
        self.assertFalse(events.handed_over('stale', generation=previous))
        self.assertEqual(events.session_id, 'current')
        self.assertTrue(events.handed_over('migrated', generation=current))
        self.assertEqual((events.phase, events.session_id), ('ready', 'migrated'))
        snapshot = events.begin_reconcile(generation=current, session_id='migrated')
        newer = events.begin_reconcile(generation=current, session_id='migrated')
        self.assertFalse(events.reconciliation_current(snapshot))
        self.assertFalse(events.reconciled(False, snapshot))
        self.assertEqual(control.state, 'HOLD')
        self.assertTrue(events.reconciled(False, newer))
        fault_generation = events.fault('disconnected')
        self.assertGreater(fault_generation, current)
        self.assertIsNone(events.session_id)
        self.assertIsNone(events.begin_reconcile(generation=fault_generation, session_id='migrated'))
        self.assertFalse(events.welcome('late', generation=fault_generation))
        self.assertFalse(events.reconciled(False, newer))
        self.assertEqual(control.state, 'HOLD')

    def test_releases_require_ready_current_generation_and_strict_timestamps(self):
        for topic, release, actor in [('channel.chat.message', '!shield resume', '1'),
                                     ('channel.shield_mode.end', '', '2')]:
            for phase in ('connecting', 'subscribing', 'reconciling', 'handover', 'disconnected', 'revoked'):
                with self.subTest(topic=topic, phase=phase):
                    control, events = adapter()
                    if phase in ('connecting', 'subscribing'):
                        events.connection_started()
                        if phase == 'subscribing':
                            events.welcome('next', generation=events.generation)
                    elif phase == 'reconciling':
                        events.begin_reconcile(generation=events.generation, session_id=events.session_id)
                    elif phase == 'handover':
                        events.reconnect('wss://eventsub.wss.twitch.tv/ws', generation=events.generation)
                    else:
                        events.fault(revoked=phase == 'revoked')
                    before = control.transitions
                    self.assertEqual(events.accept(notification('release', release, actor=actor, topic=topic),
                                                   generation=events.generation), 'inactive')
                    self.assertEqual(control.transitions, before)
            for at, expected in [(START - 1, 'invalid'), (START + 10.2, 'released'),
                                 (START + 40, 'released'), (START + 40.000001, 'invalid'),
                                 ('malformed', 'invalid'), ('naive', 'invalid'), ('missing', 'invalid')]:
                with self.subTest(topic=topic, at=at):
                    control, events = adapter()
                    hold_topic = 'channel.chat.message' if topic == 'channel.chat.message' else 'channel.shield_mode.begin'
                    events.accept(notification('hold', topic=hold_topic), generation=events.generation)
                    msg = notification('release', release, actor=actor, topic=topic,
                                       at=at if isinstance(at, float) else START + 2)
                    if at == 'malformed':
                        msg['metadata']['message_timestamp'] = 'invalid'
                    elif at == 'naive':
                        msg['metadata']['message_timestamp'] = '2026-10-29T00:00:02'
                    elif at == 'missing':
                        del msg['metadata']['message_timestamp']
                    self.assertEqual(events.accept(msg, generation=events.generation - 1), 'inactive')
                    result = events.accept(msg, generation=events.generation)
                    self.assertEqual(result, ('chat-resume' if topic == 'channel.chat.message' else 'shield-end')
                                     if expected == 'released' else expected)
                    self.assertEqual(control.state, 'LIVE' if expected == 'released' else 'HOLD')

    def test_far_future_hold_keeps_raw_order_until_newer_release_is_fresh(self):
        for topic, release_topic, release in [('channel.chat.message', 'channel.chat.message', '!shield resume'),
                                            ('channel.shield_mode.begin', 'channel.shield_mode.end', '')]:
            with self.subTest(topic=topic):
                control, events = adapter()
                self.assertIn(events.accept(notification('future-hold', topic=topic, at=START + 100000),
                                            generation=events.generation), ('chat-hold', 'shield-begin'))
                self.assertEqual(control.state, 'HOLD')
                self.assertEqual(events.accept(notification('early-release', release, actor='1',
                                                           topic=release_topic, at=START + 11),
                                               generation=events.generation), 'expired')
                self.assertEqual(control.state, 'HOLD')
                events.clock = lambda: START + 40
                self.assertEqual(events.accept(notification('tied-release', release, actor='1',
                                                           topic=release_topic, at=START + 40),
                                               generation=events.generation), 'expired')
                self.assertEqual(control.state, 'HOLD')
                self.assertEqual(events.accept(notification('older-release', release, actor='1',
                                                           topic=release_topic, at=START + 41),
                                               generation=events.generation), 'expired')
                self.assertEqual(control.state, 'HOLD')
                events.clock = lambda: START + 100000
                self.assertEqual(events.accept(notification('far-future-older-release', release, actor='1',
                                                           topic=release_topic, at=START + 99999.5),
                                               generation=events.generation), 'expired')
                self.assertEqual(control.state, 'HOLD')
                self.assertIn(events.accept(notification('later-release', release, actor='1',
                                                        topic=release_topic, at=START + 100001),
                                            generation=events.generation), ('chat-resume', 'shield-end'))
                self.assertEqual(control.state, 'LIVE')

    def test_forward_skew_rejects_older_and_equal_releases(self):
        for skew in (10, 29, 29.9, 30.0, 30.001, 31, 41):
            for topic, release_topic, release in [
                    ('channel.chat.message', 'channel.chat.message', '!shield resume'),
                    ('channel.shield_mode.begin', 'channel.shield_mode.end', '')]:
                for relation, offset in [('older', -.0005), ('equal', 0)]:
                    with self.subTest(skew=skew, topic=topic, relation=relation):
                        control, events = adapter()
                        at = START + 10 + skew
                        self.assertIn(events.accept(notification('new-hold', topic=topic, at=at),
                                                    generation=events.generation), ('chat-hold', 'shield-begin'))
                        self.assertEqual(control.state, 'HOLD')
                        events.clock = lambda: START + max(11, skew - 19)
                        self.assertEqual(events.accept(notification(relation, release, actor='1',
                                                                   topic=release_topic, at=at + offset),
                                                       generation=events.generation), 'expired')
                        self.assertEqual(control.state, 'HOLD')
                        self.assertIn(events.accept(notification('newer', release, actor='1',
                                                                topic=release_topic, at=at + 1),
                                                    generation=events.generation), ('chat-resume', 'shield-end'))
                        self.assertEqual(control.state, 'LIVE')

    def test_unstamped_hold_uses_global_twitch_watermark_including_ignored_chat(self):
        for topic, release_topic, release in [('channel.chat.message', 'channel.chat.message', '!shield resume'),
                                            ('channel.shield_mode.begin', 'channel.shield_mode.end', '')]:
            for raw in ('missing', 'malformed', 'naive'):
                with self.subTest(topic=topic, raw=raw):
                    control, events = adapter()
                    self.assertEqual(events.accept(notification('ordinary', 'ordinary text', actor='3',
                                                                badge=None, at=START + 29),
                                                   generation=events.generation), 'ignored')
                    self.assertEqual(events.remembered, 0)
                    hold = notification('unstamped', topic=topic)
                    if raw == 'missing':
                        del hold['metadata']['message_timestamp']
                    else:
                        hold['metadata']['message_timestamp'] = 'bad' if raw == 'malformed' else '2026-10-29T00:00:01'
                    self.assertIn(events.accept(hold, generation=events.generation), ('chat-hold', 'shield-begin'))
                    for name, at in [('older', START + 28), ('equal', START + 29)]:
                        self.assertEqual(events.accept(notification(name, release, actor='1',
                                                                   topic=release_topic, at=at),
                                                       generation=events.generation), 'expired')
                        self.assertEqual(control.state, 'HOLD')
                    self.assertIn(events.accept(notification('newer', release, actor='1',
                                                            topic=release_topic, at=START + 30),
                                                generation=events.generation), ('chat-resume', 'shield-end'))
                    self.assertEqual(control.state, 'LIVE')

    def test_first_unstamped_hold_fences_first_fresh_twitch_stamp(self):
        control, events = adapter()
        foreign = notification('foreign', at=START + 100000)
        foreign['payload']['event']['broadcaster_user_id'] = '9'
        self.assertEqual(events.accept(foreign, generation=events.generation), 'invalid')
        hold = notification()
        del hold['metadata']['message_timestamp']
        self.assertEqual(events.accept(hold, generation=events.generation), 'chat-hold')
        self.assertEqual(control.state, 'HOLD')
        self.assertEqual(events.accept(notification('first-stamp', '!shield resume', actor='1', at=START + 2),
                                       generation=events.generation), 'expired')
        self.assertEqual(control.state, 'HOLD')
        self.assertEqual(events.accept(notification('equal-stamp', '!shield resume', actor='1', at=START + 2),
                                       generation=events.generation), 'expired')
        self.assertEqual(control.state, 'HOLD')
        self.assertEqual(events.accept(notification('later-stamp', '!shield resume', actor='1', at=START + 3),
                                       generation=events.generation), 'chat-resume')
        self.assertEqual(control.state, 'LIVE')

    def test_reconcile_shield_hold_uses_missing_stamp_barrier(self):
        for seed in (None, START + 29):
            with self.subTest(seed=seed):
                control, events = adapter()
                if seed is not None:
                    self.assertEqual(events.accept(notification('ordinary', 'ordinary text', actor='3',
                                                                badge=None, at=seed),
                                                   generation=events.generation), 'ignored')
                token = events.begin_reconcile(generation=events.generation, session_id=events.session_id)
                self.assertTrue(events.reconciled(True, token))
                self.assertEqual(control.state, 'HOLD')
                barrier = START + 25 if seed is None else seed
                stamps = [barrier, barrier] if seed is None else [barrier - 1, barrier]
                for index, stamp in enumerate(stamps):
                    self.assertEqual(events.accept(notification('older-' + str(index), topic='channel.shield_mode.end',
                                                               at=stamp), generation=events.generation), 'expired')
                    self.assertEqual(control.state, 'HOLD')
                self.assertEqual(events.accept(notification('newer', topic='channel.shield_mode.end', at=barrier + 1),
                                               generation=events.generation), 'shield-end')
                self.assertEqual(control.state, 'LIVE')

    def test_far_future_release_warns_with_fixed_code_and_retains_hold(self):
        control, events = adapter()
        events.accept(notification('hold', at=START + 40), generation=events.generation)
        with self.assertLogs('shield.twitch.events', level='WARNING') as captured:
            self.assertEqual(events.accept(notification('synthetic-private-id', '!shield resume', actor='1',
                                                       at=START + 100000), generation=events.generation), 'invalid')
        self.assertEqual([(r.msg, r.args, r.exc_info) for r in captured.records], [('clock-skew', (), None)])
        self.assertEqual(control.state, 'HOLD')
        missing = notification('missing-after-future')
        del missing['metadata']['message_timestamp']
        self.assertEqual(events.accept(missing, generation=events.generation), 'chat-hold')
        events.clock = lambda: START + 100000
        self.assertEqual(events.accept(notification('seen-stamp', '!shield resume', actor='1', at=START + 100000),
                                       generation=events.generation), 'expired')
        self.assertEqual(control.state, 'HOLD')
        self.assertEqual(events.accept(notification('new-stamp', '!shield resume', actor='1', at=START + 100001),
                                       generation=events.generation), 'chat-resume')
        self.assertEqual(control.state, 'LIVE')

    def test_tlc_release_clobber_shortest_path_retains_active_shield(self):
        control = Control()
        def hold(active, source, reason, now):
            return control.set_hold(active, source, reason, now)
        events = ShieldEvents('1', hold, started_at=0, clock=lambda: 0,
                              capacity=1, max_age=2, control_clock=lambda: 0)
        self.assertEqual(control.state, 'HOLD')
        generation = events.connection_started()
        self.assertTrue(events.welcome('session', generation=generation))
        snapshot = events.begin_reconcile(generation=events.generation, session_id=events.session_id)
        self.assertEqual((snapshot.generation, snapshot.shield_revision, snapshot.session_id),
                         (generation, 0, 'session'))
        self.assertTrue(events.reconciled(True, snapshot))
        self.assertEqual(events.phase, 'ready')
        self.assertEqual(control.state, 'HOLD')

    def test_reconciliation_release_preserves_newer_shield_chat_and_local_holds(self):
        for source in ('local', 'chat'):
            single, policy = adapter()
            token = policy.begin_reconcile(generation=policy.generation, session_id=policy.session_id)
            if source == 'local':
                single.set_hold(True, source='local')
            else:
                policy.accept(notification('single-chat'), generation=policy.generation)
            self.assertTrue(policy.reconciled(False, token))
            self.assertEqual(single.state, 'HOLD', source + ' was cleared by reconciliation')
        control, events = adapter()
        snapshot = events.begin_reconcile(generation=events.generation, session_id=events.session_id)
        events.accept(notification('chat-during-query'), generation=events.generation)
        events.accept(notification('shield-during-query', topic='channel.shield_mode.begin', at=START + 2), generation=events.generation)
        control.set_hold(True, source='local')
        self.assertTrue(events.reconciled(False, snapshot))
        self.assertEqual(control.state, 'HOLD')
        control.set_hold(False, source='local')
        events.accept(notification('owner-after-query', '!shield resume', actor='1', at=START + 3), generation=events.generation)
        self.assertEqual(control.state, 'HOLD')
        events.accept(notification('shield-after-query', topic='channel.shield_mode.end', at=START + 4), generation=events.generation)
        self.assertEqual(control.state, 'LIVE')
        stale = events.begin_reconcile(generation=events.generation, session_id=events.session_id)
        events.fault('another-outage')
        self.assertFalse(events.reconciled(False, stale))
        self.assertEqual(control.state, 'HOLD')

    def test_only_broadcaster_resumes_and_cannot_release_other_holds(self):
        control, events = adapter()
        self.assertEqual(events.accept(notification(), generation=events.generation), 'chat-hold')
        self.assertEqual(control.state, 'HOLD')
        self.assertEqual(events.accept(notification('mod-resume', '!shield resume', at=START + 2), generation=events.generation), 'ignored')
        control.set_hold(True, source='local')
        events.accept(notification('shield-on', topic='channel.shield_mode.begin'), generation=events.generation)
        self.assertEqual(events.accept(notification('owner-resume', '!shield resume', actor='1', at=START + 3), generation=events.generation), 'chat-resume')
        self.assertEqual(control.state, 'HOLD')
        events.accept(notification('shield-off', topic='channel.shield_mode.end', at=START + 4), generation=events.generation)
        self.assertEqual(control.state, 'HOLD')
        self.assertEqual(control.set_hold(False, source='local'), 'LIVE')
        events.accept(notification('fake-owner', actor='3', badge='broadcaster'), generation=events.generation)
        self.assertEqual(control.state, 'LIVE')

    def test_replay_floor_survives_reconnect_capacity_and_expiry(self):
        control, events = adapter(capacity=1)
        hold = notification()
        events.accept(hold, generation=events.generation)
        events.accept(notification('resume', '!shield resume', actor='1', at=START + 2), generation=events.generation)
        self.assertEqual(control.state, 'LIVE')
        self.assertTrue(events.reconnect('wss://eventsub.wss.twitch.tv/ws?session=synthetic', generation=events.generation))
        self.assertEqual(control.state, 'LIVE')
        events.handed_over('new-session', generation=events.generation)
        # Bounded memory may conservatively reassert an evicted hold. Its old
        # release can never replay, including after a new session welcomes.
        self.assertEqual(events.accept(hold, generation=events.generation), 'chat-hold')
        self.assertEqual(events.accept(notification('resume', '!shield resume', actor='1', at=START + 2), generation=events.generation), 'invalid')
        self.assertEqual(control.state, 'HOLD')
        self.assertEqual(events.remembered, 1)
        self.assertEqual(events.accept(notification('fresh-resume', '!shield resume', actor='1', at=START + 11), generation=events.generation), 'chat-resume')
        self.assertEqual(control.state, 'LIVE')
        events.clock = lambda: START + 1000
        self.assertEqual(events.accept(hold, generation=events.generation), 'chat-hold')
        self.assertEqual(events.remembered, 1)
        self.assertEqual(events.accept(notification('fresh-resume', '!shield resume', actor='1', at=START + 11), generation=events.generation), 'invalid')
        self.assertEqual(control.state, 'HOLD')

    def test_revocation_latches_and_foreign_reconnect_never_connects(self):
        control, events = adapter()
        for url in ['wss://eventsub.wss.twitch.tv.evil/ws', 'ws://eventsub.wss.twitch.tv/ws',
                    'wss://user@eventsub.wss.twitch.tv/ws', 'wss://eventsub.wss.twitch.tv:443/ws',
                    'ws://127.0.0.1:9876/ws']:
            control, events = adapter()
            self.assertFalse(events.reconnect(url, generation=events.generation))
            self.assertEqual(control.state, 'HOLD')
        control, events = adapter()
        events.fault('authorization-revoked', revoked=True)
        events.welcome('replacement', generation=events.generation)
        self.assertFalse(events.reconciled(False, events.begin_reconcile(generation=events.generation, session_id=events.session_id)))
        self.assertEqual(events.phase, 'revoked')
        self.assertEqual(events.accept(notification('resume', '!shield resume', actor='1'), generation=events.generation), 'inactive')
        self.assertEqual(control.state, 'HOLD')

    def test_untrusted_chat_fields_and_out_of_order_releases_cannot_resume(self):
        control, events = adapter()
        for key, value in [('source_broadcaster_user_id', '9'), ('broadcaster_user_id', '9'),
                           ('chatter_user_id', '9')]:
            msg = notification(key, badge='broadcaster')
            msg['payload']['event'][key] = value
            msg['metadata']['message_timestamp'] = 'malformed'
            events.accept(msg, generation=events.generation)
            self.assertEqual(control.state, 'LIVE')
        events.accept(notification('new-hold', actor='1', at=START + 4), generation=events.generation)
        events.accept(notification('old-resume', '!shield resume', actor='1', at=START + 3), generation=events.generation)
        self.assertEqual(control.state, 'HOLD')
        events.accept(notification('shield-new', topic='channel.shield_mode.begin', at=START + 5), generation=events.generation)
        events.accept(notification('shield-old', topic='channel.shield_mode.end', at=START + 4), generation=events.generation)
        events.accept(notification('owner', '!shield resume', actor='1', at=START + 6), generation=events.generation)
        self.assertEqual(control.state, 'HOLD')


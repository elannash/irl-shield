"""Twitch control policy, shared by the real transport and offline replay."""
import math
import time
from collections import OrderedDict
from datetime import datetime
from urllib.parse import urlsplit

TOPICS = ('channel.chat.message', 'channel.shield_mode.begin', 'channel.shield_mode.end')


def websocket_url(url, *, mock=False):
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError('unapproved EventSub endpoint')
    if mock:
        valid = parsed.scheme == 'ws' and parsed.hostname == '127.0.0.1' and parsed.port is not None
    else:
        valid = (parsed.scheme == 'wss' and parsed.netloc == 'eventsub.wss.twitch.tv'
                 and parsed.path in ('', '/', '/ws'))
    if not valid:
        raise ValueError('unapproved EventSub endpoint')
    return url


class ShieldEvents:
    """One session lifetime, including reconnects. Never recreate this on reconnect.

    hold is MaskingEngine.hold. A standalone Control can be adapted by the caller.
    Eviction advances a timestamp floor: old IDs cannot become executable again.
    At that floor even unseen events are discarded; loss is conservative and
    reported by return value. No transport transition releases chat/Shield holds.
    """
    def __init__(self, broadcaster_id, hold, *, started_at=None, clock=time.time,
                 capacity=4096, max_age=600, mock=False, control_clock=time.monotonic):
        if capacity < 1 or not math.isfinite(max_age) or max_age <= 0:
            raise ValueError('invalid replay bounds')
        self.broadcaster_id, self.hold, self.clock = broadcaster_id, hold, clock
        self.control_clock = control_clock
        self.started_at = clock() if started_at is None else started_at
        self.capacity, self.max_age, self.mock = capacity, max_age, mock
        self._floor = self.started_at - 0.000001
        self._seen = OrderedDict()
        self._shield_time = self.started_at - 0.000001
        self._chat_time = self.started_at - 0.000001
        self._shield_revision = 0
        self._generation = 0
        self.phase, self.session_id = 'connecting', None
        self._revoked = False
        self._connection_hold(True, 'twitch-connecting')

    @property
    def remembered(self):
        return len(self._seen)

    def _connection_hold(self, active, reason):
        self.hold(active, source='twitch-connection', reason=reason, now=self.control_clock())

    def welcome(self, session_id):
        if not isinstance(session_id, str) or not session_id:
            self.fault('invalid-welcome')
            return
        self.session_id = session_id
        if not self._revoked:
            self.phase = 'subscribing'

    def reconnect(self, url):
        try:
            websocket_url(url, mock=self.mock)
        except (ValueError, TypeError):
            self.fault('unapproved-reconnect')
            return False
        if self.phase == 'ready':
            self.phase = 'handover'
        return True

    def handed_over(self, session_id):
        self.session_id = session_id
        if self.phase == 'handover' and not self._revoked:
            self.phase = 'ready'

    def begin_reconcile(self):
        if self._revoked:
            return None
        self.phase = 'reconciling'
        self._connection_hold(True, 'twitch-reconciling')
        return self._generation, self._shield_revision

    def reconciled(self, active, snapshot):
        if not self.reconciliation_current(snapshot) or not isinstance(active, bool):
            return False
        if snapshot[1] == self._shield_revision:
            self.hold(active, source='shield_mode', reason='twitch-shield-status', now=self.control_clock())
        self.phase = 'ready'
        self._connection_hold(False, 'twitch-reconciled')
        return True

    def reconciliation_current(self, snapshot):
        return (not self._revoked and self.phase == 'reconciling'
                and snapshot is not None and snapshot[0] == self._generation)

    def fault(self, reason='disconnected', *, revoked=False):
        self._generation += 1
        self._revoked = self._revoked or revoked
        self.phase = 'revoked' if self._revoked else 'disconnected'
        self._connection_hold(True, 'twitch-' + reason)

    def accept(self, envelope):
        if self.phase not in ('ready', 'handover', 'reconciling'):
            return 'inactive'
        try:
            metadata, payload = envelope['metadata'], envelope['payload']
            mid, topic = metadata['message_id'], metadata['subscription_type']
            subscription, event = payload['subscription'], payload['event']
            stamp = datetime.fromisoformat(metadata['message_timestamp'].replace('Z', '+00:00'))
            if stamp.tzinfo is None:
                return 'invalid'
            at = stamp.timestamp()
            now = self.clock()
            self._floor = max(self._floor, now - self.max_age)
            for old_id, old_time in list(self._seen.items()):
                if old_time <= self._floor:
                    del self._seen[old_id]
            if (metadata['message_type'] != 'notification' or topic not in TOPICS
                    or metadata['subscription_version'] != '1'
                    or subscription['type'] != topic or subscription['version'] != '1'
                    or subscription['status'] != 'enabled'
                    or subscription['condition']['broadcaster_user_id'] != self.broadcaster_id
                    or event['broadcaster_user_id'] != self.broadcaster_id
                    or not isinstance(mid, str) or not 0 < len(mid) <= 256
                    or not math.isfinite(at) or at < self.started_at or at <= self._floor or at > now):
                return 'invalid'
            if mid in self._seen:
                return 'duplicate'
            if len(self._seen) >= self.capacity:
                _, evicted = self._seen.popitem(last=False)
                self._floor = max(self._floor, evicted)
                if at <= self._floor:
                    return 'expired'
            self._seen[mid] = at
            if topic == 'channel.chat.message':
                # Shared-chat badges describe their origin channel, not ours.
                if event.get('source_broadcaster_user_id') not in (None, '', self.broadcaster_id):
                    return 'ignored'
                owner = event['chatter_user_id'] == self.broadcaster_id
                moderator = any(b['set_id'] == 'moderator' and b['id'] == '1' for b in event['badges'])
                command = event['message']['text'].strip().lower()
                if command == '!shield hold' and (owner or moderator):
                    self._chat_time = max(self._chat_time, at)
                    self.hold(True, source='chat', reason='twitch-chat-hold', now=self.control_clock())
                    return 'chat-hold'
                if command == '!shield resume' and owner:
                    if at <= self._chat_time:
                        return 'expired'
                    self._chat_time = at
                    self.hold(False, source='chat', reason='twitch-chat-resume', now=self.control_clock())
                    return 'chat-resume'
            else:
                # An out-of-order end may never undo a newer begin. At equal
                # timestamps begin wins, since nanoseconds can round in Python.
                active = topic == 'channel.shield_mode.begin'
                if at < self._shield_time or (at == self._shield_time and not active):
                    return 'expired'
                self._shield_time = at
                self._shield_revision += 1
                self.hold(active, source='shield_mode', reason='twitch-' + topic, now=self.control_clock())
                return 'shield-begin' if active else 'shield-end'
        except (KeyError, TypeError, ValueError, AttributeError):
            return 'invalid'
        return 'ignored'

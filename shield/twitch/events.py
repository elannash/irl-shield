"""Twitch control policy, shared by the real transport and offline replay."""
import math
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from threading import RLock
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


@dataclass(frozen=True)
class Reconciliation:
    generation: int
    shield_revision: int
    session_id: str


class ShieldEvents:
    """One session lifetime, including reconnects. Never recreate on reconnect.

    Public calls serialize under an RLock; hold callbacks may reenter the policy.
    Releases require a live welcomed generation. Protective events survive clock
    errors and stale generations. Eviction can reassert an expired-ID hold, but
    advances a permanent timestamp floor so an expired release cannot replay.
    """
    def __init__(self, broadcaster_id, hold, *, started_at=None, clock=time.time,
                 capacity=4096, max_age=600, mock=False, control_clock=time.monotonic):
        if capacity < 1 or not math.isfinite(max_age) or max_age <= 0:
            raise ValueError('invalid replay bounds')
        self.broadcaster_id, self.hold, self.clock = broadcaster_id, hold, clock
        self.control_clock = control_clock
        self.started_at = clock() if started_at is None else started_at
        self.capacity, self.max_age, self.mock = capacity, max_age, mock
        self._lock = RLock()
        self._floor = self.started_at - 0.000001
        self._seen = OrderedDict()
        self._shield_time = self.started_at - 0.000001
        self._chat_time = self.started_at - 0.000001
        self._shield_revision = 0
        self._generation = 0
        self._phase, self._session_id = 'connecting', None
        self._connection_live = False
        self._reconciliation = None
        self._revoked = False
        self._connection_hold(True, 'twitch-connecting')

    @property
    def generation(self):
        with self._lock:
            return self._generation

    @property
    def phase(self):
        with self._lock:
            return self._phase

    @property
    def session_id(self):
        with self._lock:
            return self._session_id

    @property
    def remembered(self):
        with self._lock:
            return len(self._seen)

    def _connection_hold(self, active, reason):
        self.hold(active, source='twitch-connection', reason=reason, now=self.control_clock())

    def connection_started(self):
        with self._lock:
            generation = self.fault('connecting')
            if generation == self._generation and not self._revoked:
                self._phase = 'connecting'
            return generation

    def welcome(self, session_id, *, generation):
        with self._lock:
            if generation != self._generation or self._revoked or self._phase != 'connecting':
                return False
            if not isinstance(session_id, str) or not session_id:
                self.fault('invalid-welcome')
                return False
            self._session_id, self._connection_live = session_id, True
            self._phase = 'subscribing'
            return True

    def reconnect(self, url, *, generation):
        with self._lock:
            if (generation != self._generation or not self._connection_live
                    or self._revoked or self._phase != 'ready'):
                return False
            try:
                websocket_url(url, mock=self.mock)
            except (ValueError, TypeError):
                self.fault('unapproved-reconnect')
                return False
            self._phase = 'handover'
            return True

    def handed_over(self, session_id, *, generation):
        with self._lock:
            if (generation != self._generation or not self._connection_live
                    or self._revoked or self._phase != 'handover'):
                return False
            if not isinstance(session_id, str) or not session_id:
                self.fault('invalid-handover')
                return False
            self._session_id, self._phase = session_id, 'ready'
            return True

    def begin_reconcile(self, *, generation, session_id):
        with self._lock:
            if (generation != self._generation or session_id != self._session_id
                    or not self._connection_live or self._revoked
                    or self._phase not in ('subscribing', 'ready', 'reconciling')):
                return None
            snapshot = Reconciliation(generation, self._shield_revision, session_id)
            self._reconciliation = snapshot
            self._phase = 'reconciling'
            self._connection_hold(True, 'twitch-reconciling')
            if not self.reconciliation_current(snapshot):
                return None
            self.hold(True, source='twitch-reconcile', reason='twitch-reconciling', now=self.control_clock())
            return snapshot if self.reconciliation_current(snapshot) else None

    def reconciled(self, active, snapshot):
        with self._lock:
            if not self.reconciliation_current(snapshot) or not isinstance(active, bool):
                return False
            if snapshot.shield_revision == self._shield_revision:
                self.hold(active, source='shield_mode', reason='twitch-shield-status', now=self.control_clock())
                if not self.reconciliation_current(snapshot):
                    return False
                # A callback may deliver begin before applying the older False.
                # End is inactive during reconciliation, so a changed revision
                # here always requires protection. The connection guard is held.
                if not active and snapshot.shield_revision != self._shield_revision:
                    self.hold(True, source='shield_mode', reason='twitch-shield-during-status',
                              now=self.control_clock())
            # RLock permits callback reentry: a fault/revoke inside hold invalidates
            # the token even though another thread cannot interleave here.
            if not self.reconciliation_current(snapshot):
                return False
            # Keep a separate guard through the connection-release callback.
            # If it faults before applying False, the guard still holds. If the
            # final guard-release callback faults, twitch-connection still holds.
            self._connection_hold(False, 'twitch-reconciled')
            if not self.reconciliation_current(snapshot):
                return False
            self._phase = 'ready'
            self.hold(False, source='twitch-reconcile', reason='twitch-reconciliation-complete',
                      now=self.control_clock())
            if (snapshot is not self._reconciliation or snapshot.generation != self._generation
                    or not self._connection_live or self._revoked or self._phase != 'ready'):
                return False
            self._reconciliation = None
            return True

    def reconciliation_current(self, snapshot):
        with self._lock:
            return (snapshot is not None and snapshot is self._reconciliation
                    and not self._revoked and self._connection_live and self._phase == 'reconciling'
                    and snapshot.generation == self._generation and snapshot.session_id == self._session_id)

    def fault(self, reason='disconnected', *, revoked=False):
        with self._lock:
            self._generation += 1
            generation = self._generation
            self._revoked = self._revoked or revoked
            self._phase = 'revoked' if self._revoked else 'disconnected'
            self._session_id, self._connection_live, self._reconciliation = None, False, None
            self._connection_hold(True, 'twitch-' + reason)
            return generation

    def accept(self, envelope, *, generation):
        with self._lock:
            try:
                metadata, payload = envelope['metadata'], envelope['payload']
                mid, topic = metadata['message_id'], metadata['subscription_type']
                subscription, event = payload['subscription'], payload['event']
                if (metadata['message_type'] != 'notification' or topic not in TOPICS
                        or metadata['subscription_version'] != '1'
                        or subscription['type'] != topic or subscription['version'] != '1'
                        or subscription['status'] != 'enabled'
                        or subscription['condition']['broadcaster_user_id'] != self.broadcaster_id
                        or event['broadcaster_user_id'] != self.broadcaster_id
                        or not isinstance(mid, str) or not 0 < len(mid) <= 256):
                    return 'invalid'
                if topic == 'channel.chat.message':
                    # Shared-chat badges describe their origin channel, not ours.
                    if event.get('source_broadcaster_user_id') not in (None, '', self.broadcaster_id):
                        return 'ignored'
                    owner = event['chatter_user_id'] == self.broadcaster_id
                    moderator = any(b['set_id'] == 'moderator' and b['id'] == '1' for b in event['badges'])
                    command = event['message']['text'].strip().lower()
                    if command == '!shield hold' and (owner or moderator):
                        active, source, outcome = True, 'chat', 'chat-hold'
                    elif command == '!shield resume' and owner:
                        active, source, outcome = False, 'chat', 'chat-resume'
                    else:
                        return 'ignored'
                else:
                    active, source = topic == 'channel.shield_mode.begin', 'shield_mode'
                    outcome = 'shield-begin' if active else 'shield-end'
            except (KeyError, TypeError, ValueError, AttributeError):
                return 'invalid'
            try:
                stamp = datetime.fromisoformat(metadata['message_timestamp'].replace('Z', '+00:00'))
                at = stamp.timestamp() if stamp.tzinfo is not None else None
                if at is not None and not math.isfinite(at):
                    at = None
            except (KeyError, TypeError, ValueError, AttributeError, OverflowError, OSError):
                at = None
            now = self.clock()
            self._floor = max(self._floor, now - self.max_age)
            for old_id, old_time in list(self._seen.items()):
                if old_time <= self._floor:
                    del self._seen[old_id]
            if not active:
                if (generation != self._generation or not self._connection_live
                        or self._revoked or self._phase != 'ready'):
                    return 'inactive'
                # Thirty seconds of forward skew is a local engineering choice;
                # protective admission never depends on the wall clock.
                if at is None or at < self.started_at or at <= self._floor or at > now + 30:
                    return 'invalid'
            if mid in self._seen:
                return 'duplicate'
            if active:
                # Preserve Twitch ordering within the same skew bound as releases.
                # Unusable stamps use receipt; extreme future stamps fail closed
                # for at most the forward-skew window before a fresh release.
                if at is None or at < self.started_at or at <= self._floor:
                    at = now
                at = max(self.started_at, min(at, now + 30))
            if len(self._seen) >= self.capacity:
                _, evicted = self._seen.popitem(last=False)
                self._floor = max(self._floor, evicted)
                if not active and at <= self._floor:
                    return 'expired'
            self._seen[mid] = at
            if source == 'chat':
                if not active and at <= self._chat_time:
                    return 'expired'
                self._chat_time = max(self._chat_time, at)
                reason = 'twitch-chat-hold' if active else 'twitch-chat-resume'
            else:
                # Equal timestamps favor protection, including subsecond stamps
                # rounded to the same Python float.
                if not active and at <= self._shield_time:
                    return 'expired'
                self._shield_time = max(self._shield_time, at)
                self._shield_revision += 1
                reason = 'twitch-' + topic
            self.hold(active, source=source, reason=reason, now=self.control_clock())
            return outcome

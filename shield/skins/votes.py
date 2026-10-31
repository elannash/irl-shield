"""Session-scoped chat voting; accepts sanitized authenticated events only."""
from collections import Counter
from dataclasses import dataclass
import math
import re

from .paint import SKINS


# Patch: native receipt be3c10c2. Bar: conductor retains earlier 36245885
# after byte parity; unit7 literally failed with two seam PROTECTs (b136a202).
# This is a conductor decision, not a unit7 pass; see docs/MASK-RUNTIME.md.
CHAT_SKINS = ('patch', 'bar')


@dataclass(frozen=True)
class ChatEvent:
    id: str
    user_id: str
    roles: frozenset[str]
    text: str
    timestamp: float


class SkinVotes:
    """Rolling (now - 60, now] plurality, keeping the incumbent on ties.

    Root creates one reducer per authenticated session, using its start time
    in the same clock domain as event timestamps. No parsing of user-claimed
    roles, network calls or OAuth scopes occurs here.

    Up to 30 seconds of forward clock skew is accepted, clamped to receiver
    time for both vote expiry and event ordering.
    """
    def __init__(self, session_started_at, incumbent='patch'):
        if not math.isfinite(session_started_at) or incumbent not in SKINS:
            raise ValueError('Expected a finite session start and known incumbent')
        self.session_started_at = session_started_at
        self.incumbent = incumbent
        self.locked = None
        self._votes = {}
        self._seen = set()
        self._control_order = (session_started_at, '')
        self._now = session_started_at

    def _advance(self, now):
        if not math.isfinite(now) or now < self._now:
            raise ValueError('Vote clock must be finite and monotonic')
        self._now = now
        self._votes = {user: vote for user, vote in self._votes.items() if vote[1] > now - 60}

    def _choose(self):
        counts = Counter(vote[0] for vote in self._votes.values())
        if counts and self.locked is None:
            maximum = max(counts.values())
            tied = sorted(name for name, value in counts.items() if value == maximum)
            self.incumbent = self.incumbent if self.incumbent in tied else tied[0]
        return {'skin': self.locked or self.incumbent, 'skin_locked': self.locked is not None,
                'votes': dict(sorted(counts.items()))}

    def snapshot(self, now):
        self._advance(now)
        return self._choose()

    def apply(self, event: ChatEvent, *, now):
        self._advance(now)
        valid = (isinstance(event.id, str) and 0 < len(event.id) <= 256
                 and isinstance(event.user_id, str) and 0 < len(event.user_id) <= 256
                 and isinstance(event.text, str) and len(event.text) <= 96
                 and isinstance(event.roles, frozenset)
                 and isinstance(event.timestamp, (int, float)) and math.isfinite(event.timestamp)
                 and max(self.session_started_at, now - 60) <= event.timestamp <= now + 30
                 and event.timestamp > now - 60)
        if not valid or event.id in self._seen:
            return self._choose()
        timestamp = min(event.timestamp, now)
        # IDs live for the entire reducer session. A repeated ID with a forged
        # fresh timestamp still cannot become a second event.
        self._seen.add(event.id)
        # ASCII grammar with whole-input matching rejects commands appended
        # after newlines, NULs, role-looking text and Unicode lookalikes.
        match = re.fullmatch(r'!skin (?:([a-z]+)|lock ([a-z]+))', event.text, flags=re.ASCII)
        if match is None:
            return self._choose()
        name, lock_name = match.groups()
        privileged = bool(event.roles & {'moderator', 'broadcaster'})
        control_order = (timestamp, event.id)
        if lock_name:
            if privileged and lock_name in CHAT_SKINS and control_order >= self._control_order:
                self.locked = lock_name
                self.incumbent = lock_name
                self._control_order = control_order
        elif name == 'unlock':
            if privileged and control_order >= self._control_order:
                self.locked = None
                self._control_order = control_order
        elif name in CHAT_SKINS:
            previous = self._votes.get(event.user_id)
            if previous is None or (timestamp, event.id) >= (previous[1], previous[2]):
                self._votes[event.user_id] = (name, timestamp, event.id)
        return self._choose()

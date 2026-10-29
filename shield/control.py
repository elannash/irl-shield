"""Explicit stream protection state; original code with no external assets."""


class Control:
    """Coverage controls LIVE/PROTECT; any named hold independently forces HOLD.

    Callers supply event times. The most recently asserted active hold supplies
    the reason, and only state changes append to the transition ledger.
    """

    def __init__(self):
        self._state = 'PROTECT'
        self._reason = 'startup'
        self._coverage_ok = False
        self._coverage_reason = 'startup'
        self._holds = {}
        self._transitions = []

    @property
    def state(self):
        return self._state

    @property
    def reason(self):
        return self._reason

    @property
    def transitions(self):
        return [event.copy() for event in self._transitions]

    def set_hold(self, active: bool, source: str = 'local', reason: str = 'manual', at: float = 0.0):
        self._holds.pop(source, None)
        if active:
            self._holds[source] = reason
        return self._settle(at)

    def update_coverage(self, ok: bool, reason: str, at: float):
        self._coverage_ok = ok
        self._coverage_reason = reason
        return self._settle(at)

    def _settle(self, at):
        if self._holds:
            state, reason = 'HOLD', next(reversed(self._holds.values()))
        else:
            state = 'LIVE' if self._coverage_ok else 'PROTECT'
            reason = self._coverage_reason
        if state != self._state:
            self._transitions.append({'from': self._state, 'to': state,
                                      'reason': reason, 'at': float(at)})
        self._state, self._reason = state, reason
        return state

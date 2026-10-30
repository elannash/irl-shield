"""Session totals from opaque, session-stable track identifiers."""


class TrackTally:
    """Count only tracks whose masks were actually presented.

    Use separate instances for clues and faces. The upstream tracker owns
    identity; recycled or split IDs cannot prove unique physical objects.
    There is deliberately no box-per-frame or geometric fallback.
    """

    def __init__(self):
        self._seen = set()

    @property
    def count(self):
        return len(self._seen)

    def observe(self, track_ids):
        incoming = list(track_ids)
        if any(type(track) not in (int, str) or
               (type(track) is int and track < 0) or
               (type(track) is str and not 1 <= len(track) <= 128)
               for track in incoming):
            raise ValueError('Expected opaque nonnegative integer or bounded string track IDs')
        # Include the type so integer 12 and string "12" cannot alias.
        self._seen.update((type(track), track) for track in incoming)
        return self.count

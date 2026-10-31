"""Session paint, public presentation and sanitized chat skin state."""
import threading
import time

from shield.presentation import PresentationRenderer, PresentationSnapshot
from shield.render import Renderer
from shield.skins import ChatEvent, MaskRegion, SkinPainter, SkinVotes


_OPERATOR_HOLDS = frozenset(('local', 'chat', 'shield_mode', 'twitch-chat', 'eventsub'))


class Appearance:
    """Keep private pairing separate from all render inputs.

    Unique-object counters stay unavailable until upstream supplies stable IDs.
    The caption is consequently disabled, rather than counting boxes per frame.
    """

    def __init__(self, *, skin='patch', desaturation=0.0, width=1280, height=720):
        self._lock = threading.RLock()
        self._wall_offset = time.time() - time.monotonic()
        self._votes = SkinVotes(time.monotonic(), incumbent=skin)
        self._painter = SkinPainter(desaturation=desaturation)
        self._presentation = PresentationRenderer(width, height, badge=False)
        self._painted_skin = None
        self.engine = None

    def renderer(self, *, padding):
        return Renderer(padding=padding, paint=self._paint)

    def _paint(self, pixels, regions, state):
        with self._lock:
            choice = self._votes.snapshot(time.monotonic())
        painted = self._painter.paint(pixels, [MaskRegion(*region) for region in regions],
                                      state=state, skin=choice['skin'])
        if state == 'LIVE':
            with self._lock:
                self._painted_skin = painted.skin
        return painted

    def chat(self, message_id, user_id, roles, text, timestamp):
        event = ChatEvent(message_id, user_id, frozenset(roles), text,
                          timestamp - self._wall_offset)
        with self._lock:
            return self._votes.apply(event, now=time.monotonic())

    def snapshot(self):
        engine = self.engine
        if engine is None:
            state, reason = 'PROTECT', 'startup'
        else:
            with engine.lock:
                state, reason = engine.control.state, engine.control.reason
                holds = dict(engine.control._holds)
                if state == 'HOLD':
                    if 'shield_mode' in holds:
                        reason = 'shield-mode'
                    elif 'chat' in holds or 'twitch-chat' in holds or 'eventsub' in holds:
                        reason = 'moderator'
                    elif 'local' in holds:
                        reason = 'manual'
        reason = ('clear' if state == 'LIVE' else
                  'shield_mode' if reason == 'shield-mode' else
                  'chat' if reason == 'moderator' else
                  'manual' if reason == 'manual' else
                  'egress' if reason == 'egress-reconnect' else
                  'transport' if reason in ('ingest-drop', 'startup') else 'coverage')
        with self._lock:
            choice = self._votes.snapshot(time.monotonic())
            effective = self._painted_skin or choice['skin']
        return {'state': state, 'reason_code': reason, 'clues_hidden': None,
                'faces_hidden': None, 'face_mode': 'off', 'skin': effective,
                'votes': choice['votes'], 'skin_locked': choice['skin_locked']}

    def present(self, frame, *, capture_highwater):
        engine = self.engine
        if engine is None:
            raise RuntimeError('Presentation requires its session engine')
        with engine.lock:
            current_state = engine.control.state
            holds = frozenset(engine.control._holds)
        state = 'HOLD' if current_state == 'HOLD' else frame.state
        if state == 'HOLD':
            if 'shield_mode' in holds:
                shown_state, reason = 'SHIELD_MODE', 'shield_mode'
            elif holds & _OPERATOR_HOLDS:
                shown_state, reason = 'HOLD', 'moderator'
            else:
                # Transport/reconciliation safety holds recover automatically.
                shown_state, reason = 'FAILURE', 'transport'
        else:
            shown_state, reason = state, 'none' if state == 'LIVE' else 'safety_check'
        # A control HOLD fences ingress already buffered before release. Automatic
        # coverage checks fence only their output frame; a newer independently
        # covered LIVE frame may resume without waiting another full delay.
        sequence = capture_highwater if state == 'HOLD' else frame.index
        with self._lock:
            skin = self._painted_skin or self._votes.snapshot(time.monotonic())['skin']
        shown = self._presentation.render(frame.pixels, frame.mask,
            PresentationSnapshot(shown_state, reason_code=reason, skin_name=skin),
            source_sequence=sequence)
        frame.pixels, frame.mask = shown.pixels, shown.mask
        frame.slate = shown.slate
        if shown.slate:
            frame.quads = []
            frame.protected = True
            frame.state = 'HOLD' if state == 'HOLD' or shown.state in ('HOLD', 'SHIELD_MODE') else 'PROTECT'
        return frame

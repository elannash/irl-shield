"""Session paint, public presentation and sanitized chat skin state."""
import threading
import time

from shield.presentation import PresentationRenderer, PresentationSnapshot
from shield.render import Renderer
from shield.skins import ChatEvent, MaskRegion, SkinPainter, SkinVotes


class Appearance:
    """Keep private pairing separate from all render inputs.

    Unique-object counters stay unavailable until upstream supplies stable IDs.
    The caption is consequently disabled, rather than counting boxes per frame.
    """

    def __init__(self, *, skin='frosted', desaturation=0.0, width=1280, height=720):
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
            current_state, current_reason = engine.control.state, engine.control.reason
        state = 'HOLD' if current_state == 'HOLD' else frame.state
        reason = ('shield_mode' if state == 'HOLD' and current_reason == 'shield-mode'
                  else 'moderator' if state == 'HOLD' else 'safety_check' if state != 'LIVE' else 'none')
        # A hold fences the ingress high-water mark, including frames buffered
        # ahead of this delayed output. LIVE must cross that mark after release.
        sequence = capture_highwater if state != 'LIVE' else frame.index
        with self._lock:
            skin = self._painted_skin or self._votes.snapshot(time.monotonic())['skin']
        shown = self._presentation.render(frame.pixels, frame.mask,
            PresentationSnapshot(state, reason_code=reason, skin_name=skin),
            source_sequence=sequence)
        frame.pixels, frame.mask = shown.pixels, shown.mask
        frame.slate = shown.slate
        if shown.slate:
            frame.quads = []
            frame.protected = True
            frame.state = 'HOLD' if shown.state in ('HOLD', 'SHIELD_MODE') else 'PROTECT'
        return frame

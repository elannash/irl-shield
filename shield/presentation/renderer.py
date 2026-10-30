"""Cached opaque plates and source-independent slates, newly authored for W7.

Pillow rasterizes licensed glyphs only at construction. NumPy copies cached
pixels at presentation. No prototype renderer code is used.
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from shield.skins.paint import SKINS


STATES = frozenset(('LIVE', 'HOLD', 'SHIELD_MODE', 'PROTECT', 'FAILURE'))
REASONS = frozenset(('none', 'moderator', 'shield_mode', 'safety_check',
                     'transport', 'starting'))
MAX_COUNT = 999_999_999
FONT = Path(__file__).with_name('assets') / 'AtkinsonHyperlegibleNext-wght.ttf'

# RGB tokens are fixed, opaque colors over arbitrary video.
FIELD = (18, 22, 28)
PLATE = (26, 31, 38)
INK = (243, 246, 249)
MUTED = (205, 214, 224)
GREEN = (126, 225, 166)
AMBER = (244, 199, 123)
COPY = {
    'HOLD': ('Paused for privacy', 'Back when the streamer resumes'),
    'SHIELD_MODE': ('SHIELD MODE ON', 'Back when Shield Mode ends'),
    'FAILURE': ('Paused while Shield\nchecks this view', 'Back on its own once it’s safe'),
}


def _count(value):
    if type(value) is not int or not 0 <= value <= MAX_COUNT:
        raise ValueError('Expected a bounded nonnegative session count')


@dataclass(frozen=True)
class PresentationSnapshot:
    """Allowlisted public fields only; never pass engine/control dictionaries."""

    state: str
    reason_code: str = 'none'
    clue_count: int = 0
    face_count: int = 0
    skin_name: str = 'frosted'

    def __post_init__(self):
        if self.state not in STATES:
            raise ValueError('Unsupported public presentation state')
        if self.reason_code not in REASONS:
            raise ValueError('Unsupported public presentation reason')
        if self.skin_name not in SKINS:
            raise ValueError('Unsupported public presentation skin')
        _count(self.clue_count)
        _count(self.face_count)


@dataclass
class Presentation:
    pixels: np.ndarray
    mask: np.ndarray
    overlay_mask: np.ndarray
    state: str
    slate: bool


class PresentationRenderer:
    """One instance per fixed-size session, owned by one presentation thread.

    `pixels` must already be privacy-masked. `mask` is its actual coverage.
    `source_sequence` is a monotonically increasing capture serial, assigned
    before detection. After any hold a release requires a newer LIVE frame.
    Changes cut instantly; no entrance, exit, fade or original-frame sampling.
    """

    def __init__(self, width=1280, height=720, *, badge=True):
        if (type(width) is not int or type(height) is not int or
                width < 160 or height < 90 or width * 9 != height * 16):
            raise ValueError('Expected a 16:9 frame at least 160x90')
        if type(badge) is not bool:
            raise ValueError('Expected a boolean badge setting')
        self.width, self.height, self.badge = width, height, badge
        self._scale = height / 720
        self._fonts = {}
        self._slates = {state: self._make_slate(state) for state in COPY}
        self._glyphs = {text: self._text_tile(text) for text in
                        ('Shield hid ', ' clues', *'0123456789')}
        self._digit_width = max(tile.shape[1] for text, tile in self._glyphs.items()
                                if len(text) == 1)
        self._plate = None
        self._plate_count = None
        self._full_mask = np.full((height, width), 255, np.uint8)
        self._latest_sequence = -1
        self._blocked_through = -1
        self._last_slate = 'FAILURE'

    def _px(self, value):
        return max(1, round(value * self._scale))

    def _font(self, size, weight):
        key = (size, weight)
        if key not in self._fonts:
            font = ImageFont.truetype(str(FONT), self._px(size))
            font.set_variation_by_axes([weight])
            self._fonts[key] = font
        return self._fonts[key]

    def _make_slate(self, state):
        canvas = Image.new('RGB', (self.width, self.height), FIELD)
        draw = ImageDraw.Draw(canvas)
        center = self.width // 2
        accent = AMBER if state == 'FAILURE' else GREEN
        # This small geometric shield is original project artwork.
        mark = [(center + round(x * self._scale), self._px(y)) for x, y in
                ((0, 190), (26, 200), (23, 229), (0, 247), (-23, 229), (-26, 200))]
        draw.polygon(mark, fill=accent)
        headline, back = COPY[state]
        lines = headline.split('\n')
        top = 298 if len(lines) == 1 else 270
        for i, line in enumerate(lines):
            draw.text((center, self._px(top + i * 68)), line,
                      font=self._font(60, 650), fill=INK, anchor='mt')
        draw.text((center, self._px(425)), back, font=self._font(40, 450),
                  fill=MUTED, anchor='mt')
        return np.asarray(canvas)[:, :, ::-1].copy()

    def _text_tile(self, text):
        font = self._font(40, 550)
        width = max(1, int(np.ceil(font.getlength(text))))
        canvas = Image.new('RGB', (width, self._px(52)), PLATE)
        ImageDraw.Draw(canvas).text((0, self._px(4)), text, font=font, fill=INK,
                                   anchor='lt')
        return np.asarray(canvas)[:, :, ::-1].copy()

    def _badge_plate(self, count):
        if count != self._plate_count:
            digits = str(count)
            prefix, suffix = self._glyphs['Shield hid '], self._glyphs[' clues']
            padding = self._px(16)
            width = 2 * padding + prefix.shape[1] + len(digits) * self._digit_width + suffix.shape[1]
            plate = np.empty((self._px(72), width, 3), np.uint8)
            plate[:] = PLATE[::-1]
            x, y = padding, self._px(10)
            for tile, cell in [(prefix, prefix.shape[1]),
                               *((self._glyphs[digit], self._digit_width) for digit in digits),
                               (suffix, suffix.shape[1])]:
                offset = (cell - tile.shape[1]) // 2
                plate[y:y + tile.shape[0], x + offset:x + offset + tile.shape[1]] = tile
                x += cell
            self._plate, self._plate_count = plate, count
        return self._plate

    def render(self, pixels, mask, snapshot, *, source_sequence):
        shape = (self.height, self.width)
        if (not isinstance(pixels, np.ndarray) or pixels.dtype != np.uint8 or
                pixels.shape != (*shape, 3) or not isinstance(mask, np.ndarray) or
                mask.dtype != np.uint8 or mask.shape != shape):
            raise ValueError('Expected configured uint8 BGR pixels and coverage mask')
        if not isinstance(snapshot, PresentationSnapshot):
            raise ValueError('Expected a safe presentation snapshot')
        if type(source_sequence) is not int or source_sequence < 0:
            raise ValueError('Expected a nonnegative capture sequence')
        self._latest_sequence = max(self._latest_sequence, source_sequence)
        if snapshot.state != 'LIVE':
            state = ('SHIELD_MODE' if snapshot.state == 'SHIELD_MODE' or
                     (snapshot.state == 'HOLD' and snapshot.reason_code == 'shield_mode')
                     else 'HOLD' if snapshot.state == 'HOLD' else 'FAILURE')
            self._last_slate = state
            self._blocked_through = self._latest_sequence
        if snapshot.state != 'LIVE' or source_sequence <= self._blocked_through:
            return Presentation(self._slates[self._last_slate].copy(), self._full_mask.copy(),
                                self._full_mask.copy(), self._last_slate, True)
        output = pixels.copy()
        covered = mask.copy()
        overlay = np.zeros(shape, np.uint8)
        if self.badge:
            plate = self._badge_plate(snapshot.clue_count)
            h, w = plate.shape[:2]
            x, y = self._px(24), self.height - self._px(24) - h
            output[y:y + h, x:x + w] = plate
            covered[y:y + h, x:x + w] = 255
            overlay[y:y + h, x:x + w] = 255
        return Presentation(output, covered, overlay, 'LIVE', False)

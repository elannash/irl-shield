"""Continuous source clock around the single shared MaskingEngine.

Transport holds have their own source, so a reconnect cannot clear M3's hold.
The sink receives only objects returned by engine.poll, never decoded frames.
"""
import math
import time

import cv2
import numpy as np

from relay.security import TwitchStub
from shield.types import Frame


class RelayControl:
    def __init__(self, engine):
        self.engine = engine
        self.twitch = TwitchStub()

    def hold(self, active, source='local', reason='manual', now=None):
        twitch_sources = {'chat': 'moderator', 'shield_mode': 'shield-mode',
                          'twitch-connection': 'shield-mode', 'twitch-reconcile': 'shield-mode'}
        if source in twitch_sources:
            # M3 owns its fixed reasons; do not forward arbitrary callback text.
            return self.engine.hold(bool(active), source=source, reason=twitch_sources[source], now=now)

        # Source names/reasons are controlled vocabulary, never raw chat text.
        if source not in ('local', 'twitch-chat', 'eventsub'):
            raise ValueError('Unknown control source')
        if reason not in ('manual', 'synthetic hold', 'moderator', 'shield-mode'):
            raise ValueError('Unknown hold reason')
        return self.engine.hold(bool(active), source=source, reason=reason, now=now)

    def set_stream_key(self, key):
        self.twitch.set_key(key)


class RelaySession:
    def __init__(self, engine, sink, width=1280, height=720, fps=30, start=None, control=None):
        if fps != 30 or min(width, height) < 32 or width % 2 or height % 2:
            raise ValueError('Live transport requires even dimensions and 30fps')
        self.engine, self.sink = engine, sink
        self.width, self.height, self.fps = width, height, fps
        self.start = time.monotonic() if start is None else start
        self.control = control if control is not None else RelayControl(engine)
        self.generation = None
        self.source_origin = self.session_pts = None
        self.last_index = 0
        self.sessions = self.disconnections = self.video_drops = self.audio_drops = 0
        self.audio_capacity = math.ceil((engine.delay + 3) * 48000)
        self.samples = np.zeros(self.audio_capacity, np.int16)
        self.tags = np.full(self.audio_capacity, -1, np.int64)
        self.audio_cursor = 0
        self.egress_interruptions = 0
        self._egress_holding = False
        self.engine.hold(True, source='transport', reason='startup')
        self.engine.submit(Frame(0, 0., np.zeros((height, width, 3), np.uint8)), now=self.start)

    def video(self, pts, pixels, generation, now=None):
        now = time.monotonic() if now is None else now
        if not math.isfinite(pts) or pixels.dtype != np.uint8 or pixels.ndim != 3 or pixels.shape[2] != 3:
            raise ValueError('Invalid decoded video')
        if generation != self.generation:
            self.audio_drops += int((self.tags >= self.audio_cursor).sum())
            self.tags.fill(-1)
            self.generation, self.source_origin = generation, pts
            self.session_pts = max(self.last_index + 1, round((now - self.start) * self.fps)) / self.fps
            self.sessions += 1
        index = round((self.session_pts + pts - self.source_origin) * self.fps)
        if index <= self.last_index:
            self.video_drops += 1
            return
        if pixels.shape[:2] != (self.height, self.width):
            pixels = cv2.resize(pixels, (self.width, self.height))
        self.engine.hold(False, source='transport', now=now)
        self.engine.submit(Frame(index, index / self.fps, pixels), now=now)
        self.last_index = index

    def audio(self, pts, samples, generation):
        if generation != self.generation or not math.isfinite(pts):
            self.audio_drops += len(samples)
            return
        first = round((self.session_pts + pts - self.source_origin) * 48000)
        indices = np.arange(first, first + len(samples))
        valid = (indices >= self.audio_cursor) & (indices < self.audio_cursor + self.audio_capacity)
        self.audio_drops += int((~valid).sum())
        slots = indices[valid] % self.audio_capacity
        self.samples[slots] = samples[valid]
        self.tags[slots] = indices[valid]

    def disconnected(self):
        self.disconnections += 1
        self.audio_drops += int((self.tags >= self.audio_cursor).sum())
        self.tags.fill(-1)
        self.engine.hold(True, source='transport', reason='ingest-drop')

    def tick(self, now=None):
        for result in self.engine.poll(now=now):
            first = round(result.pts * 48000)
            indices = np.arange(first, first + 1600)
            slots = indices % self.audio_capacity
            pcm = np.where(self.tags[slots] == indices, self.samples[slots], 0).astype(np.int16)
            self.tags[slots] = -1
            self.audio_cursor = first + 1600
            # poll() releases the engine lock before transport writes. A hold
            # arriving in that interval must not forward the stale LIVE pixels.
            if self.engine.control.state == 'HOLD' and not result.slate:
                result.pixels = np.zeros_like(result.pixels)
                result.mask = np.full_like(result.mask, 255)
                result.quads = []
                result.state, result.protected, result.slate = 'HOLD', True, True
            accepted = self.sink(result, pcm)
            if accepted is False:
                self.egress_interruptions += 1
                self.engine.hold(True, source='egress', reason='egress-reconnect')
                self._egress_holding = True
                self.audio_drops += int((self.tags >= self.audio_cursor).sum())
                self.tags.fill(-1)
                return
            if self._egress_holding and accepted is True:
                self.engine.hold(False, source='egress')
                self._egress_holding = False

    @property
    def stats(self):
        return {'sessions': self.sessions, 'disconnections': self.disconnections,
                'egress_interruptions': self.egress_interruptions,
                'video_drops': self.video_drops, 'audio_dropped_samples': self.audio_drops,
                'audio_buffer_samples': int((self.tags >= self.audio_cursor).sum()),
                'audio_capacity_samples': self.audio_capacity}

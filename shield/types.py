"""Value records shared at the engine's detector, render and transport seams."""
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class Frame:
    index: int
    pts: float
    pixels: np.ndarray


@dataclass(frozen=True)
class Detection:
    lane: str
    frame_index: int
    quads: list
    completed_at: float
    error: str | None = None


@dataclass(frozen=True)
class Coverage:
    fast_age: int | None
    accurate_age: int | None
    ok: bool
    reason: str


@dataclass
class PresentedFrame:
    index: int
    pts: float
    pixels: np.ndarray
    mask: np.ndarray
    quads: list
    coverage: Coverage
    state: str
    deadline: float
    presented_at: float
    protected: bool
    slate: bool

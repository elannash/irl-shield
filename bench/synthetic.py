"""Deterministic text fixtures composited over real video.

``quad`` bounds the text ink, in clockwise TL/TR/BR/BL pixel coordinates, not
its sign backing. It can extend outside the image during entry and exit.
``visible`` is true when at least 30% of the text quad is on screen and the
text is at least 8 pixels tall. ``visibility_fraction`` records the clipped
quad area divided by its full area. IDs stay stable for the life of a sign.
Coordinates use the input image's pixel space.
"""

from functools import lru_cache
from pathlib import Path
import math

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


_FONT_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "fonts"
_FONTS = ("DejaVuSans-Bold.ttf", "DejaVuSansMono-Bold.ttf", "DejaVuSerif-Bold.ttf")
_TEXTS = (
    ("CEDAR AVE", "PINE STREET", "NORTH 8TH ST", "MAPLE ROAD"),
    ("7KQ 482", "BXR 219", "4NV 635", "JHT 806"),
    ("1842", "307", "5916", "728"),
    ("NORTHSIDE MARKET", "HARBOR CAFE", "CEDAR BOOKS", "LUNA PHARMACY"),
)
_KINDS = ("street", "plate", "house", "storefront")
# Positions keep the four simultaneous targets apart while the plate crosses
# a frame edge and the others move with a gently turning camera.
_CENTERS = ((0.29, 0.18), (0.50, 0.82), (0.16, 0.54), (0.73, 0.43))


@lru_cache(maxsize=192)
def _sign(kind: int, text: str, font_index: int, size: int):
    font = ImageFont.truetype(str(_FONT_DIR / _FONTS[font_index]), size)
    left, top, right, bottom = font.getbbox(text)
    pad_x, pad_y = max(6, size // 3), max(5, size // 4)
    width, height = right - left + 2 * pad_x, bottom - top + 2 * pad_y
    backgrounds = ((30, 92, 58, 255), (234, 231, 211, 255),
                   (38, 45, 55, 255), (232, 208, 158, 255))
    foregrounds = ((255, 255, 247, 255), (19, 24, 29, 255),
                   (255, 244, 218, 255), (54, 32, 23, 255))
    panel = Image.new("RGBA", (width, height), backgrounds[kind])
    draw = ImageDraw.Draw(panel)
    draw.rectangle((2, 2, width - 3, height - 3), outline=foregrounds[kind], width=1)
    draw.text((pad_x - left, pad_y - top), text, font=font, fill=foregrounds[kind])
    # The bbox's origin is removed above; this rectangle exactly encloses the
    # font's ink, rather than the padded board that is easier to detect.
    text_quad = np.array(((pad_x, pad_y), (width - pad_x, pad_y),
                          (width - pad_x, height - pad_y), (pad_x, height - pad_y)),
                         dtype=np.float32)
    return np.asarray(panel), text_quad


def _quad(panel_width: int, panel_height: int, center, angle: float, perspective: float):
    points = np.array(((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)), dtype=np.float32)
    points[:, 0] *= panel_width
    points[:, 1] *= panel_height
    # Opposing edges differ in height: a planar sign viewed off axis.
    points[0, 1] += perspective * panel_height
    points[3, 1] -= perspective * panel_height
    rotation = np.array(((math.cos(angle), -math.sin(angle)),
                         (math.sin(angle), math.cos(angle))), dtype=np.float32)
    return (points @ rotation.T + np.asarray(center, dtype=np.float32)).astype(np.float32)


def overlay(frame_bgr: np.ndarray, frame_index: int, fps: float, seed: int,
            camera_offset: tuple[float, float] = (0.0, 0.0)) -> tuple[np.ndarray, list[dict]]:
    """Return a new BGR frame and exact, repeatable per-frame text truth.

    Four kinds cycle independently every 4.8 seconds. Seed controls their text,
    font, size, rotation and perspective; frame time controls continuous motion.
    camera_offset adds measured pixel translation to the three scene-attached
    signs; the travelling plate keeps its independent edge-entry path.
    No global RNG, mutable scene state, OS font lookup, or video metadata enters
    the result, so random-access decoding produces the same frame and labels.
    """
    if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3 or frame_bgr.dtype != np.uint8:
        raise ValueError("frame_bgr must be a uint8 HxWx3 BGR image")
    if frame_index < 0 or not math.isfinite(fps) or fps <= 0:
        raise ValueError("frame_index must be nonnegative and fps must be finite and positive")
    camera_dx, camera_dy = camera_offset
    if not math.isfinite(camera_dx) or not math.isfinite(camera_dy):
        raise ValueError("camera_offset must contain two finite pixel offsets")
    height, width = frame_bgr.shape[:2]
    if min(width, height) < 32:
        raise ValueError("frame must be at least 32 pixels in each dimension")
    time = frame_index / fps
    result = frame_bgr.copy()
    truth = []
    for kind in range(4):
        scene_time = time + kind * 0.67
        interval = int(scene_time // 4.8)
        phase = (scene_time % 4.8) / 4.8
        rng = np.random.default_rng(np.random.SeedSequence([int(seed) & 0xFFFFFFFF, kind, interval]))
        text = _TEXTS[kind][int(rng.integers(0, len(_TEXTS[kind])))]
        font_index = int(rng.integers(0, len(_FONTS)))
        base_size = (34, 32, 42, 26)[kind]
        size = max(10, round((base_size + int(rng.integers(-6, 9))) * height / 720))
        panel, text_quad = _sign(kind, text, font_index, size)
        panel_height, panel_width = panel.shape[:2]
        center_x, center_y = _CENTERS[kind]
        center_x = width * (center_x + 0.018 * math.sin(time * 1.5 + kind))
        center_y = height * (center_y + 0.014 * math.sin(time * 1.2 + kind * 0.6))
        # Cross the frame from left to right. At 30 fps the first visible letters
        # are recorded in truth with the precise fraction inside the viewport.
        if kind == 1:
            center_x = -panel_width * 0.65 + phase * (width + panel_width * 1.3)
        else:
            center_x += camera_dx
            center_y += camera_dy
        angle = math.radians(float(rng.uniform(-10, 10)) + 2.0 * math.sin(time * 0.9 + kind))
        perspective = float(rng.uniform(-0.14, 0.14)) + 0.025 * math.sin(time + kind)
        destination = _quad(panel_width, panel_height, (center_x, center_y), angle, perspective)
        source = np.array(((0, 0), (panel_width - 1, 0),
                           (panel_width - 1, panel_height - 1), (0, panel_height - 1)), dtype=np.float32)
        matrix = cv2.getPerspectiveTransform(source, destination)
        text_destination = cv2.perspectiveTransform(text_quad[None], matrix)[0]
        viewport = np.array(((0, 0), (width, 0), (width, height), (0, height)), dtype=np.float32)
        full_area = float(cv2.contourArea(text_destination))
        clipped_area, _ = cv2.intersectConvexConvex(text_destination, viewport)
        visibility_fraction = max(0.0, min(1.0, float(clipped_area) / full_area))
        text_height = min(float(np.linalg.norm(text_destination[3] - text_destination[0])),
                          float(np.linalg.norm(text_destination[2] - text_destination[1])))
        visible = bool(visibility_fraction >= 0.30 and text_height >= 8.0)
        # Warp only the local region touched by a sign, which keeps fixture
        # generation from doing four full-frame perspective warps per frame.
        x0 = max(0, math.floor(float(destination[:, 0].min())) - 1)
        y0 = max(0, math.floor(float(destination[:, 1].min())) - 1)
        x1 = min(width, math.ceil(float(destination[:, 0].max())) + 2)
        y1 = min(height, math.ceil(float(destination[:, 1].max())) + 2)
        if x1 > x0 and y1 > y0:
            local_matrix = matrix.copy()
            local_matrix[0] -= x0 * local_matrix[2]
            local_matrix[1] -= y0 * local_matrix[2]
            warped = cv2.warpPerspective(panel, local_matrix, (x1 - x0, y1 - y0), flags=cv2.INTER_LINEAR)
            alpha = warped[:, :, 3:4].astype(np.float32) / 255.0
            roi = result[y0:y1, x0:x1]
            roi[:] = np.rint(warped[:, :, :3][:, :, ::-1] * alpha + roi * (1 - alpha)).astype(np.uint8)
        truth.append({"id": f"{int(seed)}:{_KINDS[kind]}:{interval}", "text": text,
                      "quad": text_destination.astype(float).tolist(), "visible": visible,
                      "visibility_fraction": visibility_fraction})
    return result, truth

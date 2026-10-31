"""Wholly synthetic, silent and brand-free skin review fixture."""
import cv2
import numpy as np

from shield.skins import MaskRegion


def scene():
    frame = np.full((360, 640, 3), (201, 184, 157), np.uint8)
    cv2.rectangle(frame, (0, 120), (230, 359), (179, 191, 198), -1)
    cv2.rectangle(frame, (410, 60), (639, 359), (124, 151, 168), -1)
    cv2.fillConvexPoly(frame, np.array([[180, 360], [330, 220], [410, 220], [530, 360]]), (145, 145, 140))
    for x in (20, 72, 124, 176, 442, 498, 554, 610):
        for y in (150, 220, 290):
            cv2.rectangle(frame, (x, y), (x + 24, y + 40), (64, 72, 76), -1)
    cv2.rectangle(frame, (240, 170), (397, 205), (58, 105, 53), -1)
    cv2.putText(frame, 'ALDER WAY', (248, 194), cv2.FONT_HERSHEY_SIMPLEX, .65, (255, 255, 255), 2, cv2.LINE_8)
    cv2.rectangle(frame, (425, 90), (610, 129), (220, 230, 240), -1)
    cv2.putText(frame, '1842', (470, 120), cv2.FONT_HERSHEY_SIMPLEX, 1, (12, 12, 12), 3, cv2.LINE_8)
    cv2.rectangle(frame, (24, 88), (191, 129), (55, 60, 65), -1)
    cv2.putText(frame, '37', (76, 118), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 3, cv2.LINE_8)
    regions = []
    for left, top, width, height, text_height in [(236, 166, 166, 44, 22), (421, 86, 194, 48, 30), (20, 84, 176, 50, 30)]:
        regions.append(MaskRegion(left, top, np.full((height, width), 255, np.uint8), text_height))
    return frame, regions


def cost_scene():
    rng = np.random.default_rng(1804)
    frame = rng.integers(0, 256, (720, 1280, 3), np.uint8)
    regions = [MaskRegion(16 + column * 208, 24 + row * 168,
                          np.full((48, 160), 255, np.uint8), 24)
               for row in range(4) for column in range(6)]
    return frame, regions

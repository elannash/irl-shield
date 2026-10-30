"""Opaque masks over BGR frames; no stream or codec dependencies."""
import numpy as np


def masked_frame(frame, boxes, padding):
    output = frame.copy()
    h, w = frame.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    for x0, y0, x1, y1 in boxes:
        pad = max(3, (y1 - y0) * padding)
        x0, x1 = max(0, int(x0-pad)), min(w, int(np.ceil(x1+pad)))
        y0, y1 = max(0, int(y0-pad)), min(h, int(np.ceil(y1+pad)))
        if x1 > x0 and y1 > y0:
            mask[y0:y1, x0:x1] = 255
            output[y0:y1, x0:x1] = 0
    return output, mask



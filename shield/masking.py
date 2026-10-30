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



def text_geometry(quads):
    """Return exact projected quads and per-quad text-height estimates for paint.

    The shorter mean of opposite hull edges is a geometry estimate, not an OCR
    ink measurement. Consumers must paint the supplied actual raster mask and
    cannot shrink it using this estimate.
    """
    import cv2
    points=np.asarray(list(quads),dtype=np.float64)
    if not len(points):
        return {"quads":[],"estimated_text_heights":[],"height_scope":"shorter opposite-edge mean; not observed ink"}
    if points.shape[1:]!=(4,2) or not np.isfinite(points).all():
        raise ValueError("Text geometry needs four finite quad vertices")
    heights=[]
    for quad in points:
        hull=cv2.convexHull(quad.astype(np.float32)).reshape(-1,2)
        if len(hull)!=4:
            raise ValueError("Text geometry needs convex quads")
        edges=np.linalg.norm(np.roll(hull,-1,axis=0)-hull,axis=1)
        heights.append(float(min((edges[0]+edges[2])/2,(edges[1]+edges[3])/2)))
    return {"quads":points.tolist(),"estimated_text_heights":heights,
            "height_scope":"shorter opposite-edge mean; not observed ink"}

"""Supplemental flicker evidence; existing privacy scoring is unchanged."""
import math
import numpy as np

SCOPE=("Distinct per-clip frames with observed unmasked truth between two observed fully masked anchors in the same truth interval. "
       "Natural truth uses independent input judges; all output judges can establish a leak. "
       "Unsampled/input-unobserved/partially masked/protected frames are unknown, never clean. "
       "Full box coverage is a geometric masked anchor, not proof of OCR or ink hiding.")


def mask_observations(mask, targets):
    height,width=mask.shape
    rows=[]
    for target in targets:
        box=target["box"]
        if len(box)!=4 or not all(math.isfinite(float(v)) for v in box):
            raise ValueError("Flicker target needs a finite box")
        left,top=np.maximum(0,np.floor(box[:2])).astype(int)
        right,bottom=np.minimum([width,height],np.ceil(box[2:])).astype(int)
        fraction=float((mask[top:bottom,left:right]>0).mean()) if right>left and bottom>top else None
        rows.append({"box":list(box),"fraction":fraction})
    return rows


def interval_flicker(tracks, coverage, *, sampled_frames, protected_frames):
    details=[]
    flicker=set()
    totals={"known_masked_observations":0,"known_unmasked_observations":0,"unknown_observations":0}
    for track in tracks:
        observed=dict(track["observations"])
        states=[]
        for frame in range(track["first"],track["last"]+1):
            state="unknown"
            if frame in sampled_frames and frame in observed and frame not in protected_frames:
                if frame in track["leak_frames"]:
                    state="unmasked"
                else:
                    fractions=[r["fraction"] for r in coverage[frame] if list(r["box"])==list(observed[frame])]
                    fraction=fractions[0] if fractions else None
                    if fraction==1.:
                        state="masked"
                    elif fraction==0.:
                        state="unmasked"
            states.append(state)
            totals[{"masked":"known_masked_observations","unmasked":"known_unmasked_observations","unknown":"unknown_observations"}[state]]+=1
        anchors=[i for i,s in enumerate(states) if s=="masked"]
        leaks=[track["first"]+i for i,s in enumerate(states) if len(anchors)>=2 and anchors[0]<i<anchors[-1] and s=="unmasked"]
        flicker.update(leaks)
        details.append({"first":track["first"],"last":track["last"],"states":states,"flicker_leak_frames":leaks})
    return {"scope":SCOPE,"flicker_leak_frames":sorted(flicker),"flicker_leak_count":len(flicker),
            "evaluated_interval_frame_pairs":sum(totals.values()),**totals,"intervals":details}

"""Opt-in Paddle recall arms. No raw quad is trimmed, suppressed or area-capped.

Reuses existing model manifests/licenses, NumPy BSD-3-Clause and OpenCV Apache-2.0.
Each wrapper records its component identities; detector calls remain synchronous.
"""
import math
import cv2
import numpy as np

ARMS=("w1-small-server-union","w1-small-light-pair","w1-small-tiled")


def light_pair(pixels):
    lab=cv2.cvtColor(pixels,cv2.COLOR_BGR2LAB)
    lab[:,:,0]=cv2.createCLAHE(clipLimit=2.,tileGridSize=(8,8)).apply(lab[:,:,0])
    contrast=cv2.cvtColor(lab,cv2.COLOR_LAB2BGR)
    return [cv2.LUT(contrast,np.rint(255*(np.arange(256)/255.)**gamma).astype(np.uint8)) for gamma in (.6,1.6)]


class RecallDetector:
    def __init__(self,name,models,expected_shape):
        self.name,self.models,self.expected_shape=name,models,expected_shape
        self.metadata={"name":name,"detector_families":["paddleocr"],
                       "components":{key:backend.metadata for key,backend in models.items()},
                       "raw_geometry_policy":"Union every component quad; no NMS, trim or area exemption",
                       "light_pair_gamma":[.6,1.6] if name=="w1-small-light-pair" else None}

    def detect_quads(self,pixels):
        if pixels.shape[:2]!=self.expected_shape:
            raise ValueError("Recall wrapper input differs from its declared preprocessing shape")
        quads=list(self.models["base"].detect_quads(pixels))
        if self.name=="w1-small-server-union":
            quads.extend(self.models["server"].detect_quads(pixels))
        elif self.name=="w1-small-light-pair":
            for augmented in light_pair(pixels):
                quads.extend(self.models["base"].detect_quads(augmented))
        else:
            height,width=pixels.shape[:2]
            th,tw=math.ceil(height*.6),math.ceil(width*.6)
            for y in (0,height-th):
                for x in (0,width-tw):
                    for quad in self.models["tile"].detect_quads(pixels[y:y+th,x:x+tw]):
                        quads.append((np.asarray(quad,dtype=float)+[x,y]).tolist())
        return quads

    def close(self):
        errors=[]
        for backend in self.models.values():
            try: backend.close()
            except Exception as error: errors.append(error)
        if errors: raise ExceptionGroup("Recall detector cleanup failed",errors)


def create_arm(name,options,*,detector_factory=None):
    if name not in ARMS:
        raise ValueError("Unknown W1 recall arm")
    if detector_factory is None:
        from bench.pipeline import detector_for
        detector_factory=detector_for
    height,width=options["input_size"]
    lane_width=options.get("detect_width",width) or width
    height,width=round(height*lane_width/width),lane_width
    models={}
    try:
        models["base"]=detector_factory("ppocr-v6-small",options)
        if name=="w1-small-server-union":
            models["server"]=detector_factory("ppocr-v5-server",options)
        if name=="w1-small-tiled":
            th,tw=math.ceil(height*.6),math.ceil(width*.6)
            models["tile"]=detector_factory("ppocr-v6-small",{**options,"input_size":[th,tw],"detect_width":tw})
        return RecallDetector(name,models,(height,width))
    except BaseException:
        for backend in models.values(): backend.close()
        raise

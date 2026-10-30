"""A bounded BGR frame processor. The caller owns transport, clock and detector lifetime."""
from collections import deque
from dataclasses import dataclass

import cv2
import numpy as np

from shield.masking import masked_frame


@dataclass
class MaskedFrame:
    index: int
    pixels: np.ndarray
    mask: np.ndarray
    boxes: list


class MaskingEngine:
    def __init__(self,detector,options):
        self.detector=detector
        self.padding=options.get('padding',.3)
        self.persistence=options.get('persistence',1)
        self.lookahead=options.get('lookahead',0)
        self.stride=options.get('stride',1)
        self.detect_width=options.get('detect_width')
        if self.persistence<1 or self.lookahead<0 or self.stride<1:
            raise ValueError('Invalid temporal configuration')
        self.history=deque()
        self.pending=deque()
        self.index=0
        self.boxes=[]
        self.shape=None
        self.finished=False

    def push(self,frame):
        """Accept an owned snapshot of one H×W×3 uint8 BGR frame; return zero or one output."""
        if self.finished:
            raise RuntimeError('Cannot push after flush')
        if frame.dtype!=np.uint8 or frame.ndim!=3 or frame.shape[2]!=3:
            raise ValueError('Expected an H×W×3 uint8 BGR frame')
        if self.shape is not None and frame.shape!=self.shape:
            raise ValueError('Resolution changed with frames pending; recreate the engine')
        self.shape=frame.shape
        h,w=frame.shape[:2]
        if self.index%self.stride==0:
            scale=(self.detect_width or w)/w
            small=cv2.resize(frame,(int(w*scale),int(h*scale))) if scale!=1 else frame
            self.boxes=[[float(v)/scale for v in box] for box in self.detector.detect(small)]
        self.history.append((self.index,self.boxes))
        # Transport buffers may be reused immediately after this call returns.
        self.pending.append((self.index,frame.copy()))
        self.index+=1
        return self._emit() if len(self.pending)>self.lookahead else None

    def _emit(self):
        index,frame=self.pending.popleft()
        boxes=[b for i,group in self.history if index-self.persistence+1<=i<=index+self.lookahead for b in group]
        output,mask=masked_frame(frame,boxes,self.padding)
        while self.history and self.history[0][0]<index-self.persistence+1:
            self.history.popleft()
        return MaskedFrame(index,output,mask,boxes)

    def flush(self):
        """Emit the bounded tail at EOF. No further frames can be submitted."""
        self.finished=True
        while self.pending:
            yield self._emit()

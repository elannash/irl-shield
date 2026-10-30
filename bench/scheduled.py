"""Two persistent Vision lanes with a bounded accurate-pass cadence.

The slow lane never skips a scheduled frame: it applies backpressure when late.
The pipeline's delayed mask window can then cover a sign's entrance before its
first completed accurate observation. A failure on either lane aborts the run.
"""
from concurrent.futures import ThreadPoolExecutor

import cv2

from bench.vision import Vision


class ScheduledVision:
    def __init__(self, options):
        self.fast=Vision('vision-rectangles')
        self.accurate=Vision('vision-accurate')
        self.executor=ThreadPoolExecutor(max_workers=1)
        self.future=None
        self.index=0
        self.last=[]
        self.period=options.get('accurate_stride',6)
        self.fast_width=options.get('rectangle_width',640)
        self.accurate_width=options.get('accurate_width',960)
        if self.period<1:
            raise ValueError('accurate_stride must be positive')
        self.metadata={'engine':'vision-scheduled','detector_families':['apple-vision'],'accurate_stride':self.period,
                       'rectangle_width':self.fast_width,'accurate_width':self.accurate_width,
                       'schedule':'No dropped accurate jobs; block if previous pass is late',
                       'accurate':self.accurate.metadata,'rectangles':self.fast.metadata}

    def _accurate(self, frame):
        h,w=frame.shape[:2]
        scale=self.accurate_width/w
        small=cv2.resize(frame,(self.accurate_width,round(h*scale)))
        return [[v/scale for v in box] for box in self.accurate.detect(small)]

    def warmup(self,frame):
        self._accurate(frame)
        h,w=frame.shape[:2]
        self.fast.detect(cv2.resize(frame,(self.fast_width,round(h*self.fast_width/w))))

    def detect(self, frame):
        if self.future and (self.future.done() or self.index%self.period==0):
            self.last=self.future.result()
            self.future=None
        if self.index%self.period==0:
            self.future=self.executor.submit(self._accurate,frame.copy())
        h,w=frame.shape[:2]
        scale=self.fast_width/w
        small=cv2.resize(frame,(self.fast_width,round(h*scale)))
        boxes=[[v/scale for v in box] for box in self.fast.detect(small)]
        self.index+=1
        return boxes+self.last

    def close(self):
        try:
            if self.future:
                self.future.result(timeout=35)
        finally:
            self.executor.shutdown(wait=True,cancel_futures=True)
            try:
                self.fast.close()
            finally:
                self.accurate.close()

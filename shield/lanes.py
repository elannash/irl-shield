"""Newest-frame detector workers. A slow model drops work, never source frames.

OpenCV (Apache-2.0) resizes input; injected adapters own model licensing and inference.
"""
from collections import deque
import threading
import time

import cv2

from shield.types import Detection


class DetectorLane:
    def __init__(self,name,backend,rate_hz,width=0,fault_intervals=()):
        if rate_hz<=0 or width<0:
            raise ValueError('Invalid lane rate or width')
        self.name,self.backend,self.width=name,backend,width
        self.period=1/rate_hz
        self.fault_intervals=fault_intervals
        self.condition=threading.Condition()
        self.latest=None
        self.origin=None
        self.results=deque()
        self.stopping=False
        self.completed=self.failed=self.offered=0
        self.service_seconds=deque(maxlen=4096)
        self.thread_cpu_seconds=deque(maxlen=4096)
        self.thread=threading.Thread(target=self._run,name=f'shield-{name}',daemon=True)
        self.thread.start()

    def offer(self,frame):
        with self.condition:
            if self.stopping:
                raise RuntimeError('Detector lane is closed')
            if self.origin is None:
                self.origin=time.monotonic()-frame.pts
            self.latest=frame
            self.offered+=1
            self.condition.notify()

    def _run(self):
        next_allowed=0.
        while True:
            with self.condition:
                while not self.stopping and (self.latest is None or time.monotonic()<next_allowed):
                    delay=max(0,next_allowed-time.monotonic()) if self.latest is not None else None
                    self.condition.wait(delay)
                if self.stopping:
                    return
                frame,self.latest=self.latest,None
            began,cpu=time.monotonic(),time.thread_time()
            next_allowed=began+self.period
            try:
                for start,end in self.fault_intervals:
                    if start<=frame.pts<end:
                        with self.condition:
                            until=self.origin+end
                            while not self.stopping and time.monotonic()<until:
                                self.condition.wait(until-time.monotonic())
                            if self.stopping:
                                return
                h,w=frame.pixels.shape[:2]
                scale=self.width/w if self.width else 1.
                pixels=cv2.resize(frame.pixels,(self.width,round(h*scale))) if scale!=1 else frame.pixels
                if hasattr(self.backend,'detect_quads'):
                    quads=self.backend.detect_quads(pixels)
                else:
                    quads=[[[x0,y0],[x1,y0],[x1,y1],[x0,y1]] for x0,y0,x1,y1 in self.backend.detect(pixels)]
                quads=[[[float(x)/scale,float(y)/scale] for x,y in quad] for quad in quads]
                result=Detection(self.name,frame.index,quads,time.monotonic())
                self.completed+=1
            except Exception as error:
                result=Detection(self.name,frame.index,[],time.monotonic(),f'{type(error).__name__}: {error}')
                self.failed+=1
            self.service_seconds.append(time.monotonic()-began)
            self.thread_cpu_seconds.append(time.thread_time()-cpu)
            with self.condition:
                self.results.append(result)

    def drain(self):
        with self.condition:
            results=list(self.results)
            self.results.clear()
            return results

    def close(self):
        with self.condition:
            self.stopping=True
            self.condition.notify_all()
        self.thread.join(timeout=35)
        try:
            self.backend.close()
        finally:
            if self.thread.is_alive():
                raise RuntimeError(f'Detector lane {self.name} did not stop')

    @property
    def stats(self):
        return {'rate_hz':1/self.period,'offered':self.offered,'completed':self.completed,'failed':self.failed,
                'service_seconds':list(self.service_seconds),'thread_cpu_seconds':list(self.thread_cpu_seconds),
                'sample_capacity':4096,'backend':getattr(self.backend,'metadata',{})}

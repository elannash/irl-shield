import threading
import time
import unittest

import numpy as np

from shield.types import Frame
from shield.lanes import DetectorLane


class BlockingBackend:
    metadata={'adapter':'synthetic controlled detector'}
    def __init__(self):
        self.entered=threading.Event()
        self.release=threading.Event()
    def detect(self,pixels):
        if int(pixels[0,0,0])==0:
            self.entered.set()
            if not self.release.wait(1):
                raise TimeoutError('Synthetic lane stall was not released')
        return [[0,0,4,4]]
    def close(self):
        self.release.set()


class DetectorLanes(unittest.TestCase):
    def test_slow_detection_does_not_block_ingest_and_next_job_is_newest(self):
        backend=BlockingBackend()
        lane=DetectorLane('accurate',backend,rate_hz=1000,width=8)
        try:
            lane.offer(Frame(0,0,np.zeros((8,8,3),np.uint8)))
            self.assertTrue(backend.entered.wait(1))
            self.assertEqual(lane.drain(),[])
            lane.offer(Frame(1,1/30,np.ones((8,8,3),np.uint8)))
            lane.offer(Frame(2,2/30,np.full((8,8,3),2,np.uint8)))
            backend.release.set()
            results=[]
            until=time.monotonic()+2
            while len(results)<2 and time.monotonic()<until:
                results.extend(lane.drain())
                time.sleep(.005)
            self.assertEqual([r.frame_index for r in results],[0,2])
            self.assertTrue(all(r.error is None for r in results))
            self.assertEqual(results[0].quads,[[[0.,0.],[4.,0.],[4.,4.],[0.,4.]]])
        finally:
            lane.close()

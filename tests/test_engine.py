import unittest

import numpy as np

from bench.reference_engine import MaskingEngine


class RedPixelDetector:
    def detect(self,frame):
        y,x=np.where((frame[:,:,2]==255)&(frame[:,:,0]==0))
        return [[int(x.min()),int(y.min()),int(x.max()+1),int(y.max()+1)]] if len(x) else []


class FrameEngine(unittest.TestCase):
    def test_future_masks_and_reused_transport_buffers(self):
        engine=MaskingEngine(RedPixelDetector(),{'lookahead':2,'padding':0})
        buffer=np.zeros((20,80,3),np.uint8)
        output=None
        for index,x in enumerate([10,30,50]):
            buffer[:]=[30+20*index,40,50]
            buffer[5:10,x:x+5]=[0,0,255]
            result=engine.push(buffer)
            if index<2:
                self.assertIsNone(result)
            else:
                output=result
        self.assertEqual(output.index,0)
        self.assertEqual(output.pixels[0,0].tolist(),[30,40,50])
        for x in [10,30,50]:
            self.assertEqual(output.mask[7,x],255)
            self.assertEqual(output.pixels[7,x].tolist(),[0,0,0])
        self.assertEqual(int((output.mask>0).sum()),363)
        buffer[:]=0
        tail=list(engine.flush())
        self.assertEqual([frame.index for frame in tail],[1,2])
        self.assertEqual([frame.pixels[0,0].tolist() for frame in tail],[[50,40,50],[70,40,50]])
        self.assertEqual(tail[0].mask[7,10],0)
        with self.assertRaises(RuntimeError):
            engine.push(buffer)

    def test_resolution_change_fails_before_emitting_pending_frame(self):
        engine=MaskingEngine(RedPixelDetector(),{'lookahead':2})
        self.assertIsNone(engine.push(np.zeros((20,80,3),np.uint8)))
        with self.assertRaises(ValueError):
            engine.push(np.zeros((30,80,3),np.uint8))
        self.assertEqual(len(list(engine.flush())),1)

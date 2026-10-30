import threading
import unittest

import numpy as np

from shield.engine import MaskingEngine
from shield.motion import MotionHistory,MotionWorker
from shield.types import Frame,Detection


class Lane:
    stats={}
    def offer(self,frame):
        pass
    def drain(self):
        return [Detection('probe',0,[],10.1)]
    def close(self):
        pass


class MotionScheduling(unittest.TestCase):
    def test_batch_and_empty_receipts_reject_a_late_interior_motion_frame(self):
        completed = threading.Event()
        stamps = iter([100., 100.2, 100.])
        calls = [0]

        def clock():
            stamp = next(stamps)
            calls[0] += 1
            if calls[0] == 3:
                completed.set()
            return stamp

        worker = MotionWorker(MotionHistory(mode='phase'), clock=clock)
        source = np.random.default_rng(33).integers(0, 256, (32, 32, 3), dtype=np.uint8)
        quad = [[4, 4], [20, 4], [20, 16], [4, 16]]
        try:
            for index in range(3):
                worker.add(index, source)
            self.assertTrue(completed.wait(1))
            projected = worker.project_many([quad], 0, 0, deadline=100.1)
            self.assertEqual(projected, [quad])
            projected[0][0][0] = -9999
            self.assertEqual(worker.project_many([quad], 0, 0, deadline=100.1), [quad])
            self.assertEqual(worker.project_many([], 0, 0, deadline=100.1), [])
            self.assertIsNone(worker.project_many([quad], 0, 2, deadline=100.1))
            self.assertIsNone(worker.project_many([], 0, 2, deadline=100.1))
            self.assertIsNone(worker.project_many([], 2, 0, deadline=100.1))
            self.assertIsNone(worker.project(quad, 0, 2, deadline=100.1))
            self.assertIsNone(worker.project_many([], 0, 1000000, deadline=100.1))
            self.assertIsNone(worker.project_many([], 0, 0, deadline=float('nan')))
        finally:
            worker.close()
        self.assertFalse(worker.stats['running'])

    def test_motion_completed_after_deadline_cannot_retroactively_allow_live(self):
        import time
        entered,release=threading.Event(),threading.Event()
        clock=[100.]
        class HeldSecond(MotionHistory):
            def add(self,index,pixels):
                if index==1:
                    entered.set()
                    if not release.wait(1):
                        raise TimeoutError('Late motion probe was not released')
                super().add(index,pixels)
        class OnTimeLane(Lane):
            def drain(self):
                return [Detection('probe',0,[],100.01)]
        worker=MotionWorker(HeldSecond(mode='phase'),clock=lambda:clock[0])
        engine=MaskingEngine({'fast':OnTimeLane(),'accurate':OnTimeLane()},
                             {'fps':30,'delay_seconds':.1},motion=worker)
        source=np.random.default_rng(29).integers(0,256,(32,32,3),dtype=np.uint8)
        def wait_completed(count):
            for _ in range(200):
                if worker.stats['completed']>=count:
                    return
                time.sleep(.005)
            self.fail('Motion worker did not complete the controlled operation')
        try:
            engine.submit(Frame(0,0,source),now=100)
            wait_completed(1)
            engine.submit(Frame(1,1/30,source),now=100+1/30)
            self.assertTrue(entered.wait(1))
            clock[0]=100.2
            release.set()
            wait_completed(2)
            engine.end(1)
            frames=engine.poll(now=100.2)
            self.assertEqual(frames[0].state,'LIVE')
            self.assertEqual(frames[1].state,'PROTECT')
            self.assertFalse(frames[1].coverage.ok)
            self.assertFalse(np.array_equal(frames[1].pixels,source))
        finally:
            release.set()
            engine.close()

    def test_stalled_motion_does_not_block_ingest_deadline_or_hold(self):
        entered,release=threading.Event(),threading.Event()
        class HeldHistory(MotionHistory):
            def add(self,index,pixels):
                entered.set()
                if not release.wait(1):
                    raise TimeoutError('Motion probe was not released')
                super().add(index,pixels)
        worker=MotionWorker(HeldHistory(mode='phase'),capacity=4)
        engine=MaskingEngine({'fast':Lane(),'accurate':Lane()},{'fps':30,'delay_seconds':1},motion=worker)
        source=np.random.default_rng(71).integers(0,256,(32,32,3),dtype=np.uint8)
        try:
            engine.submit(Frame(0,0,source),now=10)
            self.assertTrue(entered.wait(1))
            result=engine.poll(now=11)
            self.assertEqual(len(result),1)
            self.assertEqual(result[0].state,'PROTECT')
            self.assertFalse(result[0].coverage.ok)
            self.assertFalse(np.array_equal(result[0].pixels,source))
            engine.hold(True,now=11)
        finally:
            release.set()
            engine.close()
        self.assertEqual(worker.stats['completed'],1)
        self.assertFalse(worker.stats['running'])


if __name__=='__main__':
    unittest.main()

import unittest
import numpy as np
from shield.engine import MaskingEngine
from shield.types import Frame,Detection
from shield.motion import MotionHistory


class SilentLane:
    stats={}
    def offer(self,frame):
        pass
    def drain(self):
        return []
    def close(self):
        pass


class ScriptedLane(SilentLane):
    def __init__(self,receipts):
        self.receipts=receipts
    def drain(self):
        result,self.receipts=self.receipts,[]
        return result


class DeadlineEngine(unittest.TestCase):
    def test_late_results_and_age_limits_cannot_claim_live_coverage(self):
        class Stationary:
            def add(self,index,pixels):
                pass
            def project_many(self,quads,source,target,deadline=None):
                return quads
        for result_index,completed,expected in [(12,10.9,'LIVE'),(13,10.9,'PROTECT'),(0,11.001,'PROTECT')]:
            with self.subTest(index=result_index,completed=completed):
                lanes={'fast':ScriptedLane([Detection('fast',0,[],10.1)]),
                       'accurate':ScriptedLane([Detection('accurate',result_index,[],completed)])}
                engine=MaskingEngine(lanes,{'delay_seconds':1,'fps':30},motion=Stationary())
                engine.submit(Frame(0,0,np.zeros((32,32,3),np.uint8)),now=10)
                engine.end(0)
                frame=engine.poll(now=11)[0]
                self.assertEqual(frame.state,expected)
                self.assertEqual(frame.coverage.ok,expected=='LIVE')
                engine.close()

    def test_overdue_output_is_bounded_and_hold_can_intervene_between_batches(self):
        engine=MaskingEngine({'fast':SilentLane(),'accurate':SilentLane()},
                             {'fps':30,'delay_seconds':1,'max_poll_frames':2})
        engine.submit(Frame(0,0,np.zeros((32,32,3),np.uint8)),now=10)
        engine.end(20)
        first=engine.poll(now=20)
        self.assertEqual(len(first),2)
        engine.hold(True,now=20)
        second=engine.poll(now=20)
        self.assertEqual([frame.index for frame in second],[2,3])
        self.assertTrue(all(frame.state=='HOLD' and frame.slate for frame in second))
        engine.close()

    def test_ingest_after_its_deadline_is_a_gap_even_before_poll(self):
        lanes={name:ScriptedLane([Detection(name,0,[],10.1)]) for name in ['fast','accurate']}
        source=np.random.default_rng(17).integers(0,256,(32,32,3),dtype=np.uint8)
        engine=MaskingEngine(lanes,{'delay_seconds':1,'fps':30},motion=MotionHistory(mode='phase'))
        engine.submit(Frame(0,0,source),now=10)
        engine.submit(Frame(1,1/30,source),now=12)
        engine.end(1)
        result=engine.poll(now=12)
        self.assertEqual(result[1].state,'PROTECT')
        self.assertEqual(result[1].coverage.reason,'ingest-gap')
        self.assertEqual(engine.stats['late_ingest'],1)
        engine.close()

    def test_poll_just_before_deadline_does_not_emit_or_raise(self):
        engine=MaskingEngine({'fast':SilentLane(),'accurate':SilentLane()},{'delay_seconds':1,'fps':30})
        engine.submit(Frame(0,0,np.zeros((32,32,3),np.uint8)),now=10)
        engine.end(0)
        self.assertEqual(engine.poll(now=11-5e-10),[])
        self.assertEqual(len(engine.poll(now=11)),1)
        engine.close()

    def test_overrun_bounds_frame_memory_and_protects_evicted_input(self):
        engine=MaskingEngine({'fast':SilentLane(),'accurate':SilentLane()},
                             {'delay_seconds':.1,'fps':30,'max_buffer_frames':3,'max_poll_frames':8})
        for index in range(8):
            engine.submit(Frame(index,index/30,np.full((32,32,3),index*20,np.uint8)),now=10+index/30)
        self.assertLessEqual(engine.stats['buffered_frames'],3)
        engine.end(7)
        result=engine.poll(now=11)
        self.assertEqual([frame.index for frame in result],list(range(8)))
        self.assertTrue(all(frame.state=='PROTECT' for frame in result[:5]))
        self.assertTrue(all(frame.coverage.reason=='ingest-gap' for frame in result[:5]))
        self.assertEqual(engine.stats['buffer_evictions'],5)
        engine.close()

    def test_empty_detection_from_a_disconnected_scene_is_not_coverage(self):
        class CutMotion:
            def add(self,index,pixels):
                pass
            def project_many(self,quads,source,target,deadline=None):
                return quads if source==target else None
        lanes={name:ScriptedLane([Detection(name,0,[],10.1)]) for name in ['fast','accurate']}
        engine=MaskingEngine(lanes,{'delay_seconds':1,'fps':30},motion=CutMotion())
        engine.submit(Frame(0,0,np.full((32,32,3),120,np.uint8)),now=10)
        engine.submit(Frame(1,1/30,np.full((32,32,3),220,np.uint8)),now=10+1/30)
        engine.end(1)
        result=engine.poll(now=11+1/30)
        self.assertEqual([frame.state for frame in result],['LIVE','PROTECT'])
        engine.close()

    def test_nonfinite_clock_values_are_rejected_before_the_frame_clock_starts(self):
        for options in [{'fps':float('inf')},{'fps':float('nan')},{'delay_seconds':float('inf')},{'delay_seconds':float('nan')}]:
            with self.subTest(options=options),self.assertRaises(ValueError):
                MaskingEngine({'fast':SilentLane(),'accurate':SilentLane()},options)
        engine=MaskingEngine({'fast':SilentLane(),'accurate':SilentLane()},{})
        with self.assertRaises(ValueError):
            engine.submit(Frame(0,float('nan'),np.zeros((32,32,3),np.uint8)),now=10)
        self.assertEqual(engine.poll(now=100),[])
        engine.close()

    def test_protection_duration_uses_missed_deadline_not_late_poll_time(self):
        engine=MaskingEngine({'fast':SilentLane(),'accurate':SilentLane()},{'fps':30,'delay_seconds':1})
        engine.submit(Frame(0,0,np.full((32,32,3),120,np.uint8)),now=10)
        engine.end(0)
        result=engine.poll(now=12.1)[0]
        self.assertTrue(result.slate)
        self.assertEqual(result.state,'PROTECT')
        self.assertTrue((result.pixels==0).all())
        engine.close()

    def test_foreign_scene_results_do_not_replace_fresh_current_scene_coverage(self):
        class DisconnectedMotion:
            def add(self,index,pixels):
                pass
            def project_many(self,quads,source,target,deadline=None):
                return quads if source==target else None
        a=[[5,5],[10,5],[10,10],[5,10]]
        b=[[20,20],[25,20],[25,25],[20,25]]
        lanes={name:ScriptedLane([Detection(name,0,[a],10.1),Detection(name,1,[b],10.2)]) for name in ['fast','accurate']}
        engine=MaskingEngine(lanes,{'fps':30,'delay_seconds':1},motion=DisconnectedMotion())
        engine.submit(Frame(0,0,np.full((32,32,3),120,np.uint8)),now=10)
        engine.submit(Frame(1,1/30,np.full((32,32,3),180,np.uint8)),now=10+1/30)
        engine.end(1)
        result=engine.poll(now=11)[0]
        self.assertEqual(result.state,'LIVE')
        self.assertEqual(result.mask[7,7],255)
        self.assertEqual(result.mask[22,22],0)
        engine.close()

    def test_fresh_both_lane_results_allow_live_and_union_all_masks(self):
        a=[[5,5],[10,5],[10,10],[5,10]]
        b=[[20,20],[25,20],[25,25],[20,25]]
        lanes={'fast':ScriptedLane([Detection('fast',0,[a],10.1)]),
               'accurate':ScriptedLane([Detection('accurate',0,[b],10.2)])}
        source=np.full((32,32,3),120,np.uint8)
        engine=MaskingEngine(lanes,{'delay_seconds':1,'fps':30},motion=MotionHistory(mode='phase'))
        engine.submit(Frame(0,0,source),now=10)
        source[:]=250
        engine.end(0)
        result=engine.poll(now=11)[0]
        self.assertEqual(result.state,'LIVE')
        self.assertTrue(result.coverage.ok)
        self.assertEqual((result.coverage.fast_age,result.coverage.accurate_age),(0,0))
        self.assertFalse(result.protected)
        self.assertEqual(result.mask[7,7],255)
        self.assertEqual(result.mask[22,22],255)
        self.assertEqual(result.pixels[0,31].tolist(),[120,120,120])
        engine.close()

    def test_deadline_without_coverage_emits_protection_never_raw(self):
        source=np.repeat(((np.indices((32,32)).sum(axis=0)%2)*255).astype(np.uint8)[:,:,None],3,axis=2)
        engine=MaskingEngine({'fast':SilentLane(),'accurate':SilentLane()},{'delay_seconds':1,'fps':30})
        engine.submit(Frame(0,0,source),now=10)
        engine.end(0)
        self.assertEqual(engine.poll(now=10.999),[])
        result=engine.poll(now=11)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0].index,0)
        self.assertEqual(result[0].deadline,11)
        self.assertEqual(result[0].state,'PROTECT')
        self.assertFalse(result[0].coverage.ok)
        self.assertTrue(result[0].protected)
        self.assertTrue((result[0].mask==255).all())
        self.assertFalse(np.array_equal(result[0].pixels,source))
        self.assertTrue(engine.drained)
        engine.close()

    def test_flow_generation_change_fails_closed_and_fresh_receipts_recover(self):
        import threading
        from shield.motion import MotionWorker
        from test_motion import scene
        complete = threading.Event()
        count = [0]
        def clock():
            count[0] += 1
            if count[0] == 3:
                complete.set()
            return 10.1
        quad = [[100, 70], [300, 70], [300, 190], [100, 190]]
        lanes = {name: ScriptedLane([Detection(name, 0, [quad], 10.1),
                                    Detection(name, 2, [quad], 10.1)])
                 for name in ('fast', 'accurate')}
        motion = MotionWorker(MotionHistory(mode='flow', max_projection_frames=30), clock=clock)
        engine = MaskingEngine(lanes, {'fps':30, 'delay_seconds':1, 'motion_mode':'flow'}, motion=motion)
        try:
            source = scene()
            engine.submit(Frame(0, 0, source), now=10, generation=0)
            engine.submit(Frame(1, 1/30, source), now=10+1/30, generation=1)
            engine.submit(Frame(2, 2/30, source), now=10+2/30, generation=2)
            self.assertTrue(complete.wait(2))
            engine.end(2)
            frames = engine.poll(now=11+2/30)
            self.assertEqual([f.state for f in frames], ['LIVE', 'PROTECT', 'LIVE'])
            self.assertFalse(frames[1].coverage.ok)
            self.assertTrue(frames[1].protected)
            self.assertEqual(frames[1].coverage.reason, 'unresolved-motion-accurate-coverage')
            self.assertEqual(frames[2].mask[120, 200], 255)
            self.assertEqual((frames[2].coverage.fast_age, frames[2].coverage.accurate_age), (0, 0))
        finally:
            engine.close()
        self.assertFalse(motion.stats['running'])

    def test_flow_receipts_cannot_exceed_delay_with_a_more_permissive_motion_adapter(self):
        from test_motion import scene
        quad = [[100, 70], [300, 70], [300, 190], [100, 190]]
        lanes = {name: ScriptedLane([Detection(name, 0, [quad], 10.),
                                    Detection(name, 3, [quad], 11.5)])
                 for name in ('fast', 'accurate')}
        engine = MaskingEngine(lanes, {'fps':2, 'delay_seconds':1, 'motion_mode':'flow'},
                               motion=MotionHistory(mode='flow', max_projection_frames=30))
        try:
            for index in range(4):
                engine.submit(Frame(index, index/2, scene()), now=10+index/2)
            engine.end(3)
            frames = engine.poll(now=12.5)
            self.assertEqual([f.state for f in frames], ['LIVE', 'LIVE', 'LIVE', 'LIVE'])
            self.assertEqual(len(frames[1].quads), 4)
            self.assertEqual(len(frames[0].quads), 2)
            self.assertEqual(len(frames[3].quads), 2)
        finally:
            engine.close()

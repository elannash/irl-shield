"""Per-detection motion contracts on independently moving synthetic signs."""
import unittest
import cv2
import numpy as np
from shield.motion import MotionHistory


def scene(offsets=(0, 0)):
    image = np.full((180, 320, 3), 30, np.uint8)
    for seed, x, y, delta in ((41, 35, 35, offsets[0]), (71, 190, 100, offsets[1])):
        tile = np.random.default_rng(seed).integers(40, 245, (40, 70, 3), dtype=np.uint8)
        image[y:y+40, x+delta:x+delta+70] = tile
    return image


QUADS = [[[35, 35], [104, 35], [104, 74], [35, 74]],
         [[190, 100], [259, 100], [259, 139], [190, 139]]]


class BoxFlow(unittest.TestCase):
    def test_each_quad_follows_its_own_motion_forward_and_backward(self):
        history = MotionHistory(mode='box-flow', max_projection_frames=30, analysis_width=320)
        history.add(0, scene())
        history.add(1, scene((7, -5)))
        moved = history.project_many(QUADS, 0, 1)
        self.assertIsNotNone(moved)
        np.testing.assert_allclose(moved[0], np.asarray(QUADS[0]) + [7, 0], atol=1.)
        np.testing.assert_allclose(moved[1], np.asarray(QUADS[1]) + [-5, 0], atol=1.)
        returned = history.project_many(moved, 1, 0)
        np.testing.assert_allclose(returned, QUADS, atol=1.)

    def test_bad_local_path_missing_frame_and_generation_never_bridge(self):
        for reason in ('unrelated', 'gap', 'generation', 'horizon'):
            with self.subTest(reason=reason):
                history = MotionHistory(mode='box-flow', max_projection_frames=0 if reason=='horizon' else 30, analysis_width=320)
                history.add(0, scene(), generation=1)
                pixels = np.random.default_rng(9).integers(0,256,(180,320,3),dtype=np.uint8) if reason=='unrelated' else scene((7,-5))
                target = 2 if reason=='gap' else 1
                history.add(target, pixels, generation=2 if reason=='generation' else 1)
                self.assertIsNone(history.project_many(QUADS, 0, target))
                if reason != 'unrelated':
                    self.assertIsNone(history.project_many([], 0, target))


class Receipts:
    stats = {}
    def __init__(self, name):
        self.name = name
        self.rows = []
    def offer(self, frame):
        from shield.types import Detection
        self.rows.append(Detection(self.name, frame.index, [QUADS[0]] if frame.index in (0, 4) else [], frame.pts))
    def drain(self):
        rows, self.rows = self.rows, []
        return rows
    def close(self):
        pass


class Persistence(unittest.TestCase):
    def test_mask_persists_through_empty_receipts_and_fills_before_next_detection(self):
        from bench.offline_quality import render_offline
        frames = [scene((i * 2, 0)) for i in range(7)]
        # Match the second observation to its source geometry.
        class MovingReceipts(Receipts):
            def detect_quads(self, pixels):
                index = int(pixels[0, 0, 0])
                return [(np.asarray(QUADS[0])+[index*2,0]).tolist()] if index in (0,4) else []
        for i,pixels in enumerate(frames): pixels[0,0,0] = i
        outputs=[]
        result=render_offline(frames,10.,{n:MovingReceipts(n) for n in ("fast","accurate")},
            {"delay_seconds":.3,"before":0,"after":3,"motion_mode":"box-flow","motion_width":320,
             "tracking_persist_frames":3,"fast_rate_hz":10.,"accurate_rate_hz":10.,"padding":0},outputs.append)
        self.assertTrue(all(not row["protected"] for row in result["records"]))
        self.assertEqual(outputs[6].mask[55,70],255)
        self.assertEqual(outputs[2].mask[55,70],255)

    def test_transport_generation_stops_old_masks_even_if_a_motion_adapter_accepts_them(self):
        from shield.engine import MaskingEngine
        from shield.types import Frame
        class UnsafeMotion:
            def add(self,index,pixels,**kwargs): pass
            def project_many(self,quads,source,target,deadline=None): return quads
        lanes={n:Receipts(n) for n in ("fast","accurate")}
        engine=MaskingEngine(lanes,{"fps":10.,"delay_seconds":.3,"before":0,"after":0,
            "motion_mode":"box-flow","tracking_persist_frames":3},motion=UnsafeMotion())
        try:
            engine.submit(Frame(0,0.,scene()),now=0.,generation=1)
            first=engine.poll(now=.3)[0]
            self.assertEqual(first.mask[55,70],255)
            engine.submit(Frame(1,.1,scene()),now=.1,generation=2)
            second=engine.poll(now=.4)[0]
            self.assertEqual(second.mask[55,70],0)
            self.assertEqual(second.state,"LIVE")
        finally: engine.close()


class GeometryContract(unittest.TestCase):
    def test_geometry_is_exact_and_height_does_not_follow_long_sign_width(self):
        from shield.masking import text_geometry
        quads=[[[1,2],[101,2],[101,12],[1,12]]]
        result=text_geometry(quads)
        self.assertEqual(result["quads"],quads)
        self.assertEqual(result["estimated_text_heights"],[10.])
        result["quads"][0][0][0]=-1
        self.assertEqual(quads[0][0][0],1)


class CapturedGeneration(unittest.TestCase):
    def test_phase_mode_captured_generation_also_fences_old_receipts(self):
        from shield.engine import MaskingEngine
        from shield.types import Frame,Detection
        class Motion:
            def add(self,index,pixels): pass
            def project_many(self,quads,source,target,deadline=None): return quads
        lanes={n:Receipts(n) for n in ("fast","accurate")}
        engine=MaskingEngine(lanes,{"fps":10.,"delay_seconds":.1,"before":6,"after":0},motion=Motion())
        try:
            engine.submit(Frame(0,0.,scene(),1),now=0.)
            engine.poll(now=.1)
            engine.submit(Frame(1,.1,scene(),2),now=.1)
            result=engine.poll(now=.2)[0]
            self.assertEqual(result.state,"LIVE")
            self.assertEqual(result.mask[55,70],0)
        finally: engine.close()

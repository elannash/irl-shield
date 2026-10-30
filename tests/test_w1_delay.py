"""D>1 is explicit bench diagnostics; production validators retain D<=1."""
import unittest
import numpy as np
from tests.test_q2_execution import Stationary, Boxes
from bench.offline_quality import render_offline
from bench.clocked_pipeline import VideoSource


class DiagnosticDelay(unittest.TestCase):
    def test_d2_d3_require_explicit_opt_in_and_never_claim_adoption(self):
        pixels=np.full((48,96,3),128,np.uint8)
        for delay in (2.,3.):
            options={"delay_seconds":delay,"fast_rate_hz":2.,"accurate_rate_hz":2.}
            with self.subTest(delay=delay):
                with self.assertRaisesRegex(ValueError,"one second"):
                    render_offline([pixels]*8,2.,{n:Boxes() for n in ("fast","accurate")},options,lambda frame:None,motion=Stationary())
                result=render_offline([pixels]*8,2.,{n:Boxes() for n in ("fast","accurate")},options,
                    lambda frame:None,motion=Stationary(),diagnostic_delay=True)
                self.assertEqual(result["frames"],8)
                self.assertEqual(result["records"][0]["deadline"],delay)
                self.assertFalse(result["delay_adoption_eligible"])
                media={"frames":3,"fps":30.,"resolution":[1280,720]}
                with self.assertRaisesRegex(ValueError,"one second"):
                    VideoSource("synthetic.mp4",media,delay_seconds=delay)
                source=VideoSource("synthetic.mp4",media,delay_seconds=delay,diagnostic_delay=True)
                self.assertEqual(source.buffer_capacity_frames,int(30*(delay+1)))
                self.assertIsNone(source.thread)
        with self.assertRaisesRegex(ValueError,"three seconds"):
            render_offline([pixels],2.,{n:Boxes() for n in ("fast","accurate")},
                {"delay_seconds":3.1},lambda frame:None,motion=Stationary(),diagnostic_delay=True)

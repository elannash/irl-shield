"""Observed truth and actual mask states; missing frames never count clean."""
import unittest


class Flicker(unittest.TestCase):
    def test_interior_unmasked_frames_count_but_unsampled_and_partial_masks_stay_unknown(self):
        from bench.w1.flicker import interval_flicker
        box=[2,2,9,9]
        track={"first":0,"last":5,"observations":[(i,box) for i in (0,1,2,3,4,5)],"leak_frames":[2]}
        coverage=[[{"box":box,"fraction":v}] for v in (1.,0.,1.,.5,0.,1.)]
        result=interval_flicker([track],coverage,sampled_frames={0,1,2,3,5},protected_frames=set())
        self.assertEqual(result["flicker_leak_frames"],[1,2])
        self.assertEqual(result["flicker_leak_count"],2)
        self.assertEqual(result["unknown_observations"],2)
        self.assertEqual(result["intervals"][0]["states"],["masked","unmasked","unmasked","unknown","unknown","masked"])
        self.assertEqual(result["evaluated_interval_frame_pairs"],6)

    def test_interpolated_input_truth_and_protection_cannot_create_clean_anchors(self):
        from bench.w1.flicker import interval_flicker
        box=[0,0,4,4]
        tracks=[{"first":0,"last":3,"observations":[(0,box),(3,box)],"leak_frames":[]}]
        coverage=[[{"box":box,"fraction":v}] for v in (1.,0.,0.,1.)]
        result=interval_flicker(tracks,coverage,sampled_frames={0,1,2,3},protected_frames={3})
        self.assertEqual(result["flicker_leak_frames"],[])
        self.assertEqual(result["unknown_observations"],3)
        self.assertEqual(result["known_masked_observations"],1)

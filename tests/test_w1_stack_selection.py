"""Real-only selection and finite measured search; all data here are synthetic records."""
import unittest


def clips():
    rows=[]
    for i in range(7):
        natural={"hidden":2,"total":4} if i==0 else {"hidden":1,"total":1}
        rows.append({"clip":str(i),"synthetic_variant":False,"natural":natural,
                     "synthetic":{"hidden":0,"total":0},"flicker":{"natural":{"flicker_leak_count":i}}})
        rows.append({"clip":str(i),"synthetic_variant":True,"natural":{"hidden":100,"total":100},
                     "synthetic":{"hidden":2,"total":2},"flicker":{"natural":{"flicker_leak_count":999}}})
    return rows


class NaturalSelection(unittest.TestCase):
    def test_overlay_background_never_enters_selection_numerator_or_flicker(self):
        from bench.w1.stack_selection import natural_summary
        result=natural_summary(clips())
        self.assertEqual(result["natural"],{"hidden":8,"total":10,"hidden_fraction":.8,"hidden_percent":80.})
        self.assertEqual(result["natural_flicker_frames"],21)
        self.assertEqual(result["synthetic_regression"],{"hidden":14,"total":14,"selection_numerator":False})

    def test_duplicate_natural_clip_and_nonboolean_variant_are_refused(self):
        from bench.w1.stack_selection import natural_summary
        rows=clips();rows[2]["clip"]=rows[0]["clip"]
        with self.assertRaisesRegex(ValueError,"seven unique"): natural_summary(rows)
        rows=clips();rows[0]["synthetic_variant"]=0
        with self.assertRaisesRegex(ValueError,"boolean"): natural_summary(rows)


class StagedGuards(unittest.TestCase):
    def row(self):
        return {"source_freeze_sha256":"source","selection_identity_sha256":"natural-only",
          "natural_hidden_percent":91.,"gpu_ms_per_source_frame":5.,"cpu_percent_one_core_100":50.,
          "gpu_utilization_p95_percent":60.,"max_sustainable_fps":35.,"e2e_latency_p95_seconds_including_D":1.2,
          "sustained_30fps_pass":True,"real_video_guard_pass":True,"synthetic_regression_pass":True,
          "per_clip_protection_pass":True,"area_guard_pass":True,"queue_clean":True}

    def test_missing_cost_or_cpu_threshold_cannot_qualify_best(self):
        from bench.w1.stack_selection import assess
        base=self.row();arm=base|{"natural_hidden_percent":92.}
        result=assess(arm,base)
        self.assertFalse(result["eligible_for_owner_shortlist"])
        self.assertIn("CPU-walk-budget-threshold-not-provided",result["pending"])
        result=assess(arm|{"gpu_ms_per_source_frame":None},base,cpu_budget_one_core_percent=70.)
        self.assertFalse(result["eligible_for_owner_shortlist"])
        self.assertIn("missing-gpu_ms_per_source_frame",result["pending"])

    def test_half_point_boundary_and_measured_speed_guard_stop_factor(self):
        from bench.w1.stack_selection import assess
        base=self.row()
        low=assess(base|{"natural_hidden_percent":91.49,"gpu_ms_per_source_frame":6.},base,cpu_budget_one_core_percent=70.)
        self.assertTrue(low["stop_adding_factor"])
        enough=assess(base|{"natural_hidden_percent":91.5,"gpu_ms_per_source_frame":6.},base,cpu_budget_one_core_percent=70.)
        self.assertFalse(enough["stop_adding_factor"])
        self.assertEqual(enough["gain_percentage_points_per_added_gpu_ms"],.5)
        slow=assess(base|{"natural_hidden_percent":92.,"gpu_utilization_p95_percent":70.1},base,cpu_budget_one_core_percent=70.)
        self.assertTrue(slow["stop_adding_factor"])
        self.assertFalse(slow["eligible_for_owner_shortlist"])

    def test_area_pools_natural_source_frames_instead_of_averaging_clip_medians(self):
        from bench.w1.stack_selection import natural_area
        records={"0":[{"mask_fraction":.2}]*10}
        records.update({str(i):[{"mask_fraction":0.}] for i in range(1,7)})
        self.assertEqual(natural_area(records),{"p50":.2,"p95":.2})

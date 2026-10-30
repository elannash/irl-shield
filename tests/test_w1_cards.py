"""No incomplete or invalid baseline can become a W1 winner."""
import unittest


class PolicyAndComparison(unittest.TestCase):
    def test_explicit_area_basis_and_ceiling_are_required_without_family_override(self):
        from bench.w1.cards import validate_policy
        base={"candidate":"ppocr-v6-small","options":{"area_ceiling":.15,"area_ceiling_basis":"bench/gate-1-policy.json"}}
        self.assertEqual(validate_policy(base)["detector_families"],["paddleocr"])
        for changed in ({"area_ceiling":.16},{"area_ceiling_basis":""},{"detector_families":[]}):
            with self.subTest(changed=changed),self.assertRaises(ValueError):
                validate_policy({**base,"options":base["options"]|changed})

    def test_invalid_baseline_and_added_latency_cap_block_stacking(self):
        from bench.w1.cards import compare
        good={"complete":True,"guards_pass":True,"natural_fraction":.95,"actual_total_added_latency_seconds":.9,"flicker_leaks":2,"gpu_ms_per_source_frame":5.,"source_freeze_sha256":"a","input_identity":"tune"}
        baseline=good|{"guards_pass":False,"natural_fraction":.8}
        result=compare(baseline,good)
        self.assertFalse(result["stack_eligible"])
        self.assertIsNone(result["winner"])
        self.assertEqual(result["rejection_reasons"],["baseline-invalid"])
        too_slow=good|{"actual_total_added_latency_seconds":3.01}
        result=compare(good,too_slow)
        self.assertFalse(result["stack_eligible"])
        self.assertIn("total-latency-over3s",result["rejection_reasons"])
        with self.assertRaisesRegex(ValueError,"identities"):
            compare(good,good|{"input_identity":"lighting-stress"})


class SealedStage(unittest.TestCase):
    def test_stage_artifacts_and_queue_binding_are_checked_without_polling(self):
        import hashlib,json,tempfile
        from pathlib import Path
        from bench.w1.report import execution
        def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            raw=root/"clocked.performance.json";raw.write_text("{}")
            plan=root/"execution.json";plan.write_text(json.dumps({"artifacts":{raw.name:{"sha256":digest(raw),"bytes":2}}}))
            (root/"execution.sha256").write_text(digest(plan))
            attempt=root/"attempt.json";attempt.write_text(json.dumps({"phase":"closed","returncode":0,"contended":True,
                "receipts":[{"path":str(plan),"sha256":digest(plan),"bytes":plan.stat().st_size}]}))
            _,clean=execution(root,attempt)
            self.assertFalse(clean)
            raw.write_text("{\"tampered\":true}")
            with self.assertRaisesRegex(ValueError,"artifact changed"):
                execution(root,attempt)

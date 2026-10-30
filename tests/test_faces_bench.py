import unittest
from dataclasses import replace
from pathlib import Path
import tempfile
import numpy as np
from bench.faces.scoring import score_frame
from bench.faces.synthetic import Truth, overlay
from shield.faces import Face, FaceBatch, FacePolicy, FaceTracker, opaque
from shield.faces.detector import model_path


class ScriptedJudge:
    """Independent inference boundary; assertions exercise scorer, not model quality."""
    def __init__(self, outputs):
        self.outputs = iter(outputs)

    def detect(self, frame):
        return next(self.outputs)


class FaceBenchTests(unittest.TestCase):
    def scene(self):
        before = np.full((100, 100, 3), 200, np.uint8)
        truth = (Truth('a', (30, 30, 60, 60), 1.),)
        batch = FaceTracker().assign(FaceBatch(0, 0, (100, 100), 1., (Face(truth[0].box, 0.9),)))
        plan = FacePolicy('all').plan((100, 100), 0, 0, batch, now=1.1)
        return before, truth, plan

    def test_no_detection_judge_fails_positive_controls_even_with_full_mask(self):
        before, truth, plan = self.scene()
        score = score_frame(before, opaque(before, plan.mask), truth, plan,
                            ScriptedJudge([(), (), ()]), mode='all')
        self.assertFalse(score['controls_ok'])
        self.assertFalse(score['privacy_pass'])
        self.assertEqual(score['placement_coverage_fraction'], [1.])

    def test_controls_plus_truth_catch_residual_and_mask_miss(self):
        before, truth, plan = self.scene()
        control = (Face((10, 10, 45, 45), 0.9),)
        good = score_frame(before, opaque(before, plan.mask), truth, plan,
                           ScriptedJudge([control, (), ()]), mode='all')
        self.assertTrue(good['privacy_pass'])
        for residual, changed in [(control, plan), ((), replace(plan, mask=np.zeros((100, 100), np.uint8)))]:
            bad = score_frame(before, before, truth, changed,
                              ScriptedJudge([control, residual, ()]), mode='all')
            self.assertFalse(bad['privacy_pass'])
            self.assertEqual(bad['unmasked_required_faces'], 1)

    def test_off_is_measured_but_never_receives_privacy_pass(self):
        before, truth, _ = self.scene()
        plan = FacePolicy('off').plan((100, 100), 0, 0, None, now=1.)
        face = (Face((10, 10, 45, 45), 0.9),)
        score = score_frame(before, before, truth, plan, ScriptedJudge([face, face, face]), mode='off', natural_background=True)
        self.assertTrue(score['mode_behavior_ok'])
        self.assertFalse(score['privacy_pass'])
        self.assertIsNone(score['detector_false_positives'])
        self.assertEqual(score['output_face_count'], 1)

    def test_synthetic_alpha_placement_is_repeatable_and_matches_truth(self):
        source = np.zeros((100, 200, 3), np.uint8)
        cutout = np.full((100, 100, 4), 255, np.uint8)
        assets = [(cutout, (20, 20, 80, 80)), (cutout, (20, 20, 80, 80))]
        a, truth = overlay(source, 10, assets, 'bystanders-only')
        b, second = overlay(source, 10, assets, 'bystanders-only')
        self.assertTrue(np.array_equal(a, b))
        self.assertEqual(truth, second)
        self.assertEqual(len(truth), 2)
        for t in truth:
            x0, y0, x1, y1 = map(int, t.box)
            self.assertTrue(np.all(a[y0:y1, x0:x1] == 255))
        blank, none = overlay(source, 10, assets, 'no-people')
        self.assertTrue(np.array_equal(blank, source))
        self.assertEqual(none, ())

    def test_corrupted_weights_are_rejected_before_inference(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'models/cache/faces').mkdir(parents=True)
            (root / 'models/cache/faces/face.onnx').write_bytes(b'wrong weights')
            (root / 'models/faces-manifest.json').write_text(json.dumps({'models':[{'id':'test','filename':'face.onnx','sha256':'0'*64}]}))
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                model_path('test', root)


if __name__ == '__main__':
    unittest.main()

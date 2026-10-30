import unittest
from dataclasses import replace
import numpy as np
from shield.faces import Face, FaceBatch, FacePolicy, FaceTracker, opaque


class FacePolicyTests(unittest.TestCase):
    def batch(self, faces=(), index=8, generation=2, shape=(100, 100)):
        return FaceTracker().assign(FaceBatch(index, generation, shape, 10., tuple(Face(box, 0.95) for box in faces)))

    def plan(self, batch, policy=None, **kw):
        return (policy or FacePolicy()).plan((100, 100), 8, 2, batch, now=kw.get('now', 10.1))

    def test_missing_stalled_failed_wrong_source_and_generation_fail_closed(self):
        fresh = self.batch([(10, 10, 30, 30)])
        cases = [(None, 'missing'), (replace(fresh, completed_at=9.), 'stalled'),
                 (replace(fresh, completed_at=11.), 'stalled'),
                 (replace(fresh, error='timeout'), 'detector-error'),
                 (replace(fresh, source_index=7), 'source-mismatch'),
                 (replace(fresh, source_index=9), 'source-mismatch'),
                 (replace(fresh, generation=1), 'generation-mismatch'),
                 (replace(fresh, shape=(50, 50)), 'shape-mismatch'),
                 (replace(fresh, faces=(Face((10, 10, 30, 30), 0.9),)), 'untracked'),
                 (replace(fresh, faces=(Face((-1, 0, 10, 10), 0.9, 'a'),)), 'invalid-geometry')]
        for batch, reason in cases:
            with self.subTest(reason=reason):
                plan = self.plan(batch)
                self.assertFalse(plan.coverage.ok)
                self.assertEqual(plan.coverage.reason, reason)
                self.assertTrue(plan.requires_hold)
                self.assertTrue(np.all(plan.mask == 255))
                self.assertIsNone(plan.exempt_track_id)

    def test_bystanders_exempts_only_largest_strictly_above_threshold(self):
        faces = [(0, 0, 40, 40), (60, 60, 90, 90)]
        batch = self.batch(faces)
        plan = self.plan(batch)
        self.assertEqual(plan.exempt_track_id, batch.faces[0].track_id)
        self.assertEqual(plan.masked_track_ids, (batch.faces[1].track_id,))
        self.assertEqual(plan.mask[10, 10], 0)
        self.assertEqual(plan.mask[70, 70], 255)
        boundary = self.plan(self.batch([(0, 0, 20, 40)]))
        self.assertIsNone(boundary.exempt_track_id)  # 800 / 10000 equals, does not exceed 8%.
        self.assertTrue(boundary.mask[10, 10])

    def test_equal_large_faces_never_all_exempt(self):
        plan = self.plan(self.batch([(0, 0, 40, 40), (60, 60, 100, 100)]))
        self.assertEqual(len(plan.masked_track_ids), 1)
        self.assertEqual(plan.exempt_track_id, 'face:2:1')

    def test_all_off_and_empty_completion_have_distinct_contracts(self):
        batch = self.batch([(20, 20, 80, 80)])
        all_plan = self.plan(batch, FacePolicy('all'))
        self.assertIsNone(all_plan.exempt_track_id)
        self.assertTrue(all_plan.mask[50, 50])
        off = self.plan(None, FacePolicy('off'))
        self.assertFalse(off.requires_hold)
        self.assertFalse(np.any(off.mask))
        empty = self.plan(self.batch())
        self.assertTrue(empty.coverage.ok)
        self.assertFalse(np.any(empty.mask))

    def test_mask_area_is_union_and_opaque_pixels_ignore_source(self):
        plan = self.plan(self.batch([(0, 0, 20, 20), (10, 10, 30, 30)]), FacePolicy('all', padding=0))
        self.assertEqual(plan.area_pixels, 700)
        self.assertEqual(plan.area_fraction, 0.07)
        a = np.zeros((100, 100, 3), np.uint8)
        b = np.full_like(a, 255)
        aa, bb = opaque(a, plan.mask), opaque(b, plan.mask)
        self.assertTrue(np.array_equal(aa[plan.mask != 0], bb[plan.mask != 0]))
        self.assertTrue(np.array_equal(aa[plan.mask == 0], a[plan.mask == 0]))
        self.assertTrue(np.array_equal(bb[plan.mask == 0], b[plan.mask == 0]))
        self.assertTrue(np.all(opaque(b, self.plan(None).mask) == 24))

    def test_tracks_one_to_one_across_reordering_but_reset_on_generation(self):
        tracker = FaceTracker()
        def batch(index, gen, boxes):
            return tracker.assign(FaceBatch(index, gen, (100, 100), 10., tuple(Face(b, 0.9) for b in boxes)))
        one = batch(1, 0, [(0, 0, 20, 20), (70, 70, 90, 90)])
        two = batch(2, 0, [(71, 71, 91, 91), (1, 1, 21, 21)])
        self.assertEqual(two.faces[0].track_id, one.faces[1].track_id)
        self.assertEqual(two.faces[1].track_id, one.faces[0].track_id)
        three = batch(3, 0, [(1, 1, 21, 21), (2, 2, 22, 22)])
        self.assertEqual(len({f.track_id for f in three.faces}), 2)
        reset = batch(0, 1, [(1, 1, 21, 21)])
        self.assertNotIn(reset.faces[0].track_id, {f.track_id for f in three.faces})
        with self.assertRaisesRegex(ValueError, 'did not advance'):
            batch(0, 1, [])
        with self.assertRaisesRegex(ValueError, 'backwards'):
            batch(10, 0, [])

    def test_invalid_settings_and_nonbinary_paint_mask_rejected(self):
        for options in ({'mode':'self'}, {'selfie_min_fraction':0}, {'padding':-1}, {'max_result_age_seconds':float('nan')}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                FacePolicy(**options)
        with self.assertRaises(ValueError):
            opaque(np.zeros((2, 2, 3), np.uint8), np.ones((2, 2), np.uint8))


if __name__ == '__main__':
    unittest.main()

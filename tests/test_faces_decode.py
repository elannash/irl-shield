import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from shield.faces.yunet_ort import decode, prepare, profile_placement, source_faces


def predictions():
    return {f'{kind}_{s}': np.zeros((1, (640 // s)**2, dims), np.float32)
            for kind, dims in [('cls', 1), ('obj', 1), ('bbox', 4), ('kps', 10)] for s in (8, 16, 32)}


class DecodeTests(unittest.TestCase):
    def test_official_stride_score_landmarks_and_negative_control(self):
        outputs = predictions()
        self.assertEqual(decode(outputs).shape, (0, 15))
        index = 3 * 80 + 4
        outputs['cls_8'][0, index, 0] = 0.81
        outputs['obj_8'][0, index, 0] = 1.
        outputs['bbox_8'][0, index] = [0.5, 0.5, np.log(2), np.log(4)]
        outputs['kps_8'][0, index] = np.tile([0.25, 0.75], 5)
        rows = decode(outputs)
        np.testing.assert_allclose(rows[0, :4], [28, 12, 16, 32], atol=1e-5)
        np.testing.assert_allclose(rows[0, 4:14], np.tile([34, 30], 5), atol=1e-5)
        self.assertAlmostEqual(rows[0, 14], 0.9, places=6)
        faces = source_faces(rows, (1280, 1280), (2., 2.))
        np.testing.assert_allclose(faces[0].box, [56, 24, 88, 88], atol=1e-4)
        outputs['bbox_8'][0, index, 2] = float('nan')
        with self.assertRaisesRegex(ValueError, 'non-finite'):
            decode(outputs)

    def test_nms_uses_integer_boxes_and_preserves_high_score(self):
        outputs = predictions()
        for index, score in [(0, 0.9), (1, 0.8)]:
            outputs['cls_8'][0, index, 0] = score**2
            outputs['obj_8'][0, index, 0] = 1
            outputs['bbox_8'][0, index] = [2 - index, 2, np.log(4), np.log(4)]
        rows = decode(outputs)
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0, 14], 0.9, places=6)

    def test_preprocess_has_no_channel_swap_normalization_or_center_pad(self):
        image = np.empty((4, 8, 3), np.uint8);image[:] = [10, 20, 30]
        padded, scales = prepare(image)
        np.testing.assert_array_equal(padded[:4, :8], image)
        self.assertEqual(scales, (1., 1.))
        self.assertFalse(np.any(padded[4:]))
        self.assertFalse(np.any(padded[:, 8:]))
        rows = np.zeros((1, 15), np.float32);rows[0, :4] = [100, 100, 10, 10];rows[0, -1] = 0.9
        self.assertEqual(source_faces(rows, (4, 8), scales), ())

    def test_provider_presence_without_executed_cuda_nodes_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'profile.json'
            def report(providers):
                path.write_text(json.dumps([{'cat':'Node','name':f'n{i}_kernel_time','args':{'provider':p},'dur':1} for i,p in enumerate(providers)]))
                return profile_placement(path, expect_cuda=True)
            self.assertFalse(report([])['placement_verified'])
            self.assertFalse(report(['CPUExecutionProvider'])['placement_verified'])
            mixed = report(['CUDAExecutionProvider', 'CPUExecutionProvider'])
            self.assertFalse(mixed['placement_verified'])
            self.assertEqual(len(mixed['cpu_fallback_events']), 1)
            self.assertTrue(report(['CUDAExecutionProvider'])['placement_verified'])
            self.assertFalse(report([None])['placement_verified'])


if __name__ == '__main__':
    unittest.main()

"""Small synthetic ONNX graph exercises real OnnxTR and CPU EP, never weights."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import onnx
from onnx import helper, TensorProto

from bench.fast import FastDetector
from bench.fast_static import prepare_static
from models.prepare import load_manifest, sha256_file


class SyntheticOnnxTests(unittest.TestCase):
    def test_real_predictor_preserves_red_label_geometry_and_static_weights(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / 'synthetic.onnx'
            graph = helper.make_graph(
                [helper.make_node('Gather', ['pixels', 'red'], ['logits'], axis=1)],
                'synthetic-red-label',
                [helper.make_tensor_value_info('pixels', TensorProto.FLOAT, ['batch', 3, 'h', 'w'])],
                [helper.make_tensor_value_info('logits', TensorProto.FLOAT, ['batch', 1, 'h', 'w'])],
                [helper.make_tensor('red', TensorProto.INT64, [1], [0])])
            model = helper.make_model(graph, opset_imports=[helper.make_opsetid('', 13)], ir_version=9)
            onnx.save(model, source)
            artifact = {**load_manifest()['artifacts']['fast-tiny'], 'sha256': sha256_file(source)}
            with patch('bench.fast.verified_path', return_value=(source, artifact)):
                detector = FastDetector(cache_dir=directory, provider='cpu', side=64)
            try:
                image = np.zeros((64, 64, 3), np.uint8)
                image[16:40, 16:40] = [0, 0, 255]
                quads = detector.detect_quads(image)
                self.assertEqual(len(quads), 1)
                polygon = np.asarray(quads[0])
                self.assertTrue((polygon.min(axis=0) < [28, 28]).all())
                self.assertTrue((polygon.max(axis=0) > [28, 28]).all())
                self.assertTrue((polygon.min(axis=0) > [1, 1]).all())
                wrong_channel = np.zeros_like(image)
                wrong_channel[16:40, 16:40] = [255, 0, 0]
                self.assertEqual(detector.detect_quads(wrong_channel), [])
                self.assertEqual(detector.metadata['active_execution_providers'], ['CPUExecutionProvider'])
                derived = onnx.load(detector.metadata['model_path'])
                self.assertEqual([dim.dim_value for dim in derived.graph.input[0].type.tensor_type.shape.dim], [1, 3, 64, 64])
                self.assertEqual([node.SerializeToString() for node in derived.graph.node],
                                 [node.SerializeToString() for node in graph.node])
                self.assertEqual([weight.SerializeToString() for weight in derived.graph.initializer],
                                 [weight.SerializeToString() for weight in graph.initializer])
                with self.assertRaisesRegex(ValueError, 'SHA-256'):
                    prepare_static(source, '0' * 64, 64, directory)
            finally:
                detector.close()


class InputEvidenceTests(unittest.TestCase):
    def test_input_ocr_reuse_checks_pixels_and_output_always_reaches_judge(self):
        import cv2
        from bench.fast_replay import ReferenceInputs
        class OutputJudge:
            names = ['synthetic-output-judge']
            def __init__(self):
                self.seen = []
            def read(self, pixels):
                self.seen.append(pixels.copy())
                return [{'text': 'OUTPUT', 'confidence': .9, 'box': [1, 2, 3, 4]}]
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'source.png'
            pixels = np.full((32, 64, 3), [12, 34, 56], np.uint8)
            self.assertTrue(cv2.imwrite(str(source), pixels))
            judge = OutputJudge()
            readings = [[{'text': 'INPUT', 'confidence': .95, 'box': [1, 2, 3, 4]}]]
            wrapped = ReferenceInputs(judge, source, readings)
            with self.assertRaisesRegex(ValueError, 'pixel identity'):
                wrapped.read(np.zeros_like(pixels))
            self.assertEqual(wrapped.read(pixels), readings[0])
            with self.assertRaisesRegex(RuntimeError, 'incomplete'):
                wrapped.verify_complete()
            masked = np.full_like(pixels, 89)
            self.assertEqual(wrapped.read(masked), [{'text': 'OUTPUT', 'confidence': .9, 'box': [1, 2, 3, 4]}])
            wrapped.verify_complete()
            self.assertEqual(len(judge.seen), 1)
            np.testing.assert_array_equal(judge.seen[0], masked)


if __name__ == '__main__':
    unittest.main()

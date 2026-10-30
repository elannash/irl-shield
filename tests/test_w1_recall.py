"""Layered arms preserve all raw geometry and expose each actual model call."""
import unittest
import numpy as np


class Model:
    def __init__(self,name):
        self.name=name
        self.inputs=[]
        self.metadata={"name":name,"detector_families":["paddleocr"]}
    def detect_quads(self,pixels):
        self.inputs.append(pixels.copy())
        x=10 if self.name=="ppocr-v5-server" else 1
        return [[[x,1],[x+2,1],[x+2,3],[x,3]]]
    def close(self): pass


class RecallArms(unittest.TestCase):
    def build(self,name):
        from bench.w1.detectors import create_arm
        self.models=[]
        def factory(model,options):
            backend=Model(model)
            self.models.append(backend)
            return backend
        return create_arm(name,{"input_size":[48,96],"detect_width":96,"limit_side_len":960},detector_factory=factory)

    def test_v6_v5_server_union_retains_both_models_without_family_override(self):
        from bench.independence import policy_metadata
        arm=self.build("w1-small-server-union")
        quads=arm.detect_quads(np.full((48,96,3),80,np.uint8))
        self.assertEqual([q[0][0] for q in quads],[1,10])
        self.assertEqual([m.name for m in self.models],["ppocr-v6-small","ppocr-v5-server"])
        self.assertEqual(policy_metadata("w1-small-server-union",{})["detector_families"],["paddleocr"])
        with self.assertRaisesRegex(ValueError,"overrides"):
            policy_metadata("w1-small-server-union",{"detector_families":["apple-vision"]})

    def test_light_pair_keeps_original_pass_and_does_not_mutate_input(self):
        arm=self.build("w1-small-light-pair")
        pixels=np.full((48,96,3),30,np.uint8)
        saved=pixels.copy()
        quads=arm.detect_quads(pixels)
        self.assertEqual(len(quads),3)
        self.assertEqual(len(self.models[0].inputs),3)
        self.assertGreater(len({p.tobytes() for p in self.models[0].inputs}),1)
        np.testing.assert_array_equal(pixels,saved)

    def test_tiling_returns_source_coordinates_and_all_crop_results(self):
        arm=self.build("w1-small-tiled")
        quads=arm.detect_quads(np.full((48,96,3),80,np.uint8))
        self.assertEqual(len(quads),5)
        self.assertEqual([q[0] for q in quads],[[1,1],[1,1],[39,1],[1,20],[39,20]])

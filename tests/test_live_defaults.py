"""Frozen S10 policy wiring, executable with stdlib only and no model sessions.

The live factory body is compiled from source so its heavyweight transport imports
cannot initialize GPU/media dependencies in this source-only smoke suite.
"""
import ast
from contextlib import redirect_stdout
import importlib.machinery
import importlib.util
from io import StringIO
import json
import math
from numbers import Real
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

from models import prepare
from shield.cli import parser, validate
from tools.demo_renderer.options import validate_demo

ROOT = Path(__file__).resolve().parents[1]


def live_factory():
    source = ast.parse((ROOT / 'relay/runtime.py').read_text())
    function = next(node for node in source.body if isinstance(node, ast.FunctionDef) and node.name == 'make_engine')
    namespace = {'math': math, 'Real': Real, 'DetectorLane': Mock(), 'MaskingEngine': Mock()}
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'relay/runtime.py', 'exec'), namespace)
    return namespace


def walk_module():
    loader = importlib.machinery.SourceFileLoader('default_walk_linux', str(ROOT / 'scripts/walk-linux'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class FrozenLiveDefaults(unittest.TestCase):
    def construct(self, **options):
        namespace = live_factory()
        detector = ModuleType('bench.onnx_detectors')
        detector.create_detector = Mock()
        with patch.dict(sys.modules, {'bench.onnx_detectors': detector}):
            namespace['make_engine']('/synthetic-cache', **options)
        return namespace, detector.create_detector

    def test_s10_effective_lane_models_widths_caps_shapes_and_thresholds(self):
        # Independent literals from the owner-selected S10 policy, not live defaults.
        namespace, factory = self.construct()
        fast, accurate = factory.call_args_list
        for call, cap, shape in ((fast, 640, [352, 640]), (accurate, 960, [544, 960])):
            self.assertEqual(call.args, ('ppocr-v5-mobile', {
                'thresh': .3, 'box_thresh': .5, 'unclip_ratio': 1.6,
                'provider': 'cuda', 'threads': 2, 'cache_dir': '/synthetic-cache',
                'limit_side_len': cap, 'static_shape': shape}))
        self.assertEqual([(c.args[0], c.args[2], c.kwargs['width'])
                          for c in namespace['DetectorLane'].call_args_list],
                         [('fast', 8, 640), ('accurate', 4, 1280)])
        self.assertEqual(namespace['MaskingEngine'].call_args.args[1], {
            'fps': 30, 'delay_seconds': 1., 'before': 6, 'after': 30,
            'fast_max_age': 6, 'accurate_max_age': 12, 'motion_mode': 'phase',
            'motion_width': 320, 'motion_min_response': .05, 'padding': .3})

    def test_explicit_cpu_delay_cadence_and_floor_keep_fast_policy(self):
        namespace, factory = self.construct(provider='cpu', delay_seconds=2.5,
                                             accurate_rate_hz=15, accurate_box_thresh=.73)
        self.assertEqual([c.args[1]['provider'] for c in factory.call_args_list], ['cpu', 'cpu'])
        self.assertEqual([c.args[1]['box_thresh'] for c in factory.call_args_list], [.5, .73])
        self.assertEqual([c.args[2] for c in namespace['DetectorLane'].call_args_list], [8, 15])
        self.assertEqual(namespace['MaskingEngine'].call_args.args[1]['delay_seconds'], 2.5)

    def test_invalid_policy_still_rejects_before_detector_construction(self):
        for options in ({'delay_seconds': .49}, {'accurate_rate_hz': 31},
                        {'accurate_box_thresh': float('nan')}):
            with self.subTest(options=options):
                namespace = live_factory()
                detector = ModuleType('bench.onnx_detectors')
                detector.create_detector = Mock()
                with patch.dict(sys.modules, {'bench.onnx_detectors': detector}), self.assertRaises(ValueError):
                    namespace['make_engine']('/unused', **options)
                detector.create_detector.assert_not_called()

    def test_cli_and_launcher_leave_frozen_defaults_to_live_factory(self):
        walk = walk_module()
        for prefix in (['run'], ['login', '--run']):
            args = parser().parse_args([*prefix, '--host', '127.0.0.1'])
            validate(args)
            self.assertIsNone(args.accurate_rate_hz)
            self.assertIsNone(args.accurate_box_thresh)
        args = walk.parser().parse_args(['--local-only', '--host', '127.0.0.1'])
        routed = parser().parse_args(walk.cli_arguments(args, args.host))
        self.assertIsNone(routed.accurate_rate_hz)
        self.assertIsNone(routed.accurate_box_thresh)

    def test_demo_accepts_defaults_and_rejects_detector_overrides(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / 'source.json'
            source.write_text(json.dumps({'fps': 30, 'seconds': 210, 'frames': [{}] * 6300}))
            base = ['run', '--local-only', '--host', '127.0.0.1', '--seconds', '230',
                    '--demo-source', str(source), '--demo-receipt', str(root / 'sender.jsonl'),
                    '--archive', str(root / 'archive')]
            validate_demo(parser().parse_args(base))
            for override in (['--accurate-rate-hz', '4'], ['--accurate-box-thresh', '.5']):
                with self.subTest(override=override), self.assertRaisesRegex(ValueError, 'frozen PP-OCRv5-mobile'):
                    validate_demo(parser().parse_args(base + override))


class ModelPreparationDefaults(unittest.TestCase):
    def test_v5_mobile_retains_reviewed_apache_pin(self):
        artifact = prepare.load_manifest()['artifacts']['ppocr-v5-mobile']
        self.assertEqual(artifact['license'], 'Apache-2.0')
        self.assertEqual(artifact['sha256'], '4d97c44a20d30a81aad087d6a396b08f786c4635742afc391f6621f5c6ae78ae')
        self.assertIn('/v3.10.0/', artifact['url'])
        self.assertIn('/0d63e78e2b680928f6b1747d76a08db6e645efb7/', artifact['license_source'])

    def test_default_all_artifacts_adds_two_live_static_graphs_without_inference(self):
        static = ModuleType('bench.static_model')
        static.prepare_static = Mock(return_value=(Path('/synthetic-static'), {}))
        with tempfile.TemporaryDirectory() as name:
            weight = Path(name) / 'weight'
            weight.write_bytes(b'synthetic')
            artifact = prepare.load_manifest()['artifacts']['ppocr-v5-mobile']
            with patch.object(sys, 'argv', ['models.prepare', '--cache-dir', name]), \
                    patch.object(prepare, 'download', return_value=weight) as download, \
                    patch.object(prepare, 'verified_path', return_value=(weight, artifact)) as verified, \
                    patch.dict(sys.modules, {'bench.static_model': static}), redirect_stdout(StringIO()):
                prepare.main()
            verified.assert_called_once_with('ppocr-v5-mobile', Path(name))
            self.assertEqual([c.args[0] for c in download.call_args_list], list(prepare.load_manifest()['artifacts']))
            self.assertEqual([(c.args[2], c.args[3]) for c in static.prepare_static.call_args_list],
                             [(352, 640), (544, 960)])
            for call in static.prepare_static.call_args_list:
                self.assertEqual(call.args[:2], (weight, artifact['sha256']))

    def test_explicit_artifact_and_verify_only_keep_no_extra_work_contract(self):
        with tempfile.TemporaryDirectory() as name:
            weight = Path(name) / 'weight'
            weight.write_bytes(b'synthetic')
            artifact = prepare.load_manifest()['artifacts']['ppocr-v6-small']
            for flags in (['ppocr-v6-small'], ['--verify-only']):
                with self.subTest(flags=flags), patch.object(sys, 'argv', ['models.prepare', *flags]), \
                        patch.object(prepare, 'download', return_value=weight) as download, \
                        patch.object(prepare, 'verified_path', return_value=(weight, artifact)) as verified, \
                        patch.dict(sys.modules, {'bench.static_model': None}), redirect_stdout(StringIO()):
                    prepare.main()
                if flags == ['--verify-only']:
                    download.assert_not_called()
                    self.assertEqual(verified.call_count, len(prepare.load_manifest()['artifacts']))
                else:
                    download.assert_called_once_with('ppocr-v6-small', prepare.DEFAULT_CACHE)
                    verified.assert_not_called()


if __name__ == '__main__':
    unittest.main()

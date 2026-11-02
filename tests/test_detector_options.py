"""Lane policy wiring, without model sessions or native workers."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from bench.detector_options import lane_detector_options
from bench.offline_quality import _make_backends
from bench.clocked_pipeline import _run_file
from relay.runtime import make_engine


class EmptyDetector:
    def __init__(self):
        self.closed = False

    def detect_quads(self, pixels):
        return []

    def close(self):
        self.closed = True


class StopAfterFactory(RuntimeError):
    pass


class DetectorOptions(unittest.TestCase):
    def test_default_off_preserves_options_without_mutation(self):
        for options in ({}, {'box_thresh': .42}, {'box_thresh': .42, 'accurate_box_thresh': None}):
            saved = dict(options)
            expected = {key: value for key, value in options.items() if key != 'accurate_box_thresh'}
            for lane in ('fast', 'accurate'):
                with self.subTest(options=options, lane=lane):
                    self.assertEqual(lane_detector_options(options, lane), expected)
            self.assertEqual(options, saved)

    def test_override_is_accurate_only_including_zero_and_one(self):
        for floor in (0, .73, 1):
            options = {'box_thresh': .42, 'accurate_box_thresh': floor, 'provider': 'cpu'}
            with self.subTest(floor=floor):
                self.assertEqual(lane_detector_options(options, 'fast'), {'box_thresh': .42, 'provider': 'cpu'})
                self.assertEqual(lane_detector_options(options, 'accurate'), {'box_thresh': floor, 'provider': 'cpu'})
                self.assertEqual(options['box_thresh'], .42)

    def test_invalid_floors_reject_before_offline_clocked_or_native_construction(self):
        for floor in (True, False, '0.7', [], {}, -.01, 1.01, 10**1000, float('nan'), float('inf'), -float('inf')):
            with self.subTest(floor=floor), \
                 patch('bench.pipeline.detector_for') as factory, \
                 patch('bench.onnx_detectors.create_detector') as native, \
                 patch('bench.clocked_pipeline.probe_media', side_effect=AssertionError('Unexpected media work')):
                options = {'accurate_box_thresh': floor}
                with self.assertRaisesRegex(ValueError, 'accurate_box_thresh'):
                    _make_backends('ppocr-v6-small', options, [1280, 720])
                with self.assertRaisesRegex(ValueError, 'accurate_box_thresh'):
                    _run_file('/unused', '/unused-output', 'ppocr-v6-small', options, None, {})
                with self.assertRaisesRegex(ValueError, 'accurate_box_thresh'):
                    make_engine('/unused', accurate_box_thresh=floor)
                factory.assert_not_called()
                native.assert_not_called()

    def test_offline_routes_override_and_keeps_fast_configuration(self):
        for floor in (None, .73):
            options = {'box_thresh': .42, 'accurate_box_thresh': floor, 'provider': 'cuda',
                       'fast_provider': 'cpu', 'fast_limit_side_len': 640, 'limit_side_len': 960}
            saved = dict(options)
            with self.subTest(floor=floor), \
                 patch('bench.pipeline.detector_for', side_effect=lambda *args: EmptyDetector()) as factory:
                backends = _make_backends('ppocr-v6-small', options, [1280, 720])
                try:
                    fast, accurate = factory.call_args_list
                    self.assertEqual([fast.args[0], accurate.args[0]], ['ppocr-v6-tiny', 'ppocr-v6-small'])
                    self.assertEqual(fast.args[1]['box_thresh'], .42)
                    self.assertEqual(accurate.args[1]['box_thresh'], .42 if floor is None else .73)
                    self.assertEqual([fast.args[1]['provider'], accurate.args[1]['provider']], ['cpu', 'cuda'])
                    self.assertEqual([fast.args[1]['limit_side_len'], accurate.args[1]['limit_side_len']], [640, 960])
                    self.assertNotIn('accurate_box_thresh', fast.args[1])
                    self.assertNotIn('accurate_box_thresh', accurate.args[1])
                    self.assertEqual(options, saved)
                finally:
                    for backend in backends.values():
                        backend.close()

    def test_clocked_routes_override_before_workers_and_closes_fast_on_abort(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'source.mp4'
            source.write_bytes(b'synthetic source; decoding is supplied at the boundary')
            backend = EmptyDetector()
            with patch('bench.clocked_pipeline.probe_media', return_value={'fps': 30., 'frames': 2, 'resolution': [1280, 720]}), \
                 patch('bench.clocked_pipeline.subprocess.check_output', return_value='synthetic ffmpeg version\n'), \
                 patch('bench.clocked_pipeline.cv2.VideoCapture') as capture, \
                 patch('bench.pipeline.detector_for', side_effect=[backend, StopAfterFactory()]) as factory:
                capture.return_value.read.return_value = (True, np.zeros((720, 1280, 3), np.uint8))
                with self.assertRaises(StopAfterFactory):
                    _run_file(source, Path(temporary) / 'output.mp4', 'ppocr-v6-small',
                              {'box_thresh': .42, 'accurate_box_thresh': .73}, None, {})
                self.assertEqual([call.args[1]['box_thresh'] for call in factory.call_args_list], [.42, .73])
                self.assertTrue(backend.closed)
                capture.return_value.release.assert_called_once_with()

    def test_native_routes_override_without_changing_defaults_or_starting_workers(self):
        for provider, floor, rate, delay in ((None, None, None, None), ('cpu', None, None, 2.5),
                                            ('cpu', .73, 15, .5), ('cpu', .73, 7.5, 3.25),
                                            ('cpu', None, None, 10), ('cuda', None, None, .5),
                                            ('cuda', None, None, 2.5), ('cuda', None, None, 10)):
            with self.subTest(provider=provider, floor=floor, rate=rate, delay=delay), \
                 patch('bench.onnx_detectors.create_detector', side_effect=lambda *args: EmptyDetector()) as factory, \
                 patch('relay.runtime.DetectorLane') as lane, patch('relay.runtime.MaskingEngine') as engine:
                options = {'accurate_box_thresh': floor}
                if rate is not None:
                    options['accurate_rate_hz'] = rate
                if provider is not None:
                    options['provider'] = provider
                if delay is not None:
                    options['delay_seconds'] = delay
                result = make_engine('/synthetic-cache', **options)
                self.assertIs(result, engine.return_value)
                fast, accurate = factory.call_args_list
                self.assertEqual(fast.args, ('ppocr-v5-mobile', {'provider': provider or 'cuda', 'threads': 2,
                                                           'cache_dir': '/synthetic-cache', 'limit_side_len': 640, 'static_shape': [352, 640],
                                                           'thresh': .3, 'box_thresh': .5, 'unclip_ratio': 1.6}))
                expected = {'provider': provider or 'cuda', 'threads': 2, 'cache_dir': '/synthetic-cache', 'limit_side_len': 960,
                            'static_shape': [544, 960], 'thresh': .3, 'box_thresh': .5, 'unclip_ratio': 1.6}
                if floor is not None:
                    expected['box_thresh'] = .73
                self.assertEqual(accurate.args, ('ppocr-v5-mobile', expected))
                self.assertEqual([call.args[0] for call in lane.call_args_list], ['fast', 'accurate'])
                self.assertEqual([call.args[2] for call in lane.call_args_list], [8, 4 if rate is None else rate])
                self.assertEqual([call.kwargs['width'] for call in lane.call_args_list], [640, 1280])
                self.assertEqual(engine.call_args.args[1]['delay_seconds'], 1 if delay is None else delay)
                self.assertEqual(engine.call_args.args[1]['fps'], 30)

    def test_native_invalid_delay_stops_before_backend_construction(self):
        for provider in ('cpu', 'cuda'):
            for delay in (True, False, '2.5', [], -.1, 0, .25, 10.000001, 10**1000,
                          float('nan'), float('inf'), float('-inf')):
                with self.subTest(provider=provider, delay=delay), patch('bench.onnx_detectors.create_detector') as factory, \
                        patch('relay.runtime.DetectorLane'), patch('relay.runtime.MaskingEngine'):
                    with self.assertRaisesRegex(ValueError, 'delay_seconds'):
                        make_engine('/unused', provider=provider, delay_seconds=delay)
                    factory.assert_not_called()

    def test_native_invalid_rate_stops_before_backend_construction(self):
        for rate in (True, False, '15', [], 0, -.1, 30.1, 10**1000, float('nan'), float('inf')):
            with self.subTest(rate=rate), patch('bench.onnx_detectors.create_detector') as factory:
                with self.assertRaisesRegex(ValueError, 'accurate_rate_hz'):
                    make_engine('/unused', accurate_rate_hz=rate)
                factory.assert_not_called()

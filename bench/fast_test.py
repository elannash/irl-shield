"""FAST adapter contracts; synthetic arrays, no model download or inference."""
import unittest
from unittest.mock import patch

import numpy as np

from bench.fast import FastDetector


class FastAdapterTests(unittest.TestCase):
    def test_unavailable_requested_provider_is_an_error_before_model_loading(self):
        from bench.fast import provider_config
        with self.assertRaisesRegex(RuntimeError, 'CUDAExecutionProvider'):
            provider_config('cuda', ['CPUExecutionProvider'], '/unused')

    def test_bgr_frame_and_normalized_rotated_polygon_cross_detector_seam(self):
        seen = []

        def predict(pages):
            seen.append(pages[0])
            # OnnxTR's fifth point is (score, score), never geometry.
            return [np.array([[[.1, .2], [.6, .1], [.7, .5], [.2, .6], [.9, .9]]])]

        frame = np.full((100, 200, 3), [10, 20, 30], dtype=np.uint8)
        with patch('bench.fast._load_predictor', return_value=(predict, {'name': 'fast-tiny'})):
            detector = FastDetector()
        quads = detector.detect_quads(frame)
        np.testing.assert_allclose(quads, [[[20, 20], [120, 10], [140, 50], [40, 60]]])
        np.testing.assert_array_equal(seen[0][0, 0], [30, 20, 10])
        np.testing.assert_array_equal(frame[0, 0], [10, 20, 30])
        detector.close()
        with self.assertRaisesRegex(RuntimeError, 'closed'):
            detector.detect_quads(frame)

class ComplementarityTests(unittest.TestCase):
    def test_complete_leaked_interval_recovery_rejects_partial_and_protected_wins(self):
        from bench.fast_compare import interval_complementarity
        def track(text, first, last, leaks):
            return {'text': text, 'texts': [text], 'first': first, 'last': last,
                    'observations': [[first, [1, 2, 3, 4]], [last, [1, 2, 3, 4]]],
                    'leaked': bool(leaks), 'leak_frames': leaks}
        rows = [{'state': 'LIVE', 'protected': False, 'slate': False} for _ in range(8)]
        baseline = {'natural': [track('ALPHA', 0, 1, [0, 1]), track('BETA', 2, 3, [2, 3]),
                                track('GAMMA', 4, 5, [4, 5]), track('DELTA', 6, 7, [])]}
        candidate = {'natural': [track('ALPHA', 0, 1, []), track('BETA', 2, 3, [3]),
                                 track('GAMMA', 4, 5, []), track('DELTA', 6, 7, [7])], 'presentation': rows,
                     'frame_guards': [{'pass': True} for _ in rows]}
        rows[5]['protected'] = True
        result = interval_complementarity(baseline, candidate)
        self.assertEqual(result['baseline_leaked_intervals'], 3)
        self.assertEqual(result['new_raw_leaked_intervals'], 1)
        self.assertEqual(result['raw_net_hidden_interval_change'], 1)
        self.assertEqual(result['raw_recovered_intervals'], 2)
        self.assertEqual(result['guarded_recovered_intervals'], 1)
        self.assertAlmostEqual(result['guarded_recovered_fraction'], 1 / 3)
        self.assertEqual(result['rejected_protected_intervals'], 1)
        candidate['frame_guards'][0]['pass'] = False
        self.assertEqual(interval_complementarity(baseline, candidate)['guarded_recovered_intervals'], 0)
        candidate['natural'][0]['text'] = 'CHANGED TRUTH'
        with self.assertRaisesRegex(ValueError, 'truth'):
            interval_complementarity(baseline, candidate)

class ReplayTests(unittest.TestCase):
    def test_union_replays_original_schedule_and_scales_source_quads_once(self):
        from bench.fast_replay import ReplayDetector, UnionDetector
        rows = [{'source_index': index, 'detector_input_shape': [50, 100, 3],
                 'quads': [[[20, 10], [60, 10], [60, 30], [20, 30]]]} for index in [0, 3]]
        replay = ReplayDetector(rows, source_shape=(100, 200, 6), fps=30., rate=10.)
        class Extra:
            metadata = {'name': 'synthetic-fast'}
            def detect_quads(self, pixels):
                return [[[70, 10], [80, 10], [80, 20], [70, 20]]]
        union = UnionDetector(replay, Extra())
        pixels = np.zeros((50, 100, 3), dtype=np.uint8)
        result = union.detect_quads(pixels)
        np.testing.assert_allclose(result, [[[10, 5], [30, 5], [30, 15], [10, 15]],
                                          [[70, 10], [80, 10], [80, 20], [70, 20]]])
        with self.assertRaisesRegex(RuntimeError, 'every scheduled'):
            replay.verify_complete()
        union.detect_quads(pixels)
        replay.verify_complete()
        with self.assertRaisesRegex(RuntimeError, 'exhausted'):
            union.detect_quads(pixels)
        with self.assertRaisesRegex(ValueError, 'schedule'):
            ReplayDetector(rows, source_shape=(100, 200, 6), fps=30., rate=15.)

class ReadinessTests(unittest.TestCase):
    def test_corrected_false_marker_cannot_authorize_work_after_waiting_for_lease(self):
        import json
        from pathlib import Path
        import tempfile
        from bench.fast_lease import require_complete
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / 'ready.json'
            marker.write_text(json.dumps({'complete': True, 'valid': False}))
            self.assertIs(require_complete(marker)['complete'], True)
            marker.write_text(json.dumps({'complete': False}))
            with self.assertRaisesRegex(RuntimeError, 'must wait'):
                require_complete(marker)


class QueueContextTests(unittest.TestCase):
    def test_forced_queue_receipt_stays_diagnostic_and_lease_must_match(self):
        import json
        import os
        from pathlib import Path
        import tempfile
        from bench.fast_lease import read_queue_context
        from bench.fast_runtime import cost_trust
        with tempfile.TemporaryDirectory() as temporary:
            lock = Path(temporary) / 'perf.lock'
            other = Path(temporary) / 'other.lock'
            with lock.open('w') as stream, other.open('w') as wrong:
                values = {'IRL_SHIELD_PERF_QUEUE_FORCED': '1',
                          'IRL_SHIELD_PERF_QUEUE_ATTEMPT': '2',
                          'IRL_SHIELD_PERF_QUEUE_RECEIPT': str(Path(temporary) / 'attempt.json'),
                          'IRL_SHIELD_PERF_QUEUE_LEASE_FD': str(stream.fileno())}
                with patch.dict(os.environ, values, clear=True), patch('bench.fast_lease.PERF_LOCK', lock):
                    context = read_queue_context()
                    self.assertIs(context['forced'], True)
                    self.assertEqual(context['attempt'], 2)
                    healthy = {phase: {'pressure_state': 'normal'} for phase in ('start', 'end')}
                    verdict = cost_trust(healthy, contended=False, provider_executed=True,
                                         forced=context['forced'])
                    self.assertFalse(verdict['valid'])
                    self.assertIn('forced-contended', verdict['reasons'])
                    self.assertTrue(cost_trust(healthy, contended=False, provider_executed=True,
                                               forced=False)['valid'])
                    healthy['end']['pressure_state'] = 'warn'
                    self.assertFalse(cost_trust(healthy, contended=False, provider_executed=True,
                                                forced=False)['valid'])
                    os.environ['IRL_SHIELD_PERF_QUEUE_LEASE_FD'] = str(wrong.fileno())
                    with self.assertRaisesRegex(RuntimeError, 'canonical'):
                        read_queue_context()


if __name__ == '__main__':
    unittest.main()

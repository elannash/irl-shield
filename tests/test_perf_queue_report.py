"""Synthetic receipts exercise the joined queue/benchmark acceptance seam."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from bench.perf_queue import Queue
from bench.perf_queue_report import report, queue_attempt_clean


class JoinedPerformanceReceipts(unittest.TestCase):
    def test_v2_accepts_job_cpu_and_rejects_external_mean_while_preserving_legacy(self):
        endpoint = {'idle_percent': 90., 'memory_ok': True}
        sample = {'idle_percent': 50., 'memory_ok': True, 'interval_seconds': 10.,
                  'total_busy_percent': 50., 'job_tree_busy_percent': 50.,
                  'other_busy_percent': 0., 'cpu_accounting_valid': True}
        receipt = {'phase': 'closed', 'contended': False,
                   'contamination_policy': 'other-busy-v2',
                   'start_health': endpoint, 'end_health': endpoint,
                   'periodic_health': [sample]}
        self.assertTrue(queue_attempt_clean(receipt))
        legacy = {key: value for key, value in receipt.items() if key != 'contamination_policy'}
        self.assertFalse(queue_attempt_clean(legacy))
        sample.update(idle_percent=12.5, total_busy_percent=87.5, other_busy_percent=37.5)
        self.assertFalse(queue_attempt_clean(receipt))

    def test_normal_endpoint_memory_cannot_hide_queue_contamination(self):
        snapshot = {'platform': 'Linux', 'health_adapter': 'linux-available-owner-v2',
                    'pressure_state': 'normal', 'pressure_level': None,
                    'load_average': [2., 2., 2.], 'cpu_count': 8,
                    'raw': {key: {'returncode': 0} for key in ('memory_psi', 'meminfo', 'vmstat')}}
        performance = {
            'frames': 1200, 'encoded_frames': 1200, 'source_frames': 1200,
            'source_fps': 30., 'resolution': [1280, 720], 'source_duration_seconds': 40.,
            'warmup_frames': 300, 'warmup_seconds': 10.,
            'steady': {'frames': 900, 'start_frame': 300, 'stop_frame_exclusive': 1200,
                       'source_duration_seconds': 30.},
            'output_media': {'frames': 1200, 'fps': 30., 'resolution': [1280, 720],
                             'pts': [index / 30 for index in range(1200)]},
            'output_wall_rate_fps': 30., 'output_clock_drift_seconds': 0.,
            'first_encoded_at': 11., 'last_encoded_at': 40.96666666666667,
            'realtime_added_latency_seconds': {'p50': 1.1, 'p95': 1.2},
            'protected_fraction': .01, 'live_frames': 891, 'seconds': 41.02,
            'performance_valid': True, 'candidate': 'ppocr-v6-small',
            'encoder': 'h264_nvenc', 'options': {'fast_rate_hz': 8},
            'perf_health': {'start': snapshot, 'end': snapshot}}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue = Queue(root / 'queue')
            job = queue.enqueue('linux', 'root-sustained', ['true'], cwd=root)
            claimed, attempt = queue.begin('linux')
            path = root / 'sample.performance.json'
            path.write_text(json.dumps(performance))
            receipt = {'phase': 'closed', 'contended': True, 'returncode': 0,
                       'start_health': {'idle_percent': 95., 'memory_ok': True},
                       'end_health': {'idle_percent': 95., 'memory_ok': True},
                       'periodic_health': [{'idle_percent': 45., 'memory_ok': True}],
                       'receipts': [{'path': str(path), 'exists': True,
                                     'bytes': path.stat().st_size,
                                     'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}]}
            queue.finish(claimed, attempt, receipt)
            row = report(queue.root)['rows'][0]
            self.assertFalse(row['measurement_trusted'])
            self.assertFalse(row['clock_guards']['throughput'])
            self.assertFalse(row['clock_guards']['latency'])
            self.assertIn('queue-contended', row['rejection_reasons'])
            self.assertEqual(row['steady_fps'], 30.)
            self.assertEqual(row['steady_p95_seconds'], 1.2)
            receipt.update(contended=False, periodic_health=[{'idle_percent': 90., 'memory_ok': True}])
            (attempt / 'attempt.json').write_text(json.dumps(receipt))
            clean = report(queue.root)['rows'][0]
            self.assertTrue(clean['measurement_trusted'])
            self.assertTrue(clean['clock_guards']['throughput'])
            self.assertTrue(clean['clock_guards']['latency'])
            path.write_text(path.read_text() + '\n')
            changed = report(queue.root)['rows'][0]
            self.assertFalse(changed['measurement_trusted'])
            self.assertTrue(any('artifact hash/size' in reason for reason in changed['rejection_reasons']))

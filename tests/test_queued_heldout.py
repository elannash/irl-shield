"""Queue-selection/once-only seam; synthetic grader, real persisted receipts.

This catches repeated scoring or selecting a contended trial over a clean one;
it does not exercise native OCR or sealed-plan validation, owned by cross_host.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from bench.perf_queue import Queue
from bench.queued_heldout import finish_once


class QueuedHeldout(unittest.TestCase):
    def trial(self, queue, contended):
        job, folder = queue.begin('mac')
        plan = folder / 'measurement-plan.json'
        plan.write_text('synthetic sealed measurement, not a real video bundle')
        snapshot = {'idle_percent': 90., 'memory_ok': True}
        receipt = {'phase': 'closed', 'attempt': len(job['attempts']), 'contended': contended,
                   'returncode': 0, 'start_health': snapshot, 'end_health': snapshot,
                   'periodic_health': [snapshot],
                   'receipts': [{'path': str(plan), 'exists': True, 'bytes': plan.stat().st_size,
                                 'sha256': hashlib.sha256(plan.read_bytes()).hexdigest()}]}
        queue.finish(job, folder, receipt)
        return plan

    def test_selects_by_clean_measurement_receipt_and_grades_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); queue = Queue(root / 'queue')
            job = queue.enqueue('mac', 'heldout', ['true'], cwd=root)
            rejected, folder = queue.begin('mac')
            queue.finish(rejected, folder, {'phase': 'closed', 'attempt': 1,
                         'contended': True, 'returncode': 1,
                         'receipts': [{'path': str(folder / 'measurement-plan.json'), 'exists': False}]})
            self.trial(queue, True)
            clean = self.trial(queue, False)
            calls = []
            def grader(plan):
                calls.append(plan)
                return {'split': 'heldout', 'scope': 'synthetic test',
                        'natural': {'hidden': 9, 'total': 10}, 'synthetic': {'hidden': 2, 'total': 2},
                        'gate_1': {'throughput': True, 'latency': True, 'natural': True,
                                   'synthetic': True, 'eligible': True, 'pass': True}}
            final = root / 'final'
            card = finish_once(queue.root, job['id'], final, grade=grader)
            self.assertEqual(calls, [clean])
            self.assertTrue(card['gate_1']['pass'])
            self.assertTrue(card['queue_measurement_trust']['clean'])
            saved = (final / 'scorecard.json').read_bytes()
            again = finish_once(queue.root, job['id'], final, grade=grader)
            self.assertEqual(again, card)
            self.assertEqual(calls, [clean])
            self.assertEqual((final / 'scorecard.json').read_bytes(), saved)
            with self.assertRaisesRegex(ValueError, 'different measurement job'):
                finish_once(queue.root, 'another-job', final, grade=grader)
            clean.write_text(clean.read_text() + '\nchanged after scoring')
            with self.assertRaisesRegex(ValueError, 'retained measurement changed'):
                finish_once(queue.root, job['id'], final, grade=grader)
            self.assertEqual(calls, [clean])

    def test_all_contended_measurements_retain_quality_but_cannot_pass_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); queue = Queue(root / 'queue')
            job = queue.enqueue('mac', 'heldout', ['true'], cwd=root)
            self.trial(queue, True)
            self.trial(queue, True)
            last = self.trial(queue, True)
            observed = []
            def grader(plan):
                observed.append(plan)
                return {'split': 'heldout', 'scope': 'synthetic test',
                        'natural': {'hidden': 9, 'total': 10},
                        'synthetic': {'hidden': 2, 'total': 2},
                        'gate_1': {'throughput': True, 'latency': True,
                                   'natural': True, 'synthetic': True, 'pass': True}}
            card = finish_once(queue.root, job['id'], root / 'final', grade=grader)
            self.assertEqual(observed, [last])
            self.assertFalse(card['gate_1']['pass'])
            self.assertFalse(card['gate_1']['throughput'])
            self.assertFalse(card['gate_1']['latency'])
            self.assertEqual(card['natural'], {'hidden': 9, 'total': 10})
            self.assertEqual(card['synthetic'], {'hidden': 2, 'total': 2})

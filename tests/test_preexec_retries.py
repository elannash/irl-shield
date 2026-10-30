"""Execution budgets use synthetic health, real trial files and foreground jobs."""
import json
from pathlib import Path
import sys
import unittest

from bench import perf_queue
import test_perf_queue as fixtures


class PreExecutionRetries(unittest.TestCase):
    def setUp(self):
        fixtures.PerformanceQueue.setUp(self)
        self.queue = perf_queue.Queue(self.storage)

    def runner(self, **options):
        return fixtures.PerformanceQueue.runner(self, self.queue, **options)

    def test_rejected_start_leaves_all_three_executions_available(self):
        self.queue.enqueue('linux', 'rejected-start', ['must-not-execute'], cwd=self.caller)

        class RejectStart(fixtures.QuietHealth):
            def sample(self, **options):
                return super().sample(**options) | {'idle_percent': 10.}

        runner = self.runner(sensor=RejectStart())
        with perf_queue.PerlLease(self.root / 'perf.lock') as lease:
            runner.attempt(*self.queue.begin('linux'), lease, False)
        row = self.queue.status('linux')['linux']['jobs'][0]
        self.assertEqual(row['state'], 'pending')
        self.assertEqual(row['attempts'], [], 'START rejection must not spend an execution')
        self.assertEqual(len(row['preexec_rejections']), 1)
        path = Path(row['preexec_rejections'][0])
        rejected = json.loads(path.read_text())
        self.assertTrue(rejected['rejected_before_exec'])
        self.assertFalse(rejected['execution_started'])
        self.assertEqual(rejected['periodic_health'], [])
        self.assertFalse((path.parent / 'launch.json').exists())
        self.assertFalse((path.parent / 'stdout.log').exists())
        for _ in range(3):
            selected = self.queue.begin('linux')
            self.assertIsNotNone(selected)
            self.queue.finish(*selected, {'phase': 'closed', 'returncode': 0, 'contended': True})
        self.assertEqual(self.queue.jobs('linux')[0]['state'], 'exhausted-contended')

    def test_four_rejected_starts_then_first_execution_keep_distinct_artifacts(self):
        code = 'from pathlib import Path; import sys; Path(sys.argv[1]).write_text("executed")'
        job = self.queue.enqueue('linux', 'readiness-race', [sys.executable, '-c', code,
                                  '{job_dir}/output-{attempt}.txt'], cwd=self.caller,
                                 receipts=['{job_dir}/output-{attempt}.txt'])

        class ReadinessRace(fixtures.QuietHealth):
            checks = 0

            def sample(self, *, cpu_sampler=None, **options):
                health = super().sample(cpu_sampler=cpu_sampler, **options)
                if cpu_sampler is None:
                    self.checks += 1
                    if self.checks <= 12 and self.checks % 3 == 2:
                        health['idle_percent'] = 10.
                return health

        self.queue.seal('linux')
        self.assertEqual(self.runner(sensor=ReadinessRace()).run(), 'drained')
        row = self.queue.status('linux')['linux']['jobs'][0]
        self.assertEqual(row['state'], 'completed')
        self.assertEqual(len(row['preexec_rejections']), 4)
        self.assertEqual(len(row['attempts']), 1)
        executed = json.loads(Path(row['attempts'][0]).read_text())
        self.assertEqual((executed['attempt'], executed['execution_attempt']), (5, 1))
        self.assertEqual(executed['queue_environment']['IRL_SHIELD_PERF_QUEUE_ATTEMPT'], '5')
        self.assertEqual(Path(executed['receipts'][0]['path']).read_text(), 'executed')
        self.assertEqual(Path(executed['receipts'][0]['path']).name, 'output-5.txt')
        trials = row['preexec_rejections'] + row['attempts']
        self.assertEqual(len({Path(path).parent for path in trials}), 5)
        before = {path: Path(path).read_bytes() for path in trials}
        self.assertEqual(self.queue.recover('linux'), [])
        self.assertEqual(self.queue.recover('linux'), [])
        self.assertEqual(self.queue.jobs('linux')[0], row)
        self.assertEqual({path: Path(path).read_bytes() for path in trials}, before)
        self.assertEqual(list((self.storage / 'linux/jobs' / job['id']).glob('output-*.txt')),
                         [Path(executed['receipts'][0]['path'])])

    def busy_health(self):
        class BusyDuringExecution(fixtures.QuietHealth):
            def sample(self, *, cpu_sampler=None, **options):
                health = super().sample(cpu_sampler=cpu_sampler, **options)
                if cpu_sampler is not None:
                    health.update(idle_percent=30., total_busy_percent=70., other_busy_percent=70.)
                return health
        return BusyDuringExecution()

    def test_actual_contended_commands_exhaust_after_three_executions(self):
        output = self.root / 'executions'
        code = 'from pathlib import Path; import sys; f=Path(sys.argv[1]).open("a"); f.write(sys.argv[2]+"\\n"); f.close()'
        self.queue.enqueue('linux', 'contended', [sys.executable, '-c', code, str(output), '{attempt}'],
                           cwd=self.caller)
        self.queue.seal('linux')
        self.assertEqual(self.runner(sensor=self.busy_health()).run(), 'drained')
        row = self.queue.jobs('linux')[0]
        self.assertEqual(row['state'], 'exhausted-contended')
        self.assertEqual(output.read_text().splitlines(), ['1', '2', '3'])
        self.assertEqual(row['preexec_rejections'], [])
        receipts = [json.loads(Path(path).read_text()) for path in row['attempts']]
        self.assertEqual([receipt['execution_attempt'] for receipt in receipts], [1, 2, 3])
        self.assertTrue(all(receipt['execution_started'] and receipt['contended']
                            and receipt['returncode'] == 0 for receipt in receipts))
        self.assertIsNone(self.queue.begin('linux'))

    def test_old_exhausted_mixed_history_retains_bytes_and_only_spends_executions(self):
        code = 'from pathlib import Path; import sys; Path(sys.argv[1]).write_text("new execution")'
        job = self.queue.enqueue('linux', 'legacy', [sys.executable, '-c', code,
                                  '{job_dir}/output-{attempt}.txt'], cwd=self.caller,
                                 receipts=['{job_dir}/output-{attempt}.txt'])
        job.pop('preexec_rejections')
        directory = self.storage / 'linux/jobs' / job['id']
        before = {}
        for number, rejected in ((1, True), (2, False), (3, True)):
            path = directory / 'attempts' / f'{number:03d}' / 'attempt.json'
            path.parent.mkdir(parents=True)
            # Deliberately noncanonical whitespace guards against JSON rewrites.
            path.write_text(json.dumps({'phase': 'closed', 'attempt': number, 'returncode': None if rejected else 0,
                                        'contended': True, 'rejected_before_exec': rejected,
                                        'historical_label': 'total-idle-v1'}, separators=(',', ':')))
            job['attempts'].append(str(path))
            artifact = directory / f'output-{number}.txt'
            artifact.write_text('historical bytes')
            before.update({path: path.read_bytes(), artifact: artifact.read_bytes()})
        job['state'] = 'exhausted-contended'
        perf_queue.atomic_json(directory / 'job.json', job)
        self.queue.seal('linux')
        self.assertEqual(self.runner(sensor=self.busy_health()).run(), 'drained')
        row = self.queue.jobs('linux')[0]
        self.assertEqual(row['state'], 'exhausted-contended')
        self.assertEqual(row['attempts'][:3], job['attempts'])
        new = [json.loads(Path(path).read_text()) for path in row['attempts'][3:]]
        self.assertEqual([(receipt['attempt'], receipt['execution_attempt']) for receipt in new], [(4, 2), (5, 3)])
        self.assertEqual([Path(receipt['receipts'][0]['path']).name for receipt in new], ['output-4.txt', 'output-5.txt'])
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertEqual(self.queue.recover('linux'), [])
        self.assertEqual(self.queue.jobs('linux')[0], row)

    def test_recovery_separates_unlaunched_trial_but_charges_ambiguous_crash(self):
        self.queue.enqueue('linux', 'recover-before-launch', ['must-not-execute'], cwd=self.caller)
        _, unlaunched = self.queue.begin('linux')
        self.assertEqual(self.queue.recover('linux'), [])
        row = self.queue.jobs('linux')[0]
        self.assertEqual(row['attempts'], [])
        self.assertEqual(row['preexec_rejections'], [str(unlaunched / 'attempt.json')])
        preserved = (unlaunched / 'attempt.json').read_bytes()
        _, rejected = self.queue.begin('linux')
        perf_queue.atomic_json(rejected / 'attempt.json', {'phase': 'prepared', 'rejected_before_exec': True})
        self.queue.recover('linux')
        self.assertEqual(self.queue.jobs('linux')[0]['attempts'], [])
        self.assertTrue(json.loads((rejected / 'attempt.json').read_text())['rejected_before_exec'])
        for metadata in ({'phase': 'prepared', 'execution_started': True, 'execution_attempt': 1},
                         {'phase': 'starting'}, {'phase': 'starting'}):
            _, directory = self.queue.begin('linux')
            perf_queue.atomic_json(directory / 'attempt.json', metadata)
            self.assertEqual(self.queue.recover('linux'), [])
        row = self.queue.jobs('linux')[0]
        self.assertEqual(row['state'], 'exhausted-contended')
        self.assertEqual(len(row['attempts']), 3)
        self.assertEqual([Path(path).parent.name for path in row['attempts']], ['003', '004', '005'])
        self.assertEqual((unlaunched / 'attempt.json').read_bytes(), preserved)
        self.assertIsNone(self.queue.begin('linux'))

    def test_recovery_keeps_closed_rejection_after_crash_between_metadata_writes(self):
        job = self.queue.enqueue('linux', 'finish-crash', ['must-not-execute'], cwd=self.caller)
        _, directory = self.queue.begin('linux')
        receipt = directory / 'attempt.json'
        receipt.write_text('{"phase":"closed","contended":true,"returncode":null,"rejected_before_exec":true}')
        before = receipt.read_bytes()
        # Simulate the receipt landing before the matching atomic job update.
        perf_queue.atomic_json(directory.parents[1] / 'job.json', job)
        self.assertEqual(self.queue.recover('linux'), [])
        row = self.queue.jobs('linux')[0]
        self.assertEqual(row['state'], 'pending')
        self.assertEqual(row['attempts'], [])
        self.assertEqual(row['preexec_rejections'], [str(receipt)])
        self.assertEqual(self.queue.recover('linux'), [])
        self.assertEqual(self.queue.jobs('linux')[0], row)
        self.assertEqual(receipt.read_bytes(), before)
        # A crash after mkdir but before receipt creation also reserves its ordinal.
        (directory.parent / '002').mkdir()
        _, next_trial = self.queue.begin('linux')
        self.assertEqual(next_trial.name, '003')
        self.queue.recover('linux')
        self.assertEqual(receipt.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()

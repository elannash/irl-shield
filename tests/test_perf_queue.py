"""Public queue contracts use synthetic health and real files/subprocesses."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys
import time
import tempfile
import threading
import unittest
from unittest.mock import patch

from bench import perf_queue


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/perf-queue'
SCRATCH = Path('/tmp/agents/irl-shield/m1-perf-queue')


class QuietHealth:
    def sample(self, *, deadline, cancel=None, cpu_sampler=None):
        result = {'at': time.time(), 'idle_percent': 95., 'memory_ok': True, 'raw': {'fixture': 'quiet'}}
        if cpu_sampler is not None:
            result.update(total_busy_percent=5., job_tree_busy_percent=0., other_busy_percent=5.,
                          interval_seconds=.01, cpu_accounting_valid=True, cpu_accounting={'method': 'synthetic fixture'})
        return result


class OtherBusyPolicy(unittest.TestCase):
    def sample(self, total, job, seconds=10., **extra):
        return {'total_busy_percent': total, 'job_tree_busy_percent': job,
                'other_busy_percent': max(0., total - job), 'interval_seconds': seconds,
                'cpu_accounting_valid': True, 'memory_ok': True, **extra}

    def test_external_load_mean_max_and_missing_telemetry_fail_closed(self):
        clean = self.sample(50., 50.)
        self.assertFalse(perf_queue.contamination_summary([clean] * 3)['contended'])
        busy = perf_queue.contamination_summary([self.sample(87.5, 50.)] * 3)
        self.assertEqual(busy['mean_other_busy_percent'], 37.5)
        self.assertIn('other_busy', busy['reasons'])
        self.assertTrue(busy['contended'])
        self.assertFalse(perf_queue.contamination_summary([clean] * 3)['contended'])
        zero_work = perf_queue.contamination_summary([self.sample(25., 0.)])
        self.assertTrue(zero_work['contended'])
        spike = perf_queue.contamination_summary([self.sample(0., 0., 100.), self.sample(41., 0., 1.)])
        self.assertLess(spike['mean_other_busy_percent'], 20.)
        self.assertTrue(spike['contended'])
        self.assertEqual(spike['max_other_busy_percent'], 41.)
        for samples in ([], [self.sample(50., 50., cpu_accounting_valid=False)],
                        [self.sample(50., 50., memory_ok=False)]):
            with self.subTest(samples=samples):
                result = perf_queue.contamination_summary(samples)
                self.assertFalse(result['valid'])
                self.assertTrue(result['contended'])

    def process(self, pid, ppid, cpu, reaped=0., start=None, pgid=10):
        return {'pid': pid, 'ppid': ppid, 'pgid': pgid, 'session': pgid,
                'start': str(pid if start is None else start), 'cpu_seconds': cpu,
                'reaped_cpu_seconds': reaped, 'state': 'S'}

    def snapshot(self, at, *processes, host='linux'):
        return {'at': at, 'boot_ticks': 100 + int(at * 100), 'host': host, 'valid': True,
                'records': {process['pid']: process for process in processes}, 'errors': []}

    def test_linux_tree_ancestry_reaped_transfers_and_reuse_are_conservative(self):
        init = self.process(1, 0, 0., pgid=1)
        before = self.snapshot(0., init, self.process(10, 1, 1.), self.process(11, 10, 4.),
                               self.process(99, 1, 1000., pgid=10))
        after = self.snapshot(10., init, self.process(10, 1, 2.), self.process(11, 10, 6.),
                              self.process(99, 1, 1070., pgid=10))
        sampler = perf_queue.JobCPUSampler(10, host='linux', cpu_count=8)
        live = sampler.account(before, after)
        self.assertTrue(live['valid'])
        self.assertEqual(live['job_cpu_seconds'], 3.)
        self.assertEqual(live['job_tree_busy_percent'], 3.75)
        self.assertNotIn(99, live['after_member_pids'])
        reaped = self.snapshot(10., init, self.process(10, 1, 2., reaped=6.))
        result = perf_queue.JobCPUSampler(10, host='linux', cpu_count=8).account(before, reaped)
        self.assertEqual(result['job_cpu_seconds'], 3.)
        short_before = self.snapshot(0., init, self.process(10, 1, 1.))
        short = perf_queue.JobCPUSampler(10, host='linux', cpu_count=8).account(short_before, reaped)
        self.assertEqual(short['job_cpu_seconds'], 7.)
        nested = self.snapshot(0., init, self.process(10, 1, 1.), self.process(11, 10, 4., reaped=2.),
                               self.process(12, 11, 3.))
        nested_reaped = self.snapshot(10., init, self.process(10, 1, 2., reaped=13.))
        self.assertEqual(perf_queue.JobCPUSampler(10, host='linux', cpu_count=8).account(nested, nested_reaped)['job_cpu_seconds'], 5.)
        reused = self.snapshot(10., init, self.process(10, 1, 2.), self.process(11, 10, 500., start='reused'))
        self.assertFalse(perf_queue.JobCPUSampler(10, host='linux', cpu_count=8).account(before, reused)['valid'])
        missing = self.snapshot(10., init, self.process(10, 1, 2.), self.process(11, 777, 6.))
        self.assertFalse(perf_queue.JobCPUSampler(10, host='linux', cpu_count=8).account(before, missing)['valid'])
        self.assertFalse(perf_queue.JobCPUSampler(10, host='linux', cpu_count=8).account(before, self.snapshot(10., init))['valid'])
        fields = ['0'] * 22
        fields[0:4] = ['S', '1', '10', '10']
        for index, value in ((11, '100'), (12, '20'), (13, '30'), (14, '10'), (19, '1000')):
            fields[index] = value
        parsed = perf_queue.linux_process_stat('10 (worker with) name) ' + ' '.join(fields), 100)
        self.assertEqual((parsed['cpu_seconds'], parsed['reaped_cpu_seconds'], parsed['start']), (1.2, .4, '1000'))

    def test_mac_ps_times_and_stable_identity_lower_bound_exclude_short_and_foreign_children(self):
        rows = perf_queue.mac_process_rows('10 1 10 1:00.50 Fri Oct 30 02:00:00 2026\n')
        self.assertEqual(rows[10]['cpu_seconds'], 60.5)
        self.assertEqual(perf_queue.cpu_time_seconds('1-02:03:04.50'), 93784.5)
        init = self.process(1, 0, 0., pgid=1)
        before = self.snapshot(0., init, self.process(10, 1, 1.), self.process(11, 10, 2.),
                               self.process(99, 1, 100., pgid=99), host='mac')
        after = self.snapshot(10., init, self.process(10, 1, 2.), self.process(11, 10, 4.),
                              self.process(12, 10, 100.), self.process(99, 1, 150., pgid=99), host='mac')
        result = perf_queue.JobCPUSampler(10, host='mac', cpu_count=8).account(before, after)
        self.assertTrue(result['valid'])
        self.assertEqual(result['job_cpu_seconds'], 3.)
        self.assertEqual(result['attributed_pids'], [10, 11])
        after['records'][11]['start'] = 'PID reused'
        reused = perf_queue.JobCPUSampler(10, host='mac', cpu_count=8).account(before, after)
        self.assertEqual(reused['job_cpu_seconds'], 1.)
        self.assertEqual(reused['attributed_pids'], [10])

    @unittest.skipUnless(sys.platform == 'linux', 'Real procfs integration is Linux-only; Mac uses its native proof')
    def test_real_short_tree_partial_window_attributes_only_its_descendants(self):
        job = subprocess.Popen([sys.executable, '-c', 'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c","import time; time.sleep(3)"]); time.sleep(3)'], start_new_session=True)
        foreign = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(3)'], start_new_session=True)
        cancel = threading.Event()
        timer = threading.Timer(.15, cancel.set)
        timer.start()
        try:
            sampler = perf_queue.JobCPUSampler(job.pid, host='linux')
            sample = perf_queue.SystemHealth('linux').sample(cpu_sampler=sampler, deadline=time.time() + 2, cancel=cancel)
            self.assertTrue(sample['partial_cpu_window'])
            self.assertTrue(sample['cpu_accounting_valid'], sample)
            self.assertGreater(sample['interval_seconds'], 0.)
            self.assertLess(sample['interval_seconds'], 2.)
            self.assertIn(job.pid, sample['cpu_accounting']['attributed_pids'])
            self.assertNotIn(foreign.pid, sample['cpu_accounting']['attributed_pids'])
        finally:
            timer.cancel()
            for process in (job, foreign):
                if process.poll() is None:
                    os.killpg(process.pid, __import__('signal').SIGKILL)
                process.wait(timeout=2)

    def test_mac_cancelled_partial_uses_kernel_ticks_and_keeps_normal_memory(self):
        self.assertEqual(perf_queue.mac_ticks_idle([100, 0, 100, 0], [140, 0, 140, 0]), 50.)
        self.assertEqual(perf_queue.mac_ticks_idle([2**32 - 5, 0, 100, 0], [5, 0, 110, 0]), 50.)
        with self.assertRaises(ValueError):
            perf_queue.mac_ticks_idle([1, 2, 3, 4], [1, 2, 3, 4])
        ticks = iter(([100, 0, 100, 0], [140, 0, 140, 0]))
        calls = []
        def command(argv, deadline, cancel=None):
            calls.append(argv)
            if argv == ['memory_pressure', '-Q']:
                text = 'System-wide memory free percentage: 70%\n'
            elif argv[-1] == 'kern.memorystatus_vm_pressure_level':
                text = 'kern.memorystatus_vm_pressure_level: 1\n'
            elif argv[-1] == 'vm.swapusage':
                text = 'vm.swapusage: total = 0.00M used = 0.00M free = 0.00M\n'
            else:
                raise AssertionError('Partial job sampling must not call top')
            return {'argv': argv, 'stdout': text, 'stderr': '', 'returncode': 0, 'interrupted': False}
        root1 = self.process(10, 1, 1.)
        root2 = self.process(10, 1, 1.4)
        snapshots = iter((self.snapshot(0., root1, host='mac'), self.snapshot(.1, root2, host='mac')))
        class Counters(perf_queue.JobCPUSampler):
            def snapshot(inner, **options):
                return next(snapshots)
        sampler = Counters(10, host='mac', cpu_count=8)
        cancel = threading.Event()
        cancel.set()
        with patch('bench.perf_queue.platform.system', return_value='Darwin'):
            health = perf_queue.SystemHealth('mac', mac_ticks_reader=lambda: next(ticks), command_reader=command)
        sample = health.sample(cpu_sampler=sampler, deadline=time.time() + 2, cancel=cancel)
        self.assertTrue(sample['partial_cpu_window'])
        self.assertTrue(sample['memory_ok'], sample)
        self.assertTrue(sample['cpu_accounting_valid'], sample)
        self.assertEqual(sample['total_busy_percent'], 50.)
        self.assertAlmostEqual(sample['job_tree_busy_percent'], 50.)
        self.assertLess(sample['interval_seconds'], 1.)
        self.assertFalse(perf_queue.contamination_summary([sample])['contended'])
        self.assertEqual(len(calls), 3)


class PerformanceQueue(unittest.TestCase):
    def setUp(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        self.folder = tempfile.TemporaryDirectory(dir=SCRATCH)
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name).resolve()
        self.storage = self.root / 'queue'
        self.caller = self.root / 'caller'
        self.caller.mkdir()

    def cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), '--queue-dir', str(self.storage), *args],
                              cwd=self.caller, text=True, capture_output=True)

    def test_enqueue_preserves_caller_directory_and_options_after_job_before_separator(self):
        result = self.cli('enqueue', 'linux', 'literal-job', '--lane', 'experiment-a', '--priority', '2',
                          '--receipt', '{job_dir}/result-{attempt}.json', '--',
                          sys.executable, '-c', 'print("$(not a shell)")')
        self.assertEqual(result.returncode, 0, result.stderr)
        job = json.loads(result.stdout)
        self.assertEqual(job['cwd'], str(self.caller))
        self.assertEqual((job['host'], job['lane'], job['priority']), ('linux', 'experiment-a', 2))
        self.assertEqual(job['argv'][-1], 'print("$(not a shell)")')
        self.assertEqual(job['receipts'], ['{job_dir}/result-{attempt}.json'])
        status = self.cli('status')
        self.assertEqual(status.returncode, 0, status.stderr)
        persisted = json.loads(status.stdout)['linux']['jobs'][0]
        self.assertEqual(persisted, job)
        self.assertEqual(list(self.storage.rglob('*.tmp')), [])

    def test_sensor_parsers_use_second_mac_sample_and_eight_linux_counters(self):
        top = 'CPU usage: 90.00% user, 5.00% sys, 5.00% idle\nCPU usage: 10.00% user, 4.50% sys, 85.50% idle\n'
        self.assertEqual(perf_queue.mac_idle(top), 85.5)
        with self.assertRaises(ValueError):
            perf_queue.mac_idle(top.splitlines()[0])
        before = 'cpu 100 10 20 800 50 5 5 10 90 9\ncpu0 0 0 0 0\n'
        after = 'cpu 110 10 25 880 55 5 5 10 1090 1009\n'
        self.assertEqual(perf_queue.linux_idle(before, after), 80.)
        free = '              total used free shared buff/cache available\nMem: 16000000000 1 2 3 4 4294967296\nSwap: 900 200 700\n'
        self.assertEqual(perf_queue.free_memory(free), {'available_bytes': 4294967296, 'swap_total_bytes': 900, 'swap_used_bytes': 200})
        self.assertTrue(perf_queue.ready({'idle_percent': 80., 'memory_ok': True}))
        self.assertFalse(perf_queue.ready({'idle_percent': 79.99, 'memory_ok': True}))
        self.assertFalse(perf_queue.ready({'idle_percent': 99., 'memory_ok': False}))

    def runner(self, queue, **options):
        settings = dict(sensor=QuietHealth(), perf_lock=self.root / 'perf.lock', readiness_period=.01,
                        sample_period=.01, force_at=time.time() + 60, hard_stop=time.time() + 10)
        settings.update(options)
        return perf_queue.Runner(queue, 'linux', **settings)

    def until(self, condition, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(.01)
        self.fail('Required subprocess/file condition did not become true')

    def test_runner_orders_priorities_executes_literal_subprocess_and_retains_unique_receipt(self):
        queue = perf_queue.Queue(self.storage)
        code = 'from pathlib import Path; import os,sys; Path(sys.argv[1]).write_text(os.getcwd()); print("literal $(safe)"); print("stderr receipt",file=sys.stderr)'
        lane = queue.enqueue('linux', 'lane', [sys.executable, '-c', code, '{job_dir}/result-{attempt}.txt'],
                             cwd=self.caller, lane='lane-a', receipts=['{job_dir}/result-{attempt}.txt'])
        root = queue.enqueue('linux', 'root', [sys.executable, '-c', 'print("root")'], cwd=self.caller)
        failed = queue.enqueue('linux', 'nonzero', [sys.executable, '-c', 'import sys; print("failure receipt",file=sys.stderr); sys.exit(7)'], cwd=self.caller)
        queue.seal('linux')
        self.runner(queue).run()
        rows = {row['id']: row for row in queue.status('linux')['linux']['jobs']}
        self.assertEqual(rows[lane['id']]['state'], 'completed')
        self.assertEqual(rows[root['id']]['state'], 'completed')
        a = json.loads(Path(rows[lane['id']]['attempts'][0]).read_text())
        b = json.loads(Path(rows[root['id']]['attempts'][0]).read_text())
        self.assertLess(b['started_at'], a['started_at'])
        self.assertEqual(a['returncode'], 0)
        self.assertEqual(Path(a['receipts'][0]['path']).read_text(), str(self.caller))
        self.assertTrue(a['receipts'][0]['exists'])
        self.assertIn('literal $(safe)', Path(a['stdout']).read_text())
        self.assertIn('stderr receipt', Path(a['stderr']).read_text())
        self.assertFalse(a['contended'])
        self.assertEqual(a['benchmark_verdict'], 'unassessed')
        bad = rows[failed['id']]
        self.assertEqual(bad['state'], 'failed')
        self.assertEqual(json.loads(Path(bad['attempts'][0]).read_text())['returncode'], 7)

    def test_perl_flock_lease_survives_acquirer_exit_and_singleton_is_separate(self):
        path = self.root / 'perf.lock'
        contender = ['perl', '-MFcntl=:flock', '-e', 'open my $f,"+<",$ARGV[0] or die $!; exit(flock($f,LOCK_EX|LOCK_NB)?0:75)', str(path)]
        with perf_queue.PerlLease(path):
            self.assertEqual(subprocess.run(contender).returncode, 75)
        self.assertEqual(subprocess.run(contender).returncode, 0)
        queue = perf_queue.Queue(self.storage)
        queue.seal('linux')
        with perf_queue.file_lock(queue.host_dir('linux') / 'runner.lock'):
            with self.assertRaises(BlockingIOError):
                self.runner(queue).run()

    def test_contention_retries_at_back_of_priority_and_stops_after_three_attempts(self):
        queue = perf_queue.Queue(self.storage)
        busy, sampled, order = self.root / 'busy', self.root / 'sampled', self.root / 'order'
        class LoadWindow:
            def sample(inner, *, deadline, cancel=None, cpu_sampler=None):
                idle = 40. if busy.exists() else 95.
                result = QuietHealth().sample(deadline=deadline, cancel=cancel, cpu_sampler=cpu_sampler)
                result['idle_percent'] = idle
                if cpu_sampler is not None:
                    result.update(total_busy_percent=100 - idle, other_busy_percent=100 - idle)
                    if idle == 40.:
                        sampled.write_text('busy window observed')
                return result
        # Keep the synthetic busy window open until observed, even if the host
        # schedules the monitor after a short foreground command would exit.
        code = ('from pathlib import Path; import sys,time; busy=Path(sys.argv[1]); '
                'sampled=Path(sys.argv[4]); sampled.unlink(missing_ok=True); busy.write_text("busy"); '
                'f=Path(sys.argv[2]).open("a"); f.write("A"+sys.argv[3]+"\\n"); f.close(); '
                'deadline=time.monotonic()+3\n'
                'while not sampled.exists() and time.monotonic()<deadline: time.sleep(.005)\n'
                'if not sampled.exists(): raise RuntimeError("Busy window was never sampled")\n'
                'busy.unlink()')
        a = queue.enqueue('linux', 'contended', [sys.executable, '-c', code, str(busy), str(order), '{attempt}', str(sampled)],
                          cwd=self.caller, lane='a')
        queue.enqueue('linux', 'quiet', [sys.executable, '-c', 'from pathlib import Path; import sys; f=Path(sys.argv[1]).open("a"); f.write("B1\\n"); f.close()', str(order)], cwd=self.caller, lane='b')
        queue.seal('linux')
        runner = self.runner(queue, hard_stop=time.time() + 60)
        runner.sensor = LoadWindow()
        runner.run()
        row = next(job for job in queue.status('linux')['linux']['jobs'] if job['id'] == a['id'])
        self.assertEqual(row['state'], 'exhausted-contended')
        self.assertEqual(len(row['attempts']), 3)
        self.assertEqual(order.read_text().splitlines(), ['A1', 'B1', 'A2', 'A3'])
        self.assertTrue(all(json.loads(Path(path).read_text())['contended'] for path in row['attempts']))
        self.assertTrue(all(json.loads(Path(path).read_text())['returncode'] == 0 for path in row['attempts']))

    def test_crashed_attempt_is_retained_and_retried_without_signaling_a_reused_identity(self):
        queue = perf_queue.Queue(self.storage)
        job = queue.enqueue('linux', 'recover', [sys.executable, '-c', 'from pathlib import Path; import sys; Path(sys.argv[1]).write_text("recovered")', '{job_dir}/result-{attempt}.txt'], cwd=self.caller)
        claimed, directory = queue.begin('linux')
        identity = perf_queue.process_identity(__import__('os').getpid())
        identity['started'] = 'a different process start time'
        perf_queue.atomic_json(directory / 'child.json', identity)
        queue.seal('linux')
        self.runner(queue).run()
        row = queue.status('linux')['linux']['jobs'][0]
        self.assertEqual(row['state'], 'completed')
        self.assertEqual(len(row['attempts']), 2)
        old = json.loads(Path(row['attempts'][0]).read_text())
        self.assertTrue(old['recovered_after_runner_crash'])
        self.assertTrue(old['contended'])
        self.assertIn('unavailable', old['end_health'])
        self.assertIsNone(old['returncode'])
        self.assertEqual((self.storage / 'linux/jobs' / job['id'] / 'result-2.txt').read_text(), 'recovered')

    def test_new_policy_subtracts_self_load_ignores_end_idle_and_preserves_legacy_attempts(self):
        queue = perf_queue.Queue(self.storage)
        finished = self.root / 'finished'
        class SelfBusy:
            def sample(inner, *, deadline, cancel=None, cpu_sampler=None):
                if cpu_sampler is not None:
                    return {'idle_percent': 50., 'memory_ok': True, 'total_busy_percent': 50.,
                            'job_tree_busy_percent': 50., 'other_busy_percent': 0., 'interval_seconds': .01,
                            'cpu_accounting_valid': True, 'cpu_accounting': {'method': 'synthetic self-load fixture'}}
                return {'idle_percent': 50. if finished.exists() else 95., 'memory_ok': True}
        job = queue.enqueue('linux', 'cpu', [sys.executable, '-c', 'from pathlib import Path; import sys,time; time.sleep(.05); Path(sys.argv[1]).write_text("done")', str(finished)], cwd=self.caller)
        old = []
        for _ in range(2):
            claimed, directory = queue.begin('linux')
            queue.finish(claimed, directory, {'phase': 'closed', 'returncode': 0, 'contended': True,
                                             'historical_label': 'legacy idle <60', 'end_health': {'idle_percent': 50.}})
            old.append(((directory / 'attempt.json'), (directory / 'attempt.json').read_bytes()))
        queue.seal('linux')
        self.runner(queue, sensor=SelfBusy()).run()
        row = queue.jobs('linux')[0]
        self.assertEqual(row['state'], 'completed')
        self.assertEqual(len(row['attempts']), 3)
        for path, content in old:
            self.assertEqual(path.read_bytes(), content)
        attempt = json.loads(Path(row['attempts'][-1]).read_text())
        self.assertEqual(attempt['contamination_policy'], 'other-busy-v2')
        self.assertFalse(attempt['contended'])
        self.assertEqual(attempt['contamination']['mean_other_busy_percent'], 0.)
        self.assertEqual(attempt['end_health']['idle_percent'], 50.)

    def test_final_partial_external_window_is_retained_before_watchdog_ack(self):
        queue = perf_queue.Queue(self.storage)
        class LateExternal:
            def sample(inner, *, deadline, cancel=None, cpu_sampler=None):
                if cpu_sampler is None:
                    return {'idle_percent': 95., 'memory_ok': True}
                began = time.monotonic()
                cancel.wait(.5)
                alive = perf_queue.process_identity(cpu_sampler.root_pid) is not None
                return {'idle_percent': 5., 'memory_ok': True, 'total_busy_percent': 95.,
                        'job_tree_busy_percent': 50., 'other_busy_percent': 45.,
                        'interval_seconds': time.monotonic() - began, 'cpu_accounting_valid': alive,
                        'partial_cpu_window': True, 'cpu_accounting': {'root_alive_during_final_sample': alive}}
        queue.enqueue('linux', 'late-window', [sys.executable, '-c', 'import time; time.sleep(.05)'], cwd=self.caller)
        queue.seal('linux')
        self.runner(queue, sensor=LateExternal()).run()
        row = queue.jobs('linux')[0]
        self.assertEqual(row['state'], 'exhausted-contended')
        for path in row['attempts']:
            attempt = json.loads(Path(path).read_text())
            self.assertEqual(attempt['contamination']['max_other_busy_percent'], 45.)
            self.assertIn('other_busy', attempt['contamination']['reasons'])
            self.assertTrue(all(sample['cpu_accounting_valid'] and sample['cpu_accounting']['root_alive_during_final_sample']
                                for sample in attempt['periodic_health']))
            directory = Path(path).parent
            self.assertTrue((directory / 'sampling-complete.json').exists())
            self.assertLessEqual((directory / 'command-exit.json').stat().st_mtime,
                                 (directory / 'sampling-complete.json').stat().st_mtime)

    def test_malformed_cpu_and_free_files_are_rejected_and_concurrent_enqueues_do_not_collide(self):
        before = self.root / 'before.stat'
        after = self.root / 'after.stat'
        bad_free = self.root / 'free.txt'
        before.write_text('cpu 10 20 30 40 50 60 70 80 90 100\n')
        after.write_text('cpu 9 20 30 40 50 60 70 80 90 100\n')
        bad_free.write_text('Mem: 100 1 2 3 4 not-a-byte-count\nSwap: 10 1 9\n')
        with self.assertRaises(ValueError):
            perf_queue.linux_idle(before.read_text(), after.read_text())
        with self.assertRaises(ValueError):
            perf_queue.free_memory(bad_free.read_text())
        with self.assertRaises(ValueError):
            perf_queue.linux_idle('cpu 1 2\n', after.read_text())
        queue = perf_queue.Queue(self.storage)
        with ThreadPoolExecutor(max_workers=4) as workers:
            jobs = list(workers.map(lambda n: queue.enqueue('linux', str(n), [sys.executable, '-c', 'pass'], cwd=self.caller), range(16)))
        self.assertEqual(len({row['id'] for row in jobs}), 16)
        self.assertEqual(sorted(row['order'] for row in queue.jobs('linux')), list(range(1, 17)))
        queue.seal('linux')
        with self.assertRaisesRegex(ValueError, 'sealed'):
            queue.enqueue('linux', 'late', ['true'], cwd=self.caller)

    def test_unsealed_producer_wait_and_stop_leave_reused_metadata_and_unowned_child_untouched(self):
        queue = perf_queue.Queue(self.storage)
        unrelated = subprocess.Popen([sys.executable, '-c', 'import sys; sys.stdin.buffer.read()'],
                                     stdin=subprocess.PIPE, start_new_session=True)
        driver = None
        try:
            identity = perf_queue.process_identity(unrelated.pid)
            identity['started'] = 'stale reused PID identity'
            perf_queue.atomic_json(queue.host_dir('linux') / 'runner.json', {'pid': unrelated.pid, 'identity': identity, 'state': 'stale'})
            self.assertEqual(self.cli('stop', 'linux').returncode, 0)
            self.assertIsNone(unrelated.poll())
            self.assertFalse(queue.status('linux')['linux']['runner']['identity_matches'])
            runner = self.runner(queue, hard_stop=time.time() + 60)
            outcomes = []
            driver = threading.Thread(target=lambda: outcomes.append(runner.run()), daemon=True)
            driver.start()
            self.until(lambda: queue.status('linux')['linux']['runner']['state'] == 'waiting-for-producers', timeout=30)
            marker = self.root / 'started'
            queue.enqueue('linux', 'stop-me', [sys.executable, '-c', 'from pathlib import Path; import os,sys,threading; Path(sys.argv[1]).write_text(str(os.getpid())); threading.Event().wait()', str(marker)], cwd=self.caller)
            queue.seal('linux')
            self.until(marker.exists, timeout=30)
            self.assertEqual(self.cli('stop', 'linux').returncode, 0)
            self.until(lambda: not driver.is_alive(), timeout=30)
            driver.join()
            self.assertFalse(driver.is_alive())
            self.assertEqual(outcomes, ['stop-requested'])
            self.assertIsNone(perf_queue.process_identity(int(marker.read_text())))
            self.assertIsNone(unrelated.poll())
        finally:
            queue.stop('linux')
            if driver is not None:
                driver.join(10)
            if unrelated.poll() is None:
                unrelated.terminate()
            unrelated.stdin.close()
            unrelated.wait(timeout=5)

    def test_forced_jobs_receive_queue_context_and_hard_deadline_stops_only_owned_group(self):
        queue = perf_queue.Queue(self.storage)
        class Busy:
            def sample(self, *, deadline, cancel=None, cpu_sampler=None):
                result = QuietHealth().sample(deadline=deadline, cancel=cancel, cpu_sampler=cpu_sampler)
                result.update(idle_percent=10., memory_ok=False)
                if cpu_sampler is not None:
                    result.update(total_busy_percent=90., other_busy_percent=90.)
                return result
        code = 'from pathlib import Path; import os,sys,json; keys=["FORCED","ATTEMPT","RECEIPT","LEASE_FD"]; d={k:os.environ["IRL_SHIELD_PERF_QUEUE_"+k] for k in keys}; d["lease_inode"]=os.fstat(int(d["LEASE_FD"])).st_ino; Path(sys.argv[1]).write_text(json.dumps(d))'
        job = queue.enqueue('linux', 'forced', [sys.executable, '-c', code, '{job_dir}/env-{attempt}.json'], cwd=self.caller)
        queue.seal('linux')
        self.assertEqual(self.runner(queue, sensor=Busy(), force_at=time.time() - 1).run(), 'drained')
        row = queue.status('linux')['linux']['jobs'][0]
        self.assertEqual(row['state'], 'exhausted-contended')
        for index, path in enumerate(row['attempts'], 1):
            data = json.loads((self.storage / 'linux/jobs' / job['id'] / f'env-{index}.json').read_text())
            self.assertEqual((data['FORCED'], data['ATTEMPT'], data['RECEIPT']), ('1', str(index), path))
            self.assertEqual(data['lease_inode'], (self.root / 'perf.lock').stat().st_ino)
        queue.seal('linux', False)
        marker = self.root / 'deadline-child'
        hard = queue.enqueue('linux', 'deadline', [sys.executable, '-c', 'from pathlib import Path; import os,sys,time; Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(5)', str(marker)], cwd=self.caller)
        queue.seal('linux')
        deadline = time.time() + .8
        self.assertEqual(self.runner(queue, hard_stop=deadline).run(), 'hard-stop')
        self.assertLess(time.time(), deadline + .5)
        self.assertTrue(marker.exists())
        self.assertIsNone(perf_queue.process_identity(int(marker.read_text())))
        attempt = next(row for row in queue.jobs('linux') if row['id'] == hard['id'])['attempts'][0]
        self.assertEqual(json.loads(Path(attempt).read_text())['stop_reason'], 'hard-stop')

    def test_watchdog_retains_lease_and_hard_stop_after_runner_process_crashes(self):
        queue = perf_queue.Queue(self.storage)
        marker = self.root / 'orphan-command'
        job = queue.enqueue('linux', 'orphan', [sys.executable, '-c', 'from pathlib import Path; import os,sys,time; Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(5)', str(marker)], cwd=self.caller)
        queue.seal('linux')
        helper = 'from bench.perf_queue import Queue,Runner\nfrom pathlib import Path\nimport sys,time\nclass H:\n def sample(self,**kw): return {"idle_percent":95.,"memory_ok":True}\nRunner(Queue(sys.argv[1]),"linux",sensor=H(),perf_lock=Path(sys.argv[2]),readiness_period=.01,sample_period=.01,force_at=time.time()+60,hard_stop=time.time()+2).run()\n'
        parent = subprocess.Popen([sys.executable, '-c', helper, str(self.storage), str(self.root / 'perf.lock')],
                                  cwd=self.caller, env=os.environ | {'PYTHONPATH': str(SCRIPT.parents[1])},
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            child_json = self.storage / 'linux/jobs' / job['id'] / 'attempts/001/child.json'
            self.until(lambda: marker.exists() and child_json.exists())
            worker = json.loads(child_json.read_text())
            parent.kill()
            parent.wait(timeout=2)
            with self.assertRaises(BlockingIOError):
                with perf_queue.PerlLease(self.root / 'perf.lock'):
                    pass
            self.until(lambda: perf_queue.process_identity(worker['pid']) is None, timeout=4)
            self.assertIsNone(perf_queue.process_identity(int(marker.read_text())))
            with perf_queue.PerlLease(self.root / 'perf.lock'):
                pass
            self.assertEqual(queue.recover('linux'), [])
            self.assertTrue(json.loads(Path(queue.jobs('linux')[0]['attempts'][0]).read_text())['recovered_after_runner_crash'])
        finally:
            queue.stop('linux')
            if parent.poll() is None:
                parent.kill()
            parent.wait(timeout=2)


if __name__ == '__main__':
    unittest.main()

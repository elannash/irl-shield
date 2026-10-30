"""Evidence accounting contracts; no GPU, natural media or elapsed-time assertions."""
import json
from pathlib import Path
import tempfile
import unittest
import socket
import threading
import sys
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import ExitStack

from bench.efficiency.profile import Ledger, Profiler, summarize
from bench.efficiency.job import PreflightError, preflight_runtime, run_job, verify_sources


class EfficiencyTests(unittest.TestCase):
    def collect_fixture(self, mode='success', startup=23.):
        """Fake only native/process/clock boundaries; execute real run_job collection."""
        import bench.efficiency.job as job
        state = SimpleNamespace(now=0., profiler=None, first=None, output=None, events=[])
        class Process:
            def __init__(self, target, args, name):
                self.pid = 1001 if name == 'w11-sender' else 1002
                self.exitcode = 0
                self.name = name
                if name == 'w11-observer' and len(args) > 3:
                    state.first = args[3]
            def start(self): pass
        class Capture:
            def __init__(self, start, end, **kwargs):
                self.ledger = SimpleNamespace(start=start, end=end)
                state.profiler = self
            def start(self): pass
            def close(self, directory, role):
                for owner in ('relay', 'encoder'):
                    data = {'pid': 1003 if owner == 'encoder' else 1000, 'role': owner,
                            'rows': [{'stage': s, 'window': 'steady', 'start': startup + 20., 'end': startup + 20.01,
                                      'wall_seconds': .01, 'caller_cpu_seconds': .001}
                                     for s in ('decode', 'colorconvert', 'resize', 'detector-pre', 'detector-infer',
                                               'detector-post', 'tracking', 'maskrender', 'encode', 'mux', 'ipc-copies')],
                            'source_frames': [e for e in state.events if e['kind'] == 'source'],
                            'evidence': state.events if owner == 'relay' else [],
                            'ipc_payloads': [], 'errors': ['synthetic-error'] if mode == 'instrumentation-error' else [],
                            'unfinished_spans': int(mode == 'unfinished-span'), 'worker_completed': True}
                    if mode != 'missing-encoder' or owner != 'encoder':
                        job.write(Path(directory) / ('spans-' + owner + '-synthetic.json'), data)
        def runtime(engine, address, phone, internal, directory, stopped, **kwargs):
            def emit(kind, at, **fields):
                state.now = at
                event = {'kind': kind, 'at': at, **fields}
                state.events.append(event)
                if hasattr(stopped, 'observe'):
                    stopped.observe(event)
            emit('source', startup - 3, pts=0., generation=1)
            for lane in ('fast', 'accurate'):
                emit('detector', startup - 2, lane=lane, inference_completed=True, index=1, pts=1 / 30)
            emit('encoded', startup - 1, index=1, pts=1 / 30, generation=1, state='HOLD', slate=True)
            if state.first is not None:
                state.first.value = startup
            state.now = startup
            stopped.is_set()
            for offset in (16., 45., 90., 134., 135.):
                if mode == 'early-stop' and offset > 16:
                    break
                at = startup + offset
                if mode not in ('no-source', 'all-slate', 'startup-only'):
                    emit('source', at, pts=offset, generation=1)
                if mode not in ('no-detector', 'all-slate', 'startup-only'):
                    for lane in ('fast', 'accurate'):
                        emit('detector', at, lane=lane, inference_completed=True, index=round(offset * 30), pts=offset)
                if mode != 'no-encoded':
                    emit('encoded', at, index=round(offset * 30), pts=offset, generation=1,
                         state='HOLD' if mode in ('all-slate', 'startup-only') else 'LIVE', slate=mode in ('all-slate', 'startup-only'))
                state.now = at
                stopped.is_set()
            now = state.now
            emit('encoder-exit', now, pid=1003, exitcode=0, alive=False)
            frames = [{'index': round((at - startup) * 30), 'at': at} for at in (startup + 16, now)]
            job.write(state.output / 'sender.json', {'status': 'closed', 'frames': frames})
            if mode != 'missing-observer':
                job.write(state.output / 'observer.json', {'status': 'eof' if mode.startswith('observer-eof-') else 'closed',
                    'finished_at': now - 100 if mode == 'observer-eof-early' else now,
                    'frames': [] if mode in ('no-observer', 'startup-only') else
                              [{'at': f['at'], 'pts': f['index'] / 30, 'all_dark': False, 'spatial_std': 30.} for f in frames],
                    'errors': []})
            return {'status': 'stopped', 'output_frames': 3, 'cleanup_errors': [], 'engine': {'lanes': {}}}
        def stop(process, event, name, receipts):
            receipts.append({'role': name, 'pid': process.pid, 'exitcode': 9 if mode == 'bad-process' else 0,
                             'alive': False, 'forced': False})
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            folder = Path(temporary)
            sources = folder / 'sources.json'
            sources.write_text('{}')
            state.output = folder / 'output'
            args = SimpleNamespace(sources=sources, output=state.output, instrument=True,
                mediamtx_dir=folder, model_cache=folder, warmup=15., startup_timeout=180.,
                launcher_receipt=folder / 'launcher.json', launcher_sha256='synthetic')
            context = SimpleNamespace(Event=threading.Event, Process=Process,
                Array=lambda *a, **kw: list(a[1]), Value=lambda *a, **kw: SimpleNamespace(value=a[1]))
            server = SimpleNamespace(process=SimpleNamespace(pid=1004, returncode=-15, poll=lambda: -15))
            patches = {'relay.soak.require_queue_lease': lambda: {'synthetic': True},
                'bench.efficiency.job.require_root_launcher': lambda *a: {'synthetic': True},
                'bench.efficiency.job.preflight_runtime': lambda: {}, 'bench.efficiency.job.check_ports': lambda: None,
                'bench.efficiency.job.signal.signal': lambda *a: None,
                'bench.efficiency.job.time.monotonic': lambda: state.now,
                'bench.efficiency.job.mp.get_context': lambda *a: context,
                'bench.efficiency.job.stop': stop, 'bench.efficiency.profile.Profiler': Capture,
                'relay.mediamtx.verified_binary': lambda *a: Path(__file__),
                'models.prepare.verified_path': lambda *a: (Path(__file__), {}),
                'importlib.metadata.version': lambda *a: 'synthetic-test',
                'relay.runtime.make_engine': lambda *a, **kw: SimpleNamespace(close=lambda: None), 'relay.runtime.run': runtime}
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement, create=True))
            stack.enter_context(patch('relay.mediamtx.MediaMTX')).return_value.__enter__.return_value = server
            sampler = stack.enter_context(patch('bench.efficiency.telemetry.HostSamples')).return_value
            sampler.close.side_effect = lambda path: job.write(path, {'rows': [{'at': state.now, 'processes': [{'pid': 1000}]}]})
            error = None
            try:
                run_job(args)
            except RuntimeError as caught:
                error = caught
            report = json.loads((state.output / 'profile.json').read_text())
        return error, report

    def test_collector_rejects_startup_only_black_output(self):
        error, report = self.collect_fixture('startup-only')
        self.assertIsNotNone(error, 'Black startup output alone must fail real collection boundary')
        self.assertEqual(report['status'], 'failed')

    def test_collector_requires_all_steady_populations_and_capture_success(self):
        for mode in ('all-slate', 'no-source', 'no-detector', 'no-encoded', 'no-observer', 'missing-observer',
                     'missing-encoder', 'bad-process', 'instrumentation-error', 'unfinished-span', 'early-stop', 'observer-eof-early'):
            with self.subTest(mode=mode):
                error, report = self.collect_fixture(mode)
                self.assertIsNotNone(error, mode)
                self.assertEqual(report['status'], 'failed')
                self.assertTrue(report['collection_failures'], mode)

    def test_delayed_readiness_precedes_actual_warmup_and_complete_steady_window(self):
        error, report = self.collect_fixture(startup=43.)
        self.assertIsNone(error)
        self.assertEqual(report['status'], 'collected-ungraded')
        self.assertEqual(report['phases']['pipeline_ready'], 43.)
        self.assertEqual(report['phases']['steady_start'], 58.)
        self.assertEqual(report['phases']['steady_end'], 178.)
        self.assertEqual(report['measurement_seconds'], 120.)
        self.assertGreater(report['populations']['encoded_live']['count'], 0)
        self.assertIsNone(report['quality_scorecard'])

    def test_early_stop_reports_only_the_observed_steady_second(self):
        error, report = self.collect_fixture('early-stop', startup=43.)
        self.assertIsNotNone(error)
        self.assertFalse(report['steady_completed'])
        self.assertEqual(report['measurement_seconds'], 1.)
        self.assertEqual(report['actual_warmup_seconds'], 15.)
        self.assertEqual(report['phases']['steady_start'], 58.)
        self.assertEqual(report['phases']['steady_end'], 59.)

    def test_observer_eof_after_window_is_expected_native_writer_cleanup(self):
        error, report = self.collect_fixture('observer-eof-after-window')
        self.assertIsNone(error)
        self.assertEqual(report['status'], 'collected-ungraded')

    def test_job_installs_hook_before_engine_worker_construction(self):
        observed = []
        def engine_boundary(*args, **kwargs):
            observed.append(sys.getprofile() is not None)
            raise RuntimeError('synthetic engine boundary stop')
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            sources = folder / 'sources.json'
            sources.write_text('{}')
            args = SimpleNamespace(sources=sources, output=folder / 'output', instrument=True,
                                   mediamtx_dir=folder, model_cache=folder, warmup=15., startup_timeout=180.)
            with patch('relay.soak.require_queue_lease', return_value={'test': True}), \
                 patch('bench.efficiency.job.require_root_launcher', return_value={'synthetic': True}), \
                 patch('bench.efficiency.job.preflight_runtime', return_value={}), \
                 patch('bench.efficiency.job.check_ports'), \
                 patch('bench.efficiency.job.signal.signal'), \
                 patch('relay.mediamtx.MediaMTX') as media, \
                 patch('relay.mediamtx.verified_binary', return_value=Path(__file__)), \
                 patch('models.prepare.verified_path', return_value=(Path(__file__), {})), \
                 patch('bench.efficiency.telemetry.HostSamples'), \
                 patch('importlib.metadata.version', return_value='synthetic-test'), \
                 patch('relay.runtime.make_engine', side_effect=engine_boundary):
                media.return_value.__enter__.return_value.process = SimpleNamespace(pid=2000, returncode=-15, poll=lambda: -15)
                with self.assertRaisesRegex(RuntimeError, 'Profile incomplete'):
                    run_job(args)
            report = json.loads((args.output / 'profile.json').read_text())
        self.assertEqual(observed, [True])
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['source_frames'], 0)
        self.assertIsNone(report['performance_claim'])

    def test_missing_cuda_launcher_env_fails_before_runtime_imports(self):
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaisesRegex(PreflightError, 'missing-required-env: LD_LIBRARY_PATH'):
                preflight_runtime()

    def test_profiled_real_ipc_preserves_payload_and_counts_serialized_bytes(self):
        from relay.stream import _message, _receive
        left, right = socket.socketpair()
        profiler = Profiler(0., float('inf'))
        try:
            profiler.start()
            sender = threading.Thread(target=_message, args=(left, ('write', [1, 2, 3])))
            sender.start()
            self.assertEqual(_receive(right), ('write', [1, 2, 3]))
            sender.join(3)
            self.assertFalse(sender.is_alive())
        finally:
            with tempfile.TemporaryDirectory() as directory:
                profiler.close(directory, 'functional-test')
                evidence = json.loads(next(Path(directory).glob('spans-*')).read_text())
            left.close()
            right.close()
        self.assertEqual(evidence['errors'], [])
        self.assertEqual(evidence['unfinished_spans'], 0)
        self.assertEqual([r['stage'] for r in evidence['rows']], ['ipc-copies', 'ipc-copies'])
        self.assertEqual(len({r['thread'] for r in evidence['rows']}), 2)
        self.assertEqual(sorted(r['operation'] for r in evidence['ipc_payloads']), ['_message', '_receive'])
        self.assertEqual(evidence['ipc_payloads'][0]['serialized_bytes'], evidence['ipc_payloads'][1]['serialized_bytes'])
        self.assertGreater(evidence['ipc_payloads'][0]['serialized_bytes'], 3)

    def test_nested_spans_subtract_children_without_cross_thread_subtraction(self):
        ledger = Ledger(10., 20.)
        ledger.enter(1, 'outer', 'tracking', 11., 1.)
        ledger.enter(1, 'inner', 'resize', 12., 1.2)
        ledger.enter(2, 'parallel', 'detector-infer', 12., .1)
        ledger.leave(1, 'inner', 14., 1.5)
        ledger.leave(2, 'parallel', 15., .2)
        ledger.leave(1, 'outer', 16., 2.)
        rows = summarize(ledger.rows, source_frames=10, seconds=10.)
        self.assertAlmostEqual(rows['tracking']['wall_ms_per_source_frame'], 300.)
        self.assertAlmostEqual(rows['tracking']['caller_thread_cpu_percent_one_core'], 7.)
        self.assertEqual(rows['resize']['calls'], 1)
        self.assertEqual(rows['detector-infer']['wall_ms_per_source_frame'], 300.)

    def test_crossing_window_is_retained_but_excluded_from_steady(self):
        ledger = Ledger(10., 20.)
        for token, start, end in [('startup', 9., 11.), ('steady', 11., 12.), ('shutdown', 19., 21.)]:
            ledger.enter(1, token, 'encode', start, 0.)
            ledger.leave(1, token, end, .1)
        self.assertEqual([r['window'] for r in ledger.rows], ['boundary', 'steady', 'boundary'])
        result = summarize(ledger.rows, source_frames=30, seconds=10.)
        self.assertEqual(result['encode']['calls'], 1)
        self.assertAlmostEqual(result['encode']['wall_ms_per_source_frame'], 1000 / 30)

    def test_missing_observation_never_becomes_zero(self):
        result = summarize([], source_frames=0, seconds=120.)
        for name in ('decode', 'colorconvert', 'resize', 'detector-pre', 'detector-infer',
                     'detector-post', 'tracking', 'maskrender', 'encode', 'mux', 'ipc-copies'):
            self.assertIsNone(result[name]['wall_ms_per_source_frame'])
            self.assertIsNone(result[name]['caller_thread_cpu_percent_one_core'])
            self.assertEqual(result[name]['evidence_kind'], 'unknown')

    def test_bad_nesting_cannot_silently_produce_a_table(self):
        ledger = Ledger(0., 10.)
        ledger.enter(1, 'outer', 'tracking', 1., 0.)
        with self.assertRaisesRegex(RuntimeError, 'unbalanced'):
            ledger.leave(1, 'wrong', 2., 1.)

    def test_source_manifest_fails_for_drift_and_missing_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'source.py').write_text('before')
            manifest = root / 'sources.json'
            manifest.write_text(json.dumps({'source.py': '6db7d803e74f1ffa7d8f5adc0bf95b3e15bf4c8373fffadf546227cc6c6742cb'}))
            verify_sources(root, manifest)
            (root / 'source.py').write_text('after')
            with self.assertRaisesRegex(RuntimeError, 'source-drift'):
                verify_sources(root, manifest)
            (root / 'source.py').unlink()
            with self.assertRaisesRegex(RuntimeError, 'source-missing'):
                verify_sources(root, manifest)

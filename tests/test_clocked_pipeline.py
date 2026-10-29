"""Synthetic transport adapters exercise the public clocked adapter seam."""
import unittest
import threading
import time
import hashlib
import io
import json
from pathlib import Path
import tempfile
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from bench.clocked_pipeline import drive, run, measurement_windows, perf_health, source_window
from bench.clocked_bench import score_observations
from bench.clocked_bench import clock_guards
from bench.clocked_bench import baseline_deltas
from bench.clocked_bench import quality_window
from bench.clocked_bench import main as bench_main
from shield.types import Coverage, Frame, PresentedFrame
from shield.types import Detection
from shield.engine import MaskingEngine


class ImmediateLane:
    """Synthetic detector adapter at the engine's public lane interface."""
    def __init__(self, name, second_offered):
        self.name = name
        self.second_offered = second_offered
        self.results = []
        self.lock = threading.Lock()
        self.closed = False

    def offer(self, frame):
        with self.lock:
            self.results.append(Detection(self.name, frame.index, [], time.monotonic()))
        if self.name == 'fast' and frame.index == 1:
            self.second_offered.set()

    def drain(self):
        with self.lock:
            results, self.results = self.results, []
        return results

    @property
    def stats(self):
        return {}

    def close(self):
        self.closed = True


class IdentityMotion:
    def add(self, index, pixels):
        pass

    def project_many(self, quads, source, target, deadline=None):
        return quads


class CoordinatedSource:
    fps = 30.
    total_frames = 2
    duration = 2 / 30

    def __init__(self, write_entered):
        self.write_entered = write_entered
        self.arrivals = {}
        self.next_index = 0
        self.ended = False
        self.closed = False

    def start(self, origin):
        self.origin = origin

    def poll(self):
        index = self.next_index
        if index > 1 or (index == 1 and (not self.write_entered.is_set()
                         or time.monotonic() < self.origin + 1 / self.fps)):
            return []
        self.next_index += 1
        self.ended = self.next_index == 2
        self.arrivals[index] = time.monotonic()
        return [Frame(index, index / self.fps, np.full((8, 8, 3), 80, np.uint8))]

    def close(self):
        self.closed = True


class HeldEncoder:
    def __init__(self, write_entered, second_offered):
        self.write_entered, self.second_offered = write_entered, second_offered
        self.completions = []
        self.aborted = False

    def start(self):
        pass

    def write(self, frame):
        if frame.index == 0:
            self.write_entered.set()
            if not self.second_offered.wait(1):
                raise AssertionError('Ingest did not submit frame1 while encoder write was held')
        self.completions.append(time.monotonic())

    def finish(self):
        return self.completions

    def abort(self):
        self.aborted = True


class ManualClock:
    def __init__(self):
        self.now = 10.
        self.observed = self.now
        self.ingest_ended = False
        self.condition = threading.Condition()

    def monotonic(self):
        with self.condition:
            return self.now

    def sleep(self, seconds):
        with self.condition:
            self.now += seconds
            if not self.condition.wait_for(lambda: self.ingest_ended or self.observed >= self.now, timeout=1):
                raise AssertionError('Ingest did not observe the controlled source clock')


class ScheduledSource:
    fps = 10.
    total_frames = 5
    duration = .5

    def __init__(self, clock):
        self.clock = clock
        self.arrivals = {}
        self.emitted = set()
        self.ended = False

    def start(self, origin):
        self.origin = origin

    def poll(self):
        with self.clock.condition:
            frames = []
            for index in (0, 2):
                if index not in self.emitted and self.clock.now >= self.origin + index / self.fps:
                    self.emitted.add(index)
                    self.arrivals[index] = self.origin + index / self.fps
                    frames.append(Frame(index, index / self.fps, np.full((8, 8, 3), 80, np.uint8)))
            self.ended = self.clock.now >= self.origin + .4
            self.clock.observed = self.clock.now
            self.clock.condition.notify_all()
            return frames

    def close(self):
        pass


class ClockedEngineAdapter:
    """A synthetic public engine adapter; detector/render internals are absent."""
    def __init__(self, clock):
        self.clock = clock
        self.received = {}
        self.last = None
        self.next_index = 0
        self.drained = False
        self.stats = {'lanes': {}}

    def submit(self, frame, now=None):
        self.received[frame.index] = frame

    def end(self, last_index=None):
        with self.clock.condition:
            self.last = last_index
            self.clock.ingest_ended = True
            self.clock.condition.notify_all()

    def poll(self, now=None):
        output = []
        while self.last is not None and self.next_index <= self.last:
            index = self.next_index
            deadline = 10.5 + index / 10
            if now < deadline:
                break
            protected = index not in self.received
            output.append(PresentedFrame(
                index, index / 10, np.full((8, 8, 3), 0 if protected else 80, np.uint8),
                np.full((8, 8), 255 if protected else 0, np.uint8), [],
                Coverage(None, None, not protected, 'missing' if protected else 'covered'),
                'PROTECT' if protected else 'LIVE', deadline, now, protected, protected))
            self.next_index += 1
        self.drained = self.last is not None and self.next_index > self.last
        return output

    def close(self):
        pass


class MemoryEncoder:
    def __init__(self, clock):
        self.clock = clock
        self.frames = []

    def start(self):
        pass

    def write(self, frame):
        self.frames.append(frame)

    def finish(self):
        self.clock.now = max(self.clock.now, 10.99)
        return [10.57 + index / 10 for index in range(len(self.frames))]

    def abort(self):
        pass


class ClockedTransport(unittest.TestCase):
    def run_orchestration(self, *, borrowed=False, performance_only=False, fail_constructor=False, deferred=False):
        scratch = Path('/tmp/agents/irl-shield/m1-clocked-bench/judge-isolation')
        scratch.mkdir(parents=True, exist_ok=True)
        events, movies = [], {}
        state = {'resident': borrowed, 'timed': 0, 'reads': 0, 'closed': 0, 'created': 0}
        pixels = np.arange(8 * 8 * 3, dtype=np.uint8).reshape(8, 8, 3)
        mask = np.zeros((8, 8), dtype=np.uint8)

        class JudgeAdapter:
            names = ['synthetic-test-reader']

            def __init__(self, *args):
                events.append('judge-create')
                state['created'] += 1
                if fail_constructor:
                    raise RuntimeError('synthetic judge initialization failure')
                state['resident'] = True

            def read(self, frame):
                if state['timed'] != 5:
                    raise AssertionError('Judge read occurred before all five measurements completed')
                state['reads'] += 1
                events.append('judge-read')
                return []

            def close(self):
                state['closed'] += 1
                state['resident'] = False
                events.append('judge-close')

        class CaptureAdapter:
            def __init__(self, path, *args):
                self.frames = movies[str(path)]
                self.index = 0

            def set(self, key, index):
                self.index = int(index)
                return 0 <= self.index <= len(self.frames)

            def read(self):
                if self.index >= len(self.frames):
                    return False, None
                frame = self.frames[self.index].copy()
                self.index += 1
                return True, frame

            def release(self):
                pass

        def prepare(clip, path, synthetic, seconds):
            if not borrowed and state['resident']:
                raise AssertionError('Judge memory was resident during source preparation')
            events.append('prepare')
            path.write_bytes(b'synthetic source movie')
            movies[str(path)] = [pixels.copy(), pixels.copy()]
            label = {'id': 'unit-label', 'text': '12 Elm', 'visible': True, 'box': [1, 1, 4, 4]}
            return [[label] if synthetic else [] for _ in range(2)]

        def measure(source, output, candidate, options):
            if not borrowed and state['resident']:
                raise AssertionError('Judge memory was resident during measurement')
            events.append('measure')
            state['timed'] += 1
            output.write_bytes(b'synthetic output movie')
            movies[str(output)] = [pixels.copy() for _ in range(4)]
            records = [{'frame': index, 'pts': index / 30, 'mask_shape': [8, 8],
                        'mask_sha256': hashlib.sha256(mask.tobytes()).hexdigest(), 'mask_fraction': 0.,
                        'state': 'LIVE', 'protected': False, 'slate': False,
                        'emitted_at':11.01+index/30,
                        'coverage':{'fast_age':0,'accurate_age':0,'ok':True,'reason':'covered'}} for index in range(4)]
            output.with_suffix('.masks.json').write_text(json.dumps(records))
            with zipfile.ZipFile(output.with_suffix('.mask-pixels.zip'), 'w') as archive:
                for index in range(4):
                    archive.writestr(f'{index:08d}.bin', np.packbits(mask > 0, bitorder='little').tobytes())
            snapshot = {'pressure_state': 'normal', 'pressure_level': 1, 'cpu_count': 8,
                        'load_average': [1., 1., 1.],
                        'raw': {key: {'returncode': 0} for key in ('memory_pressure', 'swapusage', 'pressure_level')}}
            performance = self.warmed_performance(snapshot)
            performance.update({'clock_origin':10.,'frames': 4, 'encoded_frames': 4, 'source_frames': 4,
                                'candidate': candidate, 'options': options,
                                'pipeline_sha256': 'synthetic-source-snapshot',
                                'source_sha256': hashlib.sha256(Path(source).read_bytes()).hexdigest(),
                                'output_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
                                'mask_pixels_sha256': hashlib.sha256(output.with_suffix('.mask-pixels.zip').read_bytes()).hexdigest(),
                                'warmup_frames': 2, 'source_duration_seconds': 4 / 30,
                                'steady': {'frames': 2, 'start_frame': 2, 'stop_frame_exclusive': 4,
                                           'source_duration_seconds': 2 / 30},
                                'output_media': {'frames': 4, 'fps': 30., 'resolution': [1280, 720],
                                                 'pts': [index / 30 for index in range(4)]},
                                'cpu_percent_one_core_100': 7.,
                                'peak_tree_rss_mb': 10. + (400. if state['resident'] else 0.),
                                'startup': {'first_packet_delay_seconds': 1.1}})
            output.with_suffix('.performance.json').write_text(json.dumps(performance))
            output.with_suffix('.egress.json').write_text('[]\n')
            return performance

        supplied = object.__new__(JudgeAdapter) if borrowed else None
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            root = Path(folder)
            (root / 'fixtures').mkdir()
            (root / 'fixtures/manifest.json').write_text(json.dumps({'clips': [
                {'id': name, 'split': 'tune', 'path': f'fixtures/{name}.mp4'} for name in ('unit-a', 'unit-b')]}))
            argv = ['--candidate', 'unmasked', '--run-id', 'orchestration', '--sustained-seconds', '30']
            if deferred:
                prepared = root / 'prepared'
                prepared.mkdir()
                for name in ('unit-a', 'unit-b'):
                    for kind in ('natural', 'synthetic'):
                        (prepared / f'{name}-{kind}-input.mp4').write_bytes(f'exact prepared {name} {kind}'.encode())
                        (prepared / f'{name}-{kind}-input.truth.json').write_text('[[], []]\n')
                argv += ['--prepared-dir', str(prepared), '--defer-score', '--seconds', str(2 / 30)]
            if performance_only:
                argv.append('--performance-only')
            with patch('bench.clocked_bench.ROOT', root), \
                 patch('bench.clocked_pipeline.fingerprint', return_value='synthetic-source-snapshot'), \
                 patch('bench.clocked_pipeline.run', side_effect=measure), \
                 patch.dict('sys.modules', {'bench.run': SimpleNamespace(variant=prepare),
                                           'bench.judges': SimpleNamespace(Judges=JudgeAdapter)}), \
                 patch('fixtures.prepare.verify_cached'), \
                 patch('bench.clocked_bench.cv2.VideoCapture', side_effect=CaptureAdapter), \
                 patch('bench.clocked_bench.subprocess.check_output', return_value='ffmpeg synthetic\n'), \
                 patch('bench.clocked_bench.platform.platform', return_value='synthetic-platform'), \
                 patch('sys.stdout', new=io.StringIO()):
                card = bench_main(argv, judge=supplied)
            if deferred:
                self.assertEqual(card, json.loads((root / 'out/orchestration/measurement-plan.json').read_text()))
                for name in ('unit-a', 'unit-b'):
                    for kind in ('natural', 'synthetic'):
                        path = f'{name}-{kind}-input.mp4'
                        self.assertEqual((root / 'out/orchestration' / path).read_bytes(), (prepared / path).read_bytes())
                return card, events, state
            persisted = json.loads((root / 'out/orchestration/scorecard.json').read_text())
            self.assertEqual(card, persisted)
            for result in card['clips']:
                receipt = json.loads(Path(result['output']).with_suffix('.performance.json').read_text())
                self.assertEqual(receipt, result['performance'])
            self.assertEqual(json.loads((root / 'out/orchestration/sustained-masked.performance.json').read_text()),
                             card['sustained'])
        return card, events, state

    def test_main_constructs_owned_judges_only_after_all_measurements_and_then_reads(self):
        card, events, state = self.run_orchestration()
        self.assertEqual(state['timed'], 5)
        self.assertEqual(state['created'], 1)
        self.assertEqual(state['reads'], 16)
        self.assertEqual(state['closed'], 1)
        self.assertLess(max(index for index, event in enumerate(events) if event == 'measure'),
                        events.index('judge-create'))
        self.assertEqual(card['peak_tree_rss_mb'], 10.)
        self.assertTrue(card['real_video_pass'])
        self.assertTrue(all('truth' not in result for result in card['clips']))

    def test_main_reports_borrowed_residency_and_never_constructs_performance_only_judges(self):
        for borrowed, performance_only, mode, isolated, reads, peak in (
                (True, False, 'borrowed-resident', False, 16, 410.),
                (False, True, 'no-judge', True, 0, 10.),
                (True, True, 'borrowed-resident', False, 0, 410.)):
            with self.subTest(borrowed=borrowed, performance_only=performance_only):
                card, events, state = self.run_orchestration(borrowed=borrowed, performance_only=performance_only)
                self.assertEqual(state['timed'], 5)
                self.assertEqual((state['created'], state['closed'], state['reads']), (0, 0, reads))
                self.assertEqual(card['peak_tree_rss_mb'], peak)
                isolation = card['judge_memory_isolation']
                self.assertEqual((isolation['mode'], isolation['isolated']), (mode, isolated))
                for receipt in [result['performance'] for result in card['clips']] + [card['sustained']]:
                    self.assertEqual(receipt['judge_memory_isolation'], isolation)
                if performance_only:
                    self.assertEqual(card['judges'], [])
                    self.assertNotIn('judge-read', events)

    def test_main_preserves_deferred_judge_constructor_failure(self):
        with self.assertRaisesRegex(RuntimeError, 'synthetic judge initialization failure'):
            self.run_orchestration(fail_constructor=True)

    def test_main_defers_grading_and_copies_exact_prepared_sources_into_bundle(self):
        plan, events, state = self.run_orchestration(deferred=True)
        self.assertEqual(state['timed'], 5)
        self.assertEqual((state['created'], state['reads'], state['closed']), (0, 0, 0))
        self.assertNotIn('prepare', events)
        self.assertEqual(plan['status'], 'awaiting-grading')
        self.assertEqual(plan['card']['judges'], [])
        self.assertTrue(all(result['truth'].endswith('.truth.json') for result in plan['card']['clips']))

    def test_warmed_perf_requires_thirty_steady_seconds_and_normal_endpoint_pressure(self):
        self.assertEqual(source_window({'frames': 150, 'fps': 30.}, {'repeat_seconds': 30})['total_frames'], 1200)
        quality_plan = source_window({'frames': 150, 'fps': 30.}, {})
        self.assertEqual((quality_plan['warmup_frames'], quality_plan['steady_frames'], quality_plan['total_frames']),
                         (300, 150, 450))
        snapshot = {'platform': 'Darwin', 'pressure_level': 1, 'pressure_state': 'normal',
                    'load_average': [2., 2., 2.], 'cpu_count': 8,
                    'raw': {key: {'returncode': 0} for key in ('memory_pressure', 'swapusage', 'pressure_level')}}
        performance = self.warmed_performance(snapshot)
        self.assertTrue(clock_guards(performance)['throughput'])
        from copy import deepcopy
        hd=deepcopy(performance)
        hd['resolution']=hd['output_media']['resolution']=[1920,1080]
        self.assertFalse(clock_guards(hd)['throughput'])
        self.assertTrue(clock_guards(hd,required_resolution=(1920,1080))['throughput'])
        for fault in ('start-warn', 'end-critical', 'unknown-level', 'short-steady'):
            with self.subTest(fault=fault):
                damaged = deepcopy(performance)
                if fault == 'start-warn':
                    damaged['perf_health']['start'].update(pressure_level=2, pressure_state='warn')
                elif fault == 'end-critical':
                    damaged['perf_health']['end'].update(pressure_level=4, pressure_state='critical')
                elif fault == 'unknown-level':
                    damaged['perf_health']['end'].update(pressure_level=None, pressure_state='unknown')
                else:
                    damaged['steady']['frames'] = 600
                    damaged['steady']['source_duration_seconds'] = 20.
                self.assertFalse(clock_guards(damaged)['throughput'])
                self.assertFalse(clock_guards(damaged)['latency'])

    @staticmethod
    def warmed_performance(snapshot):
        from copy import deepcopy
        return {
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
            'performance_valid': True,
            'presentation_delay_seconds':{'p50':1.01,'p95':1.01},
            'engine':{'lanes':{'fast':{'actual_hz':8.},'accurate':{'actual_hz':4.}}},
            'perf_health': {'start': deepcopy(snapshot), 'end': deepcopy(snapshot)},
        }

    def test_quality_window_wraps_original_truth_and_normalizes_only_selected_indices(self):
        records = [{'frame': index, 'pts': index / 30} for index in range(8)]
        truth = [[{'id': letter}] for letter in ('A', 'B', 'C')]
        performance = {'frames': 8, 'warmup_frames': 4, 'source_fps': 30.,
                       'steady': {'start_frame': 4, 'frames': 4}}
        selected, labels = quality_window(records, performance, truth)
        self.assertEqual([row['frame'] for row in selected], [0, 1, 2])
        self.assertEqual([row['original_frame'] for row in selected], [5, 6, 7])
        self.assertEqual([row['source_frame'] for row in selected], [2, 0, 1])
        self.assertEqual([items[0]['id'] for items in labels], ['C', 'A', 'B'])
        self.assertEqual([row['frame'] for row in records], list(range(8)))
        self.assertEqual(records[5]['pts'], 5 / 30)
        self.assertEqual(selected[0]['pts'], 0.)
        with self.assertRaisesRegex(ValueError, 'steady'):
            quality_window(records, {**performance, 'warmup_frames': 6,
                                    'steady': {'start_frame': 6, 'frames': 2}}, truth)

    def test_perf_health_keeps_raw_commands_and_never_infers_normal_from_free_percent(self):
        for level, expected in ((1, 'normal'), (2, 'warn'), (4, 'critical'), (0, 'unknown'), (None, 'unknown')):
            with self.subTest(level=level):
                def command_result(command, **options):
                    if command[0] == 'memory_pressure':
                        return SimpleNamespace(returncode=0, stdout='System-wide memory free percentage: 71%\n', stderr='')
                    if command[-1] == 'vm.swapusage':
                        return SimpleNamespace(returncode=0, stdout='vm.swapusage: total = 4096.00M used = 1024.00M free = 3072.00M\n', stderr='')
                    return SimpleNamespace(returncode=0 if level is not None else 1,
                                           stdout=f'kern.memorystatus_vm_pressure_level: {level}\n' if level is not None else '',
                                           stderr='' if level is not None else 'unknown oid')
                with patch('bench.clocked_pipeline.platform.system', return_value='Darwin'), \
                     patch('bench.clocked_pipeline.os.getloadavg', return_value=(16., 12., 10.)), \
                     patch('bench.clocked_pipeline.os.cpu_count', return_value=8), \
                     patch('bench.clocked_pipeline.subprocess.run', side_effect=command_result):
                    receipt = perf_health()
                self.assertEqual(receipt['pressure_state'], expected)
                self.assertEqual(receipt['load_average'], [16., 12., 10.])
                self.assertEqual(receipt['load_per_cpu'], 2.)
                self.assertEqual(receipt['raw']['memory_pressure']['command'], ['memory_pressure', '-Q'])
                self.assertIn('71%', receipt['raw']['memory_pressure']['stdout'])
                self.assertIn('1024.00M', receipt['raw']['swapusage']['stdout'])
                self.assertEqual(receipt['raw']['pressure_level']['returncode'], 0 if level is not None else 1)

    def test_linux_health_uses_psi_and_available_memory_without_a_macos_level(self):
        for some, full, available, expected in ((.2, .02, 4 * 1024**2, 'normal'),
                                                (1., .02, 4 * 1024**2, 'warn'),
                                                (.2, 1., 4 * 1024**2, 'critical'),
                                                (.2, .02, 1024**2, 'warn')):
            with self.subTest(some=some, full=full, available=available):
                files = {'/proc/pressure/memory': f'some avg10={some} avg60=0.00 avg300=0.00 total=1234\nfull avg10={full} avg60=0.00 avg300=0.00 total=321\n',
                         '/proc/pressure/cpu': 'some avg10=2.00 avg60=1.00 avg300=0.50 total=500\n',
                         '/proc/pressure/io': 'some avg10=0.00 avg60=0.00 avg300=0.00 total=0\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0\n',
                         '/proc/meminfo': f'MemTotal: 16777216 kB\nMemAvailable: {available} kB\nSwapTotal: 8388608 kB\nSwapFree: 7340032 kB\n',
                         '/proc/vmstat': 'pswpin 10\npswpout 20\n'}
                with patch('bench.clocked_pipeline.platform.system', return_value='Linux'), \
                     patch.object(Path, 'read_text', autospec=True, side_effect=lambda path, *a, **k: files[str(path)]):
                    receipt = perf_health()
                self.assertEqual(receipt['pressure_state'], expected)
                self.assertIsNone(receipt['pressure_level'])
                self.assertEqual(receipt['health_adapter'], 'linux-psi-memavailable-v1')
                self.assertEqual(receipt['swap_used_bytes'], 1024**3)
                self.assertEqual(receipt['memory_psi']['some']['total'], 1234)
                self.assertEqual(receipt['raw']['memory_psi']['stdout'], files['/proc/pressure/memory'])
                self.assertNotIn('memory_pressure', receipt['raw'])
                self.assertEqual(clock_guards(self.warmed_performance(receipt))['throughput'], expected == 'normal')

    def test_measurement_windows_exclude_startup_protection_latency_and_first_packet(self):
        records = []
        for index, (encoded, latency) in enumerate(zip((13., 13.1, 13.2, 14.1, 15.1, 16.1),
                                                       (3., 2.1, 1.2, 1.1, 1.1, 1.1))):
            records.append({'frame': index, 'pts': float(index), 'encoded_at': encoded,
                            'encoded_source_clock_latency': latency, 'encoded_source_arrival_latency': latency,
                            'presentation_lateness': .01, 'emitted_at':11.01+index,
                            'coverage':{'fast_age':None if index<3 else index-3,
                                        'accurate_age':None if index<3 else index,
                                        'ok':index>=3,'reason':'missing' if index<3 else 'covered'},
                            'protected': index < 3,
                            'state': 'PROTECT' if index < 3 else 'LIVE', 'slate': False})
        windows = measurement_windows(records, source_fps=1., origin=10., ended_at=16.2, warmup_frames=3)
        self.assertEqual(windows['steady']['frames'], 3)
        self.assertEqual(windows['steady']['start_frame'], 3)
        self.assertAlmostEqual(windows['steady']['source_duration_seconds'], 3.)
        self.assertAlmostEqual(windows['steady']['realtime_added_latency_seconds']['p95'], 1.1)
        self.assertEqual(windows['steady']['protected_fraction'], 0.)
        self.assertAlmostEqual(windows['steady']['presentation_delay_seconds']['p95'],1.01)
        self.assertEqual(windows['steady']['coverage']['reasons'],{'covered':3})
        self.assertAlmostEqual(windows['steady']['coverage']['fast']['age_frames']['p50'],1.)
        self.assertAlmostEqual(windows['steady']['coverage']['accurate']['age_frames']['p95'],4.9)
        self.assertEqual(windows['steady']['coverage']['fast']['missing_fraction'],0.)
        self.assertEqual(windows['startup']['coverage']['fast']['missing_fraction'],1.)
        self.assertEqual(windows['full']['coverage']['fast']['missing_fraction'],.5)
        self.assertAlmostEqual(windows['steady']['fps'], 1.)
        self.assertEqual(windows['startup']['protected_fraction'], 1.)
        self.assertAlmostEqual(windows['startup']['first_packet_delay_seconds'], 3.)
        self.assertEqual(windows['full']['frames'], 6)
        self.assertEqual(windows['full']['protected_fraction'], .5)
        with self.assertRaisesRegex(ValueError, 'steady'):
            measurement_windows(records, source_fps=1., origin=10., ended_at=16.2, warmup_frames=6)

    def test_ingest_reaches_real_engine_while_encoder_write_is_held(self):
        write_entered, second_offered = threading.Event(), threading.Event()
        source = CoordinatedSource(write_entered)
        sink = HeldEncoder(write_entered, second_offered)
        lanes = {name: ImmediateLane(name, second_offered) for name in ('fast', 'accurate')}
        engine = MaskingEngine(lanes, {'fps': 30., 'delay_seconds': .05}, motion=IdentityMotion())
        result = drive(source, engine, sink)
        self.assertEqual(result['frames'], 2)
        self.assertEqual([row['frame'] for row in result['records']], [0, 1])
        self.assertTrue(second_offered.is_set())
        self.assertTrue(source.closed)
        self.assertTrue(all(lane.closed for lane in lanes.values()))
        self.assertFalse(any(thread.name == 'clocked-ingest' for thread in threading.enumerate()))

    def test_ingest_failure_aborts_output_and_closes_real_engine_adapters(self):
        write_entered, failure_seen = threading.Event(), threading.Event()

        class FailingSource(CoordinatedSource):
            def poll(self):
                if self.write_entered.is_set():
                    failure_seen.set()
                    raise RuntimeError('synthetic decoder failure')
                return super().poll()

        source = FailingSource(write_entered)
        sink = HeldEncoder(write_entered, failure_seen)
        lanes = {name: ImmediateLane(name, threading.Event()) for name in ('fast', 'accurate')}
        engine = MaskingEngine(lanes, {'fps': 30., 'delay_seconds': .05}, motion=IdentityMotion())
        with self.assertRaisesRegex(RuntimeError, 'synthetic decoder failure'):
            drive(source, engine, sink)
        self.assertTrue(source.closed)
        self.assertTrue(sink.aborted)
        self.assertTrue(all(lane.closed for lane in lanes.values()))
        self.assertFalse(any(thread.name == 'clocked-ingest' for thread in threading.enumerate()))

    def test_legacy_scheduled_composite_is_rejected_before_media_or_model_loading(self):
        for candidate, options in (('vision-scheduled', {}), ('vision-accurate', {'fast_candidate': 'vision-scheduled'})):
            with self.subTest(candidate=candidate, options=options):
                with self.assertRaisesRegex(ValueError, 'legacy vision-scheduled'):
                    run('/does-not-exist/source.mp4', '/does-not-exist/output.mp4', candidate, options)

    def test_baseline_deltas_use_percentage_points_and_keep_unavailable_metrics_null(self):
        baseline = {'natural': {'hidden_fraction': 0.}, 'synthetic': {'hidden_fraction': 0.}}
        measured = {'natural': {'hidden_fraction': .95}, 'synthetic': {'hidden_fraction': 1.}}
        self.assertEqual(baseline_deltas(measured, baseline), {'natural': 95., 'synthetic': 100.})
        self.assertEqual(baseline_deltas({'natural': {'hidden_fraction': None}, 'synthetic': None}, baseline),
                         {'natural': None, 'synthetic': None})
        self.assertEqual(baseline_deltas(measured, {'natural': {'hidden_fraction': None}}),
                         {'natural': None, 'synthetic': None})
        self.assertEqual(baseline_deltas(baseline, baseline), {'natural': 0., 'synthetic': 0.})

    def test_missing_ingest_and_tail_keep_frame_clock_and_use_encoder_egress(self):
        clock = ManualClock()
        result = drive(ScheduledSource(clock), ClockedEngineAdapter(clock), MemoryEncoder(clock),
                       clock=clock.monotonic, sleep=clock.sleep)
        self.assertEqual(result['frames'], 5)
        self.assertEqual([r['frame'] for r in result['records']], [0, 1, 2, 3, 4])
        self.assertEqual([r['protected'] for r in result['records']], [False, True, False, True, True])
        self.assertAlmostEqual(result['realtime_added_latency_seconds']['p95'], .57)
        self.assertAlmostEqual(result['output_wall_rate_fps'], 10.)
        self.assertAlmostEqual(result['seconds'], .99)
        self.assertIsNone(result['records'][1]['source_arrived_at'])
        self.assertAlmostEqual(result['records'][2]['encoded_source_arrival_latency'], .57)

    def test_unconfirmed_packets_duplicate_frames_and_wrong_pts_fail_closed(self):
        for fault in ('short-packets', 'duplicate-index', 'wrong-pts', 'nonfinite-packet'):
            with self.subTest(fault=fault):
                class DamagedEngine(ClockedEngineAdapter):
                    def poll(self, now=None):
                        frames = super().poll(now)
                        for frame in frames:
                            if frame.index == 2 and fault == 'duplicate-index':
                                frame.index = 1
                            if frame.index == 2 and fault == 'wrong-pts':
                                frame.pts = .25
                        return frames

                class DamagedEncoder(MemoryEncoder):
                    def finish(self):
                        packets = super().finish()
                        if fault == 'short-packets':
                            return packets[:-1]
                        if fault == 'nonfinite-packet':
                            packets[-1] = float('nan')
                        return packets

                clock = ManualClock()
                with self.assertRaisesRegex(RuntimeError, 'Frame accounting'):
                    drive(ScheduledSource(clock), DamagedEngine(clock), DamagedEncoder(clock),
                          clock=clock.monotonic, sleep=clock.sleep)

    def test_live_pixel_guards_and_protected_frames_keep_strict_privacy_scoring(self):
        natural = {'text': 'Main Street', 'box': [8, 8, 16, 16], 'confidence': .95}
        label = {'id': 'house', 'text': '42 Elm', 'box': [0, 0, 4, 4], 'visible': True}
        synthetic_reading = {**label, 'confidence': .95}
        inputs = [[natural, synthetic_reading] for _ in range(3)]
        truth = [[label] for _ in range(3)]
        records = [{'state': state, 'protected': state != 'LIVE', 'slate': False}
                   for state in ('LIVE', 'PROTECT', 'LIVE')]
        quality, details = score_observations(inputs, [[], [], []], truth,
                                              [{'pass': True}, None, {'pass': True}], records)
        self.assertTrue(quality['real_video_pass'])
        self.assertEqual(quality['natural']['hidden_fraction'], 1.)
        self.assertEqual(quality['synthetic']['hidden_fraction'], 1.)
        self.assertEqual(quality['synthetic_input_control'], {'total': 1, 'unreadable': 0})
        self.assertAlmostEqual(quality['protected_fraction'], 1 / 3)
        self.assertEqual(len(details['frame_guards']), 3)
        protected = [{'state': 'PROTECT', 'protected': True, 'slate': False} for _ in range(3)]
        quality, _ = score_observations(inputs, [[], [], []], truth, [None] * 3, protected)
        self.assertFalse(quality['real_video_pass'])
        self.assertEqual(quality['natural']['hidden'], 0)
        self.assertEqual(quality['synthetic']['hidden'], 0)
        quality, _ = score_observations([[]] * 3, [[], [], []], truth,
                                        [{'pass': True}, None, {'pass': True}], records)
        self.assertEqual(quality['synthetic_input_control'], {'total': 1, 'unreadable': 1})

    def test_clock_gate_requires_media_pts_observed_egress_and_under_two_percent_protection(self):
        from copy import deepcopy
        snapshot = {'pressure_state': 'normal', 'pressure_level': 1, 'cpu_count': 8,
                    'load_average': [2., 2., 2.],
                    'raw': {key: {'returncode': 0} for key in ('memory_pressure', 'swapusage', 'pressure_level')}}
        performance = self.warmed_performance(snapshot)
        self.assertEqual(clock_guards(performance), {'throughput': True, 'latency': True, 'protected': True})
        for fault, guard in (('pts', 'throughput'), ('packet-count', 'throughput'),
                              ('wall-rate', 'throughput'), ('protected-limit', 'protected'),
                              ('added-latency', 'latency'), ('short-run', 'throughput')):
            with self.subTest(fault=fault):
                damaged = deepcopy(performance)
                if fault == 'pts':
                    damaged['output_media']['pts'][13] = 1.5
                elif fault == 'packet-count':
                    damaged['encoded_frames'] = 899
                elif fault == 'wall-rate':
                    damaged['last_encoded_at'] = 41.2
                    damaged['output_wall_rate_fps'] = 29.7
                    damaged['output_clock_drift_seconds'] = .2333333333
                elif fault == 'protected-limit':
                    damaged['protected_fraction'] = .02
                elif fault == 'added-latency':
                    damaged['realtime_added_latency_seconds']['p95'] = 1.3001
                elif fault == 'short-run':
                    damaged['source_duration_seconds'] = 5.
                self.assertFalse(clock_guards(damaged)[guard])


if __name__ == '__main__':
    unittest.main()

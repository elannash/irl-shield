"""Q2 readiness contracts; synthetic pixels and fake CUDA boundary only."""
from dataclasses import dataclass
import unittest

import cv2
import numpy as np

from bench.offline_quality import render_offline
from shield.render import Renderer, Rendered


class Stationary:
    def add(self, index, pixels):
        pass

    def project_many(self, quads, source, target, deadline=None):
        return quads

    def diagnostics(self, index):
        return {'valid': True, 'reason': 'synthetic'}


class Boxes:
    def close(self):
        pass

    def detect_quads(self, pixels):
        return [[[2, 2], [24, 2], [24, 24], [2, 24]]]


@dataclass
class Budget:
    limit_pixels: int = 10
    covered_pixels: int = 625
    minimum_pixels: int = 625
    padding_scale: float = 0.
    satisfied: bool = False


@dataclass
class Budgeted(Rendered):
    budget: Budget | None = None


class ImpossibleBudget:
    def render(self, *args):
        rendered = Renderer(padding=0).render(*args)
        return Budgeted(rendered.pixels, rendered.mask, rendered.protected, rendered.slate, Budget())


class QualitySeams(unittest.TestCase):
    def test_impossible_budget_survives_presentation_without_dropping_quads(self):
        pixels = np.full((48, 96, 3), 200, np.uint8)
        outputs = []
        result = render_offline([pixels] * 3, 10., {n: Boxes() for n in ('fast', 'accurate')},
                                {'delay_seconds': .2}, outputs.append,
                                motion=Stationary(), renderer=ImpossibleBudget())
        self.assertEqual([r['render_budget']['satisfied'] for r in result['records']], [False] * 3)
        self.assertEqual(result['records'][0]['render_budget']['minimum_pixels'], 625)
        self.assertGreater(int(cv2.countNonZero(outputs[0].mask)), 10)
        self.assertEqual(outputs[0].mask[12, 12], 255)
        self.assertEqual(len(outputs[0].quads), 3)


def synthetic_renderer(fps, options, parameters):
    return ImpossibleBudget()


def synthetic_motion(fps, options, parameters):
    return Stationary()


class SealedFactories(unittest.TestCase):
    def test_sealed_render_injects_factories_and_binds_diagnostics_and_source(self):
        import json
        from pathlib import Path
        import tempfile
        from unittest.mock import patch
        from tests.test_quality_bundle import QualityBundle
        from bench import quality_bundle as bundle
        from bench.q2_execution.adapters import RenderFactories
        fixture = QualityBundle(methodName='test_real_encoded_bundle_requires_input_pixels_judging_and_unchanged_masks')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        destination = fixture.base / 'adapter'
        factories = RenderFactories(synthetic_renderer, synthetic_motion)
        with patch('bench.pipeline.detector_for', side_effect=lambda *args: Boxes()):
            plan = bundle.render(Path.cwd(), fixture.inputs, fixture.config, destination,
                                 fixture.clips[0], False, factories=factories)
        records = json.loads((destination / 'masked.masks.json').read_text())
        self.assertEqual([r['render_budget']['satisfied'] for r in records], [False] * 4)
        self.assertIn(f'{synthetic_renderer.__module__}.synthetic_renderer', plan['execution_adapters']['factories'].values())
        self.assertEqual(bundle.verify(destination)['execution_adapters'], factories.identity(Path.cwd()))
        path = destination / 'masked.masks.json'
        path.write_text(path.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'artifact changed'):
            bundle.verify(destination)


class FakeEvents:
    def __init__(self, fail=None):
        self.actions = []
        self.fail = fail

    def prepare(self):
        self.actions.append('prepare')

    def record(self, event):
        self.actions.append(event)
        if event == self.fail:
            raise RuntimeError('synthetic CUDA ' + event)

    def wait(self):
        self.actions.append('wait')
        if self.fail == 'wait':
            raise RuntimeError('synthetic CUDA wait')

    def elapsed_ms(self):
        self.actions.append('elapsed')
        return 12.


class EventAccounting(unittest.TestCase):
    def test_device_interval_waits_and_uses_source_frames_not_inferences(self):
        from bench.q2_execution.events import EventTimer, summarize
        events = FakeEvents()
        timer = EventTimer(events, lane='fast')
        self.assertEqual(timer.run(lambda: 42), 42)
        self.assertEqual(events.actions, ['prepare', 'start', 'end', 'wait', 'elapsed'])
        timer.run(lambda: 43)
        result = summarize(timer.rows, source_frames=30)
        self.assertEqual(result['attempted_calls'], 2)
        self.assertEqual(result['gpu_ms_per_inference'], 12.)
        self.assertEqual(result['gpu_ms_per_source_frame'], .8)
        self.assertEqual(result['source_frames'], 30)

    def test_inference_and_wait_errors_are_retained_and_never_become_cost(self):
        from bench.q2_execution.events import EventTimer, summarize
        for failure in ('inference', 'start', 'end', 'wait'):
            events = FakeEvents(fail=failure)
            timer = EventTimer(events, lane='accurate')
            def infer():
                if failure == 'inference':
                    raise ValueError('synthetic inference')
                return []
            with self.subTest(failure=failure), self.assertRaisesRegex(Exception, 'synthetic'):
                timer.run(infer)
            result = summarize(timer.rows, source_frames=30)
            self.assertFalse(result['valid'])
            self.assertEqual(result['attempted_calls'], 1)
            self.assertEqual(result['failed_calls'], 1)
            self.assertIsNone(result['gpu_ms_per_source_frame'])
            self.assertIsNone(result['gpu_ms_per_inference'])
            if failure == 'inference':
                self.assertEqual(events.actions, ['prepare', 'start', 'end', 'wait', 'elapsed'])


class QueueBarriers(unittest.TestCase):
    def test_release_requires_both_phone_flags_exact_freeze_and_inherited_ex(self):
        import fcntl
        import json
        import os
        from pathlib import Path
        import tempfile
        from unittest.mock import patch
        from bench.q2_execution.queued import require_release
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lock, release = root / 'perf.lock', root / 'release.json'
            queue = root / 'queue'
            receipt = queue / 'linux/jobs/synthetic/attempts/1/attempt.json'
            receipt.parent.mkdir(parents=True)
            sha = 'a' * 64
            with lock.open('w') as stream:
                fcntl.flock(stream, fcntl.LOCK_EX)
                env = {'IRL_SHIELD_PERF_QUEUE_LEASE_FD': str(stream.fileno()),
                       'IRL_SHIELD_PERF_QUEUE_ATTEMPT': '1',
                       'IRL_SHIELD_PERF_QUEUE_RECEIPT': str(receipt),
                       'IRL_SHIELD_PERF_QUEUE_FORCED': '0'}
                stat = os.fstat(stream.fileno())
                receipt.write_text(json.dumps({'host': 'linux', 'phase': 'prepared', 'execution_started': True,
                    'queue_environment': env, 'lease_path': str(lock),
                    'lease_identity': {'device': stat.st_dev, 'inode': stat.st_ino}}))
                valid = {'PHONE_TEST_DONE': False, 'GPU_RELEASED': True, 'V2_FROZEN': sha}
                with patch('bench.q2_execution.queued.PERF_LOCK', lock):
                    for change in ({'GPU_RELEASED': False}, {'V2_FROZEN': 'b' * 64}):
                        release.write_text(json.dumps(valid | change))
                        with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'release|frozen'):
                            require_release(release, sha, queue, env=env)
                    release.write_text(json.dumps(valid))
                    self.assertEqual(require_release(release, sha, queue, env=env)['v2_manifest_sha256'], sha)
                    fcntl.flock(stream, fcntl.LOCK_UN)
                    fcntl.flock(stream, fcntl.LOCK_SH)
                    with self.assertRaisesRegex(ValueError, 'exclusive'):
                        require_release(release, sha, queue, env=env)


class FactoryContracts(unittest.TestCase):
    def test_flow_receives_floored_source_horizon_and_bad_path_protects(self):
        from unittest.mock import patch
        from bench.q2_execution.adapters import flow_motion
        class HorizonMotion(Stationary):
            def __init__(self, **options):
                self.horizon = options['max_projection_frames']
            def project_many(self, quads, source, target, deadline=None):
                return None
        with patch('shield.motion.MotionHistory', HorizonMotion):
            motion = flow_motion(29.97, {'delay_seconds': 1.}, {})
        self.assertEqual(motion.horizon, 29)
        outputs = []
        result = render_offline([np.full((48, 96, 3), 100, np.uint8)] * 3, 10.,
            {n: Boxes() for n in ('fast', 'accurate')}, {'delay_seconds': .2}, outputs.append, motion=motion)
        self.assertTrue(all(r['protected'] for r in result['records']))
        self.assertTrue(all(r['coverage']['ok'] is False for r in result['records']))

    def test_default_renderer_pixels_and_masks_match_explicit_existing_renderer(self):
        pixels = np.full((48, 96, 3), 200, np.uint8)
        outputs = [[], []]
        for i, renderer in enumerate((None, Renderer(padding=.3))):
            render_offline([pixels] * 4, 10., {n: Boxes() for n in ('fast', 'accurate')},
                           {}, outputs[i].append, renderer=renderer, motion=Stationary())
        for default, explicit in zip(*outputs):
            np.testing.assert_array_equal(default.pixels, explicit.pixels)
            np.testing.assert_array_equal(default.mask, explicit.mask)

    def test_source_identity_detects_mutation_and_rejects_absolute_escape(self):
        from pathlib import Path
        import tempfile
        from bench.q2_execution.adapters import verify_identity, sha256
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'adapter.py'
            source.write_text('version=1')
            identity = {'sources': [{'path': 'adapter.py', 'sha256': sha256(source)}]}
            verify_identity(root, identity)
            source.write_text('version=2')
            with self.assertRaisesRegex(ValueError, 'source changed'):
                verify_identity(root, identity)
            identity['sources'][0]['path'] = str(source)
            with self.assertRaisesRegex(ValueError, 'escapes root'):
                verify_identity(root, identity)

    def test_queue_entry_refuses_hold_before_any_gpu_or_media_construction(self):
        import json
        from pathlib import Path
        import tempfile
        from unittest.mock import patch
        from bench.q2_execution.queued import main
        with tempfile.TemporaryDirectory() as temporary:
            release = Path(temporary) / 'release.json'
            release.write_text(json.dumps({'PHONE_TEST_DONE': True, 'GPU_RELEASED': True, 'V2_FROZEN': None}))
            with patch('ctypes.CDLL', side_effect=AssertionError('GPU runtime loaded during hold')), \
                 patch('cv2.VideoCapture', side_effect=AssertionError('Media decoded during hold')):
                with self.assertRaisesRegex(ValueError, 'frozen'):
                    main(['gpu-cost', '--release', str(release), '--v2-manifest-sha256', 'a' * 64,
                          '--queue-dir', temporary, '--config', 'missing.json', '--directory', 'out/not-created'])


def synthetic_backend(lane, name, options):
    backend = Boxes()
    backend.metadata = {'synthetic_stand_in': True, 'lane': lane, 'model': name}
    return backend


class ClockedInjection(unittest.TestCase):
    def test_clocked_saves_adapter_diagnostics_with_borrowed_synthetic_backends(self):
        import json
        from pathlib import Path
        import subprocess
        import tempfile
        from unittest.mock import patch
        from bench.clocked_pipeline import _run_file
        from bench.q2_execution.adapters import RenderFactories
        with tempfile.TemporaryDirectory() as temporary:
            source, output = Path(temporary) / 'source.mp4', Path(temporary) / 'output.mp4'
            pixels = np.full((720, 1280, 3), 128, np.uint8)
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'rawvideo',
                '-pix_fmt', 'bgr24', '-s', '1280x720', '-r', '30', '-i', 'pipe:0', '-an',
                '-c:v', 'libx264', '-preset', 'ultrafast', '-threads', '2', '-bf', '0', str(source)],
                input=pixels.tobytes() * 3, check=True, timeout=20)
            with patch('bench.pipeline.detector_for', side_effect=AssertionError('Unexpected model construction')), \
                 patch('bench.clocked_pipeline.perf_health', return_value={'pressure_state': 'normal'}):
                result = _run_file(source, output, 'ppocr-v6-small',
                    {'encoder': 'libx264', 'warmup_seconds': 0, 'repeat_seconds': .1,
                     'delay_seconds': .1, 'fast_width': 0, 'accurate_width': 0}, None, {},
                    backend_factory=synthetic_backend, factories=RenderFactories(synthetic_renderer, synthetic_motion))
            records = json.loads(output.with_suffix('.masks.json').read_text())
            self.assertEqual(len(records), 3)
            self.assertEqual([r['render_budget']['satisfied'] for r in records], [False] * 3)
            self.assertEqual(result['backend_factory']['factory'], f'{synthetic_backend.__module__}.synthetic_backend')
            self.assertEqual(result['loading']['accurate']['metadata']['model'], 'ppocr-v6-small')

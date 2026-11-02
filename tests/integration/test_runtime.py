"""Production egress routing seam: fake transport, actual runtime/key callback."""
from contextlib import redirect_stderr
from io import StringIO
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from relay.runtime import make_engine, run
from relay.security import Credentials, RelayAddress


class RuntimeDestination(unittest.TestCase):
    def test_runtime_receipt_uses_effective_lane_settings_and_actual_encoder_and_delay(self):
        artifact = {'sha256': '0' * 64, 'license': 'CC0-1.0', 'license_source': 'synthetic',
                    'source': 'synthetic', 'url': 'not-downloaded',
                    'preprocess': {'mean': [0., 0., 0.], 'std': [1., 1., 1.]}}
        class Output:
            error_code = error_details = None
            count = max_write_seconds = recovery_count = 0
            recovery_events = ()
            def close(self):
                pass
        class Source:
            error_code = last_failure = None
            high_water = active_generation = 0
            timestamp_issues = {}
            def close(self):
                pass
        for provider, encoder, delay, options, rate, floor in (
                ('cuda', 'h264_nvenc', 1., {}, 4., .5),
                ('cpu', 'libx264', 2.5, {}, 4., .5),
                ('cpu', 'libx264', 3.25, {'accurate_rate_hz': 7.5, 'accurate_box_thresh': .73}, 7.5, .73)):
            active = ['CPUExecutionProvider'] if provider == 'cpu' else ['CUDAExecutionProvider', 'CPUExecutionProvider']
            with self.subTest(provider=provider, options=options), tempfile.TemporaryDirectory() as directory, \
                    patch('bench.onnx_detectors.verified_path', return_value=('/synthetic/not-read.onnx', artifact)), \
                    patch('bench.onnx_detectors.ort.get_available_providers', return_value=['CPUExecutionProvider', 'CUDAExecutionProvider']), \
                    patch('bench.onnx_detectors.ort.InferenceSession') as session, \
                    patch('bench.onnx_detectors.TextDetector'), \
                    patch('relay.runtime.Egress', return_value=Output()) as output, \
                    patch('relay.runtime.NetworkInput', return_value=Source()):
                session.return_value.get_providers.return_value = active
                engine = make_engine('/synthetic-cache', provider=provider, delay_seconds=delay, **options)
                stopped = threading.Event()
                stopped.set()
                summary = run(engine, RelayAddress('127.0.0.1'), Credentials.generate(), Credentials.generate(),
                              directory, stopped, encoder=encoder)
                saved = json.loads((Path(directory) / 'runtime.json').read_text())
                self.assertEqual(saved, summary)
                self.assertEqual(saved['status'], 'stopped')
                configuration = saved['configuration']
                self.assertEqual(configuration['encoder'], encoder)
                self.assertEqual(output.call_args.args[-1], encoder)
                self.assertEqual(configuration['delay_seconds'], delay)
                for name, expected_rate, expected_floor in (('fast', 8., .5), ('accurate', rate, floor)):
                    self.assertEqual(configuration['lanes'][name], {
                        'rate_hz': expected_rate, 'box_thresh': expected_floor,
                        'execution_provider': active[0], 'active_execution_providers': active})
                    self.assertEqual(saved['engine']['lanes'][name]['rate_hz'], expected_rate)

    def test_legacy_runtime_cli_propagates_cpu_delay_and_preserves_defaults(self):
        from relay.runtime import main
        defaults = (([], {}, {}), (['--cpu'], {'provider': 'cpu', 'delay_seconds': 2.5}, {'encoder': 'libx264'}))
        overrides = [([*cpu, '--delay-seconds', str(delay)],
                      {**({'provider': 'cpu'} if cpu else {}), 'delay_seconds': delay},
                      {'encoder': 'libx264'} if cpu else {})
                     for cpu in ([], ['--cpu']) for delay in (.5, 2.5, 3.25, 10)]
        for extra, expected, run_options in (*defaults, *overrides):
            with self.subTest(extra=extra), patch('sys.argv', ['relay.runtime', '--host', '127.0.0.1', *extra]), \
                    patch('relay.runtime.MediaMTX'), patch('relay.runtime.make_engine') as factory, \
                    patch('relay.runtime.run') as runtime, patch('relay.runtime.signal.signal'):
                main()
                self.assertEqual(factory.call_args.kwargs, expected)
                self.assertEqual(runtime.call_args.kwargs, run_options)
        for cpu in ([], ['--cpu']):
            for value in ('nan', 'inf', '-inf', '-.1', '0', '.25', '10.000001'):
                with self.subTest(cpu=cpu, value=value), \
                        patch('sys.argv', ['relay.runtime', '--host', '127.0.0.1', *cpu, f'--delay-seconds={value}']), \
                        patch('relay.runtime.Credentials.generate') as credentials, \
                        patch('relay.runtime.MediaMTX') as media, patch('relay.runtime.make_engine') as factory, \
                        patch('relay.runtime.run') as runtime, patch('relay.runtime.signal.signal'), \
                        redirect_stderr(StringIO()) as error:
                    with self.assertRaises(SystemExit) as ended:
                        main()
                    self.assertEqual(ended.exception.code, 2)
                    self.assertIn('Presentation delay', error.getvalue())
                    credentials.assert_not_called()
                    media.assert_not_called()
                    factory.assert_not_called()
                    runtime.assert_not_called()

    def test_callback_key_is_consumed_by_production_bandwidthtest_route_in_memory(self):
        captured = []
        class Engine:
            delay = .1
            stats = {}
            def hold(self, *args, **kwargs):
                pass
            def submit(self, *args, **kwargs):
                pass
            def close(self):
                pass
        class Output:
            error_code = error_details = None
            count = max_write_seconds = recovery_count = 0
            recovery_events = ()
            def __init__(self, urls, *args):
                captured.extend(urls)
            def write(self, frame, pcm):
                raise AssertionError('Stopped runtime must not encode a frame')
            def close(self):
                pass
        class Source:
            error_code = None
            high_water = active_generation = 0
            last_failure = None
            timestamp_issues = {}
            def __init__(self, url):
                pass
            def close(self):
                pass
        class Forwarder:
            def __init__(self, host, port):
                assert (host, port) == ('live.twitch.tv', 443)
            port = 54321
            stats = {'connections': 0, 'failures': 0}
            def __enter__(self):
                return self
            def close(self):
                pass
        stopped = threading.Event()
        stopped.set()
        phone, internal = Credentials.generate(), Credentials.generate()
        from shield.cli import parser
        self.assertFalse(parser().parse_args(['run', '--host', '127.0.0.1']).twitch_bandwidth_test)
        with tempfile.TemporaryDirectory() as directory, patch('relay.runtime.Egress', Output), \
                patch('relay.runtime.NetworkInput', Source), patch('relay.tls_forwarder.TLSForwarder', Forwarder):
            # A configured/stored key alone must not even form a Twitch URL.
            with patch('relay.security.TwitchDestination.destination', side_effect=AssertionError('default route formed Twitch URL')):
                run(Engine(), RelayAddress('127.0.0.1'), phone, internal, directory, stopped,
                    width=32, height=32, control_ready=lambda control:
                    control.set_stream_key('SYNTHETIC-ROUTE-SENTINEL'))
            self.assertEqual(len(captured), 1)
            self.assertTrue(captured[0].startswith('rtmp://127.0.0.1:19350/shielded?'))
            captured.clear()
            self.assertTrue(parser().parse_args(['run', '--host', '127.0.0.1', '--twitch-bandwidth-test']).twitch_bandwidth_test)
            run(Engine(), RelayAddress('127.0.0.1'), phone, internal, directory, stopped,
                width=32, height=32, control_ready=lambda control:
                control.set_stream_key('SYNTHETIC-ROUTE-SENTINEL'), publish_twitch=True)
            self.assertEqual(len(captured), 2)
            self.assertTrue(captured[0].startswith('rtmp://127.0.0.1:19350/shielded?'))
            self.assertEqual(captured[1],
                             'rtmp://127.0.0.1:54321/app/SYNTHETIC-ROUTE-SENTINEL?bandwidthtest=true')
            summary = (Path(directory) / 'runtime.json').read_text()
            self.assertNotIn('SYNTHETIC-ROUTE-SENTINEL', summary)
            self.assertNotIn(internal.password, summary)
            self.assertEqual(json.loads(summary)['status'], 'stopped')
            import asyncio
            from shield.app.live import LiveModeError
            grant = asyncio.run(approved_live())
            captured.clear()
            run(Engine(), RelayAddress('127.0.0.1'), phone, internal, directory, stopped,
                width=32, height=32, control_ready=lambda control:
                control.set_stream_key('SYNTHETIC-ROUTE-SENTINEL'), publish_twitch=True,
                twitch_live=True, live_approval=grant)
            self.assertEqual(captured[1], 'rtmp://127.0.0.1:54321/app/SYNTHETIC-ROUTE-SENTINEL')
            with self.assertRaises(LiveModeError):
                grant.consume()


class RuntimeWriterFailure(unittest.TestCase):
    def test_phone_context_cleanup_precedes_relay_teardown_on_stop_failure_and_init_error(self):
        from contextlib import contextmanager
        for failure in ('stop', 'sender-check', 'context-enter', 'input-init'):
            with self.subTest(failure=failure):
                events = []
                stopped = threading.Event()
                class Engine:
                    delay = 1
                    stats = {}
                    def hold(self, *args, **kwargs):
                        pass
                    def submit(self, *args, **kwargs):
                        pass
                    def poll(self, *args, **kwargs):
                        return []
                    def close(self):
                        events.append('engine-close')
                class Output:
                    error_code = error_details = None
                    count = max_write_seconds = recovery_count = 0
                    recovery_events = ()
                    def __init__(self, *args):
                        events.append('output-ready')
                    def close(self):
                        events.append('output-close')
                class Source:
                    error_code = last_failure = None
                    high_water = active_generation = 0
                    timestamp_issues = {}
                    def __init__(self, *args):
                        if failure == 'input-init':
                            raise RuntimeError('synthetic-input-init')
                        events.append('input-ready')
                    def drain(self):
                        return []
                    def close(self):
                        events.append('input-close')
                class Sender:
                    def check(self):
                        events.append('sender-check')
                        if failure == 'sender-check':
                            raise RuntimeError('synthetic-worker-error')
                        stopped.set()
                @contextmanager
                def factory(address, phone):
                    events.append('factory')
                    try:
                        if failure == 'context-enter':
                            raise RuntimeError('synthetic-start-error')
                        yield Sender()
                    finally:
                        events.append('sender-joined')
                with patch('relay.runtime.Egress', Output), patch('relay.runtime.NetworkInput', Source):
                    def execute():
                        return run(Engine(), RelayAddress('127.0.0.1'), Credentials.generate(),
                            Credentials.generate(), None, stopped, seconds=1, width=32, height=32,
                            phone_input=factory)
                    if failure == 'stop':
                        self.assertEqual(execute()['status'], 'stopped')
                    else:
                        with self.assertRaisesRegex(RuntimeError, 'Relay transport failed'):
                            execute()
                self.assertIn('output-close', events)
                self.assertIn('engine-close', events)
                if failure == 'input-init':
                    self.assertNotIn('factory', events)
                else:
                    self.assertEqual(events.count('sender-joined'), 1)
                    for closed in ('input-close', 'output-close', 'engine-close'):
                        self.assertLess(events.index('sender-joined'), events.index(closed))

    def failure(self, write_fails, close_fails, stop_on_write=False):
        from contextlib import redirect_stderr, redirect_stdout
        import io
        import traceback
        from relay.stream import EgressError
        from recovery_fixture import engine, record

        # This intentionally invalid synthetic destination is never contacted.
        private_url = 'rtmp://127.0.0.1:1/shielded?password=SYNTHETIC-PRIVATE-SENTINEL'
        outputs, sources = [], []
        stopped = threading.Event()

        class Output:
            error_code = 'egress-recovery-limit' if write_fails else None
            error_details = None
            count = max_write_seconds = recovery_count = 0
            recovery_events = ()

            def __init__(self, *args):
                self.closed = False
                self.attempts = 0
                outputs.append(self)

            def write(self, frame, pcm):
                self.attempts += 1
                if stop_on_write:
                    stopped.set()
                if write_fails:
                    try:
                        raise OSError(private_url)
                    except OSError:
                        raise EgressError('egress-recovery-limit')
                self.count += 1
                return True

            def close(self):
                self.closed = True
                if close_fails:
                    raise OSError(private_url)

        class Source:
            error_code = last_failure = None
            high_water = active_generation = 0
            timestamp_issues = {}

            def __init__(self, url):
                self.closed = False
                sources.append(self)

            def drain(self):
                return []

            def close(self):
                self.closed = True

        source_engine = engine(delay=.01)
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory, patch('relay.runtime.Egress', Output), \
                patch('relay.runtime.NetworkInput', Source), redirect_stdout(output), redirect_stderr(output):
            with self.assertRaises(RuntimeError) as caught:
                run(source_engine, RelayAddress('127.0.0.1'), Credentials.generate(), Credentials.generate(),
                    directory, stopped, seconds=.15, width=64, height=32, encoder='libx264')
            summary_text = (Path(directory) / 'runtime.json').read_text()
            diagnostics = ''.join(traceback.format_exception(caught.exception)) + output.getvalue() + summary_text
            self.assertNotIn(private_url, diagnostics)
            self.assertNotIn('SYNTHETIC-PRIVATE-SENTINEL', diagnostics)
            self.assertGreater(outputs[0].attempts, 0, 'the terminal path must reach the actual writer')
            self.assertTrue(outputs[0].closed)
            self.assertTrue(sources[0].closed)
            self.assertFalse(any(thread.name == 'relay-egress-writer' for thread in threading.enumerate()))
            self.assertTrue(all(not lane.thread.is_alive() for lane in source_engine.lanes.values()))
            summary = json.loads(summary_text)
            record(self, {'summary': summary, 'surfaced_message': str(caught.exception),
                          'write_attempts': outputs[0].attempts, 'output_closed': outputs[0].closed,
                          'input_closed': sources[0].closed, 'writer_and_engine_threads_reaped': True},
                   secrets=(private_url, 'SYNTHETIC-PRIVATE-SENTINEL'))
            return str(caught.exception), summary

    def test_terminal_write_error_survives_successful_cleanup(self):
        message, summary = self.failure(write_fails=True, close_fails=False)
        self.assertEqual(message, 'Relay transport failed (upstream diagnostics suppressed)')
        self.assertEqual(summary['status'], 'failed')
        self.assertEqual(summary['failure']['output_code'], 'egress-recovery-limit')
        self.assertEqual(summary['cleanup_errors'], [])

    def test_actual_writer_cleanup_failure_is_reported(self):
        message, summary = self.failure(write_fails=False, close_fails=True)
        self.assertEqual(message, 'Relay cleanup failed: EgressWriter')
        self.assertNotIn('failure', summary)
        self.assertEqual(summary['cleanup_errors'], ['EgressWriter'])
        self.assertGreater(summary['output_frames'], 0, 'the real runtime must have written frames')

    def test_terminal_write_error_stays_primary_when_cleanup_also_fails(self):
        message, summary = self.failure(write_fails=True, close_fails=True)
        self.assertEqual(message, 'Relay transport failed (upstream diagnostics suppressed)')
        self.assertEqual(summary['failure']['output_code'], 'egress-recovery-limit')
        self.assertEqual(summary['cleanup_errors'], ['EgressWriter'])

    def test_terminal_error_during_stop_is_not_lost_without_another_tick(self):
        message, summary = self.failure(write_fails=True, close_fails=False, stop_on_write=True)
        self.assertEqual(message, 'Relay transport failed (upstream diagnostics suppressed)')
        self.assertEqual(summary['status'], 'failed')
        self.assertEqual(summary['failure']['output_code'], 'egress-recovery-limit')
        self.assertEqual(summary['cleanup_errors'], [])


async def approved_live():
    from aiohttp import ClientSession
    from shield.app.live import authorize_live
    from shield.twitch.http import TwitchHTTP
    from test_live_mode import LiveTwitch, Terminal, user_session
    async with LiveTwitch() as mock, ClientSession() as network:
        http = TwitchHTTP(network, mock_origin=mock.origin)
        with patch.dict('os.environ', {'TWITCH_BROADCASTER_LOGIN': 'naie'}), \
                patch('builtins.open', return_value=Terminal('LIVE naie\n')):
            return await authorize_live(user_session(http), http)


class RuntimeLiveApproval(unittest.IsolatedAsyncioTestCase):
    async def test_prepared_sender_starts_only_after_live_approval_is_consumed(self):
        from contextlib import contextmanager
        from shield.app.live import LiveModeError
        events = []
        stopped = threading.Event()
        class Engine:
            delay = 1
            stats = {}
            def hold(self, *args, **kwargs):
                pass
            def submit(self, *args, **kwargs):
                pass
            def poll(self, *args, **kwargs):
                return []
            def close(self):
                events.append('engine-close')
        class Output:
            error_code = error_details = None
            count = max_write_seconds = recovery_count = 0
            recovery_events = ()
            def __init__(self, *args):
                events.append('output-ready')
            def close(self):
                events.append('output-close')
        class Source:
            error_code = last_failure = None
            high_water = active_generation = 0
            timestamp_issues = {}
            def __init__(self, *args):
                events.append('input-ready')
            def drain(self):
                return []
            def close(self):
                events.append('input-close')
        class Forwarder:
            port = 54321
            stats = {}
            def __init__(self, *args):
                events.append('verified-forwarder')
            def __enter__(self):
                return self
            def close(self):
                events.append('forwarder-close')
        class Sender:
            def check(self):
                stopped.set()
        grant = await approved_live()
        @contextmanager
        def factory(address, phone):
            # The authentic local authorization fixture issued this object;
            # entering a publisher cannot race ahead of its one-shot consume.
            with self.assertRaises(LiveModeError):
                grant.consume()
            events.append('sender-enter')
            try:
                yield Sender()
            finally:
                events.append('sender-joined')
        def execute(approval):
            return run(Engine(), RelayAddress('100.80.2.3'), Credentials.generate(),
                Credentials.generate(), None, stopped, seconds=1, width=32, height=32,
                phone_input=factory, publish_twitch=True, twitch_live=True,
                live_approval=approval, control_ready=lambda control: control.set_stream_key('SYNTHETIC-KEY'))
        with patch('relay.runtime.Egress', Output), patch('relay.runtime.NetworkInput', Source), \
                patch('relay.tls_forwarder.TLSForwarder', Forwarder):
            with self.assertRaises(RuntimeError):
                execute(None)
            self.assertEqual(events, ['engine-close'])
            events.clear()
            self.assertEqual(execute(grant)['status'], 'stopped')
        for ready in ('verified-forwarder', 'output-ready', 'input-ready'):
            self.assertLess(events.index(ready), events.index('sender-enter'))
        for closed in ('input-close', 'output-close', 'engine-close'):
            self.assertLess(events.index('sender-joined'), events.index(closed))

    async def test_real_runtime_refuses_missing_or_consumed_approval_before_any_route(self):
        from recovery_fixture import engine
        grant = await approved_live()
        grant.consume()
        for approval in (None, object(), grant):
            with self.subTest(approval=type(approval).__name__), \
                    patch('relay.runtime.Egress') as output, \
                    patch('relay.runtime.NetworkInput') as source, \
                    patch('relay.tls_forwarder.TLSForwarder', side_effect=AssertionError('verified route opened before approval')) as forwarder:
                stopped = threading.Event()
                stopped.set()
                with self.assertRaises(RuntimeError):
                    run(engine(), RelayAddress('127.0.0.1'), Credentials.generate(),
                        Credentials.generate(), None, stopped, width=32, height=32,
                        publish_twitch=True, twitch_live=True, live_approval=approval)
                output.assert_not_called()
                source.assert_not_called()
                forwarder.assert_not_called()

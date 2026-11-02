"""Application auth/key/control wiring across real loopback HTTP and SDK sockets."""
import asyncio
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import AsyncMock, patch

from aiohttp import ClientSession

from shield.app.session import TwitchControls, login
from shield.cli import doctor, parser, validate, execute, main
from shield.control import Control
from shield.twitch.http import TwitchHTTP
from relay.live import RelayControl
from mock_twitch import MockTwitch, until
from network import local_network


class EngineControl:
    def __init__(self):
        self.control = Control()
        self.control.update_coverage(True, 'fresh', 0)

    def hold(self, active, source, reason, now=None):
        return self.control.set_hold(active, source, reason, now or 0)


class CommandLine(unittest.TestCase):
    def test_mock_demo_accepts_only_loopback_without_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.json'
            source.write_text('{}')
            arguments = ['run', '--host', '127.0.0.1', '--mock-origin', 'http://127.0.0.1:18080',
                         '--demo-source', str(source), '--demo-receipt', str(root / 'sender.jsonl'),
                         '--archive', str(root / 'relay'), '--seconds', '230', '--dashboard']
            args = parser().parse_args(arguments)
            validate(args)
            self.assertFalse(args.local_only or args.twitch_live or args.twitch_bandwidth_test)
            self.assertIsNone(args.local_sink)
            for extra in (['--host', '127.0.0.2'], ['--twitch-live'], ['--twitch-bandwidth-test'],
                          ['--local-only'], ['--phone-setup'], ['--mock-origin', ''],
                          ['--local-sink', 'rtmp://127.0.0.1:19351/shielded']):
                with self.subTest(extra=extra), self.assertRaises(ValueError):
                    validate(parser().parse_args([*arguments, *extra]))

    def test_invalid_delay_and_login_only_cpu_options_fail_before_authentication(self):
        modes = (['run', '--local-only'], ['run'], ['run', '--twitch-live'],
                 ['run', '--twitch-bandwidth-test'], ['login', '--run'])
        invalid = [[*mode, *cpu, f'--delay-seconds={value}']
                   for mode in modes for cpu in ([], ['--cpu'])
                   for value in ('nan', 'inf', '-inf', '-.1', '0', '.25', '10.000001')]
        for arguments in (*invalid, ['login', '--cpu'], ['login', '--delay-seconds', '2.5']):
            with self.subTest(arguments=arguments):
                args = parser().parse_args([*arguments, '--host', '127.0.0.1'])
                with self.assertRaisesRegex(ValueError, 'delay|CPU'):
                    validate(args)
                with patch('aiohttp.ClientSession') as network, \
                        patch('shield.app.session.login', new_callable=AsyncMock, return_value=None) as login, \
                        patch('relay.security.Credentials.generate') as credentials, \
                        patch('relay.mediamtx.MediaMTX') as media, \
                        patch('relay.runtime.make_engine') as factory, \
                        patch('shield.cli.resource.setrlimit'):
                    with self.assertRaisesRegex(ValueError, 'delay|CPU'):
                        asyncio.run(execute(args))
                    login.assert_not_awaited()
                    network.assert_not_called()
                    credentials.assert_not_called()
                    media.assert_not_called()
                    factory.assert_not_called()
        for mode in modes:
            for cpu in ([], ['--cpu']):
                for value in ('.5', '2.5', '10'):
                    with self.subTest(mode=mode, cpu=cpu, accepted=value):
                        args = parser().parse_args([*mode, *cpu, '--host', '127.0.0.1', '--delay-seconds', value])
                        validate(args)
                        self.assertEqual(args.cpu, bool(cpu))
                        self.assertEqual(args.delay_seconds, float(value))

    def test_missing_bind_is_actionable_before_any_authentication(self):
        for arguments in (['run', '--local-only'], ['login', '--run']):
            with self.subTest(arguments=arguments), patch.dict('os.environ', {}, clear=True):
                error = StringIO()
                with patch('shield.cli.execute', side_effect=AssertionError('authentication reached')) as execute_mock:
                    with redirect_stderr(error), self.assertRaises(SystemExit) as stopped:
                        main(arguments)
                    self.assertEqual(stopped.exception.code, 2)
                    execute_mock.assert_not_called()
                for hint in ('--host', '127.0.0.0/8', '100.64.0.0/10', 'shield doctor'):
                    self.assertIn(hint, error.getvalue())

    def test_synthetic_soak_defaults_to_loopback_even_with_phone_bind_environment(self):
        import argparse
        from relay import soak

        class NativeBoundary(Exception):
            pass

        parsed = []
        original = argparse.ArgumentParser.parse_args
        def observe(parser, *args, **kwargs):
            result = original(parser, *args, **kwargs)
            parsed.append(result)
            return result
        with patch.dict('os.environ', {'SHIELD_BIND_HOST': '100.80.1.2'}), \
                patch.object(argparse.ArgumentParser, 'parse_args', observe), \
                patch('relay.soak.require_queue_lease', side_effect=NativeBoundary):
            with self.assertRaises(NativeBoundary):
                soak.main(['--output', 'unused-synthetic-output', '--model-cache', 'unused-cache'])
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].host, '127.0.0.1')


class Application(unittest.IsolatedAsyncioTestCase):
    async def test_login_key_and_eventsub_use_one_memory_session_and_preserve_manual_hold(self):
        with local_network(), patch('shield.app.session.TokenStore', side_effect=AssertionError('unexpected disk store')):
            async with MockTwitch() as mock, ClientSession() as network:
                prompts = []
                http = TwitchHTTP(network, mock_origin=mock.origin)
                user = await login(http, 'synthetic-client', '1', asyncio.Event(), present=prompts.append)
                self.assertEqual(len(prompts), 1)
                stopped = threading.Event()
                controls = TwitchControls(user, http, stopped, mock_origin=mock.origin)
                engine = EngineControl()
                control = RelayControl(engine)
                try:
                    await controls.prepare()
                    await asyncio.to_thread(controls.register, control)
                    await until(lambda: controls.events.phase == 'ready')
                    self.assertTrue(control.twitch.configured)
                    self.assertFalse(stopped.is_set())
                    self.assertEqual(engine.control.state, 'LIVE')
                    await mock.send()
                    await until(lambda: engine.control.state == 'HOLD')
                    control.hold(True)
                    await mock.send('!shield resume', actor='1')
                    await until(lambda: controls.events.remembered >= 2)
                    self.assertEqual(engine.control.state, 'HOLD')
                    await mock.send(topic='channel.shield_mode.begin')
                    await until(lambda: controls.events.remembered >= 3)
                    control.hold(False)
                    self.assertEqual(engine.control.state, 'HOLD')
                    await mock.send(topic='channel.shield_mode.end')
                    await until(lambda: engine.control.state == 'LIVE')
                    self.assertEqual(mock.calls.count(('GET', '/helix/streams/key')), 1)
                finally:
                    await controls.close()
                    control.set_stream_key(None)
                self.assertFalse(control.twitch.configured)
                self.assertEqual(engine.control.state, 'HOLD')

    async def test_nonlocal_mock_and_fake_sink_cannot_publish_real_twitch(self):
        for arguments in (['--mock-origin', 'http://0.0.0.0:8080'],
                          ['--mock-origin', 'http://127.0.0.1:8080', '--remember'],
                          ['--mock-origin', 'http://127.0.0.1:8080', '--twitch-bandwidth-test'],
                          ['--local-only', '--twitch-bandwidth-test'],
                          ['--local-sink', 'rtmp://live.twitch.tv/app/fake'],
                          ['--mock-origin', 'http://127.0.0.1:8080', '--local-sink', 'rtmp://127.0.0.1:1935/camera'],
                          ['--accurate-rate-hz', '0'], ['--accurate-rate-hz', '30.1'],
                          ['--accurate-rate-hz', 'nan'], ['--accurate-rate-hz', 'inf'],
                          ['--accurate-box-thresh', '-.1'], ['--accurate-box-thresh', '1.1'],
                          ['--accurate-box-thresh', 'nan'], ['--accurate-box-thresh', 'inf']):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                validate(parser().parse_args(['run', '--host', '127.0.0.1', *arguments]))
        report = doctor()
        self.assertFalse(report['ready'])
        self.assertIn('UNQUALIFIED', report['srt'])
        self.assertIn('UNQUALIFIED', report['privacy'])
        self.assertNotIn('SYNTHETIC-INTEGRATION-KEY', json.dumps(report))

    async def test_cli_login_exits_without_a_saved_credential_or_real_network(self):
        with local_network(), patch('shield.app.session.TokenStore', side_effect=AssertionError('unexpected store')):
            async with MockTwitch() as mock:
                output = StringIO()
                with redirect_stdout(output), patch.dict('os.environ', {}, clear=True):
                    await execute(parser().parse_args(['login', '--mock-origin', mock.origin]))
                self.assertIn('Memory-only session ends here', output.getvalue())
                self.assertNotIn('synthetic-access', output.getvalue())
                self.assertEqual(mock.calls.count(('POST', '/oauth2/token')), 1)
                self.assertNotIn(('GET', '/helix/streams/key'), mock.calls)

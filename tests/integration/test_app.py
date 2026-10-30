"""Application auth/key/control wiring across real loopback HTTP and SDK sockets."""
import asyncio
from contextlib import redirect_stdout
from io import StringIO
import json
import threading
import unittest
from unittest.mock import patch

from aiohttp import ClientSession

from shield.app.session import TwitchControls, login
from shield.cli import doctor, parser, validate, execute
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
                          ['--mock-origin', 'http://127.0.0.1:8080', '--local-sink', 'rtmp://127.0.0.1:1935/camera']):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                validate(parser().parse_args(['run', *arguments]))
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

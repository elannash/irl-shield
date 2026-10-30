"""Live-mode authorization and CLI wiring with synthetic loopback HTTP only."""
import copy
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from io import StringIO
import os
import pickle
import time
import unittest
from unittest.mock import call, patch

from aiohttp import ClientSession, web

from shield.app.live import LiveApproval, LiveModeError, authorize_live
from shield.cli import execute, main, parser, validate
from shield.twitch.auth import DeviceAuth, Secret, Tokens, TwitchError, UserSession
from shield.twitch.http import TwitchHTTP
from mock_twitch import MockTwitch
from network import local_network


class LiveTwitch(MockTwitch):
    def __init__(self):
        super().__init__()
        self.validation = {'client_id': 'synthetic-client', 'user_id': '1', 'login': 'naie',
            'scopes': ['user:read:chat', 'moderator:read:shield_mode', 'channel:read:stream_key'],
            'expires_in': 14400}
        self.status = 200

    async def route(self, request):
        if request.path == '/oauth2/validate':
            self.calls.append((request.method, request.path))
            if request.method != 'GET' or request.headers.get('Authorization') != 'OAuth synthetic-access':
                return web.json_response({'error': 'unexpected synthetic request'}, status=400)
            return web.json_response(self.validation, status=self.status)
        return await super().route(request)


class Terminal(StringIO):
    """A real canonical PTY descriptor for the attended-read boundary."""
    def __init__(self, response):
        super().__init__()
        self.master, self.slave = os.openpty()
        # Canonical EOF also makes deliberately incomplete input readable.
        os.write(self.master, response.encode() + (b'\x04\x04' if not response.endswith('\n') else b''))
        self.output = StringIO()

    def fileno(self):
        return self.slave

    def isatty(self):
        return True

    def write(self, value):
        return self.output.write(value)

    def close(self):
        if not self.closed:
            os.close(self.master)
            os.close(self.slave)
        super().close()


def user_session(http):
    return UserSession(DeviceAuth('synthetic-client', http),
        Tokens(Secret('synthetic-access'), Secret('synthetic-refresh'), time.monotonic() + 14400), '1')


class LiveAuthorization(unittest.IsolatedAsyncioTestCase):
    async def test_attended_confirmation_works_with_a_nonseekable_os_terminal(self):
        with local_network():
            async with LiveTwitch() as mock, ClientSession() as network:
                http = TwitchHTTP(network, mock_origin=mock.origin)
                user = user_session(http)
                await user.access_token()
                master, slave = os.openpty()
                original_open = open
                try:
                    os.write(master, b'LIVE naie\n')
                    def open_terminal(path, mode):
                        self.assertEqual(path, '/dev/tty')
                        return original_open(os.ttyname(slave), mode)
                    with patch('builtins.open', side_effect=open_terminal):
                        approval = await authorize_live(user, http)
                    approval.consume()
                finally:
                    os.close(master)
                    os.close(slave)

    async def test_fresh_naie_validation_and_attended_confirmation_issue_one_use_approval(self):
        with local_network():
            async with LiveTwitch() as mock, ClientSession() as network:
                http = TwitchHTTP(network, mock_origin=mock.origin)
                user = user_session(http)
                await user.access_token()
                self.assertEqual(mock.calls, [('GET', '/oauth2/validate')])
                terminal = Terminal('LIVE naie\n')
                def open_terminal(path, mode):
                    self.assertEqual(path, '/dev/tty')
                    self.assertIn(mode, ('r', 'w'))
                    self.assertEqual(mock.calls, [('GET', '/oauth2/validate'), ('GET', '/oauth2/validate')])
                    return terminal
                with patch('builtins.open', side_effect=open_terminal):
                    approval = await authorize_live(user, http)
                self.assertIsInstance(approval, LiveApproval)
                for duplicate in (copy.copy, copy.deepcopy, pickle.dumps):
                    with self.subTest(duplicate=duplicate.__name__), self.assertRaises(TypeError):
                        duplicate(approval)
                approval.consume()
                with self.assertRaises(LiveModeError):
                    approval.consume()
                with self.assertRaises(LiveModeError):
                    LiveApproval()
                with patch('builtins.open', return_value=Terminal('LIVE naie\n')) as repeated:
                    second = await authorize_live(user, http)
                self.assertEqual(repeated.call_args_list, [call('/dev/tty', 'r'), call('/dev/tty', 'w')])
                self.assertEqual(mock.calls.count(('GET', '/oauth2/validate')), 3)
                second.consume()

    async def test_cached_session_cannot_bypass_fresh_identity_scopes_expiry_or_http_failure(self):
        cases = [({'login': 'nale'}, 200), ({'login': 'someone_else'}, 200),
                 ({'login': 'Naie'}, 200), ({'login': None}, 200),
                 ({'user_id': '2'}, 200), ({'user_id': 1}, 200),
                 ({'client_id': 'different-client'}, 200),
                 ({'scopes': ['channel:read:stream_key']}, 200),
                 ({'scopes': ['user:read:chat', 'moderator:read:shield_mode',
                              'channel:read:stream_key', 'channel:manage:broadcast']}, 200),
                 ({'expires_in': 0}, 200), ({'expires_in': True}, 200),
                 ({'expires_in': None}, 200), ({'expires_in': float('inf')}, 200),
                 ({'message': 'synthetic-remote-secret'}, 401),
                 ({'message': 'synthetic-remote-secret'}, 503)]
        with local_network():
            async with LiveTwitch() as mock, ClientSession() as network:
                http = TwitchHTTP(network, mock_origin=mock.origin)
                original = mock.validation.copy()
                for changes, status in cases:
                    with self.subTest(changes=changes, status=status):
                        mock.validation, mock.status = original.copy(), 200
                        user = user_session(http)
                        await user.access_token()
                        before = len(mock.calls)
                        mock.validation.update(changes)
                        mock.status = status
                        with patch('builtins.open', return_value=Terminal('LIVE naie\n')) as terminal:
                            with self.assertRaises(LiveModeError) as denied:
                                await authorize_live(user, http)
                        self.assertEqual(len(mock.calls), before + 1)
                        self.assertEqual(str(denied.exception), str(LiveModeError()))
                        self.assertNotIn('synthetic-remote-secret', str(denied.exception))
                        terminal.assert_not_called()
                for malformed in ([], 'synthetic-remote-secret'):
                    with self.subTest(malformed=malformed):
                        mock.validation, mock.status = original.copy(), 200
                        user = user_session(http)
                        await user.access_token()
                        mock.validation = malformed
                        with patch('builtins.open') as terminal, self.assertRaises(LiveModeError):
                            await authorize_live(user, http)
                        terminal.assert_not_called()

    async def test_confirmation_requires_exact_completed_line_on_a_working_attended_tty(self):
        cases = [('no tty', '', 'open'), ('not attended', 'LIVE naie\n', 'isatty'),
                 ('EOF', '', None), ('wrong channel', 'LIVE nale\n', None),
                 ('incomplete', 'LIVE naie', None), ('whitespace', 'LIVE naie \n', None),
                 ('wrong case', 'live naie\n', None), ('too long', 'LIVE naie' + 'x' * 80 + '\n', None),
                 ('read failure', 'LIVE naie\n', 'fileno'),
                 ('write failure', 'LIVE naie\n', 'write'),
                 ('flush failure', 'LIVE naie\n', 'flush')]
        with local_network():
            async with LiveTwitch() as mock, ClientSession() as network:
                http = TwitchHTTP(network, mock_origin=mock.origin)
                user = user_session(http)
                await user.access_token()
                for reason, response, fault in cases:
                    with self.subTest(reason=reason), ExitStack() as stack:
                        terminal = Terminal(response)
                        if fault == 'open':
                            opened = stack.enter_context(patch('builtins.open', side_effect=OSError('synthetic-remote-secret')))
                        else:
                            opened = stack.enter_context(patch('builtins.open', return_value=terminal))
                            if fault == 'isatty':
                                stack.enter_context(patch.object(terminal, 'isatty', return_value=False))
                            elif fault:
                                stack.enter_context(patch.object(terminal, fault, side_effect=OSError('synthetic-remote-secret')))
                        with self.assertRaises(LiveModeError) as denied:
                            await authorize_live(user, http)
                        self.assertEqual(opened.call_args_list,
                            [call('/dev/tty', 'r')] if fault == 'open' else
                            [call('/dev/tty', 'r'), call('/dev/tty', 'w')])
                        self.assertEqual(str(denied.exception), str(LiveModeError()))
                        terminal.close()

    async def test_validation_that_expires_while_owner_confirms_cannot_issue_approval(self):
        with local_network():
            async with LiveTwitch() as mock, ClientSession() as network:
                http = TwitchHTTP(network, mock_origin=mock.origin)
                now = [100.]
                user = UserSession(DeviceAuth('synthetic-client', http, clock=lambda: now[0]),
                    Tokens(Secret('synthetic-access'), Secret('synthetic-refresh'), 14400), '1')
                await user.access_token()
                mock.validation['expires_in'] = 1
                terminal = Terminal('LIVE naie\n')
                def descriptor():
                    now[0] = 102.
                    return terminal.slave
                with patch('builtins.open', return_value=terminal), \
                        patch.object(terminal, 'fileno', side_effect=descriptor), \
                        self.assertRaises(LiveModeError):
                    await authorize_live(user, http)


class LiveCommandLine(unittest.TestCase):
    def test_live_and_bandwidth_flags_are_explicit_and_mutually_exclusive_before_auth(self):
        for command in ('login', 'run'):
            with self.subTest(command=command):
                live = parser().parse_args([command, '--host', '127.0.0.1', '--twitch-live'])
                self.assertTrue(live.twitch_live)
                self.assertFalse(live.twitch_bandwidth_test)
                test = parser().parse_args([command, '--host', '127.0.0.1', '--twitch-bandwidth-test'])
                self.assertTrue(test.twitch_bandwidth_test)
                self.assertFalse(test.twitch_live)
                with patch('shield.cli.execute', side_effect=AssertionError('auth reached')) as execute:
                    error = StringIO()
                    with redirect_stderr(error), self.assertRaises(SystemExit) as stopped:
                        main([command, '--host', '127.0.0.1', '--twitch-live', '--twitch-bandwidth-test'])
                    self.assertEqual(stopped.exception.code, 2)
                    self.assertIn('not allowed with argument', error.getvalue())
                    execute.assert_not_called()

    def test_live_rejects_mock_local_only_and_local_sink_modes(self):
        for extra in (['--local-only'], ['--mock-origin', 'http://127.0.0.1:8080'],
                      ['--local-sink', 'rtmp://127.0.0.1:1935/shielded'],
                      ['--mock-origin', 'http://127.0.0.1:8080',
                       '--local-sink', 'rtmp://127.0.0.1:1935/shielded']):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                validate(parser().parse_args(['run', '--host', '127.0.0.1', '--twitch-live', *extra]))

    def test_live_failures_are_actionable_and_other_upstream_failures_stay_redacted(self):
        for error in (LiveModeError(), TwitchError('synthetic-remote-secret')):
            output, diagnostic = StringIO(), StringIO()
            with self.subTest(error=type(error).__name__), \
                    patch('shield.cli.execute', side_effect=error), \
                    redirect_stderr(diagnostic), redirect_stdout(output):
                self.assertEqual(main(['run', '--host', '127.0.0.1', '--twitch-live']), 1)
            self.assertEqual(output.getvalue(), '')
            self.assertNotIn('synthetic-remote-secret', diagnostic.getvalue())
            if isinstance(error, LiveModeError):
                self.assertIn('naie', diagnostic.getvalue())
                self.assertIn('terminal confirmation', diagnostic.getvalue())
            else:
                self.assertIn('credentialed upstream diagnostics suppressed', diagnostic.getvalue())


class LiveWiring(unittest.IsolatedAsyncioTestCase):
    async def test_publication_requires_explicit_mode_and_live_approval_precedes_key_and_media(self):
        modes = [((), False, False), (('--twitch-bandwidth-test',), True, False),
                 (('--twitch-live',), True, True), (('mock',), False, False)]
        for flags, publication, live in modes:
            with self.subTest(flags=flags), local_network():
                async with LiveTwitch() as mock:
                    class RoutedHTTP(TwitchHTTP):
                        def __init__(self, session, **kwargs):
                            super().__init__(session, mock_origin=mock.origin)

                    opened = []
                    def open_terminal(path, mode):
                        self.assertEqual(path, '/dev/tty')
                        opened.append(mode)
                        self.assertNotIn(('GET', '/helix/streams/key'), mock.calls)
                        return Terminal('LIVE naie\n' if mode == 'r' else '')

                    def runtime(*args, **kwargs):
                        self.assertEqual(kwargs['publish_twitch'], publication)
                        self.assertEqual(kwargs['twitch_live'], live)
                        self.assertIn(('GET', '/helix/streams/key'), mock.calls)
                        if live:
                            self.assertEqual(opened, ['w', 'r', 'w'])
                            self.assertIsInstance(kwargs['live_approval'], LiveApproval)
                            kwargs['live_approval'].consume()
                        else:
                            self.assertEqual(opened, [] if flags == ('mock',) else ['w'])
                            self.assertIsNone(kwargs['live_approval'])

                    arguments = ['run', '--host', '127.0.0.1']
                    arguments += ['--mock-origin', mock.origin] if flags == ('mock',) else list(flags)
                    with patch.dict('os.environ', {'TWITCH_CLIENT_ID': 'synthetic-client',
                            'TWITCH_BROADCASTER_ID': '1'}, clear=True), \
                            patch('shield.twitch.http.TwitchHTTP', RoutedHTTP), \
                            patch('relay.mediamtx.MediaMTX') as media, \
                            patch('relay.mediamtx.verified_binary'), \
                            patch('relay.runtime.make_engine'), \
                            patch('relay.runtime.run', side_effect=runtime) as run, \
                            patch('builtins.open', side_effect=open_terminal), \
                            patch('shield.app.session.TokenStore', side_effect=AssertionError('unexpected keyring')):
                        await execute(parser().parse_args(arguments))
                    run.assert_called_once()
                    media.assert_called_once()
                    self.assertEqual(mock.calls.count(('GET', '/oauth2/validate')), 2 if live else 1)
                    self.assertEqual(mock.calls.count(('GET', '/helix/streams/key')), 1)

    async def test_wrong_login_stops_cli_before_stream_key_and_media(self):
        with local_network():
            async with LiveTwitch() as mock:
                mock.validation['login'] = 'nale'
                class RoutedHTTP(TwitchHTTP):
                    def __init__(self, session, **kwargs):
                        super().__init__(session, mock_origin=mock.origin)
                with patch.dict('os.environ', {'TWITCH_CLIENT_ID': 'synthetic-client',
                        'TWITCH_BROADCASTER_ID': '1'}, clear=True), \
                        patch('shield.twitch.http.TwitchHTTP', RoutedHTTP), \
                        patch('relay.mediamtx.MediaMTX') as media, \
                        patch('relay.mediamtx.verified_binary', side_effect=AssertionError('media before approval')), \
                        patch('relay.runtime.make_engine') as engine, \
                        patch('relay.runtime.run') as run, \
                        patch('builtins.open', return_value=Terminal('')) as terminal:
                    with self.assertRaises(LiveModeError):
                        await execute(parser().parse_args(['run', '--host', '127.0.0.1', '--twitch-live']))
                self.assertNotIn(('GET', '/helix/streams/key'), mock.calls)
                terminal.assert_called_once_with('/dev/tty', 'w')
                media.assert_not_called()
                engine.assert_not_called()
                run.assert_not_called()


if __name__ == '__main__':
    unittest.main()

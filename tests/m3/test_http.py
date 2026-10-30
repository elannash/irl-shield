import asyncio
import json
import pickle
import unittest
from unittest.mock import Mock

from aiohttp import ClientSession, web

from shield.twitch.auth import DeviceAuth, InvalidToken, Secret, SCOPES, Tokens, UserSession, TwitchError
from shield.twitch.http import TwitchHTTP
from shield.twitch.keys import HelixKeyProvider
from shield.twitch.storage import TokenStore
from test_auth import Clock, success
from network import local_network


class HelixIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        guard = local_network()
        guard.__enter__()
        self.addCleanup(guard.__exit__, None, None, None)
        self.clock, self.requests = Clock(), []
        self.validation_user, self.validate_count = '1', 0
        self.reply = None
        async def route(request):
            self.requests.append((request.method, request.path))
            if self.reply is not None:
                return await self.reply(request)
            if request.path == '/oauth2/token':
                self.assertEqual((await request.post())['refresh_token'], 'synthetic-refresh')
                return web.json_response(success()[1])
            if request.path == '/oauth2/validate':
                self.validate_count += 1
                self.assertEqual(request.headers['Authorization'], 'OAuth synthetic-access')
                return web.json_response(dict(client_id='synthetic-client', user_id=self.validation_user,
                                               scopes=list(SCOPES), expires_in=14400))
            if request.path == '/helix/streams/key':
                self.assertEqual(request.query['broadcaster_id'], '1')
                self.assertEqual(request.headers['Authorization'], 'Bearer synthetic-access')
                return web.json_response({'data': [{'stream_key': 'SYNTHETIC-KEY-SENTINEL'}]})
            raise AssertionError('unexpected mock request')
        app = web.Application()
        app.router.add_route('*', '/{path:.*}', route)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await self.site.start()
        port = self.site._server.sockets[0].getsockname()[1]
        self.client = ClientSession()
        self.http = TwitchHTTP(self.client, mock_origin=f'http://127.0.0.1:{port}')
        self.auth = DeviceAuth('synthetic-client', self.http, clock=lambda: self.clock.now)
        self.session = UserSession(self.auth, Tokens(Secret('synthetic-access'), Secret('synthetic-refresh'), 14400), '1')
        self.addAsyncCleanup(self.client.close)
        self.addAsyncCleanup(self.runner.cleanup)

    async def test_key_stays_redacted_and_wrong_identity_never_requests_key(self):
        provider = HelixKeyProvider(self.session, self.http)
        key = await provider.get_key()
        self.assertEqual(key.reveal(), 'SYNTHETIC-KEY-SENTINEL')
        self.assertNotIn('SYNTHETIC-KEY-SENTINEL', repr(key))
        self.assertNotIn('SYNTHETIC-KEY-SENTINEL', str(key))
        with self.assertRaises(TypeError):
            pickle.dumps(key)
        with self.assertRaises(TypeError):
            json.dumps(key)
        self.validation_user = '2'
        self.clock.now = 3600
        with self.assertRaisesRegex(TwitchError, 'validation failed'):
            await provider.get_key()
        self.assertEqual(self.requests.count(('GET', '/helix/streams/key')), 1)

    async def test_refresh_rotation_and_hourly_validation(self):
        await self.session.access_token()
        self.clock.now = 3599
        await self.session.access_token()
        self.assertEqual(self.validate_count, 1)
        self.clock.now = 3600
        await self.session.access_token()
        self.assertEqual(self.validate_count, 2)
        self.clock.now = 14400
        await self.session.access_token()
        self.assertEqual(self.requests.count(('POST', '/oauth2/token')), 1)
        self.assertEqual(self.validate_count, 3)

    async def test_validation_distinguishes_invalid_token_from_transient_and_claim_errors(self):
        valid = dict(client_id='synthetic-client', user_id='1', scopes=list(SCOPES), expires_in=14400)
        cases = (
            ('unauthorized', 401, {'message': 'SYNTHETIC-SECRET'},
             InvalidToken, 'authorization validation failed'),
            ('unreadable-unauthorized', 401, None,
             InvalidToken, 'authorization validation failed'),
            ('unavailable', 503, {'message': 'SYNTHETIC-SECRET'},
             TwitchError, 'authorization validation failed'),
            ('disconnect', None, {}, TwitchError, 'Twitch HTTP request failed'),
            ('wrong-identity', 200, dict(valid, user_id='2'),
             TwitchError, 'authorization validation failed'),
        )
        for label, status, body, expected_type, expected_message in cases:
            with self.subTest(response=label):
                self.requests.clear()

                async def reply(request):
                    self.assertEqual((request.method, request.path), ('GET', '/oauth2/validate'))
                    if status is None:
                        request.transport.close()
                        return web.Response()
                    if body is None:
                        return web.Response(status=status, text='SYNTHETIC-SECRET')
                    return web.json_response(body, status=status)

                self.reply = reply
                session = UserSession(self.auth, Tokens(Secret('synthetic-access'),
                                      Secret('synthetic-refresh'), 14400), '1')
                with self.assertRaises(TwitchError) as caught:
                    await HelixKeyProvider(session, self.http).get_key()
                self.assertIs(type(caught.exception), expected_type)
                self.assertEqual(str(caught.exception), expected_message)
                self.assertNotIn('SYNTHETIC-SECRET', repr(caught.exception))
                self.assertTrue(self.requests, 'validation never reached the local wire')
                self.assertEqual(set(self.requests), {('GET', '/oauth2/validate')})

    async def test_keyring_is_explicit_and_mock_only(self):
        backend = Mock()
        store = TokenStore(backend)
        for remember in (False, None, 'false', 1):
            store.save('synthetic-client', '1', self.session.tokens, remember=remember)
        backend.set_password.assert_not_called()
        store.save('synthetic-client', '1', self.session.tokens, remember=True)
        backend.get_password.return_value = backend.set_password.call_args.args[2]
        loaded = store.load('synthetic-client', '1')
        self.assertEqual(loaded.refresh.reveal(), 'synthetic-refresh')
        self.assertEqual(loaded.expires_at, 0)
        backend.set_password.side_effect = RuntimeError('SYNTHETIC-KEY-SENTINEL')
        with self.assertRaisesRegex(TwitchError, '^OS keyring write failed$'):
            store.save('synthetic-client', '1', self.session.tokens, remember=True)

    async def test_streamed_json_waits_for_complete_bounded_response(self):
        started, release = asyncio.Event(), asyncio.Event()

        async def reply(request):
            response = web.StreamResponse(headers={'Content-Type': 'application/json'})
            await response.prepare(request)
            await response.write(b'{')
            started.set()
            await release.wait()
            await response.write(b'"ok":true}')
            await response.write_eof()
            return response

        self.reply = reply
        task = asyncio.create_task(self.http.request('GET', '/oauth2/validate'))
        try:
            await asyncio.wait_for(started.wait(), 1)
            done, _ = await asyncio.wait({task}, timeout=0.05)
            self.assertNotIn(task, done, 'HTTP decoded an incomplete JSON chunk')
            release.set()
            self.assertEqual(await task, (200, {'ok': True}))
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)

    async def test_fixed_origin_redirect_and_response_guards(self):
        for origin in ('', 'https://127.0.0.1:1', 'http://localhost:1', 'http://127.0.0.1',
                       'http://user@127.0.0.1:1', 'http://127.0.0.1:1/path',
                       'http://127.0.0.1:1?query=1', 'http://127.0.0.1:1#fragment'):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                TwitchHTTP(self.client, mock_origin=origin)
        for method, path in (('GET', 'https://example.invalid/'), ('GET', '/oauth2/token'),
                             ('POST', '/oauth2/token?redirect=1'), ('GET', '//example.invalid')):
            with self.subTest(path=path), self.assertRaisesRegex(TwitchError, 'unapproved'):
                await self.http.request(method, path)
        self.assertEqual(self.requests, [])
        for response, expected in (
                (web.Response(status=302, headers={'Location': '/stolen'}), 'redirect refused'),
                (web.Response(body=b'not JSON SYNTHETIC-SECRET'), 'request failed'),
                (web.json_response(['SYNTHETIC-SECRET']), 'invalid Twitch response'),
                (web.Response(body=b' ' * 65537), 'oversized Twitch response')):
            async def reply(request):
                return response
            self.reply = reply
            with self.subTest(expected=expected), self.assertRaisesRegex(TwitchError, expected) as caught:
                await self.http.request('GET', '/oauth2/validate')
            self.assertNotIn('SYNTHETIC-SECRET', str(caught.exception))
        self.assertNotIn(('GET', '/stolen'), self.requests)

    async def test_concurrent_access_rotates_refresh_token_once_and_uses_new_token_next(self):
        refreshes = []
        validations = []

        async def reply(request):
            if request.path == '/oauth2/token':
                refreshes.append((await request.post())['refresh_token'])
                body = dict(success()[1], access_token=f'synthetic-access-{len(refreshes)}',
                            refresh_token=f'synthetic-refresh-{len(refreshes)}')
                return web.json_response(body)
            if request.path == '/oauth2/validate':
                validations.append(request.headers['Authorization'])
                return web.json_response(dict(client_id='synthetic-client', user_id='1',
                                               scopes=list(SCOPES), expires_in=14400))
            self.fail('unexpected rotation request')

        self.reply = reply
        self.session = UserSession(self.auth, Tokens(Secret('synthetic-access'),
                                                     Secret('synthetic-refresh'), 0), '1')
        tokens = await asyncio.gather(*(self.session.access_token() for _ in range(3)))
        self.assertEqual(refreshes, ['synthetic-refresh'])
        self.assertEqual([token.reveal() for token in tokens], ['synthetic-access-1'] * 3)
        self.assertEqual(validations, ['OAuth synthetic-access-1'])
        self.clock.now = 14400
        token = await self.session.access_token()
        self.assertEqual(refreshes, ['synthetic-refresh', 'synthetic-refresh-1'])
        self.assertEqual(token.reveal(), 'synthetic-access-2')
        self.assertEqual(validations, ['OAuth synthetic-access-1', 'OAuth synthetic-access-2'])

    async def test_device_flow_over_localhost_encodes_exact_scopes_and_poll_timing(self):
        polls, forms, prompts = [], [], []
        replies = iter([(400, {'message': 'authorization_pending'}),
                        (400, {'error': 'slow_down'}), success()])

        async def reply(request):
            self.assertEqual(request.method, 'POST')
            form = dict(await request.post())
            forms.append(form)
            if request.path == '/oauth2/device':
                return web.json_response(dict(device_code='synthetic-device', user_code='SYNTHETIC',
                    verification_uri='https://www.twitch.tv/activate?public=true&device-code=SYNTHETIC',
                    interval=3, expires_in=60))
            self.assertEqual(request.path, '/oauth2/token')
            polls.append(self.clock.now)
            status, body = next(replies)
            return web.json_response(body, status=status)

        self.reply = reply
        auth = DeviceAuth('synthetic-client', self.http, clock=lambda: self.clock.now, wait=self.clock.wait)
        tokens = await auth.login(prompts.append, asyncio.Event())
        self.assertEqual(polls, [3, 6, 14])
        self.assertEqual(forms[0], {'client_id': 'synthetic-client',
            'scopes': 'user:read:chat moderator:read:shield_mode channel:read:stream_key'})
        for form in forms[1:]:
            self.assertEqual(form, {'client_id': 'synthetic-client',
                'scopes': 'user:read:chat moderator:read:shield_mode channel:read:stream_key',
                'device_code': 'synthetic-device', 'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'})
        self.assertEqual(tokens.access.reveal(), 'synthetic-access')
        self.assertEqual(tokens.refresh.reveal(), 'synthetic-refresh')
        self.assertEqual(len(prompts), 1)
        self.assertEqual(prompts[0].code.reveal(), 'SYNTHETIC')
        for value in (tokens, tokens.access, tokens.refresh, prompts[0], prompts[0].uri, prompts[0].code):
            self.assertNotIn('synthetic-access', repr(value))
            self.assertNotIn('synthetic-refresh', str(value))
            self.assertNotIn('SYNTHETIC', repr(value))
            with self.assertRaises(TypeError):
                pickle.dumps(value)
            with self.assertRaises(TypeError):
                json.dumps(value)

    async def test_cancel_event_aborts_localhost_token_response(self):
        started, release, finished, cancel = (asyncio.Event() for _ in range(4))

        async def reply(request):
            if request.path == '/oauth2/device':
                return web.json_response(dict(device_code='synthetic-device', user_code='SYNTHETIC',
                    verification_uri='https://www.twitch.tv/activate', interval=3, expires_in=60))
            self.assertEqual(request.path, '/oauth2/token')
            started.set()
            try:
                await release.wait()
                return web.json_response(success()[1])
            finally:
                finished.set()

        self.reply = reply
        auth = DeviceAuth('synthetic-client', self.http, clock=lambda: self.clock.now, wait=self.clock.wait)
        task = asyncio.create_task(auth.login(lambda prompt: None, cancel))
        try:
            await asyncio.wait_for(started.wait(), 1)
            cancel.set()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, 1)
            self.assertEqual(self.requests, [('POST', '/oauth2/device'), ('POST', '/oauth2/token')])
        finally:
            release.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await asyncio.wait_for(finished.wait(), 1)

    async def test_validation_rejects_malformed_claims_before_releasing_a_key(self):
        valid = dict(client_id='synthetic-client', user_id='1', scopes=list(SCOPES), expires_in=14400)
        for changes in (dict(client_id='other-client'), dict(user_id=None), dict(scopes=None),
                        dict(scopes=[['SYNTHETIC-SECRET']]), dict(scopes={scope: True for scope in SCOPES}),
                        dict(scopes=list(SCOPES) + ['channel:manage:broadcast']), dict(expires_in=0)):
            async def reply(request):
                if request.path == '/oauth2/validate':
                    return web.json_response(dict(valid, **changes))
                return web.json_response({'data': [{'stream_key': 'SYNTHETIC-SECRET'}]})
            self.reply = reply
            session = UserSession(self.auth, Tokens(Secret('synthetic-access'), Secret('synthetic-refresh'), 14400), '1')
            with self.subTest(fields=list(changes)), self.assertRaisesRegex(TwitchError, 'validation failed'):
                await HelixKeyProvider(session, self.http).get_key()
        self.assertNotIn(('GET', '/helix/streams/key'), self.requests)

    async def test_validation_lifetime_limits_when_refresh_must_happen(self):
        async def reply(request):
            if request.path == '/oauth2/validate':
                return web.json_response(dict(client_id='synthetic-client', user_id='1',
                                               scopes=list(SCOPES), expires_in=120))
            self.assertEqual(request.path, '/oauth2/token')
            return web.json_response(dict(success()[1], access_token='synthetic-rotated'))
        self.reply = reply
        await self.session.access_token()
        self.clock.now = 61
        self.assertEqual((await self.session.access_token()).reveal(), 'synthetic-rotated')
        self.assertEqual(self.requests.count(('POST', '/oauth2/token')), 1)

    async def test_keyring_rejects_malformed_scopes_and_sanitizes_read_failures(self):
        backend = Mock()
        store = TokenStore(backend)
        for raw in (json.dumps(dict(access='synthetic-access', refresh='synthetic-refresh',
                                   scopes={scope: True for scope in SCOPES})),
                    'SYNTHETIC-SECRET', json.dumps([])):
            backend.get_password.return_value = raw
            with self.subTest(payload_type=raw[:1]), self.assertRaisesRegex(TwitchError, '^OS keyring read failed$'):
                store.load('synthetic-client', '1')
        backend.get_password.return_value = None
        self.assertIsNone(store.load('synthetic-client', '1'))
        backend.get_password.side_effect = RuntimeError('SYNTHETIC-SECRET')
        with self.assertRaisesRegex(TwitchError, '^OS keyring read failed$'):
            store.load('synthetic-client', '1')
        backend.set_password.assert_not_called()

    async def test_malformed_or_denied_key_response_never_returns_a_key(self):
        for status, body in ((403, {'message': 'SYNTHETIC-SECRET'}), (200, {}),
                             (200, {'data': None}), (200, {'data': []}), (200, {'data': [{}]}),
                             (200, {'data': [{'stream_key': 'synthetic-key'}, {'stream_key': 'other-key'}]})):
            async def reply(request):
                if request.path == '/oauth2/validate':
                    return web.json_response(dict(client_id='synthetic-client', user_id='1',
                                                   scopes=list(SCOPES), expires_in=14400))
                self.assertEqual(request.path, '/helix/streams/key')
                return web.json_response(body, status=status)
            self.reply = reply
            with self.subTest(status=status, fields=list(body)), self.assertRaises(TwitchError) as caught:
                await HelixKeyProvider(self.session, self.http).get_key()
            self.assertNotIn('SYNTHETIC-SECRET', str(caught.exception))

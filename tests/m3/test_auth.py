"""OAuth tests at the public client seam; all credentials are synthetic."""
import asyncio
import unittest

from shield.twitch.auth import DeviceAuth, TwitchError
from network import local_network


class Clock:
    def __init__(self):
        self.now = 0
        self.waits = []

    async def wait(self, seconds, cancel):
        self.waits.append(seconds)
        self.now += seconds
        if cancel.is_set():
            raise asyncio.CancelledError


class OAuthServer:
    def __init__(self, replies, expires=60):
        self.replies = iter(replies)
        self.polls = 0
        self.expires = expires

    async def request(self, method, path, **kwargs):
        if path == '/oauth2/device':
            return 200, dict(device_code='synthetic-device', user_code='SYNTHETIC',
                             verification_uri='https://www.twitch.tv/activate?device-code=SYNTHETIC',
                             interval=3, expires_in=self.expires)
        if path == '/oauth2/token':
            self.polls += 1
            return next(self.replies)
        raise AssertionError('unexpected request')


def success():
    return 200, dict(access_token='synthetic-access', refresh_token='synthetic-refresh',
                     scope=['user:read:chat', 'moderator:read:shield_mode', 'channel:read:stream_key'],
                     token_type='bearer', expires_in=14400)


class DeviceAuthorization(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        guard = local_network()
        guard.__enter__()
        self.addCleanup(guard.__exit__, None, None, None)

    async def test_server_interval_and_slow_down_apply_before_every_poll(self):
        clock = Clock()
        server = OAuthServer([(400, {'message': 'authorization_pending'}),
                              (400, {'error': 'slow_down'}), success()])
        prompts = []
        client = DeviceAuth('synthetic-client', server, clock=lambda: clock.now, wait=clock.wait)
        tokens = await client.login(prompts.append, asyncio.Event())
        self.assertEqual(clock.waits, [3, 3, 8])
        self.assertEqual(tokens.access.reveal(), 'synthetic-access')
        self.assertEqual(len(prompts), 1)
        self.assertNotIn('SYNTHETIC', repr(prompts))
        self.assertNotIn('synthetic-access', repr(tokens))

    async def test_expiry_denial_and_cancellation_never_continue_polling(self):
        for error, expected in [('access_denied', 'denied'), ('expired_token', 'expired'),
                                ('invalid device code', 'expired'), ('untrusted synthetic-access', 'failed')]:
            with self.subTest(error=error):
                server, clock = OAuthServer([(400, {'message': error})]), Clock()
                with self.assertRaisesRegex(TwitchError, expected):
                    await DeviceAuth('synthetic', server, clock=lambda: clock.now, wait=clock.wait).login(
                        lambda prompt: None, asyncio.Event())
                self.assertEqual(server.polls, 1)
        server, clock = OAuthServer([], expires=2), Clock()
        with self.assertRaisesRegex(TwitchError, 'expired'):
            await DeviceAuth('synthetic', server, clock=lambda: clock.now, wait=clock.wait).login(
                lambda prompt: None, asyncio.Event())
        self.assertEqual(server.polls, 0)
        cancel = asyncio.Event()
        with self.assertRaises(asyncio.CancelledError):
            await DeviceAuth('synthetic', server).login(lambda prompt: cancel.set(), cancel)
        self.assertEqual(server.polls, 0)


    async def test_cancellation_aborts_inflight_device_and_token_requests(self):
        for blocked_path in ('/oauth2/device', '/oauth2/token'):
            with self.subTest(path=blocked_path):
                entered, aborted, cancel = asyncio.Event(), asyncio.Event(), asyncio.Event()
                server, clock = OAuthServer([success()]), Clock()
                original_request = server.request

                async def request(method, path, **kwargs):
                    if path == blocked_path:
                        entered.set()
                        try:
                            await asyncio.Event().wait()
                        finally:
                            aborted.set()
                    return await original_request(method, path, **kwargs)

                server.request = request
                prompts = []
                task = asyncio.create_task(DeviceAuth('synthetic', server, clock=lambda: clock.now,
                                                       wait=clock.wait).login(prompts.append, cancel))
                try:
                    await asyncio.wait_for(entered.wait(), 1)
                    cancel.set()
                    done, _ = await asyncio.wait({task}, timeout=0.1)
                    self.assertIn(task, done, 'cancel event left HTTP request running')
                    with self.assertRaises(asyncio.CancelledError):
                        await task
                    self.assertTrue(aborted.is_set())
                    self.assertEqual(len(prompts), int(blocked_path == '/oauth2/token'))
                finally:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

    async def test_malformed_token_responses_fail_with_safe_local_errors(self):
        cases = [dict(scope=None), dict(scope=[['SYNTHETIC-SECRET']]),
                 dict(scope={scope: True for scope in ('user:read:chat', 'moderator:read:shield_mode',
                                                       'channel:read:stream_key')}),
                 dict(token_type=['SYNTHETIC-SECRET']), dict(expires_in=10 ** 400),
                 dict(access_token='SYNTHETIC-SECRET\r\nInjected: value')]
        for changes in cases:
            with self.subTest(fields=list(changes)):
                body = dict(success()[1], **changes)
                server, clock = OAuthServer([(200, body)]), Clock()
                with self.assertRaises(TwitchError) as caught:
                    await DeviceAuth('synthetic', server, clock=lambda: clock.now, wait=clock.wait).login(
                        lambda prompt: None, asyncio.Event())
                self.assertNotIn('SYNTHETIC-SECRET', str(caught.exception))

    async def test_malformed_device_responses_never_reach_presenter(self):
        for body in ([], None, {'device_code': 'synthetic-device', 'expires_in': True},
                     {'device_code': 'synthetic-device', 'expires_in': 60, 'interval': 3,
                      'user_code': 'SYNTHETIC', 'verification_uri': 'https://www.twitch.tv/activate#evil'}):
            with self.subTest(body_type=type(body).__name__):
                class Server:
                    async def request(self, method, path, **kwargs):
                        return 200, body
                prompts = []
                clock = Clock()
                with self.assertRaises(TwitchError):
                    await DeviceAuth('synthetic', Server(), clock=lambda: clock.now, wait=clock.wait).login(
                        prompts.append, asyncio.Event())
                self.assertEqual(prompts, [])

    async def test_omitted_interval_defaults_to_five_and_slow_down_accumulates(self):
        clock = Clock()
        server = OAuthServer([(400, {'error': 'slow_down'}),
                              (400, {'error': 'slow_down'}), success()])
        request = server.request

        async def without_interval(method, path, **kwargs):
            status, body = await request(method, path, **kwargs)
            if path == '/oauth2/device':
                body.pop('interval')
            return status, body

        server.request = without_interval
        tokens = await DeviceAuth('synthetic', server, clock=lambda: clock.now, wait=clock.wait).login(
            lambda prompt: None, asyncio.Event())
        self.assertEqual(clock.waits, [5, 10, 15])
        self.assertEqual(server.polls, 3)
        self.assertEqual(tokens.access.reveal(), 'synthetic-access')

    async def test_expiry_during_response_rejects_late_credentials(self):
        clock, server = Clock(), OAuthServer([success()], expires=4)
        request = server.request

        async def expires_during_poll(method, path, **kwargs):
            result = await request(method, path, **kwargs)
            if path == '/oauth2/token':
                clock.now = 4
            return result

        server.request = expires_during_poll
        with self.assertRaisesRegex(TwitchError, 'expired'):
            await DeviceAuth('synthetic', server, clock=lambda: clock.now, wait=clock.wait).login(
                lambda prompt: None, asyncio.Event())
        self.assertEqual(server.polls, 1)

"""Synthetic loopback OAuth/Helix/EventSub fixture, no external account records."""
import asyncio
from contextlib import suppress
from datetime import datetime, timezone

from aiohttp import web

from shield.twitch.auth import SCOPES


class MockTwitch:
    def __init__(self):
        self.sockets, self.subscriptions = [], {}
        self.calls = []
        self.counter = 0

    async def __aenter__(self):
        app = web.Application()
        app.router.add_route('*', '/{path:.*}', self.route)
        self.runner = web.AppRunner(app, access_log=None)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await site.start()
        self.origin = 'http://127.0.0.1:' + str(site._server.sockets[0].getsockname()[1])
        return self

    async def __aexit__(self, *error):
        for ws, _ in self.sockets:
            await ws.close()
        await self.runner.cleanup()

    async def route(self, request):
        self.calls.append((request.method, request.path))
        if request.path == '/oauth2/device':
            return web.json_response({'device_code': 'synthetic-device', 'user_code': 'synthetic-code',
                'verification_uri': 'https://www.twitch.tv/activate', 'expires_in': 600, 'interval': .001})
        if request.path == '/oauth2/token':
            return web.json_response({'access_token': 'synthetic-access', 'refresh_token': 'synthetic-refresh',
                'expires_in': 14400, 'token_type': 'bearer', 'scope': list(SCOPES)})
        if request.path == '/oauth2/validate':
            return web.json_response({'client_id': 'synthetic-client', 'user_id': '1',
                'scopes': list(SCOPES), 'expires_in': 14400})
        if request.path == '/helix/streams/key':
            return web.json_response({'data': [{'stream_key': 'SYNTHETIC-INTEGRATION-KEY'}]})
        if request.path == '/helix/moderation/shield_mode':
            return web.json_response({'data': [{'is_active': False}]})
        if request.path == '/eventsub/subscriptions' and request.method == 'POST':
            body = await request.json()
            identifier = 'synthetic-sub-' + str(len(self.subscriptions))
            self.subscriptions[(body['transport']['session_id'], body['type'])] = identifier
            return web.json_response({'data': [{**body, 'id': identifier, 'status': 'enabled'}]}, status=202)
        if request.path == '/ws':
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            sid = 'synthetic-session-' + str(len(self.sockets))
            self.sockets.append((ws, sid))
            await ws.send_json({'metadata': {'message_type': 'session_welcome',
                'message_timestamp': self.timestamp()}, 'payload': {'session': {'id': sid,
                'status': 'connected', 'keepalive_timeout_seconds': 10, 'reconnect_url': None}}})
            async def keepalive():
                while not ws.closed:
                    await asyncio.sleep(2)
                    await ws.send_json({'metadata': {'message_type': 'session_keepalive',
                        'message_timestamp': self.timestamp()}, 'payload': {}})
            task = asyncio.create_task(keepalive())
            try:
                async for _ in ws:
                    pass
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            return ws
        raise AssertionError('Unexpected mock operation: ' + request.path)

    @staticmethod
    def timestamp():
        return datetime.now(timezone.utc).isoformat()

    async def send(self, text='!shield hold', actor='2', topic='channel.chat.message', mid=None):
        ws, sid = self.sockets[-1]
        self.counter += 1
        envelope = {'metadata': {'message_id': mid or 'integration-' + str(self.counter),
            'message_type': 'notification', 'message_timestamp': self.timestamp(),
            'subscription_type': topic, 'subscription_version': '1'}, 'payload': {
            'subscription': {'id': self.subscriptions[(sid, topic)], 'type': topic, 'version': '1',
                'status': 'enabled', 'condition': {'broadcaster_user_id': '1'}},
            'event': {'broadcaster_user_id': '1', 'chatter_user_id': actor,
                'message': {'text': text}, 'badges': [{'set_id': 'moderator', 'id': '1', 'info': ''}]}}}
        await ws.send_json(envelope)
        return envelope


async def until(predicate, seconds=5):
    async with asyncio.timeout(seconds):
        while not predicate():
            await asyncio.sleep(.005)

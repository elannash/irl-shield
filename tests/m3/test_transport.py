"""Actual pyTwitchAPI sockets against synthetic loopback servers, no Twitch calls."""
import asyncio
import hashlib
import os
from pathlib import Path
import socket
import tempfile
import time
import unittest
from datetime import datetime, timezone

from aiohttp import ClientSession, web

from shield.twitch.auth import DeviceAuth, Tokens, Secret, UserSession, SCOPES
from shield.twitch.http import TwitchHTTP
from shield.twitch.transport import EventSubClient
from network import local_network
from test_events import adapter, notification, START


async def until(predicate):
    async with asyncio.timeout(5):
        while not predicate():
            await asyncio.sleep(.01)


class MockTransport(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        guard = local_network()
        guard.__enter__()
        self.addCleanup(guard.__exit__, None, None, None)
        self.sockets, self.subscriptions = [], []
        self.validations = 0
        self.valid = True
        self.now = 0
        self.shield_active = False
        self.status_failure = False
        self.status_entered = asyncio.Event()
        self.status_release = None
        self.status_requests = 0
        app = web.Application()
        async def ws(request):
            connection = web.WebSocketResponse()
            await connection.prepare(request)
            self.sockets.append(connection)
            sid = 'session-' + str(len(self.sockets))
            await connection.send_json({'metadata': {'message_type': 'session_welcome'}, 'payload': {
                'session': {'id': sid, 'status': 'connected', 'connected_at': '2026-10-29T00:00:00Z',
                            'keepalive_timeout_seconds': 10, 'reconnect_url': None}}})
            async for _ in connection:
                pass
            return connection
        async def subscribe(request):
            body = await request.json()
            self.subscriptions.append(body)
            return web.json_response({'data': [{**body, 'id': body['type'], 'status': 'enabled'}]}, status=202)
        async def validate(request):
            self.validations += 1
            return web.json_response({'client_id': 'synthetic', 'user_id': '1' if self.valid else '9',
                                      'scopes': list(SCOPES), 'expires_in': 14400})
        async def shield_status(request):
            self.assertEqual(dict(request.query), {'broadcaster_id': '1', 'moderator_id': '1'})
            self.status_requests += 1
            self.status_entered.set()
            if self.status_release is not None:
                await self.status_release.wait()
            if self.status_failure:
                return web.json_response({'message': 'synthetic-failure'}, status=503)
            return web.json_response({'data': [{'is_active': self.shield_active}]})
        app.router.add_get('/ws', ws)
        app.router.add_post('/eventsub/subscriptions', subscribe)
        app.router.add_get('/oauth2/validate', validate)
        app.router.add_get('/helix/moderation/shield_mode', shield_status)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await site.start()
        self.origin = 'http://127.0.0.1:' + str(site._server.sockets[0].getsockname()[1])
        self.http_session = ClientSession()
        auth = DeviceAuth('synthetic', TwitchHTTP(self.http_session, mock_origin=self.origin), clock=lambda: self.now)
        self.user = UserSession(auth, Tokens(Secret('synthetic-access'), Secret('synthetic-refresh'), 14400), '1')
        self.control, self.events = adapter(mock=True)
        self.client = EventSubClient(self.user, self.events, mock_origin=self.origin)
        self.addAsyncCleanup(self.runner.cleanup)
        self.addAsyncCleanup(self.http_session.close)
        self.addAsyncCleanup(self.client.stop)

    async def send(self, message):
        message['payload']['subscription']['id'] = message['metadata']['subscription_type']
        await self.sockets[-1].send_json(message)

    async def test_real_transport_commands_reconnect_dedup_and_revocation(self):
        await self.client.start()
        self.assertEqual(len(self.subscriptions), 3)
        self.assertEqual(self.status_requests, 1)
        self.assertEqual(self.events.phase, 'ready')
        await self.send(notification())
        await until(lambda: self.control.state == 'HOLD')
        await self.send(notification('resume-mod', '!shield resume'))
        await self.send(notification('resume-owner', '!shield resume', actor='1', at=START + 2))
        await until(lambda: self.control.state == 'LIVE')
        before_handover = self.control.transitions
        await self.sockets[-1].send_json({'metadata': {'message_type': 'session_reconnect'}, 'payload': {
            'session': {'id': 'session-1', 'status': 'reconnecting', 'keepalive_timeout_seconds': None,
                        'reconnect_url': self.origin.replace('http:', 'ws:') + '/ws',
                        'connected_at': '2026-10-29T00:00:00Z'}}})
        try:
            await until(lambda: self.events.session_id == 'session-2' and self.events.phase == 'ready')
        except TimeoutError:
            self.fail(f'reconnect incomplete: phase={self.events.phase}, sockets={len(self.sockets)}, reason={self.control.reason}')
        self.assertEqual(self.control.transitions, before_handover)
        await self.send(notification())
        await self.send(notification('sync', '!shield resume', actor='1', at=START + 3))
        await until(lambda: self.events.remembered == 4)
        self.assertEqual(self.control.state, 'LIVE')
        self.assertEqual(len(self.subscriptions), 3)
        await self.sockets[-1].send_json({'metadata': {'message_type': 'revocation'}, 'payload': {
            'subscription': {'id': 'channel.chat.message', 'type': 'channel.chat.message',
                             'status': 'authorization_revoked'}}})
        await until(lambda: self.events.phase == 'revoked')
        self.assertEqual(self.control.state, 'HOLD')
        await self.client.stop()
        self.assertTrue(all(ws.closed for ws in self.sockets))

    async def test_idle_session_validates_and_failed_validation_stops_transport(self):
        await self.client.start()
        # Patch the system clock wait, not UserSession or transport behavior.
        from unittest.mock import patch
        original_sleep = asyncio.sleep
        async def advance(seconds):
            if seconds >= 60:
                self.now = 3600
                self.valid = False
            await original_sleep(.001)
        with patch('shield.twitch.transport.asyncio.sleep', advance):
            await until(lambda: self.validations >= 2)
            await until(lambda: self.events.phase == 'revoked')
            await until(lambda: all(ws.closed for ws in self.sockets))
        self.assertEqual(self.control.state, 'HOLD')

    async def test_actual_hash_pinned_twitch_cli_shield_events_and_reconnect(self):
        binary = Path('.tmp/tools/twitch-cli_1.1.24_Linux_x86_64/twitch').resolve()
        self.assertEqual(hashlib.sha256(binary.read_bytes()).hexdigest(),
                         '40958ae7aed8a58f58bd9f32dec98cdd326741e5f9c1c6e6da9f7ae1df599240')
        # CLI RPC uses fixed 44747. Refuse to start if another session owns it.
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 44747))
        with socket.socket() as reserve:
            reserve.bind(('127.0.0.1', 0))
            port = reserve.getsockname()[1]
        with tempfile.TemporaryDirectory(prefix='m3-cli-', dir='/tmp/agents/irl-shield/m3-twitch') as tmp:
            config = str(Path(tmp) / 'absent-config')
            process = await asyncio.create_subprocess_exec(str(binary), '--config', config, 'event',
                'websocket', 'start-server', '--ip', '127.0.0.1', '--port', str(port),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, cwd=tmp)
            async def stop_process():
                if process.returncode is None:
                    process.terminate()
                await asyncio.wait_for(process.wait(), 5)
            self.addAsyncCleanup(stop_process)
            lines = []
            async with asyncio.timeout(5):
                while True:
                    line = await process.stdout.readline()
                    lines.append(line)
                    if not line:
                        self.fail('Twitch CLI server exited before ready')
                    if b'Connect to the WebSocket server at' in line:
                        break
            async def drain():
                async for line in process.stdout:
                    lines.append(line)
            drain_task = asyncio.create_task(drain())
            async def finish_log():
                await stop_process()
                await drain_task
                Path('/tmp/agents/irl-shield/m3-twitch/cli-server.log').write_bytes(b''.join(lines))
            self.addAsyncCleanup(finish_log)
            control, events = adapter(mock=True)
            events.clock = time.time
            events.started_at = time.time() - 1
            cli_origin = f'http://127.0.0.1:{port}'
            # v1.1.24 cannot create chat subscriptions. This local facade supplies
            # that one synthetic response and forwards Shield subscriptions and
            # every WebSocket byte to the actual CLI server.
            facade = web.Application()
            async def proxy_ws(request):
                downstream = web.WebSocketResponse()
                await downstream.prepare(request)
                async with self.http_session.ws_connect(cli_origin + '/ws') as upstream:
                    async def forward():
                        async for message in upstream:
                            if isinstance(message.data, str):
                                await downstream.send_str(message.data)
                        await downstream.close()
                    task = asyncio.create_task(forward())
                    try:
                        async for _ in downstream:
                            pass
                    finally:
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
                return downstream
            async def proxy_subscribe(request):
                body = await request.json()
                if body['type'] == 'channel.chat.message':
                    return web.json_response({'data': [{**body, 'id': 'synthetic-chat', 'status': 'enabled'}]}, status=202)
                async with self.http_session.post(cli_origin + '/eventsub/subscriptions',
                    headers={'Client-Id': 'synthetic'}, json=body) as response:
                    return web.json_response(await response.json(), status=response.status)
            facade.router.add_get('/ws', proxy_ws)
            facade.router.add_post('/eventsub/subscriptions', proxy_subscribe)
            facade_runner = web.AppRunner(facade)
            await facade_runner.setup()
            facade_site = web.TCPSite(facade_runner, '127.0.0.1', 0)
            await facade_site.start()
            self.addAsyncCleanup(facade_runner.cleanup)
            facade_port = facade_site._server.sockets[0].getsockname()[1]
            client = EventSubClient(self.user, events, mock_origin=f'http://127.0.0.1:{facade_port}')
            self.addAsyncCleanup(client.stop)
            await client.start()
            async with self.http_session.get(f'http://127.0.0.1:{port}/eventsub/subscriptions',
                                              headers={'Client-Id': 'synthetic'}) as response:
                subscriptions = {s['type']: s['id'] for s in (await response.json())['data']}
            async def cli(*args):
                command = await asyncio.create_subprocess_exec(str(binary), '--config', config, 'event', *args,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, cwd=tmp)
                try:
                    output, _ = await asyncio.wait_for(command.communicate(), 10)
                finally:
                    if command.returncode is None:
                        command.terminate()
                    await asyncio.wait_for(command.wait(), 5)
                self.assertEqual(command.returncode, 0, output.decode())
            await cli('trigger', 'channel.shield_mode.begin', '--no-config', '--transport', 'websocket',
                      '--to-user', '1', '--from-user', '2', '--subscription-id', subscriptions['channel.shield_mode.begin'],
                      '--timestamp', '2026-10-29T00:00:01Z')
            await until(lambda: control.state == 'HOLD')
            old_session = events.session_id
            await cli('websocket', 'reconnect')
            await until(lambda: events.session_id != old_session and events.phase == 'ready')
            self.assertEqual(control.state, 'HOLD')
            await cli('trigger', 'channel.shield_mode.end', '--no-config', '--transport', 'websocket',
                      '--to-user', '1', '--from-user', '2', '--subscription-id', subscriptions['channel.shield_mode.end'],
                      '--timestamp', '2026-10-29T00:00:02Z')
            await until(lambda: control.state == 'LIVE')
            await client.stop()
            await stop_process()
            self.assertIsNotNone(process.returncode)

    async def test_startup_existing_shield_and_failed_reconcile_remain_held(self):
        self.shield_active = True
        await self.client.start()
        self.assertEqual(self.control.state, 'HOLD')
        self.assertEqual(self.control.reason, 'twitch-shield-status')
        self.assertEqual(self.status_requests, 1)
        await self.send(notification('clear-shield', topic='channel.shield_mode.end', at=START + 2))
        await until(lambda: self.control.state == 'LIVE')
        self.shield_active = False
        self.status_failure = True
        await self.sockets[-1].close()
        await until(lambda: self.status_requests >= 2)
        self.assertEqual(self.control.state, 'HOLD')
        self.status_failure = False
        await until(lambda: self.events.phase == 'ready')
        self.assertEqual(self.control.state, 'LIVE')

    async def test_drop_holds_through_reconcile_and_release_preserves_chat_and_local(self):
        await self.client.start()
        self.assertEqual(self.control.state, 'LIVE')
        self.status_release = asyncio.Event()
        self.addCleanup(self.status_release.set)
        self.status_entered.clear()
        await self.sockets[-1].close()
        await asyncio.wait_for(self.status_entered.wait(), 5)
        self.assertEqual(self.control.state, 'HOLD')
        self.control.set_hold(True, source='local')
        # Commands can arrive once resubscribed even while the status call waits.
        await self.send(notification('hold-during-reconcile', at=START + 3))
        await until(lambda: self.events.remembered == 1)
        self.status_release.set()
        await until(lambda: self.events.phase == 'ready')
        self.control.set_hold(False, source='local')
        self.assertEqual(self.control.state, 'HOLD')
        await self.send(notification('owner-after-reconcile', '!shield resume', actor='1', at=START + 4))
        await until(lambda: self.control.state == 'LIVE')


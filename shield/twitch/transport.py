"""pyTwitchAPI owns WebSocket I/O; these pinned hooks enforce control policy.

Private hooks are necessary for raw envelope IDs, reconnect-host validation and
fail-closed lifecycle. Remove them when upstream offers equivalent public hooks.
"""
import asyncio
import logging
from functools import partial

import aiohttp

from twitchAPI.eventsub.websocket import EventSubWebsocket
from twitchAPI.twitch import Twitch
from twitchAPI.type import AuthScope
from twitchAPI.helper import done_task_callback

from .auth import SCOPES, TwitchError
from .events import TOPICS, websocket_url


class _PolicySocket(EventSubWebsocket):
    def __init__(self, twitch, session, events, owner_loop, reconcile, **kwargs):
        super().__init__(twitch, **kwargs)
        self.user_session, self.events, self.owner_loop = session, events, owner_loop
        self.reconcile = reconcile
        self._connecting = False
        # Upstream debug/error paths interpolate URLs and raw remote payloads.
        # Use an instance logger so other sessions' logging stays unchanged.
        self.logger = logging.Logger('irl-shield.twitch.private')
        self.logger.disabled = True
        self._task_callback = partial(done_task_callback, self.logger)

    async def _build_request_header(self):
        if asyncio.get_running_loop() is self.owner_loop:
            token = await self.user_session.access_token()
        else:
            token = await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(
                self.user_session.access_token(), self.owner_loop))
        return {'Client-ID': self.user_session.auth.client_id, 'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + token.reveal()}

    async def _api_post_request(self, session, url, data=None):
        # The base implementation follows redirects, which could disclose auth.
        return await session.post(url, headers=await self._build_request_header(), json=data,
                                  allow_redirects=False)

    async def _connect(self, is_startup=False):
        self.events.fault('connecting')
        if self._session is None:
            trace = aiohttp.TraceConfig()
            async def refuse_redirect(session, context, params):
                raise TwitchError('WebSocket redirect refused')
            trace.on_request_redirect.append(refuse_redirect)
            self._session = aiohttp.ClientSession(timeout=self._twitch.session_timeout, trace_configs=[trace])
        self._connecting = True
        try:
            await asyncio.wait_for(super()._connect(is_startup), 20)
        finally:
            self._connecting = False

    async def _keep_loop_alive(self):
        # Upstream can leave a closed connection waiting for its keepalive
        # timeout. Detect that condition immediately and reuse its connect path.
        while not self._closing:
            if (self._running and not self._connecting and self._connection is not None
                    and self._connection.closed and self.events.phase != 'handover'
                    and self._reconnect is None):
                try:
                    await self._connect(False)
                except Exception:
                    self.events.fault('connect-failed')
                    await asyncio.sleep(1)
            await asyncio.sleep(.01)

    async def _handle_welcome(self, data):
        try:
            await super()._handle_welcome(data)
            self.events.welcome(self.active_session.id)
            if {s['sub_type'] for s in self._active_subscriptions.values()} == set(TOPICS):
                await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(self.reconcile(), self.owner_loop))
        except Exception:
            self.events.fault('invalid-welcome')
            self._startup_complete = True

    async def _handle_reconnect(self, data):
        url = data.get('payload', {}).get('session', {}).get('reconnect_url')
        if not self.events.reconnect(url):
            return
        previous_id = self.events.session_id
        try:
            await asyncio.wait_for(super()._handle_reconnect(data), 30)
            # The receive task can consume _reconnect while close() yields.
            migrated = self._reconnect.session if self._reconnect else self.active_session
            if migrated is not None and migrated.id != previous_id:
                self.events.handed_over(migrated.id)
            else:
                self.events.fault('reconnect-failed')
                await self._connection.close()
        except Exception:
            self.events.fault('reconnect-failed')
            await self._connection.close()

    async def _handle_notification(self, data):
        self._reset_timeout()
        subscription = data.get('payload', {}).get('subscription', {})
        known = self._active_subscriptions.get(subscription.get('id'))
        if known is not None and known['sub_type'] == subscription.get('type'):
            self.events.accept(data)

    async def _handle_revocation(self, data):
        if data.get('payload', {}).get('subscription', {}).get('type') in TOPICS:
            self.events.fault('subscription-revoked', revoked=True)
        await super()._handle_revocation(data)

    async def _task_receive(self):
        try:
            await super()._task_receive()
        finally:
            self.events.fault('disconnected')

    def _run_socket(self):
        try:
            super()._run_socket()
        except Exception:
            self.events.fault('transport-failed')
        finally:
            self._startup_complete = True
            loop = self._socket_loop
            if loop is not None:
                async def cleanup():
                    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    if self._session is not None:
                        await self._session.close()
                loop.run_until_complete(cleanup())
                loop.close()


class EventSubClient:
    def __init__(self, session, events, *, mock_origin=None, allow_live=False):
        self.session, self.events = session, events
        self.mock_origin, self.allow_live = mock_origin, allow_live
        self._socket, self._twitch = None, None
        self._validation_task = None
        self._shutdown = None

    async def start(self):
        if self._socket is not None or self._shutdown is not None:
            raise TwitchError('EventSub already started')
        if self.session.broadcaster_id != self.events.broadcaster_id:
            raise TwitchError('EventSub broadcaster identity mismatch')
        if self.mock_origin is not None:
            from .http import TwitchHTTP
            TwitchHTTP(None, mock_origin=self.mock_origin)
            url = self.mock_origin.replace('http://', 'ws://', 1) + '/ws'
            if not self.events.mock:
                raise TwitchError('mock policy required')
        elif self.allow_live and not self.events.mock:
            url = 'wss://eventsub.wss.twitch.tv/ws'
        else:
            raise TwitchError('live EventSub requires explicit authorization')
        websocket_url(url, mock=self.events.mock)
        token = await self.session.access_token()
        twitch = self._twitch = await Twitch(self.session.auth.client_id, authenticate_app=False)
        twitch.auto_refresh_auth = False
        await twitch.set_user_authentication(token.reveal(), [AuthScope(s) for s in SCOPES], validate=False)
        socket = self._socket = _PolicySocket(twitch, self.session, self.events, asyncio.get_running_loop(),
            self._reconcile,
            connection_url=url, subscription_url=(self.mock_origin + '/') if self.mock_origin else None)
        try:
            await asyncio.wait_for(asyncio.to_thread(socket.start), 25)
            if self.events.phase != 'subscribing':
                raise TwitchError('EventSub startup failed')
            async def unused(event):
                pass  # The raw-envelope hook applies policy before object conversion.
            user = self.session.broadcaster_id
            await socket.listen_channel_chat_message(user, user, unused)
            await socket.listen_channel_shield_mode_begin(user, user, unused)
            await socket.listen_channel_shield_mode_end(user, user, unused)
            await self._reconcile()
            self._validation_task = asyncio.create_task(self._validate_idle())
        except asyncio.CancelledError:
            await self.stop()
            raise
        except Exception:
            await self.stop()
            raise TwitchError('EventSub startup failed') from None

    async def _reconcile(self):
        snapshot = self.events.begin_reconcile()
        if snapshot is None:
            return
        delay = 1
        while self.events.reconciliation_current(snapshot):
            try:
                token = await self.session.access_token()
                status, body = await self.session.auth.http.request('GET', '/helix/moderation/shield_mode',
                    params={'broadcaster_id': self.session.broadcaster_id, 'moderator_id': self.session.broadcaster_id},
                    headers={'Client-Id': self.session.auth.client_id, 'Authorization': 'Bearer ' + token.reveal()})
                data = body.get('data') if isinstance(body, dict) else None
                if (status != 200 or not isinstance(data, list) or len(data) != 1
                        or not isinstance(data[0], dict) or type(data[0].get('is_active')) is not bool):
                    raise TwitchError('Shield Mode reconciliation failed')
                self.events.reconciled(data[0]['is_active'], snapshot)
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(delay)
                delay = min(30, delay * 2)

    async def _validate_idle(self):
        try:
            while True:
                await asyncio.sleep(60)
                await self.session.access_token()
        except asyncio.CancelledError:
            raise
        except Exception:
            self.events.fault('authorization-invalid', revoked=True)
            await self.stop()

    async def stop(self):
        validation, self._validation_task = self._validation_task, None
        if validation is not None and validation is not asyncio.current_task():
            validation.cancel()
            await asyncio.gather(validation, return_exceptions=True)
        if self._shutdown is None:
            self._shutdown = asyncio.create_task(self._stop_socket())
        await asyncio.shield(self._shutdown)

    async def _stop_socket(self):
        socket = self._socket
        if socket is not None:
            socket._startup_complete = True
            if socket._socket_thread and socket._socket_thread.is_alive():
                await asyncio.to_thread(lambda: asyncio.run(socket.stop()))
                await asyncio.to_thread(socket._socket_thread.join, 5)
                if socket._socket_thread.is_alive():
                    raise TwitchError('EventSub worker did not stop')
            self._socket = None
        if self._twitch is not None:
            await self._twitch.close()
            self._twitch = None
        self.events.fault('stopped')

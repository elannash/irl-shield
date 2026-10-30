"""Pinned pyTwitchAPI I/O with owner-loop policy and verified subscriptions.

Private hooks retain connection provenance and validate subscription responses.
Remove them when upstream exposes equivalent lifecycle and readiness hooks.
"""
import asyncio
import json
import logging
from functools import partial

import aiohttp
from twitchAPI.eventsub.websocket import EventSubWebsocket
from twitchAPI.helper import done_task_callback
from twitchAPI.twitch import Twitch
from twitchAPI.type import AuthScope

from .auth import SCOPES, TwitchError, InvalidToken
from .events import TOPICS, websocket_url


class _PolicySocket(EventSubWebsocket):
    def __init__(self, twitch, session, events, owner_loop, reconcile, **kwargs):
        super().__init__(twitch, **kwargs)
        self.user_session, self.events, self.owner_loop = session, events, owner_loop
        self.reconcile = reconcile
        self._connect_lock = asyncio.Lock()
        self._connection_generation = None
        self._planned_generation = None
        self._confirmed = {}
        self._connection_provenance = {}
        self._dial_task = None
        self._handlers = set()
        self.logger = logging.Logger('irl-shield.twitch.private')
        self.logger.disabled = True
        self._task_callback = partial(done_task_callback, self.logger)

    async def owner(self, call, *args, **kwargs):
        async def invoke():
            return call(*args, **kwargs)
        if asyncio.get_running_loop() is self.owner_loop:
            return await invoke()
        return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(invoke(), self.owner_loop))

    async def _build_request_header(self):
        if asyncio.get_running_loop() is self.owner_loop:
            token = await self.user_session.access_token()
        else:
            token = await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(
                self.user_session.access_token(), self.owner_loop))
        return {'Client-ID': self.user_session.auth.client_id, 'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + token.reveal()}

    async def _api_post_request(self, session, url, data=None):
        generation = self._connection_generation
        response = await session.post(url, headers=await self._build_request_header(), json=data,
                                      allow_redirects=False)
        try:
            body = await response.json()
            records = body.get('data') if isinstance(body, dict) else None
            record = records[0] if isinstance(records, list) and len(records) == 1 else None
            if (response.status != 202 or not isinstance(record, dict)
                    or not isinstance(record.get('id'), str) or not record['id']
                    or record.get('status') != 'enabled' or record.get('type') != data['type']
                    or record.get('version') != '1' or record.get('condition') != data['condition']
                    or record.get('transport', {}).get('method') != 'websocket'
                    or record.get('transport', {}).get('session_id') != data['transport']['session_id']):
                raise TwitchError('EventSub subscription not enabled for this session')
            if (generation != self._connection_generation or self.active_session is None
                    or self.active_session.id != data['transport']['session_id']):
                raise TwitchError('stale EventSub subscription response')
            self._confirmed[data['type']] = dict(record)
            return response
        except BaseException:
            response.release()
            raise

    async def _connect(self, is_startup=False):
        observed = self._connection
        async with self._connect_lock:
            if self._connection is not observed and self._connection is not None and not self._connection.closed:
                return
            if self._session is None:
                trace = aiohttp.TraceConfig()
                async def refuse_redirect(session, context, params):
                    raise TwitchError('WebSocket redirect refused')
                trace.on_request_redirect.append(refuse_redirect)
                self._session = aiohttp.ClientSession(timeout=self._twitch.session_timeout, trace_configs=[trace])
            delay = 1
            while self._running and not self._closing:
                generation = await self.owner(self.events.connection_started)
                self._confirmed = {}
                self._active_subscriptions.clear()
                self._callbacks.clear()
                try:
                    self._dial_task = asyncio.create_task(super()._connect(is_startup))
                    await asyncio.wait_for(self._dial_task, 20)
                    self._connection_generation = generation
                    self._remember_connection(self._connection, generation, self._confirmed)
                    return
                except asyncio.CancelledError:
                    if self._closing or not self._running:
                        return
                    raise
                except Exception:
                    # Upstream watchdog and reader callers cannot catch TimeoutError.
                    # Recovery stays inside this boundary; those tasks remain alive.
                    await self.owner(self.events.fault, 'connect-failed')
                    await asyncio.sleep(delay)
                    delay = min(30, delay * 2)
                finally:
                    self._dial_task = None

    async def _resubscribe(self):
        # Upstream restores stale entries after failed POSTs. Readiness and retry
        # instead use only enabled responses verified against this welcome.
        return

    def _remember_connection(self, connection, generation, subscriptions):
        self._connection_provenance[connection] = generation, subscriptions
        while len(self._connection_provenance) > 2:
            self._connection_provenance.pop(next(iter(self._connection_provenance)))

    def _current(self, generation, session_id):
        return (self.events.generation == generation and self.events.session_id == session_id
                and self.events.phase not in ('disconnected', 'connecting', 'revoked'))

    def _subscriptions_enabled(self, session_id):
        return len({record['id'] for record in self._confirmed.values()}) == len(TOPICS) and all(topic in self._confirmed
                   and self._confirmed[topic]['status'] == 'enabled'
                   and self._confirmed[topic]['transport']['session_id'] == session_id for topic in TOPICS)

    async def _handle_welcome(self, data):
        generation = data['_irl_generation']
        session_id = data.get('payload', {}).get('session', {}).get('id')
        if not await self.owner(self.events.welcome, session_id, generation=generation):
            return
        try:
            await super()._handle_welcome(data)
            user = self.user_session.broadcaster_id
            async def unused(event):
                pass
            listeners = {
                TOPICS[0]: self.listen_channel_chat_message,
                TOPICS[1]: self.listen_channel_shield_mode_begin,
                TOPICS[2]: self.listen_channel_shield_mode_end,
            }
            delay = 1
            while await self.owner(self._current, generation, session_id):
                try:
                    for topic in TOPICS:
                        if (topic not in self._confirmed
                                or self._confirmed[topic]['transport']['session_id'] != session_id):
                            await listeners[topic](user, user, unused)
                        if not await self.owner(self._current, generation, session_id):
                            return
                    if not self._subscriptions_enabled(session_id):
                        raise TwitchError('EventSub subscriptions incomplete')
                    await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(
                        self.reconcile(generation, session_id), self.owner_loop))
                    return
                except InvalidToken:
                    await self.owner(self.events.fault, 'authorization-invalid', revoked=True)
                    return
                except asyncio.CancelledError:
                    raise
                except Exception:
                    await asyncio.sleep(delay)
                    delay = min(30, delay * 2)
        except asyncio.CancelledError:
            raise
        except Exception:
            await self.owner(self.events.fault, 'invalid-welcome')
            self._startup_complete = True

    async def _handle_reconnect(self, data):
        generation = data['_irl_generation']
        url = data.get('payload', {}).get('session', {}).get('reconnect_url')
        if not await self.owner(self.events.reconnect, url, generation=generation):
            return
        self._planned_generation = generation
        previous_id = self.events.session_id
        try:
            await asyncio.wait_for(super()._handle_reconnect(data), 30)
            migrated = self._reconnect.session if self._reconnect else self.active_session
            if migrated is None or migrated.id == previous_id:
                raise TwitchError('EventSub handover incomplete')
            if not await self.owner(self.events.handed_over, migrated.id, generation=generation):
                if self._reconnect:
                    await self._reconnect.connection.close()
                    self._reconnect = None
                return
            # Twitch's reconnect welcome carries the old subscriptions to this
            # session; unlike unplanned connects, it requires no new POSTs.
            for record in self._confirmed.values():
                record['transport'] = {**record['transport'], 'session_id': migrated.id}
        except asyncio.CancelledError:
            raise
        except Exception:
            await self.owner(self.events.fault, 'reconnect-failed')
            if self._connection is not None:
                await self._connection.close()

    async def _handle_notification(self, data):
        if data['_irl_generation'] == self.events.generation and self.active_session is not None:
            self._reset_timeout()
        known = data.get('_irl_subscription')
        subscription = data.get('payload', {}).get('subscription', {})
        if known is not None and known['id'] == subscription.get('id') and known['type'] == subscription.get('type'):
            await self.owner(self.events.accept, data, generation=data['_irl_generation'])

    async def _handle_keepalive(self, data):
        if data['_irl_generation'] == self.events.generation and self.active_session is not None:
            await super()._handle_keepalive(data)

    async def _handle_revocation(self, data):
        subscription = data.get('payload', {}).get('subscription', {})
        known = data.get('_irl_subscription')
        if known is not None and subscription.get('type') in TOPICS:
            await self.owner(self.events.fault, 'subscription-revoked', revoked=True)

    async def _dispatch(self, handler, data):
        try:
            await handler(data)
        except asyncio.CancelledError:
            raise
        except Exception:
            await self.owner(self.events.fault, 'invalid-message')

    async def _task_receive(self):
        handlers = {'session_welcome': self._handle_welcome, 'session_keepalive': self._handle_keepalive,
                    'notification': self._handle_notification, 'session_reconnect': self._handle_reconnect,
                    'revocation': self._handle_revocation}
        while not self._closing:
            try:
                if not self._running:
                    return
                connection = self._connection
                if connection is None:
                    await asyncio.sleep(.01)
                    continue
                if self._reconnect and self.events.generation == self._planned_generation:
                    self._connection = self._reconnect.connection
                    self.active_session = self._reconnect.session
                    self._remember_connection(self._connection, self._planned_generation, self._confirmed)
                    self._reconnect = None
                    continue
                if connection.closed:
                    await self._connect(False)
                    continue
                provenance = self._connection_provenance.get(connection)
                if provenance is None:
                    await asyncio.sleep(.01)
                    continue
                generation, subscriptions = provenance
                message = await connection.receive()
                if message.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(message.data)
                    data['_irl_generation'] = generation
                    subscription_id = data.get('payload', {}).get('subscription', {}).get('id')
                    data['_irl_subscription'] = next((dict(record) for record in subscriptions.values()
                                                      if record['id'] == subscription_id), None)
                    handler = handlers.get(data.get('metadata', {}).get('message_type'))
                    if handler is not None:
                        task = asyncio.create_task(self._dispatch(handler, data))
                        self._handlers.add(task)
                        task.add_done_callback(self._handlers.discard)
                elif message.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING,
                                       aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    if self._closing or not self._running:
                        return
                    if self._reconnect and self.events.generation == self._planned_generation:
                        continue
                    # A watchdog-initiated connect already invalidated this
                    # reader's generation before closing the old socket.
                    if generation == self.events.generation:
                        await self.owner(self.events.fault, 'disconnected')
                    await self._connect(False)
            except asyncio.CancelledError:
                return
            except Exception:
                await self.owner(self.events.fault, 'receive-failed')
                await asyncio.sleep(1)
                await self._connect(False)

    async def _keep_loop_alive(self):
        while not self._closing:
            await asyncio.sleep(.01)

    async def _stop(self):
        if self._dial_task is not None:
            self._dial_task.cancel()
        if self._connection is not None:
            await self._connection.close()
        if self._reconnect is not None:
            await self._reconnect.connection.close()
        if self._session is not None:
            await self._session.close()
        self._closing = True

    def _run_socket(self):
        try:
            super()._run_socket()
        except asyncio.CancelledError:
            pass
        except Exception:
            asyncio.run_coroutine_threadsafe(self.owner(self.events.fault, 'transport-failed'), self.owner_loop)
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
        self._ready = asyncio.Event()

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
        socket = self._socket = _PolicySocket(twitch, self.session, self.events, asyncio.get_running_loop(), self._reconcile,
            connection_url=url, subscription_url=(self.mock_origin + '/') if self.mock_origin else None)
        try:
            await asyncio.to_thread(socket.start)
            await self._ready.wait()
            self._validation_task = asyncio.create_task(self._validate_idle())
        except asyncio.CancelledError:
            await self.stop()
            raise
        except Exception:
            await self.stop()
            raise TwitchError('EventSub startup failed') from None

    async def _reconcile(self, generation, session_id):
        snapshot = self.events.begin_reconcile(generation=generation, session_id=session_id)
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
                if self.events.reconciled(data[0]['is_active'], snapshot):
                    self._ready.set()
                return
            except InvalidToken:
                self.events.fault('authorization-invalid', revoked=True)
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(delay)
                delay = min(30, delay * 2)

    async def _validate_idle(self):
        delay = 1
        while True:
            try:
                await asyncio.sleep(60)
                await self.session.access_token()
                delay = 1
            except InvalidToken:
                self.events.fault('authorization-invalid', revoked=True)
                await self.stop()
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                self.events.fault('authorization-unavailable')
                await asyncio.sleep(delay)
                delay = min(30, delay * 2)
                socket = self._socket
                if socket is not None:
                    asyncio.run_coroutine_threadsafe(socket._connect(False), socket._socket_loop)

    async def stop(self):
        self.events.fault('stopping')
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

"""Memory-only authentication and EventSub lifecycle for one relay lifetime."""
import asyncio

from shield.twitch.auth import DeviceAuth, UserSession, TwitchError
from shield.twitch.events import ShieldEvents
from shield.twitch.keys import HelixKeyProvider
from shield.twitch.storage import TokenStore, owner_terminal_prompt
from shield.twitch.transport import EventSubClient


async def login(http, client_id, broadcaster_id, cancel, *, remember=False,
                present=owner_terminal_prompt):
    if not client_id or not broadcaster_id or not broadcaster_id.isdecimal():
        raise TwitchError('Twitch client and numeric broadcaster IDs required')
    auth = DeviceAuth(client_id, http)
    store = TokenStore() if remember else None
    tokens = store.load(client_id, broadcaster_id) if store else None
    if tokens is None:
        tokens = await auth.login(present, cancel)
    session = UserSession(auth, tokens, broadcaster_id)
    await session.access_token()
    if store:
        store.save(client_id, broadcaster_id, session.tokens, remember=True)
    return session


class TwitchControls:
    """Register once through runtime.control_ready; retain policy across reconnects."""
    def __init__(self, session, http, stopped, *, mock_origin=None, skin_chat=None):
        self.session, self.http, self.stopped = session, http, stopped
        self.mock_origin = mock_origin
        self.skin_chat = skin_chat
        self.loop = asyncio.get_running_loop()
        self.client = self.events = self.task = self.key = None
        self.failure = False

    async def prepare(self):
        self.key = await HelixKeyProvider(self.session, self.http).get_key()

    def register(self, control):
        # The synchronous constructor asserts connection HOLD before any poll.
        self.events = ShieldEvents(self.session.broadcaster_id, control.hold,
                                   mock=self.mock_origin is not None, on_chat=self.skin_chat)
        control.set_stream_key(self.key.reveal())
        self.key = None
        self.loop.call_soon_threadsafe(self._start)

    def _start(self):
        self.task = asyncio.create_task(self._serve())

    async def _serve(self):
        try:
            self.client = EventSubClient(self.session, self.events, mock_origin=self.mock_origin,
                                        allow_live=self.mock_origin is None)
            await self.client.start()
        except asyncio.CancelledError:
            raise
        except Exception:
            self.failure = True
            self.events.fault('integration-start-failed')
            self.stopped.set()

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        if self.client:
            await self.client.stop()
        self.key = None

"""Owned device-code polling. Only an owner-facing presenter may reveal codes."""
import asyncio
import math
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

SCOPES = ('user:read:chat', 'moderator:read:shield_mode', 'channel:read:stream_key')


class TwitchError(Exception):
    """Errors contain fixed local reasons, never remote response bodies."""


class InvalidToken(TwitchError):
    """The token validation endpoint definitively rejected the access token."""


class Secret:
    __slots__ = ('_value',)

    def __init__(self, value):
        if (not isinstance(value, str) or not value
                or any(ord(char) <= 32 or ord(char) == 127 for char in value)):
            raise TwitchError('missing credential')
        self._value = value

    def reveal(self):
        return self._value

    def __repr__(self):
        return '<redacted>'

    __str__ = __repr__

    def __reduce__(self):
        raise TypeError('credentials cannot be serialized')


@dataclass(frozen=True)
class DevicePrompt:
    uri: Secret
    code: Secret


@dataclass(frozen=True)
class Tokens:
    access: Secret
    refresh: Secret
    expires_at: float


def positive(value):
    try:
        valid = (not isinstance(value, bool) and isinstance(value, (int, float))
                 and math.isfinite(value) and value > 0)
    except OverflowError:
        valid = False
    if not valid:
        raise TwitchError('invalid authorization lifetime')
    return value


def approved_scopes(value):
    return (isinstance(value, list) and len(value) == len(SCOPES)
            and all(isinstance(scope, str) for scope in value) and set(value) == set(SCOPES))


async def cancellable_wait(seconds, cancel):
    try:
        await asyncio.wait_for(cancel.wait(), seconds)
    except TimeoutError:
        return
    raise asyncio.CancelledError


class DeviceAuth:
    def __init__(self, client_id, http, *, clock=time.monotonic, wait=cancellable_wait):
        self.client_id, self.http = client_id, http
        self.clock, self.wait = clock, wait

    def _tokens(self, body):
        if not isinstance(body, dict):
            raise TwitchError('invalid token response')
        token_type = body.get('token_type')
        if (not approved_scopes(body.get('scope')) or not isinstance(token_type, str)
                or token_type.lower() != 'bearer'):
            raise TwitchError('authorization scopes do not match approved scopes')
        return Tokens(Secret(body.get('access_token')), Secret(body.get('refresh_token')),
                      self.clock() + positive(body.get('expires_in')))

    async def _request(self, cancel, method, path, *, deadline=None, **kwargs):
        if cancel.is_set():
            raise asyncio.CancelledError
        if deadline is not None and self.clock() >= deadline:
            raise TwitchError('device authorization expired')
        request = asyncio.create_task(self.http.request(method, path, **kwargs))
        cancelled = asyncio.create_task(cancel.wait())
        try:
            timeout = None if deadline is None else max(0, deadline - self.clock())
            done, _ = await asyncio.wait({request, cancelled}, timeout=timeout,
                                         return_when=asyncio.FIRST_COMPLETED)
            if cancel.is_set():
                raise asyncio.CancelledError
            if request not in done or (deadline is not None and self.clock() >= deadline):
                raise TwitchError('device authorization expired')
            return request.result()
        finally:
            # Both event cancellation and caller-task cancellation own the HTTP task.
            request.cancel()
            cancelled.cancel()
            await asyncio.gather(request, cancelled, return_exceptions=True)

    async def login(self, present, cancel):
        if cancel.is_set():
            raise asyncio.CancelledError
        began = self.clock()
        status, body = await self._request(cancel, 'POST', '/oauth2/device', data={
            'client_id': self.client_id, 'scopes': ' '.join(SCOPES)})
        if status != 200 or not isinstance(body, dict):
            raise TwitchError('device authorization unavailable')
        device = Secret(body.get('device_code'))
        deadline = began + positive(body.get('expires_in'))
        interval = positive(body.get('interval', 5))
        prompt = DevicePrompt(Secret(body.get('verification_uri')), Secret(body.get('user_code')))
        # Validate before handing a secret-bearing URI to the owner presenter.
        try:
            uri = urlsplit(prompt.uri.reveal())
        except ValueError:
            raise TwitchError('invalid activation endpoint') from None
        if (uri.scheme != 'https' or uri.netloc != 'www.twitch.tv'
                or uri.path != '/activate' or uri.fragment):
            raise TwitchError('invalid activation endpoint')
        present(prompt)
        while True:
            if cancel.is_set():
                raise asyncio.CancelledError
            remaining = deadline - self.clock()
            if remaining <= 0:
                raise TwitchError('device authorization expired')
            await self.wait(min(interval, remaining), cancel)
            if cancel.is_set():
                raise asyncio.CancelledError
            if self.clock() >= deadline:
                raise TwitchError('device authorization expired')
            status, body = await self._request(cancel, 'POST', '/oauth2/token', deadline=deadline, data={
                'client_id': self.client_id, 'scopes': ' '.join(SCOPES),
                'device_code': device.reveal(), 'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'})
            if self.clock() >= deadline:
                raise TwitchError('device authorization expired')
            if status == 200:
                return self._tokens(body)
            if not isinstance(body, dict):
                raise TwitchError('device authorization failed')
            # Twitch uses message; RFC8628 uses error. Never propagate other text.
            error = body.get('error', body.get('message'))
            if error == 'authorization_pending':
                continue
            if error == 'slow_down':
                interval += 5
                continue
            if error in ('expired_token', 'invalid device code'):
                raise TwitchError('device authorization expired')
            if error == 'access_denied':
                raise TwitchError('device authorization denied')
            raise TwitchError('device authorization failed')

    async def refresh(self, tokens):
        status, body = await self.http.request('POST', '/oauth2/token', data={
            'client_id': self.client_id, 'grant_type': 'refresh_token',
            'refresh_token': tokens.refresh.reveal()})
        if status != 200:
            raise TwitchError('authorization refresh failed')
        return self._tokens(body)


class UserSession:
    """Validate at startup and hourly; rotate public-client refresh tokens in RAM."""
    def __init__(self, auth, tokens, broadcaster_id):
        self.auth, self.tokens, self.broadcaster_id = auth, tokens, broadcaster_id
        self._validated_at = None
        self._lock = asyncio.Lock()

    async def access_token(self):
        # Public-client refresh tokens are single-use; callers share one rotation.
        async with self._lock:
            return await self._access_token()

    async def _access_token(self):
        if self.auth.clock() >= self.tokens.expires_at - 60:
            self.tokens = await self.auth.refresh(self.tokens)
            self._validated_at = None
        now = self.auth.clock()
        if self._validated_at is None or now - self._validated_at >= 3600:
            status, body = await self.auth.http.request('GET', '/oauth2/validate', headers={
                'Authorization': 'OAuth ' + self.tokens.access.reveal()})
            if status == 401:
                raise InvalidToken('authorization validation failed')
            if (status != 200 or not isinstance(body, dict)
                    or body.get('client_id') != self.auth.client_id
                    or not isinstance(self.broadcaster_id, str) or not self.broadcaster_id
                    or body.get('user_id') != self.broadcaster_id
                    or not approved_scopes(body.get('scopes'))):
                raise TwitchError('authorization validation failed')
            try:
                expires_at = now + positive(body.get('expires_in'))
            except TwitchError:
                raise TwitchError('authorization validation failed') from None
            self.tokens = Tokens(self.tokens.access, self.tokens.refresh,
                                 min(self.tokens.expires_at, expires_at))
            self._validated_at = now
        return self.tokens.access

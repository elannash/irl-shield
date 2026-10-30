"""M2 seam: await provider.get_key() -> Secret. No stream destination is built here."""
from typing import Protocol

from .auth import Secret, TwitchError


class KeyProvider(Protocol):
    async def get_key(self) -> Secret: ...


class HelixKeyProvider:
    def __init__(self, session, http):
        self.session, self.http = session, http

    async def get_key(self):
        token = await self.session.access_token()
        status, body = await self.http.request('GET', '/helix/streams/key',
            params={'broadcaster_id': self.session.broadcaster_id},
            headers={'Client-Id': self.session.auth.client_id, 'Authorization': 'Bearer ' + token.reveal()})
        if status != 200:
            raise TwitchError('stream key unavailable')
        try:
            data = body['data']
            if len(data) != 1:
                raise TwitchError('invalid stream key response')
            return Secret(data[0]['stream_key'])
        except (KeyError, TypeError):
            raise TwitchError('invalid stream key response') from None

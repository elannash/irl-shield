"""Fixed-origin HTTP with no redirects, response logging or URL-bearing errors."""
import asyncio
import json
from urllib.parse import urlsplit

import aiohttp

from .auth import TwitchError


class TwitchHTTP:
    def __init__(self, session, *, mock_origin=None):
        self.session, self.mock_origin = session, mock_origin
        if mock_origin is not None:
            try:
                parsed = urlsplit(mock_origin)
                valid = (parsed.scheme == 'http' and parsed.hostname == '127.0.0.1'
                         and parsed.port is not None and 0 < parsed.port <= 65535
                         and not (parsed.username or parsed.password or parsed.path
                                  or parsed.query or parsed.fragment)
                         and not any(ord(char) <= 32 for char in mock_origin))
            except (ValueError, TypeError, AttributeError):
                valid = False
            if not valid:
                raise ValueError('mock HTTP must use a loopback origin') from None

    async def request(self, method, path, **kwargs):
        allowed = {('POST', '/oauth2/device'), ('POST', '/oauth2/token'),
                   ('GET', '/oauth2/validate'), ('GET', '/helix/streams/key'),
                   ('GET', '/helix/moderation/shield_mode')}
        if (method, path) not in allowed:
            raise TwitchError('unapproved HTTP operation')
        origin = self.mock_origin or ('https://api.twitch.tv' if path.startswith('/helix/') else 'https://id.twitch.tv')
        try:
            async with self.session.request(method, origin + path, allow_redirects=False,
                                            timeout=aiohttp.ClientTimeout(total=20), **kwargs) as response:
                if response.status // 100 == 3:
                    raise TwitchError('HTTP redirect refused')
                if response.content_length and response.content_length > 65536:
                    raise TwitchError('oversized Twitch response')
                try:
                    raw = await response.content.readexactly(65537)
                except asyncio.IncompleteReadError as error:
                    raw = error.partial
                if len(raw) > 65536:
                    raise TwitchError('oversized Twitch response')
                body = json.loads(raw)
                if not isinstance(body, dict):
                    raise TwitchError('invalid Twitch response')
                return response.status, body
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, RecursionError):
            raise TwitchError('Twitch HTTP request failed') from None

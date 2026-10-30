"""Session-local approval for the owner's attended naie live sessions."""
import threading

from shield.twitch.auth import approved_scopes, positive


class LiveModeError(Exception):
    """Fixed local failure text; never includes upstream responses or credentials."""

    def __init__(self):
        super().__init__('Live mode requires fresh naie authorization and an attended '
                         'terminal confirmation for this session.')


class LiveApproval:
    """Issued only by authorize_live; consumed once by runtime at startup."""

    __slots__ = ('_consumed', '_lock')

    def __init__(self):
        raise LiveModeError()

    def consume(self):
        with self._lock:
            if self._consumed:
                raise LiveModeError()
            self._consumed = True

    def __reduce__(self):
        raise TypeError('Live approval cannot be copied or serialized')


async def authorize_live(session, http):
    """Bypass cached validation, then ask on /dev/tty for this session only."""
    try:
        token = await session.access_token()
        began = session.auth.clock()
        status, body = await http.request('GET', '/oauth2/validate', headers={
            'Authorization': 'OAuth ' + token.reveal()})
        if (status != 200 or not isinstance(body, dict)
                or not isinstance(session.auth.client_id, str) or not session.auth.client_id
                or body.get('client_id') != session.auth.client_id
                or not isinstance(session.broadcaster_id, str) or not session.broadcaster_id.isdecimal()
                or body.get('user_id') != session.broadcaster_id
                or body.get('login') != 'naie'
                or not approved_scopes(body.get('scopes'))):
            raise LiveModeError()
        expires_at = min(session.tokens.expires_at, began + positive(body.get('expires_in')))
        # Buffered update mode requires seeking; terminals need separate handles.
        with open('/dev/tty', 'r') as response, open('/dev/tty', 'w') as terminal:
            if not response.isatty() or not terminal.isatty():
                raise LiveModeError()
            terminal.write('LIVE publication to naie. Only continue during a Sat/Sun session '
                           'started by the owner. Type LIVE naie and press Enter for this session: ')
            terminal.flush()
            if response.readline(64) != 'LIVE naie\n':
                raise LiveModeError()
        if session.auth.clock() >= expires_at:
            raise LiveModeError()
    except Exception:
        raise LiveModeError() from None
    approval = object.__new__(LiveApproval)
    approval._consumed = False
    approval._lock = threading.Lock()
    return approval

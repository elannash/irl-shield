"""Session-local approval for the owner's attended naie live sessions."""
import asyncio
import os
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


async def _confirmation(response, cancel, timeout):
    """Own a readiness callback, not a blocking reader thread or terminal mode."""
    loop = asyncio.get_running_loop()
    ready = loop.create_future()
    fd = response.fileno()
    blocking = os.get_blocking(fd)
    line = bytearray()
    def readable():
        if ready.done():
            return
        try:
            part = os.read(fd, 64 - len(line))
            line.extend(part)
            if not part or b'\n' in part or len(line) == 64:
                ready.set_result(bytes(line))
        except BlockingIOError:
            return
        except Exception as error:
            ready.set_exception(error)
    cancelled = asyncio.create_task(cancel.wait()) if cancel is not None else None
    try:
        os.set_blocking(fd, False)
        loop.add_reader(fd, readable)
        waiting = {ready, cancelled} if cancelled is not None else {ready}
        done, _ = await asyncio.wait(waiting, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
        if cancel is not None and cancel.is_set():
            raise asyncio.CancelledError
        if ready not in done or ready.result() != b'LIVE naie\n':
            raise LiveModeError()
    finally:
        loop.remove_reader(fd)
        os.set_blocking(fd, blocking)
        ready.cancel()
        if cancelled is not None:
            cancelled.cancel()
            await asyncio.gather(cancelled, return_exceptions=True)


async def authorize_live(session, http, cancel=None):
    """Bypass cached validation, then ask on /dev/tty for this session only."""
    try:
        if cancel is not None and cancel.is_set():
            raise asyncio.CancelledError
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
            await _confirmation(response, cancel, max(0, expires_at - session.auth.clock()))
        if cancel is not None and cancel.is_set():
            raise asyncio.CancelledError
        if session.auth.clock() >= expires_at:
            raise LiveModeError()
    except Exception:
        raise LiveModeError() from None
    approval = object.__new__(LiveApproval)
    approval._consumed = False
    approval._lock = threading.Lock()
    return approval

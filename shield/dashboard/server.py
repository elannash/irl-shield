"""Authenticated aiohttp service isolated from Twitch, render and archive state."""
import asyncio
import hmac
import inspect
import json
from pathlib import Path
import secrets

from aiohttp import web

from .pairing import PairingData, private_address
from .snapshot import public_snapshot

ASSETS = Path(__file__).parent
HEADERS = {
    'Cache-Control': 'no-store, max-age=0',
    'Pragma': 'no-cache',
    'Referrer-Policy': 'no-referrer',
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Cross-Origin-Resource-Policy': 'same-origin',
    'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src blob:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
}


class DashboardServer:
    """Callbacks run on this event loop; root owns thread-safe engine handoff.

    set_manual_hold(False) MUST release only the local/manual source. No
    generic control object, renderer or outgoing stream is retained here.
    """

    def __init__(self, *, host, port, get_public_snapshot, set_manual_hold, pairing: PairingData):
        self.host = private_address(host)
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError('Invalid dashboard port')
        self.port = port
        self._snapshot = get_public_snapshot
        self._hold = set_manual_hold
        self._pairing = pairing
        self._token = None
        self._runner = None
        self._authority = None
        self._origin = None
        self._control_lock = asyncio.Lock()

    async def _call(self, callback, *args):
        result = callback(*args)
        return await result if inspect.isawaitable(result) else result

    async def start(self):
        if self._runner is not None:
            raise RuntimeError('Dashboard already started')
        self._token = secrets.token_urlsafe(32)
        app = web.Application(middlewares=[self._security], client_max_size=1024)
        app.router.add_get('/', self._bootstrap)
        app.router.add_get('/bootstrap.js', self._script)
        app.router.add_get('/dashboard.css', self._style)
        app.router.add_get('/private/ui', self._ui)
        app.router.add_get('/private/snapshot', self._status)
        app.router.add_post('/private/hold', self._manual)
        app.router.add_get('/private/pairing', self._pair)
        app.router.add_get('/private/qr/{protocol}.png', self._qr)
        # Disable access and exception loggers: requests may contain malicious
        # credential-bearing paths/headers; handlers emit only fixed errors.
        self._runner = web.AppRunner(app, access_log=None, logger=None, shutdown_timeout=2)
        try:
            await self._runner.setup()
            site = web.TCPSite(self._runner, self.host, self.port)
            await site.start()
            self.port = site._server.sockets[0].getsockname()[1]
            address = f'[{self.host}]' if ':' in self.host else self.host
            self._authority = f'{address}:{self.port}'
            self._origin = f'http://{self._authority}'
            self._announce()
        except Exception:
            await self.close()
            raise RuntimeError('Dashboard could not start; private terminal required') from None

    def _announce(self):
        # A missing controlling terminal is a startup failure, never a stdout fallback.
        with open('/dev/tty', 'w', encoding='utf-8') as terminal:
            terminal.write(f'IRL Shield private dashboard: {self._origin}/#token={self._token}\n')
            terminal.flush()

    async def close(self):
        if self._runner is not None:
            await self._runner.cleanup()
        self._runner = None
        self._token = None
        self._authority = None
        self._origin = None

    @web.middleware
    async def _security(self, request, handler):
        try:
            if (request.headers.getall('Host', []) != [self._authority]
                    or request.query_string
                    or len(request.headers.getall('Origin', [])) > 1
                    or request.headers.get('Origin') not in (None, self._origin)
                    or request.headers.get('Sec-Fetch-Site') not in (None, 'same-origin', 'none')):
                response = web.Response(status=403, text='Request rejected')
            elif request.method not in ('GET', 'HEAD', 'POST'):
                response = web.Response(status=405, text='Method not allowed')
            elif request.path not in ('/', '/bootstrap.js', '/dashboard.css'):
                auth = request.headers.getall('Authorization', [])
                expected = f'Bearer {self._token}'
                if len(auth) != 1 or not hmac.compare_digest(auth[0].encode(), expected.encode()):
                    response = web.Response(status=401, text='Dashboard authorization required')
                elif request.method == 'POST' and request.headers.get('Origin') != self._origin:
                    response = web.Response(status=403, text='Request rejected')
                else:
                    response = await handler(request)
            else:
                response = await handler(request)
        except asyncio.CancelledError:
            raise
        except web.HTTPException as error:
            response = web.Response(status=error.status, text='Request unavailable')
        except Exception:
            # Callback/parse exceptions can contain private URLs or credentials.
            response = web.Response(status=503, text='Dashboard unavailable')
        response.headers.update(HEADERS)
        return response

    async def _bootstrap(self, request):
        return web.Response(text=(ASSETS / 'bootstrap.html').read_text(), content_type='text/html')

    async def _script(self, request):
        return web.Response(text=(ASSETS / 'bootstrap.js').read_text(), content_type='text/javascript')

    async def _style(self, request):
        return web.Response(text=(ASSETS / 'dashboard.css').read_text(), content_type='text/css')

    async def _ui(self, request):
        return web.Response(text=(ASSETS / 'dashboard.html').read_text(), content_type='text/html')

    async def _status(self, request):
        safe = public_snapshot(await self._call(self._snapshot))
        return web.json_response(safe)

    async def _manual(self, request):
        if request.content_type != 'application/json':
            return web.Response(status=415, text='Expected JSON')
        try:
            payload = json.loads(await request.text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return web.Response(status=400, text='Expected a manual hold choice')
        if type(payload) is not dict or set(payload) != {'active'} or type(payload['active']) is not bool:
            return web.Response(status=400, text='Expected a manual hold choice')
        async with self._control_lock:
            await self._call(self._hold, payload['active'])
        return web.json_response({'accepted': True})

    async def _pair(self, request):
        return web.json_response(self._pairing.private_payload())

    async def _qr(self, request):
        protocol = request.match_info['protocol']
        if protocol not in ('rtmp', 'srt') or (protocol == 'srt' and self._pairing.srt_url is None):
            return web.Response(status=404, text='Pairing unavailable')
        return web.Response(body=self._pairing.qr_png(protocol), content_type='image/png')

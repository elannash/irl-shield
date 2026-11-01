"""Synthetic loopback security and independent QR/encoded-output boundary tests."""
import asyncio
from contextlib import redirect_stdout, redirect_stderr
from io import BytesIO, StringIO
import ipaddress
import json
import logging
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlsplit, parse_qs

import aiohttp
import av
import cv2
import numpy as np

from shield.control import Control
from shield.dashboard import DashboardServer, PairingData, presentation_fields, public_snapshot
from shield.dashboard.pairing import private_address
from shield.render import Renderer


TAILNET = ipaddress.IPv4Network('100.64.0.0/10')
TAILNET_HOST = '.'.join(map(str, (100, 100, 10, 20)))

cv2.setNumThreads(1)
RTMP = f'rtmp://{TAILNET_HOST}:1935/live/canary-stream?user=canary-user&pass=canary-pass%2Bword'
SRT = f'srt://{TAILNET_HOST}:9000?streamid=canary-srt&passphrase=canary-srt-pass'
CANARIES = ('canary-stream', 'canary-user', 'canary-pass', 'canary-srt', 'canary-dashboard')


def snapshot():
    return dict(state='LIVE', reason_code='clear', clues_hidden=17, faces_hidden=4,
                face_mode='bystanders', skin='frosted', votes={'frosted': 3, 'bar': 1}, skin_locked=False)


class Terminal(StringIO):
    def __exit__(self, *args):
        pass


class DashboardHTTP(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.terminal = Terminal()
        self.stdout, self.stderr, self.logs = StringIO(), StringIO(), StringIO()
        self.out_context, self.err_context = redirect_stdout(self.stdout), redirect_stderr(self.stderr)
        self.out_context.__enter__(); self.err_context.__enter__()
        self.log_handler = logging.StreamHandler(self.logs)
        logging.getLogger().addHandler(self.log_handler)
        self.raw = snapshot()
        self.calls = []
        self.control = Control()
        self.control.update_coverage(True, 'clear', 0)
        def hold(active):
            self.calls.append(active)
            self.control.set_hold(active, source='local', reason='manual', at=1)
        self.server = DashboardServer(host='127.0.0.1', port=0,
            get_public_snapshot=lambda: self.raw, set_manual_hold=hold, pairing=PairingData(RTMP, SRT))
        with patch('shield.dashboard.server.open', return_value=self.terminal, create=True) as opened:
            await self.server.start()
        opened.assert_called_once_with('/dev/tty', 'w', encoding='utf-8')
        self.origin = f'http://127.0.0.1:{self.server.port}'
        self.token = self.terminal.getvalue().split('#token=')[1].strip()
        self.headers = {'Authorization': 'Bearer ' + self.token}
        self.client = aiohttp.ClientSession()

    async def asyncTearDown(self):
        port = self.server.port
        await self.client.close()
        await self.server.close()
        with self.assertRaises(OSError):
            await asyncio.open_connection('127.0.0.1', port)
        logging.getLogger().removeHandler(self.log_handler)
        self.out_context.__exit__(None, None, None); self.err_context.__exit__(None, None, None)
        emitted = self.stdout.getvalue() + self.stderr.getvalue() + self.logs.getvalue()
        self.assertFalse(self.token in emitted, 'Dashboard token reached stdout/stderr/logging')
        for canary in CANARIES:
            self.assertNotIn(canary, emitted)
        self.assertIsNone(self.server._token)

    async def get(self, path, **kwargs):
        return await self.client.get(self.origin + path, **kwargs)

    async def test_all_private_routes_require_header_token_and_are_uncacheable(self):
        for path in ('/private/ui', '/private/snapshot', '/private/pairing', '/private/qr/rtmp.png', '/private/qr/srt.png'):
            for headers in ({}, {'Authorization': 'Bearer wrong'}, {'Cookie': 'token=' + self.token}):
                response = await self.get(path, headers=headers)
                self.assertEqual(response.status, 401)
                body = await response.text()
                self.assertFalse(self.token in body)
                self.assertIn('no-store', response.headers['Cache-Control'])
                self.assertNotIn('Access-Control-Allow-Origin', response.headers)
            response = await self.get(path, headers=self.headers)
            self.assertEqual(response.status, 200, path)
            await response.read()
            self.assertIn('no-store', response.headers['Cache-Control'])
        response = await self.client.post(self.origin + '/private/hold', json={'active': True})
        self.assertEqual(response.status, 401)
        self.assertEqual(self.calls, [])

    async def test_bootstrap_has_no_private_html_pairing_or_token(self):
        for path in ('/', '/bootstrap.js', '/dashboard.css'):
            response = await self.get(path)
            self.assertEqual(response.status, 200)
            text = await response.text()
            for secret in (*CANARIES, self.token, RTMP, SRT):
                self.assertFalse(secret in text)
            self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])
        response = await self.get('/')
        self.assertNotIn('id="qr"', await response.text())

    async def test_host_origin_query_and_csrf_rejection(self):
        for headers in ({'Host': 'evil.invalid'}, {'Host': 'localhost:' + str(self.server.port)},
                        {'Origin': 'https://evil.invalid'}, {'Origin': 'null'}, {'Sec-Fetch-Site': 'cross-site'}):
            response = await self.get('/private/pairing', headers={**self.headers, **headers})
            self.assertEqual(response.status, 403)
            self.assertNotIn('canary-', await response.text())
        for path in ('/?token=canary-dashboard', '/private/snapshot?token=canary-dashboard'):
            response = await self.get(path, headers=self.headers)
            self.assertEqual(response.status, 403)
        for origin in (None, 'http://evil.invalid'):
            headers = dict(self.headers)
            if origin is not None: headers['Origin'] = origin
            response = await self.client.post(self.origin + '/private/hold', headers=headers, json={'active': True})
            self.assertEqual(response.status, 403)
        self.assertEqual(self.calls, [])

    async def test_resume_clears_local_only_with_chat_shield_transport_active(self):
        for source in ('chat', 'shield_mode', 'transport'):
            self.control.set_hold(True, source=source, reason=source, at=0)
        for active in (True, False):
            response = await self.client.post(self.origin + '/private/hold',
                headers={**self.headers, 'Origin': self.origin}, json={'active': active})
            self.assertEqual(response.status, 200)
            self.assertEqual(await response.json(), {'accepted': True})
        self.assertEqual(self.calls, [True, False])
        for source in ('chat', 'shield_mode'):
            self.control.set_hold(False, source=source, at=2)
            self.assertEqual(self.control.state, 'HOLD')
        self.assertEqual(self.control.reason, 'transport')
        self.control.set_hold(False, source='transport', at=2)
        self.assertEqual(self.control.state, 'LIVE')

    async def test_invalid_control_payload_never_calls_callback(self):
        for payload in ({'active': 'false'}, {'active': 1}, {'active': False, 'release_all': True}, {}):
            response = await self.client.post(self.origin + '/private/hold',
                headers={**self.headers, 'Origin': self.origin}, json=payload)
            self.assertEqual(response.status, 400)
        for body, expected in ((b'{', 400), (b'x' * 1025, 413)):
            response = await self.client.post(self.origin + '/private/hold',
                headers={**self.headers, 'Origin': self.origin, 'Content-Type': 'application/json'}, data=body)
            self.assertEqual(response.status, expected)
        self.assertEqual(self.calls, [])

    async def test_callback_exceptions_are_fixed_errors_without_secret_logs(self):
        def broken():
            raise RuntimeError(RTMP + self.token)
        self.server._snapshot = broken
        response = await self.get('/private/snapshot', headers=self.headers)
        self.assertEqual((response.status, await response.text()), (503, 'Dashboard unavailable'))
        response = await self.get('/private/missing/canary-dashboard', headers=self.headers)
        self.assertEqual((response.status, await response.text()), (404, 'Request unavailable'))

    async def test_actual_snapshot_serialization_drops_private_fields_and_untrusted_reason(self):
        self.raw.update(dashboard_token='canary-dashboard', rtmp_url=RTMP, qr='canary-qr',
                        reason_code='canary-pass', coordinates='canary-place', candidate='canary-place')
        response = await self.get('/private/snapshot', headers=self.headers)
        self.assertEqual(response.status, 200)
        data = await response.json()
        self.assertEqual(set(data), {'state', 'reason_code', 'clues_hidden', 'faces_hidden', 'face_mode', 'skin', 'votes', 'skin_locked'})
        self.assertEqual(data['reason_code'], 'unknown')
        self.assertEqual((data['clues_hidden'], data['faces_hidden']), (17, 4))
        for canary in CANARIES:
            self.assertNotIn(canary, json.dumps(data))
        # Positive control: the private endpoint actually has the synthetic secret.
        response = await self.get('/private/pairing', headers=self.headers)
        private = await response.json()
        self.assertEqual(private['rtmp_url'], RTMP)
        self.assertEqual(private['srt_status'], 'unqualified')

    async def test_unavailable_totals_preserve_current_privacy_state(self):
        for clues, faces in ((None, None), (None, 4), (0, None)):
            with self.subTest(clues=clues, faces=faces):
                self.raw.update(clues_hidden=clues, faces_hidden=faces)
                response = await self.get('/private/snapshot', headers=self.headers)
                self.assertEqual(response.status, 200)
                data = await response.json()
                self.assertEqual((data['state'], data['reason_code']), ('LIVE', 'clear'))
                self.assertEqual((data['clues_hidden'], data['faces_hidden']), (clues, faces))
        self.raw['clues_hidden'] = True
        response = await self.get('/private/snapshot', headers=self.headers)
        self.assertEqual(response.status, 503)

    async def test_malformed_http_closes_cleanly_without_protocol_log_errors(self):
        loop = asyncio.get_running_loop()
        previous = loop.get_exception_handler()
        protocol_errors = []
        loop.set_exception_handler(lambda _, context: protocol_errors.append(
            type(context.get('exception')).__name__))
        writer = None
        try:
            reader, writer = await asyncio.open_connection('127.0.0.1', self.server.port)
            writer.write(b'BAD-CANARY-REQUEST\x00 / HTTP/1.1\r\nHost: canary-dashboard\r\n\r\n')
            await writer.drain()
            reply = await asyncio.wait_for(reader.read(), 30)
            writer.close()
            await writer.wait_closed()
            await asyncio.sleep(0)
            self.assertTrue(reply.startswith((b'HTTP/1.0 400', b'HTTP/1.1 400')),
                            'Malformed request must receive an ordinary HTTP 400')
            self.assertEqual(protocol_errors, [])
            self.assertEqual(self.calls, [])
            response = await self.get('/private/snapshot', headers=self.headers)
            self.assertEqual(response.status, 200)
        finally:
            if writer is not None:
                writer.close()
                await writer.wait_closed()
            loop.set_exception_handler(previous)

    async def test_qr_positive_decode_exact_credentials_single_outer_decode(self):
        response = await self.get('/private/qr/rtmp.png', headers=self.headers)
        self.assertEqual(response.status, 200)
        image = cv2.imdecode(np.frombuffer(await response.read(), np.uint8), cv2.IMREAD_COLOR)
        text, points, _ = cv2.QRCodeDetector().detectAndDecode(image)
        self.assertIsNotNone(points)
        self.assertTrue(text.startswith('moblin://?'))
        imported = json.loads(unquote(text.split('?', 1)[1]))
        stream = imported['streams'][0]
        self.assertEqual(stream, {'name': 'IRL Shield', 'url': RTMP, 'selected': True})
        self.assertEqual(parse_qs(urlsplit(stream['url']).query), {'user': ['canary-user'], 'pass': ['canary-pass+word']})
        self.assertTrue(stream['url'].rsplit('/', 1)[1].endswith('?user=canary-user&pass=canary-pass%2Bword'))
        self.assertNotIn('%3Fuser', stream['url'])


class DashboardBoundaries(unittest.TestCase):
    def test_bind_and_pairing_reject_public_dns_wildcard_and_reflect_no_input(self):
        for host in ('0.0.0.0', '::', 'localhost', '8.8.8.8', '192.168.1.1', '100.63.255.255', '100.128.0.0', 'canary-pass', 2130706433):
            with self.assertRaisesRegex(ValueError, '^Expected a literal loopback or Tailscale address$'):
                private_address(host)
        for host in ('127.0.0.1', '::1', str(TAILNET.network_address), str(TAILNET.broadcast_address)):
            self.assertEqual(private_address(host), host)
        for url in ('rtmp://evil.invalid:1935/live/canary-pass', f'rtmp://{TAILNET_HOST}:1935/live/key#canary-pass',
                    f'rtmp://canary-user:canary-pass@{TAILNET_HOST}:1935/live/key', f'rtmp://{TAILNET_HOST}/live/key',
                    f'rtmp://{TAILNET_HOST}:1935/live/key?pass=canary-pass/raw',
                    RTMP + '\n', f'https://{TAILNET_HOST}:443/canary-pass'):
            with self.assertRaisesRegex(ValueError, '^Invalid private stream configuration$'):
                PairingData(url)
        self.assertNotIn('canary-', repr(PairingData(RTMP, SRT)))

    def test_snapshot_rejects_credentials_in_modes_voter_names_and_nonfinite_risk(self):
        for field, value in [('state', 'canary-pass'), ('skin', 'canary-pass'), ('face_mode', 'canary-pass'),
                             ('votes', {'canary-user': 1}), ('clues_hidden', True), ('faces_hidden', -1),
                             ('skin_locked', 'canary-pass')]:
            raw = snapshot(); raw[field] = value
            with self.assertRaises(ValueError): public_snapshot(raw)
        for risk, age in ((float('nan'), 1), (.5, float('inf')), (1.01, 0), (.5, -1)):
            raw = snapshot(); raw.update(geo_risk=risk, geo_risk_age_s=age)
            with self.assertRaises(ValueError): public_snapshot(raw)
        raw = snapshot(); raw.update(geo_risk=.35, geo_risk_age_s=12, place='canary-place')
        self.assertEqual(public_snapshot(raw)['geo_risk'], .35)
        self.assertNotIn('geo_risk', presentation_fields(raw))

    def test_private_pairing_changes_cannot_affect_renderer_or_encoded_archive(self):
        raw = snapshot()
        # Private data is present before the real serialization/projection boundary.
        raw.update(dashboard_token='canary-dashboard', rtmp_url=RTMP,
                   qr_png=PairingData(RTMP).qr_png(), geo_risk=.7, geo_risk_age_s=3)
        projected = presentation_fields(raw)
        self.assertEqual(projected, {'state': 'LIVE', 'reason_code': 'clear', 'clue_count': 17, 'face_count': 4, 'skin_name': 'frosted'})
        self.assertNotIn('canary-', json.dumps(projected))
        frame = np.zeros((96, 160, 3), np.uint8)
        cv2.rectangle(frame, (50, 30), (90, 60), (140, 100, 80), -1)
        def render(fields):
            return Renderer(badge=True).render(frame, [], state=fields['state'], clues=fields['clue_count']).pixels
        first = render(projected)
        raw.update(dashboard_token='different-private-token', rtmp_url=RTMP + '-changed', qr_png=b'different-private-pixels')
        second = render(presentation_fields(raw))
        np.testing.assert_array_equal(first, second)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.mkv'
            with av.open(str(path), mode='w') as container:
                stream = container.add_stream('ffv1', rate=1)
                stream.width, stream.height, stream.pix_fmt = 160, 96, 'bgr0'
                for pixels in (first, second):
                    for packet in stream.encode(av.VideoFrame.from_ndarray(pixels, format='bgr24')): container.mux(packet)
                for packet in stream.encode(): container.mux(packet)
            archive = path.read_bytes()
            for canary in CANARIES: self.assertNotIn(canary.encode(), archive)
            with av.open(str(path)) as container:
                decoded = [frame.to_ndarray(format='bgr24') for frame in container.decode(video=0)]
            self.assertEqual(len(decoded), 2)
            for pixels in decoded:
                np.testing.assert_array_equal(pixels, first)
                text, points, _ = cv2.QRCodeDetector().detectAndDecode(pixels)
                self.assertEqual(text, '')
                self.assertIsNone(points)

    def test_tty_failure_aborts_listener_without_stdout_fallback(self):
        async def exercise():
            server = DashboardServer(host='127.0.0.1', port=0, get_public_snapshot=snapshot,
                                     set_manual_hold=lambda active: None, pairing=PairingData(RTMP))
            output = StringIO()
            with redirect_stdout(output), redirect_stderr(output), patch('shield.dashboard.server.open', side_effect=OSError(RTMP), create=True):
                with self.assertRaisesRegex(RuntimeError, '^Dashboard could not start; private terminal required$'):
                    await server.start()
            self.assertEqual(output.getvalue(), '')
            self.assertIsNone(server._runner)
            self.assertIsNone(server._token)
            with self.assertRaises(OSError): await asyncio.open_connection('127.0.0.1', server.port)
        asyncio.run(exercise())

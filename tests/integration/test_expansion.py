"""Expansion seams: authenticated voting, exact pixels and private phone controls."""
import asyncio
from io import StringIO
import threading
import unittest
from unittest.mock import patch

import aiohttp
import numpy as np

from relay.bridge import NoOpDetector
from relay.live import RelayControl, RelaySession
from shield.app.appearance import Appearance
from shield.control import Control
from shield.engine import MaskingEngine
from shield.lanes import DetectorLane
from shield.types import Coverage, PresentedFrame
from tests.m3.test_events import START, adapter, notification


def engine_for(appearance):
    engine = MaskingEngine({n: DetectorLane(n, NoOpDetector(), 30) for n in ('fast', 'accurate')},
        {'fps': 30, 'delay_seconds': .1}, renderer=appearance.renderer(padding=.3))
    appearance.engine = engine
    return engine


class Expansion(unittest.TestCase):
    def test_real_event_policy_only_passes_authenticated_skin_roles_and_current_generation(self):
        with patch('shield.app.appearance.time') as clock:
            clock.time.return_value = START
            clock.monotonic.return_value = 10
            appearance = Appearance(width=320, height=180)
            clock.monotonic.return_value = 20
            _, events = adapter(on_chat=appearance.chat)
            generation = events.generation
            self.assertEqual(events.accept(notification('viewer', '!skin bar', badge=None), generation=generation), 'skin-chat')
            self.assertEqual(appearance.snapshot()['votes'], {'bar': 1})
            self.assertEqual(events.accept(notification('viewer-lock', '!skin lock bar', badge=None, at=START+2), generation=generation), 'skin-chat')
            self.assertFalse(appearance.snapshot()['skin_locked'])
            events.accept(notification('mod-lock', '!skin lock bar', at=START+3), generation=generation)
            self.assertTrue(appearance.snapshot()['skin_locked'])
            self.assertEqual(appearance.snapshot()['skin'], 'bar')
            shared = notification('shared', '!skin unlock', actor='1', at=START+4)
            shared['payload']['event']['source_broadcaster_user_id'] = '999'
            self.assertEqual(events.accept(shared, generation=generation), 'ignored')
            self.assertEqual(events.accept(notification('old-generation', '!skin unlock', actor='1', at=START+4), generation=generation-1), 'inactive')
            self.assertTrue(appearance.snapshot()['skin_locked'])
            events.accept(notification('owner-unlock', '!skin unlock', actor='1', at=START+5), generation=generation)
            self.assertFalse(appearance.snapshot()['skin_locked'])
            events.accept(notification('viewer', '!skin bar', badge=None, at=START+6), generation=generation)
            clock.monotonic.return_value = 72
            self.assertEqual(appearance.snapshot()['votes'], {}, 'Replay must not extend the authenticated vote lifetime')

    def test_actual_relay_keeps_poll_identity_and_ingress_highwater_through_hold_release(self):
        appearance = Appearance(width=320, height=180)
        engine = engine_for(appearance)
        written = []
        relay = RelaySession(engine, lambda f, pcm: written.append(f), width=320, height=180,
                             start=10, appearance=appearance)
        raw = np.full((180, 320, 3), 211, np.uint8)
        def presented(index):
            return PresentedFrame(index, index/30, raw.copy(), np.zeros((180,320), np.uint8), [],
                Coverage(0,0,True,'covered'), 'LIVE', 10+index/30, 10+index/30, False, False)
        try:
            relay.video(0, raw, 1, now=10+10/30)
            self.assertEqual(relay.last_index, 10)
            engine.control.update_coverage(True, 'covered', 10)
            first = presented(5)
            def hold_after_poll(*args, **kwargs):
                relay.control.hold(True)
                return [first]
            with patch.object(engine, 'poll', side_effect=hold_after_poll):
                relay.tick(10.5)
            self.assertIs(written[-1], first)
            self.assertEqual(first.state, 'HOLD')
            self.assertTrue(first.slate and np.all(first.mask==255))
            relay.control.hold(False)
            before, fresh, replay = presented(7), presented(11), presented(8)
            for frame in (before, fresh, replay):
                with patch.object(engine, 'poll', return_value=[frame]):
                    relay.tick(10.7)
                self.assertIs(written[-1], frame)
            self.assertTrue(before.slate)
            self.assertFalse(fresh.slate)
            self.assertTrue(replay.slate)
            self.assertTrue(np.all(replay.mask==255))
            np.testing.assert_array_equal(fresh.pixels, raw, 'Unavailable counts must not draw a false zero caption')
            self.assertIsNone(appearance.snapshot()['clues_hidden'])
            self.assertIsNone(appearance.snapshot()['faces_hidden'])
        finally:
            engine.close()


    def test_slate_distinguishes_operator_holds_from_automatic_transport(self):
        from shield.presentation import PresentationRenderer, PresentationSnapshot
        raw = np.full((180, 320, 3), 211, np.uint8)
        cases = [
            ([('transport', 'ingest-drop')], 'FAILURE', 'transport'),
            ([('chat', 'moderator'), ('transport', 'ingest-drop')], 'HOLD', 'moderator'),
            ([('shield_mode', 'shield-mode'), ('transport', 'ingest-drop')], 'SHIELD_MODE', 'shield_mode'),
        ]
        for sources, shown_state, shown_reason in cases:
            with self.subTest(sources=sources):
                appearance = Appearance(width=320, height=180)
                engine = engine_for(appearance)
                try:
                    for source, reason in sources:
                        engine.hold(True, source=source, reason=reason)
                    frame = PresentedFrame(5, 5/30, raw.copy(), np.zeros((180,320), np.uint8), [],
                        Coverage(0,0,True,'covered'), 'HOLD', 0., 0., True, True)
                    actual = appearance.present(frame, capture_highwater=10)
                    expected = PresentationRenderer(320,180,badge=False).render(raw,
                        np.zeros((180,320),np.uint8), PresentationSnapshot(shown_state, reason_code=shown_reason),
                        source_sequence=10)
                    np.testing.assert_array_equal(actual.pixels, expected.pixels,
                        'Automatic recovery must not claim operator resume; operator holds retain their slate')
                    self.assertEqual(actual.state, 'HOLD', 'Visual copy must not relabel the control HOLD')
                    self.assertTrue(actual.slate and np.all(actual.mask==255))
                finally:
                    engine.close()


class Terminal(StringIO):
    def __exit__(self, *args):
        pass


class DashboardCLI(unittest.IsolatedAsyncioTestCase):
    async def test_real_cli_dashboard_callbacks_preserve_chat_and_close_private_listener(self):
        from shield.cli import execute, parser
        from shield.dashboard import DashboardServer
        terminal = Terminal()
        servers = []
        engines = []
        controls = []
        ready = asyncio.Event()
        loop = asyncio.get_running_loop()
        release = threading.Event()
        class ObservedServer(DashboardServer):
            async def start(self):
                await super().start()
                servers.append(self)
        def make_engine(cache, *, appearance):
            engine = engine_for(appearance)
            engines.append(engine)
            return engine
        def runtime(engine, address, phone, internal, directory, stopped, seconds, **kwargs):
            control = RelayControl(engine)
            controls.append(control)
            kwargs['control_ready'](control)
            engine.control.update_coverage(True, 'covered', 0)
            control.hold(True, source='chat', reason='moderator')
            loop.call_soon_threadsafe(ready.set)
            try:
                if not release.wait(30):
                    raise RuntimeError('Synthetic CLI cancellation fuse')
                return {'status':'stopped'}
            finally:
                engine.close()
        with patch('relay.mediamtx.MediaMTX'), patch('relay.mediamtx.verified_binary'), \
             patch('relay.runtime.make_engine', side_effect=make_engine), \
             patch('relay.runtime.run', side_effect=runtime), \
             patch('shield.dashboard.DashboardServer', ObservedServer), \
             patch('shield.dashboard.server.open', return_value=terminal, create=True):
            work = asyncio.create_task(execute(parser().parse_args(['run','--local-only','--host','127.0.0.1','--dashboard'])))
            try:
                await asyncio.wait_for(ready.wait(), 30)
                self.assertEqual(len(servers), 1)
                server = servers[0]
                origin = f'http://127.0.0.1:{server.port}'
                headers = {'Authorization':'Bearer '+server._token,'Origin':origin}
                async with aiohttp.ClientSession() as client:
                    for active in (True,False):
                        response = await client.post(origin+'/private/hold', headers=headers, json={'active':active})
                        self.assertEqual(response.status, 200)
                        self.assertEqual(await response.json(), {'accepted':True})
                    self.assertEqual(engines[0].control.state, 'HOLD')
                    self.assertEqual(engines[0].control.reason, 'moderator')
                    response = await client.get(origin+'/private/snapshot', headers=headers)
                    data = await response.json()
                    self.assertEqual((data['state'], data['reason_code']), ('HOLD','chat'))
                    self.assertEqual(data['skin'], 'bar', 'The real CLI must start the measured default material')
                    self.assertEqual((data['clues_hidden'],data['faces_hidden']), (None,None))
                    self.assertNotIn(server._token, str(data))
                    self.assertIn('/#token=', terminal.getvalue())
            finally:
                release.set()
                await work
            self.assertIsNone(servers[0]._token)
            with self.assertRaises(OSError):
                await asyncio.open_connection('127.0.0.1', servers[0].port)

"""Production decoder clock recovery over real MPEG-TS/TCP (CPU only)."""
import time
import unittest

from relay.live import RelaySession
from relay.stream import NetworkInput
from recovery_fixture import engine
from srt_fixture import TCPVideo, mpegts


class SRTInput(unittest.TestCase):
    def test_decoded_clock_reset_reanchors_without_latched_transport_hold(self):
        # Existing EOF tests close the socket. A phone can restart its clock
        # inside the same TS transport, leaving the decoder connection alive.
        publisher = TCPVideo([mpegts(origin=80), mpegts(origin=10)])
        source = NetworkInput(publisher.url)
        model = engine(delay=.05)
        output = []
        session = RelaySession(model, lambda frame, pcm: output.append(frame), width=64, height=64)
        seen = []
        try:
            deadline = time.monotonic() + 9
            while time.monotonic() < deadline:
                rows = source.drain()
                seen.extend((kind, pts, generation) for kind, pts, _, generation, _ in rows)
                for kind, pts, value, generation, arrived in rows:
                    if kind == 'video':
                        session.video(pts, value, generation, now=arrived)
                    elif kind == 'audio':
                        session.audio(pts, value, generation)
                    else:
                        session.disconnected()
                session.tick()
                if publisher.finished.is_set() and any(kind == 'video' and gen > 1 for kind, _, gen in seen):
                    break
                time.sleep(.003)
            self.assertEqual(publisher.errors, [])
            self.assertTrue(any(kind == 'video' and pts > 79 for kind, pts, _ in seen), seen[-10:])
            reset_video = [(pts, gen) for kind, pts, gen in seen if kind == 'video' and (pts < 14 or pts > 1000)]
            self.assertTrue(reset_video, {'reason': 'the reset must reach the real decoder', 'seen_tail': seen[-12:], 'issues': source.timestamp_issues, 'failure': source.last_failure})
            self.assertGreater(reset_video[-1][1], 1, 'a reset must invalidate the old timeline and reanchor a newer generation')
            self.assertGreater(session.stats['sessions'], 1)
            self.assertTrue(any(kind == 'drop' for kind, _, _ in seen))
            self.assertGreater(source.timestamp_issues['packet_pts_ne_dts'], 0)
            self.assertEqual(source.timestamp_issues['discontinuities'], 1)
            self.assertNotEqual(model.control.state, 'HOLD', 'the newer generation must release transport HOLD')
            self.assertTrue(any(frame.state == 'LIVE' and frame.pixels.any() for frame in output))
        finally:
            publisher.close()
            source.close()
            model.close()



class SRTNetwork(unittest.TestCase):
    def test_real_srt_disconnect_reconnect_preserves_moderator_hold(self):
        import json
        from srt_fixture import SRTPublisher, local_server
        server, address, phone, internal = local_server()
        payload = mpegts(origin=10, frames=360)
        with server:
            source = NetworkInput(address.rtsp('camera', internal))
            model = engine(delay=1.)
            output = []
            session = RelaySession(model, lambda frame, pcm: output.append(frame), width=64, height=64)
            first = second = None
            seen = []

            def advance(predicate, seconds=6):
                end = time.monotonic() + seconds
                while time.monotonic() < end:
                    for kind, pts, value, gen, arrived in source.drain():
                        seen.append((kind, pts, gen))
                        if kind == 'video':
                            session.video(pts, value, gen, now=arrived)
                        elif kind == 'audio':
                            session.audio(pts, value, gen)
                        else:
                            session.disconnected()
                    session.tick()
                    if predicate():
                        return True
                    time.sleep(.003)
                return False

            try:
                first = SRTPublisher(address.srt('publish', 'camera', phone), payload)
                ready = advance(lambda: len([f for f in output if f.state == 'LIVE']) >= 3)
                from collections import Counter
                diagnostic = {'failure': source.last_failure, 'active_generation': source.active_generation,
                              'publisher_errors': first.errors,
                              'timestamp_issues': source.timestamp_issues, 'seen_head': seen[:8],
                              'seen_tail': seen[-8:], 'session': session.stats,
                              'states': dict(Counter(f.state for f in output)),
                              'server_events': list(server.close_events)}
                print(json.dumps(diagnostic), flush=True)
                self.assertTrue(ready, diagnostic)
                self.assertGreater(source.timestamp_issues['packet_pts_ne_dts'], 0)
                self.assertEqual(source.timestamp_issues['discontinuities'], 0, source.timestamp_issues)
                old = session.generation
                session.control.hold(True, source='twitch-chat', reason='moderator')
                disconnections = session.disconnections
                first.process.kill()
                first.process.join(3)
                self.assertFalse(first.process.is_alive())
                self.assertTrue(advance(lambda: session.disconnections > disconnections), source.last_failure)
                self.assertEqual(model.control.state, 'HOLD')
                second = SRTPublisher(address.srt('publish', 'camera', phone), payload)
                replaced = advance(lambda: session.generation > old, seconds=15)
                reconnect = {'replaced': replaced, 'publisher_errors': second.errors,
                             'failure': source.last_failure,
                             'server_events': list(server.close_events), 'active_generation': source.active_generation}
                print(json.dumps(reconnect), flush=True)
                self.assertTrue(replaced, reconnect)
                self.assertEqual(model.control.state, 'HOLD', 'a reconnect must retain the moderator hold')
                session.control.hold(False, source='twitch-chat', reason='moderator')
                released = len(output)
                self.assertTrue(advance(lambda: any(f.state == 'LIVE' and f.pixels.any() for f in output[released:])), source.last_failure)
                self.assertGreater(session.sessions, 1)
                receipt = {'status': 'pass', 'session': session.stats,
                           'input_timestamp_issues': source.timestamp_issues,
                           'drop_events': list(source.drop_events),
                           'held_generation': old, 'released_generation': session.generation,
                           'outputs': len(output), 'live_after_release': sum(f.state == 'LIVE' for f in output[released:])}
                print(json.dumps(receipt), flush=True)
            finally:
                if first is not None:
                    first.close()
                if second is not None:
                    second.close()
                source.close()
                model.close()


if __name__ == '__main__':
    unittest.main()

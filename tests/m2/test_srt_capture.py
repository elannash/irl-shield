"""Independent raw-SRT capture must keep recording after a publisher returns."""
import tempfile
import time
import unittest
from pathlib import Path

from relay.srt_capture import Capture
from srt_fixture import SRTPublisher, local_server, mpegts


def until(predicate, seconds=7):
    end = time.monotonic() + seconds
    while not predicate() and time.monotonic() < end:
        time.sleep(.01)
    return predicate()


class SRTCapture(unittest.TestCase):
    def test_capture_resumes_after_publisher_disconnect(self):
        server, address, phone, internal = local_server()
        payload = mpegts(origin=10)
        scratch_root = Path('/tmp/agents/irl-shield/srt-tests')
        scratch_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch_root) as scratch, server:
            capture = Capture(address.srt('read', 'camera', internal), Path(scratch) / 'capture')
            first = second = None
            try:
                first = SRTPublisher(address.srt('publish', 'camera', phone), payload)
                self.assertTrue(until(lambda: capture.stats['packets'] > 60), capture.stats)
                first.close()
                self.assertEqual(first.errors, [])
                # Observe the server's close, rather than assuming a sleep
                # delivered the fault. The second publisher is a new SRT socket.
                self.assertTrue(until(lambda: any(e['protocol'] == 'SRT' for e in server.close_events)))
                self.assertTrue(until(lambda: capture.stats.get('receive_failures', 0) or not capture.thread.is_alive()))
                before = capture.stats['packets']
                second = SRTPublisher(address.srt('publish', 'camera', phone), payload)
                self.assertTrue(until(lambda: capture.stats['packets'] > before + 60), capture.stats)
                self.assertEqual(second.errors, [])
            finally:
                if first is not None:
                    first.close()
                if second is not None:
                    second.close()
                capture.close()
            self.assertFalse(capture.thread.is_alive())
            self.assertGreaterEqual(capture.stats['connections'], 2)
            import av
            for segment in (capture.segments[0], capture.segments[-1]):
                with av.open(str(capture.directory / segment['file'])) as clip:
                    for stream in clip.streams:
                        stream.codec_context.thread_count = 2
                    counts = {'video': 0, 'audio': 0}
                    for packet in clip.demux():
                        for frame in packet.decode():
                            counts['video' if isinstance(frame, av.VideoFrame) else 'audio'] += 1
                self.assertGreater(counts['video'], 0)
                self.assertGreater(counts['audio'], 0)

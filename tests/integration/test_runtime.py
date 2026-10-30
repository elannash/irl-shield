"""Production egress routing seam: fake transport, actual runtime/key callback."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from relay.runtime import run
from relay.security import Credentials, RelayAddress


class RuntimeDestination(unittest.TestCase):
    def test_callback_key_is_consumed_by_production_bandwidthtest_route_in_memory(self):
        captured = []
        class Engine:
            delay = .1
            stats = {}
            def hold(self, *args, **kwargs):
                pass
            def submit(self, *args, **kwargs):
                pass
            def close(self):
                pass
        class Output:
            error_code = error_details = None
            count = max_write_seconds = recovery_count = 0
            recovery_events = ()
            def __init__(self, urls, *args):
                captured.extend(urls)
            def write(self, frame, pcm):
                raise AssertionError('Stopped runtime must not encode a frame')
            def close(self):
                pass
        class Source:
            error_code = None
            high_water = active_generation = 0
            last_failure = None
            timestamp_issues = {}
            def __init__(self, url):
                pass
            def close(self):
                pass
        stopped = threading.Event()
        stopped.set()
        phone, internal = Credentials.generate(), Credentials.generate()
        from shield.cli import parser
        self.assertFalse(parser().parse_args(['run', '--host', '127.0.0.1']).twitch_bandwidth_test)
        with tempfile.TemporaryDirectory() as directory, patch('relay.runtime.Egress', Output), \
                patch('relay.runtime.NetworkInput', Source):
            # A configured/stored key alone must not even form a Twitch URL.
            with patch('relay.security.TwitchDestination.destination', side_effect=AssertionError('default route formed Twitch URL')):
                run(Engine(), RelayAddress('127.0.0.1'), phone, internal, directory, stopped,
                    width=32, height=32, control_ready=lambda control:
                    control.set_stream_key('SYNTHETIC-ROUTE-SENTINEL'))
            self.assertEqual(len(captured), 1)
            self.assertTrue(captured[0].startswith('rtmp://127.0.0.1:19350/shielded?'))
            captured.clear()
            self.assertTrue(parser().parse_args(['run', '--host', '127.0.0.1', '--twitch-bandwidth-test']).twitch_bandwidth_test)
            run(Engine(), RelayAddress('127.0.0.1'), phone, internal, directory, stopped,
                width=32, height=32, control_ready=lambda control:
                control.set_stream_key('SYNTHETIC-ROUTE-SENTINEL'), publish_twitch=True)
            self.assertEqual(len(captured), 2)
            self.assertTrue(captured[0].startswith('rtmp://127.0.0.1:19350/shielded?'))
            self.assertEqual(captured[1],
                             'rtmps://live.twitch.tv:443/app/SYNTHETIC-ROUTE-SENTINEL?bandwidthtest=true')
            summary = (Path(directory) / 'runtime.json').read_text()
            self.assertNotIn('SYNTHETIC-ROUTE-SENTINEL', summary)
            self.assertNotIn(internal.password, summary)
            self.assertEqual(json.loads(summary)['status'], 'stopped')

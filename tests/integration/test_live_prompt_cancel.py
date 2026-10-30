"""Real controlling-terminal CLI cancellation, with synthetic loopback OAuth."""
import asyncio
import fcntl
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import termios
import threading
import time
import unittest
from unittest.mock import patch

# The subprocess has the same import roots as the functional gate.
ROOT = Path(__file__).resolve().parents[2]


async def prompt_child():
    from shield.app.live import LiveModeError
    from shield.cli import execute, parser
    from shield.app.session import login
    from shield.twitch.http import TwitchHTTP
    from test_live_mode import LiveTwitch
    from network import local_network

    if os.isatty(0):
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)
        before_terminal = termios.tcgetattr(0)
    else:
        before_terminal = None
    before_threads = {thread.ident for thread in threading.enumerate()}
    loop = asyncio.get_running_loop()
    before_handlers = dict(loop._signal_handlers)
    boundaries = []
    def forbidden(name):
        def fail(*args, **kwargs):
            boundaries.append(name)
            raise AssertionError('startup crossed before approval: ' + name)
        return fail
    with local_network():
        async with LiveTwitch() as mock:
            class RoutedHTTP(TwitchHTTP):
                def __init__(self, session, **kwargs):
                    super().__init__(session, mock_origin=mock.origin)
            async def unattended_device_code(*args, **kwargs):
                # Synthetic OAuth code presentation is not the LIVE approval.
                return await login(*args, **kwargs, present=lambda _: None)
            with patch('shield.app.session.login', side_effect=unattended_device_code), \
                    patch.dict(os.environ, {'TWITCH_CLIENT_ID': 'synthetic-client',
                    'TWITCH_BROADCASTER_ID': '1'}), \
                    patch('shield.twitch.http.TwitchHTTP', RoutedHTTP), \
                    patch('relay.mediamtx.verified_binary', side_effect=forbidden('route')), \
                    patch('relay.mediamtx.MediaMTX', side_effect=forbidden('media')), \
                    patch('relay.runtime.make_engine', side_effect=forbidden('engine')), \
                    patch('relay.runtime.run', side_effect=forbidden('run')), \
                    patch('shield.app.session.TokenStore', side_effect=forbidden('storage')):
                try:
                    await execute(parser().parse_args(['run', '--host', '127.0.0.1', '--twitch-live']))
                except asyncio.CancelledError:
                    outcome = 'cancelled'
                except LiveModeError as error:
                    outcome = str(error)
                else:
                    outcome = 'unexpected approval'
            calls = list(mock.calls)
    print('CHILD_AUDIT ' + json.dumps({'outcome': outcome, 'pid': os.getpid(), 'pgid': os.getpgrp(),
        'sid': os.getsid(0), 'boundaries': boundaries,
        'calls': calls, 'handlers_restored': dict(loop._signal_handlers) == before_handlers,
        'terminal_restored': before_terminal is None or termios.tcgetattr(0) == before_terminal,
        'threads_restored': {thread.ident for thread in threading.enumerate()} == before_threads,
        'pending_tasks': [task.get_name() for task in asyncio.all_tasks() if task is not asyncio.current_task()]}), flush=True)


class LivePromptCancel(unittest.TestCase):
    def child(self, attended=True):
        master, slave = os.openpty() if attended else (None, None)
        env = dict(os.environ)
        env.pop('PYTHONPATH', None)
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--prompt-child'],
            cwd=ROOT, env=env, stdin=slave if attended else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        if slave is not None:
            os.close(slave)
        def cleanup():
            if child.poll() is None:
                child.kill()  # Popen owns this unreaped child, never an owner PID.
            child.communicate(timeout=5)
            if master is not None:
                os.close(master)
        self.addCleanup(cleanup)
        return child, master

    def prompt(self, child, master):
        output = b''
        deadline = time.monotonic() + 20
        while b'Type LIVE naie' not in output:
            remaining = deadline - time.monotonic()
            self.assertGreater(remaining, 0, 'attended LIVE prompt did not become active')
            ready, _, _ = select.select([master], [], [], remaining)
            self.assertTrue(ready, 'attended LIVE prompt did not become active')
            output += os.read(master, 4096)
        self.assertIsNone(child.poll())
        return output

    def audit(self, child, *, timeout=2):
        try:
            output, error = child.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.fail('CLI remained blocked at the attended prompt after cancellation/input')
        self.assertEqual(child.returncode, 0, error.decode())
        self.assertEqual(error, b'')
        line = next(line for line in output.decode().splitlines() if line.startswith('CHILD_AUDIT '))
        audit = json.loads(line.removeprefix('CHILD_AUDIT '))
        print(line, flush=True)
        self.assertEqual(audit['pid'], child.pid)
        self.assertEqual(audit['pgid'], child.pid)
        self.assertEqual(audit['sid'], child.pid)
        self.assertEqual(audit['boundaries'], [])
        self.assertNotIn(['GET', '/helix/streams/key'], audit['calls'])
        self.assertEqual(audit['calls'].count(['GET', '/oauth2/validate']), 2)
        self.assertTrue(audit['handlers_restored'])
        self.assertTrue(audit['terminal_restored'])
        self.assertTrue(audit['threads_restored'])
        self.assertEqual(audit['pending_tasks'], [])
        self.assertFalse(Path('/proc', str(child.pid)).exists(), 'synthetic child must be reaped')
        return audit

    def test_sigint_aborts_attended_cli_before_key_route_and_media(self):
        child, master = self.child()
        self.prompt(child, master)
        child.send_signal(signal.SIGINT)
        self.assertEqual(self.audit(child)['outcome'], 'cancelled')

    def test_sigterm_aborts_attended_cli_before_key_route_and_media(self):
        child, master = self.child()
        self.prompt(child, master)
        child.send_signal(signal.SIGTERM)
        self.assertEqual(self.audit(child)['outcome'], 'cancelled')

    def test_wrong_line_and_eof_are_redacted_and_headless_is_rejected(self):
        from shield.app.live import LiveModeError
        for response in (b'LIVE nale\n', b'\x04'):
            with self.subTest(response=response):
                child, master = self.child()
                self.prompt(child, master)
                os.write(master, response)
                self.assertEqual(self.audit(child)['outcome'], str(LiveModeError()))
        child, _ = self.child(attended=False)
        self.assertEqual(self.audit(child)['outcome'], str(LiveModeError()))


if __name__ == '__main__':
    sys.path[:0] = [str(ROOT), str(ROOT / 'tests/m2'), str(ROOT / 'tests/m3'), str(ROOT / 'tests/integration')]
    if sys.argv[1:] == ['--prompt-child']:
        asyncio.run(prompt_child())
    else:
        unittest.main()

"""Walk bootstrap boundaries. All leases are private, including subprocess leases."""
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import fcntl
import importlib.machinery
import importlib.util
from io import StringIO
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from lock_isolation import install_lock_guard

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/walk-linux'
loader = importlib.machinery.SourceFileLoader('walk_linux', str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
walk = importlib.util.module_from_spec(spec)
loader.exec_module(walk)
install_lock_guard()


@contextmanager
def installed_bootstrap(root):
    # Exercise main without provisioning an SDK or replacing its CLI handoff.
    (root / 'models/cache').mkdir(parents=True)
    (root / '.tmp/tools/mediamtx-v1.21.3').mkdir(parents=True)
    prefix = Path(sys.prefix).resolve()
    original_flags = sys.flags
    flags = type('Flags', (), {'isolated': 1, 'no_site': 0,
        '__getattr__': lambda self, name: getattr(original_flags, name)})()
    with patch.object(walk, 'ROOT', root), patch.object(sys, 'flags', flags), patch.object(sys, 'path', sys.path.copy()), \
            patch.object(walk, 'venv_paths', return_value=(prefix, Path(sys.executable), root, [])), \
            patch.object(walk, 'verify_environment'), patch.object(walk.resource, 'setrlimit'), \
            patch.object(walk.os, 'execve', side_effect=AssertionError('unexpected interpreter exec')):
        yield


class WalkSelection(unittest.TestCase):
    def test_modes_and_unknown_forwarding_refuse_without_echoing_private_values(self):
        sentinel = 'SYNTHETIC-PRIVATE-ARGUMENT'
        for argv in ([], ['--local-only', '--twitch-live'],
                     ['--local-only', '--twitch-bandwidth-test'], ['--twitch-live', '--twitch-bandwidth-test'],
                     ['--local-only', '--twitch-live', '--twitch-bandwidth-test'], ['--local-only', '--remember'],
                     ['--local-only', '--mock-origin', sentinel], ['--local'],
                     ['--local-only', '--', '--twitch-live'], ['--local-only', '--stream-key', sentinel]):
            with self.subTest(argv=argv), redirect_stderr(StringIO()) as error, redirect_stdout(StringIO()) as output:
                with self.assertRaises(SystemExit) as stopped:
                    walk.parser().parse_args(argv)
                self.assertEqual(stopped.exception.code, 2)
                self.assertNotIn(sentinel, error.getvalue() + output.getvalue())

    def test_host_source_fails_closed_and_mode_cannot_be_negated(self):
        with patch.dict(os.environ, {'SHIELD_BIND_HOST': '100.80.2.3', 'SHIELD_WALK_VENV': '/private/venv'}):
            args = walk.parser().parse_args(['--local-only'])
        self.assertEqual(args.venv, Path('/private/venv'))
        self.assertEqual(walk.private_host(args.host), '100.80.2.3')
        for bad in ('0.0.0.0', '192.168.1.2', '8.8.8.8', '::1', 'unavailable', '', '127.0.0.2'):
            with self.subTest(host=bad), self.assertRaises(walk.WalkError):
                walk.private_host(bad)
        with patch.object(walk.subprocess, 'run', side_effect=FileNotFoundError()):
            with self.assertRaises(walk.WalkError):
                walk.private_host(None)
        with patch.object(walk.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '100.80.4.5\n')):
            self.assertEqual(walk.private_host(None), '100.80.4.5')
        from shield.cli import parser, validate
        for mode in ('--local-only', '--twitch-live', '--twitch-bandwidth-test'):
            args = walk.parser().parse_args([mode, '--host', '127.0.0.1', '--seconds', '12', '--dashboard-port', '12345'])
            routed = parser().parse_args(walk.cli_arguments(args, walk.private_host(args.host)))
            validate(routed)
            self.assertEqual(routed.command, 'run')
            self.assertEqual((routed.local_only, routed.twitch_live, routed.twitch_bandwidth_test),
                             (mode == '--local-only', mode == '--twitch-live', mode == '--twitch-bandwidth-test'))
            self.assertTrue(routed.phone_setup and routed.dashboard)
            self.assertFalse(routed.remember)
            self.assertIsNone(routed.mock_origin)
            self.assertEqual((routed.seconds, routed.dashboard_port), (12, 12345))

    def test_bad_duration_or_port_is_refused_before_any_lease_or_sdk(self):
        for extra in (['--seconds', 'nan'], ['--seconds', '0'], ['--rtmp-port', '80'], ['--dashboard-port', '65536'],
                      ['--accurate-rate-hz', '0'], ['--accurate-rate-hz', 'nan'], ['--accurate-rate-hz', '31'],
                      ['--accurate-box-thresh', '-.1'], ['--accurate-box-thresh', '1.1'], ['--accurate-box-thresh', 'nan']):
            with self.subTest(extra=extra), patch.object(walk, 'exclusive_lease', side_effect=AssertionError('lease reached')):
                with redirect_stderr(StringIO()):
                    self.assertEqual(walk.main(['--local-only', '--host', '127.0.0.1', *extra]), 2)


@unittest.skipUnless(sys.platform == 'linux', 'Linux kernel flock FD proof')
class WalkLease(unittest.TestCase):
    def assert_excluded(self, path):
        with path.open('a+') as contender:
            with self.assertRaises(BlockingIOError):
                fcntl.flock(contender, fcntl.LOCK_SH | fcntl.LOCK_NB)

    def test_real_inherited_ex_is_reused_without_flock_and_survives_context(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            with (root / 'perf.lock').open('a+') as owner:
                fcntl.flock(owner, fcntl.LOCK_EX)
                for environment in ({walk.LEASE_ENV: str(owner.fileno())}, {}):
                    with self.subTest(queue_env=bool(environment)), patch.dict(os.environ, environment, clear=True), \
                            patch.object(walk.fcntl, 'flock', side_effect=AssertionError('nested flock')):
                        with walk.exclusive_lease(root) as fd:
                            self.assertEqual(fd, owner.fileno())
                            self.assert_excluded_without_patch(root / 'perf.lock')
                self.assert_excluded(root / 'perf.lock')

    def assert_excluded_without_patch(self, path):
        # A different process owns its flock implementation, outside the nested-call spy.
        result = subprocess.run([sys.executable, '-I', '-c',
            'import fcntl,sys; f=open(sys.argv[1],"a+"); fcntl.flock(f,fcntl.LOCK_SH|fcntl.LOCK_NB)', str(path)],
            capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'BlockingIOError', result.stderr)

    def test_shared_unlocked_wrong_inode_and_environment_only_leases_are_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            for kind in ('shared', 'unlocked', 'wrong-inode', 'missing-fd'):
                with self.subTest(kind=kind), (root / 'perf.lock').open('a+') as owner, (root / 'other').open('a+') as other:
                    if kind == 'shared':
                        fcntl.flock(owner, fcntl.LOCK_SH)
                    if kind == 'wrong-inode':
                        fcntl.flock(other, fcntl.LOCK_EX)
                    fd = other.fileno() if kind == 'wrong-inode' else owner.fileno()
                    with patch.dict(os.environ, {walk.LEASE_ENV: '9999999' if kind == 'missing-fd' else str(fd)}):
                        with self.assertRaises(walk.WalkError):
                            with walk.exclusive_lease(root):
                                self.fail('unverified lease accepted')

    def test_standalone_lock_crosses_exec_and_releases_after_sigterm(self):
        # The real executable's acquisition and inheritable FD logic run in a child.
        code = '''import importlib.machinery,sys,os
m=importlib.machinery.SourceFileLoader('walk',sys.argv[1]).load_module()
from pathlib import Path
with m.exclusive_lease(Path(sys.argv[2])):
 os.execv(sys.executable,[sys.executable,'-I','-u','-c','import sys; print("LEASED",flush=True); sys.stdin.read(1)'])
'''
        with tempfile.TemporaryDirectory() as name:
            env = {key: value for key, value in os.environ.items() if key != walk.LEASE_ENV}
            child = subprocess.Popen([sys.executable, '-I', '-u', '-c', code, str(SCRIPT), name],
                env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertTrue(select.select([child.stdout], [], [], 10)[0], 'lock child readiness')
                self.assertEqual(child.stdout.readline().strip(), 'LEASED')
                self.assert_excluded(Path(name) / 'perf.lock')
                child.send_signal(signal.SIGTERM)
                child.communicate(timeout=10)
                self.assertEqual(child.returncode, -signal.SIGTERM)
                with (Path(name) / 'perf.lock').open('a+') as contender:
                    fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                if child.poll() is None:
                    child.kill()
                child.communicate(timeout=10)


class WalkEnvironment(unittest.TestCase):
    def test_authenticated_ids_stop_before_host_lease_interpreter_or_cli(self):
        client, broadcaster = 'TWITCH_CLIENT_ID', 'TWITCH_BROADCASTER_ID'
        for mode in ('--twitch-live', '--twitch-bandwidth-test'):
            for environment, missing in (({}, [client, broadcaster]),
                    ({broadcaster: '123456789'}, [client]),
                    ({client: 'SYNTHETIC-CLIENT'}, [broadcaster]),
                    ({client: '', broadcaster: '123456789'}, [client]),
                    ({client: 'SYNTHETIC-CLIENT', broadcaster: ''}, [broadcaster]),
                    ({client: '', broadcaster: ''}, [client, broadcaster])):
                with self.subTest(mode=mode, missing=missing, empty=bool(environment)), \
                        tempfile.TemporaryDirectory() as name, patch.dict(os.environ, environment, clear=True), \
                        patch.object(walk, 'private_host', side_effect=walk.WalkError('SYNTHETIC-SETUP-STOP')) as host, \
                        patch.object(walk, 'exclusive_lease') as lease, patch.object(walk, 'venv_paths') as venv, \
                        patch.object(walk.os, 'execve') as execute, patch.object(walk, 'launch_cli') as launch, \
                        patch.object(walk.runpy, 'run_module') as module, \
                        redirect_stderr(StringIO()) as error, redirect_stdout(StringIO()) as output:
                    try:
                        result = walk.main([mode], lock_root=Path(name))
                    except SystemExit as stopped:
                        self.fail(f'Selected mode {mode} refused with exit {stopped.code}')
                    self.assertEqual(result, 2)
                    self.assertIn('Missing required environment: ' + ', '.join(missing), error.getvalue())
                    for key in (client, broadcaster):
                        self.assertEqual(key in error.getvalue(), key in missing)
                    for value in ('SYNTHETIC-CLIENT', '123456789', 'SYNTHETIC-SETUP-STOP'):
                        self.assertNotIn(value, error.getvalue() + output.getvalue())
                    for boundary in (host, lease, venv, execute, launch, module):
                        boundary.assert_not_called()

    def test_priority_changes_only_for_bounded_local_verification(self):
        for mode in ('--local-only', '--twitch-live', '--twitch-bandwidth-test'):
            for seconds in ([], ['--seconds', '12']):
                for inherited in (0, 15):
                    with self.subTest(mode=mode, seconds=seconds, inherited=inherited), \
                            tempfile.TemporaryDirectory() as name, \
                            patch.dict(os.environ, {'TWITCH_CLIENT_ID': 'SYNTHETIC-CLIENT',
                                'TWITCH_BROADCASTER_ID': '123456789'}, clear=True), \
                            installed_bootstrap(Path(name)), \
                            patch.object(walk.os, 'getpriority', return_value=inherited) as priority, \
                            patch.object(walk.os, 'nice') as nice, patch.object(walk, 'launch_cli') as launch:
                        try:
                            result = walk.main([mode, '--host', '127.0.0.1', *seconds], lock_root=Path(name))
                        except SystemExit as stopped:
                            self.fail(f'Selected mode {mode} refused with exit {stopped.code}')
                        self.assertEqual(result, 0)
                        launch.assert_called_once()
                        if mode == '--local-only' and seconds:
                            priority.assert_called_once_with(os.PRIO_PROCESS, 0)
                            nice.assert_called_once_with(10 if inherited == 0 else 0)
                        else:
                            priority.assert_not_called()
                            nice.assert_not_called()

    def test_declared_nested_requirements_drive_rejection_without_package_imports(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / 'requirements-check-linux.txt').write_text('-r nested.txt\nqrcode==8.2\n')
            (root / 'nested.txt').write_text('onnxruntime-gpu==1.20.2\n')
            packages = root / 'lib/python3.11/site-packages'
            packages.mkdir(parents=True)
            def distribution(package, version):
                from importlib.metadata import PathDistribution
                info = packages / (package + '-' + version + '.dist-info')
                info.mkdir(exist_ok=True)
                (info / 'METADATA').write_text(f'Name: {package}\nVersion: {version}\n')
                return PathDistribution(info)
            gpu = distribution('onnxruntime-gpu', '1.20.2')
            qr = distribution('qrcode', '8.2')
            cpu = distribution('onnxruntime', '1.20.2')
            stdlib = Path(sys.base_prefix).resolve() / 'lib'
            paths = [str(stdlib / item) for item in ('python3.11', 'python3.11/lib-dynload', 'python311.zip')] + [str(packages)]
            original_flags = sys.flags
            flags = type('Flags', (), {'isolated': 1, '__getattr__': lambda self, name: getattr(original_flags, name)})()
            with patch.object(walk, 'ROOT', root), patch.object(sys, 'prefix', str(root)), \
                    patch.object(sys, 'path', paths), patch.object(sys, 'flags', flags), \
                    patch.object(walk.site, 'ENABLE_USER_SITE', False), \
                    patch.object(walk.metadata, 'distributions', return_value=[gpu, qr]) as distributions:
                walk.verify_environment(root, packages)
                for installed in ([gpu], [gpu, distribution('qrcode', '8.1')], [gpu, qr, cpu], [gpu, qr, qr]):
                    with self.subTest(installed=[d.metadata['Name'] + d.version for d in installed]):
                        distributions.return_value = installed
                        with self.assertRaises(walk.WalkError):
                            walk.verify_environment(root, packages)
                distributions.return_value = [gpu, qr]
                with patch.object(sys, 'path', [*paths, '/unrelated/site-packages']):
                    with self.assertRaises(walk.WalkError):
                        walk.verify_environment(root, packages)

    def test_system_site_venv_and_inherited_cuda_overlays_are_refused_or_removed(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / 'pyvenv.cfg').write_text('include-system-site-packages = true\n')
            with self.assertRaises(walk.WalkError):
                walk.venv_paths(root)
            private = root / 'nvidia/cudnn/lib'
            with patch.dict(os.environ, {'PYTHONPATH': '/overlay', 'PYTHONHOME': '/global',
                    'LD_LIBRARY_PATH': '/random/cuda', 'LD_PRELOAD': '/random/preload',
                    'OMP_NUM_THREADS': '99', 'TWITCH_CLIENT_ID': 'SYNTHETIC-ID'}):
                env = walk.isolated_environment([private])
            self.assertNotIn('PYTHONPATH', env)
            self.assertNotIn('PYTHONHOME', env)
            self.assertNotIn('LD_PRELOAD', env)
            self.assertEqual(env['LD_LIBRARY_PATH'], str(private))
            self.assertEqual((env['OMP_NUM_THREADS'], env['OPENCV_FOR_THREADS_NUM']), ('2', '1'))
            self.assertEqual(env['TWITCH_CLIENT_ID'], 'SYNTHETIC-ID')

    def test_bootstrap_refuses_invalid_venv_under_lease_before_cli_and_releases(self):
        with tempfile.TemporaryDirectory() as name, patch.dict(os.environ, {}, clear=True):
            root = Path(name)
            with patch.object(walk, 'launch_cli', side_effect=AssertionError('CLI reached')), redirect_stderr(StringIO()) as error:
                self.assertEqual(walk.main(['--local-only', '--host', '127.0.0.1', '--venv', str(root / 'absent')],
                                          lock_root=root), 2)
            self.assertIn('required local file', error.getvalue())
            with (root / 'perf.lock').open('a+') as contender:
                fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)


class WalkRealCLI(unittest.TestCase):
    def test_selected_routes_use_real_launcher_and_cli_with_private_tty_cleanup(self):
        for mode in ('--local-only', '--twitch-live', '--twitch-bandwidth-test'):
            with self.subTest(mode=mode):
                self.check_route(mode)

    def test_measurement_policy_reaches_real_cli_engine_factory(self):
        self.check_route('--local-only', {'accurate_rate_hz': 15., 'accurate_box_thresh': .73})

    def check_route(self, mode, detector_options=None):
        from relay.security import Credentials
        records = {}
        terminal = StringIO()
        class Terminal:
            def __enter__(self):
                return terminal
            def __exit__(self, *args):
                pass
        terminal.isatty = lambda: True
        class Engine:
            def close(self):
                records['closed'] = True
        class Dashboard:
            def __init__(self, **kwargs):
                records['dashboard'] = kwargs
            async def start(self):
                records['started'] = True
            async def close(self):
                records['dashboard_closed'] = True
        def runtime(engine, address, phone, internal, directory, stopped, seconds, **kwargs):
            records['route'] = kwargs
            records['phone'] = phone
            records['seconds'] = seconds
            records['archive'] = directory
            engine.close()
        phone = Credentials('synthetic-phone-user', 'SYNTHETIC-PHONE-PASSWORD')
        internal = Credentials('synthetic-internal-user', 'SYNTHETIC-INTERNAL-PASSWORD')
        authenticated = mode != '--local-only'
        environment = {'TWITCH_CLIENT_ID': 'SYNTHETIC-CLIENT', 'TWITCH_BROADCASTER_ID': '123456789'} if authenticated else {}
        approval = object()
        with tempfile.TemporaryDirectory() as name, patch.dict(os.environ, environment, clear=True), \
                installed_bootstrap(Path(name)), patch.object(walk.os, 'nice'), patch('relay.mediamtx.MediaMTX'), \
                patch('relay.mediamtx.verified_binary'), patch('relay.security.Credentials.generate', side_effect=[phone, internal]), \
                patch('relay.runtime.make_engine', return_value=Engine()) as engine_factory, patch('relay.runtime.run', side_effect=runtime), \
                patch('shield.dashboard.DashboardServer', Dashboard), patch('builtins.open', return_value=Terminal()), \
                patch('shield.app.session.login', return_value=object()) as login, \
                patch('shield.app.session.TwitchControls') as controls, \
                patch('shield.app.live.authorize_live', return_value=approval) as authorize, \
                patch('shield.twitch.http.TwitchHTTP.request', side_effect=AssertionError('Twitch HTTP')), \
                redirect_stdout(StringIO()) as output, redirect_stderr(StringIO()) as error:
            controls.return_value.prepare = AsyncMock()
            controls.return_value.close = AsyncMock()
            controls.return_value.failure = False
            extra = [arg for key, value in (detector_options or {}).items()
                     for arg in ('--' + key.replace('_', '-'), str(value))]
            with patch.object(sys, 'argv', ['walk-linux']), self.assertRaises(SystemExit) as stopped:
                walk.main([mode, '--host', '127.0.0.1', '--seconds', '12', *extra], lock_root=Path(name))
            self.assertEqual(stopped.exception.code, 0)
            self.assertNotIn('TWITCH_STREAM_KEY', os.environ)
            self.assertEqual({key: value for key, value in engine_factory.call_args.kwargs.items()
                              if key != 'appearance'}, detector_options or {})
        self.assertEqual(records['route']['publish_twitch'], authenticated)
        self.assertEqual(records['route']['twitch_live'], mode == '--twitch-live')
        self.assertIs(records['route']['live_approval'], approval if mode == '--twitch-live' else None)
        if authenticated:
            login.assert_awaited_once()
            self.assertEqual(login.call_args.args[1:3], ('SYNTHETIC-CLIENT', '123456789'))
            self.assertFalse(login.call_args.kwargs['remember'])
            controls.return_value.prepare.assert_awaited_once()
            controls.return_value.close.assert_awaited_once()
        else:
            login.assert_not_called()
            controls.assert_not_called()
        if mode == '--twitch-live':
            authorize.assert_awaited_once()
        else:
            authorize.assert_not_called()
        self.assertIsNone(records['route']['local_sink'])
        self.assertEqual(records['seconds'], 12)
        self.assertIsNone(records['archive'])
        self.assertTrue(records['closed'] and records['started'] and records['dashboard_closed'])
        self.assertEqual(records['dashboard']['host'], '127.0.0.1')
        self.assertIn(phone.password, terminal.getvalue())
        self.assertNotIn(phone.password, output.getvalue() + error.getvalue())
        self.assertNotIn(internal.password, output.getvalue() + error.getvalue())


if __name__ == '__main__':
    unittest.main()

"""Walk bootstrap boundaries. All leases are private, including subprocess leases."""
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import fcntl
import hashlib
import importlib.machinery
import importlib.util
from io import StringIO
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from lock_isolation import install_lock_guard

ROOT = Path(__file__).resolve().parents[1]
TAILNET_HOST = '.'.join(map(str, (100, 80, 2, 3)))
DISCOVERED_TAILNET_HOST = '.'.join(map(str, (100, 80, 4, 5)))
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
    def test_demo_modes_and_paths_are_rejected_before_discovery_lease_or_login(self):
        from shield.cli import execute, parser
        import asyncio
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            manifest = root / 'source.json'
            manifest.write_text('{}')
            options = ['--demo-source', str(manifest), '--demo-receipt', str(root / 'sender.jsonl'),
                       '--archive', str(root / 'archive'), '--seconds', '230']
            for extra in (['--twitch-live', '--accurate-rate-hz', '15'], ['--twitch-bandwidth-test'], ['--local-only', '--host', TAILNET_HOST]):
                with self.subTest(extra=extra), patch.dict(os.environ, {}, clear=True), \
                        patch.object(walk, 'private_host', side_effect=AssertionError('discovery')) as discovery, \
                        patch.object(walk, 'exclusive_lease', side_effect=AssertionError('lease')) as lease, \
                        patch('shield.app.session.login', side_effect=AssertionError('login')) as login, \
                        redirect_stderr(StringIO()):
                    argv = ['--host', '127.0.0.1', *options, *extra]
                    self.assertEqual(walk.main(argv), 2)
                    with self.assertRaises(ValueError):
                        asyncio.run(execute(parser().parse_args(['run', *argv])))
                    discovery.assert_not_called()
                    lease.assert_not_called()
                    login.assert_not_called()
            for broken in ('receipt-missing', 'archive-exists', 'source-missing'):
                with self.subTest(broken=broken), patch.object(walk, 'exclusive_lease') as lease, \
                        redirect_stderr(StringIO()):
                    args = walk.parser().parse_args(['--local-only', '--host', '127.0.0.1', *options])
                    if broken == 'receipt-missing':
                        args.demo_receipt = None
                    elif broken == 'archive-exists':
                        args.archive = root
                    else:
                        args.demo_source = root / 'absent.json'
                    with self.assertRaises(walk.WalkError):
                        walk.cli_arguments(args, args.host)
                    lease.assert_not_called()

    def test_attended_demo_preserves_live_routing_and_requires_ids_before_login(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            manifest = root / 'source.json'
            manifest.write_text('{}')
            argv = ['--twitch-live', '--host', TAILNET_HOST, '--seconds', '600',
                    '--demo-source', str(manifest), '--demo-receipt', str(root / 'sender.jsonl'),
                    '--archive', str(root / 'archive')]
            args = walk.parser().parse_args(argv)
            command = walk.cli_arguments(args, args.host)
            self.assertIn('--twitch-live', command)
            self.assertNotIn('--phone-setup', command)
            self.assertIn('--demo-source', command)
            with patch.dict(os.environ, {}, clear=True), \
                    patch.object(walk, 'private_host', side_effect=AssertionError('discovery')) as discovery, \
                    patch('shield.app.session.login', side_effect=AssertionError('login')) as login, \
                    redirect_stderr(StringIO()) as error:
                self.assertEqual(walk.main(argv), 2)
            self.assertIn('TWITCH_CLIENT_ID', error.getvalue())
            self.assertIn('TWITCH_BROADCASTER_ID', error.getvalue())
            discovery.assert_not_called()
            login.assert_not_called()

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
        with patch.dict(os.environ, {'SHIELD_BIND_HOST': TAILNET_HOST, 'SHIELD_WALK_VENV': '/private/venv'}):
            args = walk.parser().parse_args(['--local-only'])
        self.assertEqual(args.venv, Path('/private/venv'))
        self.assertEqual(walk.private_host(args.host), TAILNET_HOST)
        for bad in ('0.0.0.0', '192.168.1.2', '8.8.8.8', '::1', 'unavailable', '', '127.0.0.2'):
            with self.subTest(host=bad), self.assertRaises(walk.WalkError):
                walk.private_host(bad)
        with patch.object(walk.subprocess, 'run', side_effect=FileNotFoundError()):
            with self.assertRaises(walk.WalkError):
                walk.private_host(None)
        with patch.object(walk.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, DISCOVERED_TAILNET_HOST + '\n')):
            self.assertEqual(walk.private_host(None), DISCOVERED_TAILNET_HOST)
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
                      ['--cpu', '--delay-seconds', 'nan'], ['--delay-seconds', 'inf'], ['--delay-seconds', '-.1'],
                      ['--accurate-rate-hz', '0'], ['--accurate-rate-hz', 'nan'], ['--accurate-rate-hz', '31'],
                      ['--accurate-box-thresh', '-.1'], ['--accurate-box-thresh', '1.1'], ['--accurate-box-thresh', 'nan']):
            with self.subTest(extra=extra), patch.object(walk, 'exclusive_lease', side_effect=AssertionError('lease reached')):
                with redirect_stderr(StringIO()):
                    self.assertEqual(walk.main(['--local-only', '--host', '127.0.0.1', *extra]), 2)
        for mode in ('--local-only', '--twitch-live', '--twitch-bandwidth-test'):
            for cpu in ([], ['--cpu']):
                for value in ('nan', 'inf', '-inf', '-.1', '0', '.25', '10.000001'):
                    argv = [mode, *cpu, '--host', '127.0.0.1', f'--delay-seconds={value}']
                    with self.subTest(mode=mode, cpu=cpu, delay=value):
                        args = walk.parser().parse_args(argv)
                        with self.assertRaisesRegex(walk.WalkError, '--delay-seconds'):
                            walk.cli_arguments(args, args.host)
                        with patch.dict(os.environ, {}, clear=True), \
                                patch.object(walk.os.environ, 'get', wraps=walk.os.environ.get) as environment, \
                                patch.object(walk, 'private_host', side_effect=AssertionError('discovery reached')) as discovery, \
                                patch.object(walk, 'exclusive_lease', side_effect=AssertionError('lease reached')) as lease, \
                                patch.object(walk, 'launch_cli', side_effect=AssertionError('SDK reached')) as launch, \
                                redirect_stderr(StringIO()) as error:
                            self.assertEqual(walk.main(argv), 2)
                            self.assertIn('--delay-seconds', error.getvalue())
                            self.assertFalse(any(call.args[0] in ('TWITCH_CLIENT_ID', 'TWITCH_BROADCASTER_ID')
                                                 for call in environment.call_args_list))
                            discovery.assert_not_called()
                            lease.assert_not_called()
                            launch.assert_not_called()


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
                            from tools.demo_renderer.lease import inherited_exclusive
                            with patch('tools.demo_renderer.lease.runpy.run_path', return_value={
                                    'verified_fd': walk.verified_fd, 'LOCK_ROOT': root}):
                                self.assertEqual(inherited_exclusive(), fd)
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
    def test_cpu_venv_needs_no_nvidia_libraries_and_hides_cuda(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / 'pyvenv.cfg').write_text('include-system-site-packages = false\n')
            (root / 'bin').mkdir()
            python = root / 'bin/python'
            python.write_text('synthetic interpreter, never executed')
            python.chmod(0o700)
            packages = root / 'lib/python3.11/site-packages'
            packages.mkdir(parents=True)
            self.assertEqual(walk.venv_paths(root, cpu=True), (root, python, packages, []))
            with self.assertRaisesRegex(walk.WalkError, 'NVIDIA'):
                walk.venv_paths(root)
            with patch.dict(os.environ, {'CUDA_VISIBLE_DEVICES': '0', 'LD_LIBRARY_PATH': '/external/cuda',
                                        'LD_PRELOAD': '/external/preload', 'CUDA_CACHE_PATH': '/external/cache'}):
                env = walk.isolated_environment([], cpu=True)
            self.assertEqual(env['CUDA_VISIBLE_DEVICES'], '-1')
            self.assertEqual(env['LD_LIBRARY_PATH'], '')
            self.assertNotIn('LD_PRELOAD', env)
            self.assertNotIn('CUDA_CACHE_PATH', env)
            self.assertEqual((env['OMP_NUM_THREADS'], env['OPENCV_FOR_THREADS_NUM']), ('2', '1'))

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
    def test_cancelled_demo_model_initialization_is_reaped_without_starting_sender(self):
        import asyncio
        import threading
        from shield.cli import execute, parser
        async def scenario():
            loop = asyncio.get_running_loop()
            building = asyncio.Event()
            release = threading.Event()
            events = []
            class Engine:
                def close(self):
                    events.append('engine-close')
            class Media:
                def __init__(self, *args, **kwargs):
                    pass
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    events.append('media-close')
            def build(*args, **kwargs):
                loop.call_soon_threadsafe(building.set)
                if not release.wait(5):
                    raise RuntimeError('Synthetic model release timeout')
                events.append('engine-built')
                return Engine()
            temporary = tempfile.TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            root = Path(temporary.name)
            video = root / 'source.mp4'
            video.write_bytes(b'synthetic-source-not-native-media')
            manifest = root / 'source.json'
            manifest.write_text(json.dumps({'schema': 'irl-shield-w8-source-v1', 'video': 'source.mp4',
                'video_sha256': hashlib.sha256(video.read_bytes()).hexdigest(), 'fps': 30, 'seconds': 210,
                'frames': [{'source_index': i, 'pts': f'{i}/30'} for i in range(6300)]}))
            args = parser().parse_args(['run', '--local-only', '--host', '127.0.0.1', '--seconds', '230',
                '--demo-source', str(manifest), '--demo-receipt', str(root / 'sender.jsonl'),
                '--archive', str(root / 'archive')])
            with patch('relay.mediamtx.MediaMTX', Media), patch('relay.mediamtx.verified_binary'), \
                    patch('relay.runtime.make_engine', side_effect=build), \
                    patch('relay.runtime.run', side_effect=AssertionError('runtime before model ready')) as runtime, \
                    patch('tools.demo_renderer.sender.Sender', side_effect=AssertionError('sender before readiness')) as factory, \
                    patch('shield.app.session.login', side_effect=AssertionError('login')) as login:
                task = asyncio.create_task(execute(args))
                try:
                    await asyncio.wait_for(building.wait(), 5)
                    task.cancel()
                    release.set()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
                finally:
                    release.set()
                    if not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                factory.assert_not_called()
                runtime.assert_not_called()
                login.assert_not_called()
            self.assertEqual(events, ['engine-built', 'engine-close', 'media-close'])
        asyncio.run(scenario())

    def test_local_demo_reaches_actual_runtime_and_reaps_failed_sender_without_tty(self):
        for cpu in (False, True):
            with self.subTest(cpu=cpu):
                self.check_local_demo(cpu)

    def check_local_demo(self, cpu):
        from relay.security import Credentials
        events, runtime_phone = [], []
        class Engine:
            delay = 1
            stats = {}
            def hold(self, *args, **kwargs):
                pass
            def submit(self, *args, **kwargs):
                pass
            def poll(self, *args, **kwargs):
                return []
            def close(self):
                events.append('engine-close')
        class Output:
            error_code = error_details = None
            count = max_write_seconds = recovery_count = 0
            recovery_events = ()
            def __init__(self, *args):
                self_test.assertEqual(args[-1], 'libx264' if cpu else 'h264_nvenc')
                events.append('encoder-ready')
            def close(self):
                events.append('output-close')
        class Source:
            error_code = last_failure = None
            high_water = active_generation = 0
            timestamp_issues = {}
            def __init__(self, *args):
                events.append('reader-ready')
            def drain(self):
                raise AssertionError('Expected sender failure before input drain')
            def close(self):
                events.append('input-close')
        class Sender:
            def __init__(self, manifest, address, phone, receipt, *, local_only):
                self.local_only = local_only
                runtime_phone.append((address, phone, os.environ[walk.LEASE_ENV], local_only))
                events.append('factory')
            def __enter__(self):
                events.append('sender-enter')
                return self
            def check(self):
                events.append('sender-check')
                raise RuntimeError('SYNTHETIC-WORKER-FAILURE')
            def __exit__(self, *args):
                events.append('sender-joined')
        phone = Credentials('synthetic-phone', 'SYNTHETIC-PHONE-PASSWORD')
        internal = Credentials('synthetic-internal', 'SYNTHETIC-INTERNAL-PASSWORD')
        original_open = open
        self_test = self
        tty = Mock(side_effect=AssertionError('TTY opened'))
        def open_without_tty(path, *args, **kwargs):
            if isinstance(path, (str, bytes, os.PathLike)) and os.fsdecode(path) == '/dev/tty':
                return tty(path, *args, **kwargs)
            return original_open(path, *args, **kwargs)
        with tempfile.TemporaryDirectory() as name, patch.dict(os.environ, {}, clear=True):
            root = Path(name)
            video = root / 'source.mp4'
            video.write_bytes(b'synthetic-source-not-native-media')
            manifest = root / 'source.json'
            manifest.write_text(json.dumps({'schema': 'irl-shield-w8-source-v1', 'video': 'source.mp4',
                'video_sha256': hashlib.sha256(video.read_bytes()).hexdigest(), 'fps': 30, 'seconds': 210,
                'frames': [{'source_index': i, 'pts': f'{i}/30'} for i in range(6300)]}))
            with installed_bootstrap(root), patch.object(walk.os, 'nice'), \
                    patch('relay.mediamtx.MediaMTX') as media, patch('relay.mediamtx.verified_binary'), \
                    patch('relay.security.Credentials.generate', side_effect=[phone, internal]), \
                    patch('relay.runtime.make_engine', return_value=Engine()) as factory, \
                    patch('relay.runtime.Egress', Output), patch('relay.runtime.NetworkInput', Source), \
                    patch('tools.demo_renderer.sender.Sender', Sender), \
                    patch('builtins.open', side_effect=open_without_tty), \
                    patch('shield.app.session.login', side_effect=AssertionError('login')) as login, \
                    redirect_stdout(StringIO()) as output, redirect_stderr(StringIO()) as error, \
                    self.assertRaises(SystemExit) as ended:
                walk.main(['--local-only', *(['--cpu'] if cpu else []), '--host', '127.0.0.1', '--seconds', '230',
                    '--demo-source', str(manifest), '--demo-receipt', str(root / 'sender.jsonl'),
                    '--archive', str(root / 'archive')], lock_root=root)
            self.assertEqual(ended.exception.code, 1)
            self.assertEqual({key: value for key, value in factory.call_args.kwargs.items() if key != 'appearance'},
                             {'provider': 'cpu', 'delay_seconds': 2.5} if cpu else {})
            self.assertEqual(media.call_args.kwargs['archive'], root / 'archive')
            tty.assert_not_called()
            login.assert_not_called()
            self.assertIs(runtime_phone[0][1], phone)
            self.assertEqual(runtime_phone[0][0].host, '127.0.0.1')
            self.assertGreaterEqual(int(runtime_phone[0][2]), 3)
            self.assertTrue(runtime_phone[0][3])
            self.assertLess(events.index('encoder-ready'), events.index('factory'))
            self.assertLess(events.index('reader-ready'), events.index('factory'))
            self.assertIn('sender-check', events)
            for closed in ('input-close', 'output-close', 'engine-close'):
                self.assertLess(events.index('sender-joined'), events.index(closed))
            saved = (root / 'archive/runtime.json').read_text()
            self.assertEqual(json.loads(saved)['status'], 'failed')
            for secret in (phone.password, internal.password, 'SYNTHETIC-WORKER-FAILURE'):
                self.assertNotIn(secret, output.getvalue() + error.getvalue() + saved)

    def test_selected_routes_use_real_launcher_and_cli_with_private_tty_cleanup(self):
        for mode in ('--local-only', '--twitch-live', '--twitch-bandwidth-test'):
            with self.subTest(mode=mode):
                self.check_route(mode)

    def test_measurement_policy_reaches_real_cli_engine_factory(self):
        self.check_route('--local-only', {'accurate_rate_hz': 15., 'accurate_box_thresh': .73})

    def test_cpu_and_explicit_delay_reach_real_cli_without_changing_auth_routes(self):
        for mode in ('--local-only', '--twitch-live', '--twitch-bandwidth-test'):
            with self.subTest(mode=mode):
                self.check_route(mode, cpu=True)
        for mode in ('--local-only', '--twitch-live', '--twitch-bandwidth-test'):
            for cpu in (False, True):
                for delay in (.5, 2.5, 10):
                    with self.subTest(mode=mode, cpu=cpu, delay=delay):
                        self.check_route(mode, cpu=cpu, delay_seconds=delay)
        self.check_route('--local-only', cpu=True, delay_seconds=3.25)
        self.check_route('--local-only', delay_seconds=1.75)

    def check_route(self, mode, detector_options=None, *, cpu=False, delay_seconds=None):
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
            expected_options = dict(detector_options or {})
            if cpu:
                extra.append('--cpu')
                expected_options.update(provider='cpu', delay_seconds=2.5)
            if delay_seconds is not None:
                extra += ['--delay-seconds', str(delay_seconds)]
                expected_options['delay_seconds'] = delay_seconds
            with patch.object(sys, 'argv', ['walk-linux']), self.assertRaises(SystemExit) as stopped:
                walk.main([mode, '--host', '127.0.0.1', '--seconds', '12', *extra], lock_root=Path(name))
            self.assertEqual(stopped.exception.code, 0)
            self.assertNotIn('TWITCH_STREAM_KEY', os.environ)
            self.assertEqual({key: value for key, value in engine_factory.call_args.kwargs.items()
                              if key != 'appearance'}, expected_options)
            if cpu:
                self.assertEqual(os.environ['CUDA_VISIBLE_DEVICES'], '-1')
                self.assertEqual(records['route']['encoder'], 'libx264')
            else:
                self.assertNotIn('encoder', records['route'])
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

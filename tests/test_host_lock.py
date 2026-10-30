"""Real leases use private files; the gate refuses accidental global access."""
import fcntl
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from bench import quality_bundle
from lock_isolation import MESSAGE

ROOT = Path(__file__).resolve().parents[1]


class HostLock(unittest.TestCase):
    def test_linux_shared_is_exclusive_and_mac_shared_is_unchanged(self):
        original = (ROOT / 'scripts/host-lock').read_text()
        for platform, exclusive in (('linux', True), ('darwin', False)):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as name:
                directory = Path(name)
                # Replace only external filesystem/OS boundaries, not lock logic.
                self.assertEqual(original.count("'/tmp/agents/irl-shield'"), 1)
                script = original.replace("'/tmp/agents/irl-shield'", repr(str(directory)))
                script = script.replace("$^O eq 'linux'", repr(platform) + " eq 'linux'")
                path = directory / 'host-lock'
                path.write_text(script)
                process = subprocess.Popen(['perl', str(path), 'shared', sys.executable, '-u', '-c',
                    'import sys; print("LEASED",flush=True); sys.stdin.read(1)'],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    # The marker is written only AFTER the actual lease is held.
                    import select
                    self.assertTrue(select.select([process.stdout], [], [], 30)[0], 'Lease child must become ready')
                    self.assertEqual(process.stdout.readline().strip(), 'LEASED')
                    with (directory / 'perf.lock').open('a+') as contender:
                        if exclusive:
                            with self.assertRaises(BlockingIOError):
                                fcntl.flock(contender, fcntl.LOCK_SH | fcntl.LOCK_NB)
                        else:
                            fcntl.flock(contender, fcntl.LOCK_SH | fcntl.LOCK_NB)
                            fcntl.flock(contender, fcntl.LOCK_UN)
                    process.stdin.write('x'); process.stdin.flush()
                    _, error = process.communicate(timeout=30)
                    self.assertEqual(process.returncode, 0)
                    self.assertEqual(error, 'host-lock: Linux shared request upgraded to exclusive\n' if exclusive else '')
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.communicate(timeout=30)

    def test_clip_lease_excludes_a_shared_contender_on_its_temp_lock_root(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            with quality_bundle.clip_lease(root, 'linux', lock_root=root / 'locks'):
                with (root / 'locks/perf.lock').open('a+') as contender:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(contender, fcntl.LOCK_SH | fcntl.LOCK_NB)
            with (root / 'locks/perf.lock').open('a+') as contender:
                fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_actual_gate_rejects_a_test_resolving_the_global_lock(self):
        code = '''import importlib.util, pathlib, sys, unittest
from unittest.mock import patch
root=pathlib.Path(sys.argv[1])
spec=importlib.util.spec_from_file_location('actual_gate', root/'tests/integration/gate.py')
gate=importlib.util.module_from_spec(spec); spec.loader.exec_module(gate)
from lock_isolation import GLOBAL_PERF_LOCK
class AccidentalGlobalLease(unittest.TestCase):
 def runTest(self): pathlib.Path(GLOBAL_PERF_LOCK).resolve()
def discover(*args, **kwargs): return unittest.TestSuite([AccidentalGlobalLease()])
with patch.object(unittest.TestLoader, 'discover', side_effect=discover):
 raise SystemExit(gate.main())
'''
        with tempfile.TemporaryDirectory() as name:
            env = dict(__import__('os').environ)
            env['SHIELD_GATE_RECEIPT'] = str(Path(name) / 'receipt.json')
            result = subprocess.run([sys.executable, '-c', code, str(ROOT)], cwd=ROOT, env=env,
                                    text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn(MESSAGE, result.stderr)

"""Approved loopback functional gate; native CLI is NOT RUN BY DESIGN."""
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests'), str(ROOT / 'tests/m3'), str(ROOT / 'tests/integration')]
from network import local_network
from lock_isolation import install_lock_guard


def main():
    install_lock_guard()
    suite = unittest.TestSuite()
    selection = {}
    selected_ids = []
    def identities(tests):
        for test in tests:
            if isinstance(test, unittest.TestSuite):
                yield from identities(test)
            else:
                yield test.id()
    for folder in ('tests', 'tests/m2', 'tests/m3', 'tests/integration'):
        loaded = unittest.TestLoader().discover(folder)
        if not loaded.countTestCases():
            raise RuntimeError('Empty functional gate selection: ' + folder)
        selection[folder] = loaded.countTestCases()
        selected_ids.extend(identities(loaded))
        suite.addTests(loaded)
    compiled = []
    for folder in ('bench', 'fixtures', 'models', 'shield', 'relay', 'tests', 'scripts'):
        for directory, children, files in os.walk(folder):
            if 'pyvenv.cfg' in files:
                children[:] = []
                continue
            # Do not parse another interpreter's installed packages as source.
            children[:] = sorted(name for name in children if not name.startswith('.venv'))
            for name in sorted(files):
                if name.endswith('.py'):
                    path = Path(directory) / name
                    compile(path.read_text(), str(path), 'exec')
                    compiled.append(str(path))
    print(json.dumps({'selected': selection, 'compiled_files': len(compiled),
        'not_run_by_design': ['native Twitch CLI when binary unprovisioned: explicit SkipTest, local-only boundary',
                              'external Twitch login/publish',
                              'Apple Vision Swift build is handled by scripts/check on macOS',
                              'Q/held-out grading'],
        'authorization': 'Conductor 2026-10-30: real pyTwitchAPI + all-loopback aiohttp gate'}, indent=2), flush=True)
    with local_network():
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    receipt = Path(os.environ.get('SHIELD_GATE_RECEIPT', 'out/check-python.json'))
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({'scope': 'Python functional and compile portion of scripts/check',
        'interpreter': sys.executable, 'python': sys.version.split()[0],
        'selected': selection, 'selected_ids': selected_ids, 'compiled': compiled,
        'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
        'skipped': [{'test': test.id(), 'reason': reason} for test, reason in result.skipped],
        'success': result.wasSuccessful()}, indent=2) + '\n')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())

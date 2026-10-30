"""Run all portable repository functional tests in one process, plus M3 guards."""
import ast
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests/m3'))

from network import local_network


def main():
    suite = unittest.TestSuite()
    for folder in ('tests', 'tests/m2', 'tests/m3'):
        loaded = unittest.TestLoader().discover(folder)
        if loaded.countTestCases() == 0:
            raise RuntimeError('functional gate discovered no tests in ' + folder)
        print(folder, loaded.countTestCases(), 'test methods', flush=True)
        suite.addTests(loaded)
    for folder in ('bench', 'fixtures', 'models', 'shield', 'relay', 'tests/m3'):
        for path in Path(folder).rglob('*.py'):
            if '__pycache__' not in path.parts:
                ast.parse(path.read_text(), filename=str(path))
    with local_network():
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())

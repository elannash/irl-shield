"""Exercise the real gate compiler against synthetic source and ignored venvs."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class GateCompiler(unittest.TestCase):
    def fixture(self, temporary):
        root = Path(temporary)
        for folder in ('tests', 'tests/m2', 'tests/m3', 'tests/integration'):
            directory = root / folder
            directory.mkdir(parents=True, exist_ok=True)
            name = folder.replace('/', '_')
            # Minimal discovery fixtures let the actual CLI reach compilation.
            (directory / ('test_' + name + '.py')).write_text(
                'import unittest\nclass DiscoveryFixture(unittest.TestCase):\n'
                '    def test_source_is_importable(self):\n'
                '        self.assertTrue(__file__.endswith(".py"))\n')
        shutil.copy2(ROOT / 'tests/integration/gate.py', root / 'tests/integration/gate.py')
        shutil.copy2(ROOT / 'tests/m3/network.py', root / 'tests/m3/network.py')
        (root / 'models').mkdir()
        (root / 'models/keep.py').write_text('value = "project source must still compile"\n')
        return root

    def invoke(self, root):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
                   SHIELD_GATE_RECEIPT=str(root / 'out/check-python.json'))
        env.pop('PYTHONPATH', None)
        return subprocess.run([sys.executable, 'tests/integration/gate.py'], cwd=root,
                              env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, timeout=20)

    def test_ignored_virtualenv_poison_is_pruned_and_project_source_compiles(self):
        scratch = Path(tempfile.gettempdir()) / 'agents/irl-shield/integration-gate'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temporary:
            root = self.fixture(temporary)
            for directory in ('models/.venv', 'shield/generated/.venv311', 'fixtures/custom-python'):
                venv = root / directory
                module = venv / 'lib/python3.14/site-packages/poison.py'
                module.parent.mkdir(parents=True)
                module.write_text('type _HookFunc = int\n')
                if directory == 'fixtures/custom-python':
                    (venv / 'pyvenv.cfg').write_text('version = 3.14.0\n')
            result = self.invoke(root)
            self.assertEqual(result.returncode, 0, result.stdout)
            receipt = json.loads((root / 'out/check-python.json').read_text())
            self.assertIn('models/keep.py', receipt['compiled'])
            self.assertFalse(any('poison.py' in path for path in receipt['compiled']))
            self.assertTrue(receipt['success'])

    def test_invalid_project_source_is_still_a_compile_failure(self):
        scratch = Path(tempfile.gettempdir()) / 'agents/irl-shield/integration-gate'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temporary:
            root = self.fixture(temporary)
            (root / 'models/keep.py').write_text('def broken(:\n')
            result = self.invoke(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('SyntaxError', result.stdout)
            self.assertIn('models/keep.py', result.stdout)

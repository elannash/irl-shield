"""The stream's sole video writer must consume the shared engine's poll result."""
import ast
from pathlib import Path
import unittest


class SingleWriter(unittest.TestCase):
    def test_all_session_output_is_inside_engine_poll_and_uses_its_result(self):
        tree = ast.parse(Path('relay/live.py').read_text())
        session = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'RelaySession')
        writers = [n for n in ast.walk(session) if isinstance(n, ast.Call)
                   and ast.unparse(n.func) == 'self.sink']
        self.assertEqual(len(writers), 1, 'A decoded-frame or secondary sink route bypasses the engine')
        tick = next(n for n in session.body if isinstance(n, ast.FunctionDef) and n.name == 'tick')
        loop = next(n for n in tick.body if isinstance(n, ast.For))
        self.assertEqual(ast.unparse(loop.iter.func), 'self.engine.poll')
        self.assertIn(writers[0], list(ast.walk(loop)))
        self.assertEqual(ast.unparse(writers[0].args[0]), ast.unparse(loop.target))
        self.assertFalse(any(isinstance(n, ast.Assign) and any(
            ast.unparse(target) == ast.unparse(loop.target) for target in n.targets)
            for n in ast.walk(loop)), 'A source frame replaces the engine result before encoding')


if __name__ == '__main__':
    unittest.main()

"""The selection seam catches accidental v1 seeds/cache reuse before any decode.

Final real-media verification is the prepare/freeze CLI, not a mocked encoder.
No harness or policy behavior is owned here.
"""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare_v2', ROOT / 'fixtures/prepare_heldout_v2.py')
prep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prep)


class SelectionContract(unittest.TestCase):
    def test_copied_v1_identity_or_rebound_recipe_is_rejected_before_decode(self):
        selection = json.loads((ROOT / 'fixtures/fresh-heldout-v2/selection.json').read_text())
        self.assertEqual(len(prep.validate_selection(selection)), 3)
        for key, value in [('seed', 863287663),
                           ('source_path', 'fixtures/cache/fresh-heldout/zurich-spiegelgasse.ogv'),
                           ('excerpt_start', 3.0)]:
            with self.subTest(key=key):
                changed = copy.deepcopy(selection)
                changed['clips'][0][key] = value
                with self.assertRaises(ValueError):
                    prep.validate_selection(changed)
        for fault in ('missing-third', 'duplicate-title'):
            with self.subTest(fault=fault):
                changed = copy.deepcopy(selection)
                if fault == 'missing-third':
                    changed['clips'].pop()
                else:
                    changed['clips'][1]['title'] = changed['clips'][0]['title']
                with self.assertRaises(ValueError):
                    prep.validate_selection(changed)


if __name__ == '__main__':
    unittest.main()

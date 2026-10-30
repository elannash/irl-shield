"""The serial reference constructor reports one-judge truth as insufficient."""
from copy import deepcopy
import unittest

from bench.run import build_gate


class LegacyJudgeGate(unittest.TestCase):
    def test_mixed_policy_fails_independence_with_every_other_substantive_check_true(self):
        sample = {'candidate': 'ppocr-v6-small', 'options': {},
                  'clips': [{'synthetic_variant': True,
                             'synthetic_input_control': {'total': 1, 'unreadable': 0}}],
                  'natural': {'hidden': 1, 'total': 1, 'hidden_fraction': 1.},
                  'synthetic': {'hidden': 1, 'total': 1, 'hidden_fraction': 1.},
                  'masked_area_fraction': {'p50': .1}, 'real_video_pass': True,
                  'sustained': {'results': {'720-saturated': {'fps': 30.},
                                          '720-paced': {'realtime_added_latency_seconds': {'p95': .5}}}}}
        for fast, independent in [('ppocr-v6-tiny', True), ('vision-rectangles', False)]:
            with self.subTest(fast=fast):
                card = deepcopy(sample)
                card['options']['fast_candidate'] = fast
                build_gate(card)
                self.assertIs(card['gate_1']['independent_judges'], independent,
                              'Legacy constructor must report a single truth judge as insufficient')
                for key, value in card['gate_1'].items():
                    if key not in ('independent_judges', 'eligible', 'pass'):
                        self.assertIs(value, True, key)
                self.assertEqual(card['judge_independence']['truth_judges'],
                                 ['tesseract', 'vision-accurate'] if independent else ['tesseract'])
                self.assertFalse(card['gate_1']['eligible'])
                self.assertFalse(card['gate_1']['pass'])

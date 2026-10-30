import unittest

import numpy as np

from bench.skins.judging import attack_views, judge_output
from shield.skins import MaskRegion, SkinPainter


class SkinJudging(unittest.TestCase):
    def test_all_output_families_and_attacks_count_while_truth_stays_independent(self):
        source = np.full((24, 48, 3), 255, np.uint8)
        region = MaskRegion(0, 0, np.full((24, 48), 255, np.uint8), 12)
        painted = SkinPainter().paint(source, [region])
        class Judges:
            names = ['tesseract-5-psm11', 'vision-accurate', 'ppocr-independent']
            def read(self, frame):
                return [{'text': '1842', 'confidence': .9, 'box': [0, 0, 12, 12], 'judge': name}
                        for name in ('tesseract', 'vision-accurate', 'ppocr-independent')]
        result = judge_output(Judges(), source, painted, [region], candidate='vision-accurate', options={})
        self.assertEqual({r['judge'] for r in result['primary_independent_truth']}, {'tesseract', 'ppocr-independent'})
        self.assertEqual(len(result['output_judges']), 6)
        self.assertEqual(len(result['credible_output_leaks']), 18)
        self.assertFalse(result['passed'])
        self.assertIsNone(result['hidden_fraction'])
        views = attack_views(source)
        self.assertEqual(views[-1][1].shape, (48, 96, 3))
        with self.assertRaises(ValueError):
            judge_output(Judges(), source, painted, [region], candidate='vision-accurate',
                         options={'fast_candidate': 'ppocr-v6-tiny'})
        with self.assertRaises(ValueError):
            judge_output(Judges(), source, painted, [region], candidate='vision-accurate',
                         options={'detector_families': []})
        missing = Judges()
        missing.names = ['tesseract-5-psm11', 'vision-accurate']
        with self.assertRaises(ValueError):
            judge_output(missing, source, painted, [region], candidate='vision-accurate', options={})

    def test_unmasked_readings_do_not_hide_a_mask_reading_without_geometry(self):
        source = np.full((20, 40, 3), 255, np.uint8)
        mask = np.zeros((20, 40), np.uint8)
        mask[:, :10] = 255
        region = MaskRegion(0, 0, mask, 10)
        class Judges:
            names = ['tesseract-5-psm11', 'vision-accurate', 'ppocr-independent']
            def read(self, frame):
                return [{'text': 'OUTSIDE', 'confidence': .9, 'box': [20, 0, 40, 20], 'judge': 'tesseract'},
                        {'text': 'credible', 'confidence': .5, 'judge': 'vision-accurate'},
                        {'text': 'noise', 'confidence': .49, 'judge': 'ppocr-independent'}]
        result = judge_output(Judges(), source, SkinPainter().paint(source, [region]), [region],
                              candidate='vision-accurate', options={})
        self.assertTrue(any(r['text'] == 'credible' for r in result['credible_output_leaks']))
        self.assertFalse(any(r['text'] == 'noise' for r in result['credible_output_leaks']))


if __name__ == '__main__':
    unittest.main()

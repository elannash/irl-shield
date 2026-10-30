import unittest
from types import SimpleNamespace

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


    def test_missing_correlated_output_engine_fails_before_any_ocr(self):
        source = np.full((24, 48, 3), 255, np.uint8)
        region = MaskRegion(0, 0, np.full((24, 48), 255, np.uint8), 12)

        class MissingVision:
            names = ['tesseract-5-psm11', 'ppocr-independent']

            def __init__(self):
                self.calls = 0

            def read(self, pixels):
                self.calls += 1
                if self.calls == 1:
                    return [{'text': '1842', 'confidence': .9,
                             'judge': 'tesseract', 'box': [0, 0, 12, 12]}]
                return []

        judges = MissingVision()
        with self.assertRaisesRegex(ValueError, 'missing an output judge engine'):
            judge_output(judges, source, SkinPainter().paint(source, [region]),
                         [region], candidate='vision-accurate', options={})
        self.assertEqual(judges.calls, 0)

    def test_attacks_transform_nonuniform_pixels_delivered_to_judges(self):
        y, x = np.indices((24, 48))
        checker = (110 + 18 * ((x // 4 + y // 3) % 2)).astype(np.uint8)
        source = np.repeat(checker[:, :, None], 3, axis=2)
        region = MaskRegion(0, 0, np.full((24, 48), 255, np.uint8), 12)
        painted = SimpleNamespace(pixels=source.copy(), mask=region.raster.copy())

        class PixelWitness:
            names = ['tesseract-5-psm11', 'vision-accurate', 'ppocr-independent']

            def __init__(self):
                self.seen = []

            def read(self, pixels):
                self.seen.append(pixels.copy())
                if len(self.seen) == 1:
                    return [{'text': '1842', 'confidence': .9,
                             'judge': 'tesseract', 'box': [0, 0, 12, 12]}]
                return []

        judges = PixelWitness()
        result = judge_output(judges, source, painted, [region],
                              candidate='vision-accurate', options={})
        self.assertEqual(len(judges.seen), 7)
        np.testing.assert_array_equal(judges.seen[0], source)
        supplied = {record['view']: pixels for record, pixels in
                    zip(result['output_judges'], judges.seen[1:])}
        original = supplied['region-0/original']
        np.testing.assert_array_equal(original, source)
        contrast = supplied['region-0/contrast']
        self.assertEqual((int(contrast.min()), int(contrast.max())), (0, 255))
        self.assertGreater(int(np.ptp(contrast)), int(np.ptp(original)))
        sharp = supplied['region-0/sharpen']
        self.assertFalse(np.array_equal(sharp, original))
        self.assertGreater(int(np.ptp(sharp)), int(np.ptp(original)))
        upscale = supplied['region-0/upscale2x']
        self.assertEqual(upscale.shape, (48, 96, 3))
        nearest = np.repeat(np.repeat(original, 2, axis=0), 2, axis=1)
        self.assertFalse(np.array_equal(upscale, nearest))
        combined = supplied['region-0/contrast-sharpen-upscale2x']
        self.assertEqual(combined.shape, upscale.shape)
        self.assertFalse(np.array_equal(combined, upscale))

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
        self.assertFalse(any(r['text'] == 'OUTSIDE' for r in result['credible_output_leaks']))


if __name__ == '__main__':
    unittest.main()

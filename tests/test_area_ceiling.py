"""Quality comparisons require a fractional ceiling and its receipt reference."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bench import clocked_bench, offline_quality, quality_bundle
import test_quality_bundle as bundle_fixtures


class AreaCeiling(unittest.TestCase):
    def test_bundle_rejects_missing_percent_negative_nan_and_unbacked_ceilings(self):
        fixture = bundle_fixtures.QualityBundle('test_real_encoded_bundle_requires_input_pixels_judging_and_unchanged_masks')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        original = json.loads(fixture.config.read_text())
        original['options']['area_ceiling_basis'] = 'unit:known-mask-area-receipt'
        cases = [('missing', None, 'unit:known-mask-area-receipt'),
                 ('percent-15', 15, 'unit:known-mask-area-receipt'),
                 ('negative', -.1, 'unit:known-mask-area-receipt'),
                 ('nan', float('nan'), 'unit:known-mask-area-receipt'),
                 ('missing-basis', .15, None)]
        for name, ceiling, basis in cases:
            with self.subTest(case=name):
                config = deepcopy(original)
                config['options'].pop('area_ceiling', None)
                if ceiling is not None:
                    config['options']['area_ceiling'] = ceiling
                config['options']['area_ceiling_basis'] = basis
                fixture.config.write_text(json.dumps(config))
                with self.assertRaisesRegex(ValueError, 'ceiling|receipt'):
                    fixture.render(fixture.base / name)

    def test_missing_ceiling_or_basis_cannot_validate_a_comparison(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'masked.mp4'
            output.with_suffix('.masks.json').write_text(json.dumps([
                {'state': 'LIVE', 'protected': False, 'slate': False, 'mask_fraction': .01}] * 2))
            result = self.result(output)
            for options in ({'fast_candidate': 'ppocr-v6-tiny'},
                            {'fast_candidate': 'ppocr-v6-tiny', 'area_ceiling': .15}):
                with self.subTest(options=options):
                    card = offline_quality.build_scorecard([result], 'ppocr-v6-small', options)
                    self.assertIs(card['quality_checks']['masked_area'], False)
                    self.assertIs(card['comparison_valid'], False)

    def test_verify_and_grade_reject_unconfigured_or_invalid_sealed_options(self):
        fixture = bundle_fixtures.QualityBundle('test_real_encoded_bundle_requires_input_pixels_judging_and_unchanged_masks')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        directory = fixture.base / 'sealed'
        plan = fixture.render(directory)
        judge = bundle_fixtures.Judge()
        for field, value in (('area_ceiling', None), ('area_ceiling', 15), ('area_ceiling_basis', '')):
            with self.subTest(field=field, value=value):
                changed = deepcopy(plan)
                changed['options'][field] = value
                quality_bundle.write_json(directory / 'bundle.json', changed)
                (directory / 'bundle.sha256').write_text(quality_bundle.digest(directory / 'bundle.json') + '\n')
                with self.assertRaisesRegex(ValueError, 'ceiling|receipt'):
                    quality_bundle.verify(directory)
                with self.assertRaisesRegex(ValueError, 'ceiling|receipt'):
                    quality_bundle.grade(bundle_fixtures.ROOT, directory, judge=judge)
                self.assertEqual(judge.calls, 0)
                self.assertFalse((directory / 'grade.json').exists())

    def test_valid_ceiling_still_rejects_an_over_ceiling_median(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'masked.mp4'
            output.with_suffix('.masks.json').write_text(json.dumps([
                {'state': 'LIVE', 'protected': False, 'slate': False, 'mask_fraction': .57}] * 2))
            options = {'fast_candidate': 'ppocr-v6-tiny', 'area_ceiling': .15,
                       'area_ceiling_basis': 'unit:known-mask-area-receipt'}
            card = offline_quality.build_scorecard([self.result(output)], 'ppocr-v6-small', options)
            self.assertEqual(card['masked_area_fraction']['p50'], .57)
            self.assertIs(card['quality_checks']['masked_area'], False)
            self.assertIs(card['comparison_valid'], False)
            self.assertTrue(all(value is True for key, value in card['quality_checks'].items()
                                if key != 'masked_area'))

    @staticmethod
    def result(output):
        return {'output': str(output), 'frames': 2, 'real_video_pass': True, 'synthetic_variant': True,
                'natural': {'hidden': 10, 'total': 10}, 'synthetic': {'hidden': 2, 'total': 2},
                'synthetic_input_control': {'total': 2, 'unreadable': 0}}

    def test_both_clis_reject_a_ceiling_without_basis_before_host_work(self):
        for cli in (clocked_bench, offline_quality):
            with self.subTest(cli=cli.__name__), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                (root / 'fixtures').mkdir()
                (root / 'fixtures/manifest.json').write_text(json.dumps({'clips': [
                    {'id': 'unit', 'split': 'tune', 'path': 'fixture.mp4'}]}))
                diagnostic = io.StringIO()
                with patch.object(cli, 'ROOT', root), \
                     patch('fixtures.prepare.verify_cached', side_effect=AssertionError('Unexpected fixture access')), \
                     patch.object(offline_quality, '_fingerprint', side_effect=AssertionError('Unexpected source access')), \
                     contextlib.redirect_stderr(diagnostic):
                    with self.assertRaises(SystemExit) as error:
                        cli.main(['--area-ceiling', '.15'], judge=object())
                self.assertEqual(error.exception.code, 2)
                self.assertIn('basis receipt', diagnostic.getvalue())
                self.assertFalse((root / 'out').exists())


if __name__ == '__main__':
    unittest.main()

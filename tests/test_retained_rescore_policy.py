"""Retained rescoring must validate lane provenance before touching evidence."""
import contextlib
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from bench import regrade, rescore_independent


MIXED_METADATA = {
    'lanes': {'accurate': {'detector_families': ['paddleocr']},
              'fast': {'detector_families': ['apple-vision']}},
    'detector_families': ['apple-vision', 'paddleocr'],
}
ABSENT = object()


class RetainedRescorePolicy(unittest.TestCase):
    def setUp(self):
        scratch = Path('/tmp/agents/irl-shield/q4-retained/tests')
        scratch.mkdir(parents=True, exist_ok=True)
        folder = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        (self.root / 'bench/results').mkdir(parents=True)
        source = Path(__file__).resolve().parents[1]
        for name in ('scoring.py', 'metrics.py', 'independence.py', 'rescore_independent.py'):
            shutil.copyfile(source / 'bench' / name, self.root / 'bench' / name)
        self.write_json(self.root / 'bench/baseline.json', {
            'natural': {'hidden_fraction': 0.}, 'synthetic': {'hidden_fraction': 0.}})

    @staticmethod
    def write_json(path, value):
        path.write_text(json.dumps(value))

    def write_source(self, *, name, candidate='ppocr-v6-small', options=None,
                     metadata=ABSENT, natural_total=1):
        source = self.root / 'out' / name
        source.mkdir(parents=True)
        card = {
            'schema_version': 1, 'run_id': name, 'candidate': candidate,
            'options': {'area_ceiling': .15, 'area_ceiling_basis': 'unit:known-raster-area',
                        **({} if options is None else options)},
            'clips': [{'clip': 'one', 'synthetic_variant': True,
                       'source': str(source / 'one-synthetic-input.mp4')}],
            'natural': {'total': 3, 'hidden': 3, 'hidden_fraction': 1.},
            'synthetic': {'total': 1, 'hidden': 1, 'hidden_fraction': 1.},
            'gate_1': {}, 'real_video_pass': True,
            'masked_area_fraction': {'p50': .1},
            'quality_checks': {'protected': True, 'real_video': True, 'masked_area': True},
        }
        if metadata is not ABSENT:
            card['detector_metadata'] = deepcopy(metadata)
        self.write_json(source / 'scorecard.json', card)
        label = {'id': 'house', 'text': '42 CEDAR', 'box': [300, 0, 380, 20], 'visible': True}
        readings = [
            {'text': text, 'box': [i * 100, 0, i * 100 + 80, 20],
             'confidence': .99, 'judge': judge}
            for i, (text, judge) in enumerate((('ELM ROAD', 'tesseract'),
                                               ('CEDAR AVE', 'vision-accurate'),
                                               ('PINE STREET', 'ppocr-independent')))]
        readings += [{**label, 'confidence': .99, 'judge': judge}
                     for judge in ('tesseract', 'vision-accurate', 'ppocr-independent')]
        self.write_json(source / 'one-synthetic-masked.evidence.json', {
            'raw_input_readings': [readings, readings], 'output_readings': [[], []],
            'guards': [{'pass': True}, {'pass': True}]})
        self.write_json(source / 'one-synthetic-input.truth.json', [[label], [label]])
        prior = {'run_id': name,
                 'old_pooled': {kind: card[kind] for kind in ('natural', 'synthetic')},
                 'independent': {'natural': {'total': natural_total, 'hidden': natural_total,
                                              'hidden_fraction': 1.},
                                 'synthetic': card['synthetic']}}
        return source, prior

    def invoke(self, entrypoint, sources):
        if entrypoint is regrade:
            source, _ = sources[0]
            destination = self.root / 'out' / ('regraded-' + source.name)
            argv = ['regrade', source.name]
            scorecard = destination / 'scorecard.json'
        else:
            self.write_json(self.root / 'bench/results/m1-tune-comparison.json', {'rows': [
                {'source': str((source / 'scorecard.json').relative_to(self.root)),
                 'source_sha256': hashlib.sha256((source / 'scorecard.json').read_bytes()).hexdigest()}
                for source, _ in sources]})
            prior_path = self.root / 'prior.json'
            self.write_json(prior_path, {'rows': [prior for _, prior in sources]})
            destination = self.root / ('rescored-' + sources[0][0].name)
            argv = ['rescore_independent', '--retained-root', str(self.root),
                    '--out', str(destination), '--independent-both', str(prior_path)]
            scorecard = destination / sources[0][0].name / 'scorecard.json'
        events = []
        original_open = Path.open

        def observed_open(path, mode='r', *args, **kwargs):
            if path.name.endswith(('.evidence.json', '.truth.json')) or destination in path.parents:
                events.append((str(path), mode))
            return original_open(path, mode, *args, **kwargs)

        self.destination = destination
        self.evidence_io = events
        with patch.object(entrypoint, 'ROOT', self.root), \
             patch.object(sys, 'argv', argv), patch.object(Path, 'open', observed_open), \
             patch('subprocess.Popen', side_effect=AssertionError('Rescoring must not invoke OCR')), \
             contextlib.redirect_stdout(io.StringIO()):
            entrypoint.main()
        return json.loads(scorecard.read_text())

    def test_missing_recorded_policy_requires_explicit_fast_candidate_before_evidence(self):
        for entrypoint in (regrade, rescore_independent):
            with self.subTest(entrypoint=entrypoint.__name__):
                source = self.write_source(name=entrypoint.__name__.split('.')[-1], natural_total=2)
                with self.assertRaisesRegex(ValueError, 'explicit.*fast_candidate'):
                    self.invoke(entrypoint, [source])
                self.assertEqual(self.evidence_io, [])
                self.assertFalse(self.destination.exists())

    def test_recorded_mixed_policy_cannot_be_replaced_by_current_default(self):
        for entrypoint in (regrade, rescore_independent):
            with self.subTest(entrypoint=entrypoint.__name__):
                source = self.write_source(name=entrypoint.__name__.split('.')[-1],
                                           metadata=MIXED_METADATA, natural_total=2)
                with self.assertRaisesRegex(ValueError, 'recorded.*policy'):
                    self.invoke(entrypoint, [source])
                self.assertEqual(self.evidence_io, [])
                self.assertFalse(self.destination.exists())

    def test_incomplete_or_conflicting_recorded_metadata_is_rejected_before_evidence(self):
        missing_fast = deepcopy(MIXED_METADATA)
        del missing_fast['lanes']['fast']
        wrong_lane = deepcopy(MIXED_METADATA)
        wrong_lane['lanes']['fast']['detector_families'] = ['paddleocr']
        wrong_union = deepcopy(MIXED_METADATA)
        wrong_union['detector_families'] = ['paddleocr']
        for entrypoint in (regrade, rescore_independent):
            for label, metadata in (('missing-fast', missing_fast), ('wrong-lane', wrong_lane),
                                    ('wrong-union', wrong_union), ('null', None)):
                with self.subTest(entrypoint=entrypoint.__name__, metadata=label):
                    source = self.write_source(
                        name=entrypoint.__name__.split('.')[-1] + '-' + label,
                        options={'fast_candidate': 'vision-rectangles'}, metadata=metadata,
                        natural_total=2)
                    with self.assertRaisesRegex(ValueError, 'recorded.*policy'):
                        self.invoke(entrypoint, [source])
                    self.assertEqual(self.evidence_io, [])
                    self.assertFalse(self.destination.exists())

    def test_valid_recorded_controls_cannot_allow_a_family_list_override(self):
        control = {'lanes': {'accurate': {'detector_families': []}}, 'detector_families': []}
        for entrypoint in (regrade, rescore_independent):
            with self.subTest(entrypoint=entrypoint.__name__):
                source = self.write_source(name=entrypoint.__name__.split('.')[-1],
                                           candidate='unmasked', options={'detector_families': []},
                                           metadata=control, natural_total=3)
                with self.assertRaisesRegex(ValueError, 'detector_families overrides'):
                    self.invoke(entrypoint, [source])
                self.assertEqual(self.evidence_io, [])
                self.assertFalse(self.destination.exists())

    def test_supported_policies_score_with_the_validated_family_scope(self):
        same_family = {
            'lanes': {'accurate': {'detector_families': ['paddleocr']},
                      'fast': {'detector_families': ['paddleocr']}},
            'detector_families': ['paddleocr'],
        }
        control = {'lanes': {'accurate': {'detector_families': []}}, 'detector_families': []}
        cases = [
            ('explicit-fast', 'ppocr-v6-small', {'fast_candidate': 'vision-rectangles'},
             ABSENT, MIXED_METADATA, 1, ['tesseract'], False),
            ('recorded-mixed', 'ppocr-v6-small', {'fast_candidate': 'vision-rectangles'},
             MIXED_METADATA, MIXED_METADATA, 1, ['tesseract'], False),
            ('recorded-default', 'ppocr-v6-small', {}, same_family, same_family, 2,
             ['tesseract', 'vision-accurate'], True),
        ]
        for candidate in ('unmasked', 'slate'):
            for label, metadata in (('historical', ABSENT), ('recorded', control)):
                cases.append((candidate + '-' + label, candidate, {}, metadata, control, 3,
                              ['tesseract', 'vision-accurate', 'ppocr-independent'], True))
        for entrypoint in (regrade, rescore_independent):
            for label, candidate, options, recorded, expected, total, truth_judges, valid in cases:
                with self.subTest(entrypoint=entrypoint.__name__, policy=label):
                    source = self.write_source(
                        name=entrypoint.__name__.split('.')[-1] + '-' + label,
                        candidate=candidate, options=options, metadata=recorded, natural_total=total)
                    card = self.invoke(entrypoint, [source])
                    self.assertEqual(card['detector_metadata'], expected)
                    self.assertEqual(card['natural'], {'hidden': total, 'total': total,
                                                       'hidden_fraction': 1.})
                    self.assertEqual(card['synthetic'], {'hidden': 1, 'total': 1,
                                                         'hidden_fraction': 1.})
                    self.assertEqual(card['synthetic_input_control']['total'], 1)
                    self.assertEqual(card['synthetic_input_control']['unreadable'], 0)
                    self.assertEqual(card['judge_independence']['truth_judges'], truth_judges)
                    self.assertEqual(card['judge_independence']['output_leak_judges'],
                                     ['tesseract', 'vision-accurate', 'ppocr-independent'])
                    self.assertIs(card['gate_1']['independent_judges'], valid)
                    self.assertIs(card['comparison_valid'], valid)
                    self.assertIs(card['gate_1']['eligible'], False)
                    self.assertIs(card['gate_1']['pass'], False)

    def test_batch_validates_every_source_before_any_evidence_or_output(self):
        valid = self.write_source(name='first-valid', options={'fast_candidate': 'vision-rectangles'})
        invalid = self.write_source(name='second-invalid', metadata=MIXED_METADATA)
        with self.assertRaisesRegex(ValueError, 'recorded.*policy'):
            self.invoke(rescore_independent, [valid, invalid])
        self.assertEqual(self.evidence_io, [])
        self.assertFalse(self.destination.exists())

    def test_only_an_explicit_masked_area_pass_allows_comparison(self):
        for entrypoint in (regrade, rescore_independent):
            for label, area_pass, expected in (('missing', ABSENT, False), ('unknown', None, False),
                                               ('failed', False, False), ('passed', True, True)):
                with self.subTest(entrypoint=entrypoint.__name__, masked_area=label):
                    source = self.write_source(name=entrypoint.__name__.split('.')[-1] + '-' + label,
                                               candidate='unmasked', natural_total=3)
                    card_path = source[0] / 'scorecard.json'
                    original = json.loads(card_path.read_text())
                    if area_pass is ABSENT:
                        del original['quality_checks']['masked_area']
                    else:
                        original['quality_checks']['masked_area'] = area_pass
                    self.write_json(card_path, original)
                    card = self.invoke(entrypoint, [source])
                    for key in ('judge_discrimination', 'independent_judges', 'protected', 'real_video'):
                        self.assertIs(card['quality_checks'][key], True)
                    self.assertIs(card['comparison_valid'], expected)


if __name__ == '__main__':
    unittest.main()

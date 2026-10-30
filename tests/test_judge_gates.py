"""Scorecard acceptance requires two truth judges independent of every lane."""
import contextlib
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from bench import clocked_bench, offline_quality, regrade, rescore_independent, run as synchronous
from bench.independence import policy_metadata
from bench.scoring import score_records
from shield.masking import masked_frame
import test_clocked_pipeline as clocked_fixtures
import test_provenance as provenance_fixtures


class JudgeGates(unittest.TestCase):
    def setUp(self):
        scratch = Path('/tmp/agents/irl-shield/p2-gates/tests')
        scratch.mkdir(parents=True, exist_ok=True)
        folder = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        (self.root / 'bench/results').mkdir(parents=True)
        (self.root / 'out').mkdir()
        source = Path(__file__).resolve().parents[1]
        for name in ('scoring.py', 'metrics.py', 'independence.py', 'rescore_independent.py'):
            shutil.copyfile(source / 'bench' / name, self.root / 'bench' / name)
        self.write_json(self.root / 'bench/baseline.json', {
            'natural': {'hidden_fraction': 0.}, 'synthetic': {'hidden_fraction': 0.}})

    @staticmethod
    def write_json(path, value):
        path.write_text(json.dumps(value))

    @staticmethod
    def options(mixed):
        return {'fast_candidate': 'vision-rectangles' if mixed else 'ppocr-v6-tiny',
                'area_ceiling': .2, 'area_ceiling_basis': 'unit:known-raster-area', 'delay_seconds': 1.}

    @staticmethod
    def evidence():
        natural = {'text': 'ELM ROAD', 'box': [0, 0, 80, 20]}
        label = {'id': 'house', 'text': '42 CEDAR', 'box': [100, 0, 180, 20], 'visible': True}
        readings = [{**target, 'confidence': .99, 'judge': judge}
                    for target in (natural, label)
                    for judge in ('tesseract', 'vision-accurate', 'ppocr-independent')]
        return ({'raw_input_readings': [readings, readings],
                 'output_readings': [[], []], 'guards': [{'pass': True}, {'pass': True}]},
                [[label], [label]])

    def result(self, mixed, *, clip='one'):
        evidence, truth = self.evidence()
        quality, _ = score_records(evidence['raw_input_readings'], evidence['output_readings'],
                                   truth, evidence['guards'], detector_families=policy_metadata(
                                       'ppocr-v6-small', self.options(mixed))['detector_families'])
        return {'clip': clip, 'synthetic_variant': True, 'frames': 2, **quality}

    @staticmethod
    def masks(count=2):
        return [{'frame': index, 'pts': index / 30, 'emitted_at': 11. + index / 30,
                 'mask_fraction': .1, 'state': 'LIVE', 'protected': False, 'slate': False,
                 'coverage': {'ok': True, 'reason': 'covered', 'fast_age': 0, 'accurate_age': 0}}
                for index in range(count)]

    def assert_truth(self, card, mixed):
        self.assertEqual(card['judge_independence']['truth_judges'],
                         ['tesseract'] if mixed else ['tesseract', 'vision-accurate'])
        self.assertEqual(card['judge_independence']['output_leak_judges'],
                         ['tesseract', 'vision-accurate', 'ppocr-independent'])
        self.assertEqual(card['synthetic_input_control']['unreadable'], 0)
        self.assertGreater(card['synthetic_input_control']['total'], 0)
        for kind in ('natural', 'synthetic'):
            self.assertGreater(card[kind]['total'], 0)
            self.assertEqual(card[kind]['hidden_fraction'], 1.)

    def assert_checks(self, checks):
        for key, passed in checks.items():
            if key not in ('independent_judges', 'eligible', 'pass'):
                self.assertIs(passed, True, f'Another substantive gate failed: {key}')

    def assert_offline_rejection(self, card, mixed, *, gate_has_independence=True):
        self.assert_truth(card, mixed)
        self.assert_checks(card['quality_checks'])
        self.assert_checks(card['gate_1'])
        self.assertIs(card['comparison_valid'], not mixed,
                      'Privacy comparison must reject a single independent truth judge')
        self.assertIs(card['quality_checks']['independent_judges'], not mixed)
        if gate_has_independence:
            self.assertIs(card['gate_1']['independent_judges'], not mixed)
        # These builders cannot establish real-time acceptance, even with two judges.
        self.assertIs(card['gate_1']['eligible'], False)
        self.assertIs(card['gate_1']['pass'], False)

    def test_offline_comparison_rejects_one_independent_truth_judge(self):
        for mixed in (False, True):
            with self.subTest(mixed=mixed):
                result = self.result(mixed)
                output = self.root / 'output.mp4'
                result['output'] = str(output)
                self.write_json(output.with_suffix('.masks.json'), self.masks())
                card = offline_quality.build_scorecard(
                    [result], 'ppocr-v6-small', self.options(mixed))
                # Offline reports independence under quality_checks, not gate_1.
                self.assert_offline_rejection(card, mixed, gate_has_independence=False)

    def test_clocked_gate_rejects_one_independent_truth_judge_with_all_other_gates_true(self):
        snapshot = {'pressure_state': 'normal', 'pressure_level': 1, 'cpu_count': 8,
                    'load_average': [1., 1., 1.], 'raw': {key: {'returncode': 0}
                    for key in ('memory_pressure', 'swapusage', 'pressure_level')}}
        performance = clocked_fixtures.ClockedTransport.warmed_performance(snapshot)
        performance.update(clock_origin=10., cpu_percent_one_core_100=10., peak_tree_rss_mb=20.,
                           startup={'first_packet_delay_seconds': 1.})
        self.assertEqual(clocked_bench.clock_guards(performance),
                         {'throughput': True, 'latency': True, 'protected': True})
        for mixed in (False, True):
            with self.subTest(mixed=mixed):
                directory = self.root / 'out' / ('mixed' if mixed else 'independent')
                directory.mkdir()
                results = []
                for clip in ('one', 'two', 'three'):
                    result = self.result(mixed, clip=clip)
                    output = directory / f'{clip}.mp4'
                    result.update(output=str(output), performance=deepcopy(performance),
                                  quality_window={'original_start_frame': 1198})
                    self.write_json(output.with_suffix('.masks.json'), self.masks(1200))
                    results.append(result)
                card = {'candidate': 'ppocr-v6-small', 'options': self.options(mixed),
                        'clips': results, 'sustained': deepcopy(performance), 'area_ceiling': .2,
                        'area_ceiling_basis': 'synthetic-test-ceiling', 'split': 'heldout', 'pilot': False,
                        'manifest_sha256': 'synthetic-test-manifest', 'queue_measurement_trust': {'clean': True}}
                with contextlib.redirect_stdout(io.StringIO()):
                    card = clocked_bench.aggregate_card(card, directory, root=self.root)
                self.assert_truth(card, mixed)
                self.assert_checks(card['gate_1'])
                self.assertIs(card['gate_1']['eligible'], True)
                self.assertIs(card['gate_1']['pass'], not mixed,
                              'Privacy acceptance must reject a single independent truth judge')
                self.assertIs(card['gate_1'].get('independent_judges'), not mixed,
                              'Scorecard must report whether truth judges are independent')
                self.assertEqual(json.loads((directory / 'scorecard.json').read_text()), card)

    def retained_card(self, mixed):
        source = self.root / 'out' / ('mixed' if mixed else 'independent')
        source.mkdir()
        result = self.result(mixed)
        result['source'] = str(source / 'one-synthetic-input.mp4')
        card = {'schema_version': 1, 'run_id': source.name, 'candidate': 'ppocr-v6-small',
                'options': self.options(mixed), 'clips': [result], 'gate_1': {},
                'masked_area_fraction': {'p50': .1},
                'quality_checks': {'protected': True, 'real_video': True, 'masked_area': True},
                'real_video_pass': True}
        for kind in ('natural', 'synthetic'):
            card[kind] = deepcopy(result['pooled_not_independent'][kind])
        self.write_json(source / 'scorecard.json', card)
        evidence, truth = self.evidence()
        self.write_json(source / 'one-synthetic-masked.evidence.json', evidence)
        self.write_json(source / 'one-synthetic-input.truth.json', truth)
        return source, card

    def test_regrade_comparison_rejects_one_independent_truth_judge(self):
        for mixed in (False, True):
            with self.subTest(mixed=mixed):
                source, _ = self.retained_card(mixed)
                with patch.object(regrade, 'ROOT', self.root), \
                     patch.object(sys, 'argv', ['regrade', source.name]), \
                     contextlib.redirect_stdout(io.StringIO()):
                    regrade.main()
                card = json.loads((self.root / 'out' / f'regraded-{source.name}' / 'scorecard.json').read_text())
                self.assert_offline_rejection(card, mixed)

    def test_retained_rescore_comparison_rejects_one_independent_truth_judge(self):
        for mixed in (False, True):
            with self.subTest(mixed=mixed):
                source, old = self.retained_card(mixed)
                card_path = source / 'scorecard.json'
                self.write_json(self.root / 'bench/results/m1-tune-comparison.json', {'rows': [{
                    'source': str(card_path.relative_to(self.root)),
                    'source_sha256': hashlib.sha256(card_path.read_bytes()).hexdigest()}]})
                counts = {kind: old[kind] for kind in ('natural', 'synthetic')}
                prior = self.root / 'prior.json'
                self.write_json(prior, {'rows': [{'run_id': old['run_id'],
                                                 'old_pooled': counts, 'independent': counts}]})
                destination = self.root / f'rescored-{source.name}'
                with patch.object(rescore_independent, 'ROOT', self.root), \
                     patch.object(sys, 'argv', ['rescore_independent', '--retained-root', str(self.root),
                                               '--out', str(destination), '--independent-both', str(prior)]), \
                     contextlib.redirect_stdout(io.StringIO()):
                    rescore_independent.main()
                card = json.loads((destination / old['run_id'] / 'scorecard.json').read_text())
                self.assert_offline_rejection(card, mixed)

    def test_synchronous_reference_reports_supported_policy_independence_and_remains_ineligible(self):
        # This CLI has no fast-candidate option. Its supported single-family case
        # guards the reported key; the mixed-policy gap is recorded in P2-GATES.md.
        (self.root / 'fixtures').mkdir()
        self.write_json(self.root / 'fixtures/manifest.json', {
            'clips': [{'id': 'one', 'split': 'tune', 'path': 'synthetic.mp4'}]})
        movies = {}
        evidence, truth = self.evidence()
        targets = evidence['raw_input_readings'][0]
        yy, xx = np.indices((200, 200))
        background = np.repeat((60 + (xx // 4 + yy // 4) % 2 * 140)
                               .astype(np.uint8)[..., None], 3, axis=2)

        class Reader:
            names = ['tesseract', 'vision-accurate', 'ppocr-independent']
            paddle = SimpleNamespace(metadata={})

            def __init__(self, *args):
                pass

            def read(self, frame):
                return [reading for reading in targets
                        if frame[10, int(reading['box'][0]) + 10, 0] == 240]

            def close(self):
                pass

        class Capture:
            def __init__(self, path):
                self.frames = iter(movies[str(path)])

            def read(self):
                frame = next(self.frames, None)
                return frame is not None, frame

            def release(self):
                pass

        def prepare(clip, path, synthetic, seconds):
            frame = background.copy()
            frame[:20, :80] = 240
            if synthetic:
                frame[:20, 100:180] = 240
            movies[str(path)] = [frame.copy(), frame.copy()]
            path.write_bytes(b'synthetic input, never decoded as media')
            return truth if synthetic else [[], []]

        def measure(source, output, candidate, options):
            boxes = [[0, 0, 80, 20], [100, 0, 180, 20]]
            frame = movies[str(source)][0]
            _, mask = masked_frame(frame, boxes, options['padding'])
            after = frame.copy()
            after[mask > 0] = 127
            movies[str(output)] = [after.copy(), after.copy()]
            self.write_json(output.with_suffix('.masks.json'), [
                {'boxes': boxes, 'mask_fraction': float((mask > 0).mean())}] * 2)
            return {'fps': 30., 'latency_seconds': {'p50': .2, 'p95': .5},
                    'cpu_percent_one_core_100': 10., 'peak_tree_rss_mb': 20.}

        def sustained(candidate, options, source, destination):
            receipt = provenance_fixtures.SustainedReceipt().receipt()
            fingerprint = synchronous.pipeline_fingerprint()
            receipt.update(candidate=candidate, options=options,
                           source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                           pipeline_sha256=fingerprint)
            for result in receipt['results'].values():
                result['pipeline_sha256'] = fingerprint
            return receipt

        def environment(command, **kwargs):
            if command == ['ffmpeg', '-version']:
                return 'ffmpeg synthetic\n'
            if command == ['sysctl', '-n', 'machdep.cpu.brand_string', 'hw.ncpu', 'hw.memsize']:
                return 'synthetic CPU\n8\n1000000000\n'
            if command == ['uname', '-p']:
                return 'synthetic CPU\n'
            raise AssertionError(f'Unexpected external command: {command}')

        with patch.object(synchronous, 'ROOT', self.root), \
             patch.object(sys, 'argv', ['run', '--candidate', 'ppocr-v6-small',
                                       '--run-id', 'reference', '--with-sustained']), \
             patch.object(synchronous, 'Judges', Reader), \
             patch.object(synchronous, 'variant', side_effect=prepare), \
             patch.object(synchronous, 'run', side_effect=measure), \
             patch.object(synchronous.cv2, 'VideoCapture', Capture), \
             patch('fixtures.prepare.verify_cached'), \
             patch('bench.perf.measure', side_effect=sustained), \
             patch.object(synchronous.subprocess, 'check_output', side_effect=environment), \
             contextlib.redirect_stdout(io.StringIO()):
            synchronous.main()
        card = json.loads((self.root / 'out/reference/scorecard.json').read_text())
        self.assert_truth(card, mixed=False)
        self.assert_checks(card['gate_1'])
        self.assertIs(card['gate_1'].get('independent_judges'), True,
                      'Reference scorecard must report independent truth judges')
        self.assertIs(card['gate_1']['eligible'], False)
        self.assertIs(card['gate_1']['pass'], False)


if __name__ == '__main__':
    unittest.main()

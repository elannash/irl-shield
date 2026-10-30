"""Grades and aggregates remain bound to sealed pixels, policy and source."""
from contextlib import ExitStack
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from bench import offline_quality, quality_bundle as bundle
import test_quality_bundle as fixtures


class BundleProvenance(unittest.TestCase):
    # Reuse the encoded fixture without discovering its TestCase a second time.
    setUp = fixtures.QualityBundle.setUp
    render = fixtures.QualityBundle.render
    corpus = fixtures.QualityBundle.corpus

    def reseal_plan(self, directory, plan):
        bundle.write_json(directory / 'bundle.json', plan)
        (directory / 'bundle.sha256').write_text(bundle.digest(directory / 'bundle.json') + '\n')

    def assert_ungraded(self, directory):
        self.assertFalse((directory / 'grade.json').exists())
        self.assertFalse((directory / 'grade.sha256').exists())

    def test_source_identity_mismatch_rejects_before_any_ocr(self):
        for identity in ('pipeline', 'orchestrator'):
            with self.subTest(identity=identity):
                directory = self.base / identity
                self.render(directory)
                other_source = self.base / 'different-orchestrator.py'
                other_source.write_text('# a different grading implementation\n')
                judge = fixtures.Judge()
                with ExitStack() as stack:
                    if identity == 'pipeline':
                        stack.enter_context(patch.object(offline_quality, '_fingerprint', return_value='different-source'))
                    else:
                        stack.enter_context(patch.object(bundle, '__file__', str(other_source)))
                    with self.assertRaises(ValueError) as raised:
                        bundle.grade(fixtures.ROOT, directory, judge=judge)
                self.assertEqual(judge.calls, 0)
                self.assertIn('grading source differs from sealed render source', str(raised.exception))
                self.assert_ungraded(directory)
                self.assertFalse((directory / 'masked.evidence.json').exists())

    def test_source_identity_change_during_ocr_never_writes_a_grade(self):
        for identity in ('pipeline', 'orchestrator'):
            with self.subTest(identity=identity):
                directory = self.base / identity
                plan = self.render(directory)
                source_copy = self.base / 'orchestrator-copy.py'
                source_copy.write_bytes(Path(bundle.__file__).read_bytes())
                state = {'changed': False}

                class ChangingJudge(fixtures.Judge):
                    def read(self, pixels):
                        readings = super().read(pixels)
                        state['changed'] = True
                        if identity == 'orchestrator':
                            source_copy.write_text('# changed while OCR was reading\n')
                        return readings

                judge = ChangingJudge()
                with ExitStack() as stack:
                    if identity == 'pipeline':
                        stack.enter_context(patch.object(offline_quality, '_fingerprint', side_effect=lambda:
                            'changed-during-ocr' if state['changed'] else plan['pipeline_sha256']))
                    else:
                        stack.enter_context(patch.object(bundle, '__file__', str(source_copy)))
                    with self.assertRaisesRegex(ValueError, 'grading source changed during OCR'):
                        bundle.grade(fixtures.ROOT, directory, judge=judge)
                self.assertEqual(judge.calls, 8, 'Both encoded movies must reach the real saved-mask scorer')
                self.assertTrue((directory / 'masked.evidence.json').is_file())
                self.assert_ungraded(directory)

    def test_aggregate_rejects_changed_grade_evidence_and_bundle_bindings(self):
        directory = self.corpus('receipts')
        card = bundle.aggregate(fixtures.ROOT, directory, 'valid-receipts')
        self.assertEqual(len(card['clips']), 14)
        self.assertFalse(card['gate_1']['eligible'])
        scorecard = directory / 'scorecard.json'
        scorecard.unlink()
        grade_path = sorted(directory.glob('*/grade.json'))[0]
        evidence = grade_path.parent / 'masked.evidence.json'
        seal = grade_path.with_suffix('.sha256')
        originals = {path: path.read_bytes() for path in (grade_path, evidence, seal)}
        for changed, message in (
                ('grade', 'Quality grade changed'),
                ('evidence', 'Quality evidence changed'),
                ('bundle-binding', 'Quality grade refers to a different render')):
            with self.subTest(changed=changed):
                try:
                    if changed == 'grade':
                        grade_path.write_bytes(originals[grade_path] + b'\n')
                    elif changed == 'evidence':
                        evidence.write_bytes(originals[evidence] + b'\n')
                    else:
                        grade = json.loads(originals[grade_path])
                        grade['bundle_sha256'] = '0' * 64
                        bundle.write_json(grade_path, grade)
                        seal.write_text(bundle.digest(grade_path) + '\n')
                    with self.assertRaisesRegex(ValueError, message):
                        bundle.aggregate(fixtures.ROOT, directory, 'rejected-receipts')
                    self.assertFalse(scorecard.exists())
                finally:
                    for path, content in originals.items():
                        path.write_bytes(content)
                    scorecard.unlink(missing_ok=True)

    def test_uniformly_resealed_grade_policy_cannot_replace_rendered_policy(self):
        directory = self.corpus('policy')
        for path in directory.glob('*/grade.json'):
            grade = json.loads(path.read_text())
            grade['options']['padding'] = .125
            bundle.write_json(path, grade)
            path.with_suffix('.sha256').write_text(bundle.digest(path) + '\n')
        with self.assertRaisesRegex(ValueError, 'Quality grade differs from its sealed render policy'):
            bundle.aggregate(fixtures.ROOT, directory, 'wrong-policy')
        self.assertFalse((directory / 'scorecard.json').exists())

    def test_verify_rejects_resealed_artifact_that_rebinds_frozen_manifest(self):
        directory = self.base / 'manifest'
        plan = self.render(directory)
        frozen = directory / 'inputs.json'
        inputs = json.loads(frozen.read_text())
        inputs['scope'] = 'A later input manifest, with the same selected pixels'
        bundle.write_json(frozen, inputs)
        plan['artifacts']['inputs.json'] = {'bytes': frozen.stat().st_size, 'sha256': bundle.digest(frozen)}
        self.reseal_plan(directory, plan)
        with self.assertRaisesRegex(ValueError, 'Quality frozen input manifest changed'):
            bundle.verify(directory)
        self.assert_ungraded(directory)

    def test_verify_rejects_resealed_copied_source_and_truth_rebinding(self):
        for name in ('input.mp4', 'input.truth.json'):
            with self.subTest(artifact=name):
                directory = self.base / name
                plan = self.render(directory)
                artifact = directory / name
                artifact.write_bytes(artifact.read_bytes() + b'\n')
                plan['artifacts'][name] = {'bytes': artifact.stat().st_size, 'sha256': bundle.digest(artifact)}
                self.reseal_plan(directory, plan)
                with self.assertRaisesRegex(ValueError, 'Quality copied input differs from its frozen manifest: ' + name):
                    bundle.verify(directory)
                self.assert_ungraded(directory)

    def test_verify_rejects_absolute_parent_and_symlink_artifact_escapes(self):
        directory = self.base / 'confined'
        original = self.render(directory)
        outside = self.base / 'outside.json'
        outside.write_text('{"synthetic": "outside sealed directory"}\n')
        (directory / 'link.json').symlink_to(outside)
        for name in (str(outside), '../outside.json', 'link.json'):
            with self.subTest(artifact=name):
                plan = {**original, 'artifacts': {name: {
                    'bytes': outside.stat().st_size, 'sha256': bundle.digest(outside)}}}
                self.reseal_plan(directory, plan)
                with self.assertRaisesRegex(ValueError, 'Quality artifact escapes its sealed directory'):
                    bundle.verify(directory)
                self.assert_ungraded(directory)
        self.reseal_plan(directory, original)
        self.assertEqual(bundle.verify(directory)['frames'], 4)


if __name__ == '__main__':
    unittest.main()

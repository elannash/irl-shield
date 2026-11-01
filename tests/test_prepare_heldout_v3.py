"""V3 preparer boundary regressions; synthetic data only, no native imports.

The real 2–7s decode/encode/PTS check belongs to root's physical preparation.
These tests have been authored for root and are not execution receipts.
"""

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare_v3', ROOT / 'fixtures/prepare_heldout_v3.py')
prep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prep)


class SelectionContract(unittest.TestCase):
    def setUp(self):
        self.selected = json.loads((ROOT / 'fixtures/fresh-heldout-v3/selection.json').read_text())

    def test_three_mixed_by_licenses_are_accepted_with_original_metadata(self):
        clips = prep.selection()['clips']
        self.assertEqual([c['license'] for c in clips], ['CC BY 3.0', 'CC BY 3.0', 'CC BY 4.0'])
        self.assertEqual([Path(c['source_path']).suffix for c in clips], ['.ogv', '.webm', '.webm'])
        self.assertTrue(all(c['source_sha256'] is None for c in clips))

    def test_recipe_source_or_author_cannot_be_reselected_after_the_seal(self):
        cases = [('excerpt_start', 3.0), ('seed', 12), ('fps', 25), ('frames', 149),
                 ('source_path', 'fixtures/cache/fresh-heldout-v3/ryde-somerset-walk.webm'),
                 ('id', '../escape'), ('title', 'File:Alternate original.ogv'),
                 ('download_url', 'https://upload.wikimedia.org/wikipedia/commons/other.ogv'),
                 ('source_sha1', '0' * 40), ('source_duration_seconds', 6.9),
                 ('source_sha256', 'a' * 64), ('author', 'Different licensor')]
        for key, value in cases:
            with self.subTest(key=key):
                changed = copy.deepcopy(self.selected)
                changed['clips'][0][key] = value
                with self.assertRaises(ValueError):
                    prep.validate_selection(changed)

    def test_unlicensed_sharealike_and_rebound_license_identity_are_rejected(self):
        for key, value in [('license', 'CC BY-SA 4.0'), ('license', ''),
                           ('license_url', 'https://creativecommons.org/licenses/by-sa/4.0'),
                           ('license_identity', {'licensor_name': 'Somebody else'}),
                           ('license_evidence', {'metadata_license_key': 'cc-by-sa-4.0'})]:
            with self.subTest(key=key, value=value):
                changed = copy.deepcopy(self.selected)
                changed['clips'][2][key] = value
                with self.assertRaises(ValueError):
                    prep.validate_selection(changed)

    def test_missing_source_and_duplicate_origin_or_original_are_rejected(self):
        changed = copy.deepcopy(self.selected)
        changed['clips'].pop()
        with self.assertRaises(ValueError):
            prep.validate_selection(changed)
        for key in ('source_url', 'source_sha1', 'origin_work_identities'):
            with self.subTest(key=key):
                changed = copy.deepcopy(self.selected)
                changed['clips'][1][key] = changed['clips'][0][key]
                with self.assertRaises(ValueError):
                    prep.validate_selection(changed)


class PathsAndPayloads(unittest.TestCase):
    def test_missing_original_stops_prepare_before_any_probe_or_native_decode(self):
        selected = json.loads((ROOT / 'fixtures/fresh-heldout-v3/selection.json').read_text())
        plan = {'schema_version': 1, 'dataset_id': 'fresh-heldout-v3', 'status': 'planned-ungraded',
                'selection_sha256': prep.SELECTION_SHA256, 'metadata_contract_sha256': prep.CONTRACT_SHA256,
                'recipe': prep.RECIPE, 'code_identity': prep.code_identity(),
                'clips': [dict(c, source_sha256=str(index + 1) * 64) for index, c in enumerate(selected['clips'])]}
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            plan_path = base / 'plan.json'
            plan_path.write_text(json.dumps(plan))
            with patch.object(prep, 'probe', side_effect=AssertionError('decode reached')) as probe:
                with self.assertRaises(FileNotFoundError):
                    prep.prepare(plan_path, 'ryde-somerset-walk', {'cache_root': base})
                probe.assert_not_called()

    def test_paths_reject_traversal_absolute_backslash_and_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'link').symlink_to(base, target_is_directory=True)
            for relative in ('../escape', '/absolute', 'a\\b', 'a//b', 'a/./b', 'link/file', './a', ''):
                with self.subTest(relative=relative), self.assertRaises(ValueError):
                    prep.checked_path(base, relative)
            self.assertEqual(prep.checked_path(base, 'safe.webm'), base / 'safe.webm')
            with self.assertRaises(ValueError):
                prep.cache_file(base, 'fixtures/cache/other-dataset/safe.webm')

    def test_missing_payload_wrong_advertised_size_sha1_and_changed_sha256_fail(self):
        payload = b'synthetic unit fixture, never video'
        clip = {'source_path': 'fixtures/cache/fresh-heldout-v3/unit.webm',
                'source_size_bytes': len(payload), 'source_sha1': hashlib.sha1(payload).hexdigest()}
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            with self.assertRaises(FileNotFoundError):
                prep.original(clip, base)
            (base / 'unit.webm').write_bytes(payload)
            expected = hashlib.sha256(payload).hexdigest()
            self.assertEqual(prep.original(clip, base, expected_sha256=expected), expected)
            for key, value in [('source_size_bytes', len(payload) + 1), ('source_sha1', '0' * 40)]:
                with self.subTest(key=key), self.assertRaises(ValueError):
                    prep.original(dict(clip, **{key: value}), base)
            with self.assertRaisesRegex(ValueError, 'SHA256'):
                prep.original(clip, base, expected_sha256='0' * 64)

    def test_exclusive_receipts_preserve_the_first_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'attempt.json'
            prep.exclusive_write(path, {'status': 'failed and retained'})
            first = path.read_bytes()
            with self.assertRaises(FileExistsError):
                prep.exclusive_write(path, {'status': 'replaced'})
            self.assertEqual(path.read_bytes(), first)


class DecodedVideoContract(unittest.TestCase):
    def setUp(self):
        # Literal public ffprobe schema; these numbers come from the fixed
        # source-selection contract, not from the implementation under test.
        self.good = {'streams': [{'codec_type': 'video', 'codec_name': 'h264',
            'width': 1280, 'height': 720, 'avg_frame_rate': '30/1', 'r_frame_rate': '30/1',
            'nb_read_frames': '150', 'pix_fmt': 'yuv420p', 'start_time': '0.000000'}],
            'format': {'duration': '5.000000'}, 'chapters': [],
            'frames': [{'best_effort_timestamp_time': f'{index/30:.6f}'} for index in range(150)]}

    def test_actual_frame_count_audio_and_pts_are_checked_independently(self):
        self.assertEqual(prep.validate_video(self.good), self.good)
        faults = ('149-actual-frames', 'extra-frame', 'audio', 'nonzero-start',
                  'duplicate-pts', 'nan-pts', 'duration', 'subtitles', 'chapter', 'metadata')
        for fault in faults:
            with self.subTest(fault=fault):
                data = copy.deepcopy(self.good)
                if fault == '149-actual-frames':
                    data['streams'][0]['nb_read_frames'] = '149'
                elif fault == 'extra-frame':
                    data['frames'].append({'best_effort_timestamp_time': '5.000000'})
                elif fault in ('audio', 'subtitles'):
                    data['streams'].append({'codec_type': 'audio' if fault == 'audio' else 'subtitle'})
                elif fault == 'nonzero-start':
                    data['streams'][0]['start_time'] = '2.000000'
                elif fault == 'duplicate-pts':
                    data['frames'][10] = data['frames'][9]
                elif fault == 'nan-pts':
                    data['frames'][10]['best_effort_timestamp_time'] = 'nan'
                elif fault == 'duration':
                    data['format']['duration'] = '4.500000'
                elif fault == 'chapter':
                    data['chapters'] = [{'id': 0}]
                else:
                    data['format']['tags'] = {'title': 'retained source title'}
                with self.assertRaises(ValueError):
                    prep.validate_video(data)

    def test_cpu_encoder_recipe_retains_fixed_excerpt_and_limits_both_outputs(self):
        commands = prep.commands(Path('original.ogv'), Path('natural.mp4'), Path('synthetic.mp4'),
                                 {'tools': {'ffmpeg': {'path': '/root-bound/ffmpeg'}}})
        self.assertEqual(len(commands), 2)
        for command in commands:
            with self.subTest(output=command[-1]):
                for flag, value in [('-c:v', 'libx264'), ('-preset', 'medium'), ('-b:v', '10M'),
                                    ('-threads', '2'), ('-threads:v', '2'), ('-filter_threads', '1'),
                                    ('-frames:v', '150'), ('-map_metadata', '-1'), ('-map_chapters', '-1')]:
                    self.assertEqual(command[command.index(flag) + 1], value)
                self.assertTrue({'-n', '-an', '-sn', '-dn'}.issubset(command))
                self.assertNotIn('h264_nvenc', command)
        self.assertEqual(commands[0][commands[0].index('-ss') + 1], '2.0')
        self.assertEqual(commands[0][commands[0].index('-t') + 1], '5.0')
        self.assertEqual(commands[0][commands[0].index('-vf') + 1],
                         'scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=30:start_time=0,setsar=1')


class TruthAndRelease(unittest.TestCase):
    def test_freeze_and_verify_bind_each_prepared_receipt_to_its_actual_path(self):
        selected = prep.selection()
        identity = prep.code_identity()
        clips = [dict(clip, source_sha256=str(index + 1) * 64)
                 for index, clip in enumerate(selected['clips'])]
        plan = {'schema_version': 1, 'dataset_id': 'fresh-heldout-v3',
                'status': 'planned-ungraded', 'recipe': prep.RECIPE,
                'selection_sha256': prep.SELECTION_SHA256,
                'metadata_contract_sha256': prep.CONTRACT_SHA256,
                'code_identity': identity, 'clips': clips}
        video = {'streams': [{'codec_type': 'video', 'codec_name': 'h264',
            'width': 1280, 'height': 720, 'avg_frame_rate': '30/1', 'r_frame_rate': '30/1',
            'nb_read_frames': '150', 'pix_fmt': 'yuv420p', 'start_time': '0.000000'}],
            'format': {'duration': '5.000000'}, 'chapters': [],
            'frames': [{'best_effort_timestamp_time': f'{index/30:.6f}'} for index in range(150)]}
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            plan_path, manifest_path = base / 'plan.json', base / 'manifest.json'
            plan_path.write_text(json.dumps(plan))
            plan_hash = hashlib.sha256(plan_path.read_bytes()).hexdigest()
            provenance_dir = base / 'provenance'
            provenance_dir.mkdir()
            resource_bytes = b'{"synthetic_resource_check": true}\n'
            resource_hash = hashlib.sha256(resource_bytes).hexdigest()
            resource_name = f'provenance/resource-check.{resource_hash}.json'
            (base / resource_name).write_bytes(resource_bytes)
            released = {'status': 'root-authorized-v3-preparation', 'root_owned': True,
                        'resource_check_sha256': resource_hash, 'code_identity': identity,
                        'recipe': prep.RECIPE, 'queue_sources': {'synthetic-wrapper': 'a' * 64},
                        'tools': {}, 'packages': {}}
            release_bytes = json.dumps(released).encode()
            release_hash = hashlib.sha256(release_bytes).hexdigest()
            release_name = f'provenance/root-release.{release_hash}.json'
            (base / release_name).write_bytes(release_bytes)
            prefix = 'fixtures/cache/fresh-heldout-v3/'
            provenance = {prefix + release_name: release_hash, prefix + resource_name: resource_hash}
            for clip in clips:
                inputs = []
                for synthetic, variant in ((False, 'natural'), (True, 'synthetic')):
                    source = f"{clip['id']}-{variant}.mp4"
                    (base / source).write_bytes(source.encode())
                    truth = []
                    for index in range(150):
                        truth.append([{'id': f"{clip['seed']}:{kind}:{int((index/30+k*.67)//4.8)}",
                            'text': 'SYNTHETIC', 'quad': [[0., 0.], [8., 0.], [8., 8.], [0., 8.]],
                            'box': [0., 0., 8., 8.], 'visible': True, 'visibility_fraction': 1.}
                            for k, kind in enumerate(('street', 'plate', 'house', 'storefront'))]
                            if synthetic else [])
                    truth_name = str(Path(source).with_suffix('.truth.json'))
                    (base / truth_name).write_text(json.dumps(truth))
                    inputs.append({'clip': clip['id'], 'synthetic_variant': synthetic,
                        'source': prefix + source, 'truth': prefix + truth_name,
                        'source_sha256': hashlib.sha256((base / source).read_bytes()).hexdigest(),
                        'truth_sha256': hashlib.sha256((base / truth_name).read_bytes()).hexdigest()})
                receipt = {'clip': clip, 'plan_sha256': plan_hash, 'code_identity': identity,
                    'recipe': prep.RECIPE, 'root_release_sha256': release_hash, 'ungraded': True,
                    'queue': {'exclusive': True, 'execution_attempt': 1}, 'tools': {}, 'packages': {},
                    'natural_probe': video, 'synthetic_probe': video, 'provenance': provenance,
                    'inputs': inputs}
                (base / (clip['id'] + '.prepared.json')).write_text(json.dumps(receipt))
            context = {'cache_root': base, 'tools': {}, 'release': released}
            # Original verification and native decoding own separate tests. All
            # receipt, plan, provenance, asset and truth checks here stay real.
            with patch.object(prep, 'original', side_effect=lambda clip, *a, **kw: clip['source_sha256']), \
                    patch.object(prep, 'check_video', return_value=video) as decode:
                prep.freeze(plan_path, manifest_path, context)
                frozen = json.loads(manifest_path.read_text())
                prepared = {
                    prefix + 'ryde-somerset-walk.prepared.json',
                    prefix + 'madison-state-street-walk.prepared.json',
                    prefix + 'katowice-footbridge-walk.prepared.json',
                }
                self.assertEqual(set(frozen['receipts']), prepared | set(provenance))
                for name, digest in frozen['receipts'].items():
                    self.assertEqual(hashlib.sha256((base / name.removeprefix(prefix)).read_bytes()).hexdigest(), digest)
                prep.verify(plan_path, manifest_path, context)
                self.assertEqual(decode.call_count, 6)
                del frozen['receipts'][prefix + 'ryde-somerset-walk.prepared.json']
                manifest_path.write_text(json.dumps(frozen))
                with self.assertRaisesRegex(ValueError, 'final manifest differs'):
                    prep.verify(plan_path, manifest_path, context)

    def test_root_release_cannot_change_codec_or_authorize_tuning_or_retries(self):
        header = {'status': 'root-authorized-v3-preparation', 'root_owned': True,
                  'selection_sha256': prep.SELECTION_SHA256, 'metadata_contract_sha256': prep.CONTRACT_SHA256,
                  'recipe': copy.deepcopy(prep.RECIPE), 'max_preparation_jobs': 2,
                  'max_execution_attempts': 1, 'new_tuning_output_started': False,
                  'resource_check_receipt': '/unopened/synthetic-resource.json',
                  'resource_check_sha256': 'a' * 64}
        changes = [('recipe', dict(prep.RECIPE, encoder='h264_nvenc')),
                   ('new_tuning_output_started', True), ('max_execution_attempts', 2)]
        with tempfile.TemporaryDirectory() as directory:
            release = Path(directory) / 'release.json'
            for key, value in changes:
                with self.subTest(key=key):
                    release.write_text(json.dumps(dict(header, **{key: value})))
                    args = argparse.Namespace(release=release,
                                              release_sha256=hashlib.sha256(release.read_bytes()).hexdigest())
                    with patch.object(prep, 'queue_lease') as queue, patch.object(prep, 'code_identity') as code:
                        with self.assertRaisesRegex(ValueError, 'null, incomplete'):
                            prep.root_context(args)
                        queue.assert_not_called()
                        code.assert_not_called()

    def test_natural_truth_cannot_silently_claim_text_or_drop_frames(self):
        clip = {'seed': 1719557649}
        prep.validate_truth([[] for _ in range(150)], clip, False)
        for truth in ([[] for _ in range(149)], [[{'text': 'unexpected'}]] + [[] for _ in range(149)]):
            with self.assertRaises(ValueError):
                prep.validate_truth(truth, clip, False)

    def test_synthetic_truth_requires_all_four_exact_stable_ids_and_quads(self):
        clip = {'seed': 1719557649}
        rows = []
        for index in range(150):
            rows.append([{'id': f'1719557649:{kind}:{int((index/30+k*.67)//4.8)}', 'text': 'SYNTHETIC',
                          'quad': [[0., 0.], [8., 0.], [8., 8.], [0., 8.]],
                          'box': [0., 0., 8., 8.], 'visible': True, 'visibility_fraction': 1.}
                         for k, kind in enumerate(('street', 'plate', 'house', 'storefront'))])
        prep.validate_truth(rows, clip, True)
        for fault in ('missing-label', 'wrong-interval-id', 'wrong-box', 'nan-quad'):
            with self.subTest(fault=fault):
                changed = copy.deepcopy(rows)
                if fault == 'missing-label':
                    changed[0].pop()
                elif fault == 'wrong-interval-id':
                    changed[149][0]['id'] = '1719557649:street:0'
                elif fault == 'wrong-box':
                    changed[0][0]['box'][2] = 9.
                else:
                    changed[0][0]['quad'][0][0] = float('nan')
                with self.assertRaises(ValueError):
                    prep.validate_truth(changed, clip, True)

    def test_null_root_release_fails_before_queue_tool_or_payload_access(self):
        with tempfile.TemporaryDirectory() as directory:
            release = Path(directory) / 'release.json'
            release.write_text(json.dumps({'status': 'UNBOUND-DO-NOT-RUN', 'actual_argv': None}))
            args = argparse.Namespace(release=release, release_sha256=hashlib.sha256(release.read_bytes()).hexdigest())
            with patch.object(prep, 'queue_lease') as queue, patch.object(prep, 'code_identity') as code:
                with self.assertRaisesRegex(ValueError, 'null, incomplete'):
                    prep.root_context(args)
                queue.assert_not_called()
                code.assert_not_called()


if __name__ == '__main__':
    unittest.main()

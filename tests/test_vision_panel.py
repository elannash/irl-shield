"""Synthetic privacy/lifecycle guards at pack, return and scorer boundaries."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bench.vision_panel import media, pack, protocol, scoring


class VisionPanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PIL import Image, ImageDraw
        cls.storage = tempfile.TemporaryDirectory(prefix='vision-panel-synthetic-')
        cls.base = Path(cls.storage.name)
        im = Image.new('RGB', (96, 64), 'white')
        ImageDraw.Draw(im).text((5, 15), 'FAKE 123', fill='black')
        source = cls.base / 'synthetic.mp4'
        media.save(source, [im] * 60, 30)
        def put(name, value):
            p = cls.base / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(protocol.canonical(value))
            return {'path': str(p), 'sha256': protocol.digest(p)}
        manifest = put('manifest.json', {'status': 'frozen', 'source_allocation': {'synthetic-clip': 'tune'},
            'clips': [{'id': 'synthetic-clip', 'split': 'tune', 'license': 'CC0', 'license_evidence': 'synthetic-test',
                       'source_url': 'synthetic-test', 'author': 'test', 'source_sha256': protocol.digest(source)}]})
        inputs = put('inputs.json', {'fixture_manifest_sha256': manifest['sha256'], 'clips': [
            {'clip': 'synthetic-clip', 'synthetic_variant': False, 'source_sha256': protocol.digest(source)}]})
        policy = put('policy.json', {'candidate': 'synthetic-test-only', 'options': {},
                                   'selection': {'measured_source_commit': 'synthetic-test'}})
        cls.plan = {'label': 'SYNTHETIC TEST ONLY', 'assets': [], 'items': [], 'pairs': [],
                    'metrics': {'best': None, 'challenger': None}}
        for arm in ('best', 'challenger'):
            directory = cls.base / arm
            directory.mkdir()
            for name in ('input.mp4', 'masked.mp4'):
                (directory / name).write_bytes(source.read_bytes())
            artifacts = {name: {'sha256': protocol.digest(directory / name)} for name in ('input.mp4', 'masked.mp4')}
            bundle = put(arm + '/bundle.json', {'candidate': 'synthetic-test-only', 'options': {}, 'clip': 'synthetic-clip',
                'synthetic_variant': False, 'frames': 60, 'source_fps': 30, 'input_manifest_sha256': inputs['sha256'], 'artifacts': artifacts})
            (directory / 'bundle.sha256').write_text(bundle['sha256'] + '\n')
            a = {'id': arm, 'arm': arm, 'clip': 'synthetic-clip', 'variant': 'natural', 'split': 'tune',
                 'origin': 'licensed_fixture', 'role': 'shielded', 'license': 'CC0', 'manifest': manifest,
                 'inputs': inputs, 'bundle': bundle, 'policy': policy, 'source_commit': 'synthetic-test',
                 'media': {'path': str(directory / 'masked.mp4'), 'sha256': artifacts['masked.mp4']['sha256']}, 'fps': 30, 'frames': 60}
            cls.plan['assets'].append(a)
            for i in range(4):
                cls.plan['items'].append({'key': arm + str(i), 'asset': arm, 'kind': 'frame', 'frame': i * 10,
                                          'trap': 'none', 'duplicate_of': None})
        cls.plan['items'].append({'key':'best-clip', 'asset':'best', 'kind':'clip', 'frame':0, 'trap':'none', 'duplicate_of':None})
        a = cls.plan['assets'][0]
        cls.plan['assets'].append({**a, 'id': 'raw', 'role': 'raw',
                                  'media': {'path': str(cls.base / 'best/input.mp4'), 'sha256': protocol.digest(source)}})
        cls.plan['items'] += [
            {'key': 'raw', 'asset': 'raw', 'kind': 'frame', 'frame': 0, 'trap': 'raw', 'duplicate_of': None},
            {'key': 'black', 'asset': 'best', 'kind': 'clip', 'frame': 0, 'trap': 'black', 'duplicate_of': None},
            {'key': 'dup', 'asset': 'best', 'kind': 'frame', 'frame': 0, 'trap': 'duplicate', 'duplicate_of': 'best0'}]
        cls.plan['pairs'] = [{'key': 'p', 'current_best': 'best0', 'candidate': 'challenger0', 'duplicate_of': None},
                             {'key': 'pd', 'current_best': 'best0', 'candidate': 'challenger0', 'duplicate_of': 'p'}]
        cls.public = cls.base / 'public'
        cls.private = cls.base / 'private'
        pack.build(cls.plan, cls.public, cls.private)
        cls.document = protocol.verify_public(cls.public)
        cls.mapping = protocol.load(cls.private / 'SEALED.json')
        cls.map_hash = protocol.digest(cls.private / 'SEALED.json')

    @classmethod
    def tearDownClass(cls):
        cls.storage.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=self.base)
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.round = self.work / 'round'

    def begin(self):
        return scoring.begin(self.public, self.round, ('independent-sol-session', 'independent-opus-session'))

    def response(self, start):
        items = []
        for p in self.document['items']:
            m = self.mapping['items'][p['id']]
            items.append({'id': p['id'], 'readable': [], 'location_inference': '',
                          'privacy': 3 if m['trap'] == 'raw' else 9,
                          'watchability': 3 if m['trap'] == 'black' else 8})
        pairs = []
        for p in self.document['pairs']:
            candidate = self.mapping['pairs'][p['id']]['candidate']
            side = 'left' if p['left'] == candidate else 'right'
            pairs.append({'id': p['id'], 'privacy': side, 'watchability': 'tie'})
        return {'version': 1, 'pack_digest': self.document['pack_digest'], 'grader_identity': start['grader_identity'],
                'start_id': start['start_id'], 'complete': True, 'items': items, 'pairs': pairs}

    def returns(self, change=None):
        for slot, start in enumerate(self.begin()):
            response = self.response(start)
            if change:
                change(slot, response)
            p = self.work / f'return-{slot}.json'
            p.write_bytes(protocol.canonical(response))
            scoring.finish(self.public, self.round, slot, p)

    def score(self):
        return scoring.score(self.public, self.private, self.round, self.map_hash)

    def test_owner_raw_rejected_before_media_open(self):
        p = copy.deepcopy(self.plan)
        p['assets'][-1]['origin'] = 'owner'
        with patch.object(media, 'extract') as decoder, patch.object(pack, 'receipt') as receipt:
            with self.assertRaisesRegex(protocol.PanelError, 'before media open'):
                pack.validate_plan(p)
            decoder.assert_not_called()
            receipt.assert_not_called()

    def test_fresh_v2_forbidden_before_media_open(self):
        for change in ('split', 'path'):
            p = copy.deepcopy(self.plan)
            if change == 'split':
                p['assets'][0]['split'] = 'fresh-v2'
            else:
                p['assets'][0]['media']['path'] = '/forbidden/fresh-v2/a.mp4'
            with self.subTest(change=change), patch.object(pack, 'receipt') as receipt:
                with self.assertRaisesRegex(protocol.PanelError, 'fresh-v2'):
                    pack.validate_plan(p)
                receipt.assert_not_called()

    def test_synthetic_effectiveness_and_unknown_license_rejected(self):
        for field, value, error in [('variant', 'synthetic', 'synthetic'), ('license', 'unknown', 'unlicensed')]:
            p = copy.deepcopy(self.plan)
            p['assets'][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(protocol.PanelError, error):
                pack.validate_plan(p)

    def test_missing_traps_and_tiny_packs_rejected(self):
        for remove in ('raw', 'black', 'duplicate', 'none'):
            p = copy.deepcopy(self.plan)
            p['items'] = [i for i in p['items'] if i['trap'] != remove]
            if remove == 'none':
                p['items'] = [i for i in p['items'] if i['trap'] != 'duplicate']
            with self.subTest(remove=remove), self.assertRaisesRegex(protocol.PanelError, 'missing traps'):
                pack.validate_plan(p)

    def test_public_blind_metadata_and_allowlist(self):
        doc = protocol.verify_public(self.public)
        self.assertEqual(set(doc), {'version', 'pack_id', 'pack_digest', 'items', 'pairs', 'files'})
        for i in doc['items']:
            self.assertEqual(set(i), {'id', 'file', 'kind'})
            self.assertRegex(i['file'], r'^[a-f0-9]{32}\.(png|mp4)$')
            media.normalize_check(self.public / i['file'])
        raw = (self.public / 'items.json').read_text()
        for forbidden in ('challenger', 'synthetic-clip', 'policy', 'source', 'GPS'):
            self.assertNotIn(forbidden, raw)
        extra = self.public / 'leak.txt'
        extra.write_text('source')
        try:
            with self.assertRaisesRegex(protocol.PanelError, 'extra files'):
                protocol.verify_public(self.public)
        finally:
            extra.unlink()

    def test_strict_response_rejects_missing_unknown_duplicate_and_nonfinite(self):
        start = self.begin()[0]
        base = self.response(start)
        cases = []
        for field, value in [('privacy', True), ('privacy', 0), ('privacy', 11), ('privacy', 9.0), ('watchability', float('inf'))]:
            r = copy.deepcopy(base); r['items'][0][field] = value; cases.append(r)
        r = copy.deepcopy(base); r['items'][0]['extra'] = 'x'; cases.append(r)
        r = copy.deepcopy(base); del r['items'][0]['readable']; cases.append(r)
        r = copy.deepcopy(base); r['items'][1]['id'] = r['items'][0]['id']; cases.append(r)
        r = copy.deepcopy(base); r['items'][0]['id'] = 'unknown'; cases.append(r)
        r = copy.deepcopy(base); r['items'].pop(); cases.append(r)
        r = copy.deepcopy(base); r['complete'] = False; cases.append(r)
        r = copy.deepcopy(base); r['pack_digest'] = 'wrong'; cases.append(r)
        for r in cases:
            with self.subTest(r=r), self.assertRaises(protocol.PanelError):
                protocol.validate_response(r, self.document, start)
        p = self.work / 'duplicate-key.json'
        p.write_text('{"id":1,"id":2}')
        with self.assertRaisesRegex(protocol.PanelError, 'duplicate JSON key'):
            protocol.load(p)
        p.write_text('{"x":NaN}')
        with self.assertRaisesRegex(protocol.PanelError, 'nonfinite'):
            protocol.load(p)

    def test_trap_failure_either_grader_voids_all_arm_scores(self):
        def fail(slot, r):
            if slot == 1:
                raw = next(k for k, v in self.mapping['items'].items() if v['trap'] == 'raw')
                next(i for i in r['items'] if i['id'] == raw)['privacy'] = 4
        self.returns(fail)
        report = self.score()
        self.assertEqual(report['status'], 'VOID')
        self.assertEqual(report['arms'], {})
        self.assertEqual(report['pairwise'], [])
        self.assertLess(report['traps']['independent-opus-session']['rate'], 1)

    def test_both_seals_required_before_unblind(self):
        starts = self.begin()
        p = self.work / 'one.json'; p.write_bytes(protocol.canonical(self.response(starts[0])))
        scoring.finish(self.public, self.round, 0, p)
        # Nonexistent private path proves the private map is never opened first.
        with self.assertRaisesRegex(protocol.PanelError, 'both grader seals'):
            scoring.score(self.public, self.work / 'MUST-NOT-OPEN', self.round, 'irrelevant')
        self.assertFalse((self.round / 'score.json').exists())

    def test_same_identity_replay_and_output_drift_rejected(self):
        with self.assertRaisesRegex(protocol.PanelError, 'distinct'):
            scoring.begin(self.public, self.round, ('same', 'SAME'))
        self.returns()
        with self.assertRaisesRegex(protocol.PanelError, 'replay'):
            scoring.begin(self.public, self.round, ('other1', 'other2'))
        p = self.round / 'output-1.json'
        p.chmod(0o600); p.write_text('{}')
        with self.assertRaisesRegex(protocol.PanelError, 'seal/state drift'):
            self.score()

    def test_source_hash_drift_and_private_map_drift_rejected(self):
        p = copy.deepcopy(self.plan)
        p['assets'][0]['media']['sha256'] = '0' * 64
        with self.assertRaisesRegex(protocol.PanelError, 'media provenance mismatch'):
            pack.validate_plan(p)
        self.returns()
        with self.assertRaisesRegex(protocol.PanelError, 'private map drift'):
            scoring.score(self.public, self.private, self.round, '0' * 64)
        receipt = Path(self.plan['assets'][0]['policy']['path'])
        original = receipt.read_bytes()
        receipt.write_bytes(original + b' ')
        try:
            with self.assertRaisesRegex(protocol.PanelError, 'source/hash drift'):
                self.score()
        finally:
            receipt.write_bytes(original)

    def test_readable_hits_map_to_source_and_remain_inert_data(self):
        identity = next(k for k, m in self.mapping['items'].items() if m['key'] == 'challenger1')
        text = '<script>throw 1</script>;$(touch /forbidden)'
        def hit(slot, r):
            next(i for i in r['items'] if i['id'] == identity)['readable'] = [{'kind': 'word', 'text': text, 'frame_offset': 0}]
        self.returns(hit)
        report = self.score()
        self.assertEqual(report['status'], 'VALID')
        self.assertEqual(len(report['readable_work_items']), 2)
        for h in report['readable_work_items']:
            self.assertEqual((h['item_id'], h['arm'], h['source_frame'], h['hit']['text']), (identity, 'challenger', 10, text))
        self.assertEqual(report['arms']['challenger']['metrics']['panel_readable_hits'], 2)
        self.assertIsNone(report['arms']['best']['metrics']['gpu_ms'])
        self.assertFalse(report['production_promotion'])

    def test_clip_hit_at_end_stays_within_presented_frames(self):
        identity = next(k for k,m in self.mapping['items'].items() if m['key']=='best-clip')
        def hit(slot,r):
            next(i for i in r['items'] if i['id']==identity)['readable']=[{'kind':'logo','text':'SYNTHETIC MARK','frame_offset':1.99}]
        self.returns(hit)
        report=self.score()
        self.assertEqual(report['status'],'VALID')
        rows=[h for h in report['readable_work_items'] if h['item_id']==identity]
        self.assertEqual(len(rows),2)
        self.assertEqual([h['source_frame'] for h in rows],[59,59])

    def test_reversed_pair_contradiction_voids_round(self):
        duplicate = next(k for k,p in self.mapping['pairs'].items() if p['duplicate_of'] is not None)
        def contradict(slot,r):
            if slot==0:
                next(p for p in r['pairs'] if p['id']==duplicate)['privacy']='tie'
        self.returns(contradict)
        report=self.score()
        self.assertEqual(report['status'],'VOID')
        self.assertEqual(report['arms'],{})
        checks=report['traps']['independent-sol-session']['checks']
        self.assertTrue(any(c['type']=='pair_duplicate' and not c['passed'] for c in checks))

    def test_pairwise_order_maps_winners_and_ties_and_duplicates(self):
        self.returns()
        report = self.score()
        self.assertEqual(report['status'], 'VALID')
        privacy = [p for p in report['pairwise'] if p['axis'] == 'privacy']
        self.assertEqual(len(privacy), 2)
        for p in privacy:
            self.assertEqual((p['candidate'], p['wins'], p['ties'], p['denominator']), ('challenger', 1, 0, 1))
        for p in report['pairwise']:
            if p['axis'] == 'watchability':
                self.assertEqual(p['ties'], 1)
                self.assertIsNone(p['win_rate_decisive'])
        original = next(q for q in self.document['pairs'] if self.mapping['pairs'][q['id']]['duplicate_of'] is None)
        duplicate = next(q for q in self.document['pairs'] if self.mapping['pairs'][q['id']]['duplicate_of'] is not None)
        self.assertEqual((duplicate['left'], duplicate['right']), (original['right'], original['left']))
        for identity, p in self.mapping['pairs'].items():
            public = next(i for i in self.document['pairs'] if i['id'] == identity)
            self.assertEqual({public['left'], public['right']}, {p['current_best'], p['candidate']})
        self.assertIsNone(report['arms']['best']['pooled']['privacy']['ci95'])
        self.assertEqual(report['arms']['best']['pooled']['privacy']['source_clusters'], 1)

    def test_duplicate_contradiction_voids_without_threshold_tuning(self):
        dup = next(k for k, v in self.mapping['items'].items() if v['trap'] == 'duplicate')
        def contradict(slot, r):
            next(i for i in r['items'] if i['id'] == dup)['privacy'] = 7
        self.returns(contradict)
        self.assertEqual(self.score()['status'], 'VOID')

    def test_start_state_and_metric_join_drift_rejected(self):
        start = self.begin()[0]
        p = self.round / 'start-0.json'
        changed = protocol.load(p)
        changed['started_at'] = '2000-01-01T00:00:00+00:00'
        p.chmod(0o600); p.write_bytes(protocol.canonical(changed))
        response = self.work / 'response.json'
        response.write_bytes(protocol.canonical(self.response(start)))
        with self.assertRaisesRegex(protocol.PanelError, 'start state drift'):
            scoring.finish(self.public, self.round, 0, response)
        a = self.plan['assets'][0]
        metrics = {'arm': 'best', 'scope': 'natural-tune', 'source_commit': a['source_commit'],
                   'policy_sha256': a['policy']['sha256'], 'input_sha256s': [a['media']['sha256']],
                   'output_sha256s': [a['media']['sha256']], 'metrics': dict.fromkeys(pack.METRICS),
                   'evidence': dict.fromkeys(pack.METRICS)}
        evidence = self.work / 'evidence.json'
        evidence.write_bytes(protocol.canonical({'hidden': .75}))
        metrics['metrics']['natural_hidden'] = .75
        metrics['evidence']['natural_hidden'] = {'receipt': {'path': str(evidence), 'sha256': protocol.digest(evidence)}, 'pointer': ['hidden']}
        m = self.work / 'metrics.json'
        m.write_bytes(protocol.canonical(metrics))
        plan = copy.deepcopy(self.plan)
        plan['metrics']['best'] = {'path': str(m), 'sha256': protocol.digest(m)}
        pack.validate_plan(plan)
        metrics['output_sha256s'] = ['wrong']
        m.write_bytes(protocol.canonical(metrics))
        plan['metrics']['best']['sha256'] = protocol.digest(m)
        with self.assertRaisesRegex(protocol.PanelError, 'metric join identity drift'):
            pack.validate_plan(plan)

    def test_raw_traps_reject_synthetic_variants_before_receipt_access(self):
        candidate = copy.deepcopy(self.plan)
        next(a for a in candidate['assets'] if a['role']=='raw')['variant']='synthetic'
        with patch.object(pack, 'receipt', side_effect=AssertionError('Receipt accessed before raw-variant validation')):
            with self.assertRaisesRegex(protocol.PanelError, 'raw traps require natural'):
                pack.validate_plan(candidate)

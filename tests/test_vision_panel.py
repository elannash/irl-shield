"""Synthetic event cards; no detector/OCR/model/network/actual footage inputs."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bench.vision_panel import budget, pack, protocol as p, scoring


class VisionPanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PIL import Image
        # These tests exercise real files, hashes and exclusive state, not disk
        # power-loss durability. Avoid flushing the shared host disk per receipt.
        sync = patch.object(p.os, 'fsync', return_value=None)
        sync.start(); cls.addClassCleanup(sync.stop)
        cls.storage = tempfile.TemporaryDirectory(prefix='vision-panel-v2-')
        cls.base = Path(cls.storage.name)
        cls.image = cls.base / 'synthetic.png'
        Image.new('RGB', (16, 16), 'white').save(cls.image)
        cls.image_hash = p.digest(cls.image)
        def put(name, value):
            path = cls.base / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(p.canonical(value))
            return {'path': str(path), 'sha256': p.digest(path)}
        cls.put = staticmethod(put)
        instrument = put('instrument.json', {'synthetic': True})
        cls.plan = pack.skeleton(); cls.plan['status'] = 'READY'
        cls.plan['events'] = []
        decisions = []
        def item(key, event, clip, role, control=None):
            policy = p.sha(role.encode())
            source = {'origin': 'licensed_fixture', 'alias': 'synthetic-test-source', 'clip': clip, 'event': event,
                      'dataset_kind': 'tune', 'dataset_sha256': p.sha(b'synthetic-dataset'), 'license': 'CC0',
                      'variant': 'natural', 'media_role': 'raw' if control == 'readable_leak' else 'processed',
                      'source_sha256': p.sha(event.encode()), 'policy_sha256': policy, 'output_sha256': p.sha(key.encode())}
            source['receipt'] = put(key + '/source.json', {**source, 'license_verified': True, 'source_allocation_verified': True})
            frames = [{'path': str(cls.image), 'sha256': cls.image_hash, 'timestamp': t} for t in (0, 1.99)]
            extraction = put(key + '/extract.json', {'output_sha256': source['output_sha256'], 'fps': 30,
                'frame_start': 10, 'frame_count': 60, 'frames': [{'timestamp': f['timestamp'], 'sha256': f['sha256']} for f in frames], 'crops': []})
            qualification = put(key + '/qualification.json', {'status': 'LOCALLY_QUALIFIED', 'policy_sha256': policy,
                'output_sha256': source['output_sha256'], 'source_sha256': source['source_sha256'],
                'ocr_pass': True, 'runtime_pass': True, 'real_video_pass': True, 'geoclip_frozen': True,
                'geoclip_no_new_success': True, 'area_ceiling': .15, 'area_guard_pass': True,
                'area_aggregation': 'synthetic existing aggregation', 'delay_seconds': 1,
                'runtime_receipt': instrument, 'ocr_receipt': instrument, 'geoclip_receipt': instrument})
            return {'key': key, 'event': event, 'role': role, 'source': source, 'qualification': qualification,
                    'extraction': extraction, 'frames': frames, 'crops': [], 'fps': 30, 'frame_start': 10, 'frame_count': 60, 'control': control}
        for index, clip in enumerate(list(pack.TUNE_CLIPS[:5]) * 2 + list(pack.TUNE_CLIPS[5:])):
            event = 'synthetic-event-' + str(index)
            a, b = 'a' + str(index), 'b' + str(index)
            cls.plan['items'] += [item(a, event, clip, 'incumbent'), item(b, event, clip, 'challenger')]
            cls.plan['events'].append({'event': event, 'clip': clip, 'incumbent': a, 'challenger': b})
            decisions.append({'event': event, 'clip': clip, 'decision': 'keep', 'known_issue_ids': ['known-ocr'],
                              'ocr': instrument, 'area': instrument, 'runtime': instrument, 'geoclip': instrument})
        for kind in pack.CONTROLS:
            cls.plan['items'].append(item(kind, 'control-' + kind, pack.TUNE_CLIPS[0], 'control', kind))
            ref = put(kind + '/reference.json', {'target_id': 'same-synthetic-target', 'known_readable': True,
                'genuinely_removed': True, 'known_utility_failure': True, 'no_grounded_specific_location': True, 'exact_string': 'TEST'})
            cls.plan['controls'].append({'type': kind, 'item': kind, 'category': 'text_sign', 'reference': ref})
        before = cls.base / 'before.json'
        scoring.record_before(before, decisions, p.sha(b'frozen selection'))
        cls.plan['local_before'] = {'path': str(before), 'sha256': p.digest(before)}
        cls.public, cls.private = cls.base / 'public', cls.base / 'private'
        cls.receipt = pack.seal(cls.plan, cls.public, cls.private)
        cls.mapping = p.load(cls.private / 'SEALED.json')
        cls.by_key = {v['item']['key']: k for k, v in cls.mapping['items'].items()}

    @classmethod
    def tearDownClass(cls):
        cls.storage.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=self.base)
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.round = self.work / 'round'

    def starts(self, luna=False):
        providers = ('opus', 'sol', 'luna') if luna else ('opus', 'sol')
        assignments = [{'item_id': item, 'provider': provider, 'grader_identity': provider + '-' + item,
                        'model': p.MODELS[provider][0], 'effort': p.MODELS[provider][1]}
                       for item in self.mapping['items'] for provider in providers]
        return scoring.begin(self.public, self.round, assignments, self.plan['local_before'])

    def answer(self, start):
        card = p.verify_card(self.public / start['item_id'])
        m = self.mapping['items'][start['item_id']]['item']
        finding = [{'category': c, 'leak': 'absent_in_sample', 'severity': 0, 'evidence': []} for c in p.CATEGORIES]
        evidence = {'frame_id': card['frames'][-1]['id'], 'timestamp': 1.99, 'bbox': [0, 0, 1, 1], 'exact_string': 'TEST', 'cue': ''}
        if m['control'] == 'readable_leak':
            finding[0].update(leak='present', severity=3, evidence=[evidence])
        return {'version': 2, 'item_id': start['item_id'], 'card_digest': start['card_digest'],
                'grader_identity': start['grader_identity'], 'start_id': start['start_id'], 'status': 'completed', 'complete': True,
                'findings': finding, 'utility': {'state': 'unacceptable' if m['control'] == 'utility_failure' else 'acceptable',
                'defects': [evidence] if m['control'] == 'utility_failure' else []},
                'location': {'state': 'generic' if m['control'] == 'generic_context' else 'not_observed', 'evidence': []},
                'exposed_faces_count': 0, 'notes': ''}

    def finish_all(self, change=None, luna=False):
        starts = self.starts(luna)
        for row in starts:
            value = self.answer(row)
            if change:
                change(row, value)
            path = self.work / (row['entry_id'] + '.json'); path.write_bytes(p.canonical(value))
            scoring.finish(self.public, self.round, row['entry_id'], path,
                           {'received': True, 'image_sha256s': [self.image_hash]})
        return starts

    def reveal(self):
        return scoring.reveal(self.public, self.private, self.round, self.receipt['map_sha256'])

    def test_missing_challenger_never_builds_pilot(self):
        missing = pack.skeleton()
        self.assertEqual(pack.validate_plan(missing)['status'], 'MISSING_INPUTS')
        with self.assertRaisesRegex(p.PanelError, 'MISSING_INPUTS'):
            pack.seal(missing, self.work / 'public', self.work / 'private')
        self.assertFalse((self.work / 'public').exists())

    def test_owner_alias_and_raw_synthetic_rejected_before_any_receipt(self):
        for field, value in [('origin', 'owner'), ('alias', 'owner-real'), ('variant', 'synthetic')]:
            plan = copy.deepcopy(self.plan)
            target = next(i for i in plan['items'] if i['control'] == 'readable_leak')
            target['source'][field] = value
            with self.subTest(field=field), patch.object(pack, 'receipt', side_effect=AssertionError('receipt touched')):
                with self.assertRaises(p.PanelError):
                    pack.access_policy(plan)

    def test_fresh_and_spent_access_require_exact_authority_before_receipts(self):
        for kind, value in [('fresh-v2', '0' * 64), ('spent-v1', 'wrong')]:
            plan = copy.deepcopy(self.plan)
            plan['items'][0]['source'].update(dataset_kind=kind, dataset_sha256=value)
            with self.subTest(kind=kind), patch.object(pack, 'receipt', side_effect=AssertionError('receipt touched')):
                with self.assertRaises(p.PanelError):
                    pack.access_policy(plan)
        plan['phase'] = 'locked'; plan['items'][0]['source']['dataset_sha256'] = pack.SPENT_V1_SHA256
        pack.access_policy(plan)

    def test_matched_events_times_controls_and_clip_caps(self):
        mutations = [lambda x: x['events'].pop(), lambda x: x['controls'].pop(),
                     lambda x: x['items'][1]['frames'].pop(),
                     lambda x: x['items'][1]['source'].update(source_sha256='different')]
        for mutate in mutations:
            plan = copy.deepcopy(self.plan); mutate(plan)
            with self.assertRaises(p.PanelError):
                pack.validate_plan(plan)

    def test_blind_per_item_allowlist_and_source_drift(self):
        card_dir = next(self.public.iterdir()); card = p.verify_card(card_dir)
        self.assertEqual(set(card), {'version', 'item_id', 'card_digest', 'frames', 'crops', 'files'})
        raw = (card_dir / 'items.json').read_text()
        for forbidden in ('incumbent', 'challenger', 'source', 'policy', 'synthetic-event'):
            self.assertNotIn(forbidden, raw)
        extra = card_dir / 'source.txt'; extra.write_text('bad')
        try:
            with self.assertRaisesRegex(p.PanelError, 'extra card'):
                p.verify_card(card_dir)
        finally:
            extra.unlink()
        plan = copy.deepcopy(self.plan); plan['items'][0]['source']['receipt']['sha256'] = 'wrong'
        with self.assertRaisesRegex(p.PanelError, 'source/hash drift'):
            pack.validate_plan(plan)

    def test_strict_response_missing_unknown_duplicate_nonfinite_and_person_identity(self):
        row = self.starts()[0]; card = p.verify_card(self.public / row['item_id']); base = self.answer(row)
        cases = []
        r = copy.deepcopy(base); r['extra'] = True; cases.append(r)
        r = copy.deepcopy(base); del r['utility']; cases.append(r)
        r = copy.deepcopy(base); r['findings'][1]['category'] = r['findings'][0]['category']; cases.append(r)
        r = copy.deepcopy(base); r['findings'][0]['severity'] = True; cases.append(r)
        r = copy.deepcopy(base); r['card_digest'] = 'wrong'; cases.append(r)
        r = copy.deepcopy(base); r['status'] = 'timeout'; r['complete'] = False; cases.append(r)
        r = copy.deepcopy(base); r['findings'][0].update(leak='present', severity=3, evidence=[]); cases.append(r)
        r = copy.deepcopy(base); r['notes'] = 'x ' * 251; cases.append(r)
        for r in cases:
            with self.assertRaises(p.PanelError):
                p.validate_response(r, card, row)
        r = copy.deepcopy(base); r['findings'][-1].update(leak='present', severity=2, evidence=[{
            'frame_id': card['frames'][0]['id'], 'timestamp': 0, 'bbox': [0, 0, 1, 1], 'exact_string': 'PERSON NAME', 'cue': 'face'}]); r['exposed_faces_count'] = 1
        with self.assertRaisesRegex(p.PanelError, 'person identification'):
            p.validate_response(r, card, row)
        path = self.work / 'bad.json'
        for content in ('{"a":1,"a":2}', '{"x":NaN}'):
            path.write_text(content)
            with self.assertRaises(p.PanelError):
                p.load(path)

    def test_all_actual_seals_before_map_and_no_text_only_capability(self):
        rows = self.starts(luna=True)
        row = rows[0]; path = self.work / 'answer.json'; path.write_bytes(p.canonical(self.answer(row)))
        with self.assertRaisesRegex(p.PanelError, 'actual image'):
            scoring.finish(self.public, self.round, row['entry_id'], path, None)
        with self.assertRaisesRegex(p.PanelError, 'all actual first-pass'):
            scoring.reveal(self.public, self.work / 'MUST-NOT-OPEN', self.round, 'wrong')
        self.assertFalse((self.round / 'UNBLINDED.json').exists())

    def test_clip_hit_end_floor_clamp_and_reversed_contradiction(self):
        self.assertEqual([scoring.source_frame(0, 30, 60, 1.99) for _ in ('opus', 'sol')], [59, 59])
        self.assertTrue(scoring.comparison_consistency({'utility': 'A'}, {'utility': 'B'}, ['x', 'y'], ['y', 'x']))
        self.assertFalse(scoring.comparison_consistency({'utility': 'A'}, {'utility': 'tie'}, ['x', 'y'], ['y', 'x']))
        self.assertFalse(scoring.comparison_consistency({'utility': 'A'}, {'utility': 'A'}, ['x', 'y'], ['y', 'x']))
        self.assertTrue(scoring.comparison_consistency({'utility': 'tie'}, {'utility': 'tie'}, ['x', 'x'], ['x', 'x'], identical=True))

    def test_per_grader_controls_stop_automatic_use_and_preserve_findings(self):
        def fail(row, answer):
            if row['provider'] == 'sol' and self.mapping['items'][row['item_id']]['item']['control'] == 'readable_leak':
                answer['findings'][0].update(leak='absent_in_sample', severity=0, evidence=[])
        self.finish_all(fail, luna=True)
        report = self.reveal()
        self.assertTrue(report['controls']['sol']['automatic_use_stopped'])
        self.assertFalse(report['controls']['opus']['automatic_use_stopped'])
        self.assertEqual(len(report['answers']), 84)
        self.assertEqual(report['event_denominator'], 12)
        self.assertIsNone(report['privacy_score']); self.assertFalse(report['production_promotion'])

    def test_readable_hits_mapping_and_start_output_map_drift(self):
        self.finish_all()
        with self.assertRaisesRegex(p.PanelError, 'private map drift'):
            scoring.reveal(self.public, self.private, self.round, 'wrong')
        report = self.reveal()
        hits = report['readable_and_cue_work_items']
        self.assertEqual([h['source_frame'] for h in hits], [69, 69])
        self.assertTrue(all(h['evidence']['exact_string'] == 'TEST' for h in hits))
        self.assertEqual(report['source_clip_denominator'], 7)


    def test_before_after_requires_grounded_strong_receipts_and_preserves_known_failures(self):
        barrier = self.work / 'UNBLINDED.json'; barrier.write_bytes(p.canonical({'synthetic': True}))
        findings = {'unblind_barrier_sha256': p.digest(barrier), 'map_sha256': self.receipt['map_sha256'],
                    'before': self.plan['local_before'], 'controls': {provider: {'automatic_use_stopped': False} for provider in ('opus', 'sol')}}
        (self.work / 'findings.json').write_bytes(p.canonical(findings))
        event = self.plan['events'][0]
        strong = {}
        for provider in ('opus', 'sol'):
            path = self.work / (provider + '.json')
            path.write_bytes(p.canonical({'provider': provider, 'model': p.MODELS[provider][0], 'effort': p.MODELS[provider][1],
                'event': event['event'], 'evidence_id': 'new-cue', 'grounded_confirmed': True, 'status': 'completed',
                'actual_attachment_receipt': {'received': True, 'image_sha256s': [self.image_hash]}}))
            strong[provider] = {'path': str(path), 'sha256': p.digest(path)}
        check = {'event': event['event'], 'evidence_id': 'new-cue', 'verified': True, 'grounded': True,
                 'processed_evidence': {'path': str(self.image), 'sha256': self.image_hash},
                 'confirmed_by': ['opus', 'sol'], 'strong_receipts': strong}
        verification = {'unblind_barrier_sha256': p.digest(barrier), 'map_sha256': self.receipt['map_sha256'], 'checks': [check]}
        path = self.work / 'verification.json'; path.write_bytes(p.canonical(verification))
        ref = {'path': str(path), 'sha256': p.digest(path)}
        contribution = {'event': event['event'], 'clip': event['clip'], 'kind': 'veto_change', 'before': 'keep', 'after': 'veto',
                        'evidence_id': 'new-cue', 'verified': True, 'strong_confirmed': True, 'new_evidence': True}
        del check['strong_receipts']['sol']
        path.write_bytes(p.canonical(verification)); ref['sha256'] = p.digest(path)
        with self.assertRaisesRegex(p.PanelError, 'actual strong confirmation receipts'):
            scoring.record_after(self.work, [contribution], ref)
        check['strong_receipts']['sol'] = strong['sol'] if 'sol' in strong else {'path': str(self.work / 'sol.json'), 'sha256': p.digest(self.work / 'sol.json')}
        path.write_bytes(p.canonical(verification)); ref['sha256'] = p.digest(path)
        report = scoring.record_after(self.work, [contribution], ref)
        self.assertEqual((report['verified_changes'], report['different_clip_count']), (1, 1))
        self.assertTrue(report['all_findings_preserved'])
        known = {**contribution, 'kind': 'known_failure_description', 'evidence_id': 'known-ocr', 'new_evidence': False}
        self.assertEqual(budget.pilot_value([{**known, 'counts_as_contribution': False}], 12, all_comparisons_interpretable=True), 'STOP_RECURRING_KEEP_FINAL')



    def test_utility_controls_charge_special_pool_and_stop_on_reversed_contradiction(self):
        x, y = 'a' * 32, 'b' * 32
        starts, answers, refs = [], [], []
        for index, (items, winner) in enumerate([([x, x], 'tie'), ([x, y], 'A'), ([y, x], 'B')]):
            start = {'provider': 'sol', 'model': 'gpt-6.1-sol', 'effort': 'xhigh', 'grader_identity': 'fresh-' + str(index), 'start_id': p.token(), 'items': items}
            starts.append(start)
            answers.append({'version': 2, 'start_id': start['start_id'], 'grader_identity': start['grader_identity'], 'items': items, 'utility': winner, 'evidence': [items[0]]})
            path = self.work / ('attempt-' + str(index) + '.json')
            path.write_bytes(p.canonical({'attempt_id': str(index), 'provider': 'sol', 'model': 'gpt-6.1-sol', 'effort': 'xhigh',
                'pool': 'special', 'units': 1, 'status': 'completed', 'valid_reference': True, 'actual_attachment_receipt': {'received': True}}))
            refs.append({'path': str(path), 'sha256': p.digest(path)})
        report = scoring.record_utility_controls(self.work / 'pair-valid.json', 'sol', answers, starts, refs)
        self.assertTrue(report['passed'])
        wrong = copy.deepcopy(answers); wrong[1]['items'] = [y, x]
        with self.assertRaisesRegex(p.PanelError, 'comparison identity'):
            scoring.record_utility_controls(self.work / 'pair-wrong-source.json', 'sol', wrong, starts, refs)
        answers[-1]['utility'] = 'A'
        report = scoring.record_utility_controls(self.work / 'pair-invalid.json', 'sol', answers, starts, refs)
        self.assertTrue(report['automatic_use_stopped'])
        fake = p.load(refs[0]['path']); fake['pool'] = 'pilot'
        Path(refs[0]['path']).write_bytes(p.canonical(fake)); refs[0]['sha256'] = p.digest(refs[0]['path'])
        with self.assertRaisesRegex(p.PanelError, 'actual shared-special-pool'):
            scoring.record_utility_controls(self.work / 'pair-free.json', 'sol', answers, starts, refs)


class PanelBudget(unittest.TestCase):
    def state(self):
        s = budget.initial(); s['historical_elapsed_seconds'] = 0
        s = budget.start_phase(s, 'pilot', 0, 10000)
        s['capability']['sol'] = {'received': True, 'image_sha256': 'synthetic'}
        return s

    def reserve(self, s, name='a', units=1, **changes):
        args = {'model': 'gpt-6.1-sol', 'effort': 'xhigh', 'quota_ok': True, 'controls_interpretable': True, 'projected_finish': 10}
        args.update(changes)
        args['item_ids'] = [name + '-' + str(i) for i in range(units)]
        return budget.reserve_attempt(s, 'sol', 'pilot', name, units, 1, **args)

    def test_six_historical_debits_reserves_and_no_fake_usage(self):
        s = budget.initial(); c = budget.counts(s)
        self.assertEqual((c['strong_remaining'], c['special_remaining'], c['final_strong_reserved']), (214, 14, 48))
        self.assertEqual(c['provider_used'], {'opus': 0, 'sol': 6, 'luna': 0})
        self.assertTrue(all(a['latency_seconds'] is None and a['usage'] is None and not a['valid_reference'] for a in s['attempts']))
        self.assertIsNone(budget.project(s, {'sol': 1}, 0))

    def test_logical_bundles_attempts_failure_and_provider_concurrency(self):
        s = self.reserve(self.state(), units=2)
        self.assertEqual(budget.counts(s)['strong_used'], 8)
        with self.assertRaisesRegex(p.PanelError, 'concurrency'):
            self.reserve(s, 'b')
        s = budget.complete_attempt(s, 'a', 5, status='timeout', attachment_receipt=None, controls_pass=None)
        self.assertEqual(budget.counts(s)['strong_used'], 8)
        with self.assertRaisesRegex(p.PanelError, 'replay'):
            self.reserve(s)
        with self.assertRaisesRegex(p.PanelError, 'substitution'):
            self.reserve(s, 'b', effort='ultra')
        with self.assertRaisesRegex(p.PanelError, 'pool exhausted'):
            self.reserve(s, 'b', units=27)

    def test_stop_caps_projection_quota_controls_and_final_time_reserve(self):
        s = self.state()
        self.assertEqual(budget.stop_reason(s, 7200, True, True, 7300, 10000), 'pilot_time_cap')
        self.assertEqual(budget.stop_reason(s, 1, False, True, 2, 10000), 'quota_failure_or_unavailable')
        self.assertEqual(budget.stop_reason(s, 1, True, False, 2, 10000), 'uninterpretable_controls')
        self.assertEqual(budget.stop_reason(s, 1, True, True, None, 10000), 'projection_or_freeze_unavailable')
        self.assertEqual(budget.stop_reason(s, 1, True, True, 10001, 10000), 'missed_freeze')
        s['elapsed']['conditional'] = 3600; s['elapsed']['checkpoints'] = 1800
        s['elapsed']['pilot'] = 7200; s['phase'] = None
        self.assertEqual(budget.stop_reason(s, 1, True, True, 2, 10000), 'final_2h_reserved')

    def test_zero_one_two_different_clip_changes_and_uncertain_stop(self):
        def contribution(event, clip):return {'event': event, 'clip': clip, 'kind': 'veto_change', 'verified': True,
            'strong_confirmed': True, 'new_evidence': True, 'counts_as_contribution': True}
        a, b = contribution('a', 'clip1'), contribution('b', 'clip2')
        self.assertEqual(budget.pilot_value([], 12, all_comparisons_interpretable=True), 'STOP_RECURRING_KEEP_FINAL')
        self.assertEqual(budget.pilot_value([a], 12, all_comparisons_interpretable=True), 'extend_four')
        self.assertEqual(budget.pilot_value([a], 16, extension=True, all_comparisons_interpretable=True), 'STOP_RECURRING_KEEP_FINAL')
        self.assertEqual(budget.pilot_value([a, b], 12, all_comparisons_interpretable=True), 'conditional')
        b['clip'] = 'clip1'
        self.assertEqual(budget.pilot_value([a, b], 12, all_comparisons_interpretable=True), 'STOP_RECURRING_KEEP_FINAL')
        self.assertEqual(budget.pilot_value([], 12), 'STOP_INCOMPLETE_KEEP_FINAL')

    def labels(self):
        return [{'event': str(i), 'label': 'present' if i < 20 else 'absent_in_sample', 'dataset_sha256': pack.SPENT_V1_SHA256,
                 'strong_verified': True, 'variant': 'natural'} for i in range(40)]

    def locked(self):
        s = budget.initial(); s['value_gate'] = 'conditional'
        return budget.begin_locked(budget.revise_prompt(s, 'a' * 64), self.labels(), 'a' * 64)

    def test_single_revision_locked_check_no_rescue_and_all_abstain_fails(self):
        s = self.locked()
        with self.assertRaises(p.PanelError):budget.revise_prompt(s, 'b' * 64)
        result = budget.locked_result(s, {str(i): 'uncertain' for i in range(40)}, True)
        self.assertEqual(result['locked_result'], 'FAIL_END_TUNING')
        self.assertEqual(result['locked_metrics']['negative_escalations'], 20)
        with self.assertRaisesRegex(p.PanelError, 'no rescue'):
            budget.locked_result(result, {str(i): 'absent_in_sample' for i in range(40)}, True)
        answers = {str(i): 'present' if i < 20 else 'absent_in_sample' for i in range(40)}
        self.assertEqual(budget.locked_result(s, answers, True)['locked_result'], 'PASS')
        answers['0'] = 'absent_in_sample'
        self.assertEqual(budget.locked_result(s, answers, True)['locked_metrics']['false_clears'], 1)
        s = budget.initial(); s['value_gate'] = 'conditional'; s = budget.revise_prompt(s, 'a' * 64)
        self.assertEqual(budget.begin_locked(s, [], 'a' * 64)['locked_result'], 'SKIP_MISSING_DATA')

    def test_actual_attachment_capability_and_observed_shared_quota_projection(self):
        s = self.state(); s['capability']['sol'] = None
        with self.assertRaisesRegex(p.PanelError, 'actual image'):
            self.reserve(s)
        s = self.reserve(s, attachment_control=True, projected_finish=None)
        s = budget.complete_attempt(s, 'a', 5, status='completed', attachment_receipt={'received': True, 'image_sha256': 'synthetic'}, controls_pass=True)
        self.assertIsNotNone(s['capability']['sol'])
        self.assertEqual(budget.project(s, {'sol': 2}, 10), 26)
        self.assertEqual(s['clean']['sol'], 1)
        with self.assertRaisesRegex(p.PanelError, 'historical elapsed'):
            budget.start_phase(budget.initial(), 'pilot', 0, 10000)

    def test_checkpoint_audits_cannot_be_free_and_final_cannot_repeat(self):
        s = self.state(); s['checkpoint_ids'] = ['first', 'second']
        with self.assertRaisesRegex(p.PanelError, 'four random-clear'):
            budget.close_checkpoints(s, [], [])
        s = budget.end_phase(s, 10)
        s = budget.start_phase(s, 'final', 20, 10000, 'a' * 64)
        with self.assertRaisesRegex(p.PanelError, 'Luna'):
            budget.reserve_attempt(s, 'luna', 'final', 'luna-final', 1, 21, model='gpt-6-luna', effort='medium', quota_ok=True, controls_interpretable=True, projected_finish=30, attachment_control=True, item_ids=['x'])
        s = budget.end_phase(s, 30)
        with self.assertRaisesRegex(p.PanelError, 'one-shot'):
            budget.start_phase(s, 'final', 40, 10000, 'a' * 64)

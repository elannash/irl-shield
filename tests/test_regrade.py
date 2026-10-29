"""Retrospective quality must not misalign truth or retain stale units."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from bench import regrade


class RetainedQuality(unittest.TestCase):
    def setUp(self):
        scratch=Path('/tmp/agents/irl-shield/m1-regrade-tests')
        scratch.mkdir(parents=True,exist_ok=True)
        self.folder=tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name)
        (self.root/'bench').mkdir()
        for name in ('metrics.py','scoring.py'):
            shutil.copyfile(Path('bench')/name,self.root/'bench'/name)
        (self.root/'bench/baseline.json').write_text(json.dumps({
            'run_id':'literal-reference','natural':{'hidden_fraction':.5},
            'synthetic':{'hidden_fraction':1.}}))

    def write_source(self,evidence,truth,*,synthetic=False):
        source=self.root/'out/source'
        source.mkdir(parents=True)
        row={'clip':'one','synthetic_variant':synthetic,
             'synthetic_input_control':{'total':1 if synthetic else 0,'unreadable':0}}
        card={'run_id':'source','clips':[row],'gate_1':{},'real_video_pass':True,
              'quality_checks':{'protected':True,'masked_area':None},
              'baseline_deltas_pp':{'natural':50.,'synthetic':None}}
        (source/'scorecard.json').write_text(json.dumps(card))
        label='one-synthetic' if synthetic else 'one-natural'
        (source/f'{label}-masked.evidence.json').write_text(json.dumps(evidence))
        (source/f'{label}-input.truth.json').write_text(json.dumps(truth))

    def run_regrade(self):
        with patch.object(regrade,'ROOT',self.root), \
             patch.object(sys,'argv',['regrade','source']),contextlib.redirect_stdout(io.StringIO()):
            regrade.main()

    def test_changed_score_recomputes_percentage_point_deltas_and_unknowns(self):
        reading={'text':'CEDAR AVE','box':[0,0,100,20],'confidence':.99}
        evidence={'input_readings':[[reading],[reading]],'raw_input_readings':[[reading],[reading]],
                  'output_readings':[[],[reading]],'guards':[{'pass':True}]*2}
        self.write_source(evidence,[[],[]])
        self.run_regrade()
        card=json.loads((self.root/'out/regraded-source/scorecard.json').read_text())
        self.assertEqual(card['natural']['hidden_fraction'],0.)
        self.assertEqual(card['baseline_deltas_pp'],{'natural':-50.,'synthetic':None})
        self.assertEqual(card['baseline_reference']['run_id'],'literal-reference')
        self.assertFalse(card['gate_1']['eligible'])

    def test_clocked_truth_rotation_is_rejected_before_creating_a_receipt(self):
        left={'id':'A','text':'9 MAIN','box':[0,0,30,20],'visible':True}
        right={**left,'box':[100,0,130,20]}
        broad={'text':'9 MAIN','box':[0,0,130,20],'confidence':.99}
        leak={**broad,'box':right['box']}
        evidence={'input_readings':[[broad],[broad]],'raw_input_readings':[[broad],[broad]],
                  'output_readings':[[leak],[]],'guards':[{'pass':True}]*2,
                  'quality_window':{'original_start_frame':1,'source_frame_count':2},
                  'presentation':[{'frame':0,'source_frame':1},{'frame':1,'source_frame':0}]}
        self.write_source(evidence,[[left],[right]],synthetic=True)
        with self.assertRaisesRegex(ValueError,'[Cc]locked|windowed'):
            self.run_regrade()
        self.assertFalse((self.root/'out/regraded-source').exists())


if __name__=='__main__':
    unittest.main()

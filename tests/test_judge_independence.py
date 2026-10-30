"""Independent-family truth, all-judge leaks and retained pooled diagnostics."""
import unittest
from bench.scoring import score_records
from bench.independence import policy_metadata, candidate_metadata


class IndependentJudging(unittest.TestCase):
    def test_pp_family_cannot_create_truth_or_positive_input_controls(self):
        independent={'text':'ELM ROAD','box':[0,0,80,20],'confidence':.99,'judge':'tesseract'}
        own={'text':'CEDAR AVE','box':[100,0,180,20],'confidence':.99,'judge':'ppocr-independent'}
        label={'id':'plate','text':'BXR219','box':[200,0,280,20],'visible':True}
        own_label={**label,'confidence':.99,'judge':'ppocr-independent'}
        quality,details=score_records([[independent,own,own_label]]*2,
            [[{**independent,'judge':'ppocr-independent'}],[]],[[label]]*2,[{'pass':True}]*2,
            detector_families=['paddleocr'])
        self.assertEqual(quality['natural'],{'hidden':0,'total':1,'hidden_fraction':0.})
        self.assertEqual(quality['synthetic_input_control'],{'total':1,'unreadable':1})
        self.assertEqual(quality['pooled_not_independent']['natural']['total'],2)
        self.assertEqual(quality['pooled_not_independent']['natural']['hidden'],1)
        self.assertEqual(details['natural'][0]['text'],'ELM ROAD')
        self.assertEqual(details['raw_input_readings'][0],[independent,own,own_label])
        self.assertEqual(quality['judge_independence']['included_judges'],['tesseract','vision-accurate'])

    def test_same_family_only_output_reading_still_leaks_independent_truth(self):
        target={'text':'ELM ROAD','box':[0,0,80,20],'confidence':.99,'judge':'tesseract'}
        output={**target,'judge':'ppocr-independent'}
        quality,details=score_records([[target]]*2,[[output],[]],[[],[]],
            [{'pass':True}]*2,detector_families=['paddleocr'])
        self.assertEqual(quality['natural'],{'hidden':0,'total':1,'hidden_fraction':0.})
        self.assertTrue(details['natural'][0]['leaked'])
        self.assertEqual(details['natural'][0]['leak_frames'],[0])

    def test_vision_and_mixed_policies_exclude_every_lane_family(self):
        rows=[{'text':text,'box':[i*100,0,i*100+80,20],'confidence':.99,'judge':judge}
              for i,(judge,text) in enumerate([('tesseract','ELM ROAD'),('vision-accurate','CEDAR AVE'),('ppocr-independent','PINE STREET')])]
        vision,_=score_records([rows]*2,[[],[]],[[],[]],[{'pass':True}]*2,detector_families=['apple-vision'])
        self.assertEqual(vision['natural']['total'],2)
        mixed,_=score_records([rows]*2,[[],[]],[[],[]],[{'pass':True}]*2,detector_families=['apple-vision','paddleocr'])
        self.assertEqual(mixed['natural']['total'],1)
        self.assertEqual(mixed['judge_independence']['included_judges'],['tesseract'])
        self.assertFalse(mixed['judge_independence']['sufficient_independent_engines'])
        self.assertIn('only one',mixed['judge_independence']['warning'])

    def test_unidentified_readings_cannot_silently_enter_independent_truth(self):
        row={'text':'ELM ROAD','box':[0,0,80,20],'confidence':.99,'judge':'unregistered-reader'}
        with self.assertRaisesRegex(ValueError,'judge family'):
            score_records([[row]]*2,[[],[]],[[],[]],[{'pass':True}]*2,detector_families=['paddleocr'])


class DeclaredProvenance(unittest.TestCase):
    def test_lane_union_is_declared_and_unknown_candidates_do_not_use_name_heuristics(self):
        policy=policy_metadata('ppocr-v6-small',{'fast_candidate':'vision-rectangles'})
        self.assertEqual(policy['detector_families'],['apple-vision','paddleocr'])
        for candidate,fast in [('ppocr-v6-small','ppocr-v6-tiny'),('vision-union','vision-rectangles')]:
            self.assertEqual(policy_metadata(candidate,{})['lanes']['fast'],candidate_metadata(fast))
        with self.assertRaisesRegex(ValueError,'declared detector families'):
            candidate_metadata('ppocr-unknown-candidate')

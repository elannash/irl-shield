from shield.masking import masked_frame
import unittest
import numpy as np

from bench.metrics import fidelity, readable, truth_from_readings
from bench.scoring import intervals


class PrivacyScoring(unittest.TestCase):
    def test_one_leaking_frame_fails_whole_interval_including_ocr_gap(self):
        a={'text':'CEDAR AVE','box':[10,20,110,50]}
        tracks=intervals([[a],[],[a]],[[],[a],[]],False)
        self.assertEqual(len(tracks),1)
        self.assertTrue(tracks[0]['leaked'])
        self.assertEqual(tracks[0]['leak_frames'],[1])

    def test_known_synthetic_visibility_gaps_start_new_intervals(self):
        label={'id':'same-label','text':'9 MAIN','visible':True,'box':[0,0,100,20]}
        invisible={**label,'visible':False}
        tracks=intervals([[label],[label],[invisible],[label],[label]],
                         [[],[],[label],[],[label]],True)
        self.assertEqual([(t['first'],t['last'],t['leaked']) for t in tracks],
                         [(0,1,False),(3,4,True)])
        self.assertEqual(tracks[0]['leak_frames'],[])
        self.assertEqual(tracks[1]['leak_frames'],[4])

    def test_separate_repeated_occurrences_cannot_shrink_failed_denominator(self):
        a={'text':'MARKET','box':[0,0,100,20]}
        b={'text':'MARKET','box':[1000,500,1100,520]}
        names=['ALPHA','BRAVO','CHARLIE','DELTA','ECHO','FOXTROT','GOLF','HOTEL','INDIA']
        hidden=[{'text':name,'box':[200*i,100,200*i+100,120]} for i,name in enumerate(names)]
        tracks=intervals([[a]+hidden,[a]+hidden,[],[b],[b]],[[a],[],[],[b],[]],False)
        self.assertEqual(len(tracks),11)
        self.assertEqual(sum(not t['leaked'] for t in tracks),9)

    def test_long_ocr_gap_still_checks_every_intermediate_frame(self):
        a={'text':'CEDAR AVE','box':[0,0,100,20]}
        tracks=intervals([[a],[],[],[],[a]],[[],[],[a],[],[]],False)
        self.assertEqual(len(tracks),1)
        self.assertEqual(tracks[0]['leak_frames'],[2])

    def test_moving_gap_interpolates_geometry(self):
        a={'text':'CEDAR AVE','box':[0,0,100,20]}
        b={'text':'CEDAR AVE','box':[90,0,190,20]}
        leak={'text':'AVE','box':[110,0,145,20]}
        tracks=intervals([[a],[],[b]],[[],[leak],[]],False)
        self.assertEqual(tracks[0]['leak_frames'],[1])

    def test_dedup_preserves_longer_judge_reading(self):
        word={'text':'CEDAR','box':[0,0,60,20]}
        line={'text':'CEDAR AVE','box':[0,0,100,20]}
        truth=truth_from_readings([word,line])
        self.assertEqual([t['text'] for t in truth],['CEDAR AVE'])
        self.assertTrue(readable(truth[0],[{'text':'AVE','box':[65,0,100,20]}]))

    def test_small_fragment_and_single_digit_are_leaks(self):
        self.assertTrue(readable({'text':'123 BROADWAY NEW YORK','box':[0,0,1000,20]},
                                 [{'text':'123','box':[0,0,40,20]}]))
        digit={'text':'7','box':[0,0,10,20]}
        self.assertEqual(truth_from_readings([digit]),[digit])
        self.assertTrue(readable(digit,[digit]))
        self.assertTrue(readable(digit,[{'text':'7 MAIN ST','box':[0,0,150,20]}]))
        self.assertTrue(readable(digit,[{'text':'7MAIN','box':[0,0,150,20]}]))
        self.assertFalse(readable(digit,[{'text':'1847','box':[0,0,150,20]}]))
        self.assertFalse(readable(digit,[{'text':'1847MAIN','box':[0,0,150,20]}]))

    def test_same_word_different_signs_remain_separate(self):
        a={'text':'MARKET','box':[10,20,110,50]}
        b={'text':'MARKET','box':[400,20,500,50]}
        tracks=intervals([[a,b],[a,b]],[[a],[]],False)
        self.assertEqual([t['leaked'] for t in tracks],[True,False])

    def test_slate_and_all_mask_fail_even_without_leaks(self):
        image=np.indices((120,160)).sum(axis=0).astype(np.uint8)
        image=np.repeat(image[:,:,None],3,axis=2)
        black=np.zeros_like(image)
        self.assertFalse(fidelity(image,black,np.zeros((120,160),np.uint8))['pass'])
        self.assertFalse(fidelity(image,black,np.full((120,160),255,np.uint8))['pass'])
        self.assertTrue(fidelity(image,image,np.zeros((120,160),np.uint8))['pass'])

    def test_one_failed_live_guard_zeroes_both_primary_credits_at_both_scoring_entries(self):
        from bench.scoring import score_records
        from bench.clocked_bench import score_observations
        natural={'text':'ELM ROAD','box':[0,0,80,20],'confidence':.99,'judge':'tesseract'}
        label={'id':'plate','text':'BXR219','box':[100,0,180,20],'visible':True}
        inputs=[[natural,{**label,'confidence':.99,'judge':'tesseract'}]]*3
        truth=[[label]]*3
        records=[{'state':s,'protected':s!='LIVE','slate':False} for s in ('LIVE','PROTECT','LIVE')]
        for entry in ('score_records','score_observations'):
            with self.subTest(entry=entry):
                if entry=='score_records':
                    quality,_=score_records(inputs,[[],[],[]],truth,[{'pass':True},{'pass':False}],detector_families=[])
                else:
                    quality,_=score_observations(inputs,[[],[],[]],truth,[{'pass':True},None,{'pass':False}],records,detector_families=[])
                self.assertFalse(quality['real_video_pass'])
                self.assertEqual(quality['natural']['total'],1)
                self.assertEqual(quality['synthetic']['total'],1)
                self.assertEqual(quality['natural']['hidden'],0)
                self.assertEqual(quality['synthetic']['hidden'],0)

    def test_padding_area_uses_union_and_preserves_outside_pixels(self):
        source=np.full((100,100,3),127,np.uint8)
        output,mask=masked_frame(source,[[10,10,30,30],[20,10,40,30]],0)
        self.assertEqual(int((mask>0).sum()),36*26)
        np.testing.assert_array_equal(output[mask==0],source[mask==0])
        self.assertTrue((output[mask>0]==0).all())

    def test_judge_union_detects_partial_text_in_target_region(self):
        self.assertTrue(readable({'text':'CEDAR AVE','box':[0,0,100,20]},
                                 [{'text':'CEDAR','box':[0,0,60,20]}]))
        self.assertFalse(readable({'text':'CEDAR AVE','box':[0,0,100,20]},
                                  [{'text':'CEDAR','box':[500,0,560,20]}]))


if __name__=='__main__':
    unittest.main()

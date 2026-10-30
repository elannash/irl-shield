"""Retained lane provenance must agree with the model registry before grading."""
import copy
import unittest

from bench.clocked_bench import recorded_policy_metadata


class RecordedFamilyGuards(unittest.TestCase):
    def receipt(self):
        return {'candidate': 'vision-accurate', 'options': {'fast_candidate': 'ppocr-v6-tiny'},
                'loading': {
                    'accurate': {'candidate': 'vision-accurate',
                                 'metadata': {'detector_families': ['apple-vision']}},
                    'fast': {'candidate': 'ppocr-v6-tiny',
                             'metadata': {'detector_families': ['paddleocr']}}}}

    def test_recorded_family_mismatch_is_rejected_in_each_lane(self):
        receipt = self.receipt()
        expected = {'lanes': {'accurate': {'detector_families': ['apple-vision']},
                              'fast': {'detector_families': ['paddleocr']}},
                    'detector_families': ['apple-vision', 'paddleocr']}
        self.assertEqual(recorded_policy_metadata(receipt), expected)
        for lane, wrong_family in (('fast', 'apple-vision'), ('accurate', 'paddleocr')):
            with self.subTest(lane=lane):
                damaged = copy.deepcopy(receipt)
                damaged['loading'][lane]['metadata']['detector_families'] = [wrong_family]
                with self.assertRaisesRegex(ValueError, 'inconsistent recorded ' + lane + ' lane provenance'):
                    recorded_policy_metadata(damaged)

    def test_missing_recorded_accurate_lane_cannot_receive_policy_metadata(self):
        receipt = self.receipt()
        del receipt['loading']['accurate']
        with self.assertRaisesRegex(ValueError, 'inconsistent recorded accurate lane provenance'):
            recorded_policy_metadata(receipt)


if __name__ == '__main__':
    unittest.main()

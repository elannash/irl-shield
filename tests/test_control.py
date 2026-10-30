import unittest

from shield.control import Control


class ProtectionControl(unittest.TestCase):
    def test_hold_overrides_coverage_and_release_restores_current_coverage(self):
        control = Control()
        self.assertEqual((control.state, control.reason), ('PROTECT', 'startup'))
        self.assertEqual(control.transitions, [])
        self.assertEqual(control.update_coverage(True, 'fresh', at=10), 'LIVE')
        self.assertEqual(control.set_hold(True, reason='manual', at=11), 'HOLD')
        self.assertEqual(control.set_hold(True, reason='manual', at=11.5), 'HOLD')
        self.assertEqual(control.update_coverage(False, 'accurate-stale', at=12), 'HOLD')
        self.assertEqual(control.reason, 'manual')
        self.assertEqual(control.set_hold(False, at=13), 'PROTECT')
        self.assertEqual(control.reason, 'accurate-stale')
        self.assertEqual(control.update_coverage(True, 'recovered', at=14), 'LIVE')
        self.assertEqual(control.transitions, [
            {'from': 'PROTECT', 'to': 'LIVE', 'reason': 'fresh', 'at': 10},
            {'from': 'LIVE', 'to': 'HOLD', 'reason': 'manual', 'at': 11},
            {'from': 'HOLD', 'to': 'PROTECT', 'reason': 'accurate-stale', 'at': 13},
            {'from': 'PROTECT', 'to': 'LIVE', 'reason': 'recovered', 'at': 14},
        ])

    def test_each_hold_source_must_release_before_coverage_can_resume_video(self):
        control = Control()
        self.assertEqual(control.set_hold(True, source='local', reason='manual', at=1), 'HOLD')
        self.assertEqual(control.set_hold(True, source='chat', reason='moderator', at=2), 'HOLD')
        self.assertEqual(control.reason, 'moderator')
        self.assertEqual(control.update_coverage(False, 'accurate-stale', at=3), 'HOLD')
        self.assertEqual(control.set_hold(False, source='local', at=4), 'HOLD')
        self.assertEqual(control.reason, 'moderator')
        self.assertEqual(control.set_hold(False, source='unknown', at=5), 'HOLD')
        self.assertEqual(control.update_coverage(True, 'fresh', at=6), 'HOLD')
        self.assertEqual(control.set_hold(False, source='chat', at=7), 'LIVE')
        self.assertEqual(control.set_hold(False, source='chat', at=8), 'LIVE')
        self.assertEqual(control.transitions, [
            {'from': 'PROTECT', 'to': 'HOLD', 'reason': 'manual', 'at': 1},
            {'from': 'HOLD', 'to': 'LIVE', 'reason': 'fresh', 'at': 7},
        ])

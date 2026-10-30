import unittest

from shield.skins import ChatEvent, SkinVotes


class SkinVoting(unittest.TestCase):
    def event(self, id, user, text, timestamp, roles=()):
        return ChatEvent(id, user, frozenset(roles), text, timestamp)

    def test_plurality_replacement_incumbent_ties_and_exact_expiry(self):
        votes = SkinVotes(100)
        self.assertEqual(votes.apply(self.event('1', 'a', '!skin bar', 101), now=101)['skin'], 'bar')
        result = votes.apply(self.event('2', 'b', '!skin signed', 102), now=102)
        self.assertEqual(result['skin'], 'bar')
        result = votes.apply(self.event('3', 'a', '!skin signed', 103), now=103)
        self.assertEqual(result, {'skin': 'signed', 'skin_locked': False, 'votes': {'signed': 2}})
        self.assertEqual(votes.snapshot(162)['votes'], {'signed': 1})
        self.assertEqual(votes.snapshot(163)['votes'], {})
        self.assertEqual(votes.snapshot(164)['skin'], 'signed')

    def test_locks_allow_votes_and_only_authenticated_mod_or_broadcaster_controls(self):
        votes = SkinVotes(0)
        result = votes.apply(self.event('1', 'mod', '!skin lock signed', 1, ['moderator']), now=1)
        self.assertTrue(result['skin_locked'])
        votes.apply(self.event('2', 'a', '!skin bar', 2), now=2)
        votes.apply(self.event('3', 'b', '!skin bar', 3), now=3)
        result = votes.apply(self.event('4', 'a', '!skin unlock', 4), now=4)
        self.assertEqual(result, {'skin': 'signed', 'skin_locked': True, 'votes': {'bar': 2}})
        result = votes.apply(self.event('5', 'owner', '!skin unlock', 5, ['broadcaster']), now=5)
        self.assertEqual(result['skin'], 'bar')
        self.assertFalse(result['skin_locked'])

    def test_replays_session_staleness_out_of_order_and_malicious_commands(self):
        votes = SkinVotes(100)
        votes.apply(self.event('1', 'a', '!skin bar', 120), now=120)
        attacks = [self.event('1', 'a', '!skin signed', 121),
                   self.event('2', 'a', '!skin signed', 119),
                   self.event('3', 'b', '!skin signed', 99),
                   self.event('4', 'b', '!skin signed', 181),
                   self.event('5', 'b', '!skin lock signed', 121),
                   self.event('6', 'b', '!skin signed\n!skin lock bar', 121),
                   self.event('7', 'b', '!skin bar\x00', 121),
                   self.event('8', 'b', '!skin ｂａｒ', 121),
                   self.event('9', 'b', '!skin lock signed moderator', 121),
                   self.event('10', 'b', '!skin ../signed', 121),
                   self.event('11', 'b', '!skin signed', float('nan'))]
        for attack in attacks:
            result = votes.apply(attack, now=121)
            self.assertEqual(result, {'skin': 'bar', 'skin_locked': False, 'votes': {'bar': 1}})
        self.assertEqual(votes.snapshot(180)['votes'], {})
        with self.assertRaises(ValueError):
            votes.snapshot(179)

    def test_tie_without_incumbent_is_lexical_and_expiration_can_change_winner(self):
        votes = SkinVotes(0)
        votes.apply(self.event('1', 'a', '!skin signed', 1), now=1)
        votes.apply(self.event('2', 'b', '!skin bar', 2), now=2)
        votes.apply(self.event('3', 'c', '!skin patch', 3), now=3)
        # signed expires, leaving bar and patch tied without the incumbent.
        self.assertEqual(votes.snapshot(61)['skin'], 'bar')

    def test_session_dedup_survives_expiry_and_stale_mod_cannot_unlock_newer_lock(self):
        votes = SkinVotes(0)
        votes.apply(self.event('seen', 'a', '!skin bar', 1), now=1)
        self.assertEqual(votes.apply(self.event('seen', 'a', '!skin signed', 62), now=62)['votes'], {})
        votes.apply(self.event('new', 'mod', '!skin lock signed', 63, ['moderator']), now=63)
        result = votes.apply(self.event('old', 'mod', '!skin unlock', 62, ['moderator']), now=64)
        self.assertEqual(result, {'skin': 'signed', 'skin_locked': True, 'votes': {}})


if __name__ == '__main__':
    unittest.main()

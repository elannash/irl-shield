import unittest

from shield.skins import ChatEvent, SkinVotes


class SkinVoting(unittest.TestCase):
    def event(self, id, user, text, timestamp, roles=()):
        return ChatEvent(id, user, frozenset(roles), text, timestamp)

    def test_chat_votes_and_locks_exclude_every_unqualified_material(self):
        for skin in ('frosted', 'signed', 'patch', 'petals', 'ripple', 'confetti', 'cloud'):
            for text, roles in (('!skin ' + skin, ()),
                                ('!skin lock ' + skin, ('moderator',))):
                with self.subTest(skin=skin, text=text):
                    votes = SkinVotes(0)
                    result = votes.apply(self.event('unqualified', 'viewer', text, 1, roles), now=1)
                    self.assertEqual(result, {'skin': 'bar', 'skin_locked': False, 'votes': {}},
                                     'Chat must not select a material without a passing native receipt')
        votes = SkinVotes(0, incumbent='frosted')
        self.assertEqual(votes.snapshot(0)['skin'], 'frosted', 'Explicit configuration remains selectable')
        self.assertEqual(votes.apply(self.event('vote', 'viewer', '!skin bar', 1), now=1)['votes'], {'bar': 1})
        self.assertTrue(votes.apply(self.event('lock', 'mod', '!skin lock bar', 2,
                                              ['moderator']), now=2)['skin_locked'])
        for removed in ('petals', 'ripple', 'confetti', 'cloud'):
            with self.assertRaises(ValueError):
                SkinVotes(0, incumbent=removed)

    def test_votes_replace_configured_material_without_double_counting_and_expire(self):
        votes = SkinVotes(100, incumbent='frosted')
        self.assertEqual(votes.apply(self.event('1', 'a', '!skin bar', 101), now=101)['skin'], 'bar')
        self.assertEqual(votes.apply(self.event('2', 'a', '!skin bar', 102), now=102)['votes'], {'bar': 1})
        self.assertEqual(votes.apply(self.event('3', 'b', '!skin bar', 103), now=103)['votes'], {'bar': 2})
        self.assertEqual(votes.snapshot(162)['votes'], {'bar': 1})
        self.assertEqual(votes.snapshot(163)['votes'], {})
        self.assertEqual(votes.snapshot(164)['skin'], 'bar')

    def test_locks_allow_votes_and_only_authenticated_mod_or_broadcaster_controls(self):
        votes = SkinVotes(0)
        result = votes.apply(self.event('1', 'mod', '!skin lock bar', 1, ['moderator']), now=1)
        self.assertTrue(result['skin_locked'])
        votes.apply(self.event('2', 'a', '!skin bar', 2), now=2)
        votes.apply(self.event('3', 'b', '!skin bar', 3), now=3)
        result = votes.apply(self.event('4', 'a', '!skin unlock', 4), now=4)
        self.assertEqual(result, {'skin': 'bar', 'skin_locked': True, 'votes': {'bar': 2}})
        result = votes.apply(self.event('5', 'owner', '!skin unlock', 5, ['broadcaster']), now=5)
        self.assertEqual(result['skin'], 'bar')
        self.assertFalse(result['skin_locked'])

    def test_replays_session_staleness_out_of_order_and_malicious_commands(self):
        votes = SkinVotes(100)
        votes.apply(self.event('1', 'a', '!skin bar', 120), now=120)
        attacks = [self.event('1', 'a', '!skin bar', 121),
                   self.event('2', 'a', '!skin bar', 119),
                   self.event('3', 'b', '!skin bar', 99),
                   self.event('4', 'b', '!skin bar', 181),
                   self.event('5', 'b', '!skin lock bar', 121),
                   self.event('6', 'b', '!skin bar\n!skin lock bar', 121),
                   self.event('7', 'b', '!skin bar\x00', 121),
                   self.event('8', 'b', '!skin ｂａｒ', 121),
                   self.event('9', 'b', '!skin lock bar moderator', 121),
                   self.event('10', 'b', '!skin ../bar', 121),
                   self.event('11', 'b', '!skin bar', float('nan'))]
        for attack in attacks:
            result = votes.apply(attack, now=121)
            self.assertEqual(result, {'skin': 'bar', 'skin_locked': False, 'votes': {'bar': 1}})
        self.assertEqual(votes.snapshot(179)['votes'], {'bar': 1})
        self.assertEqual(votes.snapshot(180)['votes'], {})
        with self.assertRaises(ValueError):
            votes.snapshot(179)

    def test_session_dedup_survives_expiry_and_stale_mod_cannot_unlock_newer_lock(self):
        votes = SkinVotes(0)
        votes.apply(self.event('seen', 'a', '!skin bar', 1), now=1)
        self.assertEqual(votes.apply(self.event('seen', 'a', '!skin bar', 62), now=62)['votes'], {})
        votes.apply(self.event('new', 'mod', '!skin lock bar', 63, ['moderator']), now=63)
        result = votes.apply(self.event('old', 'mod', '!skin unlock', 62, ['moderator']), now=64)
        self.assertEqual(result, {'skin': 'bar', 'skin_locked': True, 'votes': {}})


if __name__ == '__main__':
    unittest.main()

"""Session rules for restarting a room and what a restart preserves.

Run from the repository root:

    python3 -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server as srv  # noqa: E402


class RestartRules(unittest.TestCase):
    def room(self):
        sess = srv.GameSession("alice", "hard", 3)
        sess.players.append("bob")
        sess.players.append("carol")
        sess.start()
        return sess

    def test_host_can_restart_at_any_time(self):
        sess = self.room()
        self.assertTrue(sess.can_restart(0))

    def test_other_captains_wait_until_every_other_game_ends(self):
        sess = self.room()
        sess.games[0].gameOver = True
        self.assertFalse(sess.can_restart(1))  # carol is still playing
        sess.games[2].gameOver = True
        self.assertTrue(sess.can_restart(1))

    def test_restart_resets_progress_and_keeps_the_difficulty(self):
        sess = self.room()
        old_game = sess.games[0]
        sess.games[0].money = 999
        sess.games[1].gameOver = True
        sess.ready.add(0)
        sess.end_votes.add(1)
        sess.restart()
        self.assertEqual(sess.difficulty, "hard")
        self.assertIsNot(sess.games[0], old_game)
        self.assertEqual(sess.games[0].money, 100)
        self.assertEqual(sess.games[0].slot, 1)
        self.assertEqual(sess.ready, set())
        self.assertEqual(sess.end_votes, set())
        self.assertEqual(sess.trade_orders, [])
        self.assertTrue(sess.started)


if __name__ == "__main__":
    unittest.main()

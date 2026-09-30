import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import AutoHomeCycle, finish_collection


class AutoHomeTests(unittest.TestCase):
    def recording(self):
        cycle = AutoHomeCycle(0, episodes=10)
        cycle.step(5, True)
        self.assertEqual(cycle.step(6, True), "begin")
        self.assertEqual(cycle.episode, 11)
        return cycle

    def test_five_second_prep_and_full_one_second_start(self):
        c = AutoHomeCycle(0)
        c.step(4.99, False)
        self.assertEqual(c.state, "PREP")
        c.step(5, False)  # Like legacy, no extra HOME gate before START.
        self.assertEqual(c.state, "START")
        self.assertIsNone(c.step(5.99, False))
        self.assertEqual(c.step(6, False), "begin")

    def test_auto_save_requires_leaving_home_minimum_time_and_stability(self):
        c = self.recording()
        self.assertIsNone(c.step(20, True))  # Never left HOME.
        c.step(21, False)
        c.step(22, True)
        self.assertIsNone(c.step(23.99, True))
        self.assertEqual(c.step(24, True), "save")
        self.assertEqual(c.state, "PREP")
        self.assertEqual(c.episode, 11)
        self.assertEqual(c.remaining(24), 5)

    def test_minimum_eight_seconds_even_when_home_already_stable(self):
        c = self.recording()
        c.step(7, False)
        c.step(8, True)
        self.assertIsNone(c.step(13.99, True))
        self.assertEqual(c.step(14, True), "save")

    def test_discard_precedes_home_save_and_reuses_number_after_ten_seconds(self):
        c = self.recording()
        c.step(7, False)
        c.step(12, True)
        self.assertEqual(c.step(14, True, command="f"), "discard")
        self.assertEqual(c.episode, 10)
        c.step(23.99, True)
        self.assertEqual(c.state, "PREP")
        c.step(24, True)
        self.assertEqual(c.state, "START")
        self.assertEqual(c.step(25, True), "begin")
        self.assertEqual(c.episode, 11)

    def test_quit_at_home_boundary_never_saves(self):
        c = self.recording()
        c.step(7, False)
        c.step(12, True)
        self.assertEqual(c.step(14, True, command="q"), "quit")

    def test_slow_save_blocks_next_start_but_does_not_restart_countdown(self):
        c = self.recording()
        c.step(7, False)
        c.step(12, True)
        c.step(14, True)
        c.step(19, True, save_busy=True)
        self.assertEqual(c.state, "PREP")
        c.step(22, True, save_busy=False)
        self.assertEqual(c.state, "START")
        self.assertEqual(c.step(23, True), "begin")

    def test_failed_frames_persist_until_home_then_discard(self):
        c = self.recording()
        c.step(7, False, failed=True)
        self.assertTrue(c.failed)
        c.step(12, True)
        self.assertEqual(c.step(14, True), "discard")
        self.assertEqual(c.remaining(14), 10)

    def test_timeout_discards_even_without_leaving_home(self):
        c = self.recording()
        self.assertEqual(c.step(96, True), "discard")
        self.assertEqual(c.episode, 10)

    def test_quit_waits_for_save_without_clearing_writer_concurrently(self):
        writing, reopened, journal = Mock(), Mock(), Mock()
        future = Mock()
        def complete():
            writing.clear_episode_buffer.assert_not_called()
            reopened.clear_episode_buffer.assert_not_called()
            return reopened
        future.result.side_effect = complete
        finish_collection(writing, future, True, journal)
        reopened.clear_episode_buffer.assert_called_once()
        reopened.finalize.assert_called_once()
        writing.clear_episode_buffer.assert_not_called()

    def test_failed_save_keeps_pending_marker_and_data(self):
        writer, future, journal = Mock(), Mock(), Mock()
        future.result.side_effect = RuntimeError("disk error")
        with self.assertRaisesRegex(RuntimeError, "disk error"):
            finish_collection(writer, future, True, journal)
        writer.clear_episode_buffer.assert_not_called()
        writer.finalize.assert_called_once()
        journal.unlink.assert_not_called()


if __name__ == "__main__":
    unittest.main()

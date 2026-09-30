import io
import os
import queue
import sys
import tempfile
import tkinter as tk
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import collect


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = collect.CollectionWindow(self.root)

    def tearDown(self):
        self.app.destroy()

    def test_opening_window_never_starts_hardware(self):
        self.assertIsNone(self.app.process)
        self.assertFalse(hasattr(self.app, "save_button"))
        self.assertIn("Pick up the doll", self.app.sentence.get())

    def test_task_selection_updates_sentence_and_destination(self):
        self.app.choice.current(5)
        self.app.refresh()
        self.assertEqual(self.app.sentence.get(), "Stack four boxes.")
        self.assertIn("stack_four", self.app.destination.get())

    def test_buttons_follow_worker_state_and_stop_is_graceful(self):
        process = MagicMock()
        process.poll.return_value = None
        process.stdin = io.StringIO()
        self.app.process = process
        self.app.events.put(("line", "@STATE:RECORDING"))
        self.app.poll()
        self.assertEqual(str(self.app.discard_button["state"]), "normal")
        self.app.send("f")
        self.app.send("q")
        self.assertEqual(process.stdin.getvalue(), "f\nq\n")
        self.assertEqual(str(self.app.discard_button["state"]), "disabled")
        process.kill.assert_not_called()
        process.terminate.assert_not_called()

    def test_launch_failure_keeps_start_available(self):
        with patch("collect.subprocess.Popen", side_effect=OSError("test launch error")):
            self.app.start()
        self.assertIsNone(self.app.process)
        self.assertIn("test launch error", self.app.status.get())
        self.assertEqual(str(self.app.start_button["state"]), "normal")

    def test_start_uses_selected_task_without_shell(self):
        process = MagicMock()
        process.stdout = iter([])
        process.wait.return_value = 0
        with tempfile.TemporaryDirectory() as temp, patch.object(collect, "BASE", Path(temp)), \
             patch("collect.subprocess.Popen", return_value=process) as launch, \
             patch("collect.threading.Thread"):
            self.app.choice.current(2)
            self.app.start()
        args, kwargs = launch.call_args
        self.assertEqual(args[0][3:5], ["--worker", "2"])
        self.assertFalse(kwargs.get("shell", False))
        self.assertEqual(str(self.app.start_button["state"]), "disabled")


class CommandPipeTests(unittest.TestCase):
    def test_open_pipe_does_not_block_stop_and_fragmented_commands(self):
        read_fd, write_fd = os.pipe()
        commands, stopped = queue.Queue(), threading.Event()
        with os.fdopen(read_fd, "rb", buffering=0) as stream:
            listener = threading.Thread(target=collect.receive_commands, args=(commands, stopped, stream))
            listener.start()
            try:
                os.write(write_fd, b"f")
                with self.assertRaises(queue.Empty):
                    commands.get(timeout=0.1)
                os.write(write_fd, b"\n")
                self.assertEqual(commands.get(timeout=2), "f")
                # Stopping must work while the pipe stays open and no line is pending.
                stopped.set()
                listener.join(timeout=2)
                self.assertFalse(listener.is_alive())
            finally:
                stopped.set()
                listener.join(timeout=2)
                os.close(write_fd)

    def test_parent_pipe_close_requests_safe_quit(self):
        read_fd, write_fd = os.pipe()
        commands, stopped = queue.Queue(), threading.Event()
        with os.fdopen(read_fd, "rb", buffering=0) as stream:
            listener = threading.Thread(target=collect.receive_commands, args=(commands, stopped, stream))
            listener.start()
            try:
                os.close(write_fd)
                self.assertEqual(commands.get(timeout=2), "q")
                listener.join(timeout=2)
                self.assertFalse(listener.is_alive())
            finally:
                stopped.set()
                listener.join(timeout=2)


if __name__ == "__main__":
    unittest.main()

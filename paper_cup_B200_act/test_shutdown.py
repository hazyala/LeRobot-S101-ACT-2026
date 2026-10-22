import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from shutdown import close_cameras, shutdown_robot


class ShutdownTests(unittest.TestCase):
    def rig(self, home=True, returned=True):
        safe = SimpleNamespace(read_motor_observation=Mock(return_value={}),
                               is_home=Mock(return_value=home),
                               return_home_and_stabilize=Mock(return_value=returned),
                               cv2=SimpleNamespace(destroyAllWindows=Mock()))
        robot = SimpleNamespace(bus=Mock(is_connected=True), cameras={},
                                config=SimpleNamespace(num_write_retries=2))
        return safe, robot

    def test_home_releases_torque_and_closes_without_second_home_or_prompt(self):
        safe, robot = self.rig()
        with patch('builtins.input', side_effect=AssertionError('No prompt allowed')):
            shutdown_robot(safe, robot, [], [], [], 30, False)
        safe.return_home_and_stabilize.assert_not_called()
        robot.bus.disable_torque.assert_called_once_with(num_retry=2)
        robot.bus.disconnect.assert_called_once_with(disable_torque=False)
        safe.cv2.destroyAllWindows.assert_called_once()

    def test_returns_home_before_releasing_torque(self):
        safe, robot = self.rig(home=False)
        sequence = Mock()
        sequence.attach_mock(safe.return_home_and_stabilize, 'home')
        sequence.attach_mock(robot.bus.disable_torque, 'off')
        shutdown_robot(safe, robot, [], [], [], 30, False)
        self.assertEqual([c[0] for c in sequence.mock_calls], ['home', 'off'])

    def test_failed_home_keeps_torque_and_never_prompts(self):
        safe, robot = self.rig(home=False, returned=False)
        with patch('builtins.input', side_effect=AssertionError('No prompt allowed')):
            with self.assertRaisesRegex(RuntimeError, 'HOME'):
                shutdown_robot(safe, robot, [], [], [], 30, False)
        robot.bus.disable_torque.assert_not_called()
        robot.bus.disconnect.assert_not_called()

    def test_emergency_never_returns_home(self):
        safe, robot = self.rig()
        shutdown_robot(safe, robot, [], [], [], 30, True)
        safe.read_motor_observation.assert_not_called()
        safe.return_home_and_stabilize.assert_not_called()
        robot.bus.disable_torque.assert_called_once()

    def test_camera_shutdown_has_bounded_wait(self):
        release = threading.Event()
        camera = Mock(is_connected=True)
        camera.disconnect.side_effect = lambda: release.wait(1)
        start = time.monotonic()
        try:
            close_cameras({'camera': camera}, timeout=0.02)
            self.assertLess(time.monotonic()-start, 0.5)
        finally:
            release.set()


if __name__ == '__main__':
    unittest.main()

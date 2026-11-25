"""Read-only tests for the uncommissioned teleoperation building block."""
import types
import unittest
import os
from unittest import mock
import numpy as np
from devices import NAMES
import teleoperation
from teleoperation import calibrated_bounds, command, wait_cameras, preview_frame

class FakeBus:
    def __init__(self):
        self.calibration = {n: types.SimpleNamespace(range_min=1000, range_max=3000) for n in NAMES}
        self.writes = []
        self.is_connected = True
        self.enabled = False
    def sync_write(self, register, values, num_retry):
        self.writes.append((register, values, num_retry))
    def enable_torque(self, **kwargs): self.enabled = True
    def disable_torque(self, **kwargs): self.enabled = False
    def disconnect(self, disable_torque=False): self.is_connected = False

class TeleoperationTests(unittest.TestCase):
    def test_camera_failure_produces_placeholder(self):
        class FailedCamera:
            def latest(self): raise RuntimeError('camera read failed')
        result = preview_frame([None, FailedCamera()])
        self.assertEqual(result.shape, (480, 1280, 3))

    def test_teleoperation_can_stop_without_cameras(self):
        leader, follower = FakeBus(), FakeBus()
        with mock.patch.dict(os.environ, {'DISPLAY': ':0'}), \
             mock.patch.object(teleoperation.devices, 'open_read_only', side_effect=[leader, follower]), \
             mock.patch.object(teleoperation, 'state', return_value=np.zeros(6)), \
             mock.patch.object(teleoperation, 'Camera', side_effect=RuntimeError('missing camera')), \
             mock.patch.object(teleoperation, 'open_fullscreen'), \
             mock.patch.object(teleoperation.cv2, 'imshow'), \
             mock.patch.object(teleoperation.cv2, 'waitKey', side_effect=[-1, ord('q')]), \
             mock.patch.object(teleoperation.cv2, 'destroyAllWindows'):
            teleoperation.run()
        self.assertTrue(follower.enabled)
        self.assertEqual(len(follower.writes), 2)  # initial measured pose and final hold

    def test_terminal_q_stops_without_window_focus(self):
        leader, follower = FakeBus(), FakeBus()
        class Terminal:
            def __init__(self): self.closed = False
            def poll(self): return ord('q')
            def close(self): self.closed = True
        terminal = Terminal()
        with mock.patch.dict(os.environ, {'DISPLAY': ':0'}), \
             mock.patch.object(teleoperation.devices, 'open_read_only', side_effect=[leader, follower]), \
             mock.patch.object(teleoperation, 'state', return_value=np.zeros(6)), \
             mock.patch.object(teleoperation, 'Camera', side_effect=RuntimeError('missing camera')), \
             mock.patch.object(teleoperation, 'TerminalStop', return_value=terminal), \
             mock.patch.object(teleoperation, 'open_fullscreen'), \
             mock.patch.object(teleoperation.cv2, 'imshow'), \
             mock.patch.object(teleoperation.cv2, 'waitKey', return_value=-1), \
             mock.patch.object(teleoperation.cv2, 'destroyAllWindows'):
            teleoperation.run()
        self.assertTrue(terminal.closed)
        self.assertEqual(len(follower.writes), 2)

    def test_waits_for_delayed_initial_frame(self):
        class DelayedCamera:
            error = None
            def __init__(self): self.calls = 0
            def latest(self):
                self.calls += 1
                if self.calls < 3: raise RuntimeError('frame not ready')
                return 'frame'
        camera = DelayedCamera()
        self.assertEqual(wait_cameras([camera], timeout=2), ['frame'])
        self.assertEqual(camera.calls, 3)

    def test_calibration_constrains_arm_and_gripper(self):
        bus = FakeBus()
        lower, upper = calibrated_bounds(bus)
        np.testing.assert_allclose(lower[:5], -2000*180/4095)
        np.testing.assert_allclose(upper[:5], 2000*180/4095)
        self.assertEqual((lower[-1], upper[-1]), (0, 100))

    def test_invalid_command_is_not_written(self):
        bus = FakeBus()
        for target in ([1]*5, [0, 1, 2, 3, 4, float('nan')]):
            with self.assertRaises(ValueError): command(bus, target)
        self.assertEqual(bus.writes, [])
        command(bus, [0, 1, 2, 3, 4, 5])
        self.assertEqual(tuple(bus.writes[0][1]), NAMES)

if __name__ == '__main__': unittest.main()

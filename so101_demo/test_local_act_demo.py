"""Simulated control-flow checks; never touches cameras or physical motors."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import numpy as np
import local_act_demo as demo
import home_return

class FakeBus:
    def __init__(self): self.is_connected = True; self.enabled = False
    def enable_torque(self, **kwargs): self.enabled = True
    def disable_torque(self, **kwargs): self.enabled = False
    def disconnect(self, disable_torque=False): self.is_connected = False

class FakeCamera:
    def __init__(self, pattern): pass
    def close(self): pass

class FakeWorker:
    fail = False
    def __init__(self, engine, stats): pass
    def start(self, model, timeout): pass
    def infer(self, state, top, side, timeout):
        if self.fail: raise TimeoutError('simulated inference failure')
        return np.tile(np.asarray(demo.HOME)[None,:], (100,1)), 0.1
    def close(self): pass

class ControlTests(unittest.TestCase):
    def run_case(self, fail, run_fault=False, timeout=False):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory,'cup_engine_stats.json').write_text(json.dumps({
                'model':'cup', 'action_min':[-150]*6, 'action_max':[150]*6}))
            bus = FakeBus()
            writes = []
            image = np.zeros((480,640,3), np.uint8)
            ticks = []
            def show(images, status, terminal=None, preview=None):
                if status.startswith('RUNNING'):
                    ticks.append(1)
                    if run_fault and len(ticks) > 1: raise RuntimeError('simulated camera failure')
                    return 255 if run_fault else ord('q')
                return 255
            FakeWorker.fail = fail
            with mock.patch.dict(os.environ, {'DISPLAY':':0'}), \
                 mock.patch.object(demo, 'ROOT', directory), \
                 mock.patch.object(demo, 'MODEL_ROOT', directory), \
                 mock.patch.object(demo, 'MAX_RUN_SECONDS', 0 if timeout else 60), \
                 mock.patch.object(demo, 'Camera', FakeCamera), \
                 mock.patch.object(demo, 'wait_cameras', return_value=[image,image]), \
                 mock.patch.object(demo, 'frames', return_value=[image,image]), \
                 mock.patch.object(demo, 'show', side_effect=show), \
                 mock.patch.object(demo.devices, 'open_read_only', return_value=bus), \
                 mock.patch.object(demo, 'state', side_effect=lambda _:demo.HOME.copy()), \
                 mock.patch.object(demo, 'command', side_effect=lambda _,x:writes.append(np.asarray(x).copy())), \
                 mock.patch.object(demo, 'LocalInference', FakeWorker), \
                 mock.patch.object(demo, 'TerminalStop') as terminal_cls, \
                 mock.patch.object(demo, 'PreviewWindow'), \
                 mock.patch.object(home_return, 'return_home') as return_home, \
                 mock.patch.object(demo.cv2, 'destroyAllWindows'):
                if fail:
                    with self.assertRaises(TimeoutError): demo.run('cup')
                    self.assertFalse(bus.enabled)
                    self.assertEqual(writes, [])
                    return_home.assert_not_called()
                elif run_fault:
                    with self.assertRaises(RuntimeError): demo.run('cup')
                    self.assertTrue(bus.enabled)
                    self.assertGreaterEqual(len(writes), 3)
                    np.testing.assert_array_equal(writes[-1],demo.HOME)
                    return_home.assert_called_once()
                else:
                    demo.run('cup')
                    self.assertTrue(bus.enabled)
                    self.assertEqual(len(writes),2)
                    if timeout: self.assertEqual(ticks, [])
                    np.testing.assert_array_equal(writes[0],demo.HOME)
                    np.testing.assert_array_equal(writes[-1],demo.HOME)
                    return_home.assert_called_once()

    def test_q_holds_current_position(self): self.run_case(False)
    def test_inference_failure_before_start_never_enables_torque(self): self.run_case(True)
    def test_camera_failure_during_run_returns_home(self): self.run_case(False, run_fault=True)
    def test_maximum_run_time_returns_home(self): self.run_case(False, timeout=True)

if __name__ == '__main__': unittest.main()

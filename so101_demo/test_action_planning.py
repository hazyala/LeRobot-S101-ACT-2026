import unittest
import numpy as np
from action_planning import action_with_early_gripper_close, switch_action_plans, StallMonitor

class PlanningTests(unittest.TestCase):
    def test_gripper_lead_does_not_open_early(self):
        plan = np.zeros((100,6), np.float32)
        plan[8,5] = 30
        self.assertEqual(action_with_early_gripper_close(plan,0,8)[5], 30)
        plan[0,5] = 50; plan[8,5] = 5
        self.assertEqual(action_with_early_gripper_close(plan,0,8)[5], 50)
        self.assertEqual(action_with_early_gripper_close(plan,0,0)[5], 50)

    def test_blend_aligns_and_preserves_new_gripper_close(self):
        old = np.zeros((10,6), np.float32)
        new = np.ones((100,6), np.float32)*9
        result = switch_action_plans(old,new,0)
        self.assertEqual(result.shape,(100,6))
        self.assertAlmostEqual(float(result[0,0]),1.0)
        self.assertEqual(result[0,5],9)

    def test_stall_detected_only_after_window(self):
        monitor = StallMonitor()
        current = np.zeros(6)
        command = np.array([0, 10, 0, 0, 0, 0])
        monitor.update(0,current,command)
        monitor.update(2,current,command)
        with self.assertRaises(RuntimeError): monitor.update(3.3,current,command)

if __name__ == '__main__': unittest.main()

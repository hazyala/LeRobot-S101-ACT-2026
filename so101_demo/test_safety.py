import unittest
import numpy as np
from safety import PlanGate, safe_action, valid_reply

class SafetyTests(unittest.TestCase):
    def test_action_is_rate_and_tracking_limited(self):
        result = safe_action([90]*6, [0]*6, [0]*6, [-100]*6, [100]*6)
        np.testing.assert_array_equal(result, [2, 3, 3, 4, 4, 5])
        result = safe_action([90]*6, [0]*6, [20]*6, [-100]*6, [100]*6)
        np.testing.assert_array_equal(result, [6, 10, 10, 10, 8, 10])

    def test_rejects_invalid_and_out_of_bounds_actions(self):
        with self.assertRaises(ValueError): safe_action([float('nan')]*6, [0]*6, None, [-1]*6, [1]*6)
        with self.assertRaises(RuntimeError): safe_action([3]*6, [0]*6, None, [-1]*6, [1]*6)
        with self.assertRaises(RuntimeError): safe_action([0]*6, [100]*6, None, [-1]*6, [1]*6)

    def test_rejects_stale_mismatched_or_malformed_reply(self):
        reply = {'id': 2, 'actions': [[0]*6 for _ in range(100)]}
        self.assertEqual(valid_reply(2, reply, 0.5, 1).shape, (100, 6))
        with self.assertRaises(TimeoutError): valid_reply(2, reply, 1.1, 1)
        with self.assertRaises(ValueError): valid_reply(3, reply, 0.5, 1)
        with self.assertRaises(ValueError): valid_reply(2, {'id': 2, 'actions': [[0]*6]}, 0.5, 1)

    def test_disconnect_or_bad_update_invalidates_remaining_actions(self):
        gate = PlanGate()
        reply = {'id': 2, 'actions': [[1]*6 for _ in range(100)]}
        gate.install(2, reply, 0.5, 1)
        np.testing.assert_array_equal(gate.next_action(), [1]*6)
        gate.disconnect()
        with self.assertRaises(RuntimeError): gate.next_action()
        gate.install(2, reply, 0.5, 1)
        with self.assertRaises(TimeoutError): gate.install(3, reply, 2, 1)
        with self.assertRaises(RuntimeError): gate.next_action()

if __name__ == '__main__': unittest.main()

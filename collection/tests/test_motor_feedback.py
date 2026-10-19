import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import MOTOR_FEEDBACK, motor_feedback_features, read_motor_feedback
from lerobot.datasets import LeRobotDataset
from lerobot.utils.feature_utils import dataset_to_policy_features


class MotorFeedbackTests(unittest.TestCase):
    def test_single_packet_feedback_decodes_signed_load_and_position(self):
        from lerobot.motors import Motor, MotorNormMode
        from lerobot.motors.feetech import FeetechMotorsBus
        bus = FeetechMotorsBus("COM_TEST", motors={"gripper": Motor(6, "sts3215", MotorNormMode.RANGE_0_100)})
        bus._normalize = lambda values: {id_: value / 10 for id_, value in values.items()}
        payload = bytearray(23)
        for offset, value in [(0, 500), (8, (1 << 15) | 100), (12, (1 << 10) | 40), (21, 23)]:
            payload[offset:offset + 2] = value.to_bytes(2, "little")
        def receive():
            bus.sync_reader.data_dict = {6: list(payload)}
            return 0
        bus.sync_reader.txRxPacket = Mock(side_effect=receive)
        values = bus.sync_read_registers(["Present_Position", "Present_Load", "Present_Current", "Torque_Limit"])
        self.assertEqual(values["Present_Position"]["gripper"], -10)
        self.assertEqual(values["Present_Load"]["gripper"], -40)
        self.assertEqual(values["Present_Current"]["gripper"], 23)
        self.assertEqual(values["Torque_Limit"]["gripper"], 500)
        bus.sync_reader.txRxPacket.assert_called_once()
        self.assertEqual((bus.sync_reader.start_address, bus.sync_reader.data_length), (48, 23))
        bus.sync_reader.txRxPacket.reset_mock()
        def incomplete():
            bus.sync_reader.data_dict = {6: [0]}
            return 0
        bus.sync_reader.txRxPacket.side_effect = incomplete
        with self.assertRaises(ConnectionError):
            bus.sync_read_registers(["Present_Load", "Present_Current"], num_retry=2)
        self.assertEqual(bus.sync_reader.txRxPacket.call_count, 3)

    def test_signed_feedback_persists_and_is_excluded_from_policy_inputs(self):
        motors = {name: None for name in (
            "shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")}
        registers = {
            "Present_Load": {name: -40 + i for i, name in enumerate(motors)},
            "Present_Current": {name: 20 + i for i, name in enumerate(motors)},
            "Torque_Limit": {name: 500 + i for i, name in enumerate(motors)},
        }
        bus = Mock(motors=motors)
        bus.sync_read.side_effect = lambda register, **kwargs: registers[register]
        robot = SimpleNamespace(bus=bus, config=SimpleNamespace(num_read_retries=2))
        frame = read_motor_feedback(robot, np)
        features = {
            "observation.state": {"dtype": "float32", "shape": (6,),
                                  "names": [name + ".pos" for name in motors]},
            "action": {"dtype": "float32", "shape": (6,),
                       "names": [name + ".pos" for name in motors]},
            **motor_feedback_features(motors),
        }
        self.assertEqual(set(dataset_to_policy_features(features)), {"observation.state", "action"})
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "dataset"
            dataset = LeRobotDataset.create("local/feedback_test", 30, root=root,
                                           features=features, use_videos=False)
            try:
                dataset.add_frame({**frame, "observation.state": np.zeros(6, dtype=np.float32),
                                   "action": np.zeros(6, dtype=np.float32), "task": "test"})
                dataset.save_episode()
            finally:
                dataset.finalize()
            rows = pq.read_table(next(root.glob("data/**/*.parquet"))).to_pydict()
            for key, register in MOTOR_FEEDBACK.items():
                self.assertEqual(rows[key][0], list(registers[register].values()))
            resumed = LeRobotDataset.resume("local/feedback_test", root=root)
            try:
                self.assertEqual(resumed.num_episodes, 1)
                self.assertEqual(resumed.features["research.motor_load_raw"]["names"], list(motors))
            finally:
                resumed.finalize()
        for call in bus.sync_read.call_args_list:
            self.assertEqual(call.kwargs, {"normalize": False, "num_retry": 2})

    def test_read_failure_is_not_replaced_by_zero(self):
        bus = Mock(motors={"gripper": None})
        bus.sync_read.side_effect = ConnectionError("read failed")
        robot = SimpleNamespace(bus=bus, config=SimpleNamespace(num_read_retries=2))
        with self.assertRaises(ConnectionError):
            read_motor_feedback(robot, np)

"""Read-only SO-101 connection support based on the existing LeRobot motor bus.

No actuator commands are exposed here. Calibration is never written.
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'vendor'))
from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

NAMES = ('shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll', 'gripper')
PORTS = {
    'leader': '/dev/serial/by-id/usb-1a86_USB_Single_Serial_5AE6058375-if00',
    'follower': '/dev/serial/by-id/usb-1a86_USB_Single_Serial_5AE6055249-if00',
}

def open_read_only(role, calibration_path):
    """Check hardware calibration without changing servo settings or torque."""
    if role not in PORTS:
        raise ValueError('unknown robot role')
    with open(calibration_path, encoding='utf-8') as f:
        values = json.load(f)
    if set(values) != set(NAMES):
        raise ValueError('calibration joint names do not match')
    calibration = {n: MotorCalibration(**values[n]) for n in NAMES}
    motors = {n: Motor(i + 1, 'sts3215', MotorNormMode.RANGE_0_100 if n == 'gripper'
                       else MotorNormMode.DEGREES) for i, n in enumerate(NAMES)}
    bus = FeetechMotorsBus(port=PORTS[role], motors=motors, calibration=calibration)
    try:
        bus.connect()
        if not bus.is_calibrated:
            raise RuntimeError(role + ': stored calibration does not match hardware')
        return bus
    except BaseException:
        if bus.is_connected:
            bus.disconnect(disable_torque=False)
        raise

def read_positions(bus):
    positions = bus.sync_read('Present_Position', num_retry=2)
    if set(positions) != set(NAMES) or not all(math.isfinite(float(v)) for v in positions.values()):
        raise RuntimeError('invalid joint state')
    return positions

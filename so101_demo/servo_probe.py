"""Read SO-101 identification and calibration only; never writes registers."""
import json
import sys
import scservo_sdk as scs

names = ('shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll', 'gripper')
for path, calibration in ((sys.argv[1], sys.argv[2]), (sys.argv[3], sys.argv[4])):
    expected = json.load(open(calibration, encoding='utf-8'))
    port = scs.PortHandler(path)
    packet = scs.PacketHandler(0)
    if not port.openPort() or not port.setBaudRate(1000000):
        raise RuntimeError('cannot open ' + path)
    print(path, flush=True)
    try:
        for i, name in enumerate(names, 1):
            values = []
            for addr in (9, 11, 31, 56):
                val, result, err = packet.read2ByteTxRx(port, i, addr)
                if result != scs.COMM_SUCCESS or err:
                    raise RuntimeError('read error id={} addr={} result={} error={}'.format(i, addr, result, err))
                values.append(val)
            lo, hi, offset, position = values
            offset = -(offset & 2047) if offset & 2048 else offset
            cal = expected[name]
            match = (lo, hi, offset) == (cal['range_min'], cal['range_max'], cal['homing_offset'])
            print(name, 'calibration_match=', match, 'raw_position=', position, flush=True)
    finally:
        port.closePort()

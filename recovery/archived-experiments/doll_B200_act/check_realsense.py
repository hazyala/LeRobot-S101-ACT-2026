"""RealSense 연결 진단만 수행한다. 로봇·모터에 연결하지 않는다."""
import json
from pathlib import Path
import pyrealsense2 as rs

ROOT = Path(__file__).resolve().parents[2]
rig = json.loads((ROOT / 'collection/settings.json').read_text(encoding='utf-8'))['rig']
serial = rig['top_serial']
devices = list(rs.context().query_devices())
print('설정된 TOP serial:', serial, flush=True)
print('감지된 RealSense 수:', len(devices), flush=True)
found = False
for device in devices:
    name = device.get_info(rs.camera_info.name)
    number = device.get_info(rs.camera_info.serial_number)
    print('장치:', name, number, flush=True)
    found |= number == serial
if not found:
    raise SystemExit('설정된 카메라가 감지되지 않았습니다. USB 연결과 serial을 확인하세요.')

for depth in (False, True):
    pipeline, started = rs.pipeline(), False
    config = rs.config()
    config.enable_device(serial)
    config.enable_stream(rs.stream.color, rig['width'], rig['height'], rs.format.rgb8, rig['fps'])
    if depth:
        config.enable_stream(rs.stream.depth, rig['width'], rig['height'], rs.format.z16, rig['fps'])
    print('\n검사:', 'RGB + depth' if depth else 'RGB만', flush=True)
    try:
        pipeline.start(config)
        started = True
        frames = pipeline.wait_for_frames(5000)
        color = frames.get_color_frame()
        if not color:
            raise RuntimeError('RGB 프레임을 받지 못했습니다.')
        print('성공:', color.get_width(), color.get_height(), flush=True)
    except RuntimeError as exc:
        print('실패 원인:', str(exc), flush=True)
    finally:
        if started:
            pipeline.stop()
print('\n검사 종료. 로봇 연결·모터 명령·USB 리셋은 수행하지 않았습니다.', flush=True)

"""One live-camera request, never writes to motors; result recorded locally."""
import glob
import json
import time
import cv2
import devices
from policy_link import PolicyLink

OUT = '/home/aisw/lerobot/live_inference_diagnostic.jsonl'
def log(stage, **data):
    with open(OUT, 'a', encoding='utf-8') as f:
        f.write(json.dumps({'time': time.time(), 'stage': stage, **data}) + '\n')

p = PolicyLink()
cams = []
bus = None
try:
    log('start')
    bus = devices.open_read_only('follower', '/home/aisw/lerobot/follower.json')
    obs = devices.read_positions(bus)
    bus.disconnect(disable_torque=False)
    bus = None
    p.start('cup', timeout=45)
    log('server-ready')
    for pattern in ('/dev/v4l/by-id/*RealSense*405*video-index2', '/dev/v4l/by-id/*ABKO*video-index0'):
        paths = glob.glob(pattern)
        if len(paths) != 1:
            raise RuntimeError('camera unavailable: ' + pattern)
        camera = cv2.VideoCapture(paths[0], cv2.CAP_V4L2)
        cams.append(camera)
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    frames = []
    for camera in cams:
        ok, frame = camera.read()
        if not ok:
            raise RuntimeError('camera read failed')
        frames.append(frame)
    log('frames-read', shapes=[list(x.shape) for x in frames])
    state = [obs[name] for name in devices.NAMES]
    actions, elapsed = p.infer(state, frames[0], frames[1], timeout=10)
    log('success', elapsed_s=elapsed, action_shape=list(actions.shape))
except Exception as exc:
    log('error', type=type(exc).__name__, detail=str(exc))
finally:
    p.close()
    if bus is not None and bus.is_connected:
        bus.disconnect(disable_torque=False)
    for camera in cams:
        camera.release()
    log('finished')

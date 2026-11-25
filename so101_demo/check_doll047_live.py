"""Check the selected doll engine with live inputs; never command motors."""
import time
import numpy as np
import devices
from teleoperation import Camera, state, wait_cameras
from local_inference_client import LocalInference

root = '/home/aisw/lerobot/tensorrt_candidate/doll047/'
cameras = []
bus = worker = None
try:
    cameras.append(Camera('/dev/v4l/by-id/*RealSense*405*video-index2'))
    cameras.append(Camera('/dev/v4l/by-id/*ABKO*video-index0'))
    wait_cameras(cameras)
    bus = devices.open_read_only('follower', '/home/aisw/lerobot/follower.json')
    worker = LocalInference(root + 'doll.engine', root + 'doll_engine_stats.json')
    worker.start('doll', timeout=60)
    for i in range(3):
        top, side = [c.latest() for c in cameras]
        actions, elapsed = worker.infer(state(bus), top, side, timeout=12)
        if actions.shape != (100, 6) or not np.isfinite(actions).all():
            raise RuntimeError('invalid prediction')
        print('inference {}: {:.3f}s, finite {}' .format(i+1, elapsed, actions.shape), flush=True)
finally:
    if worker is not None: worker.close()
    if bus is not None and bus.is_connected: bus.disconnect(disable_torque=False)
    for camera in cameras: camera.close()

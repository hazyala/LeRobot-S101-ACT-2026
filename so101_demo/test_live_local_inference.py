"""Read both cameras + follower and run local models, never command motors."""
import glob
import json
import time
import cv2
import numpy as np
import devices
from local_inference_client import LocalInference

root = '/home/aisw/lerobot/tensorrt_candidate/'
patterns = ('/dev/v4l/by-id/*RealSense*405*video-index2', '/dev/v4l/by-id/*ABKO*video-index0')
cams = []
bus = None
try:
    bus = devices.open_read_only('follower', '/home/aisw/lerobot/follower.json')
    for pattern in patterns:
        paths = glob.glob(pattern)
        if len(paths) != 1: raise RuntimeError('camera unavailable: '+pattern)
        cam = cv2.VideoCapture(paths[0], cv2.CAP_V4L2)
        cams.append(cam)
        cam.set(cv2.CAP_PROP_FRAME_WIDTH, 640); cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    def observation():
        start = time.monotonic()
        state_map = devices.read_positions(bus)
        frames = []
        for cam in cams:
            ok, image = cam.read()
            if not ok or image.shape != (480,640,3): raise RuntimeError('camera read failed')
            frames.append(image)
        return [state_map[k] for k in devices.NAMES], frames, time.monotonic()-start
    for model in ('cup','doll'):
        worker = LocalInference(root+model+'.engine', root+model+'_engine_stats.json')
        try:
            worker.start(model, timeout=60)
            results = []
            for i in range(5):
                state, frames, capture_s = observation()
                actions, inference_s = worker.infer(state, frames[0], frames[1], timeout=10)
                results.append({'capture_ms':round(capture_s*1000,1),
                                'worker_ms':round(inference_s*1000,1),
                                'finite':bool(np.isfinite(actions).all()), 'shape':list(actions.shape)})
            print(json.dumps({'model':model,'observations':results}, allow_nan=False), flush=True)
        finally:
            worker.close()
finally:
    if bus is not None and bus.is_connected: bus.disconnect(disable_torque=False)
    for cam in cams: cam.release()

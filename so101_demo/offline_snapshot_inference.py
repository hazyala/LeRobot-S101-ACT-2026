"""Diagnostic: capture and close cameras before inference, never command motors.

This deliberately stale-frame test does not validate real-time control.
"""
import glob
import json
import time
import cv2
import devices
from policy_link import PolicyLink

OUT = '/home/aisw/lerobot/snapshot_inference_diagnostic.jsonl'
def log(stage, **data):
    with open(OUT, 'a', encoding='utf-8') as f:
        f.write(json.dumps({'time': time.time(), 'stage': stage, **data}) + '\n')

cams = []
bus = None
try:
    log('start')
    bus = devices.open_read_only('follower', '/home/aisw/lerobot/follower.json')
    obs = devices.read_positions(bus)
    bus.disconnect(disable_torque=False)
    bus = None
    for pattern in ('/dev/v4l/by-id/*RealSense*405*video-index2', '/dev/v4l/by-id/*ABKO*video-index0'):
        paths = glob.glob(pattern)
        if len(paths) != 1: raise RuntimeError('camera unavailable: ' + pattern)
        camera = cv2.VideoCapture(paths[0], cv2.CAP_V4L2)
        cams.append(camera)
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    frames = []
    for camera in cams:
        ok, frame = camera.read()
        if not ok: raise RuntimeError('camera read failed')
        frames.append(frame)
    log('frames-read', shapes=[list(x.shape) for x in frames])
    for camera in cams: camera.release()
    cams = []
    log('cameras-released')
    for attempt in range(3):
        time.sleep(5)
        p = PolicyLink()
        try:
            p.start('cup', timeout=35)
            codec = 'png' if attempt == 0 else 'jpeg90'
            actions, elapsed = p.infer([obs[n] for n in devices.NAMES], frames[0], frames[1], timeout=10, codec=codec)
            log('success', elapsed_s=elapsed, action_shape=list(actions.shape), attempt=attempt, codec=codec)
            break
        except Exception as exc:
            log('attempt-error', detail=str(exc), attempt=attempt)
        finally:
            p.close()
    else:
        log('failed')
except Exception as exc:
    log('error', detail=str(exc))
finally:
    if bus is not None and bus.is_connected: bus.disconnect(disable_torque=False)
    for camera in cams: camera.release()
    log('finished')

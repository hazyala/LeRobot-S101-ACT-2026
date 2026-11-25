"""Compare lossless and lossy transport using the side webcam, no motors."""
import glob
import cv2
from policy_link import PolicyLink

paths = glob.glob('/dev/v4l/by-id/*ABKO*video-index0')
if len(paths) != 1: raise RuntimeError('side camera unavailable')
c = cv2.VideoCapture(paths[0], cv2.CAP_V4L2)
try:
    c.set(cv2.CAP_PROP_FRAME_WIDTH, 640); c.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    ok, frame = c.read()
    if not ok: raise RuntimeError('side camera read failed')
finally:
    c.release()
p = PolicyLink()
try:
    p.start('cup')
    for codec in ('png', 'jpeg90', 'png', 'jpeg90'):
        try:
            result, elapsed = p.infer([0]*6, frame, frame, timeout=15, codec=codec)
            print(codec, round(elapsed, 3), list(result.shape), flush=True)
        except Exception as exc:
            print(codec, type(exc).__name__, str(exc), flush=True)
            break
finally:
    p.close()

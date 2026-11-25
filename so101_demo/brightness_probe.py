"""Compare reversible camera brightness settings without controlling motors."""
import glob
import time
import cv2

paths = glob.glob('/dev/v4l/by-id/*RealSense*405*video-index2')
if len(paths) != 1:
    raise RuntimeError('D405 not found')
cap = cv2.VideoCapture(paths[0], cv2.CAP_V4L2)
if not cap.isOpened(): raise RuntimeError('camera unavailable')
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
original = cap.get(cv2.CAP_PROP_BRIGHTNESS)
try:
    for val in (0, -16, -32, -48):
        print('set', val, cap.set(cv2.CAP_PROP_BRIGHTNESS, val), 'actual', cap.get(cv2.CAP_PROP_BRIGHTNESS), flush=True)
        end = time.monotonic() + 4
        while time.monotonic() < end:
            ok, frame = cap.read()
            if not ok: raise RuntimeError('camera frame error')
        cv2.imwrite('/tmp/so101_brightness_{}.jpg'.format(val), frame)
finally:
    cap.set(cv2.CAP_PROP_BRIGHTNESS, original)
    cap.release()

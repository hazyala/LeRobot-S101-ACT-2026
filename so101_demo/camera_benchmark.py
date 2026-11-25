"""Compare side camera video modes without motor access or saved images."""
import cv2
import sys
import time

for mjpeg in ((True,) if '--mjpeg-only' in sys.argv else (False, True)):
    a = cv2.VideoCapture(3, cv2.CAP_V4L2)
    b = cv2.VideoCapture(0, cv2.CAP_V4L2)
    try:
        if mjpeg:
            b.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        for c in (a, b):
            c.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            c.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            c.set(cv2.CAP_PROP_FPS, 30)
        started = time.monotonic()
        count = 0
        for _ in range(30):
            x, frame_a = a.read()
            y, frame_b = b.read()
            if not x or not y:
                break
            count += 1
        fourcc = int(b.get(cv2.CAP_PROP_FOURCC))
        print('mjpeg={} fourcc={} pairs={} elapsed_s={:.2f}'.format(mjpeg,
              ''.join(chr((fourcc >> 8*i) & 255) for i in range(4)), count, time.monotonic()-started), flush=True)
    finally:
        a.release(); b.release()

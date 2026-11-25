"""Read-only camera test; does not open either robot serial port."""
import cv2
import time
for index in (0, 1, 2, 3):
    cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    ok, frame = cap.read()
    print('video{}: opened={} frame={} shape={}'.format(index, cap.isOpened(), ok, None if frame is None else frame.shape), flush=True)
    cap.release()

top = cv2.VideoCapture(3, cv2.CAP_V4L2)
side = cv2.VideoCapture(0, cv2.CAP_V4L2)
try:
    for cap in (top, side):
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    started = time.monotonic()
    count = 0
    for _ in range(30):
        ok1, a = top.read()
        ok2, b = side.read()
        if not ok1 or not ok2:
            break
        count += 1
    print('simultaneous pairs={} elapsed={:.2f}s top_channel_difference={:.2f}'.format(count, time.monotonic()-started, abs(a[:, :, 0].astype('float32')-a[:, :, 1]).mean()), flush=True)
    for codec in ('.png', '.jpg'):
        images = [cv2.imencode(codec, image)[1] for image in (a, b)]
        print('{} bytes for both frames: {}'.format(codec, sum(x.size for x in images)), flush=True)
finally:
    top.release()
    side.release()

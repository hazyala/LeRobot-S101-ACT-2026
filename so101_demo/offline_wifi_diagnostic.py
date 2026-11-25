"""Record a short D405/Wi-Fi diagnostic locally, even if SSH drops."""
import glob
import json
import os
import socket
import subprocess
import time
import cv2

OUT = '/home/aisw/lerobot/d405_wifi_diagnostic.jsonl'
def log(kind, **data):
    with open(OUT, 'a', encoding='utf-8') as f:
        f.write(json.dumps({'time': time.time(), 'kind': kind, **data}) + '\n')

def network(label):
    try:
        wifi = subprocess.run(['iwconfig', 'wlan0'], stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, timeout=3, text=True).stdout
    except Exception as ex:
        wifi = str(ex)
    try:
        start = time.monotonic()
        with socket.create_connection(('59.150.33.1', 54307), timeout=3):
            result = round((time.monotonic() - start) * 1000, 1)
    except Exception as ex:
        result = str(ex)
    log('network', label=label, tcp=result, wifi=wifi)

log('start')
network('before')
path = None
for _ in range(180):
    matches = glob.glob('/dev/v4l/by-id/*RealSense*405*video-index2')
    if matches:
        path = matches[0]
        break
    time.sleep(1)
if path is None:
    log('not-connected'); raise SystemExit(1)
log('detected', path=path)
network('connected-not-open')
cam = cv2.VideoCapture(path, cv2.CAP_V4L2)
try:
    cam.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    ok, frame = cam.read()
    log('frame', ok=bool(ok), shape=list(frame.shape) if ok else None)
    for i in range(5):
        network('stream-{}'.format(i))
finally:
    cam.release()
log('released')
time.sleep(3)
network('after')
log('finished')

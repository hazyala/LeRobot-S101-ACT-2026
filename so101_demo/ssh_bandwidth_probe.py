"""Small, read-only SSH transport probe, independent of cameras and policy."""
import hashlib
import os
import subprocess
import sys
import time

data = os.urandom(140000)
cmd = ['ssh', '-T', '-i', '/home/aisw/.ssh/so101_gateway_key', '-p', '54307',
       '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
       '-o', 'ConnectTimeout=15', 'jungsu@59.150.33.1',
       "python3 -c 'import sys,hashlib;print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())'"]
start = time.monotonic()
cams = []
if any(arg.startswith('--camera') for arg in sys.argv):
    import cv2
    indices = [3] if '--camera-top' in sys.argv else [0] if '--camera-side' in sys.argv else [3, 0]
    cams = [cv2.VideoCapture(index, cv2.CAP_V4L2) for index in indices]
    for cam in cams:
        if '--low-bandwidth' in sys.argv:
            cam.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
            cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
            cam.set(cv2.CAP_PROP_FPS, 6)
            print('camera negotiated {}x{} fps {}'.format(cam.get(cv2.CAP_PROP_FRAME_WIDTH),
                  cam.get(cv2.CAP_PROP_FRAME_HEIGHT), cam.get(cv2.CAP_PROP_FPS)), flush=True)
        ok, frame = cam.read()
        if not ok:
            raise RuntimeError('camera read failed')
try:
    p = subprocess.run(cmd, input=data, stdout=subprocess.PIPE, timeout=35, check=True)
finally:
    for cam in cams:
        cam.release()
assert p.stdout.decode().strip() == hashlib.sha256(data).hexdigest()
print('140000 bytes verified in {:.1f} ms'.format((time.monotonic()-start)*1000))

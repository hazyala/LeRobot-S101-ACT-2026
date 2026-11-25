"""Camera-to-B200 timing test; synthetic joint state and no motor commands."""
import base64
import json
import select
import subprocess
import sys
import time

import cv2

model = sys.argv[1] if len(sys.argv) > 1 else 'doll'
codec = sys.argv[2] if len(sys.argv) > 2 else '.png'
count = int(sys.argv[3]) if len(sys.argv) > 3 else 5
interval = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0
if codec not in ('.png', '.jpg'):
    raise ValueError('codec must be .png or .jpg')
if not 1 <= count <= 120 or not 0 <= interval <= 5:
    raise ValueError('invalid sample count or interval')
cmd = ['ssh', '-T', '-i', '/home/aisw/.ssh/so101_gateway_key', '-p', '54307',
       '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=15',
       'jungsu@59.150.33.1',
       '/NHNHOME/workspace/lerobot/lerobot-act/bin/python -u /NHNHOME/workspace/lerobot/so101-demo/inference_server.py']
def receive(process, timeout):
    if not select.select([process.stdout], [], [], timeout)[0]:
        raise TimeoutError('inference response timed out')
    line = process.stdout.readline()
    if not line:
        raise RuntimeError('inference connection closed')
    return json.loads(line)

def write_all(stream, data):
    remaining = memoryview(data)
    while remaining:
        written = stream.write(remaining)
        if not written:
            raise BrokenPipeError('inference input closed')
        remaining = remaining[written:]

p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0)
top = side = None
try:
    write_all(p.stdin, (json.dumps({'model': model}) + '\n').encode())
    assert receive(p, 45)['ready']
    print('model ready', flush=True)
    top = cv2.VideoCapture(3, cv2.CAP_V4L2)
    side = cv2.VideoCapture(0, cv2.CAP_V4L2)
    for c in (top, side):
        c.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        c.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    for i in range(count):
        start = time.monotonic()
        frames = []
        for c in (top, side):
            ok, frame = c.read()
            if not ok or frame.shape != (480, 640, 3):
                raise RuntimeError('invalid camera frame')
            ok, png = cv2.imencode(codec, frame)
            if not ok:
                raise RuntimeError('camera encoding failed')
            frames.append(base64.b64encode(png).decode())
        request = json.dumps({'id': i, 'state': [0]*6, 'top': frames[0], 'side': frames[1]}, separators=(',', ':')) + '\n'
        print('encoded sample={} bytes={} elapsed_ms={:.1f}'.format(i, len(request), (time.monotonic()-start)*1000), flush=True)
        write_all(p.stdin, request.encode())
        print('request sent', flush=True)
        result = receive(p, 30)
        if result['id'] != i or len(result['actions']) != 100:
            raise RuntimeError('unexpected inference reply')
        print('sample={} bytes={} total_ms={:.1f} gpu_ms={:.1f}'.format(i, len(request), (time.monotonic()-start)*1000, result['inference_ms']), flush=True)
        if interval:
            time.sleep(max(0, interval-(time.monotonic()-start)))
finally:
    if top is not None: top.release()
    if side is not None: side.release()
    p.terminate()
    try: p.wait(timeout=5)
    except subprocess.TimeoutExpired: p.kill()

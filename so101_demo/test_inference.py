"""B200 offline test: synthetic observations only, no robot connection."""
import base64
import json
import subprocess
import sys
import time

import cv2
import numpy as np

for model in ('doll', 'cup'):
    proc = subprocess.Popen([sys.executable, '/NHNHOME/workspace/lerobot/so101-demo/inference_server.py'],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    proc.stdin.write(json.dumps({'model': model}) + '\n'); proc.stdin.flush()
    assert json.loads(proc.stdout.readline())['ready']
    ok, image = cv2.imencode('.png', np.zeros((480, 640, 3), dtype=np.uint8))
    assert ok
    image = base64.b64encode(image).decode('ascii')
    t = time.monotonic()
    proc.stdin.write(json.dumps({'id': 1, 'state': [0] * 6, 'top': image, 'side': image}) + '\n'); proc.stdin.flush()
    reply = json.loads(proc.stdout.readline())
    arr = np.array(reply['actions'])
    assert arr.shape == (100, 6) and np.isfinite(arr).all()
    print(model, 'synthetic inference OK', 'gpu_ms=', round(reply['inference_ms'], 1), 'total_ms=', round((time.monotonic()-t)*1000, 1), flush=True)
    proc.stdin.close()
    assert proc.wait(timeout=15) == 0

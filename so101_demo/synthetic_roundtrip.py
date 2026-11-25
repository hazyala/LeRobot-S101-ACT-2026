"""Connectivity and inference test without cameras or robot access."""
import base64
import json
import subprocess
import sys
import time
import cv2
import numpy as np

cmd = ['ssh', '-T', '-i', '/home/aisw/.ssh/so101_gateway_key', '-p', '54307',
       '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
       '-o', 'ConnectTimeout=15', 'jungsu@59.150.33.1',
       '/NHNHOME/workspace/lerobot/lerobot-act/bin/python -u /NHNHOME/workspace/lerobot/so101-demo/inference_server.py']
image = base64.b64encode(cv2.imencode('.png', np.zeros((480, 640, 3), dtype=np.uint8))[1]).decode()
request = json.dumps({'model':'doll'}) + '\n' + json.dumps({'id': 1, 'state':[0]*6, 'top':image, 'side':image}) + '\n'
start = time.monotonic()
result = subprocess.run(cmd, input=request, text=True, stdout=subprocess.PIPE, timeout=90, check=True)
lines = result.stdout.splitlines()
assert len(lines) == 2 and json.loads(lines[0])['ready']
reply = json.loads(lines[1])
assert reply['id'] == 1 and np.asarray(reply['actions']).shape == (100, 6)
print('SSH and synthetic inference succeeded; total_ms={:.1f}, gpu_ms={:.1f}'.format((time.monotonic()-start)*1000, reply['inference_ms']))

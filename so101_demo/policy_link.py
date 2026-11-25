"""Bounded SSH transport for the Jetson ACT client (no motor control)."""
import base64
import json
import os
from pathlib import Path
import selectors
import subprocess
import time
import cv2
import numpy as np
from safety import valid_reply, vector

SSH_COMMAND = [
    'ssh', '-T', '-i', str(Path.home() / '.ssh/so101_gateway_key'), '-p', '54307',
    '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
    '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=3', '-o', 'ServerAliveCountMax=2',
    'jungsu@59.150.33.1',
    '/NHNHOME/workspace/lerobot/lerobot-act/bin/python -u /NHNHOME/workspace/lerobot/so101-demo/inference_server.py',
]

class PolicyLink:
    def __init__(self, command=None):
        self.command = command or SSH_COMMAND
        self.process = None
        self.buffer = b''
        self.counter = 0

    def start(self, model, timeout=45):
        if model not in ('doll', 'cup') or self.process is not None:
            raise ValueError('invalid model or connection already open')
        self.process = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=None, bufsize=0, start_new_session=True)
        os.set_blocking(self.process.stdin.fileno(), False)
        os.set_blocking(self.process.stdout.fileno(), False)
        try:
            reply = self._exchange({'model': model}, time.monotonic() + timeout)
            if reply.get('ready') is not True or reply.get('model') != model:
                raise RuntimeError('server returned invalid startup response')
        except BaseException:
            self.close()
            raise

    def _wait(self, fd, event, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('inference request timed out')
        with selectors.DefaultSelector() as sel:
            sel.register(fd, event)
            if not sel.select(remaining):
                raise TimeoutError('inference request timed out')

    def _exchange(self, data, deadline):
        if self.process is None or self.process.poll() is not None:
            raise ConnectionError('inference process is not running')
        outgoing = memoryview((json.dumps(data, separators=(',', ':'), allow_nan=False) + '\n').encode())
        while outgoing:
            fd = self.process.stdin.fileno()
            self._wait(fd, selectors.EVENT_WRITE, deadline)
            try:
                written = os.write(fd, outgoing)
            except BlockingIOError:
                continue
            if written == 0:
                raise ConnectionError('inference input closed')
            outgoing = outgoing[written:]
        while b'\n' not in self.buffer:
            fd = self.process.stdout.fileno()
            self._wait(fd, selectors.EVENT_READ, deadline)
            try:
                chunk = os.read(fd, 65536)
            except BlockingIOError:
                continue
            if not chunk:
                raise ConnectionError('inference output closed')
            self.buffer += chunk
            if len(self.buffer) > 2_000_000:
                raise ValueError('inference response too large')
        line, self.buffer = self.buffer.split(b'\n', 1)
        return json.loads(line)

    def infer(self, state, top, side, timeout=2.0, codec='png'):
        if timeout <= 0:
            raise ValueError('timeout must be positive')
        if codec not in ('png', 'jpeg90'):
            raise ValueError('unsupported image codec')
        started = time.monotonic()
        deadline = started + timeout
        images = []
        for frame in (top, side):
            if not isinstance(frame, np.ndarray) or frame.shape != (480, 640, 3) or frame.dtype != np.uint8:
                raise ValueError('expected 640x480 BGR uint8 image')
            ext = '.png' if codec == 'png' else '.jpg'
            opts = [] if codec == 'png' else [cv2.IMWRITE_JPEG_QUALITY, 90]
            ok, encoded = cv2.imencode(ext, frame, opts)
            if not ok:
                raise ValueError('image compression failed')
            images.append(base64.b64encode(encoded).decode('ascii'))
        self.counter += 1
        request = {'id': self.counter, 'state': vector(state, 'state').tolist(),
                   'top': images[0], 'side': images[1]}
        try:
            reply = self._exchange(request, deadline)
            elapsed = time.monotonic() - started
            return valid_reply(self.counter, reply, elapsed, timeout), elapsed
        except BaseException:
            self.close()
            raise

    def close(self):
        process, self.process = self.process, None
        self.buffer = b''
        if process is None:
            return
        for stream in (process.stdin, process.stdout):
            if stream is not None:
                stream.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)

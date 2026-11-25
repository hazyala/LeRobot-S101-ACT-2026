"""Single-client ACT inference over an authenticated SSH stdio stream."""
import base64
import contextlib
import hashlib
import json
import os
import signal
import sys
import time

import cv2
import numpy as np
import torch
from lerobot.policies import make_pre_post_processors
from lerobot.policies.act import ACTConfig, ACTPolicy

ROOT = '/NHNHOME/workspace/lerobot/so101-demo/models/doll'
CUP = '/NHNHOME/workspace/lerobot/outputs/act_paper_cup_basic_20261021_224407_822254/checkpoints/044000/pretrained_model'
MAX_LINE = 8_000_000

def reply(value):
    print(json.dumps(value, separators=(',', ':'), allow_nan=False), flush=True)

def read_deadline(max_bytes, seconds):
    def expired(_signum, _frame):
        raise TimeoutError('inference client input timed out')
    previous = signal.signal(signal.SIGALRM, expired)
    signal.alarm(seconds)
    try:
        return sys.stdin.buffer.readline(max_bytes)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)

def main():
    line = read_deadline(1024, 20)
    request = json.loads(line)
    mode = request.get('model')
    if mode not in ('doll', 'cup'):
        raise ValueError('invalid model')
    path = ROOT if mode == 'doll' else CUP
    expected = ('c604b4280f530448162ec06e70ad8435f9c38c06df6c9c263645b5d66f347fbd'
                if mode == 'doll' else '716584d6391c2879e2cdd7969c2329843433af0dd970c408fd151a6abfecd714')
    digest = hashlib.sha256()
    with open(os.path.join(path, 'model.safetensors'), 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise ValueError('model checksum mismatch')
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable')
    config = ACTConfig.from_pretrained(path)
    config.device = 'cuda'
    config.pretrained_backbone_weights = None
    if set(config.input_features) != {'observation.state', 'observation.images.top', 'observation.images.side'}:
        raise ValueError('unexpected model inputs')
    with contextlib.redirect_stdout(sys.stderr):
        policy = ACTPolicy.from_pretrained(path, config=config, strict=True).to('cuda').eval()
        preprocess, postprocess = make_pre_post_processors(config, pretrained_path=path)
    reply({'ready': True, 'model': mode})
    while True:
        line = read_deadline(MAX_LINE + 1, 20)
        if not line:
            return
        print('received request bytes={}'.format(len(line)), file=sys.stderr, flush=True)
        if len(line) > MAX_LINE or not line.endswith(b'\n'):
            raise ValueError('invalid request size')
        request = json.loads(line)
        state = np.asarray(request['state'], dtype=np.float32)
        if state.shape != (6,) or not np.isfinite(state).all():
            raise ValueError('invalid state')
        frame = {'observation.state': torch.from_numpy(state)}
        for name in ('top', 'side'):
            encoded = base64.b64decode(request[name], validate=True)
            img = cv2.imdecode(np.frombuffer(encoded, np.uint8), cv2.IMREAD_COLOR)
            if img is None or img.shape != (480, 640, 3):
                raise ValueError('invalid camera frame: ' + name)
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            frame['observation.images.' + name] = torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0
        batch = preprocess(frame)
        torch.cuda.synchronize()
        started = time.monotonic()
        amp = torch.autocast(device_type='cuda', dtype=torch.float16) if mode == 'doll' else contextlib.nullcontext()
        with torch.inference_mode(), amp:
            actions = policy.predict_action_chunk(batch)
        torch.cuda.synchronize()
        ms = (time.monotonic() - started) * 1000
        actions = postprocess(actions)[0].cpu().numpy()
        if actions.shape != (100, 6) or not np.isfinite(actions).all():
            raise ValueError('invalid model output')
        print('inference complete id={} gpu_ms={:.1f}'.format(request['id'], ms), file=sys.stderr, flush=True)
        reply({'id': request['id'], 'actions': actions.tolist(), 'inference_ms': ms})

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'inference server error: {exc}', file=sys.stderr, flush=True)
        sys.exit(1)

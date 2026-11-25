"""Jetson system-Python TensorRT worker. Does not control any hardware."""
import argparse
import json
import os
import sys
import time
import numpy as np
from standalone_act import TensorRTBackend, load_stats, postprocess, prepare, verify_model_hash

def reply(value):
    print(json.dumps(value, separators=(',', ':'), allow_nan=False), flush=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--engine', required=True)
    ap.add_argument('--stats', required=True)
    ap.add_argument('--ipc-dir', required=True)
    ap.add_argument('--extra', nargs=2)
    args = ap.parse_args()
    root = os.path.realpath(args.ipc_dir)
    if not root.startswith('/dev/shm/') or not os.path.isdir(root):
        raise ValueError('invalid temporary observation directory')
    stats = load_stats(args.stats)
    verify_model_hash(args.engine, stats, 'tensorrt')
    backend = TensorRTBackend(args.engine)
    models = {stats['model']: (stats, backend)}
    try:
        if args.extra:
            extra_engine, extra_stats = args.extra
            other = load_stats(extra_stats)
            if other['model'] in models: raise ValueError('duplicate model')
            verify_model_hash(extra_engine, other, 'tensorrt')
            models[other['model']] = (other, TensorRTBackend(extra_engine))
        hello = json.loads(sys.stdin.readline(1024))
        if hello != {'hello': True}: raise ValueError('invalid worker handshake')
        reply({'ready': True, 'model': stats['model']})
        for line in sys.stdin:
            if len(line) > 4096: raise ValueError('invalid request')
            req = json.loads(line)
            if args.extra:
                stats, backend = models[req['model']]
            path = os.path.realpath(req['path'])
            if not path.startswith(root + os.sep) or os.path.getsize(path) > 4_000_000:
                raise ValueError('invalid observation path')
            with np.load(path, allow_pickle=False) as obs:
                inputs = prepare(obs['state'], obs['top_bgr'], obs['side_bgr'], stats)
            start = time.monotonic()
            actions = postprocess(backend.run(inputs), stats)
            reply({'id':req['id'], 'actions':actions.tolist(),
                   'inference_ms':(time.monotonic()-start)*1000})
    finally:
        for _, backend in models.values(): backend.close()

if __name__ == '__main__':
    try: main()
    except Exception as exc:
        print('local inference worker error: {}'.format(exc), file=sys.stderr, flush=True)
        sys.exit(1)

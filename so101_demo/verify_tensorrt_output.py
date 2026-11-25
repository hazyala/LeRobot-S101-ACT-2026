"""Compare a target TensorRT engine with saved reference outputs, no motors."""
import argparse
import json
import time
import numpy as np
from standalone_act import TensorRTBackend, load_stats, prepare, postprocess, verify_model_hash

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--engine', required=True)
    ap.add_argument('--stats', required=True)
    ap.add_argument('--fixture', required=True)
    args = ap.parse_args()
    stats = load_stats(args.stats)
    verify_model_hash(args.engine, stats, 'tensorrt')
    with np.load(args.fixture, allow_pickle=False) as obs:
        inputs = prepare(obs['state'], obs['top_bgr'], obs['side_bgr'], stats)
        refs = {key: np.asarray(obs[key], dtype=np.float32) for key in
                ('reference_cpu', 'reference_gpu_fp32', 'reference_gpu_fp16')}
    backend = TensorRTBackend(args.engine)
    timings = []
    try:
        for _ in range(3):
            start = time.monotonic()
            result = postprocess(backend.run(inputs), stats)
            timings.append((time.monotonic()-start)*1000)
    finally:
        backend.close()
    errors = {}
    for name, ref in refs.items():
        if ref.shape != (100,6) or not np.isfinite(ref).all(): raise ValueError('invalid reference')
        difference = np.abs(ref-result)
        errors[name] = {'max_abs':float(difference.max()), 'mean_abs':float(difference.mean())}
    print(json.dumps({'model':stats['model'], 'inference_ms':timings, 'differences':errors}, allow_nan=False), flush=True)

if __name__ == '__main__': main()

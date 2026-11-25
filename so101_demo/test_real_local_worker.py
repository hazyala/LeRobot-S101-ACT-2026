"""Run a real local TensorRT worker on one saved reference, without motors."""
import argparse
import json
import numpy as np
from local_inference_client import LocalInference

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--model', choices=('cup','doll'), required=True)
    p.add_argument('--engine', required=True)
    p.add_argument('--stats', required=True)
    p.add_argument('--fixture', required=True)
    args = p.parse_args()
    with np.load(args.fixture, allow_pickle=False) as obs:
        state, top, side = obs['state'], obs['top_bgr'], obs['side_bgr']
        reference = obs['reference_cpu']
    worker = LocalInference(args.engine, args.stats)
    try:
        worker.start(args.model, timeout=60)
        times = []
        for _ in range(3):
            result, elapsed = worker.infer(state, top, side, timeout=10)
            times.append(elapsed*1000)
        delta = np.abs(result-reference)
        print(json.dumps({'model':args.model, 'worker_total_ms':times,
                          'cpu_reference_max_abs':float(delta.max()),
                          'cpu_reference_mean_abs':float(delta.mean())}, allow_nan=False), flush=True)
    finally:
        worker.close()

if __name__ == '__main__': main()

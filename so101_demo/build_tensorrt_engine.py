"""Build a target-specific TensorRT engine for an exported ACT model.

Not a motor command. Only run after transferring a checksum-verified ONNX file.
Use a separate output directory; this writes an engine and matching stats.
"""
import argparse
import hashlib
import json
import os
import time
import tensorrt as trt

def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--onnx', required=True)
    p.add_argument('--stats', required=True)
    p.add_argument('--engine', required=True)
    p.add_argument('--output-stats', required=True)
    p.add_argument('--workspace-mb', type=int, default=256)
    args = p.parse_args()
    if not 16 <= args.workspace_mb <= 512: raise ValueError('workspace must be between 16 and 512 MiB')
    if os.path.exists(args.engine) or os.path.exists(args.output_stats):
        raise FileExistsError('refusing to overwrite existing engine or stats')
    with open(args.stats) as f: stats = json.load(f)
    if sha256(args.onnx) != stats.get('onnx_sha256'):
        raise ValueError('ONNX checksum mismatch')
    logger = trt.Logger(trt.Logger.WARNING)
    builder = trt.Builder(logger)
    network = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
    parser = trt.OnnxParser(network, logger)
    with open(args.onnx, 'rb') as f: ok = parser.parse(f.read())
    if not ok:
        for i in range(parser.num_errors): print(parser.get_error(i), flush=True)
        raise RuntimeError('TensorRT cannot parse this ONNX model')
    print('ONNX parsed; building TensorRT engine', flush=True)
    config = builder.create_builder_config()
    config.max_workspace_size = args.workspace_mb * 1024 * 1024
    start = time.monotonic()
    engine = builder.build_engine(network, config)
    if engine is None: raise RuntimeError('TensorRT engine build failed')
    data = engine.serialize()
    temp = args.engine + '.partial'
    try:
        with open(temp, 'wb') as f: f.write(data)
        os.replace(temp, args.engine)
        stats['engine_sha256'] = sha256(args.engine)
        stats['engine_tensorrt_version'] = trt.__version__
        stats['engine_workspace_mb'] = args.workspace_mb
        stats['engine_precision'] = 'float32'
        with open(args.output_stats, 'x') as f: json.dump(stats, f, indent=2, allow_nan=False)
    finally:
        if os.path.exists(temp): os.remove(temp)
    print('engine built in {:.1f}s'.format(time.monotonic()-start), flush=True)

if __name__ == '__main__': main()

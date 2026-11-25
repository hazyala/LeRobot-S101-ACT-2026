"""Read a zero-weight ONNX fixture into installed TensorRT, no engine or robot."""
import gzip
import os
import sys
import tempfile
import time
import tensorrt as trt

logger = trt.Logger(trt.Logger.WARNING)
builder = trt.Builder(logger)
net = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
parser = trt.OnnxParser(net, logger)
with gzip.open(sys.argv[1], 'rb') as f: data = f.read()
if parser.parse(data):
    print('zero-weight fixture parsed: inputs={}, outputs={}'.format(net.num_inputs, net.num_outputs), flush=True)
else:
    for i in range(parser.num_errors): print(parser.get_error(i), flush=True)
    raise RuntimeError('zero-weight fixture failed to parse')

if '--build' in sys.argv:
    import numpy as np
    from standalone_act import TensorRTBackend
    config = builder.create_builder_config()
    config.max_workspace_size = 256 * 1024 * 1024
    print('building zero-weight fixture; not a trained model', flush=True)
    started = time.monotonic()
    engine = builder.build_engine(net, config)
    if engine is None: raise RuntimeError('fixture engine build failed')
    print('fixture build seconds={:.2f}'.format(time.monotonic()-started), flush=True)
    with tempfile.NamedTemporaryFile(suffix='.zero-fixture.engine', delete=False) as f:
        f.write(engine.serialize())
        path = f.name
    del engine, net, parser, builder
    try:
        backend = TensorRTBackend(path)
        data = {'state': np.zeros((1,6), np.float32),
                'top':np.zeros((1,3,480,640), np.float32),
                'side':np.zeros((1,3,480,640), np.float32)}
        try:
            for i in range(3):
                started = time.monotonic()
                result = backend.run(data)
                print('zero-fixture run={} ms={:.1f} finite={} shape={}'.format(
                    i, 1000*(time.monotonic()-started), np.isfinite(result).all(), result.shape), flush=True)
        finally:
            backend.close()
    finally:
        os.unlink(path)

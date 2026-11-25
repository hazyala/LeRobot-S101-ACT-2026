"""Exercise standalone CUDA/TensorRT bindings with a toy graph, no robot."""
import os
import tempfile
import numpy as np
import tensorrt as trt
from standalone_act import TensorRTBackend

logger = trt.Logger(trt.Logger.WARNING)
builder = trt.Builder(logger)
network = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
config = builder.create_builder_config()
config.max_workspace_size = 32 * 1024 * 1024
state = network.add_input('state', trt.float32, (1, 6))
top = network.add_input('top', trt.float32, (1, 3, 480, 640))
side = network.add_input('side', trt.float32, (1, 3, 480, 640))
def mean_2d(x):
    x = network.add_reduce(x, trt.ReduceOperation.AVG, (1 << 1) | (1 << 2) | (1 << 3), True).get_output(0)
    shuffle = network.add_shuffle(x)
    shuffle.reshape_dims = (1, 1)
    return shuffle.get_output(0)

value = network.add_elementwise(state, mean_2d(top), trt.ElementWiseOperation.SUM).get_output(0)
value = network.add_elementwise(value, mean_2d(side), trt.ElementWiseOperation.SUM).get_output(0)
sh = network.add_shuffle(value)
sh.reshape_dims = (1, 1, 6)
concat = network.add_concatenation([sh.get_output(0)] * 100)
concat.axis = 1
output = concat.get_output(0)
output.name = 'action'
network.mark_output(output)
engine = builder.build_engine(network, config)
if engine is None: raise RuntimeError('toy engine build failed')
with tempfile.NamedTemporaryFile(suffix='.engine', delete=False) as f:
    f.write(engine.serialize())
    path = f.name
try:
    backend = TensorRTBackend(path)
    state_data = np.arange(6, dtype=np.float32).reshape(1, 6)
    inputs = {'state': state_data, 'top':np.zeros((1,3,480,640), dtype=np.float32),
              'side':np.zeros((1,3,480,640), dtype=np.float32)}
    try:
        result = backend.run(inputs)
        np.testing.assert_allclose(result, np.tile(state_data[:,None,:], (1,100,1)), atol=1e-5)
        print('TensorRT standalone toy engine passed: shape {}'.format(result.shape), flush=True)
    finally:
        backend.close()
finally:
    os.unlink(path)

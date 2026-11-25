"""Make a zero-weight graph for parser tests; it is NOT a real ACT model."""
import gzip
import json
import os
import sys
import numpy as np
import onnx
from onnx import numpy_helper

source, destination = sys.argv[1:3]
model = onnx.load(source)
changed = 0
constants_changed = 0
for tensor in model.graph.initializer:
    data = numpy_helper.to_array(tensor)
    if data.dtype.kind == 'f':
        name = tensor.name
        zero = np.zeros(data.shape, dtype=data.dtype)
        tensor.CopyFrom(numpy_helper.from_array(zero, name=name))
        changed += 1
for node in model.graph.node:
    if node.op_type != 'Constant': continue
    for attr in node.attribute:
        if attr.name != 'value' or attr.type != onnx.AttributeProto.TENSOR: continue
        data = numpy_helper.to_array(attr.t)
        if data.dtype.kind == 'f' and data.size > 4096:
            attr.t.CopyFrom(numpy_helper.from_array(np.zeros(data.shape, dtype=data.dtype)))
            constants_changed += 1
onnx.checker.check_model(model)
with gzip.open(destination, 'wb', compresslevel=9) as f:
    f.write(model.SerializeToString())
print(json.dumps({'zeroed_initializers':changed, 'zeroed_constants':constants_changed, 'fixture_bytes':os.path.getsize(destination),
                  'warning':'zero weights: parser testing only, never use for robot inference'}))

"""Simplify fixed-shape ACT ONNX graph without changing its learned weights.

Replaces adjacent split-then-concatenate patterns with the original tensor only
when outputs are complete, ordered, axis-matched, and exclusively consumed by
the concat. Result must still be independently compared with the original.
"""
import collections
import sys
import onnx
from onnxsim import simplify

src, dst = sys.argv[1:3]
model, valid = simplify(onnx.load(src), check_n=2)
if not valid: raise RuntimeError('ONNX simplifier verification failed')
nodes = list(model.graph.node)
producers = {out: node for node in nodes for out in node.output}
uses = collections.Counter(value for node in nodes for value in node.input)
graph_outputs = {x.name for x in model.graph.output}
removed = set()
replacements = 0
for node in nodes:
    if node.op_type != 'Concat': continue
    axis = next((onnx.helper.get_attribute_value(a) for a in node.attribute if a.name == 'axis'), 0)
    old = list(node.input)
    new = []
    i = 0
    while i < len(old):
        split = producers.get(old[i])
        if split is not None and split.op_type == 'Split':
            split_axis = next((onnx.helper.get_attribute_value(a) for a in split.attribute if a.name == 'axis'), 0)
            outputs = list(split.output)
            if (axis == split_axis and len(outputs) > 1 and old[i:i+len(outputs)] == outputs
                    and all(uses[o] == 1 and o not in graph_outputs for o in outputs)):
                new.append(split.input[0])
                i += len(outputs)
                removed.add(split.name)
                replacements += 1
                continue
        new.append(old[i]); i += 1
    del node.input[:]
    node.input.extend(new)
if replacements != 2:
    raise RuntimeError('expected two safe split/concat replacements, found {}'.format(replacements))
kept = [node for node in nodes if node.name not in removed]
del model.graph.node[:]
model.graph.node.extend(kept)
onnx.checker.check_model(model)
onnx.save(model, dst)
concat_max = max([len(n.input) for n in model.graph.node if n.op_type == 'Concat'] or [0])
print('safe replacements={}, graph nodes={}, largest concat={}'.format(replacements, len(kept), concat_max), flush=True)

"""Standalone ACT inference, with no LeRobot or PyTorch at runtime.

This program only reads an observation file and writes a 100x6 action plan.
It never opens a robot or sends motor commands. TensorRT execution requires a
validated engine built on the target Jetson. Results are not commissioned for
real robot use until compared with the original model and safety controller.

Observation .npz keys: state (6,), top_bgr and side_bgr (480,640,3 uint8).
"""
import argparse
import ctypes
import hashlib
import json
import os
import time
import numpy as np

NAMES = ['shoulder_pan.pos', 'shoulder_lift.pos', 'elbow_flex.pos',
         'wrist_flex.pos', 'wrist_roll.pos', 'gripper.pos']

def verify_model_hash(path, stats, backend):
    key = 'onnx_sha256' if backend == 'onnx' else 'engine_sha256'
    expected = stats.get(key)
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError('missing model checksum in stats: ' + key)
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''): h.update(chunk)
    if h.hexdigest() != expected:
        raise ValueError('model and statistics do not match')

def load_stats(path):
    with open(path, 'r') as f:
        stats = json.load(f)
    if stats.get('joint_names') != NAMES or stats.get('model') not in ('doll', 'cup'):
        raise ValueError('model or joint order mismatch')
    if stats.get('eps') != 1e-8:
        raise ValueError('unexpected normalization epsilon')
    for key, size in [('observation.state', 6), ('observation.images.top', 3),
                      ('observation.images.side', 3)]:
        for part in ('mean', 'std'):
            x = np.asarray(stats['input'][key][part], dtype=np.float32)
            if x.shape != (size,) or not np.isfinite(x).all():
                raise ValueError('invalid input statistics: ' + key)
            if part == 'std' and np.any(x < 0):
                raise ValueError('negative standard deviation')
    for part in ('mean', 'std'):
        x = np.asarray(stats['action'][part], dtype=np.float32)
        if x.shape != (6,) or not np.isfinite(x).all() or (part == 'std' and np.any(x < 0)):
            raise ValueError('invalid action statistics')
    return stats

def prepare(state, top_bgr, side_bgr, stats):
    state = np.asarray(state, dtype=np.float32)
    if state.shape != (6,) or not np.isfinite(state).all():
        raise ValueError('state must have six finite values')
    arrays = {'state': state.reshape(1, 6)}
    for key, frame in (('top', top_bgr), ('side', side_bgr)):
        frame = np.asarray(frame)
        if frame.shape != (480, 640, 3) or frame.dtype != np.uint8:
            raise ValueError(key + ' must be a 640x480 uint8 BGR image')
        arrays[key] = np.ascontiguousarray(frame[:, :, ::-1].transpose(2, 0, 1)[None], dtype=np.float32) / np.float32(255.)
    for key, feature in (('state','observation.state'), ('top','observation.images.top'),
                         ('side','observation.images.side')):
        item = stats['input'][feature]
        shape = (1, 6) if key == 'state' else (1, 3, 1, 1)
        mean = np.asarray(item['mean'], dtype=np.float32).reshape(shape)
        std = np.asarray(item['std'], dtype=np.float32).reshape(shape)
        arrays[key] = np.ascontiguousarray((arrays[key] - mean) / (std + np.float32(stats['eps'])))
    return arrays

def postprocess(raw, stats):
    raw = np.asarray(raw, dtype=np.float32)
    if raw.shape != (1, 100, 6) or not np.isfinite(raw).all():
        raise ValueError('model output must be finite shape (1,100,6)')
    mean = np.asarray(stats['action']['mean'], dtype=np.float32).reshape(1, 1, 6)
    std = np.asarray(stats['action']['std'], dtype=np.float32).reshape(1, 1, 6)
    result = (raw * std + mean)[0]
    if not np.isfinite(result).all(): raise ValueError('non-finite action')
    return result

class OnnxBackend:
    def __init__(self, model):
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 4
        self.session = ort.InferenceSession(model, sess_options=opts, providers=['CPUExecutionProvider'])
        if set(i.name for i in self.session.get_inputs()) != set(('state','top','side')):
            raise ValueError('unexpected model inputs')
    def run(self, inputs):
        return self.session.run(['action'], inputs)[0]
    def close(self): pass

class TensorRTBackend:
    def __init__(self, engine_path):
        import tensorrt as trt
        self.trt = trt
        self.logger = trt.Logger(trt.Logger.WARNING)
        self.runtime = trt.Runtime(self.logger)
        with open(engine_path, 'rb') as f:
            self.engine = self.runtime.deserialize_cuda_engine(f.read())
        if self.engine is None: raise RuntimeError('TensorRT engine could not be loaded')
        self.context = self.engine.create_execution_context()
        if self.context is None: raise RuntimeError('TensorRT context creation failed')
        self.cuda = ctypes.CDLL('/usr/local/cuda/lib64/libcudart.so')
        self.cuda.cudaMalloc.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_size_t]
        self.cuda.cudaMemcpy.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
        self.cuda.cudaFree.argtypes = [ctypes.c_void_p]
        self.cuda.cudaDeviceSynchronize.argtypes = []

    def _check(self, result, stage):
        if result != 0: raise RuntimeError('CUDA {} failed: {}'.format(stage, result))

    def run(self, inputs):
        names = [self.engine.get_binding_name(i) for i in range(self.engine.num_bindings)]
        if set(names) != set(('state', 'top', 'side', 'action')):
            raise ValueError('unexpected engine bindings: {}'.format(names))
        output = None
        allocations = []
        bindings = [0] * len(names)
        try:
            for i, name in enumerate(names):
                shape = tuple(self.context.get_binding_shape(i))
                if any(int(d) <= 0 for d in shape): raise ValueError('dynamic engine shape not supported')
                if self.trt.nptype(self.engine.get_binding_dtype(i)) != np.float32:
                    raise ValueError('engine binding is not float32')
                if self.engine.binding_is_input(i):
                    host = np.ascontiguousarray(inputs[name], dtype=np.float32)
                    if host.shape != shape: raise ValueError('engine input shape mismatch: ' + name)
                else:
                    if name != 'action' or shape != (1,100,6): raise ValueError('invalid output binding')
                    output = np.empty(shape, dtype=np.float32)
                    host = output
                ptr = ctypes.c_void_p()
                self._check(self.cuda.cudaMalloc(ctypes.byref(ptr), host.nbytes), 'allocate')
                allocations.append(ptr)
                bindings[i] = ptr.value
                if self.engine.binding_is_input(i):
                    self._check(self.cuda.cudaMemcpy(ptr, ctypes.c_void_p(host.ctypes.data), host.nbytes, 1), 'upload')
            if output is None or not self.context.execute_v2(bindings): raise RuntimeError('TensorRT execution failed')
            self._check(self.cuda.cudaDeviceSynchronize(), 'synchronize')
            output_index = names.index('action')
            self._check(self.cuda.cudaMemcpy(ctypes.c_void_p(output.ctypes.data), ctypes.c_void_p(bindings[output_index]), output.nbytes, 2), 'download')
            return output
        finally:
            for ptr in allocations: self.cuda.cudaFree(ptr)

    def close(self):
        self.context = self.engine = self.runtime = None

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--backend', choices=['onnx', 'tensorrt'], required=True)
    p.add_argument('--model', required=True)
    p.add_argument('--stats', required=True)
    p.add_argument('--input', required=True)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    stats = load_stats(args.stats)
    verify_model_hash(args.model, stats, args.backend)
    with np.load(args.input, allow_pickle=False) as obs:
        inputs = prepare(obs['state'], obs['top_bgr'], obs['side_bgr'], stats)
    backend = OnnxBackend(args.model) if args.backend == 'onnx' else TensorRTBackend(args.model)
    try:
        start = time.monotonic()
        result = postprocess(backend.run(inputs), stats)
        elapsed = time.monotonic() - start
    finally:
        backend.close()
    np.savez_compressed(args.output, actions=result)
    print('model={} shape={} inference_ms={:.1f} output={}'.format(stats['model'], result.shape, elapsed*1000, args.output))

if __name__ == '__main__': main()

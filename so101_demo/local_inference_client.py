"""Local two-Python inference bridge; no network and no motor control."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import numpy as np
from policy_link import PolicyLink
from safety import valid_reply, vector

class LocalInference(PolicyLink):
    def __init__(self, engine, stats, worker_path=None):
        super().__init__()
        self.engine = str(Path(engine).resolve())
        self.stats = str(Path(stats).resolve())
        self.worker_path = str(Path(worker_path or Path(__file__).with_name('local_inference_worker.py')).resolve())
        self.ipc_dir = None
        self.extra_paths = None
        self.selected_model = None

    def start(self, model, timeout=45):
        if model not in ('doll','cup') or self.process is not None:
            raise ValueError('invalid model or already running')
        self.ipc_dir = tempfile.mkdtemp(prefix='so101-inference-', dir='/dev/shm')
        command = ['/usr/bin/python3', '-u', self.worker_path, '--engine', self.engine,
                   '--stats', self.stats, '--ipc-dir', self.ipc_dir]
        if self.extra_paths:
            command.extend(['--extra', *self.extra_paths])
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=None, bufsize=0, start_new_session=True)
        os.set_blocking(self.process.stdin.fileno(), False)
        os.set_blocking(self.process.stdout.fileno(), False)
        try:
            reply = self._exchange({'hello':True}, time.monotonic()+timeout)
            if reply != {'ready':True, 'model':model}:
                raise RuntimeError('local worker model mismatch')
        except BaseException:
            self.close()
            raise

    def infer(self, state, top, side, timeout=2.0):
        if self.ipc_dir is None or timeout <= 0: raise ValueError('worker not started or invalid timeout')
        started = time.monotonic()
        state = vector(state, 'state').astype(np.float32)
        for frame in (top, side):
            if not isinstance(frame, np.ndarray) or frame.shape != (480,640,3) or frame.dtype != np.uint8:
                raise ValueError('expected 640x480 BGR uint8 image')
        self.counter += 1
        path = os.path.join(self.ipc_dir, 'observation-{}.npz'.format(self.counter))
        try:
            with open(path, 'xb') as f:
                np.savez(f, state=state, top_bgr=top, side_bgr=side)
            request = {'id':self.counter, 'path':path}
            if self.extra_paths: request['model'] = self.selected_model
            response = self._exchange(request, started+timeout)
            elapsed = time.monotonic()-started
            return valid_reply(self.counter, response, elapsed, timeout), elapsed
        except BaseException:
            self.close()
            raise
        finally:
            if os.path.exists(path): os.unlink(path)

    def close(self):
        try:
            super().close()
        finally:
            root, self.ipc_dir = self.ipc_dir, None
            if root and root.startswith('/dev/shm/so101-inference-'):
                shutil.rmtree(root, ignore_errors=True)

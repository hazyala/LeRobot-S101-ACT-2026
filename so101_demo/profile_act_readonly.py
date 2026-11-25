"""Profile ACT loop without writing any motor registers or recording data."""
import concurrent.futures
import json
import time
import cv2
import numpy as np
import devices
from local_act_demo import Camera, frames, show, state, wait_cameras
from local_inference_client import LocalInference
from preview_window import PreviewWindow

MODEL_ROOT = '/home/aisw/lerobot/tensorrt_candidate/'
def summary(values):
    x = np.asarray(values, dtype=float)*1000
    return {'count':int(x.size), 'p50_ms':round(float(np.percentile(x,50)),1),
            'p95_ms':round(float(np.percentile(x,95)),1),
            'max_ms':round(float(x.max()),1)}

def main():
    cams, bus, worker, pool, preview = [], None, None, None, None
    stages = {x:[] for x in ('camera','preview','state','loop','infer')}
    slow = []
    pending = None
    try:
        cams.append(Camera('/dev/v4l/by-id/*RealSense*405*video-index2'))
        cams.append(Camera('/dev/v4l/by-id/*ABKO*video-index0'))
        wait_cameras(cams)
        bus = devices.open_read_only('follower', '/home/aisw/lerobot/follower.json')
        worker = LocalInference(MODEL_ROOT+'cup.engine', MODEL_ROOT+'cup_engine_stats.json')
        worker.start('cup', timeout=60)
        top, side = frames(cams)
        current = state(bus)
        worker.infer(current, top, side, timeout=10)
        worker.infer(current, top, side, timeout=10)
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        preview = PreviewWindow()
        print('READ-ONLY diagnostic; no motor commands', flush=True)
        for i in range(360):
            tick = time.monotonic()
            mark = tick
            images = frames(cams)
            now = time.monotonic(); stages['camera'].append(now-mark); mark = now
            show(images, 'READ ONLY DIAGNOSTIC', preview=preview)
            now = time.monotonic(); stages['preview'].append(now-mark); mark = now
            current = state(bus)
            now = time.monotonic(); stages['state'].append(now-mark)
            if pending is not None and pending.done():
                try:
                    _, elapsed = pending.result(); stages['infer'].append(elapsed)
                except Exception as exc:
                    slow.append({'step':i,'inference_error':str(exc)})
                pending = None
            if pending is None and i % 60 == 0:
                pending = pool.submit(worker.infer, current, images[0], images[1], 3.)
            elapsed = time.monotonic()-tick
            stages['loop'].append(elapsed)
            if elapsed > .1:
                slow.append({'step':i,'loop_ms':round(elapsed*1000,1),
                             'camera_ms':round(stages['camera'][-1]*1000,1),
                             'preview_ms':round(stages['preview'][-1]*1000,1),
                             'state_ms':round(stages['state'][-1]*1000,1)})
            time.sleep(max(0, 1/30-elapsed))
        print(json.dumps({'stages':{k:summary(v) for k,v in stages.items() if v},
                          'slow':slow, 'note':'motor write and full controller not measured'},
                         allow_nan=False), flush=True)
    finally:
        if worker is not None: worker.close()
        if pool is not None: pool.shutdown(wait=False)
        if bus is not None and bus.is_connected: bus.disconnect(disable_torque=False)
        if preview is not None: preview.close()
        for cam in cams: cam.close()
        cv2.destroyAllWindows()

if __name__ == '__main__': main()

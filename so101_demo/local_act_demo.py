"""Supervised local ACT controller. Requires a commissioned TensorRT model.

The model worker uses the system TensorRT Python, while this controller uses
the Jetson Python 3.12 environment. No remote server and no dataset recording.
Physical commissioning, camera placement, stop behavior and success rates must
be checked before enabling this controller for real operation.
"""
import concurrent.futures
from collections import deque
import json
import os
import time
import cv2
import numpy as np
import devices
from action_planning import DollGripHold, StallMonitor, action_with_early_gripper_close, switch_action_plans
from doll_approach import DollApproach
from local_inference_client import LocalInference
from preview_window import PreviewWindow
from safety import safe_action, STATE_MARGIN
from teleoperation import Camera, TerminalStop, command, state, wait_cameras

ROOT = '/home/aisw/lerobot'
MODEL_ROOT = ROOT + '/tensorrt_candidate'
FPS = 30
APPROACH_REPLAN_STEPS = 20
TRANSFER_REPLAN_STEPS = 60
DEADLINE_S = 0.75
MAX_RUN_SECONDS = 60
HOME = np.array([-5.8, -99.3, 101.05, 74.86, -10., 1.32], dtype=np.float32)
HOME_TOL = np.array([12., 12., 12., 18., 15., 20.], dtype=np.float32)

def is_home(position):
    return bool(np.all(np.abs(position-HOME) <= HOME_TOL))

APPROACH_PAN_TRIM_DEG = -3.0

class ApproachTrim:
    def __init__(self):
        self.peak = float(HOME[1])
        self.finished = False
        self.offset = 0.

    def update(self, lift, scale=1.):
        self.peak = max(self.peak, lift)
        extension = self.peak - HOME[1]
        if extension > 30 and self.peak - lift >= 8:
            self.finished = True
        target = 0. if self.finished else APPROACH_PAN_TRIM_DEG * scale * np.clip((extension-10)/30, 0., 1.)
        self.offset += float(np.clip(target-self.offset, -.1, .1))
        return self.offset

def frames(cameras):
    images, stamps = zip(*(cam.snapshot() for cam in cameras))
    now = time.monotonic()
    if now-min(stamps) > 0.3 or max(stamps)-min(stamps) > 0.2:
        raise RuntimeError('카메라 영상이 오래됐거나 두 카메라 시각 차이가 큽니다.')
    return list(images)

def show(images, status, terminal=None, preview=None):
    if preview is None:
        raise RuntimeError('영상 표시 프로세스가 없습니다.')
    window_key = preview.show(images, status)
    terminal_key = terminal.poll() if terminal is not None else -1
    return terminal_key if terminal_key in (ord('q'),ord('Q'),27) else window_key

def wait_future(future, cameras, status, timeout, terminal=None, preview=None):
    deadline = time.monotonic()+timeout
    while not future.done():
        if show(frames(cameras), status, terminal, preview) in (ord('q'), ord('Q'), 27):
            raise InterruptedError('사용자가 중지했습니다.')
        if time.monotonic() > deadline:
            raise TimeoutError('추론 준비 시간이 초과됐습니다.')
        time.sleep(0.02)
    return future.result()

def model_paths(model):
    if model not in ('cup','doll'): raise ValueError('invalid model')
    # The previously selected 020000 model was an older experiment. 047000
    # is the B200-trained model selected in the successful doll workflow.
    model_dir = MODEL_ROOT + ('/doll047' if model == 'doll' else '')
    stats_path = model_dir+'/'+model+'_engine_stats.json'
    engine_path = model_dir+'/'+model+'.engine'
    return engine_path, stats_path

def preload():
    worker = LocalInference(*model_paths('cup'))
    worker.extra_paths = model_paths('doll')
    try:
        worker.start('cup', timeout=60)
        image = np.zeros((480,640,3), dtype=np.uint8)
        for model in ('cup','doll'):
            worker.selected_model = model
            for _ in range(2):
                worker.infer(HOME, image, image, 15.)
        return worker
    except BaseException:
        worker.close()
        raise

def run(model, prepared=None):
    if not os.environ.get('DISPLAY'): raise RuntimeError('Jetson 화면의 터미널에서 실행하세요.')
    engine_path, stats_path = model_paths(model)
    with open(stats_path) as f: stats = json.load(f)
    if stats.get('model') != model: raise RuntimeError('모델과 통계 파일이 다릅니다.')
    lower = np.asarray(stats['action_min'], dtype=np.float32)
    upper = np.asarray(stats['action_max'], dtype=np.float32)
    if lower.shape != (6,) or upper.shape != (6,) or not np.isfinite(lower).all() or not np.isfinite(upper).all() or np.any(lower>=upper):
        raise ValueError('invalid demonstration action bounds')
    cams, follower, worker, pool, terminal, preview = [], None, None, None, None, None
    enabled = False
    can_return = False
    trace = []
    approach_views = []
    trim = ApproachTrim()
    doll = DollApproach() if model == 'doll' else None
    grip_hold = DollGripHold() if model == 'doll' else None
    try:
        cams.append(Camera('/dev/v4l/by-id/*RealSense*405*video-index2'))
        cams.append(Camera('/dev/v4l/by-id/*ABKO*video-index0'))
        wait_cameras(cams)
        frames(cams)
        follower = devices.open_read_only('follower', ROOT+'/follower.json')
        if model == 'doll':
            from home_return import MotorOverload, torque_state
            torque_state(follower, 'gripper')
        current = state(follower)
        if not is_home(current):
            raise RuntimeError('Follower가 HOME 범위를 벗어났습니다. 시작 자세를 확인하세요.')
        outside = np.flatnonzero((current < lower - STATE_MARGIN) | (current > upper + STATE_MARGIN))
        if len(outside):
            details = ', '.join('{} {:.1f} (허용 {:.1f}~{:.1f})'.format(
                devices.NAMES[i], current[i], lower[i]-STATE_MARGIN[i], upper[i]+STATE_MARGIN[i])
                for i in outside)
            raise RuntimeError('관절이 학습 범위를 벗어나 시작할 수 없습니다: ' + details)
        terminal = TerminalStop()
        preview = PreviewWindow()
        print('모델을 준비합니다. 영상 창 또는 실행 터미널에서 Q를 누르면 정지합니다.', flush=True)
        if show(frames(cams), 'Preparing model - Q: quit', terminal, preview) in (ord('q'), ord('Q'), 27):
            return
        worker = prepared
        if worker is None:
            worker = LocalInference(engine_path, stats_path)
            worker.start(model, timeout=60)
        if show(frames(cams), 'Preparing model - Q: quit', terminal, preview) in (ord('q'), ord('Q'), 27):
            return
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        # Two warm-ups allow the first, often slow, TensorRT execution to finish
        # before any motor command is sent.
        for _ in range(2 if prepared is None else 0):
            current = state(follower)
            top, side = frames(cams)
            future = pool.submit(worker.infer, current, top, side, 10.)
            wait_future(future, cams, 'Warming up - Q: quit', 12., terminal, preview)
        current = state(follower)
        if not is_home(current): raise RuntimeError('시작 중 HOME 위치가 변경됐습니다.')
        top, side = frames(cams)
        seed = pool.submit(worker.infer, current, top, side, DEADLINE_S)
        plan, latency = wait_future(seed, cams, 'Checking latency - Q: quit', DEADLINE_S+0.2, terminal, preview)
        if latency > DEADLINE_S: raise TimeoutError('실행 전 추론 지연 한도를 넘었습니다.')
        current = state(follower)
        if not is_home(current): raise RuntimeError('시작 전 HOME 위치가 변경됐습니다.')
        if show(frames(cams), 'Starting - Q: quit', terminal, preview) in (ord('q'), ord('Q'), 27):
            return
        command(follower, current)
        enabled = True
        follower.enable_torque(num_retry=2)
        can_return = True
        previous = current.copy()
        started = time.monotonic()
        pending, pending_step = None, 0
        # The original doll runner keeps 60 frames so the grasp portion of a
        # chunk can execute. Keep the faster approach refresh for the cup.
        approach_interval = TRANSFER_REPLAN_STEPS if model == 'doll' else APPROACH_REPLAN_STEPS
        next_replan = approach_interval
        step = 0
        index = 0
        home_since = None
        left_home = False
        stalls = StallMonitor()
        loop_times = deque(maxlen=31)
        while True:
            tick = time.monotonic()
            loop_times.append(tick)
            if len(loop_times) == 31 and loop_times[-1]-loop_times[0] > 1.2:
                raise RuntimeError('제어 주파수가 25Hz 미만으로 떨어져 정지합니다.')
            if tick-started >= MAX_RUN_SECONDS:
                print('최대 실행 시간에 도달했습니다. 홈으로 복귀합니다.', flush=True)
                break
            images = frames(cams)
            key = show(images, 'RUNNING  Q: stop', terminal, preview)
            if key in (ord('q'), ord('Q'), 27): break
            can_return = False
            current = state(follower)
            if model == 'doll' and step % FPS == 0:
                try:
                    torque_state(follower, 'gripper')
                except MotorOverload:
                    # Leave the servo fault latched; skip hold/home commands.
                    enabled = False
                    raise
            can_return = bool(np.isfinite(current).all() and
                              np.all(current >= lower-STATE_MARGIN) and
                              np.all(current <= upper+STATE_MARGIN))
            if doll is not None and step % 3 == 0:
                # Use the visual check only to stop after an empty grasp.
                doll.observe(images[0], current[5], trim.finished, images[1])
                if doll.missed:
                    print('그리퍼가 다시 열렸고 인형이 제자리에 있습니다. 홈으로 복귀합니다.', flush=True)
                    break
            if pending is not None:
                if pending.done():
                    new_plan, latency = pending.result()
                    if latency > DEADLINE_S: raise TimeoutError('추론 지연 한도를 넘었습니다.')
                    plan = switch_action_plans(plan[index:], new_plan, step-pending_step)
                    index = 0
                    pending = None
                elif tick-pending_started > DEADLINE_S:
                    raise TimeoutError('추론 시간 초과로 정지합니다.')
            if pending is None and step >= next_replan:
                pending_step = step
                pending_started = time.monotonic()
                model_state = current.copy()
                model_state[0] -= trim.offset
                pending = pool.submit(worker.infer, model_state, images[0], images[1], DEADLINE_S)
                next_replan = step + (TRANSFER_REPLAN_STEPS if trim.finished else approach_interval)
            if index >= len(plan): raise RuntimeError('새 동작 계획이 도착하지 않았습니다.')
            # Both the 047000 doll runner and cup runner use no early close.
            raw = action_with_early_gripper_close(plan, index, 0)
            index += 1
            corrected = raw.copy()
            corrected[0] += trim.update(current[1])
            if grip_hold is not None:
                corrected[5] = grip_hold.target(tick, current[5], corrected[5])
            desired_safe = safe_action(corrected, current, previous, lower, upper)
            # Existing follower driver also caps each target at 5 units from
            # the measured position. Apply the same separate guard here.
            safe = np.clip(desired_safe, current-5., current+5.)
            can_return = False
            command(follower, safe)
            stalls.update(tick, current, desired_safe)
            can_return = True
            sample = (tick-started, step, index-1, current.tolist(), raw.tolist(), safe.tolist(), trim.offset)
            if doll is not None:
                sample += (0.,)
            trace.append(sample)
            if step % 10 == 0:
                # Store at most ~42 MB per 60 s run. Encode only after motor cleanup.
                approach_views.append((step, np.hstack([im[::2, ::2] for im in images])))
            previous = desired_safe
            if not is_home(current):
                left_home = True; home_since = None
            elif left_home and tick-started >= 8:
                if home_since is None: home_since = tick
                elif tick-home_since >= 2: break
            step += 1
            duration = time.monotonic()-tick
            if duration > 0.2: raise RuntimeError('제어 주기가 너무 느려 정지합니다.')
            time.sleep(max(0., 1./FPS-duration))
    finally:
        if follower is not None and follower.is_connected:
            if enabled:
                try:
                    command(follower, state(follower))
                    if can_return:
                        from home_return import return_home
                        return_home(follower, lambda: terminal.poll() in (ord('q'), ord('Q'), 27))
                    else:
                        print('관절 또는 구동 상태를 확인하세요. 현재 자세를 유지합니다.', flush=True)
                except Exception as exc:
                    print('홈 복귀를 완료하지 못했습니다. 팔 상태를 확인하세요: {}'.format(exc), flush=True)
            try: follower.disconnect(disable_torque=False)
            except Exception as exc: print('Follower 연결 정리 실패: {}'.format(exc), flush=True)
        if worker is not None and prepared is None:
            try: worker.close()
            except Exception as exc: print('추론 프로세스 정리 실패: {}'.format(exc), flush=True)
        if pool is not None: pool.shutdown(wait=prepared is not None)
        if terminal is not None:
            try: terminal.close()
            except Exception as exc: print('터미널 설정 복원 실패: {}'.format(exc), flush=True)
        if preview is not None:
            try: preview.close()
            except Exception as exc: print('영상 표시 정리 실패: {}'.format(exc), flush=True)
        for camera in cams:
            try: camera.close()
            except Exception as exc: print('카메라 정리 실패: {}'.format(exc), flush=True)
        try: cv2.destroyAllWindows()
        except Exception: pass
        if trace:
            path = os.path.join(ROOT, 'last_' + model + '_control.json')
            try:
                with open(path+'.tmp', 'w') as stream:
                    fields = ['seconds','step','plan_index','measured','predicted','sent','pan_trim_deg']
                    if doll is not None:
                        fields.append('visual_pan_trim_deg')
                    json.dump({'fields':fields,
                               'samples':trace}, stream)
                os.replace(path+'.tmp', path)
                if approach_views:
                    view_path = os.path.join(ROOT, 'last_' + model + '_views.npz')
                    with open(view_path+'.tmp', 'wb') as stream:
                        packed = {}
                        for frame_step, view in approach_views:
                            ok, jpeg = cv2.imencode('.jpg', view)
                            if ok: packed[str(frame_step)] = jpeg
                        np.savez(stream, **packed)
                    os.replace(view_path+'.tmp', view_path)
            except OSError as exc:
                print('제어 기록 저장 실패: {}'.format(exc), flush=True)

"""Supervised SO-101 teleoperation. No dataset is recorded.

This is a commissioning implementation; do not enable until live hardware
and stop behavior have been verified in the presence of an operator.
"""
import glob
import math
import os
import select
import subprocess
import sys
import threading
import time
import cv2
import numpy as np
import devices
from preview_window import open_fullscreen, show_fullscreen

ROOT = '/home/aisw/lerobot'
MAX_STEP = np.array([1.0, 1.5, 1.5, 2.0, 2.0, 2.5])
MAX_DISTANCE = np.array([5., 5., 5., 5., 5., 5.])

class Camera:
    def __init__(self, pattern):
        paths = glob.glob(pattern)
        if len(paths) != 1:
            raise RuntimeError('Camera not found or ambiguous: ' + pattern)
        self.cap = cv2.VideoCapture(paths[0], cv2.CAP_V4L2)
        if not self.cap.isOpened():
            self.cap.release()
            raise RuntimeError('Cannot open camera: ' + paths[0])
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        if 'RealSense' in pattern:
            try:
                # The D405 exposes sensor exposure through a UVC extension
                # unit, not OpenCV's standard exposure property on Jetson.
                result = None
                for _ in range(3):
                    result = subprocess.run([ROOT + '/d405_exposure_control', paths[0], '0', '10000'],
                                            capture_output=True, text=True, timeout=4)
                    if result.returncode == 0: break
                    time.sleep(0.25)
                if result is None or result.returncode != 0:
                    raise RuntimeError('D405 노출 설정 및 확인 실패')
                if not self.cap.set(cv2.CAP_PROP_GAIN, 16) or abs(self.cap.get(cv2.CAP_PROP_GAIN)-16) > 0.1:
                    raise RuntimeError('D405 게인 설정 및 확인 실패')
            except BaseException:
                self.cap.release()
                raise
        self.lock = threading.Lock()
        self.frame = None
        self.timestamp = 0.
        self.error = None
        self.stop = False
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        while not self.stop:
            ok, frame = self.cap.read()
            if not ok or frame is None or frame.shape != (480, 640, 3):
                self.error = 'camera read failed or unexpected image size'
                return
            with self.lock:
                self.frame = frame
                self.timestamp = time.monotonic()

    def latest(self):
        return self.snapshot()[0]

    def snapshot(self):
        with self.lock:
            if self.error:
                raise RuntimeError(self.error)
            if self.frame is None or time.monotonic() - self.timestamp > 1.0:
                raise RuntimeError('camera frame missing or stale')
            return self.frame.copy(), self.timestamp

    def close(self):
        self.stop = True
        self.thread.join(timeout=2)
        self.cap.release()

def wait_cameras(cameras, timeout=12.0):
    """Allow slow camera startup before any robot or motor connection."""
    deadline = time.monotonic()+timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            return [cam.latest() for cam in cameras]
        except RuntimeError as exc:
            last_error = exc
            if any(cam.error for cam in cameras):
                raise
            time.sleep(0.1)
    raise RuntimeError('카메라 준비 시간 초과: {}'.format(last_error))

def state(bus):
    pos = devices.read_positions(bus)
    return np.array([pos[n] for n in devices.NAMES], dtype=float)

def command(bus, values):
    if len(values) != 6 or not all(math.isfinite(float(x)) for x in values):
        raise ValueError('invalid motor target')
    bus.sync_write('Goal_Position', dict(zip(devices.NAMES, map(float, values))), num_retry=2)

def calibrated_bounds(bus):
    lower, upper = [], []
    for name in devices.NAMES:
        calibration = bus.calibration[name]
        if calibration.range_min >= calibration.range_max:
            raise ValueError('invalid calibration bounds')
        if name == 'gripper':
            lower.append(0.0); upper.append(100.0)
        else:
            half = (calibration.range_max - calibration.range_min) * 180.0 / 4095.0
            lower.append(-half); upper.append(half)
    return np.array(lower), np.array(upper)

def preview_frame(cameras):
    """Display camera status independently of Leader/Follower control."""
    panels = []
    for name, cam in zip(('TOP', 'SIDE'), cameras):
        try:
            if cam is None: raise RuntimeError('camera unavailable')
            image = cam.latest()
        except RuntimeError:
            image = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(image, name + ': CAMERA UNAVAILABLE', (18, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 180, 255), 2)
        panels.append(image)
    if len(panels) != 2:
        raise ValueError('expected top and side camera slots')
    view = np.hstack(panels)
    cv2.putText(view, 'Q: return HOME and exit', (12, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
    return view

class TerminalStop:
    """Read Q from the launch terminal without needing Enter."""
    def __init__(self):
        self.fd = None
        self.saved = None
        if os.name == 'posix' and sys.stdin.isatty():
            import termios
            import tty
            self.fd = sys.stdin.fileno()
            self.saved = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)

    def poll(self):
        if self.fd is None:
            return -1
        ready, _, _ = select.select([self.fd], [], [], 0)
        if not ready:
            return -1
        data = os.read(self.fd, 1)
        return data[0] if data else -1

    def close(self):
        if self.fd is not None and self.saved is not None:
            import termios
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)
            self.fd = None

def run():
    if not __import__('os').environ.get('DISPLAY'):
        raise RuntimeError('Jetson의 화면에서 터미널을 열어 실행하세요.')
    leader = follower = None
    cams = [None, None]
    follower_started = False
    can_return = False
    terminal = None
    try:
        leader = devices.open_read_only('leader', ROOT + '/leader.json')
        follower = devices.open_read_only('follower', ROOT + '/follower.json')
        lower, upper = calibrated_bounds(follower)
        current = state(follower)
        leader_position = state(leader)
        if np.any(np.abs(current[:5] - leader_position[:5]) > 25):
            raise RuntimeError('Leader와 Follower 자세 차이가 큽니다. 메뉴에서 0을 선택하면 Follower가 홈으로 돌아갑니다.')
        for i, pattern in enumerate(('/dev/v4l/by-id/*RealSense*405*video-index2',
                                     '/dev/v4l/by-id/*ABKO*video-index0')):
            try:
                cams[i] = Camera(pattern)
            except Exception as exc:
                print('카메라 미리보기 생략: {}'.format(exc), flush=True)
        open_fullscreen('SO-101 teleoperation')
        show_fullscreen('SO-101 teleoperation', preview_frame(cams))
        cv2.waitKey(1)
        terminal = TerminalStop()
        leader.disable_torque(num_retry=2)
        current = state(follower)
        command(follower, current)
        # Mark before the operation: an error may occur after some motors have
        # already enabled, and the cleanup path must still attempt a hold.
        follower_started = True
        follower.enable_torque(num_retry=2)
        can_return = True
        print('텔레오퍼레이션 시작. Q를 누르면 홈 자세로 복귀합니다.', flush=True)
        previous = current.copy()
        while True:
            start = time.monotonic()
            show_fullscreen('SO-101 teleoperation', preview_frame(cams))
            key = cv2.waitKey(1) & 255
            terminal_key = terminal.poll()
            if key in (ord('q'), ord('Q'), 27) or terminal_key in (ord('q'), ord('Q'), 27): break
            can_return = False
            current = state(follower)
            can_return = True
            desired = np.clip(state(leader), lower, upper)
            bounded = previous + np.clip(desired - previous, -MAX_STEP, MAX_STEP)
            bounded = np.clip(bounded, current - MAX_DISTANCE, current + MAX_DISTANCE)
            can_return = False
            command(follower, bounded)
            can_return = True
            previous = bounded
            time.sleep(max(0, 0.05 - (time.monotonic() - start)))
    finally:
        if follower is not None and follower.is_connected:
            if follower_started:
                try:
                    command(follower, state(follower))
                    if can_return:
                        from home_return import return_home
                        return_home(follower, lambda: terminal.poll() in (ord('q'), ord('Q'), 27)
                                    or (cv2.waitKey(1) & 255) in (ord('q'), ord('Q'), 27))
                    else:
                        print('Follower 구동 상태를 확인하세요. 현재 자세를 유지합니다.', flush=True)
                except Exception as ex:
                    print('홈 복귀를 완료하지 못했습니다. 팔 상태를 확인하세요: {}'.format(ex), flush=True)
            try:
                follower.disconnect(disable_torque=False)
            except Exception as ex:
                print('Follower 연결 정리 실패: {}'.format(ex), flush=True)
        if leader is not None and leader.is_connected:
            try:
                leader.disconnect(disable_torque=False)
            except Exception as ex:
                print('Leader 연결 정리 실패: {}'.format(ex), flush=True)
        if terminal is not None:
            try:
                terminal.close()
            except Exception as ex:
                print('터미널 설정 복원 실패: {}'.format(ex), flush=True)
        for cam in cams:
            if cam is not None:
                try: cam.close()
                except Exception as ex: print('카메라 정리 실패: {}'.format(ex), flush=True)
        try: cv2.destroyAllWindows()
        except Exception: pass

"""Supervised return to the calibrated demonstration home pose."""
import time
import numpy as np
import devices
from teleoperation import TerminalStop, state, command, calibrated_bounds

HOME = np.array([-5.8, -99.3, 101.05, 74.86, -10., 1.32])
TOL = np.array([3., 3., 3., 5., 5., 5.])
SPEED = np.array([12., 12., 12., 15., 12., 15.])

class MotorOverload(RuntimeError):
    pass

def torque_state(bus, name):
    try:
        return int(bus.read('Torque_Enable', name, normalize=False, num_retry=1))
    except Exception as exc:
        if 'overload' in str(exc).lower():
            raise MotorOverload(f'{name} 모터 과부하. 팔을 지지하고 전원을 끈 뒤 걸림과 발열을 확인하세요. ({exc})') from exc
        raise

def return_home(bus, cancelled=lambda: False, clock=time.monotonic, sleep=time.sleep):
    current = state(bus)
    target = HOME.copy()
    lower, upper = calibrated_bounds(bus)
    if np.any(target < lower) or np.any(target > upper):
        raise RuntimeError('홈 자세가 캘리브레이션 범위를 벗어났습니다.')
    if np.all(np.abs(current-target) <= TOL):
        bus.disable_torque(num_retry=2)
        print('홈 자세에서 토크를 해제했습니다.', flush=True)
        return
    torque = [torque_state(bus, name) for name in devices.NAMES]
    if any(int(x) != 1 for x in torque):
        raise RuntimeError('모터 토크 상태를 확인하세요. 홈 복귀를 시작하지 않았습니다.')
    print('홈 자세로 천천히 복귀합니다. 도중에 실행 터미널에서 Q를 누르면 정지합니다.', flush=True)
    previous = current.copy()
    start = last = clock()
    stable_since = None
    progress_at = start
    progress_position = current.copy()
    try:
        while True:
            if cancelled():
                raise InterruptedError('홈 복귀를 중지했습니다.')
            now = clock()
            if now-start > 45:
                raise TimeoutError('홈 복귀 시간이 초과됐습니다.')
            current = state(bus)
            if np.all(np.abs(current-target) <= TOL):
                if stable_since is None: stable_since = now
                if now-stable_since >= 1.0:
                    command(bus, current)
                    bus.disable_torque(num_retry=2)
                    print('홈 자세 복귀를 완료하고 토크를 해제했습니다.', flush=True)
                    return
            else:
                stable_since = None
            dt = min(max(now-last, 0.0), 0.05)
            proposed = previous + np.clip(target-previous, -SPEED*dt, SPEED*dt)
            proposed = np.clip(proposed, current-5., current+5.)
            command(bus, proposed)
            previous = proposed
            last = now
            if now-progress_at >= 4.0:
                stuck = (np.abs(proposed-current) > 2.) & (np.abs(current-progress_position) < 0.2)
                if np.any(stuck):
                    raise RuntimeError('관절 움직임을 확인할 수 없어 홈 복귀를 중지했습니다.')
                progress_at, progress_position = now, current.copy()
            sleep(0.05)
    except BaseException:
        try: command(bus, state(bus))
        except Exception: print('정지 명령 전달 실패: 로봇 전원을 직접 차단하세요.', flush=True)
        raise

def run():
    bus = terminal = None
    try:
        bus = devices.open_read_only('follower', '/home/aisw/lerobot/follower.json')
        terminal = TerminalStop()
        return_home(bus, lambda: terminal.poll() in (ord('q'), ord('Q'), 27))
    finally:
        if terminal is not None: terminal.close()
        if bus is not None and bus.is_connected: bus.disconnect(disable_torque=False)

"""Cup-only HOME -> torque off -> bounded resource cleanup, without console input."""
import threading
import time


def close_cameras(cameras, timeout=2.0):
    threads = []
    for camera in cameras.values():
        def close(camera=camera):
            try:
                if camera.is_connected:
                    camera.disconnect()
            except Exception as error:
                print(f'Camera shutdown: {error}', flush=True)
        worker = threading.Thread(target=close, daemon=True)
        worker.start()
        threads.append(worker)
    deadline = time.monotonic() + timeout
    for worker in threads:
        worker.join(timeout=max(0, deadline-time.monotonic()))


def shutdown_robot(safe, robot, names, low, high, fps, emergency):
    bus = robot.bus
    try:
        if bus.is_connected:
            if not emergency:
                # The existing episode controller already stabilizes at this HOME.
                # Do not demand a second, tighter HOME or wait for RELEASE input.
                observation = safe.read_motor_observation(robot)
                reached = safe.is_home(observation)
                if not reached:
                    reached = safe.return_home_and_stabilize(robot, names, low, high, fps)
                if not reached:
                    raise RuntimeError('HOME 복귀 실패: 토크를 유지합니다. 로봇 상태를 확인하세요.')
            bus.disable_torque(num_retry=robot.config.num_write_retries)
            bus.disconnect(disable_torque=False)
            print('HOME 종료 처리 완료 · 토크 OFF', flush=True)
    finally:
        close_cameras(robot.cameras)
        safe.cv2.destroyAllWindows()

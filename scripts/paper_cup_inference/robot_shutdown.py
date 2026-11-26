"""로봇 종료와 카메라 연결 해제."""
import threading

import cv2

import inference_control as control


# 긴급 정지는 홈 이동 없이 종료 · 일반 종료는 필요 시 홈 복귀
def shutdown(robot, names, low, high, fps, emergency, started):
    bus = robot.bus
    try:
        if bus.is_connected:
            if not emergency and started:
                observation = control.read_motor_observation(robot)
                if not control.is_home(observation):
                    if not control.return_home_and_stabilize(robot, names, low, high, fps):
                        print("홈 복귀 실패 · 현재 위치에서 토크를 해제합니다.", flush=True)
    finally:
        # 홈 복귀 실패나 오류가 발생해도 토크 해제 시도
        if bus.is_connected:
            try:
                bus.disable_torque(num_retry=3)
                print("토크 해제 명령 완료 · 팔이 내려갈 수 있습니다.", flush=True)
            except Exception as error:
                print(f"토크 해제 실패 · 로봇 전원을 확인하세요: {error}", flush=True)
            finally:
                try:
                    bus.disconnect(disable_torque=False)
                except Exception as error:
                    print(f"로봇 연결 해제 실패: {error}", flush=True)
        # 카메라별 연결 해제 대기 시간 제한
        threads = []
        for camera in robot.cameras.values():
            def close(item=camera):
                try:
                    if item.is_connected:
                        item.disconnect()
                except Exception as error:
                    print(f"카메라 종료 실패: {error}", flush=True)
            thread = threading.Thread(target=close, daemon=True)
            thread.start()
            threads.append(thread)
        for thread in threads:
            thread.join(timeout=1)
        cv2.destroyAllWindows()

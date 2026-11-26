"""종이컵 ACT 추론과 로봇 제어. 기존 종이컵 실행 로직 기반."""
import argparse
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor

import cv2
import numpy as np
import torch
from lerobot.policies.act import ACTPolicy
from lerobot.policies.utils import build_inference_frame
from lerobot.utils.robot_utils import precise_sleep

WINDOW_NAME = "SO-101 Paper Cup ACT"
PLAN_SWITCH_BLEND_FRAMES = 8  # 새 행동으로 전환할 때 혼합할 프레임 수
MIN_COMPLETION_TIME_S = 8.0  # 홈 복귀 완료 판정 전 최소 실행 시간
HOME_STABLE_TIME_S = 2.0  # 홈 자세 유지 시간
HOME_RETURN_TIMEOUT_S = 25.0  # 종료 시 홈 복귀 최대 대기 시간
# 수집 코드의 홈 자세. 로봇별 캘리브레이션 후 확인
HOME_POSE = {"shoulder_pan.pos": -5.8, "shoulder_lift.pos": -99.3,
             "elbow_flex.pos": 101.05, "wrist_flex.pos": 74.86, "gripper.pos": 1.32}
HOME_TOLERANCE = {"shoulder_pan.pos": 12, "shoulder_lift.pos": 12,
                  "elbow_flex.pos": 12, "wrist_flex.pos": 18, "gripper.pos": 20}
# 한 제어 주기에서 관절별 목표값 변화 제한
MAX_DELTA_PER_STEP = {"shoulder_pan.pos": 2.0, "shoulder_lift.pos": 3.0,
    "elbow_flex.pos": 3.0, "wrist_flex.pos": 4.0, "wrist_roll.pos": 4.0, "gripper.pos": 5.0}
# 현재 관절 위치와 목표값의 최대 차이
MAX_TRACKING_ERROR = {"shoulder_pan.pos": 6.0, "shoulder_lift.pos": 10.0,
    "elbow_flex.pos": 10.0, "wrist_flex.pos": 10.0, "wrist_roll.pos": 8.0, "gripper.pos": 10.0}
STALL_JOINTS = ("shoulder_lift.pos", "elbow_flex.pos", "wrist_flex.pos")
STALL_WINDOW_S, STALL_MIN_DEMAND, STALL_MIN_MOVEMENT = 4.0, 8.0, 0.15
# 현재 관절이 학습 범위를 벗어났는지 확인할 여유 범위
STATE_WATCHDOG_MARGIN = np.array([20., 20., 20., 25., 30., 20.], dtype=np.float32)
MAX_RAW_RANGE_VIOLATION_FRACTION = 0.25

# 관측값을 학습 당시 관절 순서로 정리
def state_vector(observation: dict, action_names: list[str]) -> np.ndarray:
    values = np.asarray([observation[name] for name in action_names], dtype=np.float32)
    if not np.isfinite(values).all():
        raise RuntimeError("Robot observation contains NaN or Inf.")
    return values


# 현재 관절값이 학습 범위에서 크게 벗어나는지 확인
def validate_state_watchdog(
    observation: dict,
    action_names: list[str],
    action_min: np.ndarray,
    action_max: np.ndarray,
) -> np.ndarray:
    current = state_vector(observation, action_names)
    low = action_min - STATE_WATCHDOG_MARGIN
    high = action_max + STATE_WATCHDOG_MARGIN
    outside = np.flatnonzero((current < low) | (current > high))
    if len(outside):
        details = ", ".join(
            f"{action_names[i]}={current[i]:.2f} not in [{low[i]:.2f}, {high[i]:.2f}]"
            for i in outside
        )
        raise RuntimeError(f"State watchdog stopped execution: {details}")
    return current


# 카메라 영상과 관절 상태로 행동 묶음 예측 · 정규화 복원
def predict_chunk(
    observation: dict,
    policy: ACTPolicy,
    preprocess,
    postprocess,
    inference_features: dict,
    task: str,
) -> tuple[np.ndarray, float]:
    frame = build_inference_frame(
        observation=observation,
        ds_features=inference_features,
        device=torch.device("cuda"),
        task=task,
        robot_type="so101_follower",
    )
    batch = preprocess(frame)
    torch.cuda.synchronize()
    started_at = time.perf_counter()
    with torch.inference_mode():
        chunk = policy.predict_action_chunk(batch)
    torch.cuda.synchronize()
    inference_ms = (time.perf_counter() - started_at) * 1000.0
    chunk = postprocess(chunk)[0].cpu().numpy()
    if chunk.shape != (policy.config.chunk_size, 6):
        raise RuntimeError(f"Unexpected policy output shape: {chunk.shape}")
    if not np.isfinite(chunk).all():
        raise RuntimeError("Policy output contains NaN or Inf.")
    return chunk, inference_ms


# 비동기 추론 중 원본 영상이 바뀌지 않도록 복사
def copy_observation(observation: dict) -> dict:
    return {
        key: value.copy() if isinstance(value, np.ndarray) else value
        for key, value in observation.items()
    }


# 기존 행동과 새 행동을 짧게 섞어 급격한 전환 완화
def switch_action_plans(
    old_remaining: np.ndarray,
    new_chunk: np.ndarray,
    new_chunk_offset: int,
) -> np.ndarray:
    """기존 행동과 새 행동의 전환을 부드럽게 연결."""
    offset = min(max(int(new_chunk_offset), 0), len(new_chunk) - 1)
    new_aligned = new_chunk[offset:]
    if len(old_remaining) == 0:
        return new_aligned.copy()

    switched = new_aligned.copy()
    blend_frames = min(PLAN_SWITCH_BLEND_FRAMES, len(old_remaining), len(switched))
    if blend_frames:
        alpha = (
            np.arange(1, blend_frames + 1, dtype=np.float32) / (blend_frames + 1)
        )[:, None]
        switched[:blend_frames] = (
            (1.0 - alpha) * old_remaining[:blend_frames]
            + alpha * switched[:blend_frames]
        )
        # 행동 전환 중 새 그리퍼 닫기 명령이 늦어지지 않도록 처리
        switched[:blend_frames, 5] = np.maximum(
            switched[:blend_frames, 5], new_aligned[:blend_frames, 5]
        )
    return switched


# 학습 행동 범위, 관절별 변화량, 현재 위치와의 차이 제한
def make_safe_action(
    raw_values: np.ndarray,
    observation: dict,
    action_names: list[str],
    action_min: np.ndarray,
    action_max: np.ndarray,
    previous_command: np.ndarray | None = None,
) -> tuple[dict[str, float], dict[str, bool | float]]:
    raw = np.asarray(raw_values, dtype=np.float32)
    if raw.shape != (6,) or not np.isfinite(raw).all():
        raise RuntimeError("Invalid policy action; expected six finite values.")

    action_range = action_max - action_min
    low_violation = np.maximum(action_min - raw, 0.0)
    high_violation = np.maximum(raw - action_max, 0.0)
    violation_fraction = float(np.max((low_violation + high_violation) / action_range))
    if violation_fraction > MAX_RAW_RANGE_VIOLATION_FRACTION:
        raise RuntimeError(
            "Policy action exceeded the demonstrated range by more than "
            f"{MAX_RAW_RANGE_VIOLATION_FRACTION * 100:.0f}% (actual {violation_fraction * 100:.1f}%)."
        )

    absolute_clipped = np.clip(raw, action_min, action_max)
    current = state_vector(observation, action_names)
    max_delta = np.asarray([MAX_DELTA_PER_STEP[name] for name in action_names], dtype=np.float32)
    max_tracking_error = np.asarray(
        [MAX_TRACKING_ERROR[name] for name in action_names], dtype=np.float32
    )

    # 이전 명령 기준으로 목표값을 조금씩 변경해 관절이 정체되지 않도록 처리
    command_base = current if previous_command is None else np.asarray(previous_command, dtype=np.float32)
    command_delta = np.clip(absolute_clipped - command_base, -max_delta, max_delta)
    slewed = command_base + command_delta

    # 누적된 목표값이 실제 관절 위치에서 지나치게 멀어지지 않도록 제한
    tracking_low = current - max_tracking_error
    tracking_high = current + max_tracking_error
    safe = np.clip(slewed, tracking_low, tracking_high)
    safe = np.clip(safe, action_min, action_max)

    flags: dict[str, bool | float] = {
        "range_clipped": bool(np.any(np.abs(absolute_clipped - raw) > 1e-5)),
        "rate_limited": bool(np.any(np.abs(slewed - absolute_clipped) > 1e-5)),
        "tracking_limited": bool(np.any(np.abs(safe - slewed) > 1e-5)),
        "violation_fraction": violation_fraction,
    }
    return {name: float(safe[i]) for i, name in enumerate(action_names)}, flags


class JointStallError(RuntimeError):
    pass


class EmergencyStop(RuntimeError):
    pass


# 관절이 명령을 받았지만 일정 시간 움직이지 않는 상태 감지
class StallMonitor:
    """명령을 받아도 움직이지 않는 관절 감지."""

    def __init__(self, action_names: list[str]) -> None:
        self.action_names = action_names
        self.indices = {name: action_names.index(name) for name in STALL_JOINTS}
        self.history: deque[tuple[float, np.ndarray, np.ndarray]] = deque()

    def reset(self) -> None:
        self.history.clear()

    def update(self, now: float, current: np.ndarray, command: np.ndarray) -> None:
        self.history.append((now, current.copy(), command.copy()))
        while self.history and now - self.history[0][0] > STALL_WINDOW_S:
            self.history.popleft()
        if len(self.history) < 2 or now - self.history[0][0] < STALL_WINDOW_S * 0.8:
            return

        _, oldest_position, _ = self.history[0]
        stalled: list[str] = []
        for name, index in self.indices.items():
            movement = abs(float(current[index] - oldest_position[index]))
            demand = abs(float(command[index] - current[index]))
            if demand >= STALL_MIN_DEMAND and movement < STALL_MIN_MOVEMENT:
                stalled.append(f"{name} demand={demand:.2f}, movement={movement:.2f}")
        if stalled:
            raise JointStallError("Joint stall watchdog paused execution: " + "; ".join(stalled))


# 수집에 사용한 홈 자세와 허용 오차 확인
def is_home(observation: dict) -> bool:
    return all(
        abs(float(observation[key]) - target) <= HOME_TOLERANCE[key]
        for key, target in HOME_POSE.items()
    )


# 홈 기준에서 가장 많이 벗어난 관절 확인
def largest_home_error(observation: dict) -> tuple[str, float, float]:
    errors = [
        (
            key,
            abs(float(observation[key]) - HOME_POSE[key]),
            HOME_TOLERANCE[key],
        )
        for key in HOME_POSE
    ]
    return max(errors, key=lambda item: item[1] / item[2])


# 카메라 없이 현재 모터 위치 읽기
def read_motor_observation(robot) -> dict[str, float]:
    positions = robot.bus.sync_read(
        "Present_Position",
        num_retry=robot.config.num_read_retries,
    )
    return {f"{motor}.pos": float(value) for motor, value in positions.items()}


# 학습 행동 범위 안에서 홈 복귀 후 정지 확인
def return_home_and_stabilize(
    robot,
    action_names: list[str],
    action_min: np.ndarray,
    action_max: np.ndarray,
    fps: int,
) -> bool:
    """홈 자세로 돌아가 일정 시간 유지."""
    print("\nReturning to HOME before torque release. Press E only for an emergency stop.")
    initial = read_motor_observation(robot)
    fixed_wrist_roll = initial["wrist_roll.pos"]
    home_target = np.asarray(
        [
            HOME_POSE.get(name, fixed_wrist_roll if name == "wrist_roll.pos" else initial[name])
            for name in action_names
        ],
        dtype=np.float32,
    )
    home_target = np.clip(home_target, action_min, action_max)
    previous_command: np.ndarray | None = None
    started_at = time.perf_counter()
    stable_since: float | None = None
    last_reported_second = -1

    while time.perf_counter() - started_at < HOME_RETURN_TIMEOUT_S:
        loop_started_at = time.perf_counter()
        if cv2.waitKey(1) & 0xFF == ord("e"):
            robot.bus.disable_torque(num_retry=3)
            raise EmergencyStop("Emergency torque-off during HOME return.")

        observation = read_motor_observation(robot)
        safe_action, _ = make_safe_action(
            home_target,
            observation,
            action_names,
            action_min,
            action_max,
            previous_command,
        )
        previous_command = np.asarray([safe_action[name] for name in action_names], dtype=np.float32)
        robot.send_action(safe_action)

        now = time.perf_counter()
        at_home = is_home(observation)
        if at_home:
            stable_since = now if stable_since is None else stable_since
            if now - stable_since >= HOME_STABLE_TIME_S:
                print("HOME reached and stable. Torque may now be released.")
                return True
        else:
            stable_since = None

        elapsed_second = int(now - started_at)
        if elapsed_second != last_reported_second:
            joint, diff, tolerance = largest_home_error(observation)
            print(
                f"  HOME {elapsed_second:2d}s: {joint} error {diff:.2f} "
                f"(tolerance {tolerance:.2f})"
            )
            last_reported_second = elapsed_second
        precise_sleep(max(0.0, 1.0 / fps - (time.perf_counter() - loop_started_at)))

    print(f"HOME return timed out after {HOME_RETURN_TIMEOUT_S:.0f}s.")
    return False


# RGB 영상을 미리보기용 BGR로 변환
def bgr_image(image: np.ndarray) -> np.ndarray:
    if image is None or image.ndim != 3 or image.shape[2] != 3:
        return np.zeros((480, 640, 3), dtype=np.uint8)
    if image.dtype != np.uint8:
        image = np.clip(image, 0, 255).astype(np.uint8)
    return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)


# TOP·SIDE 영상과 추론 상태, 키 안내 표시
def draw_status(
    observation: dict,
    status: str,
    episode: int,
    elapsed_s: float,
    inference_ms: float | None,
    limit_counts: dict[str, int],
) -> int:
    top = bgr_image(observation.get("top"))
    side = bgr_image(observation.get("side"))
    canvas = np.hstack([top, side])
    overlay = canvas.copy()
    cv2.rectangle(overlay, (0, 0), (canvas.shape[1], 118), (0, 0, 0), -1)
    canvas = cv2.addWeighted(overlay, 0.68, canvas, 0.32, 0)
    cv2.putText(canvas, "ACT PICK & PLACE", (20, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 80, 255), 2)
    cv2.putText(
        canvas,
        f"{status}  EP {episode}  TIME {elapsed_s:5.1f}s  INFER {inference_ms or 0:5.1f}ms  "
        f"RANGE {limit_counts['range']} RATE {limit_counts['rate']} FOLLOW {limit_counts['tracking']}",
        (20, 70),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.72,
        (255, 255, 255),
        2,
    )
    cv2.putText(
        canvas,
        "SPACE=start/resume   P=pause   Q=HOME+stop   E=EMERGENCY torque off",
        (20, 105),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.68,
        (255, 255, 255),
        2,
    )
    cv2.imshow(WINDOW_NAME, canvas)
    if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
        return ord("q")
    return cv2.waitKey(1) & 0xFF


# 홈 자세 확인 후 SPACE 입력 대기
def wait_for_space(robot, action_names: list[str], action_min: np.ndarray, action_max: np.ndarray):
    print("Place the robot near the recorded HOME pose and focus the OpenCV window.")
    print("Press SPACE to start, Q to stop, or E for immediate torque-off.")
    while True:
        observation = robot.get_observation()
        validate_state_watchdog(observation, action_names, action_min, action_max)
        at_home = is_home(observation)
        status = "HOME: OK - SPACE TO START" if at_home else "HOME: NO - CHECK START POSE"
        key = draw_status(
            observation,
            status,
            0,
            0.0,
            None,
            {"range": 0, "rate": 0, "tracking": 0},
        )
        if key == ord("e"):
            robot.bus.disable_torque(num_retry=3)
            raise EmergencyStop("Emergency torque-off requested.")
        if key in (ord("q"), 27):
            raise KeyboardInterrupt("Stopped before execution.")
        if key == ord(" "):
            if not at_home:
                joint, diff, tolerance = largest_home_error(observation)
                print(f"Cannot start: {joint} differs from HOME by {diff:.2f} (limit {tolerance:.2f}).")
                continue
            return observation
        precise_sleep(1.0 / 30.0)


# 행동 예측과 로봇 제어를 반복하고 종료 조건 확인
def run_episode(
    robot,
    args: argparse.Namespace,
    runtime: tuple,
    on_start,
) -> str:
    task, policy, preprocess, postprocess, inference_features, action_names, action_min, action_max = runtime
    observation = wait_for_space(robot, action_names, action_min, action_max)
    on_start()

    # 실제 움직임 전에 두 번 예측해 GPU 초기화
    for _ in range(2):
        _, warmup_ms = predict_chunk(observation, policy, preprocess, postprocess, inference_features, task)
    print(f"Warm-up inference: {warmup_ms:.1f} ms")

    # 비동기 추론에 사용할 작업 스레드에서도 첫 예측 실행
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="act-inference") as inference_pool:
        seed_future = inference_pool.submit(
            predict_chunk,
            copy_observation(observation),
            policy,
            preprocess,
            postprocess,
            inference_features,
            task,
        )
        plan, inference_ms = seed_future.result()
        started_at = time.perf_counter()
        plan_index = 0
        limit_counts = {"range": 0, "rate": 0, "tracking": 0}
        left_home = False
        home_since: float | None = None
        paused = False
        pause_reason = ""
        previous_command: np.ndarray | None = None
        stall_monitor = StallMonitor(action_names)
        pending_inference: Future | None = None
        pending_start_step = 0
        pending_generation = 0
        plan_generation = 0
        control_step = 0
        next_replan_step = args.replan_every

        while True:
            loop_started_at = time.perf_counter()
            elapsed_s = loop_started_at - started_at
            observation = robot.get_observation()
            validate_state_watchdog(observation, action_names, action_min, action_max)

            if pending_inference is not None and pending_inference.done():
                try:
                    new_chunk, new_inference_ms = pending_inference.result()
                except BaseException:
                    raise
                if new_inference_ms > args.max_inference_ms:
                    raise RuntimeError(
                        f"Inference watchdog stopped execution: {new_inference_ms:.1f} ms exceeds "
                        f"{args.max_inference_ms:.1f} ms."
                    )
                inference_ms = new_inference_ms
                if pending_generation == plan_generation:
                    elapsed_control_steps = max(0, control_step - pending_start_step)
                    plan = switch_action_plans(
                        plan[plan_index:],
                        new_chunk,
                        elapsed_control_steps,
                    )
                    plan_index = 0
                pending_inference = None

            if (
                not paused
                and pending_inference is None
                and control_step >= next_replan_step
            ):
                pending_start_step = control_step
                pending_generation = plan_generation
                pending_inference = inference_pool.submit(
                    predict_chunk,
                    copy_observation(observation),
                    policy,
                    preprocess,
                    postprocess,
                    inference_features,
                    task,
                )
                next_replan_step = control_step + args.replan_every

            key = draw_status(
                observation,
                pause_reason if paused else "RUNNING",
                1,
                elapsed_s,
                inference_ms,
                limit_counts,
            )
            if key == ord("e"):
                robot.bus.disable_torque(num_retry=3)
                return "emergency"
            if key in (ord("q"), 27):
                return "stopped"
            if key == ord("p"):
                paused = True
                pause_reason = "USER PAUSED"
                plan = np.empty((0, 6), dtype=np.float32)
                plan_index = 0
                plan_generation += 1
                previous_command = None
                stall_monitor.reset()
                print("Paused. The last target is held; press SPACE to resume or Q to stop.")
            elif key == ord(" ") and paused:
                paused = False
                pause_reason = ""
                next_replan_step = control_step
                print("Resumed.")

            if paused:
                precise_sleep(max(0.0, 1.0 / args.fps - (time.perf_counter() - loop_started_at)))
                if elapsed_s >= args.max_duration_s:
                    return "timeout"
                continue

            if plan_index < len(plan):
                raw_values = plan[plan_index].copy()
                plan_index += 1
            else:
                # 다음 행동이 아직 준비되지 않으면 현재 관절 위치 유지
                raw_values = state_vector(observation, action_names)
            control_step += 1
            safe_action, flags = make_safe_action(
                raw_values,
                observation,
                action_names,
                action_min,
                action_max,
                previous_command,
            )
            if flags["range_clipped"]:
                limit_counts["range"] += 1
            if flags["rate_limited"]:
                limit_counts["rate"] += 1
            if flags["tracking_limited"]:
                limit_counts["tracking"] += 1

            safe_values = np.asarray([safe_action[name] for name in action_names], dtype=np.float32)
            previous_command = safe_values

            actually_sent = robot.send_action(safe_action)
            if set(actually_sent) != set(action_names):
                raise RuntimeError("Robot did not acknowledge all six joint commands.")
            try:
                stall_monitor.update(
                    time.perf_counter(),
                    state_vector(observation, action_names),
                    safe_values,
                )
            except JointStallError as exc:
                # 관절 정체 시 현재 자세 유지 · 상태 확인 후 재개 또는 종료
                current_values = state_vector(observation, action_names)
                hold_action = {
                    name: float(current_values[index]) for index, name in enumerate(action_names)
                }
                robot.send_action(hold_action)
                paused = True
                pause_reason = "STALL PAUSED - SPACE/Q"
                plan = np.empty((0, 6), dtype=np.float32)
                plan_index = 0
                plan_generation += 1
                next_replan_step = control_step
                previous_command = None
                stall_monitor.reset()
                print(f"\n{exc}")
                print("Current pose is being held with torque ON.")
                print("Inspect the arm, then press SPACE to retry or press Q to return HOME and stop.")
                continue

            at_home = is_home(observation)
            if not at_home:
                left_home = True
                home_since = None
            elif left_home and home_since is None:
                home_since = time.perf_counter()

            home_stable_s = 0.0 if home_since is None else time.perf_counter() - home_since
            if left_home and elapsed_s >= MIN_COMPLETION_TIME_S and home_stable_s >= HOME_STABLE_TIME_S:
                print(f"Episode 1 completed: robot returned HOME and stayed stable.")
                return "completed"
            if elapsed_s >= args.max_duration_s:
                print(f"Episode 1 stopped at the {args.max_duration_s:.1f}s safety timeout.")
                return "timeout"

            precise_sleep(max(0.0, 1.0 / args.fps - (time.perf_counter() - loop_started_at)))



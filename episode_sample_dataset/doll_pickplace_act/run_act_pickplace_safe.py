from __future__ import annotations

import argparse
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
import json
import os
import sys
import time
from dataclasses import replace
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
DATASET_ROOT = PROJECT_ROOT / "episode_sample_dataset" / "auto_home_collection" / "auto_home_dataset"
CHECKPOINT_DIR = SCRIPT_DIR / "outputs" / "act_100ep_20k" / "checkpoints" / "020000"
MODEL_DIR = CHECKPOINT_DIR / "pretrained_model"
CALIBRATION_ROOT = PROJECT_ROOT / "robot_calibration"
REPO_ID = "hazyala/so101_pickplace_auto_home"
TASK = "Pick up the object from the table and place it into the box, then return to home."

# Keep the same local cache and calibration locations as the collection script.
os.environ["HF_HOME"] = str(PROJECT_ROOT / "hf_pickplace_reference")
os.environ["HF_LEROBOT_HOME"] = str(PROJECT_ROOT / "hf_pickplace_reference" / "lerobot")
os.environ["HF_LEROBOT_CALIBRATION"] = str(CALIBRATION_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))

import cv2
import numpy as np
import torch

from episode_sample_dataset.auto_home_collection.auto_home_record import (
    HOME_POSE,
    HOME_STABLE_TIME_S,
    HOME_TOLERANCE,
    connect_with_saved_calibration,
    make_configs,
)
from lerobot.datasets import LeRobotDatasetMetadata
from lerobot.policies import make_pre_post_processors
from lerobot.policies.act import ACTPolicy
from lerobot.policies.utils import build_inference_frame
from lerobot.robots import make_robot_from_config
from lerobot.utils.constants import ACTION
from lerobot.utils.robot_utils import precise_sleep
from lerobot.utils.utils import init_logging


WINDOW_NAME = "SO-101 ACT Safe Pick & Place"
FPS = 30
# Inference runs asynchronously, so it does not block the 30 FPS motor loop.
# The recorded policy often places its approach and grasp 30-60 steps into a
# 100-step chunk. Replacing the chunk at step 30 discards that phase and can
# keep the arm behind the object indefinitely. Sixty steps restores the
# approach observed before the short-interval controller change.
DEFAULT_REPLAN_EVERY = 60
PLAN_SWITCH_BLEND_FRAMES = 8
# The fingers reached the object before closing in the recorded trial. Advance
# only closing commands (larger gripper values); keep opening on the policy's
# original timeline so the object is not released early during transport.
DEFAULT_GRIPPER_CLOSE_LEAD_FRAMES = 8
DEFAULT_MAX_DURATION_S = 60.0
MIN_COMPLETION_TIME_S = 8.0

# Maximum command change per control step. Arm units are degrees and gripper
# units use the same 0-100 scale as the recorded SO-101 dataset.
MAX_DELTA_PER_STEP = {
    "shoulder_pan.pos": 2.0,
    "shoulder_lift.pos": 3.0,
    "elbow_flex.pos": 3.0,
    "wrist_flex.pos": 4.0,
    "wrist_roll.pos": 4.0,
    "gripper.pos": 5.0,
}

# The target may accumulate ahead of the measured joint to create enough
# position error for gravity-loaded joints to overcome static friction. The
# robot driver applies an independent 5-degree max-relative-target guard too.
MAX_TRACKING_ERROR = {
    "shoulder_pan.pos": 6.0,
    "shoulder_lift.pos": 10.0,
    "elbow_flex.pos": 10.0,
    "wrist_flex.pos": 10.0,
    "wrist_roll.pos": 8.0,
    "gripper.pos": 10.0,
}

STALL_JOINTS = ("shoulder_lift.pos", "elbow_flex.pos", "wrist_flex.pos")
STALL_WINDOW_S = 4.0
STALL_MIN_DEMAND = 8.0
STALL_MIN_MOVEMENT = 0.15

# Stop if a measured joint is far outside the region demonstrated in the
# dataset. This margin is only a watchdog; outgoing commands remain strictly
# clipped to the demonstrated min/max range.
STATE_WATCHDOG_MARGIN = np.array([20.0, 20.0, 20.0, 25.0, 30.0, 20.0], dtype=np.float32)
MAX_RAW_RANGE_VIOLATION_FRACTION = 0.25
HOME_RETURN_TIMEOUT_S = 25.0
HOME_RELEASE_TOLERANCE = {
    "shoulder_pan.pos": 3.0,
    "shoulder_lift.pos": 3.0,
    "elbow_flex.pos": 3.0,
    "wrist_flex.pos": 5.0,
    "gripper.pos": 5.0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safely run the trained ACT policy on the SO-101 follower."
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Validate model, metadata, and calibration files without connecting hardware.",
    )
    parser.add_argument("--max-episodes", type=int, default=1)
    parser.add_argument("--max-duration-s", type=float, default=DEFAULT_MAX_DURATION_S)
    parser.add_argument("--replan-every", type=int, default=DEFAULT_REPLAN_EVERY)
    parser.add_argument(
        "--gripper-close-lead-frames",
        type=int,
        default=DEFAULT_GRIPPER_CLOSE_LEAD_FRAMES,
        help="Advance only gripper closing targets by this many control frames (0 disables).",
    )
    parser.add_argument("--fps", type=int, default=FPS)
    parser.add_argument(
        "--max-inference-ms",
        type=float,
        default=750.0,
        help="Abort if a warmed-up policy inference exceeds this latency.",
    )
    args = parser.parse_args()
    if not 50 <= args.replan_every <= 75:
        parser.error(
            "--replan-every must be between 50 and 75: shorter intervals "
            "repeatedly skip this model's approach/grasp segment."
        )
    if args.max_episodes < 1:
        parser.error("--max-episodes must be at least 1.")
    if not 0 <= args.gripper_close_lead_frames <= 8:
        parser.error("--gripper-close-lead-frames must be between 0 and 8.")
    if args.max_duration_s <= 0:
        parser.error("--max-duration-s must be positive.")
    if not 5 <= args.fps <= 30:
        parser.error("--fps must be between 5 and 30.")
    return args


def validate_follower_calibration() -> None:
    path = CALIBRATION_ROOT / "robots" / "so_follower" / "follower.json"
    expected = {
        "shoulder_pan",
        "shoulder_lift",
        "elbow_flex",
        "wrist_flex",
        "wrist_roll",
        "gripper",
    }
    if not path.is_file():
        raise RuntimeError(f"Follower calibration file is missing: {path}")
    calibration = json.loads(path.read_text(encoding="utf-8"))
    if set(calibration) != expected:
        raise RuntimeError(f"Follower calibration joints are incomplete or unexpected: {path}")
    invalid = [
        joint
        for joint, values in calibration.items()
        if int(values.get("range_min", 0)) >= int(values.get("range_max", 0))
    ]
    if invalid:
        raise RuntimeError(f"Invalid follower calibration ranges: {', '.join(invalid)}")


def validate_artifacts() -> None:
    required = [
        DATASET_ROOT / "meta" / "info.json",
        DATASET_ROOT / "meta" / "stats.json",
        MODEL_DIR / "config.json",
        MODEL_DIR / "model.safetensors",
        MODEL_DIR / "policy_preprocessor.json",
        MODEL_DIR / "policy_preprocessor_step_3_normalizer_processor.safetensors",
        MODEL_DIR / "policy_postprocessor.json",
        MODEL_DIR / "policy_postprocessor_step_0_unnormalizer_processor.safetensors",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("Required inference artifacts are missing:\n  - " + "\n  - ".join(missing))
    validate_follower_calibration()


def load_policy_runtime():
    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA GPU is required for this real-time safety profile. "
            "CPU inference can pause commands for too long."
        )

    metadata = LeRobotDatasetMetadata(REPO_ID, root=DATASET_ROOT)
    policy = ACTPolicy.from_pretrained(MODEL_DIR).to("cuda").eval()
    preprocess, postprocess = make_pre_post_processors(
        policy.config,
        pretrained_path=str(MODEL_DIR),
    )

    expected_inputs = {
        "observation.state",
        "observation.images.top",
        "observation.images.side",
    }
    if set(policy.config.input_features) != expected_inputs:
        raise RuntimeError(
            f"Unexpected model inputs: {sorted(policy.config.input_features)}; "
            f"expected {sorted(expected_inputs)}"
        )
    if set(policy.config.output_features) != {ACTION}:
        raise RuntimeError(f"Unexpected model outputs: {sorted(policy.config.output_features)}")
    if metadata.total_episodes != 100 or metadata.total_frames != 56_768:
        raise RuntimeError(
            "Dataset identity check failed: expected 100 episodes and 56,768 frames, "
            f"found {metadata.total_episodes} and {metadata.total_frames}."
        )

    action_names = list(metadata.features[ACTION]["names"])
    if action_names != list(MAX_DELTA_PER_STEP):
        raise RuntimeError(f"Unexpected action order: {action_names}")

    action_min = np.asarray(metadata.stats[ACTION]["min"], dtype=np.float32)
    action_max = np.asarray(metadata.stats[ACTION]["max"], dtype=np.float32)
    if action_min.shape != (6,) or action_max.shape != (6,) or np.any(action_min >= action_max):
        raise RuntimeError("Dataset action safety bounds are invalid.")

    # Depth is intentionally excluded: this ACT checkpoint was trained on top RGB,
    # side RGB, and robot state only.
    inference_features = {
        key: value for key, value in metadata.features.items() if key in expected_inputs
    }
    return metadata, policy, preprocess, postprocess, inference_features, action_names, action_min, action_max


def state_vector(observation: dict, action_names: list[str]) -> np.ndarray:
    values = np.asarray([observation[name] for name in action_names], dtype=np.float32)
    if not np.isfinite(values).all():
        raise RuntimeError("Robot observation contains NaN or Inf.")
    return values


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


def predict_chunk(
    observation: dict,
    policy: ACTPolicy,
    preprocess,
    postprocess,
    inference_features: dict,
) -> tuple[np.ndarray, float]:
    frame = build_inference_frame(
        observation=observation,
        ds_features=inference_features,
        device=torch.device("cuda"),
        task=TASK,
        robot_type="so101_follower",
    )
    batch = preprocess(frame)
    torch.cuda.synchronize()
    started_at = time.perf_counter()
    with torch.inference_mode(), torch.autocast(device_type="cuda", dtype=torch.float16):
        chunk = policy.predict_action_chunk(batch)
    torch.cuda.synchronize()
    inference_ms = (time.perf_counter() - started_at) * 1000.0
    chunk = postprocess(chunk)[0].numpy()
    if chunk.shape != (policy.config.chunk_size, 6):
        raise RuntimeError(f"Unexpected policy output shape: {chunk.shape}")
    if not np.isfinite(chunk).all():
        raise RuntimeError("Policy output contains NaN or Inf.")
    return chunk, inference_ms


def copy_observation(observation: dict) -> dict:
    return {
        key: value.copy() if isinstance(value, np.ndarray) else value
        for key, value in observation.items()
    }


def switch_action_plans(
    old_remaining: np.ndarray,
    new_chunk: np.ndarray,
    new_chunk_offset: int,
) -> np.ndarray:
    """Switch plans with a short crossfade, without diluting the entire horizon."""
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
        # Rate and tracking guards already limit the gripper. Avoid delaying
        # a newly predicted closing command during the arm's plan crossfade.
        switched[:blend_frames, 5] = np.maximum(
            switched[:blend_frames, 5], new_aligned[:blend_frames, 5]
        )
    return switched


def action_with_early_gripper_close(
    plan: np.ndarray, index: int, lead_frames: int
) -> np.ndarray:
    """Keep arm timing intact while allowing the gripper to start closing earlier."""
    action = plan[index].copy()
    if lead_frames:
        future_index = min(index + lead_frames, len(plan) - 1)
        action[5] = max(float(action[5]), float(plan[future_index, 5]))
    return action


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

    # Slew from the previous command, not from the measured position. Otherwise
    # a loaded joint that cannot move in response to the first small target would
    # receive the same tiny target forever and appear weak or completely stuck.
    command_base = current if previous_command is None else np.asarray(previous_command, dtype=np.float32)
    command_delta = np.clip(absolute_clipped - command_base, -max_delta, max_delta)
    slewed = command_base + command_delta

    # Still keep the accumulated target close to the real joint. This produces
    # useful servo effort without allowing an open-loop target to run away.
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


class StallMonitor:
    """Stop loaded joints that receive effort but fail to move."""

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


def is_home(observation: dict) -> bool:
    return all(
        abs(float(observation[key]) - target) <= HOME_TOLERANCE[key]
        for key, target in HOME_POSE.items()
    )


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


def is_release_home(observation: dict) -> bool:
    return all(
        abs(float(observation[key]) - HOME_POSE[key]) <= HOME_RELEASE_TOLERANCE[key]
        for key in HOME_RELEASE_TOLERANCE
    )


def largest_release_home_error(observation: dict) -> tuple[str, float, float]:
    errors = [
        (
            key,
            abs(float(observation[key]) - HOME_POSE[key]),
            HOME_RELEASE_TOLERANCE[key],
        )
        for key in HOME_RELEASE_TOLERANCE
    ]
    return max(errors, key=lambda item: item[1] / item[2])


def read_motor_observation(robot) -> dict[str, float]:
    positions = robot.bus.sync_read(
        "Present_Position",
        num_retry=robot.config.num_read_retries,
    )
    return {f"{motor}.pos": float(value) for motor, value in positions.items()}


def return_home_and_stabilize(
    robot,
    action_names: list[str],
    action_min: np.ndarray,
    action_max: np.ndarray,
    fps: int,
) -> bool:
    """Return to the recorded HOME pose before allowing torque release."""
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
    previous_command: np.ndarray | None = None
    started_at = time.perf_counter()
    stable_since: float | None = None
    last_reported_second = -1

    while time.perf_counter() - started_at < HOME_RETURN_TIMEOUT_S:
        loop_started_at = time.perf_counter()
        if cv2.waitKey(1) & 0xFF == ord("e"):
            robot.bus.disable_torque(num_retry=robot.config.num_write_retries)
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
        at_home = is_release_home(observation)
        if at_home:
            stable_since = now if stable_since is None else stable_since
            if now - stable_since >= HOME_STABLE_TIME_S:
                print("HOME reached and stable. Torque may now be released.")
                return True
        else:
            stable_since = None

        elapsed_second = int(now - started_at)
        if elapsed_second != last_reported_second:
            joint, diff, tolerance = largest_release_home_error(observation)
            print(
                f"  HOME {elapsed_second:2d}s: {joint} error {diff:.2f} "
                f"(tolerance {tolerance:.2f})"
            )
            last_reported_second = elapsed_second
        precise_sleep(max(0.0, 1.0 / fps - (time.perf_counter() - loop_started_at)))

    print(f"HOME return timed out after {HOME_RETURN_TIMEOUT_S:.0f}s.")
    return False


def bgr_image(image: np.ndarray) -> np.ndarray:
    if image is None or image.ndim != 3 or image.shape[2] != 3:
        return np.zeros((480, 640, 3), dtype=np.uint8)
    if image.dtype != np.uint8:
        image = np.clip(image, 0, 255).astype(np.uint8)
    return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)


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


def wait_for_space(robot, action_names: list[str], action_min: np.ndarray, action_max: np.ndarray):
    print("Place the robot near the recorded HOME pose and focus the OpenCV window.")
    print("Press SPACE to start, Q to stop, or E for immediate torque-off.")
    while True:
        observation = robot.get_observation()
        validate_state_watchdog(observation, action_names, action_min, action_max)
        at_home = is_home(observation)
        status = "READY - SPACE TO START" if at_home else "MOVE TO HOME BEFORE START"
        key = draw_status(
            observation,
            status,
            0,
            0.0,
            None,
            {"range": 0, "rate": 0, "tracking": 0},
        )
        if key == ord("e"):
            robot.bus.disable_torque(num_retry=robot.config.num_write_retries)
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


def run_episode(
    robot,
    episode: int,
    args: argparse.Namespace,
    runtime: tuple,
) -> str:
    _, policy, preprocess, postprocess, inference_features, action_names, action_min, action_max = runtime
    observation = wait_for_space(robot, action_names, action_min, action_max)

    # Two warm-up passes happen before any command is sent. They initialize CUDA
    # kernels and ensure the first live inference is not a latency outlier.
    for _ in range(2):
        _, warmup_ms = predict_chunk(observation, policy, preprocess, postprocess, inference_features)
    print(f"Warm-up inference: {warmup_ms:.1f} ms")

    # Seed the controller on the same worker thread used for live inference.
    # CUDA has a one-time per-thread warm-up cost; paying it before motion keeps
    # the first background refresh from tripping the latency watchdog.
    inference_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="act-inference")
    seed_future = inference_pool.submit(
        predict_chunk,
        copy_observation(observation),
        policy,
        preprocess,
        postprocess,
        inference_features,
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

    def finish(result: str) -> str:
        inference_pool.shutdown(wait=True, cancel_futures=True)
        return result

    while True:
        loop_started_at = time.perf_counter()
        elapsed_s = loop_started_at - started_at
        observation = robot.get_observation()
        validate_state_watchdog(observation, action_names, action_min, action_max)

        if pending_inference is not None and pending_inference.done():
            try:
                new_chunk, new_inference_ms = pending_inference.result()
            except BaseException:
                inference_pool.shutdown(wait=True, cancel_futures=True)
                raise
            if new_inference_ms > args.max_inference_ms:
                inference_pool.shutdown(wait=True, cancel_futures=True)
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
            )
            next_replan_step = control_step + args.replan_every

        key = draw_status(
            observation,
            pause_reason if paused else "RUNNING",
            episode,
            elapsed_s,
            inference_ms,
            limit_counts,
        )
        if key == ord("e"):
            robot.bus.disable_torque(num_retry=robot.config.num_write_retries)
            return finish("emergency")
        if key in (ord("q"), 27):
            return finish("stopped")
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
            continue

        if plan_index < len(plan):
            raw_values = action_with_early_gripper_close(
                plan, plan_index, args.gripper_close_lead_frames
            )
            plan_index += 1
        else:
            # A new asynchronous plan should normally arrive well before the
            # old 100-frame plan ends. If it does not, hold the measured pose
            # rather than blocking the control loop or extrapolating stale motion.
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
            # Remove the accumulated position error immediately, but keep
            # torque enabled so the arm does not fall. The operator can
            # inspect the arm, resume with SPACE, or support it and press Q.
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
            print(f"Episode {episode} completed: robot returned HOME and stayed stable.")
            return finish("completed")
        if elapsed_s >= args.max_duration_s:
            print(f"Episode {episode} stopped at the {args.max_duration_s:.1f}s safety timeout.")
            return finish("timeout")

        precise_sleep(max(0.0, 1.0 / args.fps - (time.perf_counter() - loop_started_at)))


def main() -> None:
    args = parse_args()
    init_logging()
    validate_artifacts()
    runtime = load_policy_runtime()
    metadata, policy, _, _, _, action_names, action_min, action_max = runtime

    print()
    print("SO-101 ACT safe pick-and-place")
    print(f"Checkpoint: {MODEL_DIR}")
    print(f"Dataset: {metadata.total_episodes} episodes, {metadata.total_frames} frames")
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"Asynchronous replan refresh: every {args.replan_every} control frames")
    print(f"Plan switches use a {PLAN_SWITCH_BLEND_FRAMES}-frame crossfade.")
    print(
        f"Gripper closing leads the arm by up to "
        f"{args.gripper_close_lead_frames} frames; opening timing is unchanged."
    )
    print("Outgoing actions are clipped to the demonstrated range and rate-limited per joint.")
    for name, low, high, delta in zip(
        action_names,
        action_min,
        action_max,
        (MAX_DELTA_PER_STEP[name] for name in action_names),
    ):
        print(f"  {name:18s} range [{low:8.2f}, {high:8.2f}]  max step {delta:.2f}")
    print("Loaded joints may accumulate at most 10 degrees ahead of measured position.")
    print("Shoulder lift, elbow flex, and wrist flex pause only after a sustained 4-second stall.")
    print("Normal stop, timeout, stall exit, and recoverable errors return HOME before torque release.")

    if args.preflight_only:
        print("\nPREFLIGHT PASS: model, processors, metadata, bounds, and calibration file are valid.")
        print("No hardware was connected and no motor command was sent.")
        return

    print("\nWARNING: REAL MOTOR COMMANDS ARE ENABLED.")
    print("Keep one hand ready at the power switch and keep the workspace clear.")
    print("The robot will connect now, but motion still requires SPACE in the preview window.")

    _, robot_config = make_configs()
    # The policy-side tracking guard remains active, but the driver's second
    # relative-target guard is widened so grasp and lift targets are not
    # repeatedly flattened before reaching gravity-loaded joints.
    robot_config.max_relative_target = 12.0
    # The trained ACT policy does not consume depth. Disabling the depth stream
    # reduces camera overhead without changing either RGB input used by the model.
    robot_config.cameras["top"] = replace(robot_config.cameras["top"], use_depth=False)
    robot = make_robot_from_config(robot_config)
    emergency = False
    failure: BaseException | None = None

    try:
        print("Connecting follower and RGB cameras with saved calibration...")
        connect_with_saved_calibration(robot, "follower")
        print("Connected. No command is sent until SPACE is pressed in the preview window.")
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WINDOW_NAME, 1280, 480)

        for episode in range(1, args.max_episodes + 1):
            result = run_episode(robot, episode, args, runtime)
            if result == "emergency":
                emergency = True
                print("EMERGENCY STOP: torque was disabled immediately.")
                break
            if result in {"stopped", "timeout"}:
                break
    except KeyboardInterrupt as exc:
        print(f"\nStopped: {exc}")
    except EmergencyStop as exc:
        emergency = True
        print(f"\nEMERGENCY STOP: {exc}")
    except BaseException as exc:
        failure = exc
        print(f"\nSAFETY STOP: {type(exc).__name__}: {exc}")
        if robot.bus.is_connected:
            try:
                observation = read_motor_observation(robot)
                current_values = state_vector(observation, action_names)
                hold_action = {
                    name: float(current_values[index]) for index, name in enumerate(action_names)
                }
                robot.send_action(hold_action)
                print("The current pose is being held with torque ON.")
            except BaseException as hold_exc:
                print(f"Could not hold the current pose: {hold_exc}")
    finally:
        bus_connected = robot.bus.is_connected
        home_reached = False
        if bus_connected and not emergency:
            try:
                home_reached = return_home_and_stabilize(
                    robot,
                    action_names,
                    action_min,
                    action_max,
                    args.fps,
                )
            except EmergencyStop as exc:
                emergency = True
                print(f"EMERGENCY STOP: {exc}")
            except BaseException as home_exc:
                print(f"Could not complete HOME return: {home_exc}")

        if bus_connected and not emergency and not home_reached:
            try:
                observation = read_motor_observation(robot)
                hold_action = {name: float(observation[name]) for name in action_names}
                robot.send_action(hold_action)
                print("HOME was not reached. Current pose remains held with torque ON.")
            except BaseException as hold_exc:
                print(f"Could not hold the current pose: {hold_exc}")
            while input("Support the arm and type RELEASE to disable torque: ").strip() != "RELEASE":
                print("Torque remains ON. Type RELEASE only after the arm is physically supported.")

        cv2.destroyAllWindows()
        all_connected = robot.is_connected
        if all_connected and not emergency:
            robot.disconnect()
        else:
            # Also clean up a partially completed connection. In the emergency
            # path torque has already been disabled, and this repeats that safe state.
            if bus_connected:
                robot.bus.disconnect(disable_torque=True)
            for camera in robot.cameras.values():
                if camera.is_connected:
                    camera.disconnect()
        print("Disconnected. Motor torque is off; support the arm before it relaxes.")

    if failure is not None:
        raise SystemExit(f"Execution stopped safely: {failure}")


if __name__ == "__main__":
    main()

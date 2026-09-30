from __future__ import annotations

import json
import os
import shutil
import threading
import time
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
CALIBRATION_ROOT = PROJECT_ROOT / "robot_calibration"

# Keep this collector independent from stale user/session cache variables.
os.environ["HF_HOME"] = str(PROJECT_ROOT / "hf_pickplace_reference")
os.environ["HF_LEROBOT_HOME"] = str(PROJECT_ROOT / "hf_pickplace_reference" / "lerobot")
os.environ["HF_LEROBOT_CALIBRATION"] = str(CALIBRATION_ROOT)

import av
import cv2
import numpy as np
import pyarrow.compute as pc
import pyarrow.parquet as pq

from lerobot.cameras import Cv2Backends
from lerobot.cameras.opencv import OpenCVCameraConfig
from lerobot.cameras.realsense import RealSenseCameraConfig
from lerobot.configs import DepthEncoderConfig, RGBEncoderConfig
from lerobot.datasets import (
    LeRobotDataset,
    VideoEncodingManager,
    aggregate_pipeline_dataset_features,
    create_initial_features,
)
from lerobot.processor import make_default_processors
from lerobot.robots import make_robot_from_config
from lerobot.robots.so_follower.config_so_follower import SOFollowerRobotConfig
from lerobot.teleoperators import make_teleoperator_from_config
from lerobot.teleoperators.so_leader.config_so_leader import SOLeaderTeleopConfig
from lerobot.utils.constants import ACTION, OBS_STR
from lerobot.utils.feature_utils import build_dataset_frame, combine_feature_dicts
from lerobot.utils.robot_utils import precise_sleep
from lerobot.utils.utils import init_logging


DATASET_ROOT = SCRIPT_DIR / "auto_home_dataset"
HOME_POSE_PATH = SCRIPT_DIR / "home_pose.json"

REPO_ID = "hazyala/so101_pickplace_auto_home"
TASK = "Pick up the object from the table and place it into the box, then return to home."
FPS = 30
RESET_TIME_S = 5.0
DISCARD_RESET_TIME_S = 10.0
START_TIME_S = 1.0
MIN_EPISODE_TIME_S = 8.0
HOME_STABLE_TIME_S = 2.0
MAX_EPISODE_TIME_S = 90.0

# The D405 reports uint16 depth in device units of 0.1 mm on this setup.
# LeRobot's depth video encoder interprets uint16 input as millimetres, so the
# raw frame must be converted before it reaches build_dataset_frame().
TOP_DEPTH_SCALE_M_PER_UNIT = 0.0001
TOP_DEPTH_RAW_TO_MM = TOP_DEPTH_SCALE_M_PER_UNIT * 1000.0
TOP_DEPTH_MIN_M = 0.0
TOP_DEPTH_MAX_M = 2.0

DEPTH_ENCODER = DepthEncoderConfig(
    preset="fast",
    depth_min=TOP_DEPTH_MIN_M,
    depth_max=TOP_DEPTH_MAX_M,
)
# NVENC can be listed by FFmpeg even when the installed GPU/driver cannot open it.
# Use the fastest software H.264 preset so RGB encoding leaves CPU headroom for
# the lossless HEVC depth stream without relying on runtime GPU availability.
RGB_ENCODER = RGBEncoderConfig(vcodec="h264", crf=23, preset="ultrafast")
ENCODER_QUEUE_MAXSIZE = 300

CALIBRATION_FILES = {
    "leader": CALIBRATION_ROOT / "teleoperators" / "so_leader" / "leader.json",
    "follower": CALIBRATION_ROOT / "robots" / "so_follower" / "follower.json",
}

# Tolerances are in the normalized units returned by SO-101: degrees for arm joints,
# 0-100 range for the gripper.
HOME_TOLERANCE = {
    "shoulder_pan.pos": 12.0,
    "shoulder_lift.pos": 12.0,
    "elbow_flex.pos": 12.0,
    "wrist_flex.pos": 18.0,
    "gripper.pos": 20.0,
}

HOME_POSE = {
    "shoulder_pan.pos": -5.80,
    "shoulder_lift.pos": -99.30,
    "elbow_flex.pos": 101.05,
    "wrist_flex.pos": 74.86,
    "gripper.pos": 1.32,
}


def choose_dataset_mode() -> str:
    if not DATASET_ROOT.exists():
        return "create"

    answer = input(
        f"Existing dataset found at {DATASET_ROOT}\n"
        "Type y to VALIDATE and CONTINUE, or type reset to DELETE ALL data and start over: "
    ).strip().lower()

    if answer == "y":
        return "resume"
    if answer != "reset":
        raise SystemExit("No changes were made. Restart and type y or reset.")

    resolved_root = SCRIPT_DIR.resolve()
    resolved_dataset = DATASET_ROOT.resolve()
    if resolved_root not in resolved_dataset.parents:
        raise RuntimeError(f"Refusing to delete outside this folder: {resolved_dataset}")
    shutil.rmtree(resolved_dataset)
    return "create"


def validate_calibration_files() -> None:
    expected_joints = {
        "shoulder_pan",
        "shoulder_lift",
        "elbow_flex",
        "wrist_flex",
        "wrist_roll",
        "gripper",
    }
    errors: list[str] = []
    for device, path in CALIBRATION_FILES.items():
        if not path.is_file():
            errors.append(f"{device}: calibration file is missing: {path}")
            continue
        try:
            calibration = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{device}: cannot read calibration file: {exc}")
            continue
        if set(calibration) != expected_joints:
            errors.append(f"{device}: calibration joints are incomplete or unexpected")
            continue
        invalid = [
            joint
            for joint, values in calibration.items()
            if int(values.get("range_min", 0)) >= int(values.get("range_max", 0))
        ]
        if invalid:
            errors.append(f"{device}: invalid calibration ranges: {', '.join(invalid)}")
    if errors:
        raise SystemExit(
            "Calibration preflight failed. Automatic recalibration was blocked:\n  - "
            + "\n  - ".join(errors)
        )


def connect_with_saved_calibration(device, label: str) -> None:
    """Connect without interactive recalibration and restore the trusted JSON values."""
    device.connect(calibrate=False)
    if not device.calibration:
        raise RuntimeError(f"{label}: no saved calibration was loaded")

    print(f"Applying saved {label} calibration (interactive recalibration is disabled)...")
    device.bus.write_calibration(device.calibration)
    if not device.is_calibrated:
        raise RuntimeError(
            f"{label}: motor calibration still does not match the saved calibration file"
        )
    print(f"{label.capitalize()} calibration verified.")


def load_info() -> dict:
    info_path = DATASET_ROOT / "meta" / "info.json"
    if not info_path.is_file():
        raise SystemExit(f"Cannot continue: dataset metadata is missing: {info_path}")
    return json.loads(info_path.read_text(encoding="utf-8"))


def read_parquet_rows(pattern: str) -> list[dict]:
    paths = sorted(DATASET_ROOT.glob(pattern))
    rows: list[dict] = []
    for path in paths:
        rows.extend(pq.read_table(path).to_pylist())
    return rows


def replace_parquet_with_filter(path: Path, column: str, upper_bound: int) -> int:
    """Atomically remove rows at or beyond an uncommitted metadata boundary."""
    table = pq.read_table(path)
    if column not in table.column_names:
        raise RuntimeError(f"Cannot recover {path}: missing column {column!r}.")

    keep = pc.less(table[column], upper_bound)
    kept_table = table.filter(keep)
    removed = table.num_rows - kept_table.num_rows
    if removed == 0:
        return 0

    temporary_path = path.with_suffix(path.suffix + ".recovering")
    pq.write_table(kept_table, temporary_path)
    temporary_path.replace(path)
    return removed


def recover_uncommitted_tail() -> None:
    """Remove only trailing data that was never committed to info/episode metadata."""
    info = load_info()
    total_frames = int(info["total_frames"])
    total_episodes = int(info["total_episodes"])

    removed_frames = sum(
        replace_parquet_with_filter(path, "index", total_frames)
        for path in sorted(DATASET_ROOT.glob("data/chunk-*/file-*.parquet"))
    )
    removed_episode_rows = sum(
        replace_parquet_with_filter(path, "episode_index", total_episodes)
        for path in sorted(DATASET_ROOT.glob("meta/episodes/chunk-*/file-*.parquet"))
    )

    committed_episodes = read_parquet_rows("meta/episodes/chunk-*/file-*.parquet")
    referenced_videos: set[Path] = set()
    for episode in committed_episodes:
        for video_key in info.get("features", {}):
            if info["features"][video_key].get("dtype") != "video":
                continue
            chunk_key = f"videos/{video_key}/chunk_index"
            file_key = f"videos/{video_key}/file_index"
            if chunk_key not in episode or file_key not in episode:
                continue
            referenced_videos.add(
                DATASET_ROOT
                / "videos"
                / video_key
                / f"chunk-{int(episode[chunk_key]):03d}"
                / f"file-{int(episode[file_key]):03d}.mp4"
            )

    removed_videos = 0
    for video_path in DATASET_ROOT.glob("videos/*/chunk-*/*.mp4"):
        if video_path not in referenced_videos:
            video_path.unlink()
            removed_videos += 1

    removed_temp_dirs = 0
    resolved_dataset = DATASET_ROOT.resolve()
    for temp_dir in DATASET_ROOT.glob("tmp*"):
        if temp_dir.is_dir() and temp_dir.resolve().parent == resolved_dataset:
            shutil.rmtree(temp_dir)
            removed_temp_dirs += 1

    if removed_frames or removed_episode_rows or removed_videos or removed_temp_dirs:
        print(
            "Recovered an unfinished trailing episode: "
            f"removed {removed_frames} frame rows, {removed_episode_rows} episode rows, "
            f"{removed_videos} orphan videos, and {removed_temp_dirs} temporary folders."
        )


def validate_existing_dataset() -> list[str]:
    """Return actionable integrity errors; an empty list means resume is safe."""
    errors: list[str] = []
    info = load_info()
    total_episodes = int(info.get("total_episodes", -1))
    total_frames = int(info.get("total_frames", -1))
    features = info.get("features", {})

    required_features = {
        "action",
        "observation.state",
        "observation.images.top",
        "observation.images.top_depth",
        "observation.images.side",
        "timestamp",
        "frame_index",
        "episode_index",
        "index",
        "task_index",
    }
    missing_features = sorted(required_features - set(features))
    if missing_features:
        errors.append(f"Dataset schema: missing features: {', '.join(missing_features)}")

    depth_info = (features.get("observation.images.top_depth") or {}).get("info") or {}
    if depth_info:
        if depth_info.get("depth_unit") != "mm":
            errors.append("Dataset schema: top depth unit is not millimetres.")
        if (
            depth_info.get("video.depth_min") != TOP_DEPTH_MIN_M
            or depth_info.get("video.depth_max") != TOP_DEPTH_MAX_M
        ):
            errors.append("Dataset schema: D405 depth range predates the corrected depth-scale format.")

    episode_rows = read_parquet_rows("meta/episodes/chunk-*/file-*.parquet")
    if len(episode_rows) != total_episodes:
        errors.append(
            f"Episode metadata: info.json says {total_episodes}, but metadata contains {len(episode_rows)} rows."
        )

    expected_from = 0
    episode_lengths: dict[int, int] = {}
    for position, episode in enumerate(episode_rows):
        episode_index = int(episode.get("episode_index", -1))
        display_index = episode_index + 1
        length = int(episode.get("length", -1))
        dataset_from = int(episode.get("dataset_from_index", -1))
        dataset_to = int(episode.get("dataset_to_index", -1))
        episode_lengths[episode_index] = length
        if episode_index != position:
            errors.append(f"Episode {display_index}: metadata order/index is inconsistent.")
        if dataset_from != expected_from or dataset_to - dataset_from != length:
            errors.append(f"Episode {display_index}: frame range and episode length do not match.")
        expected_from = dataset_to

    data_paths = sorted(DATASET_ROOT.glob("data/chunk-*/file-*.parquet"))
    if not data_paths:
        errors.append("Dataset data: no parquet data files were found.")
    else:
        data = pq.read_table(data_paths, columns=["index", "episode_index", "frame_index"])
        indices = data["index"].to_numpy()
        episode_indices = data["episode_index"].to_numpy()
        frame_indices = data["frame_index"].to_numpy()
        if data.num_rows != total_frames:
            errors.append(
                f"Dataset data: info.json says {total_frames} frames, but parquet contains {data.num_rows}."
            )
        if not np.array_equal(indices, np.arange(data.num_rows)):
            errors.append("Dataset data: global frame indices are not continuous.")
        for episode_index, length in episode_lengths.items():
            current_frames = frame_indices[episode_indices == episode_index]
            if not np.array_equal(current_frames, np.arange(length)):
                errors.append(f"Episode {episode_index + 1}: frame indices are missing or duplicated.")

    fps = int(info.get("fps", FPS))
    video_file_frames: dict[Path, int | None] = {}
    video_file_ranges: dict[tuple[str, Path], list[tuple[int, int, int]]] = {}

    for episode in episode_rows:
        episode_index = int(episode["episode_index"])
        display_index = episode_index + 1
        expected_frames = int(episode["length"])
        for video_key, feature in features.items():
            if feature.get("dtype") != "video":
                continue
            chunk_key = f"videos/{video_key}/chunk_index"
            file_key = f"videos/{video_key}/file_index"
            from_key = f"videos/{video_key}/from_timestamp"
            to_key = f"videos/{video_key}/to_timestamp"
            required_video_fields = {chunk_key, file_key, from_key, to_key}
            if not required_video_fields.issubset(episode):
                errors.append(f"Episode {display_index}: {video_key} segment metadata is missing.")
                continue
            video_path = (
                DATASET_ROOT
                / "videos"
                / video_key
                / f"chunk-{int(episode[chunk_key]):03d}"
                / f"file-{int(episode[file_key]):03d}.mp4"
            )
            if not video_path.is_file():
                errors.append(f"Episode {display_index}: missing video {video_key}: {video_path.name}")
                continue

            segment_from = int(round(float(episode[from_key]) * fps))
            segment_to = int(round(float(episode[to_key]) * fps))
            segment_frames = segment_to - segment_from
            if segment_frames != expected_frames:
                errors.append(
                    f"Episode {display_index}: {video_key} segment has {segment_frames} frames; "
                    f"expected {expected_frames}."
                )

            if video_path not in video_file_frames:
                try:
                    with av.open(str(video_path)) as container:
                        actual_frames = int(container.streams.video[0].frames)
                        if actual_frames <= 0:
                            actual_frames = sum(1 for _ in container.decode(video=0))
                    video_file_frames[video_path] = actual_frames
                except Exception as exc:
                    errors.append(f"Cannot open {video_key} file {video_path.name}: {exc}")
                    video_file_frames[video_path] = None

            actual_frames = video_file_frames[video_path]
            if actual_frames is None:
                continue
            if segment_from < 0 or segment_to > actual_frames:
                errors.append(
                    f"Episode {display_index}: {video_key} segment [{segment_from}, {segment_to}) "
                    f"is outside its {actual_frames}-frame video file."
                )
            video_file_ranges.setdefault((video_key, video_path), []).append(
                (segment_from, segment_to, display_index)
            )

    for (video_key, video_path), ranges in video_file_ranges.items():
        expected_start = 0
        for segment_from, segment_to, display_index in sorted(ranges):
            if segment_from != expected_start:
                errors.append(
                    f"Episode {display_index}: {video_key} has a gap or overlap at frame "
                    f"{segment_from}; expected {expected_start} in {video_path.name}."
                )
            expected_start = segment_to
        actual_frames = video_file_frames[video_path]
        if actual_frames is not None and expected_start != actual_frames:
            errors.append(
                f"Video {video_key}/{video_path.name} has {actual_frames} frames, but its "
                f"episode segments cover {expected_start}."
            )

    return errors


def obs_state(obs: dict) -> dict[str, float]:
    return {key: float(obs[key]) for key in HOME_TOLERANCE}


def save_home_pose(home: dict[str, float]) -> None:
    HOME_POSE_PATH.write_text(json.dumps(home, indent=2), encoding="utf-8")


def convert_top_depth_to_mm(obs: dict) -> None:
    """Convert the D405's 0.1 mm device units to LeRobot's uint16 millimetres."""
    depth = obs.get("top_depth")
    if depth is None:
        raise RuntimeError("D405 depth frame is missing: expected observation key 'top_depth'.")

    obs["top_depth"] = np.rint(depth.astype(np.float32) * TOP_DEPTH_RAW_TO_MM).astype(np.uint16)


def is_home(obs: dict, home: dict[str, float]) -> bool:
    return all(abs(float(obs[key]) - home[key]) <= tol for key, tol in HOME_TOLERANCE.items())


def max_home_error(obs: dict, home: dict[str, float]) -> float:
    return max(abs(float(obs[key]) - home[key]) / tol for key, tol in HOME_TOLERANCE.items())


def largest_home_error(obs: dict, home: dict[str, float]) -> tuple[str, float, float]:
    errors = [
        (key, abs(float(obs[key]) - home[key]), tol)
        for key, tol in HOME_TOLERANCE.items()
    ]
    return max(errors, key=lambda item: item[1] / item[2])


def draw_status(
    obs: dict,
    status: str,
    episode_index: int,
    elapsed_s: float,
    home_error: float,
    home_stable_s: float,
    at_home: bool,
    worst_joint: str,
    worst_diff: float,
    worst_tol: float,
    failed: bool,
    prep_remaining_s: float | None = None,
) -> None:
    top = obs["top"]
    side = obs["side"]
    top_bgr = cv2.cvtColor(top, cv2.COLOR_RGB2BGR)
    side_bgr = cv2.cvtColor(side, cv2.COLOR_RGB2BGR)
    top_view = cv2.resize(top_bgr, (640, 480), interpolation=cv2.INTER_AREA)
    side_view = cv2.resize(side_bgr, (640, 480), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
    canvas[:480, :640] = top_view
    canvas[:480, 640:] = side_view

    color = (0, 255, 255)
    if failed:
        color = (0, 0, 255)
    elif at_home:
        color = (0, 220, 0)

    home_text = "HOME OK" if at_home else "NOT HOME"
    if prep_remaining_s is not None:
        cv2.rectangle(canvas, (0, 0), (1280, 480), (0, 0, 0), thickness=-1)
        if status == "START":
            start_text = "START"
            font_scale = 4.2
            thickness = 12
            text_size = cv2.getTextSize(
                start_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
            )[0]
            origin = ((1280 - text_size[0]) // 2, (480 + text_size[1]) // 2)
            cv2.putText(
                canvas,
                start_text,
                origin,
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                (0, 255, 255),
                thickness,
            )
        else:
            countdown = max(int(np.ceil(prep_remaining_s)), 0)
            cv2.putText(
                canvas,
                "PREPARE OBJECT",
                (300, 130),
                cv2.FONT_HERSHEY_SIMPLEX,
                2.0,
                (0, 255, 255),
                5,
            )
            cv2.putText(
                canvas,
                str(countdown),
                (560, 400),
                cv2.FONT_HERSHEY_SIMPLEX,
                7.0,
                (0, 255, 255),
                14,
            )

    cv2.putText(canvas, f"EP {episode_index}", (24, 550), cv2.FONT_HERSHEY_SIMPLEX, 1.8, color, 4)
    cv2.putText(canvas, status, (250, 550), cv2.FONT_HERSHEY_SIMPLEX, 1.6, color, 4)
    cv2.putText(canvas, home_text, (760, 550), cv2.FONT_HERSHEY_SIMPLEX, 1.6, color, 4)
    cv2.putText(canvas, f"TIME {elapsed_s:5.1f}s", (24, 625), cv2.FONT_HERSHEY_SIMPLEX, 1.5, color, 4)
    cv2.putText(
        canvas,
        f"HOME ERR {home_error:4.2f}  STABLE {home_stable_s:3.1f}s",
        (380, 625),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.1,
        color,
        3,
    )
    cv2.putText(canvas, "f = discard now    q = quit", (24, 690), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)

    cv2.imshow("SO-101 Auto Home Recording", canvas)


def make_configs() -> tuple[SOLeaderTeleopConfig, SOFollowerRobotConfig]:
    teleop_config = SOLeaderTeleopConfig(
        port="COM4",
        id="leader",
        calibration_dir=CALIBRATION_ROOT / "teleoperators" / "so_leader",
    )
    robot_config = SOFollowerRobotConfig(
        port="COM3",
        id="follower",
        calibration_dir=CALIBRATION_ROOT / "robots" / "so_follower",
        num_read_retries=10,
        num_write_retries=10,
        max_relative_target=5.0,
        cameras={
            "top": RealSenseCameraConfig(
                serial_number_or_name="352122273503",
                width=640,
                height=480,
                fps=30,
                color_mode="rgb",
                use_depth=True,
                exposure=10000,
                gain=16,
            ),
            "side": OpenCVCameraConfig(
                index_or_path=0,
                width=640,
                height=480,
                fps=30,
                color_mode="rgb",
                backend=Cv2Backends.DSHOW,
                warmup_s=3,
            ),
        },
    )
    return teleop_config, robot_config


def main() -> None:
    init_logging()
    validate_calibration_files()
    dataset_mode = choose_dataset_mode()

    if dataset_mode == "resume":
        print("Checking the existing dataset before continuing...")
        try:
            recover_uncommitted_tail()
            validation_errors = validate_existing_dataset()
        except Exception as exc:
            raise SystemExit(f"Dataset validation failed before resume: {exc}") from exc
        if validation_errors:
            print("Cannot continue because the existing dataset has integrity problems:")
            for error in validation_errors:
                print(f"  - {error}")
            raise SystemExit(
                "Resume was stopped without changing committed episodes. "
                "Repair the reported episode/data first, or restart and type reset to start over."
            )
        print("Existing dataset validation passed. Continuing collection.")

    teleop_config, robot_config = make_configs()
    teleop = make_teleoperator_from_config(teleop_config)
    robot = make_robot_from_config(robot_config)
    teleop_action_processor, robot_action_processor, robot_observation_processor = make_default_processors()

    dataset_features = combine_feature_dicts(
        aggregate_pipeline_dataset_features(
            pipeline=teleop_action_processor,
            initial_features=create_initial_features(action=robot.action_features),
            use_videos=True,
        ),
        aggregate_pipeline_dataset_features(
            pipeline=robot_observation_processor,
            initial_features=create_initial_features(observation=robot.observation_features),
            use_videos=True,
        ),
    )

    if dataset_mode == "resume":
        dataset = LeRobotDataset.resume(
            REPO_ID,
            root=DATASET_ROOT,
            image_writer_processes=0,
            image_writer_threads=4 * len(robot.cameras),
            rgb_encoder=RGB_ENCODER,
            depth_encoder=DEPTH_ENCODER,
            streaming_encoding=True,
            encoder_queue_maxsize=ENCODER_QUEUE_MAXSIZE,
        )
    else:
        dataset = LeRobotDataset.create(
            REPO_ID,
            FPS,
            root=DATASET_ROOT,
            robot_type="so101_follower",
            features=dataset_features,
            use_videos=True,
            image_writer_processes=0,
            image_writer_threads=4 * len(robot.cameras),
            video_files_size_in_mb=1,
            rgb_encoder=RGB_ENCODER,
            depth_encoder=DEPTH_ENCODER,
            streaming_encoding=True,
            encoder_queue_maxsize=ENCODER_QUEUE_MAXSIZE,
        )

    saved_episode_count = dataset.num_episodes
    expected_depth_key = "observation.images.top_depth"
    if expected_depth_key not in dataset_features:
        raise RuntimeError(f"Depth feature was not created: {expected_depth_key}")

    save_thread: threading.Thread | None = None
    save_error: list[BaseException] = []

    def save_episode_background(saved_episode_index: int, duration_s: float) -> None:
        try:
            dataset.save_episode(parallel_encoding=True)
            print(f"[Episode {saved_episode_index}] saved ({duration_s:.1f}s).")
        except BaseException as exc:
            save_error.append(exc)

    def get_streaming_drops() -> dict[str, int]:
        writer = getattr(dataset, "writer", None)
        encoder = getattr(writer, "_streaming_encoder", None)
        dropped = getattr(encoder, "_dropped_frames", {})
        return {key: int(count) for key, count in dropped.items() if count}

    print()
    print("SO-101 auto-home recording")
    print("1. The fixed home pose is already set in this script.")
    print("2. Put the robot near home before starting.")
    print("3. Then the loop runs automatically:")
    print("   prep 5s -> start 1s -> record -> hold home 2s -> save/discard -> prep 5s ...")
    print("   failed episodes use prep 10s and reuse the same episode number.")
    print("Controls in OpenCV window: f = discard current episode now, q = quit")
    print()

    try:
        print("Connecting leader, follower, and cameras...")
        connect_with_saved_calibration(teleop, "leader")
        connect_with_saved_calibration(robot, "follower")
        print("Connected.")

        home = dict(HOME_POSE)
        save_home_pose(home)
        print("Using fixed home pose:")
        for key, value in home.items():
            print(f"  {key}: {value:.2f}")
        print(f"Saved home pose to: {HOME_POSE_PATH}")
        if dataset_mode == "resume":
            print(f"Continuing existing dataset. Next episode number: {saved_episode_count + 1}")
        else:
            print("Starting a new dataset. Next episode number: 1")
        print()

        episode_index = saved_episode_count
        status = "reset"
        reset_started_at = time.perf_counter()
        reset_duration_s = RESET_TIME_S
        start_started_at: float | None = None
        episode_started_at: float | None = None
        home_since: float | None = None
        left_home = False
        failed = False
        stop_all = False
        cv2.namedWindow("SO-101 Auto Home Recording", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("SO-101 Auto Home Recording", 1280, 720)

        with VideoEncodingManager(dataset):
            while not stop_all:
                loop_started_at = time.perf_counter()
                obs = robot.get_observation()
                convert_top_depth_to_mm(obs)
                raw_action = teleop.get_action()
                teleop_action = teleop_action_processor((raw_action, obs))
                robot_action_to_send = robot_action_processor((teleop_action, obs))
                robot.send_action(robot_action_to_send)

                obs_processed = robot_observation_processor(obs)
                at_home = is_home(obs, home)
                home_error = max_home_error(obs, home)
                worst_joint, worst_diff, worst_tol = largest_home_error(obs, home)
                now = time.perf_counter()

                if status == "reset":
                    if save_error:
                        raise save_error[0]

                    save_busy = save_thread is not None and save_thread.is_alive()
                    remaining = reset_duration_s - (now - reset_started_at)
                    draw_status(
                        obs,
                        "SAVING" if save_busy else "PREP",
                        episode_index + 1,
                        0.0,
                        home_error,
                        0.0,
                        at_home,
                        worst_joint,
                        worst_diff,
                        worst_tol,
                        failed=False,
                        prep_remaining_s=max(remaining, 0.0),
                    )
                    key = cv2.waitKeyEx(1)
                    if key in (ord("q"), ord("Q")):
                        stop_all = True

                    if remaining <= 0:
                        if save_busy:
                            continue
                        if save_thread is not None:
                            save_thread.join()
                            save_thread = None
                        status = "start"
                        start_started_at = now

                elif status == "start":
                    assert start_started_at is not None
                    remaining = START_TIME_S - (now - start_started_at)
                    draw_status(
                        obs,
                        "START",
                        episode_index + 1,
                        0.0,
                        home_error,
                        0.0,
                        at_home,
                        worst_joint,
                        worst_diff,
                        worst_tol,
                        failed=False,
                        prep_remaining_s=max(remaining, 0.0),
                    )
                    key = cv2.waitKeyEx(1)
                    if key in (ord("q"), ord("Q")):
                        stop_all = True

                    if remaining <= 0:
                        status = "recording"
                        episode_index += 1
                        start_started_at = None
                        episode_started_at = now
                        home_since = now if at_home else None
                        left_home = False
                        failed = False
                        reset_duration_s = RESET_TIME_S
                        print(f"[Episode {episode_index}] recording started.")

                elif status == "recording":
                    if not at_home:
                        left_home = True
                        home_since = None
                    elif home_since is None:
                        home_since = now

                    assert episode_started_at is not None
                    elapsed = now - episode_started_at
                    observation_frame = build_dataset_frame(
                        dataset.features, obs_processed, prefix=OBS_STR
                    )
                    action_frame = build_dataset_frame(dataset.features, teleop_action, prefix=ACTION)
                    dataset.add_frame({**observation_frame, **action_frame, "task": TASK})

                    dropped_frames = get_streaming_drops()
                    if dropped_frames and not failed:
                        failed = True
                        details = ", ".join(
                            f"{key}={count}" for key, count in sorted(dropped_frames.items())
                        )
                        print(
                            f"[Episode {episode_index}] encoder frame loss detected ({details}). "
                            "This episode will be discarded and retried automatically."
                        )

                    home_stable_s = 0.0 if home_since is None else now - home_since
                    draw_status(
                        obs,
                        "RECORDING",
                        episode_index,
                        elapsed,
                        home_error,
                        home_stable_s,
                        at_home,
                        worst_joint,
                        worst_diff,
                        worst_tol,
                        failed,
                    )

                    key = cv2.waitKeyEx(1)
                    if key in (ord("q"), ord("Q")):
                        dataset.clear_episode_buffer()
                        print(f"[Episode {episode_index}] discarded before quit.")
                        stop_all = True
                    elif key in (ord("f"), ord("F")):
                        status = "reset"
                        episode_index -= 1
                        reset_duration_s = DISCARD_RESET_TIME_S
                        reset_started_at = time.perf_counter()
                        draw_status(
                            obs,
                            "PREP",
                            episode_index + 1,
                            0.0,
                            home_error,
                            0.0,
                            at_home,
                            worst_joint,
                            worst_diff,
                            worst_tol,
                            failed=False,
                            prep_remaining_s=DISCARD_RESET_TIME_S,
                        )
                        cv2.waitKeyEx(1)
                        dataset.clear_episode_buffer()
                        print(f"[Episode {episode_index + 1}] discarded immediately. Waiting {DISCARD_RESET_TIME_S:.0f}s before retry.")
                        episode_started_at = None
                        home_since = None
                        left_home = False
                        failed = False
                        continue

                    should_finish = (
                        left_home
                        and elapsed >= MIN_EPISODE_TIME_S
                        and home_stable_s >= HOME_STABLE_TIME_S
                    )
                    timed_out = elapsed >= MAX_EPISODE_TIME_S

                    if should_finish or timed_out:
                        reset_started_at = time.perf_counter()
                        reset_duration_s = DISCARD_RESET_TIME_S if failed or timed_out else RESET_TIME_S
                        status = "reset"
                        draw_status(
                            obs,
                            "PREP",
                            episode_index + 1,
                            0.0,
                            home_error,
                            0.0,
                            at_home,
                            worst_joint,
                            worst_diff,
                            worst_tol,
                            failed=False,
                            prep_remaining_s=reset_duration_s,
                        )
                        cv2.waitKeyEx(1)

                        if failed or timed_out:
                            dataset.clear_episode_buffer()
                            reason = "timeout" if timed_out else "marked failed"
                            print(f"[Episode {episode_index}] discarded ({reason}).")
                            episode_index -= 1
                        else:
                            save_thread = threading.Thread(
                                target=save_episode_background,
                                args=(episode_index, elapsed),
                                daemon=False,
                            )
                            save_thread.start()

                        episode_started_at = None
                        home_since = None
                        left_home = False
                        failed = False

                dt_s = time.perf_counter() - loop_started_at
                precise_sleep(max(1 / FPS - dt_s, 0.0))

    except KeyboardInterrupt:
        print("Interrupted.")
        if dataset.has_pending_frames():
            dataset.clear_episode_buffer()
    finally:
        print("Finalizing dataset...")
        if save_thread is not None and save_thread.is_alive():
            save_thread.join()
        if save_error:
            print(f"Save failed: {save_error[0]}")
        dataset.finalize()
        cv2.destroyAllWindows()
        if robot.is_connected:
            robot.disconnect()
        if teleop.is_connected:
            teleop.disconnect()
        print("Done.")


if __name__ == "__main__":
    main()

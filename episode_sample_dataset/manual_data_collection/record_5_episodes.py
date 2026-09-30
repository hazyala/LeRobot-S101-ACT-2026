from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path

from lerobot.configs import RGBEncoderConfig
from lerobot.cameras import Cv2Backends
from lerobot.cameras.opencv import OpenCVCameraConfig
from lerobot.cameras.realsense import RealSenseCameraConfig
from lerobot.datasets import (
    LeRobotDataset,
    VideoEncodingManager,
    aggregate_pipeline_dataset_features,
    create_initial_features,
)
from lerobot.processor import make_default_processors
from lerobot.robots import make_robot_from_config
from lerobot.robots.so_follower.config_so_follower import SOFollowerRobotConfig
from lerobot.scripts.lerobot_record import record_loop
from lerobot.teleoperators import make_teleoperator_from_config
from lerobot.teleoperators.so_leader.config_so_leader import SOLeaderTeleopConfig
from lerobot.utils.feature_utils import combine_feature_dicts
from lerobot.utils.utils import init_logging


SCRIPT_DIR = Path(__file__).resolve().parent
DATASET_ROOT = SCRIPT_DIR / "dataset"

REPO_ID = "hazyala/so101_pickplace_sample"
TASK = "Pick up the object from the table and place it into the box."
FPS = 30
NUM_EPISODES = 5
MAX_EPISODE_TIME_S = 300


def delete_previous_dataset() -> None:
    if not DATASET_ROOT.exists():
        return

    resolved_root = SCRIPT_DIR.resolve()
    resolved_dataset = DATASET_ROOT.resolve()
    if resolved_root not in resolved_dataset.parents:
        raise RuntimeError(f"Refusing to delete outside this folder: {resolved_dataset}")

    print(f"Deleting previous dataset: {resolved_dataset}")
    shutil.rmtree(resolved_dataset)


def wait_for_enter_to_stop(events: dict, episode_index: int) -> None:
    input(f"[Episode {episode_index}] recording... Press Enter to STOP and SAVE. ")
    events["exit_early"] = True


def make_events() -> dict[str, bool]:
    return {
        "exit_early": False,
        "rerecord_episode": False,
        "stop_recording": False,
    }


def main() -> None:
    init_logging()
    delete_previous_dataset()

    teleop_config = SOLeaderTeleopConfig(
        port="COM4",
        id="leader",
    )

    robot_config = SOFollowerRobotConfig(
        port="COM3",
        id="follower",
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
                exposure=10000,
                gain=16,
            ),
            "front": OpenCVCameraConfig(
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
        rgb_encoder=RGBEncoderConfig(vcodec="h264", crf=23, preset="fast"),
    )

    print()
    print("SO-101 5 Episode Sample Recording")
    print(f"Dataset root: {DATASET_ROOT}")
    print()
    print("Controls:")
    print("  Enter = start episode")
    print("  Enter = stop and save episode")
    print("  Ctrl+C = abort")
    print()
    print("Before each episode, place the object on the table outside the box.")
    print("Keep the box fixed. Change only the object's start position.")
    print()

    try:
        print("Connecting leader, follower, and cameras...")
        teleop.connect()
        robot.connect()
        print("Connected.")
        print()

        with VideoEncodingManager(dataset):
            for episode_index in range(1, NUM_EPISODES + 1):
                input(f"[Episode {episode_index}/{NUM_EPISODES}] Place object, then press Enter to START. ")

                events = make_events()
                stop_thread = threading.Thread(
                    target=wait_for_enter_to_stop,
                    args=(events, episode_index),
                    daemon=True,
                )
                stop_thread.start()

                started_at = time.perf_counter()
                record_loop(
                    robot=robot,
                    events=events,
                    fps=FPS,
                    teleop_action_processor=teleop_action_processor,
                    robot_action_processor=robot_action_processor,
                    robot_observation_processor=robot_observation_processor,
                    dataset=dataset,
                    teleop=teleop,
                    control_time_s=MAX_EPISODE_TIME_S,
                    single_task=TASK,
                    display_data=False,
                )

                duration_s = time.perf_counter() - started_at
                if dataset.has_pending_frames():
                    dataset.save_episode(parallel_encoding=False)
                    print(f"[Episode {episode_index}] saved ({duration_s:.1f}s).")
                else:
                    print(f"[Episode {episode_index}] no frames captured; skipped.")

                print()

    except KeyboardInterrupt:
        print()
        print("Recording aborted by user.")
        if dataset.has_pending_frames():
            dataset.clear_episode_buffer()
    finally:
        print("Finalizing dataset...")
        dataset.finalize()
        if robot.is_connected:
            robot.disconnect()
        if teleop.is_connected:
            teleop.disconnect()
        print("Done.")


if __name__ == "__main__":
    main()

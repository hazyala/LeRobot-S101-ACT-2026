"""SO-101 TOP·SIDE RGB 에피소드 수집."""

import argparse
from contextlib import suppress
from pathlib import Path
from queue import Empty, Queue
import sys
from threading import Event, Thread
import time


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CALIBRATION_DIR = PROJECT_ROOT / "datasets" / "calibration"

LEADER_PORT = "COM4"  # 확인한 리더 포트로 수정
FOLLOWER_PORT = "COM3"  # 확인한 팔로워 포트로 수정
TOP_SERIAL = "262422273645"  # TOP RealSense 시리얼 번호로 수정
SIDE_CAMERA_INDEX = 0  # 카메라 테스트에서 확인한 SIDE 번호로 수정

PREPARE_SECONDS = 5  # 다음 에피소드 준비 시간
START_SECONDS = 1  # 녹화 시작 안내 시간
DISCARD_WAIT_SECONDS = 10  # 실패 시연 폐기 후 대기 시간
HOME_HOLD_SECONDS = 2  # 홈 복귀 후 자동 저장까지 유지할 시간

CAMERA_NAMES = ("top", "side")
PREVIEW = "SO-101 | TOP / SIDE"


FPS = 30
MIN_EPISODE_SECONDS = 8
# 다른 로봇이나 캘리브레이션 사용 시 홈 자세와 허용 오차 확인
HOME = {
    "shoulder_pan.pos": (-5.8, 12),
    "shoulder_lift.pos": (-99.3, 12),
    "elbow_flex.pos": (101.05, 12),
    "wrist_flex.pos": (74.86, 18),
    "gripper.pos": (1.32, 20),
}


def is_home(observation):
    return all(abs(observation[key] - center) <= tolerance
               for key, (center, tolerance) in HOME.items())


def connect_with_saved_calibration(device, name):
    if not device.calibration:
        raise RuntimeError(f"{name}: 캘리브레이션을 불러오지 못했습니다.")
    device.connect(calibrate=False)
    if not device.is_calibrated:
        device.bus.write_calibration(device.calibration)
    if not device.is_calibrated:
        raise RuntimeError(f"{name}: 캘리브레이션 적용 실패")


def send_control_action(robot, leader, action_processor, robot_processor,
                        observation, timing):
    raw = dict(leader.get_action())
    action = action_processor((dict(raw), observation))
    sent = robot.send_action(robot_processor((action, observation)))
    return raw, sent


def wait_capture_tick(deadline, period):
    target = deadline + period
    now = time.perf_counter()
    if target > now:
        time.sleep(target - now)
    return max(target, now)


def receive_commands(commands, stopped):
    for line in sys.stdin:
        if stopped.is_set():
            return
        command = line.strip()
        if command in ("q", "f"):
            commands.put(command)
        if command == "q":
            return
    commands.put("q")


class AutoHomeCycle:
    def __init__(self, now, episodes, *, prepare, start, discard, minimum, stable):
        self.episode = episodes
        self.prepare = prepare
        self.start_delay = start
        self.discard_delay = discard
        self.minimum = minimum
        self.stable = stable
        self.reset(now, prepare)

    def reset(self, now, delay):
        self.state = "PREP"
        self.until = now + delay
        self.started = self.home_since = None
        self.left_home = False

    def remaining(self, now):
        return max(0, self.until - now)

    def step(self, now, at_home, command=None, save_busy=False):
        if self.state == "RECORDING":
            if command == "f":
                self.episode -= 1
                self.reset(now, self.discard_delay)
                return "discard"
            if not at_home:
                self.left_home = True
                self.home_since = None
            elif self.home_since is None:
                self.home_since = now
            if (at_home and self.left_home and now - self.started >= self.minimum
                    and now - self.home_since >= self.stable):
                self.reset(now, self.prepare)
                return "save"
        elif self.state == "PREP" and not save_busy and now >= self.until:
            self.state = "START"
            self.until = now + self.start_delay
        elif self.state == "START":
            if not at_home:
                self.reset(now, self.prepare)
            elif now >= self.until:
                self.state = "RECORDING"
                self.started = now
                self.episode += 1
        return None


def collect(destination, task, commands, report):
    import cv2
    import numpy as np
    from lerobot.cameras import Cv2Backends
    from lerobot.cameras.opencv import OpenCVCameraConfig
    from lerobot.cameras.realsense import RealSenseCameraConfig
    from lerobot.datasets import (
        LeRobotDataset, aggregate_pipeline_dataset_features, create_initial_features,
    )
    from lerobot.processor import make_default_processors
    from lerobot.robots import make_robot_from_config
    from lerobot.robots.so_follower.config_so_follower import SOFollowerRobotConfig
    from lerobot.teleoperators import make_teleoperator_from_config
    from lerobot.teleoperators.so_leader.config_so_leader import SOLeaderTeleopConfig
    from lerobot.utils.constants import ACTION, OBS_STR
    from lerobot.utils.feature_utils import build_dataset_frame, combine_feature_dicts
    from data_inspection import dataset_lock, inspect_episode, read_info, validate_resume

    for device_id in ("leader", "follower"):
        path = CALIBRATION_DIR / f"{device_id}.json"
        if not path.is_file():
            raise FileNotFoundError(path)

    leader_config = SOLeaderTeleopConfig(
        id="leader", port=LEADER_PORT, calibration_dir=CALIBRATION_DIR,
    )
    robot_config = SOFollowerRobotConfig(
        id="follower", port=FOLLOWER_PORT, calibration_dir=CALIBRATION_DIR,
        max_relative_target=5.0,
        cameras={
            "top": RealSenseCameraConfig(
                serial_number_or_name=TOP_SERIAL, width=640, height=480,
                fps=FPS, use_depth=False,
            ),
            "side": OpenCVCameraConfig(
                index_or_path=SIDE_CAMERA_INDEX, width=640, height=480,
                fps=FPS, backend=Cv2Backends.DSHOW, warmup_s=3,
            ),
        },
    )

    leader = make_teleoperator_from_config(leader_config)
    robot = make_robot_from_config(robot_config)
    action_processor, robot_processor, observation_processor = (
        make_default_processors()
    )

    features = combine_feature_dicts(
        aggregate_pipeline_dataset_features(
            pipeline=action_processor,
            initial_features=create_initial_features(
                action=robot.action_features
            ),
            use_videos=True,
        ),
        aggregate_pipeline_dataset_features(
            pipeline=observation_processor,
            initial_features=create_initial_features(
                observation=robot.observation_features
            ),
            use_videos=True,
        ),
    )

    joints = [f"{name}.pos" for name in robot.bus.motors]
    for key, dtype, names in (
        ("research.leader_action_raw", "float32", joints),
        (
            "research.camera_frame_numbers",
            "int64",
            ["top_host_sequence", "side_host_sequence"],
        ),
        ("research.camera_capture_s", "float32", list(CAMERA_NAMES)),
    ):
        features[key] = {
            "dtype": dtype,
            "shape": (len(names),),
            "names": names,
        }

    fps = FPS
    repo_id = f"local/{destination.name}"
    options = {
        "root": destination,
        "image_writer_threads": 2,
    }
    writer = None
    previous_stamp = {}
    sequence = dict.fromkeys(CAMERA_NAMES, 0)

    destination.parent.mkdir(parents=True, exist_ok=True)
    with dataset_lock(destination):
        if destination.exists():
            validate_resume(destination, task, features)

        try:
            report("리더와 팔로워 연결 중")
            connect_with_saved_calibration(leader, "leader")
            connect_with_saved_calibration(robot, "follower")

            if destination.exists():
                writer = LeRobotDataset.resume(repo_id, **options)
            else:
                writer = LeRobotDataset.create(
                    repo_id,
                    fps,
                    features,
                    robot_type="so101_follower",
                    use_videos=True,
                    **options,
                )

            # 홈을 벗어난 시연만 자동 저장 대상. 최소 기록 시간과 홈 유지 시간 적용
            cycle = AutoHomeCycle(
                time.perf_counter(),
                writer.num_episodes,
                prepare=PREPARE_SECONDS,
                start=START_SECONDS,
                discard=DISCARD_WAIT_SECONDS,
                minimum=MIN_EPISODE_SECONDS,
                stable=HOME_HOLD_SECONDS,
            )
            deadline = time.perf_counter()

            while True:
                # q: 수집 종료, f: 현재 시연 폐기
                pending = set()
                while True:
                    try:
                        pending.add(commands.get_nowait())
                    except Empty:
                        break
                if "q" in pending:
                    break

                observation = {}
                timing = {}
                for name in CAMERA_NAMES:
                    camera = robot.cameras[name]
                    with camera.frame_lock:
                        frame = (
                            camera.latest_color_frame
                            if name == "top"
                            else camera.latest_frame
                        )
                        stamp = camera.latest_timestamp

                    if frame is None or stamp is None:
                        raise RuntimeError(
                            f"{name.upper()} RGB 프레임을 받지 못했습니다."
                        )

                    # 새 수신 시각에만 순번 증가. 같은 순번이 반복되면 영상 갱신 지연 확인
                    if stamp != previous_stamp.get(name):
                        sequence[name] += 1
                        previous_stamp[name] = stamp
                    observation[name] = frame
                    timing[f"{name}_capture"] = stamp

                preview = np.hstack([
                    cv2.cvtColor(
                        observation[name], cv2.COLOR_RGB2BGR
                    )
                    for name in CAMERA_NAMES
                ])
                cv2.imshow(PREVIEW, preview)
                key = cv2.waitKey(1)
                if key in (ord("q"), 27):
                    break
                if cv2.getWindowProperty(
                    PREVIEW, cv2.WND_PROP_VISIBLE
                ) < 1:
                    break

                if cycle.state == "RECORDING" and (
                    "f" in pending or key == ord("f")
                ):
                    cycle.step(time.perf_counter(), False, "f")
                    report(f"현재 시연 폐기 · {DISCARD_WAIT_SECONDS}초 대기")

                    # 저장 전 프레임만 폐기. 같은 에피소드 번호로 재시도
                    writer.writer._wait_image_writer()
                    writer.clear_episode_buffer()
                    continue

                positions = robot.bus.sync_read(
                    "Present_Position",
                    num_retry=robot.config.num_read_retries,
                )
                observation.update({
                    f"{name}.pos": value for name, value in positions.items()
                })
                raw, sent = send_control_action(
                    robot,
                    leader,
                    action_processor,
                    robot_processor,
                    observation,
                    timing,
                )
                now = time.perf_counter()
                at_home = is_home(observation)

                if cycle.state == "RECORDING":
                    # timestamp와 frame_index는 LeRobot에서 자동 기록
                    writer.add_frame({
                        **build_dataset_frame(
                            features,
                            observation_processor(observation),
                            prefix=OBS_STR,
                        ),
                        **build_dataset_frame(
                            features, sent, prefix=ACTION
                        ),
                        # 리더 원본값은 팔로워에 실제 전달한 목표값과 별도로 저장
                        "research.leader_action_raw": np.array(
                            [raw[joint] for joint in joints], dtype="float32"
                        ),
                        "research.camera_frame_numbers": np.array(
                            [sequence[name] for name in CAMERA_NAMES],
                            dtype="int64",
                        ),
                        # 녹화 시작 시점 기준 카메라별 프레임 수신 시각
                        "research.camera_capture_s": np.array(
                            [
                                timing[f"{name}_capture"] - cycle.started
                                for name in CAMERA_NAMES
                            ],
                            dtype="float32",
                        ),
                        "task": task,
                    })

                outcome = cycle.step(
                    now,
                    at_home,
                    save_busy=cycle.state == "PREP" and not at_home,
                )

                if outcome == "save":
                    report("에피소드 저장 및 RGB 검사 중")
                    writer.save_episode(parallel_encoding=False)
                    writer.finalize()
                    writer = None

                    # 저장된 RGB 영상과 프레임 수신 간격 검사 후 다음 시연 준비
                    index = read_info(destination)["total_episodes"] - 1
                    result = inspect_episode(destination, index)
                    report(
                        f"에피소드 {index:04d} 저장 · "
                        f"{result['frames']}프레임 · "
                        f"검사 알림 {len(result['issues'])}건"
                    )

                    writer = LeRobotDataset.resume(repo_id, **options)
                    deadline = time.perf_counter()

                elif cycle.state == "RECORDING":
                    report(
                        f"에피소드 {cycle.episode - 1:04d} 기록 중 · "
                        f"{now - cycle.started:.1f}초"
                    )
                elif cycle.state == "PREP" and not at_home:
                    report("다음 시연을 시작하려면 홈 자세로 돌아오세요.")
                else:
                    label = "시작" if cycle.state == "START" else "준비"
                    report(f"{label} · {cycle.remaining(now):.1f}초")

                deadline = wait_capture_tick(deadline, 1 / fps)

        finally:
            try:
                if writer is not None:
                    # 수집 종료 시 아직 저장하지 않은 시연 폐기
                    writer.writer._wait_image_writer()
                    writer.clear_episode_buffer()
                    writer.finalize()
            finally:
                cv2.destroyAllWindows()
                for device in (robot, leader):
                    with suppress(Exception):
                        device.disconnect()
                    for camera in getattr(device, "cameras", {}).values():
                        with suppress(Exception):
                            camera.disconnect()
                    with suppress(Exception):
                        if device.bus.is_connected:
                            device.bus.disconnect()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    parser.add_argument("task")
    args = parser.parse_args()

    commands = Queue()
    stopped = Event()
    Thread(
        target=receive_commands,
        args=(commands, stopped),
        daemon=True,
    ).start()

    last_message = None

    def report(message):
        nonlocal last_message
        if message != last_message:
            print(message, flush=True)
            last_message = message

    try:
        collect(args.destination.resolve(), args.task, commands, report)
    finally:
        stopped.set()


if __name__ == "__main__":
    main()
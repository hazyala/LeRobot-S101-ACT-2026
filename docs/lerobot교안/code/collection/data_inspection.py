"""LeRobot 에피소드 조회, RGB 영상 검사·재생, 선택 삭제."""

import argparse
from contextlib import contextmanager
import json
import shutil
from pathlib import Path
from uuid import uuid4


CAMERAS = ("top", "side")
MAX_REPEAT_RATIO = 0.05  # 반복 프레임이 전체의 5%를 넘으면 폐기
MAX_CAPTURE_GAP_SECONDS = 0.10  # 이 간격을 넘으면 카메라 수신 지연으로 표시
DEFAULT_FEATURES = {
    "timestamp", "frame_index", "episode_index", "index", "task_index",
}


def lossless_rgb_encoder():
    """RGB 원본 픽셀 보존. 설치된 PyAV의 libx264rgb 사용."""
    import av
    from lerobot.configs.video import RGBEncoderConfig

    class LosslessRGBEncoder(RGBEncoderConfig):
        def resolve_vcodec(self):
            if self.vcodec != "libx264rgb":
                raise ValueError("libx264rgb 인코더가 필요합니다.")

        def validate(self):
            codec = av.Codec(self.vcodec, "w")
            if not any(fmt.name == self.pix_fmt for fmt in codec.video_formats):
                raise ValueError("무손실 RGB 인코더를 사용할 수 없습니다.")

    return LosslessRGBEncoder(vcodec="libx264rgb", pix_fmt="rgb24",
                              crf=0, preset="ultrafast")


def read_info(root):
    path = Path(root) / "meta" / "info.json"
    return json.loads(path.read_text(encoding="utf-8"))


def dataset_size(root):
    return sum(
        path.stat().st_size
        for path in Path(root).rglob("*")
        if path.is_file()
    )


def episode_rows(root):
    import pyarrow.parquet as pq

    directory = Path(root) / "meta" / "episodes"
    rows = [
        row
        for path in directory.rglob("*.parquet")
        for row in pq.read_table(path).to_pylist()
    ]
    return sorted(rows, key=lambda row: row["episode_index"])


def find_episode(root, index):
    for row in episode_rows(root):
        if row["episode_index"] == index:
            return row
    raise ValueError(f"에피소드 {index}번을 찾을 수 없습니다.")


def validate_resume(root, task, features):
    import pyarrow.parquet as pq

    root = Path(root)
    info = read_info(root)
    saved_features = info["features"]

    # 수집 항목이 다른 데이터셋에 이어 쓰는 경우 방지
    extra = set(saved_features) - set(features) - DEFAULT_FEATURES
    if extra:
        raise ValueError(f"기존 데이터셋에 다른 저장 항목이 있습니다: {sorted(extra)}")

    for key, expected in features.items():
        saved = saved_features.get(key, {})
        if (
            saved.get("dtype") != expected["dtype"]
            or saved.get("shape") != list(expected["shape"])
            or saved.get("names") != expected.get("names")
        ):
            raise ValueError(f"기존 데이터셋과 저장 형식이 다릅니다: {key}")

    if info["total_episodes"] > 0:
        tasks = pq.read_table(root / "meta" / "tasks.parquet")
        if set(tasks["task"].to_pylist()) != {task}:
            raise ValueError("기존 데이터셋의 작업 설명과 일치해야 이어서 수집할 수 있습니다.")


def video_segment(root, info, episode, camera):
    key = f"observation.images.{camera}"
    prefix = f"videos/{key}/"
    filename = info["video_path"].format(
        video_key=key,
        chunk_index=episode[prefix + "chunk_index"],
        file_index=episode[prefix + "file_index"],
    )
    start = episode[prefix + "from_timestamp"]
    end = episode[prefix + "to_timestamp"]
    return Path(root) / filename, start, end


def inspect_episode(root, index):
    import cv2
    import pyarrow.parquet as pq

    root = Path(root)
    info = read_info(root)
    episode = find_episode(root, index)
    fps = info["fps"]

    filename = info["data_path"].format(
        chunk_index=episode["data/chunk_index"],
        file_index=episode["data/file_index"],
    )
    table = pq.read_table(
        root / filename,
        filters=[("episode_index", "=", index)],
    )
    frames = sorted(table.to_pylist(), key=lambda frame: frame["frame_index"])
    issues = []
    notes = []

    if len(frames) != episode["length"]:
        issues.append(f"프레임 수 불일치 · 예상 {episode['length']} / 실제 {len(frames)}")

    if any(frame["frame_index"] != i for i, frame in enumerate(frames)):
        issues.append("에피소드 내 frame_index가 연속되지 않습니다.")

    columns = set(table.column_names)
    has_capture_timing = "research.camera_capture_s" in columns
    has_legacy_timing = "research.capture_timing_s" in columns
    has_camera_records = (
        "research.camera_frame_numbers" in columns
        and (has_capture_timing or has_legacy_timing)
    )
    if not has_camera_records:
        notes.append("카메라 순번 또는 수신 시각이 없어 반복 프레임과 수신 간격 검사 생략")

    for camera_index, camera in enumerate(CAMERAS):
        label = camera.upper()
        previous = None
        repeated = 0

        for frame in frames if has_camera_records else ():
            numbers = frame["research.camera_frame_numbers"]
            stamps = (
                frame["research.camera_capture_s"]
                if has_capture_timing
                else frame["research.capture_timing_s"][2:4]
            )

            # 구형 데이터셋의 TOP·Depth·SIDE 순번도 지원
            number = numbers[0 if camera == "top" else -1]
            stamp = stamps[camera_index]
            timestamp = frame["timestamp"]

            if previous is not None:
                previous_number, previous_stamp = previous
                gap = stamp - previous_stamp

                if number == previous_number:
                    repeated += 1
                elif number < previous_number or gap < 0:
                    issues.append(f"{label} {timestamp:.2f}초 · 순번 또는 시각 역전")

                if gap > MAX_CAPTURE_GAP_SECONDS:
                    issues.append(f"{label} {timestamp:.2f}초 · 수신 간격 {gap:.3f}초")

            previous = number, stamp

        if repeated:
            ratio = repeated / max(len(frames) - 1, 1)
            summary = f"{label} 반복 프레임 {repeated}개 ({ratio:.1%})"
            (issues if ratio > MAX_REPEAT_RATIO else notes).append(summary)

        # 공유 MP4에서 이 에피소드의 첫 프레임과 마지막 프레임 확인
        path, start, end = video_segment(root, info, episode, camera)
        capture = cv2.VideoCapture(str(path))
        try:
            if not capture.isOpened():
                issues.append(f"{label} · 영상을 열 수 없음: {path.name}")
                continue

            first_frame = round(start * fps)
            last_frame = max(first_frame, round(end * fps) - 1)
            for frame_index in sorted({first_frame, last_frame}):
                capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ok, _ = capture.read()
                if not ok:
                    relative_time = (frame_index - first_frame) / fps
                    issues.append(f"{label} {relative_time:.2f}초 · 영상 읽기 실패")
        finally:
            capture.release()

    return {
        "episode_index": index,
        "frames": len(frames),
        "seconds": len(frames) / fps,
        "issues": issues,
        "notes": notes,
    }


def play_episode(root, index):
    import cv2

    root = Path(root)
    info = read_info(root)
    episode = find_episode(root, index)
    fps = info["fps"]
    captures = {}

    try:
        for camera in CAMERAS:
            path, start, _ = video_segment(root, info, episode, camera)
            capture = cv2.VideoCapture(str(path))
            captures[camera] = capture
            if not capture.isOpened():
                raise RuntimeError(f"{camera.upper()} 영상을 열 수 없습니다: {path}")
            capture.set(cv2.CAP_PROP_POS_FRAMES, round(start * fps))

        # 같은 에피소드의 TOP·SIDE 프레임을 나란히 재생
        for _ in range(episode["length"]):
            images = []
            for camera, capture in captures.items():
                ok, image = capture.read()
                if not ok:
                    raise RuntimeError(f"{camera.upper()} 영상 읽기 실패")
                images.append(image)

            cv2.imshow("TOP / SIDE | Q or Esc to close", cv2.hconcat(images))
            if (cv2.waitKey(max(1, round(1000 / fps))) & 0xFF) in (ord("q"), 27):
                break
    finally:
        for capture in captures.values():
            capture.release()
        cv2.destroyAllWindows()


@contextmanager
def dataset_lock(root):
    import msvcrt

    # 수집 코드와 같은 잠금 파일 사용
    path = root.with_name(root.name + ".collection.lock")
    with path.open("a+b") as lock:
        if lock.seek(0, 2) == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise RuntimeError("수집 또는 삭제가 진행 중인 데이터셋입니다.") from error

        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def remove_episode_locked(root, index):
    """잠금을 보유한 상태에서 재구성 후 선택 에피소드 삭제."""
    import lerobot.datasets.dataset_tools as dataset_tools
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    root = Path(root).resolve()
    count = read_info(root)["total_episodes"]
    if not 0 <= index < count:
        raise ValueError(f"삭제할 에피소드가 없습니다: {index}")
    if count == 1:
        shutil.rmtree(root)
        return

    token = uuid4().hex[:10]
    staged = root.with_name(f"{root.name}_rebuilt_{token}")
    old = root.with_name(f"{root.name}_replacing_{token}")
    repo_id = f"local/{root.name}"
    dataset = LeRobotDataset(repo_id, root=root)
    original_encoder = dataset_tools.encoder_config_from_video_info
    def encoder_for_info(info):
        if (info.get("video.codec") == "h264" and info.get("video.pix_fmt") == "gbrp"
                and info.get("video.crf") == 0):
            return lossless_rgb_encoder()
        return original_encoder(info)
    dataset_tools.encoder_config_from_video_info = encoder_for_info
    try:
        rebuilt = dataset_tools.delete_episodes(dataset, [index], output_dir=staged, repo_id=repo_id)
    finally:
        dataset_tools.encoder_config_from_video_info = original_encoder
    del dataset, rebuilt
    indices = [row["episode_index"] for row in episode_rows(staged)]
    if (read_info(staged)["total_episodes"] != count - 1
            or indices != list(range(count - 1))):
        raise RuntimeError(f"재구성 검증 실패: {staged}")

    # 교체 실패 시 기존 데이터셋 복구. 교체 성공 후 원본 제거
    root.rename(old)
    try:
        staged.rename(root)
    except OSError:
        old.rename(root)
        raise
    shutil.rmtree(old)


def remove_episode(root, index):
    root = Path(root).resolve()
    with dataset_lock(root):
        remove_episode_locked(root, index)


def main():
    parser = argparse.ArgumentParser(description="LeRobot 에피소드 검사")
    parser.add_argument("root", type=Path, help="데이터셋 폴더")
    parser.add_argument("episode", type=int, help="0부터 시작하는 에피소드 번호")
    parser.add_argument("--play", action="store_true", help="TOP·SIDE 영상 재생")
    args = parser.parse_args()

    result = inspect_episode(args.root, args.episode)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.play:
        play_episode(args.root, args.episode)


if __name__ == "__main__":
    main()
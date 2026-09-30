"""Build contact sheets for side-by-side inspection of two robot test videos."""

from pathlib import Path

import cv2
import numpy as np


VIDEOS = [
    Path(r"C:\Users\AISW-509-IP\Desktop\KakaoTalk_20260923_124237418.mp4"),
    Path(r"C:\Users\AISW-509-IP\Desktop\KakaoTalk_20260923_130232366.mp4"),
    Path(r"C:\Users\AISW-509-IP\Desktop\KakaoTalk_20260923_133057949.mp4"),
    Path(r"C:\Users\AISW-509-IP\Desktop\KakaoTalk_성공 1.mp4"),
    Path(r"C:\Users\AISW-509-IP\Desktop\KakaoTalk_20260923_성공2.mp4"),
]
OUTPUT_DIR = Path(__file__).resolve().parent / "video_diagnostics"


def inspect(video_path: Path) -> None:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Cannot open {video_path}")
    fps = capture.get(cv2.CAP_PROP_FPS)
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = frame_count / fps
    print(
        f"{video_path.name}: {width}x{height}, {fps:.3f} fps, "
        f"{frame_count} frames, {duration:.2f}s"
    )

    frames = []
    for timestamp in np.linspace(0.0, max(0.0, duration - 0.05), 20):
        capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000.0)
        ok, frame = capture.read()
        if not ok:
            continue
        scale = 320 / frame.shape[1]
        frame = cv2.resize(frame, (320, int(frame.shape[0] * scale)))
        cv2.rectangle(frame, (0, 0), (110, 25), (0, 0, 0), -1)
        cv2.putText(
            frame,
            f"{timestamp:5.2f}s",
            (6, 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        frames.append(frame)
    capture.release()

    rows = []
    for offset in range(0, len(frames), 5):
        row = frames[offset : offset + 5]
        if len(row) < 5:
            row.extend([np.zeros_like(frames[0])] * (5 - len(row)))
        rows.append(np.hstack(row))
    sheet = np.vstack(rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_DIR / f"{video_path.stem}_contact_sheet.jpg"
    encoded, buffer = cv2.imencode(".jpg", sheet)
    if not encoded:
        raise RuntimeError(f"Cannot encode contact sheet for {video_path}")
    buffer.tofile(str(output))
    print(output)


def inspect_range(video_path: Path, start_s: float, end_s: float, label: str) -> None:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Cannot open {video_path}")
    frames = []
    for timestamp in np.linspace(start_s, end_s, 16):
        capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000.0)
        ok, frame = capture.read()
        if not ok:
            continue
        scale = 400 / frame.shape[1]
        frame = cv2.resize(frame, (400, int(frame.shape[0] * scale)))
        cv2.rectangle(frame, (0, 0), (125, 28), (0, 0, 0), -1)
        cv2.putText(
            frame, f"{timestamp:5.2f}s", (8, 21), cv2.FONT_HERSHEY_SIMPLEX,
            0.65, (255, 255, 255), 1, cv2.LINE_AA,
        )
        frames.append(frame)
    capture.release()
    if len(frames) != 16:
        raise RuntimeError(f"Expected 16 frames from {video_path}, got {len(frames)}")
    sheet = np.vstack([np.hstack(frames[i : i + 4]) for i in range(0, 16, 4)])
    output = OUTPUT_DIR / f"{video_path.stem}_{label}.jpg"
    encoded, buffer = cv2.imencode(".jpg", sheet)
    if not encoded:
        raise RuntimeError(f"Cannot encode {output}")
    buffer.tofile(str(output))
    print(output)


if __name__ == "__main__":
    for video in VIDEOS:
        if video.is_file():
            inspect(video)
    success = VIDEOS[-1]
    if success.is_file():
        inspect_range(success, 16.5, 19.5, "first_contact")
        inspect_range(success, 30.5, 33.0, "second_grasp")

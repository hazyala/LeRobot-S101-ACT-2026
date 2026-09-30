from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from lerobot.cameras.realsense import RealSenseCamera, RealSenseCameraConfig


SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = SCRIPT_DIR / "top_exposure_test.png"


def main() -> None:
    camera = RealSenseCamera(
        RealSenseCameraConfig(
            serial_number_or_name="352122273503",
            width=640,
            height=480,
            fps=30,
            color_mode="rgb",
            exposure=10000,
            gain=16,
            warmup_s=3,
        )
    )

    camera.connect()
    try:
        frame = camera.read_latest()
    finally:
        camera.disconnect()

    Image.fromarray(frame).save(OUTPUT_PATH)

    gray = frame.mean(axis=2)
    bright = float((gray >= 245).mean() * 100)
    white_sat = float((frame >= 250).all(axis=2).mean() * 100)
    print(f"saved       : {OUTPUT_PATH}")
    print(f"mean        : {gray.mean():.1f}")
    print(f"p95         : {np.percentile(gray, 95):.1f}")
    print(f"p99         : {np.percentile(gray, 99):.1f}")
    print(f"bright>=245 : {bright:.1f}%")
    print(f"white_sat   : {white_sat:.1f}%")


if __name__ == "__main__":
    main()

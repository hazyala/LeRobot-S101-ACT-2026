from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2
import numpy as np
import pyrealsense2 as rs


# 이 스크립트는 Intel RealSense D405가 Python에서 정상 동작하는지 확인합니다.
# 학습용 코드는 아니고, 탑뷰 카메라로 쓸 D405의 color/depth 프레임을 테스트합니다.

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "notes" / "realsense_D405_test"


def list_realsense_devices() -> list[rs.device]:
    """PC에 연결된 RealSense 장치 목록을 출력하고 돌려줍니다."""
    context = rs.context()
    devices = list(context.query_devices())

    if not devices:
        print("[ERROR] 연결된 RealSense 장치를 찾지 못했습니다.")
        print("        D405 USB-C 케이블 연결, 장치 관리자, 권한을 확인하세요.")
        return []

    print("[RealSense devices]")
    for index, device in enumerate(devices):
        name = device.get_info(rs.camera_info.name)
        serial = device.get_info(rs.camera_info.serial_number)
        firmware = device.get_info(rs.camera_info.firmware_version)
        usb_type = (
            device.get_info(rs.camera_info.usb_type_descriptor)
            if device.supports(rs.camera_info.usb_type_descriptor)
            else "unknown"
        )
        print(f"  {index}: {name}")
        print(f"     serial   : {serial}")
        print(f"     firmware : {firmware}")
        print(f"     usb      : {usb_type}")

    return devices


def choose_d405_serial(devices: list[rs.device], requested_serial: str | None) -> str:
    """사용할 D405의 serial number를 고릅니다."""
    if requested_serial:
        return requested_serial

    for device in devices:
        name = device.get_info(rs.camera_info.name)
        if "D405" in name:
            return device.get_info(rs.camera_info.serial_number)

    print("[WARN] 장치 이름에 D405가 보이지 않습니다. 첫 번째 RealSense 장치를 사용합니다.")
    return devices[0].get_info(rs.camera_info.serial_number)


def make_pipeline(serial: str, width: int, height: int, fps: int) -> tuple[rs.pipeline, rs.pipeline_profile]:
    """color/depth stream을 켜는 RealSense pipeline을 만듭니다."""
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_device(serial)
    config.enable_stream(rs.stream.color, width, height, rs.format.bgr8, fps)
    config.enable_stream(rs.stream.depth, width, height, rs.format.z16, fps)

    try:
        profile = pipeline.start(config)
    except RuntimeError as error:
        print("[WARN] 요청한 해상도/FPS로 시작하지 못했습니다.")
        print(f"       requested: {width}x{height} @ {fps}fps")
        print(f"       reason   : {error}")
        print("       기본 color/depth stream으로 다시 시도합니다.")

        config = rs.config()
        config.enable_device(serial)
        config.enable_stream(rs.stream.color)
        config.enable_stream(rs.stream.depth)
        profile = pipeline.start(config)

    return pipeline, profile


def save_frames(color_image: np.ndarray, depth_image: np.ndarray, depth_scale: float) -> None:
    """받은 color/depth 프레임을 notes/realsense_D405_test 폴더에 저장합니다."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    color_path = OUTPUT_DIR / "d405_top_color.png"
    depth_raw_path = OUTPUT_DIR / "d405_top_depth_raw.png"
    depth_view_path = OUTPUT_DIR / "d405_top_depth_colormap.png"

    # color는 사람이 바로 볼 수 있는 BGR 이미지입니다.
    cv2.imwrite(str(color_path), color_image)

    # depth raw는 16-bit PNG입니다. 픽셀값 * depth_scale = meter 거리입니다.
    cv2.imwrite(str(depth_raw_path), depth_image)

    # depth colormap은 사람이 눈으로 확인하기 쉬운 가짜 색상 이미지입니다.
    depth_8bit = cv2.convertScaleAbs(depth_image, alpha=0.03)
    depth_colormap = cv2.applyColorMap(depth_8bit, cv2.COLORMAP_JET)
    cv2.imwrite(str(depth_view_path), depth_colormap)

    valid_depth = depth_image[depth_image > 0]
    if valid_depth.size:
        min_m = float(valid_depth.min() * depth_scale)
        max_m = float(valid_depth.max() * depth_scale)
    else:
        min_m = 0.0
        max_m = 0.0

    print("[Saved]")
    print(f"  color       : {color_path}")
    print(f"  depth raw   : {depth_raw_path}")
    print(f"  depth view  : {depth_view_path}")
    print("[Frame info]")
    print(f"  color shape : {color_image.shape}, dtype={color_image.dtype}")
    print(f"  depth shape : {depth_image.shape}, dtype={depth_image.dtype}")
    print(f"  depth scale : {depth_scale} meter/unit")
    print(f"  depth range : {min_m:.4f}m ~ {max_m:.4f}m")


def main() -> None:
    parser = argparse.ArgumentParser(description="Intel RealSense D405 top-view camera test")
    parser.add_argument("--serial", help="여러 RealSense가 있을 때 사용할 D405 serial number")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=30, help="저장 전 버릴 초기 프레임 수")
    parser.add_argument("--preview", action="store_true", help="실시간 미리보기 창을 띄웁니다. q 또는 ESC로 종료")
    args = parser.parse_args()

    print(f"pyrealsense2: {rs.__version__}")
    devices = list_realsense_devices()
    if not devices:
        raise SystemExit(1)

    serial = choose_d405_serial(devices, args.serial)
    print(f"[Using] serial={serial}")

    pipeline, profile = make_pipeline(serial, args.width, args.height, args.fps)

    try:
        depth_sensor = profile.get_device().first_depth_sensor()
        depth_scale = depth_sensor.get_depth_scale()

        print("[Streaming]")
        print("  D405 color/depth stream started.")
        print("  If mounted as top-view, the saved color image should look down at the workspace.")

        color_image = None
        depth_image = None

        # 카메라가 켜진 직후 몇 프레임은 자동 노출/깊이값이 안정되지 않을 수 있습니다.
        for _ in range(max(args.warmup, 1)):
            frames = pipeline.wait_for_frames()
            color_frame = frames.get_color_frame()
            depth_frame = frames.get_depth_frame()
            if color_frame and depth_frame:
                color_image = np.asanyarray(color_frame.get_data())
                depth_image = np.asanyarray(depth_frame.get_data())

        if color_image is None or depth_image is None:
            print("[ERROR] color/depth 프레임을 받지 못했습니다.")
            raise SystemExit(1)

        save_frames(color_image, depth_image, depth_scale)

        if args.preview:
            print("[Preview] q 또는 ESC를 누르면 종료합니다.")
            while True:
                frames = pipeline.wait_for_frames()
                color_frame = frames.get_color_frame()
                depth_frame = frames.get_depth_frame()
                if not color_frame or not depth_frame:
                    continue

                color_image = np.asanyarray(color_frame.get_data())
                depth_image = np.asanyarray(depth_frame.get_data())
                depth_view = cv2.applyColorMap(
                    cv2.convertScaleAbs(depth_image, alpha=0.03),
                    cv2.COLORMAP_JET,
                )

                cv2.imshow("D405 top color", color_image)
                cv2.imshow("D405 top depth", depth_view)

                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break

    finally:
        pipeline.stop()
        if args.preview:
            cv2.destroyAllWindows()
        time.sleep(0.2)
        print("[Done] D405 test finished.")


if __name__ == "__main__":
    main()

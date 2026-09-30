from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2
import numpy as np
import pyrealsense2 as rs


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


def make_realsense_pipeline(
    serial: str, width: int, height: int, fps: int
) -> tuple[rs.pipeline, rs.pipeline_profile]:
    """RealSense color/depth stream을 켜는 pipeline을 만듭니다."""
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


def open_webcam(index: int) -> cv2.VideoCapture | None:
    """일반 웹캠을 엽니다."""
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)

    if not cap.isOpened():
        print(f"[ERROR] Webcam {index} 열기 실패")
        return None

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    print(f"[Webcam {index}]")
    print(f"  Resolution : {width} x {height}")
    print(f"  FPS        : {fps}")
    print()

    return cap


def save_frames(
    color_image: np.ndarray,
    depth_image: np.ndarray,
    depth_scale: float,
    webcam_frame: np.ndarray | None = None,
) -> None:
    """RealSense color/depth 프레임을 저장합니다."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    color_path = OUTPUT_DIR / "d405_top_color.png"
    depth_raw_path = OUTPUT_DIR / "d405_top_depth_raw.png"
    depth_view_path = OUTPUT_DIR / "d405_top_depth_colormap.png"
    webcam_path = OUTPUT_DIR / "webcam_front_color.png"

    cv2.imwrite(str(color_path), color_image)
    cv2.imwrite(str(depth_raw_path), depth_image)
    if webcam_frame is not None:
        cv2.imwrite(str(webcam_path), webcam_frame)

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
    if webcam_frame is not None:
        print(f"  webcam      : {webcam_path}")
    print("[Frame info]")
    print(f"  color shape : {color_image.shape}, dtype={color_image.dtype}")
    print(f"  depth shape : {depth_image.shape}, dtype={depth_image.dtype}")
    if webcam_frame is not None:
        print(f"  webcam shape: {webcam_frame.shape}, dtype={webcam_frame.dtype}")
    print(f"  depth scale : {depth_scale} meter/unit")
    print(f"  depth range : {min_m:.4f}m ~ {max_m:.4f}m")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RealSense D405 + Webcam 실시간 스트리밍"
    )
    parser.add_argument(
        "--serial", help="여러 RealSense가 있을 때 사용할 D405 serial number"
    )
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument(
        "--warmup", type=int, default=30, help="저장 전 버릴 초기 프레임 수"
    )
    parser.add_argument(
        "--webcam-index", type=int, default=0, help="사용할 웹캠 index (기본값: 0)"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="지정한 초만큼 스트리밍 후 자동 종료합니다. 생략하면 q/ESC까지 계속 실행합니다.",
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="cv2 미리보기 창을 띄우지 않습니다. 원격/자동 검사에 사용합니다.",
    )
    args = parser.parse_args()

    # ============ RealSense D405 초기화 ============
    print("=" * 60)
    print("RealSense D405 + Webcam 통합 스트리밍")
    print("=" * 60)
    print()

    print(f"pyrealsense2: {rs.__version__}")
    devices = list_realsense_devices()
    if not devices:
        raise SystemExit(1)

    serial = choose_d405_serial(devices, args.serial)
    print(f"[Using RealSense] serial={serial}\n")

    realsense_pipeline, realsense_profile = make_realsense_pipeline(
        serial, args.width, args.height, args.fps
    )

    # ============ Webcam 초기화 ============
    print(f"[Opening Webcam] index={args.webcam_index}\n")
    webcam_cap = open_webcam(args.webcam_index)

    if webcam_cap is None:
        print("[ERROR] 웹캠을 열 수 없습니다.")
        realsense_pipeline.stop()
        raise SystemExit(1)

    try:
        depth_sensor = realsense_profile.get_device().first_depth_sensor()
        depth_scale = depth_sensor.get_depth_scale()

        print("[Streaming Started]")
        print("  RealSense D405 color/depth stream started.")
        print("  Webcam stream started.")
        print("  Press 'q' or ESC to exit.\n")

        # ============ Warmup (처음 몇 프레임 스킵) ============
        color_image = None
        depth_image = None

        for _ in range(max(args.warmup, 1)):
            frames = realsense_pipeline.wait_for_frames()
            color_frame = frames.get_color_frame()
            depth_frame = frames.get_depth_frame()
            if color_frame and depth_frame:
                color_image = np.asanyarray(color_frame.get_data())
                depth_image = np.asanyarray(depth_frame.get_data())

        if color_image is None or depth_image is None:
            print("[ERROR] RealSense color/depth 프레임을 받지 못했습니다.")
            raise SystemExit(1)

        # ============ 초기 프레임 저장 ============
        ret_webcam, webcam_frame = webcam_cap.read()
        if not ret_webcam:
            print("[ERROR] Webcam 초기 프레임 읽기 실패")
            raise SystemExit(1)

        save_frames(color_image, depth_image, depth_scale, webcam_frame)

        # ============ 실시간 스트리밍 ============
        frame_count = 0
        start_time = time.perf_counter()
        while True:
            # RealSense 프레임 읽기
            frames = realsense_pipeline.wait_for_frames(timeout_ms=1000)
            color_frame = frames.get_color_frame()
            depth_frame = frames.get_depth_frame()

            if not color_frame or not depth_frame:
                print("[WARN] RealSense 프레임 읽기 실패")
                continue

            realsense_color = np.asanyarray(color_frame.get_data())
            realsense_depth = np.asanyarray(depth_frame.get_data())

            # Webcam 프레임 읽기
            ret_webcam, webcam_frame = webcam_cap.read()

            if not ret_webcam:
                print("[ERROR] Webcam 프레임 읽기 실패")
                break

            # ============ 프레임 정보 출력 ============
            frame_count += 1
            if frame_count % 30 == 0:  # 30프레임마다 출력
                print(f"[Frame {frame_count}]")
                print(f"  RealSense color: {realsense_color.shape}, {realsense_color.dtype}")
                print(f"  RealSense depth: {realsense_depth.shape}, {realsense_depth.dtype}")
                print(f"  Webcam        : {webcam_frame.shape}, {webcam_frame.dtype}")

            if not args.no_preview:
                # ============ 화면에 텍스트 추가 ============
                realsense_display = realsense_color.copy()
                webcam_display = webcam_frame.copy()

                cv2.putText(
                    realsense_display,
                    "RealSense D405",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 255, 0),
                    2,
                )
                cv2.putText(
                    realsense_display,
                    f"Frame: {frame_count}",
                    (20, 80),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 0),
                    2,
                )

                cv2.putText(
                    webcam_display,
                    f"Webcam {args.webcam_index}",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 255, 0),
                    2,
                )
                cv2.putText(
                    webcam_display,
                    f"Frame: {frame_count}",
                    (20, 80),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 0),
                    2,
                )

                # ============ 화면 출력 ============
                cv2.imshow("RealSense D405 Color", realsense_display)
                cv2.imshow(f"Webcam {args.webcam_index}", webcam_display)

                # ============ 키 입력 감지 ============
                key = cv2.waitKey(1) & 0xFF

                if key == ord("q") or key == 27:
                    print("\n[Exit] 사용자가 종료를 요청했습니다.")
                    break

            if args.duration is not None and time.perf_counter() - start_time >= args.duration:
                print(f"\n[Exit] duration {args.duration:.1f}s reached.")
                break

    finally:
        # ============ 정리 ============
        realsense_pipeline.stop()
        webcam_cap.release()
        cv2.destroyAllWindows()
        time.sleep(0.2)
        print("[Done] 스트리밍 종료.")


if __name__ == "__main__":
    main()

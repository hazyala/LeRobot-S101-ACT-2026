import cv2
import numpy as np
import pyrealsense2 as rs

from settings import TOP_SERIAL, SIDE_CAMERA_INDEX, FPS


# 카메라 해상도와 프레임
WIDTH = 640
HEIGHT = 480

# D405 수동 노출값
# 화면이 너무 밝으면 값을 낮추고, 어두우면 값을 높입니다.
D405_EXPOSURE = 9000


def main():
    # RealSense 카메라 설정
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_device(TOP_SERIAL)

    config.enable_stream(
        rs.stream.color,
        WIDTH,
        HEIGHT,
        rs.format.bgr8,
        FPS,
    )

    webcam = None
    realsense_started = False

    try:
        # RealSense 연결
        profile = pipeline.start(config)
        realsense_started = True
        print("RealSense 카메라 연결 완료")

        # D405 자동 노출 해제 및 수동 노출 설정
        sensor = profile.get_device().first_depth_sensor()
        sensor.set_option(rs.option.enable_auto_exposure, 0)
        sensor.set_option(rs.option.exposure, D405_EXPOSURE)

        print(f"D405 수동 노출값: {D405_EXPOSURE}")

        # Side 웹캠 연결
        webcam = cv2.VideoCapture(SIDE_CAMERA_INDEX, cv2.CAP_DSHOW)
        webcam.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
        webcam.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
        webcam.set(cv2.CAP_PROP_FPS, FPS)

        if not webcam.isOpened():
            print(f"웹캠 {SIDE_CAMERA_INDEX}번을 열 수 없습니다.")
            return

        print(f"웹캠 {SIDE_CAMERA_INDEX}번 연결 완료")
        print("카메라 창에서 Q 또는 Esc를 누르면 종료합니다.")

        while True:
            # Top 카메라 화면 읽기
            frames = pipeline.wait_for_frames()
            color_frame = frames.get_color_frame()

            if not color_frame:
                continue

            top_image = np.asanyarray(color_frame.get_data())

            # Side 카메라 화면 읽기
            success, side_image = webcam.read()

            if not success:
                print("웹캠 화면을 읽을 수 없습니다.")
                break

            # 두 화면의 크기 맞추기
            top_image = cv2.resize(top_image, (WIDTH, HEIGHT))
            side_image = cv2.resize(side_image, (WIDTH, HEIGHT))

            # 카메라 이름 표시
            cv2.putText(
                top_image,
                "TOP - RealSense D405",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
            )

            cv2.putText(
                side_image,
                "SIDE - Webcam",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
            )

            # 두 화면을 가로로 연결
            combined_image = np.hstack((top_image, side_image))
            cv2.imshow("Camera Test", combined_image)

            # Q 또는 Esc를 누르면 종료
            key = cv2.waitKey(1) & 0xFF

            if key == ord("q") or key == 27:
                break

    except RuntimeError as error:
        print(f"카메라 오류: {error}")

    finally:
        if realsense_started:
            pipeline.stop()

        if webcam is not None:
            webcam.release()

        cv2.destroyAllWindows()
        print("카메라 테스트 종료")


if __name__ == "__main__":
    main()
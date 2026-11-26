"""실습 장치와 수집 설정. PC와 로봇에 맞게 수정."""

LEADER_PORT = "COM4"  # 리더 포트
FOLLOWER_PORT = "COM3"  # 팔로워 포트
TOP_SERIAL = "262422273645"  # RealSense 시리얼 번호
SIDE_CAMERA_INDEX = 0  # SIDE 웹캠 번호
SIDE_FOURCC = None  # 웹캠이 지원하면 "MJPG"로 변경 후 수신 속도 확인

FPS = 30  # 카메라 프레임

import json
import os
import subprocess
from pathlib import Path

from settings import LEADER_PORT, FOLLOWER_PORT, TOP_SERIAL, SIDE_CAMERA_INDEX, FPS


# 프로젝트 폴더
PROJECT_DIR = Path(__file__).resolve().parent.parent

# 가상환경의 Scripts 폴더
VENV_SCRIPTS = PROJECT_DIR / "lerobot" / "Scripts"

# LeRobot 실행 파일
TELEOPERATE = VENV_SCRIPTS / "lerobot-teleoperate.exe"

# 캘리브레이션 파일 폴더
CALIBRATION_DIR = PROJECT_DIR / "datasets" / "calibration"


def main():
    command = [
        str(TELEOPERATE),

        # Leader 설정
        "--teleop.type=so101_leader",
        f"--teleop.port={LEADER_PORT}",
        "--teleop.id=leader",
        f"--teleop.calibration_dir={CALIBRATION_DIR}",

        # Follower 설정
        "--robot.type=so101_follower",
        f"--robot.port={FOLLOWER_PORT}",
        "--robot.id=follower",
        f"--robot.calibration_dir={CALIBRATION_DIR}",

        # 카메라 2대 설정
        "--robot.cameras=" + json.dumps({
            "top": {"type": "intelrealsense", "serial_number_or_name": TOP_SERIAL,
                    "width": 640, "height": 480, "fps": FPS},
            "side": {"type": "opencv", "index_or_path": SIDE_CAMERA_INDEX,
                     "backend": "DSHOW", "width": 640, "height": 480,
                     "fps": FPS, "warmup_s": 3},
        }),

        # 관절값 표시 및 Rerun 시각화
        "--display_data=true",
    ]

    if not TELEOPERATE.exists():
        print(f"LeRobot 실행 파일을 찾을 수 없습니다: {TELEOPERATE}")
        return

    # 가상환경의 실행 파일을 찾을 수 있도록 PATH에 추가
    env = os.environ.copy()
    env["PATH"] = str(VENV_SCRIPTS) + os.pathsep + env.get("PATH", "")

    print("텔레오퍼레이션을 시작합니다.")
    print("종료하려면 터미널에서 Ctrl + C를 누르세요.")

    try:
        result = subprocess.run(command, env=env)

        if result.returncode != 0:
            print(f"\n실행이 종료되었습니다. 종료 코드: {result.returncode}")
            print("위에 표시된 오류 내용을 확인해 주세요.")

    except KeyboardInterrupt:
        print("\n텔레오퍼레이션을 종료합니다.")


if __name__ == "__main__":
    main()
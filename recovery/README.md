# 복구 안내

이 디렉터리에는 연구용 환경을 다시 구성할 때 참고할 패키지 목록과 수정된 LeRobot 소스를 보관한다. 수집 데이터와 학습 모델은 포함하지 않는다.

## LeRobot 소스 복원

`upstream.json`에 기록된 저장소와 커밋을 사용한다. 변경사항은 `lerobot-custom.patch`에 있으며, 변경된 12개 파일의 실제 사본은 `modified-source/`에 같은 경로로 보관한다.

```powershell
git clone https://github.com/huggingface/lerobot.git lerobot
git -C lerobot checkout 7e241bd630a3719a56157a497ce5d08f244784f1
git -C lerobot apply --check ../recovery/lerobot-custom.patch
git -C lerobot apply ../recovery/lerobot-custom.patch
```

위 명령은 이 저장소의 최상위 디렉터리에서 실행한다. 기존 환경에서 별도 수정한 코드이므로 설치 후 카메라, 모터, 데이터 수집 기능을 다시 점검한다.

## 환경 및 실습

- `research-requirements-freeze.txt`: 연구용 가상환경의 패키지 목록
- `practice-requirements-freeze.txt`: 실습용 가상환경의 패키지 목록
- `practice/README.md`: 실습 설치와 실행 안내
- `practice/docs/`: 실습 사용 안내 및 자료
- `practice/lecture/`: 강의 PDF와 PPTX
- `practice/datasets/calibration/`: 실습 장비의 기존 보정값. 다른 장비에는 보정값을 그대로 사용하지 않는다.

패키지 목록은 설치 당시 상태를 기록한 것으로, 다른 컴퓨터에서 그대로 설치된다는 보장은 없다. 가상환경은 실행 경로와 운영체제에 종속될 수 있으므로 새로 만들고 환경에 맞게 설치한다. 보정값은 해당 로봇에서만 사용하고, 실제 구동 전 포트와 카메라 및 관절을 확인한다.

# SO-101 · LeRobot 실습

SO-101 Leader와 Follower, TOP·SIDE 카메라를 사용해 종이컵 Pick & Place 시연을 수집하고 ACT 모델을 학습·추론하는 Windows 실습입니다.

## 준비 환경

- Windows 64비트, Python 3.12와 Python Launcher
- NVIDIA GPU와 정상 동작하는 드라이버. 현재 학습·추론 코드는 CUDA 사용
- SO-101 Leader·Follower, RealSense D405 TOP 카메라, SIDE 웹캠
- 패키지 설치를 위한 인터넷 연결과 데이터 저장 공간

## 가상환경 설치

이 폴더를 새 컴퓨터에 복사한 뒤 PowerShell에서 프로젝트 폴더로 이동합니다. 기존 PC의 `lerobot` 가상환경 폴더는 옮기지 않습니다. 이미 복사했다면 백업하거나 이름을 바꾼 후 설치합니다.

```powershell
cd D:\lerobot
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

스크립트는 `lerobot` 가상환경을 만들고 LeRobot 0.6.1, Feetech·학습·시각화 패키지, RealSense와 CUDA용 PyTorch를 설치합니다. 기존 `lerobot` 폴더가 있으면 내용을 건드리지 않고 중단합니다. 설치 도중 실패하면 오류 내용을 확인하고 생성된 가상환경을 정리한 뒤 다시 실행합니다.

가상환경 활성화:

```powershell
.\lerobot\Scripts\Activate.ps1
```

활성화가 실행 정책에 막히면 현재 PowerShell 창에서만 다음 명령을 실행한 뒤 다시 활성화합니다.

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\lerobot\Scripts\Activate.ps1
```

설치 마지막에 `GPU 사용 가능: True`가 표시되는지 확인합니다. False라면 NVIDIA 드라이버와 GPU 환경을 확인합니다. CPU만 있는 PC에서는 현재 학습·추론 코드를 사용할 수 없습니다.

## 장비 설정

`scripts\settings.py`에서 사용 중인 PC의 Leader·Follower COM 포트, RealSense 시리얼 번호, SIDE 웹캠 번호를 수정합니다. 캘리브레이션은 사용하는 로봇에 맞게 진행하고 `datasets\calibration\leader.json`과 `follower.json`을 확인합니다. 다른 로봇이라면 수집 코드와 추론 코드의 홈 자세 기준도 확인합니다.

```powershell
python scripts\camera_test.py
python scripts\teleoperate.py
```

## 실습 순서

1. `python scripts\collection\run_gui.py`로 데이터셋을 생성하고 시연을 수집합니다.
2. `scripts\paper_cup_training\train.py`의 데이터셋 경로와 학습 설정을 확인한 뒤 다음 명령으로 학습합니다.

   ```powershell
   python scripts\paper_cup_training\train.py
   ```

3. `outputs`의 학습 결과와 `best.json`을 확인합니다. 추론할 학습 결과 폴더가 다르면 `scripts\paper_cup_inference\run_inference.py`의 `TRAINING_DIR`을 수정합니다.
4. 학습에 사용한 데이터셋을 `datasets` 안에 함께 둡니다. 현재 추론 코드는 모델에 저장된 데이터셋 이름으로 메타데이터와 작업 설명을 읽습니다.
5. 로봇 연결 전 모델과 환경을 확인합니다.

   ```powershell
   python scripts\paper_cup_inference\run_inference.py --preflight-only
   ```

6. 로봇·카메라와 작업 공간을 확인하고 추론합니다.

   ```powershell
   python scripts\paper_cup_inference\run_inference.py
   ```

추론 화면에서 SPACE는 시작·재개, P는 일시정지, Q 또는 Esc는 종료, E는 긴급 토크 해제입니다. 토크가 해제되면 팔이 내려갈 수 있습니다. 화면에 초점을 두고 조작하며 장비 전원도 바로 끌 수 있도록 준비합니다.

## 폴더 구성

| 폴더 | 내용 |
| --- | --- |
| `scripts` | 카메라 확인, 수집, 학습, 추론 코드와 장비 설정 |
| `datasets` | 캘리브레이션과 수집 데이터셋 |
| `models` | 학습별 체크포인트와 `best_model` |
| `outputs` | 학습 설정, 검증 손실, 그래프와 모델 선택 기록 |
| `docs` | 실습 참고 자료와 수집 이력 |
| `lerobot` | 이 PC에서 생성한 가상환경 |

모델을 옮길 때는 `best_model`의 가중치뿐 아니라 설정과 전처리·후처리 파일을 함께 복사합니다. 같은 로봇과 카메라를 사용하더라도 포트 번호와 작업 배치를 확인해야 합니다.

# LeRobot Windows 개발환경 정리

> 초기 설치 당시의 환경 기록이다. 이후 ACT 학습과 실제 실행이 진행됐으며 현재 상태는 [루트 README](../README.md)와 [학습 보고서](doll_pickplace_act_testreport/01_model_training.md)를 기준으로 본다. 현재 D405 검사는 `scripts/camera_test.py`를 사용한다.

이 문서는 `D:\lerobot-2026` 폴더가 무엇인지, 어떤 프로그램이 설치됐는지, Pick & Place 데이터가 실제로 열렸는지를 짧게 정리한 기록입니다.

처음 볼 때는 아래 세 군데만 보면 됩니다.

- `notes/environment.md`: 지금 읽고 있는 설명 문서입니다.
- `notes/so101_run_commands.md`: SO-101 실행 전 주의사항과 복구 명령어입니다.
- `notes/sample_frames/`: Pick & Place 데이터셋에서 실제로 뽑은 카메라 이미지입니다.
- `scripts/verify_environment.py`: 환경이 아직 정상인지 다시 검사하는 스크립트입니다.

나머지 폴더는 대부분 사람이 직접 보는 곳이 아니라 프로그램이 쓰는 곳입니다.

## 폴더별 의미

- `.venv`: Python 가상환경입니다. 설치된 Python 패키지가 들어 있습니다. 직접 수정하지 않습니다.
- `hf_pickplace_reference`: Hugging Face에서 받은 공개 Pick & Place 참조 데이터와 관련 캐시가 저장되는 폴더입니다. 자체 수집 데이터와 구분해 관리합니다.
- `robot_calibration`: 이 PC의 SO-101 Leader/Follower 보정값입니다. Hugging Face 캐시와 분리되어 있으며 삭제하거나 다른 로봇의 값으로 덮어쓰면 안 됩니다.
- `experiments`: 나중에 ACT 학습을 시작하면 결과, 로그, 체크포인트를 넣을 예정인 폴더입니다. 지금은 비어 있어도 정상입니다.
- `lerobot`: Hugging Face 공식 LeRobot 코드입니다. 로봇 학습/데이터 로딩 엔진이라고 보면 됩니다.
- `notes`: 사람이 보는 기록 폴더입니다. 지금은 환경 기록과 샘플 이미지가 들어 있습니다.
- `scripts`: 사람이 반복 실행할 수 있는 검사/도구 스크립트가 들어갑니다.
- `.gitignore`: GitHub에 올리지 않을 폴더와 파일 목록입니다.

## 한 줄 요약

Windows PC에서 LeRobot을 설치했고, RTX 3080 GPU가 PyTorch에서 잡혔고, 공개 Pick & Place 데이터셋 `lerobot/svla_so101_pickplace`의 실제 이미지 프레임을 읽는 데 성공했습니다.

## Project

- 목표: Hugging Face LeRobot 기반 SO-101 ACT 개발환경 1차 검증
- 작업 폴더: `D:\lerobot-2026`
- Git 브랜치: `dev`
- GitHub 원격 저장소: `https://github.com/hazyala/LeRobot-S101-ACT-2026.git`
- ACT 학습: 아직 하지 않음
- SO-101 실제 로봇 연결: Follower `COM3` 모터 스캔 성공
- Leader 포트 기록: `COM4`
- SmolVLA / Isaac / GR00T 관련 패키지: 설치하지 않음

## System

- Windows 버전: `Windows-11-10.0.26200-SP0`
- GPU: `NVIDIA GeForce RTX 3080`
- VRAM: `10240 MiB`
- NVIDIA driver: `595.95`
- CUDA Toolkit / `nvcc`: 일부러 설치하지 않음

설명: PyTorch CUDA 버전은 자체 CUDA runtime을 포함하므로, 지금 단계에서는 별도 CUDA Toolkit이나 `nvcc`가 필요하지 않습니다.

## Python / uv

- uv: `uv 0.10.8 (c021be36a 2026-03-03)`
- Python 실행 파일: `D:\lerobot-2026\.venv\Scripts\python.exe`
- Python 버전: `3.12.13`
- 가상환경 위치: `D:\lerobot-2026\.venv`
- venv pip: `D:\lerobot-2026\.venv\Lib\site-packages\pip`
- Conda base 자동 활성화: 꺼짐

설명: 앞으로 이 프로젝트에서 Python을 실행할 때는 Windows 기본 Python이 아니라 위 `.venv` 안의 Python을 써야 합니다.

주의: `pip install ...` 단독 실행은 Anaconda base 쪽에 설치될 수 있습니다. 이 프로젝트에서는 `uv` 또는 `.venv`의 `python -m pip`를 사용합니다.

## PyTorch / CUDA

- PyTorch: `2.11.0+cu130`
- PyTorch CUDA runtime: `13.0`
- `torch.cuda.is_available()`: `True`
- CUDA 장치: `NVIDIA GeForce RTX 3080`

설명: `torch.cuda.is_available()`가 `True`라는 뜻은 PyTorch가 RTX 3080을 GPU 연산용으로 사용할 수 있다는 뜻입니다.

## FFmpeg / TorchCodec

- FFmpeg package: `BtbN.FFmpeg.GPL.Shared.7.1`
- FFmpeg 실행/DLL 폴더:
  `C:\Users\AISW-509-IP\AppData\Local\Microsoft\WinGet\Packages\BtbN.FFmpeg.GPL.Shared.7.1_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-n7.1.5-12-g1fdbca85aa-win64-gpl-shared-7.1\bin`
- FFmpeg 버전:
  `ffmpeg version n7.1.5-12-g1fdbca85aa-20260731`
- FFprobe 버전:
  `ffprobe version n7.1.5-12-g1fdbca85aa-20260731`
- Shared 빌드 확인: `--enable-shared --disable-static`
- `bin` 폴더에서 DLL 확인: `avcodec-61.dll`, `avformat-61.dll`, `avutil-59.dll`
- Windows 사용자 PATH에 FFmpeg DLL 폴더 추가됨
- TorchCodec: `0.11.1+cpu`
- TorchCodec import 확인:
  `python -c "import torchcodec; print(torchcodec.__version__)"` 성공

설명: LeRobot 데이터셋의 카메라 영상은 압축된 비디오 형태입니다. TorchCodec과 FFmpeg는 그 영상을 Python Tensor 이미지로 읽기 위한 도구입니다.

참고: Windows Python 3.12에서는 PATH만으로 FFmpeg DLL을 못 찾는 경우가 있습니다. 그래서 `scripts/verify_environment.py`는 `os.add_dll_directory(...)`로 FFmpeg DLL 위치를 Python에 직접 알려줍니다.

## LeRobot

- 공식 코드: `https://github.com/huggingface/lerobot`
- 설치 방식: 소스 코드를 받아 editable mode로 설치
- Release tag: `v0.6.1`
- Commit: `7e241bd630a3719a56157a497ce5d08f244784f1`
- 설치한 extras: `training`, `core_scripts`, `feetech`
- `import lerobot`: 성공
- `lerobot-train --help`: 성공
- `lerobot-record --help`: 성공

설명: `lerobot` 폴더는 LeRobot 공식 소스 코드입니다. 지금은 학습을 시작하지 않았고, 설치와 명령어 실행 가능 여부만 확인했습니다.

## Feetech / SO-101 연결 확인

- `feetech-servo-sdk`: `1.0.0`
- `pyserial`: `3.5`
- SDK import 경로:
  `D:\lerobot-2026\.venv\Lib\site-packages\scservo_sdk\__init__.py`
- Follower 포트: `COM3`
- Follower 스캔 결과: `{1000000: [1, 2, 3, 4, 5]}`
- Leader 포트 기록: `COM4`

확인 명령:

```powershell
cd D:\lerobot-2026
.\.venv\Scripts\Activate.ps1
cd .\lerobot
python -c "import scservo_sdk; print(scservo_sdk.__file__)"
python -c "from lerobot.motors.feetech import FeetechMotorsBus; print(FeetechMotorsBus.scan_port('COM3'))"
```

설명: `scservo_sdk` import와 `COM3` 스캔이 모두 성공했으므로, 이전의 `feetech-servo-sdk is required but not installed` 문제는 Python 환경 분리 문제였습니다.

## Hugging Face Cache

- `HF_HOME`: `D:\lerobot-2026\hf_pickplace_reference`
- 검증할 때 현재 세션에 설정함
- Windows 사용자 환경변수로도 저장함
- 실제 데이터셋 캐시 위치:
  `D:\lerobot-2026\hf_pickplace_reference\lerobot\hub\datasets--lerobot--svla_so101_pickplace`

설명: `HF_HOME`은 Hugging Face가 데이터를 어디에 저장할지 정하는 환경변수입니다. 이번 프로젝트에서는 공개 Pick & Place 참조 데이터와 캐시가 `D:\lerobot-2026\hf_pickplace_reference` 아래로 들어가게 했습니다.

주의: Windows 개발자 모드/관리자 symlink 권한이 꺼져 있어서 Hugging Face 캐시가 공간을 더 쓸 수 있다는 경고가 있었습니다. 다운로드와 로딩은 성공했습니다.

## Dataset Verification

- 데이터셋: `lerobot/svla_so101_pickplace`
- 로딩 코드: `LeRobotDataset("lerobot/svla_so101_pickplace")`
- 로딩 결과: 성공
- 전체 프레임 수: `11939`
- FPS: `30`
- Episode 수: `50`
- 카메라 key:
  - `observation.images.up`
  - `observation.images.side`
- 이미지 해상도: `640x480`
- 이미지 Tensor 모양: `[3, 480, 640]`
- 이미지 dtype: `torch.float32`
- 이미지 값 범위:
  - sample `0`, up: `0.0` to `0.8666666746139526`
  - sample `0`, side: `0.0` to `0.929411768913269`
  - sample `5969`, up: `0.0` to `0.8901960849761963`
  - sample `5969`, side: `0.019607843831181526` to `0.9647058844566345`
- State 차원: `6`
- Action 차원: `6`
- State/action 이름:
  - `shoulder_pan.pos`
  - `shoulder_lift.pos`
  - `elbow_flex.pos`
  - `wrist_flex.pos`
  - `wrist_roll.pos`
  - `gripper.pos`

설명:

- `observation.images.up`: 위쪽 카메라 이미지입니다.
- `observation.images.side`: 옆쪽 카메라 이미지입니다.
- `observation.state`: 그 순간 로봇팔 관절 위치 상태입니다.
- `action`: 그 다음에 로봇팔이 취해야 할 관절 명령입니다.
- `FPS 30`: 1초에 30프레임짜리 데이터라는 뜻입니다.
- `Episode 50`: Pick & Place 시도 영상/동작 묶음이 50개 있다는 뜻입니다.

## 저장된 샘플 이미지

- `D:\lerobot-2026\notes\sample_frames\sample_0_observation_images_up.png`
- `D:\lerobot-2026\notes\sample_frames\sample_0_observation_images_side.png`
- `D:\lerobot-2026\notes\sample_frames\sample_5969_observation_images_up.png`
- `D:\lerobot-2026\notes\sample_frames\sample_5969_observation_images_side.png`

설명: 위 PNG 파일 4개는 실제 데이터셋에서 뽑은 이미지입니다. 데이터가 제대로 열리는지 눈으로 확인할 때는 이 파일들을 보면 됩니다.

## RealSense D405 탑뷰 카메라

- 목적: SO-101 Pick & Place 작업대를 위에서 내려다보는 탑뷰 카메라로 사용
- Python SDK 패키지: `pyrealsense2==2.58.4`
- 확인된 장치: `RealSense D405`
- Serial number: `352122273503`
- Firmware: `5.15.1.55`
- USB: `3.2`
- 테스트 스크립트: `D:\lerobot-2026\scripts\camera_test.py`
- 저장된 컬러 이미지:
  `D:\lerobot-2026\notes\realsense_D405_test\d405_top_color.png`
- 저장된 Depth 원본 이미지:
  `D:\lerobot-2026\notes\realsense_D405_test\d405_top_depth_raw.png`
- 저장된 Depth 확인용 컬러맵:
  `D:\lerobot-2026\notes\realsense_D405_test\d405_top_depth_colormap.png`

설명:

- `pyrealsense2`는 Python에서 RealSense 카메라를 제어하게 해주는 SDK 바인딩입니다.
- `color` 이미지는 일반 카메라 화면입니다.
- `depth raw` 이미지는 거리값이 들어 있는 16-bit 이미지입니다.
- `depth colormap` 이미지는 사람이 보기 쉽게 depth를 색으로 바꾼 이미지입니다.
- 현재 테스트 이미지는 카메라가 천장/모니터 쪽을 보고 있는 상태에서 저장됐습니다. 실제 탑뷰 데이터 수집 전에는 카메라를 작업대 위에서 아래로 향하게 고정해야 합니다.

다시 테스트하려면:

```powershell
cd D:\lerobot-2026
.\.venv\Scripts\python.exe .\scripts\camera_test.py
```

현재 camera_test.py는 기본적으로 미리보기 창을 연다. 옵션은 코드의 argparse 정의를 확인한다:

```powershell
cd D:\lerobot-2026
.\.venv\Scripts\python.exe .\scripts\camera_test.py --help
```

## 발생한 문제와 해결

- 2026-09-08에 PowerShell 프롬프트가 `(base) (lerobot-2026)`처럼 겹쳐 보였고, `python`은 `D:\lerobot-2026\.venv\Scripts\python.exe`를 가리켰지만 그 venv에는 pip가 없었습니다. 반면 `pip install "lerobot[feetech]"`는 Anaconda base인 `C:\Users\AISW-509-IP\anaconda3\Lib\site-packages`에 설치되고 있었습니다. `ensurepip`로 venv의 pip를 복구한 뒤, `uv pip install --python D:\lerobot-2026\.venv\Scripts\python.exe -e "D:\lerobot-2026\lerobot[feetech]"`로 `feetech-servo-sdk`를 venv에 설치해서 해결했습니다.
- Conda base가 새 PowerShell에서 자동으로 켜지지 않도록 `auto_activate_base`를 꺼두었습니다.
- 처음 PyTorch 설치 때 `torch==2.14.0+cu130`이 설치됐습니다. 하지만 LeRobot `v0.6.1`은 `torch>=2.7,<2.12.0` 범위를 요구해서 맞지 않았습니다. 그래서 `torch==2.11.0+cu130`, `torchvision==0.26.0+cu130`, `torchaudio==2.11.0+cu130`으로 다시 설치했습니다.
- LeRobot 설치 중 `uv`가 PyTorch index 쪽의 오래된 `requests` 패키지를 먼저 보고 의존성 해결에 실패했습니다. PyPI와 PyTorch CUDA index를 함께 보도록 `--index-strategy unsafe-best-match` 옵션을 써서 해결했습니다.
- `lerobot-train --help` 실행 때 TorchCodec native loader 경고가 날 수 있습니다. Windows에서 FFmpeg DLL 경로를 Python 프로세스에 직접 등록하지 않아서 생기는 문제입니다. `scripts/verify_environment.py`에서는 `os.add_dll_directory(...)`로 해결했습니다.
- 데이터셋 포맷 변환은 필요하지 않았습니다. 현재 LeRobot `v0.6.1`에서 `lerobot/svla_so101_pickplace`가 바로 열렸습니다.
- RealSense SDK는 winget에서 별도 패키지를 찾지 못했습니다. 대신 가상환경에 `pyrealsense2`를 설치했고, 실제 D405 color/depth stream 수신에 성공했습니다.

## 다시 검사하는 방법

환경이 아직 정상인지 다시 확인하고 싶으면 PowerShell에서 아래 명령을 실행합니다.

```powershell
cd D:\lerobot-2026
$env:HF_HOME = "D:\lerobot-2026\hf_pickplace_reference"
.\.venv\Scripts\python.exe .\scripts\verify_environment.py
```

성공하면 마지막에 JSON 형태로 결과가 출력되고, `notes/sample_frames`에 샘플 이미지가 다시 저장됩니다.

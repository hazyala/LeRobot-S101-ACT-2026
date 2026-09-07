# LeRobot Windows Development Environment

## Project

- Goal: Hugging Face LeRobot 기반 SO-101 ACT 개발환경 1차 검증
- Workspace: `D:\lerobot-2026`
- Git branch: `dev`
- Remote: `https://github.com/hazyala/LeRobot-S101-ACT-2026.git`
- ACT training: not run
- SO-101 hardware connection: not run
- SmolVLA / Isaac / GR00T dependencies: not installed

## System

- Windows version: `Windows-11-10.0.26200-SP0`
- GPU: `NVIDIA GeForce RTX 3080`
- VRAM: `10240 MiB`
- NVIDIA driver: `595.95`
- CUDA Toolkit / `nvcc`: not installed intentionally

## Python / uv

- uv: `uv 0.10.8 (c021be36a 2026-03-03)`
- Python executable: `D:\lerobot-2026\.venv\Scripts\python.exe`
- Python version: `3.12.13`
- Virtual environment: `D:\lerobot-2026\.venv`

## PyTorch / CUDA

- PyTorch: `2.11.0+cu130`
- PyTorch CUDA runtime: `13.0`
- `torch.cuda.is_available()`: `True`
- CUDA device: `NVIDIA GeForce RTX 3080`

## FFmpeg / TorchCodec

- FFmpeg package: `BtbN.FFmpeg.GPL.Shared.7.1`
- FFmpeg binary directory:
  `C:\Users\AISW-509-IP\AppData\Local\Microsoft\WinGet\Packages\BtbN.FFmpeg.GPL.Shared.7.1_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-n7.1.5-12-g1fdbca85aa-win64-gpl-shared-7.1\bin`
- FFmpeg version:
  `ffmpeg version n7.1.5-12-g1fdbca85aa-20260731`
- FFprobe version:
  `ffprobe version n7.1.5-12-g1fdbca85aa-20260731`
- Shared build confirmed: `--enable-shared --disable-static`
- DLLs confirmed in `bin`: `avcodec-61.dll`, `avformat-61.dll`, `avutil-59.dll`
- User PATH contains FFmpeg DLL directory.
- TorchCodec: `0.11.1+cpu`
- TorchCodec import check:
  `python -c "import torchcodec; print(torchcodec.__version__)"` succeeded.

Note: On Windows Python 3.12, PATH alone may not be enough for dependent DLL lookup inside a running Python process. The verification script adds the FFmpeg DLL directory with `os.add_dll_directory(...)` before importing the LeRobot dataset/video stack.

## LeRobot

- Source: `https://github.com/huggingface/lerobot`
- Installed from source in editable mode
- Release tag: `v0.6.1`
- Commit: `7e241bd630a3719a56157a497ce5d08f244784f1`
- Installed extras: `training`, `core_scripts`
- `import lerobot`: succeeded
- `lerobot-train --help`: succeeded
- `lerobot-record --help`: succeeded

## Hugging Face Cache

- `HF_HOME`: `D:\lerobot-2026\datasets`
- Set for current session during verification.
- Persisted as a Windows user environment variable.
- Actual LeRobot/HF cache observed under:
  `D:\lerobot-2026\datasets\lerobot\hub\datasets--lerobot--svla_so101_pickplace`

Warning observed: Hugging Face Hub symlink cache is degraded on this Windows machine because Developer Mode/admin symlink support is not enabled. Download still succeeded, but cache may use more disk space.

## Dataset Verification

- Dataset: `lerobot/svla_so101_pickplace`
- Load API: `LeRobotDataset("lerobot/svla_so101_pickplace")`
- Loading result: succeeded
- Dataset length: `11939`
- FPS: `30`
- Episodes: `50`
- Camera keys:
  - `observation.images.up`
  - `observation.images.side`
- Image resolution: `640x480`
- Image tensor shape: `[3, 480, 640]`
- Image dtype: `torch.float32`
- Image value range:
  - sample `0`, up: `0.0` to `0.8666666746139526`
  - sample `0`, side: `0.0` to `0.929411768913269`
  - sample `5969`, up: `0.0` to `0.8901960849761963`
  - sample `5969`, side: `0.019607843831181526` to `0.9647058844566345`
- State dimension: `6`
- Action dimension: `6`
- State/action names:
  - `shoulder_pan.pos`
  - `shoulder_lift.pos`
  - `elbow_flex.pos`
  - `wrist_flex.pos`
  - `wrist_roll.pos`
  - `gripper.pos`

## Saved Sample Frames

- `D:\lerobot-2026\notes\sample_frames\sample_0_observation_images_up.png`
- `D:\lerobot-2026\notes\sample_frames\sample_0_observation_images_side.png`
- `D:\lerobot-2026\notes\sample_frames\sample_5969_observation_images_up.png`
- `D:\lerobot-2026\notes\sample_frames\sample_5969_observation_images_side.png`

## Issues And Fixes

- Initial `torch` install selected `torch==2.14.0+cu130`, which is outside LeRobot `v0.6.1`'s supported range of `torch>=2.7,<2.12.0`. Fixed by reinstalling `torch==2.11.0+cu130`, `torchvision==0.26.0+cu130`, and `torchaudio==2.11.0+cu130`.
- `uv` dependency resolution initially considered the PyTorch index copy of `requests` first and failed to resolve LeRobot. Fixed by using `--index-strategy unsafe-best-match` with PyPI and the PyTorch CUDA index.
- `lerobot-train --help` can emit a TorchCodec native-loader warning if the Python process has not registered the FFmpeg DLL directory. The dataset verification script fixes this with `os.add_dll_directory(...)`.
- No dataset format conversion was required. Current LeRobot `v0.6.1` loaded `lerobot/svla_so101_pickplace` successfully.

## Re-run Verification

```powershell
cd D:\lerobot-2026
$env:HF_HOME = "D:\lerobot-2026\datasets"
.\.venv\Scripts\python.exe .\scripts\verify_environment.py
```

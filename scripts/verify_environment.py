from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

from PIL import Image


# 이 스크립트는 "환경이 제대로 만들어졌는지" 다시 확인하는 검사 파일입니다.
# 학습은 하지 않고, 설치된 도구와 Pick & Place 데이터셋 로딩만 확인합니다.

# 프로젝트 최상위 폴더: D:\lerobot-2026
ROOT = Path(__file__).resolve().parents[1]

# TorchCodec이 영상 데이터를 읽으려면 FFmpeg의 DLL 파일 위치를 알아야 합니다.
# Windows에서는 PATH만으로 부족한 경우가 있어서 아래 경로를 Python에 직접 알려줍니다.
FFMPEG_BIN = Path(
    r"C:\Users\AISW-509-IP\AppData\Local\Microsoft\WinGet\Packages"
    r"\BtbN.FFmpeg.GPL.Shared.7.1_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\ffmpeg-n7.1.5-12-g1fdbca85aa-win64-gpl-shared-7.1\bin"
)

# 이번에 확인하는 공개 LeRobot Pick & Place 데이터셋입니다.
DATASET_REPO_ID = "lerobot/svla_so101_pickplace"

# 데이터셋에서 실제 카메라 이미지를 뽑아 PNG로 저장할 폴더입니다.
FRAME_DIR = ROOT / "notes" / "sample_frames"


def run(command: list[str]) -> str:
    """외부 명령어를 실행하고 출력 문자열을 돌려줍니다. 예: ffmpeg -version"""
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def shape_of(value: Any) -> list[int] | str:
    """Tensor나 배열이면 shape를, 아니면 타입 이름을 사람이 읽기 좋게 돌려줍니다."""
    shape = getattr(value, "shape", None)
    if shape is not None:
        return [int(dim) for dim in shape]
    return type(value).__name__


def tensor_stats(value: Any) -> dict[str, Any]:
    """Tensor의 모양, 자료형, 최소값, 최대값을 기록합니다."""
    return {
        "type": type(value).__name__,
        "shape": shape_of(value),
        "dtype": str(getattr(value, "dtype", type(value))),
        "min": float(value.min().item()) if hasattr(value, "min") else None,
        "max": float(value.max().item()) if hasattr(value, "max") else None,
    }


def save_image_tensor(value: Any, path: Path) -> dict[str, Any]:
    """LeRobot 이미지 Tensor를 일반 PNG 이미지 파일로 저장합니다."""
    import torch

    # GPU Tensor일 수도 있으므로 CPU로 옮긴 뒤 저장합니다.
    tensor = value.detach().cpu() if isinstance(value, torch.Tensor) else torch.as_tensor(value)
    stats = tensor_stats(tensor)

    # LeRobot 이미지는 보통 [채널, 높이, 너비] 형태입니다.
    # PNG 저장을 위해 [높이, 너비, 채널] 형태로 바꿉니다.
    if tensor.ndim == 3 and tensor.shape[0] in (1, 3, 4):
        tensor = tensor.permute(1, 2, 0)

    # float 이미지는 0~1 범위라서 PNG용 0~255 정수로 변환합니다.
    if tensor.dtype.is_floating_point:
        image = tensor.clamp(0, 1).mul(255).to(torch.uint8).numpy()
    else:
        image = tensor.clamp(0, 255).to(torch.uint8).numpy()

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image).save(path)
    stats["saved_png"] = str(path)
    stats["image_size"] = list(Image.open(path).size)
    return stats


def main() -> None:
    # Hugging Face가 데이터를 다운로드/캐시할 위치를 프로젝트 안의 datasets로 고정합니다.
    os.environ["HF_HOME"] = str(ROOT / "datasets")

    # 현재 실행 중인 PowerShell 세션에서도 FFmpeg를 찾을 수 있게 PATH 앞에 추가합니다.
    os.environ["PATH"] = f"{FFMPEG_BIN};{os.environ.get('PATH', '')}"

    # Windows Python 3.12에서 DLL 검색을 확실하게 하기 위한 처리입니다.
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(FFMPEG_BIN))

    # 여기서부터 실제 설치된 패키지를 import해서 문제가 없는지 확인합니다.
    import torch
    import torchcodec
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    # FFmpeg / FFprobe가 실행되는지 확인합니다.
    ffmpeg_version = run(["ffmpeg", "-version"]).splitlines()[0]
    ffprobe_version = run(["ffprobe", "-version"]).splitlines()[0]

    # LeRobotDataset이 공개 Pick & Place 데이터를 실제로 읽을 수 있는지 확인합니다.
    dataset = LeRobotDataset(DATASET_REPO_ID)

    # 맨 앞 샘플과 중간 샘플을 둘 다 봅니다. 하나만 보면 우연히 통과할 수 있어서입니다.
    indices = [0, len(dataset) // 2]
    sample_reports: dict[str, Any] = {}

    for index in indices:
        # dataset[index]가 실제 한 프레임 묶음입니다.
        # 이미지, 로봇 상태, 로봇 행동(action)이 같이 들어 있습니다.
        sample = dataset[index]
        key = f"sample_{index}"
        sample_reports[key] = {
            "keys": {name: shape_of(value) for name, value in sample.items()},
            "observation.state": tensor_stats(sample["observation.state"]),
            "action": tensor_stats(sample["action"]),
        }

        # 위쪽 카메라와 옆쪽 카메라 이미지를 PNG로 저장합니다.
        for camera_key in ["observation.images.up", "observation.images.side"]:
            png_path = FRAME_DIR / f"{key}_{camera_key.replace('.', '_')}.png"
            sample_reports[key][camera_key] = save_image_tensor(sample[camera_key], png_path)

    # 데이터셋 전체 구조 정보입니다. FPS, episode 수, 각 항목의 shape 등이 들어 있습니다.
    metadata = {
        "repo_id": DATASET_REPO_ID,
        "length": len(dataset),
        "fps": getattr(dataset.meta, "fps", None),
        "episodes": getattr(dataset.meta, "total_episodes", None),
        "features": getattr(dataset.meta, "features", None),
    }

    # 최종 검사 결과를 JSON 형태로 출력합니다.
    # notes/environment.md는 이 출력값을 사람이 읽기 쉽게 정리한 문서입니다.
    result = {
        "windows": platform.platform(),
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "hf_home": os.environ["HF_HOME"],
        "ffmpeg_bin": str(FFMPEG_BIN),
        "ffmpeg_version": ffmpeg_version,
        "ffprobe_version": ffprobe_version,
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "torch_cuda_available": torch.cuda.is_available(),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "torchcodec_version": torchcodec.__version__,
        "dataset": metadata,
        "samples": sample_reports,
    }

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()

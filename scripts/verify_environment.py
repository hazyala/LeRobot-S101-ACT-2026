from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
FFMPEG_BIN = Path(
    r"C:\Users\AISW-509-IP\AppData\Local\Microsoft\WinGet\Packages"
    r"\BtbN.FFmpeg.GPL.Shared.7.1_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\ffmpeg-n7.1.5-12-g1fdbca85aa-win64-gpl-shared-7.1\bin"
)
DATASET_REPO_ID = "lerobot/svla_so101_pickplace"
FRAME_DIR = ROOT / "notes" / "sample_frames"


def run(command: list[str]) -> str:
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def shape_of(value: Any) -> list[int] | str:
    shape = getattr(value, "shape", None)
    if shape is not None:
        return [int(dim) for dim in shape]
    return type(value).__name__


def tensor_stats(value: Any) -> dict[str, Any]:
    return {
        "type": type(value).__name__,
        "shape": shape_of(value),
        "dtype": str(getattr(value, "dtype", type(value))),
        "min": float(value.min().item()) if hasattr(value, "min") else None,
        "max": float(value.max().item()) if hasattr(value, "max") else None,
    }


def save_image_tensor(value: Any, path: Path) -> dict[str, Any]:
    import torch

    tensor = value.detach().cpu() if isinstance(value, torch.Tensor) else torch.as_tensor(value)
    stats = tensor_stats(tensor)

    if tensor.ndim == 3 and tensor.shape[0] in (1, 3, 4):
        tensor = tensor.permute(1, 2, 0)

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
    os.environ["HF_HOME"] = str(ROOT / "datasets")
    os.environ["PATH"] = f"{FFMPEG_BIN};{os.environ.get('PATH', '')}"

    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(FFMPEG_BIN))

    import torch
    import torchcodec
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    ffmpeg_version = run(["ffmpeg", "-version"]).splitlines()[0]
    ffprobe_version = run(["ffprobe", "-version"]).splitlines()[0]

    dataset = LeRobotDataset(DATASET_REPO_ID)
    indices = [0, len(dataset) // 2]
    sample_reports: dict[str, Any] = {}

    for index in indices:
        sample = dataset[index]
        key = f"sample_{index}"
        sample_reports[key] = {
            "keys": {name: shape_of(value) for name, value in sample.items()},
            "observation.state": tensor_stats(sample["observation.state"]),
            "action": tensor_stats(sample["action"]),
        }

        for camera_key in ["observation.images.up", "observation.images.side"]:
            png_path = FRAME_DIR / f"{key}_{camera_key.replace('.', '_')}.png"
            sample_reports[key][camera_key] = save_image_tensor(sample[camera_key], png_path)

    metadata = {
        "repo_id": DATASET_REPO_ID,
        "length": len(dataset),
        "fps": getattr(dataset.meta, "fps", None),
        "episodes": getattr(dataset.meta, "total_episodes", None),
        "features": getattr(dataset.meta, "features", None),
    }

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

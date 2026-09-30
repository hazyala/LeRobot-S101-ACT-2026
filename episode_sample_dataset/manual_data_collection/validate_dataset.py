from __future__ import annotations

from pathlib import Path

import torch
from PIL import Image, ImageDraw

from lerobot.datasets.lerobot_dataset import LeRobotDataset


SCRIPT_DIR = Path(__file__).resolve().parent
DATASET_ROOT = SCRIPT_DIR / "dataset"
OUTPUT_DIR = SCRIPT_DIR / "validation_frames"
REPO_ID = "hazyala/so101_pickplace_sample"


def tensor_to_image(value) -> Image.Image:
    tensor = value.detach().cpu()
    if tensor.ndim == 3 and tensor.shape[0] in (1, 3, 4):
        tensor = tensor.permute(1, 2, 0)
    array = tensor.clamp(0, 1).mul(255).to(torch.uint8).numpy()
    return Image.fromarray(array)


def main() -> None:
    dataset = LeRobotDataset(REPO_ID, root=DATASET_ROOT)
    print(f"episodes = {dataset.num_episodes}")
    print(f"frames   = {len(dataset)}")
    print(f"fps      = {dataset.fps}")
    print("features =")
    for key in dataset.features:
        print(f"  - {key}")

    OUTPUT_DIR.mkdir(exist_ok=True)
    rows = [dataset.meta.episodes[index] for index in range(dataset.num_episodes)]

    for episode in rows:
        episode_index = int(episode["episode_index"])
        start = int(episode["dataset_from_index"])
        end = int(episode["dataset_to_index"]) - 1
        middle = (start + end) // 2

        print(
            f"episode {episode_index}: "
            f"{episode['length']} frames, "
            f"{episode['length'] / dataset.fps:.1f}s"
        )

        for label, frame_index in [("start", start), ("middle", middle), ("end", end)]:
            sample = dataset[frame_index]
            top = tensor_to_image(sample["observation.images.top"])
            front = tensor_to_image(sample["observation.images.front"])

            canvas = Image.new("RGB", (top.width + front.width, max(top.height, front.height)))
            canvas.paste(top, (0, 0))
            canvas.paste(front, (top.width, 0))

            draw = ImageDraw.Draw(canvas)
            draw.text((10, 10), f"episode {episode_index} {label} top", fill=(255, 0, 0))
            draw.text((top.width + 10, 10), f"episode {episode_index} {label} front", fill=(255, 0, 0))

            output_path = OUTPUT_DIR / f"episode_{episode_index}_{label}.png"
            canvas.save(output_path)
            print(f"  saved {output_path}")


if __name__ == "__main__":
    main()

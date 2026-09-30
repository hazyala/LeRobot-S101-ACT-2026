from __future__ import annotations

import argparse
import os
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
DATASET_ROOT = PROJECT_ROOT / "episode_sample_dataset" / "auto_home_collection" / "auto_home_dataset"
REPO_ID = "hazyala/so101_pickplace_auto_home"
DEPTH_KEY = "observation.images.top_depth"

# Keep all caches inside this project instead of mixing them with user-level caches.
os.environ.setdefault("HF_HOME", str(PROJECT_ROOT / "hf_pickplace_reference"))
os.environ.setdefault("HF_LEROBOT_HOME", str(PROJECT_ROOT / "hf_pickplace_reference" / "lerobot"))

from lerobot.configs import FeatureType
from lerobot.configs.default import DatasetConfig, WandBConfig
from lerobot.configs.train import TrainPipelineConfig
from lerobot.datasets import LeRobotDatasetMetadata
from lerobot.policies.act import ACTConfig
from lerobot.scripts.lerobot_train import train
from lerobot.utils.feature_utils import dataset_to_policy_features


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train ACT on the local SO-101 doll pick-and-place dataset.")
    parser.add_argument("--steps", type=int, default=20_000)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--num-workers", type=int, default=2)
    parser.add_argument("--save-freq", type=int, default=2_000)
    parser.add_argument("--log-freq", type=int, default=20)
    parser.add_argument("--output-dir", type=Path, default=SCRIPT_DIR / "outputs" / "act_100ep_20k")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not DATASET_ROOT.is_dir():
        raise FileNotFoundError(f"Dataset not found: {DATASET_ROOT}")

    metadata = LeRobotDatasetMetadata(REPO_ID, root=DATASET_ROOT)
    if metadata.total_episodes != 100:
        raise RuntimeError(
            f"Expected the verified 100-episode dataset, found {metadata.total_episodes} episodes."
        )

    features = dataset_to_policy_features(metadata.features)
    output_features = {key: ft for key, ft in features.items() if ft.type is FeatureType.ACTION}
    input_features = {
        key: ft
        for key, ft in features.items()
        if key not in output_features and key != DEPTH_KEY
    }

    policy = ACTConfig(
        input_features=input_features,
        output_features=output_features,
        device="cuda",
        use_amp=True,
        push_to_hub=False,
        pretrained_backbone_weights="ResNet18_Weights.IMAGENET1K_V1",
    )
    dataset = DatasetConfig(
        repo_id=REPO_ID,
        root=str(DATASET_ROOT),
        return_uint8=True,
    )
    config = TrainPipelineConfig(
        dataset=dataset,
        policy=policy,
        output_dir=args.output_dir,
        job_name="doll_pickplace_act",
        steps=args.steps,
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        persistent_workers=args.num_workers > 0,
        log_freq=args.log_freq,
        save_checkpoint=True,
        save_freq=args.save_freq,
        wandb=WandBConfig(enable=False),
    )

    print(f"Dataset: {metadata.total_episodes} episodes, {metadata.total_frames} frames")
    print(f"ACT inputs: {', '.join(input_features)}")
    print(f"ACT output: {', '.join(output_features)}")
    print(f"Output: {args.output_dir}")
    train(config)


if __name__ == "__main__":
    main()

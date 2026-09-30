"""Check whether recorded grasp transitions are reproduced by the trained ACT policy."""

from pathlib import Path

import numpy as np
import torch

from lerobot.configs.train import TrainPipelineConfig
from lerobot.datasets.factory import make_dataset
from lerobot.policies import make_pre_post_processors
from lerobot.policies.act import ACTConfig, ACTPolicy  # noqa: F401 - registers ACT


ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT / "outputs" / "act_100ep_20k" / "checkpoints" / "020000" / "pretrained_model"
JOINTS = [
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
]
GRIP_THRESHOLD = 15.0
LOOKBACK = 60


def first_close_offset(actions: np.ndarray) -> int | None:
    hits = np.flatnonzero(actions[:, 5] >= GRIP_THRESHOLD)
    return int(hits[0]) if len(hits) else None


def main() -> None:
    config = TrainPipelineConfig.from_pretrained(MODEL_DIR)
    dataset = make_dataset(config)
    starts = np.asarray(dataset.meta.episodes["dataset_from_index"], dtype=int)
    ends = np.asarray(dataset.meta.episodes["dataset_to_index"], dtype=int)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    policy = ACTPolicy.from_pretrained(MODEL_DIR).to(device).eval()
    preprocess, postprocess = make_pre_post_processors(
        policy.config, pretrained_path=str(MODEL_DIR)
    )

    chosen_eps = np.linspace(0, dataset.num_episodes - 1, 10, dtype=int)
    print("episode preframe | GT close/pred close | GT arm travel/pred arm travel | arm MAE")
    print("-" * 90)
    summaries = []
    with torch.inference_mode():
        for episode in chosen_eps:
            start, end = starts[episode], ends[episode]
            # Read only scalar actions first; this avoids decoding every video frame.
            episode_actions = np.stack(
                [dataset[i]["action"][0].cpu().numpy() for i in range(start, end)]
            )
            close_local = first_close_offset(episode_actions)
            if close_local is None:
                print(f"{episode:3d}: no recorded gripper closure")
                continue

            pre_local = max(0, close_local - LOOKBACK)
            sample = dataset[start + pre_local]
            model_sample = dict(sample)
            for camera_key in dataset.meta.camera_keys:
                value = model_sample.get(camera_key)
                if value is not None and value.dtype == torch.uint8:
                    model_sample[camera_key] = value.float() / 255.0
            predicted = postprocess(policy.predict_action_chunk(preprocess(model_sample)))[0].cpu().numpy()
            target = sample["action"].cpu().numpy()
            valid = ~sample["action_is_pad"].cpu().numpy()
            predicted, target = predicted[valid], target[valid]

            gt_close = first_close_offset(target)
            pred_close = first_close_offset(predicted)
            gt_arm_travel = np.abs(target[:, 1:4] - target[0, 1:4]).max(axis=0)
            pred_arm_travel = np.abs(predicted[:, 1:4] - predicted[0, 1:4]).max(axis=0)
            arm_mae = np.abs(predicted[:, 1:4] - target[:, 1:4]).mean()
            summaries.append((gt_close, pred_close, gt_arm_travel, pred_arm_travel, arm_mae))
            print(
                f"{episode:3d} {pre_local:8d} | "
                f"{str(gt_close):>7}/{str(pred_close):<10} | "
                f"{np.round(gt_arm_travel, 1)} / {np.round(pred_arm_travel, 1)} | {arm_mae:6.2f}"
            )

    predicted_close_count = sum(item[1] is not None for item in summaries)
    print("-" * 90)
    print(f"Recorded close transitions found: {len(summaries)}/{len(chosen_eps)}")
    print(f"Model predicted close within next 100 frames: {predicted_close_count}/{len(summaries)}")
    if summaries:
        print(f"Mean arm MAE around grasp approach: {np.mean([item[4] for item in summaries]):.2f} deg")


if __name__ == "__main__":
    main()

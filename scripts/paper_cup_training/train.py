"""SO-101 종이컵 시연 데이터로 로컬 ACT 학습."""
import argparse
import copy
from datetime import datetime
import importlib
import json
import os
from pathlib import Path
import random

# 로컬 실습 폴더의 캐시 사용
PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.environ["HF_DATASETS_CACHE"] = str(PROJECT_ROOT / ".cache" / "huggingface" / "datasets")

import numpy as np
import pyarrow.parquet as pq
import torch
from lerobot.configs import FeatureType, PolicyFeature
from lerobot.configs.default import DatasetConfig, WandBConfig
from lerobot.configs.train import TrainPipelineConfig
from lerobot.datasets.compute_stats import aggregate_stats
from lerobot.datasets.factory import make_dataset
from lerobot.policies.act import ACTConfig
from best_checkpoint import train_with_best


# 실습 데이터와 학습 설정
DATASET_DIR = PROJECT_ROOT / "datasets" / "paper_cup"  # 수집 데이터셋 폴더
TASK_NAME = DATASET_DIR.name
STEPS = 20000          # 전체 학습 단계
BATCH_SIZE = 8         # 한 번에 학습할 데이터 수. GPU 메모리 부족 시 4 또는 2로 변경
SAVE_EVERY = 1000      # 검증 및 체크포인트 저장 간격
LOG_EVERY = 100        # 학습 진행 표시 간격
SEED = 1000            # 에피소드 분할 및 학습 재현용


def split_episodes(root):
    info = json.loads((root / "meta" / "info.json").read_text(encoding="utf-8"))
    count = info["total_episodes"]
    if count < 2:
        raise ValueError("학습과 검증에 최소 2개 에피소드가 필요합니다.")
    ids = list(range(count))
    random.Random(SEED).shuffle(ids)
    validation_count = max(1, round(count * 0.2))
    return {"seed": SEED, "train": sorted(ids[validation_count:]),
            "validation": sorted(ids[:validation_count])}


def training_stats(root, train_ids):
    """검증 데이터가 섞이지 않도록 학습 에피소드 통계만 합산."""
    wanted, found, selected = set(train_ids), set(), []
    required = ("observation.state", "action", "observation.images.top", "observation.images.side")
    for path in sorted((root / "meta" / "episodes").rglob("*.parquet")):
        for row in pq.read_table(path).to_pylist():
            ep = int(row["episode_index"])
            if ep not in wanted:
                continue
            if ep in found:
                raise ValueError(f"중복 에피소드: {ep}")
            found.add(ep)
            stats = {}
            for key, value in row.items():
                if key.startswith("stats/") and value is not None:
                    feature, stat = key[6:].rsplit("/", 1)
                    stats.setdefault(feature, {})[stat] = np.atleast_1d(np.asarray(value))
            for key in required:
                if not {"mean", "std", "count"}.issubset(stats.get(key, {})):
                    raise ValueError(f"에피소드 {ep} 통계 누락: {key}")
            selected.append(stats)
    if found != wanted:
        raise ValueError("학습 에피소드 통계를 모두 찾지 못했습니다.")
    stats = aggregate_stats(selected)
    for feature, values in stats.items():
        if any(not np.isfinite(value).all() for value in values.values()):
            raise ValueError(f"비정상 통계: {feature}")
    return stats


def main():
    parser = argparse.ArgumentParser(description="종이컵 ACT 학습")
    parser.parse_args()
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU를 찾을 수 없습니다. PyTorch와 GPU 설정을 확인하세요.")
    if not (DATASET_DIR / "meta" / "info.json").is_file():
        raise FileNotFoundError(f"데이터셋을 찾을 수 없습니다: {DATASET_DIR}")

    split = split_episodes(DATASET_DIR)
    stats = training_stats(DATASET_DIR, split["train"])
    label = f"{TASK_NAME}_training"
    run_name = label
    models = PROJECT_ROOT / "models"
    records = PROJECT_ROOT / "outputs"
    if (models / run_name).exists() or (records / run_name).exists():
        run_name += f"_{datetime.now():%Y%m%d_%H%M%S_%f}"
    model_output = models / run_name
    record_output = records / run_name
    record_output.mkdir(parents=True, exist_ok=False)
    (record_output / "split.json").write_text(
        json.dumps(split, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"데이터셋: {DATASET_DIR}", flush=True)
    print(f"학습 {len(split['train'])}개 · 검증 {len(split['validation'])}개", flush=True)
    print(f"학습 단계 {STEPS:,} · 배치 {BATCH_SIZE}", flush=True)
    print(f"모델 저장: {model_output}", flush=True)
    print(f"학습 기록: {record_output}", flush=True)
    print(f"최고 모델: {model_output / 'best_model'}", flush=True)
    if len(split["train"]) + len(split["validation"]) < 50:
        print("참고: 현재 데이터는 학습 실행 확인용입니다. 충분한 시연을 추가해 주세요.", flush=True)

    policy = ACTConfig(
        input_features={
            "observation.state": PolicyFeature(FeatureType.STATE, (6,)),
            "observation.images.top": PolicyFeature(FeatureType.VISUAL, (3, 480, 640)),
            "observation.images.side": PolicyFeature(FeatureType.VISUAL, (3, 480, 640)),
        },
        output_features={"action": PolicyFeature(FeatureType.ACTION, (6,))},
        device="cuda", use_amp=False, push_to_hub=False,
        chunk_size=100, n_action_steps=100,
        pretrained_backbone_weights="ResNet18_Weights.IMAGENET1K_V1",
    )
    config = TrainPipelineConfig(
        dataset=DatasetConfig(repo_id=f"local/{TASK_NAME}", root=str(DATASET_DIR),
                              video_backend="pyav", use_imagenet_stats=False, eval_split=0.2),
        policy=policy, output_dir=model_output, job_name=label,
        steps=STEPS, batch_size=BATCH_SIZE,
        num_workers=0, seed=SEED, log_freq=LOG_EVERY,
        eval_steps=SAVE_EVERY, save_freq=SAVE_EVERY, save_checkpoint=True,
        max_eval_samples=0,
        wandb=WandBConfig(enable=False),
    )

    def make_fixed_datasets(cfg):
        datasets = []
        for name in ("train", "validation"):
            selected = copy.deepcopy(cfg)
            selected.dataset.episodes = split[name]
            selected.dataset.eval_split = 0.0
            if name == "validation":
                selected.dataset.image_transforms.enable = False
            dataset = make_dataset(selected)
            dataset.meta.stats = {
                key: {stat: torch.as_tensor(value.copy()) for stat, value in values.items()}
                for key, values in stats.items()
            }
            datasets.append(dataset)
        return tuple(datasets)

    settings = {"dataset": str(DATASET_DIR), "model_directory": str(model_output),
                "steps": config.steps, "batch_size": config.batch_size,
                "save_every": config.save_freq, "log_every": config.log_freq,
                "seed": SEED, "validation_ratio": 0.2,
                "policy": "ACT", "chunk_size": 100, "video_backend": "pyav",
                "pretrained_backbone_weights": policy.pretrained_backbone_weights}
    (record_output / "training_settings.json").write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    trainer = importlib.import_module("lerobot.scripts.lerobot_train")
    train_with_best(trainer, config, make_fixed_datasets, record_output)
    print(f"학습 완료 · 최고 모델: {model_output / 'best_model'}", flush=True)


if __name__ == "__main__":
    main()

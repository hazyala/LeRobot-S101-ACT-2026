"""doll_basic: TOP/SIDE RGB + 관절 6축. 부하·전류·depth 제외.
공식 코드: https://github.com/huggingface/lerobot/tree/v0.6.1/src/lerobot
분할과 통계 연결만 추가하며 공식 ACT 학습 루프를 유지한다.
"""
import argparse
import copy
import importlib
import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import torch
from lerobot.configs import FeatureType, PolicyFeature
from lerobot.configs.default import DatasetConfig, WandBConfig
from lerobot.configs.train import TrainPipelineConfig
from lerobot.datasets.compute_stats import aggregate_stats
from lerobot.datasets.factory import make_dataset
from lerobot.policies.act import ACTConfig

ROOT = Path("/NHNHOME/workspace/lerobot")
SPLIT_PATH = Path(__file__).with_name("split.json")


def read_split(root):
    split = json.loads(SPLIT_PATH.read_text(encoding="utf-8"))
    info = json.loads((root / "meta/info.json").read_text(encoding="utf-8-sig"))
    train_ids, val_ids = split["train"], split["validation"]
    if (
        not train_ids or not val_ids
        or set(train_ids) & set(val_ids)
        or sorted(train_ids + val_ids) != list(range(info["total_episodes"]))
    ):
        raise ValueError("분할 목록이 데이터셋과 일치하지 않습니다.")
    return split


def training_stats(root, train_ids):
    # 에피소드별 통계 중 학습 에피소드만 공식 함수로 합산한다.
    wanted, found, selected = set(train_ids), set(), []
    required = (
        "observation.state", "action",
        "observation.images.top", "observation.images.side",
    )
    for path in sorted((root / "meta/episodes").rglob("*.parquet")):
        for row in pq.read_table(path).to_pylist():
            ep = int(row["episode_index"])
            if ep not in wanted:
                continue
            if ep in found:
                raise ValueError(f"중복 에피소드 통계: {ep}")
            found.add(ep)
            stats = {}
            for key, value in row.items():
                if key.startswith("stats/") and value is not None:
                    feature, stat = key[6:].rsplit("/", 1)
                    stats.setdefault(feature, {})[stat] = np.atleast_1d(
                        np.asarray(value)
                    )
            for key in required:
                if not {"mean", "std", "count"}.issubset(stats.get(key, {})):
                    raise ValueError(f"에피소드 {ep} 통계 누락: {key}")
            selected.append(stats)

    if found != wanted:
        raise ValueError("일부 학습 에피소드의 통계가 없습니다.")
    stats = aggregate_stats(selected)
    for feature, values in stats.items():
        if any(not np.isfinite(value).all() for value in values.values()):
            raise ValueError(f"비정상 통계: {feature}")
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=50000)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--num-workers", type=int, default=7)
    parser.add_argument("--save-freq", type=int, default=1000)
    parser.add_argument("--eval-steps", type=int, default=1000)
    parser.add_argument("--log-freq", type=int, default=100)
    parser.add_argument("--check-config", action="store_true")
    parser.add_argument(
        "--output-dir", type=Path,
        default=ROOT / "outputs/act_doll_basic",
    )
    args = parser.parse_args()
    if min(
        args.steps, args.batch_size, args.save_freq,
        args.eval_steps, args.log_freq
    ) < 1 or args.num_workers < 0:
        parser.error("단계·배치·간격은 양수, 작업자 수는 0 이상이어야 합니다.")

    root = ROOT / "datasets/doll/dataset"
    split = read_split(root)
    stats = training_stats(root, split["train"])
    print("학습/검증:", len(split["train"]), len(split["validation"]), flush=True)
    print("관절 표준편차:", stats["observation.state"]["std"], flush=True)
    print("행동 표준편차:", stats["action"]["std"], flush=True)

    if args.check_config:
        print("분할·학습 통계 검사 통과. 학습은 실행하지 않았습니다.")
        return
    if args.output_dir.exists():
        parser.error(f"기존 결과를 덮어쓰지 않습니다: {args.output_dir}")

    # 관절 위치는 항상 포함한다. 부하·전류·depth는 모델 입력에서 제외한다.
    policy = ACTConfig(
        input_features={
            "observation.state": PolicyFeature(FeatureType.STATE, (6,)),
            "observation.images.top": PolicyFeature(
                FeatureType.VISUAL, (3, 480, 640)
            ),
            "observation.images.side": PolicyFeature(
                FeatureType.VISUAL, (3, 480, 640)
            ),
        },
        output_features={"action": PolicyFeature(FeatureType.ACTION, (6,))},
        device="cuda", use_amp=False, push_to_hub=False,
        chunk_size=100, n_action_steps=100,
        pretrained_backbone_weights="ResNet18_Weights.IMAGENET1K_V1",
    )
    config = TrainPipelineConfig(
        dataset=DatasetConfig(
            repo_id="local/doll", root=str(root),
            video_backend="torchcodec", use_imagenet_stats=False, eval_split=0.1,
        ),
        policy=policy, output_dir=args.output_dir, job_name="act_doll_basic",
        steps=args.steps, batch_size=args.batch_size,
        num_workers=args.num_workers, seed=1000,
        log_freq=args.log_freq, eval_steps=args.eval_steps,
        save_checkpoint=True, save_freq=args.save_freq,
        wandb=WandBConfig(enable=False),
    )

    def make_fixed_datasets(cfg):
        # 지정한 에피소드를 공식 로더로 읽는다.
        datasets = []
        for name in ("train", "validation"):
            selected_cfg = copy.deepcopy(cfg)
            selected_cfg.dataset.episodes = split[name]
            selected_cfg.dataset.eval_split = 0.0
            if name == "validation":
                selected_cfg.dataset.image_transforms.enable = False
            dataset = make_dataset(selected_cfg)

            # 메모리의 영상 목록에서 depth를 제외한다. 원본 파일은 유지한다.
            depth_keys = list(dataset.meta.depth_keys)
            for key in depth_keys:
                dataset.meta.features.pop(key, None)
                if dataset.reader.delta_indices is not None:
                    dataset.reader.delta_indices.pop(key, None)
                if dataset.delta_timestamps is not None:
                    dataset.delta_timestamps.pop(key, None)

            print(
                f"{name} 로더 영상: {dataset.meta.video_keys}",
                flush=True,
            )

            # 학습·검증 모두 학습 에피소드만의 통계를 사용한다.
            dataset.meta.stats = {
                key: {
                    stat: torch.as_tensor(value.copy())
                    for stat, value in values.items()
                }
                for key, values in stats.items()
            }
            datasets.append(dataset)

        cfg.output_dir.mkdir(parents=True, exist_ok=True)
        (cfg.output_dir / "split.json").write_text(
            json.dumps(split, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        serial = {
            key: {stat: value.tolist() for stat, value in values.items()}
            for key, values in stats.items()
        }
        (cfg.output_dir / "train_stats.json").write_text(
            json.dumps(serial, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return tuple(datasets)

    # 이 실행의 분할 함수만 대체하며 설치된 패키지는 변경하지 않는다.
    trainer = importlib.import_module("lerobot.scripts.lerobot_train")
    original = trainer.make_train_eval_datasets
    trainer.make_train_eval_datasets = make_fixed_datasets
    try:
        # 공식 로직이 정규화·sampler·ACT 손실·업데이트·평가·저장을 수행한다.
        trainer.train(config)
    finally:
        trainer.make_train_eval_datasets = original


if __name__ == "__main__":
    main()

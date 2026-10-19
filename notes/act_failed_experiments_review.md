# 인형 ACT 초기 실험 정리와 B200 성공 실험 비교

작성일: 2026-10-14. 사용자가 폐기 대상으로 지정한 네 실험의 로컬 코드·설정·보고서를 읽고 작성했다. 새 학습이나 로봇 실행은 하지 않았다. 아래 원본 실험 경로는 문서 작성 후 삭제한 당시 경로이며 링크로 사용하지 않는다.

## 결론

사용자는 `experiments/doll_B200_act`를 완전히 성공한 실험으로 확인했다. 성공 실험과 원본 수집 데이터는 보존하고, `doll_basic`, `doll_pickplace_act_official`, `doll_pickplace_act_v1`, `doll_pickplace_act_v2`는 폐기한다.

네 폴더를 모두 같은 종류의 학습 실패로 볼 수는 없다. v1에는 실물 객체 추적 저하 기록이 있다. v2는 수치 안정성 문제를 수정하고 소규모 검증까지 완료한 개발 실험이며, 남아 있는 파일에는 본 학습 결과가 없다. official은 빈 폴더다. doll_basic은 B200 공식 학습 준비 코드의 계보에 해당하며 실패를 입증하는 로컬 결과가 없다.

## 실험별 확인 내용

| 실험 | 삭제 전 내용 | 확인된 문제와 판단 |
|---|---|---|
| doll_basic | train.py, prepare_split.py, split.json, Python 캐시: 4파일 | 서버 경로를 사용하는 공식 LeRobot 학습 래퍼. 로컬 모델 결과 없음. 실패 모델이라고 단정할 수 없으며 성공 실험의 준비 코드로 기록한다. |
| doll_pickplace_act_official | 파일 0개 | 비어 있어 실패 원인을 분석할 증거가 없다. |
| doll_pickplace_act_v1 | 34파일, 약 0.39 GiB. baseline/motor_feedback 046000 가중치, 학습·실행 코드, 설정·지표·보고서 | README에 사용자의 실물 실행에서 객체 추적 성능 저하가 보고됐다고 명시돼 있다. 오프라인 예측 검사 통과가 실물 파지 성공으로 이어지지 않았다. |
| doll_pickplace_act_v2 | README, train.py, test_train.py, 캐시: 5파일 | README상 초기 AMP 배율 65536에서 첫 단계 비정상 기울기가 재현됐다. 배율 1024와 건너뛰기/중단 처리를 적용했다. 2026-10-08 임시 업데이트 2회 및 회귀 검사 8개 통과 후 본 학습은 시작하지 않았다고 기록돼 있다. 본 학습 산출물은 삭제 시점에도 없다. |

## v1: 실물 추적 실패와 오프라인 평가의 한계

원본은 499개 시연, 291,869프레임이다. 분할은 train 355 / validation 48 / test 48 / embargo 48이었다. TOP/SIDE RGB를 640×480에서 320×240으로 축소했다. baseline 입력은 관절 6축, motor_feedback은 관절·load·current의 18차원이다. 깊이와 torque limit은 모델 입력에서 제외했다.

두 모델 모두 46,000단계를 검증 MAE로 선택했다. 학습 설정은 배치 4, 목표 50,000단계, AdamW 1e-5, chunk 100, KL 가중치 10이었다. RGB는 ImageNet 평균·표준편차, 수치 입력·행동은 학습 데이터 통계로 정규화했다. 자체 데이터 준비·학습·실행 코드를 사용했고 실행 기본 재계획 간격은 30프레임이었다.

| 보존 보고서 수치 | baseline | motor_feedback |
|---|---:|---:|
| 테스트 정규화 MAE | 0.24401 | 0.23272 |
| 그리퍼 전체 MAE, 0–100 단위 | 4.053 | 3.993 |
| 닫기 시작 후 0.5초 그리퍼 MAE | 11.136 | 10.420 |
| 단일 관측 추론 p95 | 36.6 ms | 35.6 ms |

모터 피드백 추가의 테스트 MAE 개선은 약 4.63%였지만 실물 성공률 개선을 입증한 자료는 없다. 닫힘 구간 오차가 전체 그리퍼 평균보다 크게 나타났다는 것은 확인된다. 이 구간은 gripper 명령 15 이상을 기준으로 만든 대리 구간이며 실제 접촉·파지 라벨이 아니다.

확인된 실패 현상은 실물 객체 추적 저하다. 가능한 기여 요인은 다음과 같으며 단독 원인으로 확정하지 않는다.

- 해상도 축소: 픽셀 수가 원본의 1/4로 줄었다. 작은 물체·그리퍼 위치 정보 감소가 영향을 줄 수 있으나 동일 설정에서 해상도만 바꾼 실물 비교가 없다.
- 전체 평균 지표 중심의 선택: 접근·이동·HOME 복귀를 포함한 평균 오차는 짧은 파지 순간의 큰 오차를 가릴 수 있다. 닫힘 구간의 높은 오차는 이 가능성을 뒷받침하지만 실패 인과를 증명하지 않는다.
- 시연 조건 내 오프라인 평가: 연속 수집 구간을 홀드아웃한 평가였으며 새로운 장소·날짜나 실제 폐루프 실행을 검증하지 않았다. 유한한 예측과 낮은 MAE만으로 물체 추적·파지 성공을 판단할 수 없다.
- 자체 구현과 실행 설정 차이: 공식 B200 실험과 전처리·샘플러·분할·정밀도·배치·재계획이 함께 달라졌다. 자체 구현의 버그나 정규화 불일치가 실제 발생했다고 확인한 자료는 없다.

## v2: 수치 문제와 미완료 실험을 구분

v2는 v1 이후 원본 640×480 입력, 그리퍼 변화 주변 추가 샘플링, 밝기·대비 ±8% 증강, 파지 주변 오차를 포함한 모델 선택을 시도한 설계였다. 분할은 train 347 / validation 50 / test 50 / embargo 52, 실제 배치 2 × 누적 4, 학습률 1e-5, 100,000 업데이트 시도를 계획했다.

초기 AMP 배율 65536에서 비정상 기울기가 재현됐다는 기록은 수치 문제의 직접 근거다. 초기 배율 1024로 낮추고 비정상 업데이트를 건너뛰며 10회 연속이면 중단하도록 수정했다. 이후 작은 학습·저장·재로딩 검증은 통과했다. 따라서 수정 후 모델도 파지에 실패했다고 결론내릴 수 없다. 본 학습과 실물 비교를 완료하지 않은 채 폐기하는 실험이다.

그리퍼 주변 샘플링·증강·선택 점수 가중치는 검증되지 않은 개선 가설이다. SIDE 카메라 약 22.2 FPS에 따른 30 Hz 수집 내 영상 재사용도 README에 남아 있지만 B200과 공유하는 데이터 특성이므로 초기 실험만의 실패 원인으로 확정할 수 없다.

## 성공한 B200 실험과의 차이

성공 실험 근거는 보존한 `experiments/doll_B200_act/README.md`, `checkpoint_audit.json`, `selection/selected_checkpoint.json`, 선택 체크포인트 `047000/pretrained_model/config.json` 및 [서버 연구 기록](research_log_3.md)이다.

| 항목 | v1 | B200 |
|---|---|---|
| 입력 RGB | 320×240 TOP/SIDE | 640×480 TOP/SIDE |
| 관절 입력 | baseline 6축 / motor 18차원 | 관절 6축, 모터 피드백·depth 제외 |
| 학습 | 자체 래퍼·루프, AMP | 공식 LeRobot 0.6.1 trainer·로더·processor, AMP 꺼짐 |
| 배치 / 단계 | 4 / 목표 50,000 | 감사 기록상 64 / 최종 50,000 |
| 학습 / 검증 | 355 / 48, 별도 test·embargo | 449 / 50, 수집 기록 그룹 내 고정 분할 |
| RGB 정규화 | ImageNet 통계 | 학습 에피소드 통계, use_imagenet_stats=False |
| 체크포인트 선택 | 검증 MAE로 046000 | 50개 체크포인트를 동일 검증 500관측으로 비교해 047000 |
| 실행 재계획 | 기본 30프레임 | run_selected.py 경로는 기존 안전 제어기의 60프레임 재계획·전환 보간 재사용 |

B200 감사 기록은 1,000~50,000단계의 번호 체크포인트 50개, 구조 오류 0개, 최종 검사 대상의 비유한 텐서 0개, train/validation 중복 0개를 보고한다. 선택 체크포인트의 정규화 MAE는 0.19671549357204854이며, 50개 검증 에피소드 × 10시점에서 padding을 제외한 100행동 chunk를 평가한 값이다.

v1 테스트 MAE와 B200 검증 MAE는 분할·통계·표본·집계가 달라 직접 개선율을 계산하지 않는다. B200의 여러 변경을 동시에 적용한 결과이므로 GPU 종류, 해상도, FP32, 배치 또는 공식 루프 중 하나만을 성공 원인으로 단정하지 않는다.

사용자는 B200의 성공을 확인했다. 로컬 선택 JSON의 robot_success_rate_measured=false와 README의 실물 미실행 기록은 당시 자동 검증 범위를 나타낸다. 이 문서에서는 사용자 성공 확인과 저장된 오프라인 검증을 구분하며 성공 횟수·분모·실물 성공률 수치를 새로 만들지 않는다.

## 앞으로 유지할 기준

성공한 B200 경로와 저장된 공식 processor·학습 통계·데이터 분할을 기준으로 삼는다. 모델 변경 시 해상도, 정규화, 관절 순서, 시간 주기를 실행에서도 맞춘다. 새 실험은 한 번에 한 요소씩 변경하고, 오프라인 지표와 동일 초기 조건의 실물 파지·운반·놓기 결과를 함께 기록한다. 평균 MAE와 파지 순간 오차를 함께 보며, AMP를 다시 적용할 때는 작은 업데이트와 저장·재로딩부터 확인한다.

## 정리 범위와 보존 기록

삭제 대상은 `D:\lerobot-2026\experiments` 바로 아래의 `doll_basic`, `doll_pickplace_act_official`, `doll_pickplace_act_v1`, `doll_pickplace_act_v2` 네 폴더 전체다. 현재 수집 코드와 B200 실행 코드에서 이 네 로컬 폴더를 사용하는 참조는 확인되지 않았다. 과거 연구 기록의 서버 경로는 당시 이력으로 유지한다. 네 폴더는 Git에서 제외된 실험 산출물이었다.

`doll_B200_act`, `robot_datasets`, 보정값, 현재 수집 코드와 기존 100시연 ACT 실험은 삭제 대상에 포함하지 않는다. 아래에 원본 코드·설정과 파일별 SHA-256 목록을 보존한다. 해시 목록은 삭제 전 파일 식별용이며 삭제한 모델 가중치를 복구하는 백업은 아니다. doll_basic의 분할은 성공 결과 폴더에 같은 내용이 있는지 확인한 결과도 기록한다.

## 삭제 전 원본 코드·설정 보존

### experiments/doll_basic/train.py

```
"""RGB + 관절 6축 ACT. 부하/전류/depth 제외, LeRobot 0.6.1 공식 학습 루프.
출처: https://github.com/huggingface/lerobot/tree/v0.6.1/src/lerobot
사용자 지정 부분은 에피소드 분할과 학습 통계 연결뿐이다.
"""
from __future__ import annotations

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

ROOT = Path('/NHNHOME/workspace/lerobot')
SPLIT = Path(__file__).with_name('split.json')


def read_split(root):
    split = json.loads(SPLIT.read_text(encoding='utf-8'))
    info = json.loads((root / 'meta/info.json').read_text(encoding='utf-8-sig'))
    train_ids, val_ids = split['train'], split['validation']
    if (not train_ids or not val_ids or len(train_ids + val_ids) != info['total_episodes']
            or set(train_ids) & set(val_ids)
            or sorted(train_ids + val_ids) != list(range(info['total_episodes']))):
        raise ValueError('분할 목록이 데이터셋과 일치하지 않습니다.')
    return split


def training_stats(root, train_ids):
    # 저장된 에피소드별 통계를 공식 함수로 합친다. 검증 통계는 포함하지 않는다.
    selected, found = [], set()
    wanted = set(train_ids)
    for path in sorted((root / 'meta/episodes').rglob('*.parquet')):
        for row in pq.read_table(path).to_pylist():
            ep = int(row['episode_index'])
            if ep not in wanted:
                continue
            if ep in found:
                raise ValueError(f'중복 에피소드 통계: {ep}')
            found.add(ep)
            stats = {}
            for key, value in row.items():
                if key.startswith('stats/') and value is not None:
                    feature, stat = key[6:].rsplit('/', 1)
                    stats.setdefault(feature, {})[stat] = np.atleast_1d(np.asarray(value))
            for key in ('observation.state', 'action', 'observation.images.top', 'observation.images.side'):
                if not {'mean', 'std', 'count'}.issubset(stats.get(key, {})):
                    raise ValueError(f'에피소드 {ep} 통계 누락: {key}')
            selected.append(stats)
    if found != wanted:
        raise ValueError('일부 학습 에피소드의 통계가 없습니다.')
    stats = aggregate_stats(selected)
    for feature, values in stats.items():
        if any(not np.isfinite(value).all() for value in values.values()):
            raise ValueError(f'유한하지 않은 통계: {feature}')
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--steps', type=int, required=True)
    parser.add_argument('--batch-size', type=int, default=2)
    parser.add_argument('--num-workers', type=int, default=0)
    parser.add_argument('--save-freq', type=int, default=1000)
    parser.add_argument('--eval-steps', type=int, default=1000)
    parser.add_argument('--log-freq', type=int, default=100)
    parser.add_argument('--check-config', action='store_true')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'outputs/act_doll_basic')
    args = parser.parse_args()
    if min(args.steps, args.batch_size, args.save_freq, args.eval_steps, args.log_freq) < 1 or args.num_workers < 0:
        parser.error('단계/배치/간격은 양수, 작업자 수는 0 이상이어야 합니다.')
    root = ROOT / 'datasets/doll/dataset'
    split = read_split(root)
    stats = training_stats(root, split['train'])
    print('학습/검증 에피소드:', len(split['train']), len(split['validation']), flush=True)
    print('관절/행동 표준편차:', stats['observation.state']['std'], stats['action']['std'], flush=True)
    if args.check_config:
        print('분할·학습 통계 검사 통과. 학습은 실행하지 않았습니다.')
        return
    if args.output_dir.exists():
        parser.error(f'기존 결과를 덮어쓰지 않습니다: {args.output_dir}')

    policy = ACTConfig(
        input_features={
            'observation.state': PolicyFeature(FeatureType.STATE, (6,)),
            'observation.images.top': PolicyFeature(FeatureType.VISUAL, (3, 480, 640)),
            'observation.images.side': PolicyFeature(FeatureType.VISUAL, (3, 480, 640)),
        },
        output_features={'action': PolicyFeature(FeatureType.ACTION, (6,))},
        device='cuda', use_amp=False, push_to_hub=False,
        chunk_size=100, n_action_steps=100,
        pretrained_backbone_weights='ResNet18_Weights.IMAGENET1K_V1',
    )
    config = TrainPipelineConfig(
        dataset=DatasetConfig(repo_id='local/doll', root=str(root), video_backend='torchcodec',
                              use_imagenet_stats=False),
        policy=policy, output_dir=args.output_dir, job_name='act_doll_basic',
        steps=args.steps, batch_size=args.batch_size, num_workers=args.num_workers,
        seed=1000, log_freq=args.log_freq, eval_steps=args.eval_steps,
        save_checkpoint=True, save_freq=args.save_freq, wandb=WandBConfig(enable=False),
    )

    def make_fixed_datasets(cfg):
        # 에피소드 지정만 바꾸고 공식 로더·시간창·sampler를 유지한다.
        # 학습/검증 모두 같은 학습 전용 통계로 정규화한다.
        datasets = []
        for name in ('train', 'validation'):
            selected_cfg = copy.deepcopy(cfg)
            selected_cfg.dataset.episodes = split[name]
            selected_cfg.dataset.eval_split = 0.0
            if name == 'validation':
                selected_cfg.dataset.image_transforms.enable = False
            dataset = make_dataset(selected_cfg)
            dataset.meta.stats = {
                key: {stat: torch.as_tensor(value.copy()) for stat, value in values.items()}
                for key, values in stats.items()
            }
            datasets.append(dataset)
        cfg.output_dir.mkdir(parents=True, exist_ok=True)
        (cfg.output_dir / 'split.json').write_text(json.dumps(split, ensure_ascii=False, indent=2), encoding='utf-8')
        serial = {key: {stat: value.tolist() for stat, value in values.items()} for key, values in stats.items()}
        (cfg.output_dir / 'train_stats.json').write_text(json.dumps(serial, ensure_ascii=False, indent=2), encoding='utf-8')
        return tuple(datasets)

    # 공식 마지막 구간 분할만 이 실행 안에서 대체한다. 설치된 패키지는 수정하지 않는다.
    trainer = importlib.import_module('lerobot.scripts.lerobot_train')
    original = trainer.make_train_eval_datasets
    trainer.make_train_eval_datasets = make_fixed_datasets
    try:
        trainer.train(config)
    finally:
        trainer.make_train_eval_datasets = original


if __name__ == '__main__':
    main()

```
### experiments/doll_basic/prepare_split.py

```
"""로컬 수집 기록별로 약 10개마다 검증 1개 선택. 원본을 변경하지 않는다."""
import json
from collections import defaultdict
from pathlib import Path
import numpy as np

root = Path(__file__).resolve().parents[2] / 'robot_datasets/tasks/pick_doll'
info = json.loads((root / 'dataset/meta/info.json').read_text(encoding='utf-8-sig'))
groups = defaultdict(list)
for ep in range(info['total_episodes']):
    row = json.loads((root / f'sessions/episode_{ep:06d}.json').read_text(encoding='utf-8-sig'))
    label = ''.join(row['session'].split())
    groups[label].append(ep)
rng = np.random.default_rng(1000)
validation, records = [], []
for label, ids in sorted(groups.items(), key=lambda item: min(item[1])):
    ids.sort()
    blocks = np.array_split(ids, max(1, round(len(ids) / 10)))
    selected = sorted(int(rng.choice(block)) for block in blocks)
    validation.extend(selected)
    records.append({'session': label, 'episodes': ids, 'validation': selected})
validation.sort()
train = sorted(set(range(info['total_episodes'])) - set(validation))
split = {'seed': 1000, 'method': 'one random episode per approximately 10 consecutive episodes within each recorded session',
         'train': train, 'validation': validation, 'groups': records}
assert not set(train) & set(validation)
assert sorted(train + validation) == list(range(info['total_episodes']))
path = Path(__file__).with_name('split.json')
path.write_text(json.dumps(split, ensure_ascii=False, indent=2), encoding='utf-8')
print('학습:', len(train), '검증:', len(validation), '수집 기록 그룹:', len(records))
print('저장:', path)

```
### experiments/doll_pickplace_act_v1/outputs/baseline/run_config.json

```
{
  "variant": "baseline",
  "seed": 20261006,
  "batch_size": 4,
  "image_hw": [
    240,
    320
  ],
  "chunk_size": 100,
  "learning_rate": 1e-05,
  "train_frames": 207717,
  "target_steps": 50000,
  "state_dimensions": 6,
  "motor_order": [
    "position"
  ],
  "sources": [
    "https://arxiv.org/abs/2304.13705",
    "https://github.com/tonyzhaozh/act",
    "https://huggingface.co/docs/lerobot/main/en/act"
  ],
  "sampler": "512-step deterministic four-tile pools, tile selection weighted by training-frame count; uniform marginal frame probability"
}
```
### experiments/doll_pickplace_act_v1/outputs/motor_feedback/run_config.json

```
{
  "variant": "motor_feedback",
  "seed": 20261006,
  "batch_size": 4,
  "image_hw": [
    240,
    320
  ],
  "chunk_size": 100,
  "learning_rate": 1e-05,
  "train_frames": 207717,
  "target_steps": 50000,
  "state_dimensions": 18,
  "motor_order": [
    "position",
    "load_raw",
    "current_raw"
  ],
  "sources": [
    "https://arxiv.org/abs/2304.13705",
    "https://github.com/tonyzhaozh/act",
    "https://huggingface.co/docs/lerobot/main/en/act"
  ],
  "sampler": "512-step deterministic four-tile pools, tile selection weighted by training-frame count; uniform marginal frame probability"
}
```

성공 결과 split.json과 삭제 대상 doll_basic/split.json의 SHA-256 일치: False.
```json
{
  "seed": 1000,
  "method": "one random episode per approximately 10 consecutive episodes within each recorded session",
  "train": [
    0,
    1,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    16,
    17,
    18,
    19,
    20,
    21,
    22,
    23,
    24,
    25,
    26,
    27,
    29,
    30,
    31,
    32,
    33,
    34,
    36,
    37,
    38,
    39,
    40,
    41,
    42,
    43,
    44,
    45,
    47,
    48,
    49,
    50,
    51,
    53,
    54,
    55,
    56,
    57,
    58,
    60,
    61,
    62,
    63,
    64,
    65,
    66,
    67,
    68,
    69,
    71,
    72,
    73,
    74,
    75,
    76,
    77,
    78,
    79,
    80,
    81,
    82,
    83,
    85,
    86,
    87,
    88,
    89,
    90,
    91,
    92,
    93,
    94,
    96,
    97,
    98,
    99,
    100,
    101,
    103,
    104,
    105,
    106,
    107,
    108,
    109,
    110,
    112,
    113,
    114,
    115,
    116,
    117,
    118,
    119,
    120,
    121,
    122,
    123,
    125,
    126,
    127,
    128,
    129,
    130,
    131,
    133,
    134,
    135,
    136,
    137,
    138,
    139,
    140,
    141,
    143,
    144,
    145,
    146,
    147,
    148,
    149,
    150,
    151,
    152,
    153,
    154,
    155,
    156,
    158,
    159,
    160,
    162,
    163,
    164,
    165,
    166,
    167,
    168,
    169,
    170,
    171,
    172,
    174,
    175,
    176,
    178,
    179,
    180,
    181,
    182,
    183,
    184,
    185,
    186,
    187,
    188,
    189,
    190,
    191,
    192,
    193,
    194,
    195,
    196,
    198,
    199,
    200,
    201,
    202,
    203,
    204,
    205,
    206,
    208,
    209,
    210,
    211,
    212,
    213,
    214,
    215,
    216,
    218,
    219,
    220,
    221,
    222,
    223,
    224,
    226,
    227,
    228,
    229,
    230,
    232,
    233,
    234,
    235,
    236,
    237,
    238,
    239,
    240,
    241,
    242,
    243,
    244,
    245,
    247,
    248,
    249,
    251,
    252,
    253,
    254,
    255,
    256,
    257,
    258,
    259,
    260,
    261,
    262,
    263,
    264,
    266,
    267,
    268,
    269,
    270,
    271,
    272,
    273,
    274,
    275,
    276,
    277,
    279,
    281,
    282,
    283,
    284,
    285,
    286,
    287,
    288,
    289,
    290,
    291,
    292,
    293,
    294,
    295,
    297,
    298,
    299,
    300,
    302,
    303,
    304,
    305,
    306,
    307,
    308,
    309,
    310,
    311,
    313,
    314,
    315,
    316,
    317,
    318,
    319,
    320,
    321,
    322,
    323,
    325,
    326,
    327,
    328,
    329,
    330,
    331,
    333,
    334,
    335,
    336,
    337,
    338,
    339,
    340,
    341,
    342,
    343,
    344,
    345,
    346,
    347,
    348,
    350,
    351,
    352,
    353,
    354,
    355,
    357,
    358,
    359,
    360,
    361,
    362,
    363,
    364,
    365,
    366,
    367,
    369,
    370,
    371,
    372,
    373,
    374,
    375,
    377,
    378,
    379,
    380,
    381,
    382,
    384,
    385,
    386,
    387,
    388,
    389,
    390,
    391,
    392,
    393,
    394,
    395,
    396,
    397,
    399,
    400,
    401,
    402,
    404,
    405,
    406,
    407,
    408,
    409,
    410,
    411,
    412,
    413,
    414,
    415,
    416,
    417,
    419,
    420,
    421,
    422,
    423,
    424,
    425,
    426,
    428,
    429,
    431,
    432,
    433,
    434,
    435,
    436,
    437,
    438,
    439,
    440,
    441,
    442,
    443,
    444,
    446,
    447,
    448,
    449,
    450,
    451,
    452,
    453,
    454,
    456,
    457,
    458,
    459,
    460,
    461,
    462,
    463,
    464,
    465,
    466,
    468,
    469,
    470,
    471,
    472,
    474,
    475,
    476,
    477,
    478,
    479,
    480,
    481,
    483,
    484,
    485,
    486,
    487,
    488,
    490,
    491,
    492,
    493,
    494,
    495,
    496,
    497,
    498
  ],
  "validation": [
    2,
    15,
    28,
    35,
    46,
    52,
    59,
    70,
    84,
    95,
    102,
    111,
    124,
    132,
    142,
    157,
    161,
    173,
    177,
    197,
    207,
    217,
    225,
    231,
    246,
    250,
    265,
    278,
    280,
    296,
    301,
    312,
    324,
    332,
    349,
    356,
    368,
    376,
    383,
    398,
    403,
    418,
    427,
    430,
    445,
    455,
    467,
    473,
    482,
    489
  ],
  "groups": [
    {
      "session": "2026-10-02:인형pickplace_stand(section1~3)",
      "episodes": [
        0,
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        11,
        12,
        13,
        14,
        15,
        16,
        17,
        18,
        19,
        20,
        21,
        22,
        23,
        24,
        25,
        26,
        27,
        28,
        29,
        30,
        31,
        32,
        33,
        34,
        35,
        36,
        37,
        38,
        39,
        40,
        41,
        42,
        43,
        44,
        45,
        46,
        47,
        48,
        49,
        50,
        51,
        52,
        53,
        54,
        55,
        56
      ],
      "validation": [
        2,
        15,
        28,
        35,
        46,
        52
      ]
    },
    {
      "session": "2026-10-03:doll_pickplace_stand(section3~5)",
      "episodes": [
        57,
        58,
        59,
        60,
        61,
        62,
        63,
        64,
        65,
        66,
        67,
        68,
        69,
        70,
        71,
        72,
        73,
        74,
        75,
        76,
        77,
        78,
        79,
        80,
        81,
        82,
        83,
        84,
        85,
        86,
        87,
        88,
        89
      ],
      "validation": [
        59,
        70,
        84
      ]
    },
    {
      "session": "2026-10-03:doll_pickplace_stand(section5~6)",
      "episodes": [
        90,
        91,
        92,
        93,
        94,
        95,
        96,
        97,
        98,
        99,
        100,
        101,
        102,
        103,
        104,
        105,
        106,
        107,
        108,
        109,
        110,
        111,
        112,
        113,
        114,
        115,
        116,
        117,
        118
      ],
      "validation": [
        95,
        102,
        111
      ]
    },
    {
      "session": "2026-10-03:doll_pickplace_stand(section7~8)",
      "episodes": [
        119,
        120,
        121,
        122,
        123,
        124,
        125,
        126,
        127,
        128,
        129,
        130,
        131,
        132,
        133,
        134,
        135,
        136,
        137,
        138,
        139,
        140,
        141,
        142,
        143,
        144,
        145,
        146,
        147,
        148,
        149,
        150,
        151,
        152,
        153,
        154,
        155,
        156,
        157,
        158,
        159
      ],
      "validation": [
        124,
        132,
        142,
        157
      ]
    },
    {
      "session": "2026-10-03:doll_pickplace_stand(section9~10)",
      "episodes": [
        160,
        161,
        162,
        163,
        164,
        165,
        166,
        167,
        168,
        169,
        170,
        171,
        172,
        173,
        174,
        175,
        176
      ],
      "validation": [
        161,
        173
      ]
    },
    {
      "session": "2026-10-04:doll_pickplace_stand(section9~10)",
      "episodes": [
        177,
        178,
        179,
        180,
        181,
        182,
        183,
        184,
        185,
        186,
        187,
        188,
        189,
        190,
        191,
        192,
        193,
        194,
        195,
        196,
        197,
        198
      ],
      "validation": [
        177,
        197
      ]
    },
    {
      "session": "2026-10-04:doll_pickplace_lie(section1~2)",
      "episodes": [
        199,
        200,
        201,
        202,
        203,
        204,
        205,
        206,
        207,
        208,
        209,
        210,
        211,
        212,
        213,
        214,
        215,
        216,
        217,
        218,
        219,
        220,
        221,
        222,
        223,
        224,
        225,
        226,
        227,
        228
      ],
      "validation": [
        207,
        217,
        225
      ]
    },
    {
      "session": "2026-10-04:doll_pickplace_lie(section3~4)",
      "episodes": [
        229,
        230,
        231,
        232,
        233,
        234,
        235,
        236,
        237,
        238,
        239,
        240,
        241,
        242,
        243,
        244,
        245,
        246,
        247,
        248,
        249,
        250,
        251,
        252,
        253,
        254,
        255,
        256,
        257,
        258,
        259,
        260,
        261,
        262,
        263,
        264,
        265,
        266,
        267,
        268,
        269,
        270,
        271,
        272,
        273,
        274,
        275,
        276,
        277,
        278
      ],
      "validation": [
        231,
        246,
        250,
        265,
        278
      ]
    },
    {
      "session": "2026-10-04:doll_pickplace_lie(section5~6)",
      "episodes": [
        279,
        280,
        281,
        282,
        283,
        284,
        285,
        286,
        287,
        288,
        289,
        290,
        291,
        292,
        293,
        294,
        295,
        296,
        297,
        298,
        299,
        300,
        301,
        302,
        303,
        304,
        305,
        306,
        307,
        308,
        309,
        310,
        311,
        312,
        313,
        314,
        315,
        316,
        317,
        318,
        319
      ],
      "validation": [
        280,
        296,
        301,
        312
      ]
    },
    {
      "session": "2026-10-06:doll_pickplace_stand(section7~8)",
      "episodes": [
        320,
        321,
        322,
        323,
        324,
        325,
        326,
        327,
        328,
        329,
        330,
        331,
        332,
        333,
        334,
        335,
        336,
        337,
        338,
        339,
        340,
        341,
        342,
        343,
        344,
        345,
        346,
        347,
        348,
        349
      ],
      "validation": [
        324,
        332,
        349
      ]
    },
    {
      "session": "2026-10-06:doll_pickplace_stand(section8~10)",
      "episodes": [
        350,
        351,
        352,
        353,
        354,
        355,
        356,
        357,
        358,
        359,
        360,
        361,
        362,
        363,
        364,
        365,
        366,
        367,
        368,
        369,
        370,
        371,
        372,
        373,
        374,
        375,
        376,
        377,
        378,
        379,
        380,
        381,
        382,
        383,
        384,
        385,
        386,
        387,
        388,
        389,
        390,
        391,
        392,
        393,
        394,
        395,
        396,
        397,
        398
      ],
      "validation": [
        356,
        368,
        376,
        383,
        398
      ]
    },
    {
      "session": "2026-10-06:doll_pickplace_stand(section1~5)",
      "episodes": [
        399,
        400,
        401,
        402,
        403,
        404,
        405,
        406,
        407,
        408,
        409,
        410,
        411,
        412,
        413,
        414,
        415,
        416,
        417,
        418,
        419,
        420,
        421,
        422,
        423,
        424,
        425,
        426,
        427,
        428,
        429,
        430,
        431,
        432,
        433,
        434,
        435,
        436,
        437,
        438,
        439,
        440,
        441,
        442,
        443,
        444,
        445,
        446,
        447,
        448
      ],
      "validation": [
        403,
        418,
        427,
        430,
        445
      ]
    },
    {
      "session": "2026-10-06:doll_pickplace_stand&lie(section5~10)",
      "episodes": [
        449,
        450,
        451,
        452,
        453,
        454,
        455,
        456,
        457,
        458,
        459,
        460,
        461,
        462,
        463,
        464,
        465,
        466,
        467,
        468,
        469,
        470,
        471,
        472,
        473,
        474,
        475,
        476,
        477,
        478,
        479,
        480,
        481,
        482,
        483,
        484,
        485,
        486,
        487,
        488,
        489,
        490,
        491,
        492,
        493,
        494,
        495,
        496,
        497,
        498
      ],
      "validation": [
        455,
        467,
        473,
        482,
        489
      ]
    }
  ]
}
```

## 삭제 전 파일 목록

| 파일 | 바이트 | SHA-256 |
|---|---:|---|
| experiments/doll_basic/prepare_split.py | 1633 | D29AD3562D931C609ACABD111C8760D19186D0EA23053A2690442EBBD50B8268 |
| experiments/doll_basic/split.json | 14470 | A0A3480C14EDDB5653A85DEDC375031EDA8A8FA03991F04F84F049B54A035F9E |
| experiments/doll_basic/train.py | 7095 | B14D6CED3C767E29436E6F652AEF4D531DE3BC89F8895ECAB1BA95313E2CB272 |
| experiments/doll_basic/__pycache__/train.cpython-312.pyc | 10407 | E5CDCB5E39C8326B1BDE4B360ED806C770C35CD066D26DC16FAD59CD91C9D4F6 |
| experiments/doll_pickplace_act_v1/README.md | 3978 | 73D1F420DD008CC234D3863D7135E3E8EBA9AC9D4A46550EA8B2D4393CF5FB10 |
| experiments/doll_pickplace_act_v1/execution/기본 모델 실행.cmd | 163 | 621C5058727714FCBAB5CDF832E484F2A3AF7E40282D245456D8ECF9D7DA6D57 |
| experiments/doll_pickplace_act_v1/execution/모터 모델 실행.cmd | 160 | B2AD910F0A6A1EF3D185F4798DD4612251033A9C67A2260C2EEF2B7E67AD0004 |
| experiments/doll_pickplace_act_v1/execution/run_baseline.py | 18733 | C66D9FD38B84317156D9F3D1D2BCE87E9D603258345C037C539311A2794F7A53 |
| experiments/doll_pickplace_act_v1/execution/run_motor.py | 18739 | E6551744F8C14EA43134A2C2681D3AD7391C6846E9F7049970EA1DEA7FD211C9 |
| experiments/doll_pickplace_act_v1/execution/run.py | 147 | 607A47A2B62C3F16477C26345CB657C601EAA1313AF28414B095C08F8BECBB9F |
| experiments/doll_pickplace_act_v1/outputs/preflight_sample.npz | 122618 | 371BB8054F6531EECE882A280A9E45F3A3EA5B7F421B175112D9CBA2FC96F416 |
| experiments/doll_pickplace_act_v1/outputs/baseline/best.json | 102 | 7224686F41C5E17301CA3D3685C908B25893F0990FFC07F57022F04722A1CFC8 |
| experiments/doll_pickplace_act_v1/outputs/baseline/execution_profile.json | 331 | 45C84464BFC4D4FED4CB8598B8145B588BD2895AD9F5C39635863B37B9519DB9 |
| experiments/doll_pickplace_act_v1/outputs/baseline/metrics.jsonl | 314000 | DE38CEB1C46EFA2A62085B023F4D0D9E71208F7C42E1B67EDD59685CB5E46D0A |
| experiments/doll_pickplace_act_v1/outputs/baseline/run_config.json | 583 | 9FA10EF6B9E642A92B7EDB1F4BD875B0D1380AEC464AE71E0D399426BA11F828 |
| experiments/doll_pickplace_act_v1/outputs/baseline/training_curve.png | 112162 | 46E1F274A71CA5F58FAA788D302274F9AAB98236EFB22B511340366B540D23E1 |
| experiments/doll_pickplace_act_v1/outputs/baseline/checkpoints/046000/complete.json | 191 | 4375C4D4CCFCA336D18F76FC51DEA5A54B37F0EA100C0D7325C96B0C6F7FF15C |
| experiments/doll_pickplace_act_v1/outputs/baseline/checkpoints/046000/normalization.json | 5976 | E2F015D440EFC4CA0EB5AFC24ED8CE5C44031913CBFF89F34117D2748C87DCA9 |
| experiments/doll_pickplace_act_v1/outputs/baseline/checkpoints/046000/validation.json | 1881 | 366D32F852AA9DD58A95F0FACFA3B7E06E3E1EBDB397577345EBA42EF22F05FC |
| experiments/doll_pickplace_act_v1/outputs/baseline/checkpoints/046000/pretrained_model/config.json | 1764 | D06EFD4072BE7887247BB3FA13C9314C28C2CDD398D527EEAEDCBB3CF52C0537 |
| experiments/doll_pickplace_act_v1/outputs/baseline/checkpoints/046000/pretrained_model/model.safetensors | 206699736 | 786846F502FFC6F9B45C1460C258C86021E795D36CAF1169FEFCFDAC3A23DAAE |
| experiments/doll_pickplace_act_v1/outputs/motor_feedback/best.json | 103 | C52FBD6BBB8803BC03F5DAF81799A6F4EB03D23B7B58C6A76DB6C4117E54ACFF |
| experiments/doll_pickplace_act_v1/outputs/motor_feedback/execution_profile.json | 337 | 8C8413F62A2BDD4464A9588DEB21A8FA41C171358C8EF25E6314068C3F5C8175 |
| experiments/doll_pickplace_act_v1/outputs/motor_feedback/metrics.jsonl | 314232 | 3ED7571AA613DD5395DFF7438668F0576E015A5CD8A19A5CDE15B2F2F9261C95 |
| experiments/doll_pickplace_act_v1/outputs/motor_feedback/run_config.json | 627 | 093023D0B7512535D952E2B661350BF2E91DA6EC2979E26100179309A5E4A218 |
| experiments/doll_pickplace_act_v1/outputs/motor_feedback/training_curve.png | 119125 | 1060F6BAE04D8CE35ACA6E9F3BF4441316921A1D157F8A4C8D1B8D124806DBAB |
| experiments/doll_pickplace_act_v1/outputs/motor_feedback/checkpoints/046000/complete.json | 197 | 8217A356436AA0E6CF1C27DF12F993151CD356595D299BA823520C8781BA2E04 |
| experiments/doll_pickplace_act_v1/outputs/motor_feedback/checkpoints/046000/normalization.json | 5976 | E2F015D440EFC4CA0EB5AFC24ED8CE5C44031913CBFF89F34117D2748C87DCA9 |
| experiments/doll_pickplace_act_v1/outputs/motor_feedback/checkpoints/046000/validation.json | 1894 | 76CAED0D682EF316199AD736AFCE3F701D939408EB317DFBEC0EFB85EB4438A6 |
| experiments/doll_pickplace_act_v1/outputs/motor_feedback/checkpoints/046000/pretrained_model/config.json | 1765 | 62B64EC4208218C0B921C7C1898B0C59A5DCA48CD55DB37B740A96DB26E6404F |
| experiments/doll_pickplace_act_v1/outputs/motor_feedback/checkpoints/046000/pretrained_model/model.safetensors | 206748888 | F5A228314FB533D9E58A0F05B2DE17ADCF9FE92646320557B6716E4E6F19B374 |
| experiments/doll_pickplace_act_v1/reports/example_baseline.png | 139930 | 4F325265122C3C659E176FEA7E73F4964C2A1A9300467BCEC6654AD5B45DC04C |
| experiments/doll_pickplace_act_v1/reports/example_motor_feedback.png | 147836 | A822D769C6C86D7D75C242A51A69C8C53B424B6250A7CD45E93D472E68DA7706 |
| experiments/doll_pickplace_act_v1/reports/RESULTS.md | 2972 | 550CEF56FD59E32984055D0631DAC69C433A55546A0CD7F4F02A0AD17777CAEF |
| experiments/doll_pickplace_act_v1/reports/test_comparison.png | 52234 | E4B08B9A9C5F01B7B6A596C8DAEA5088E9BBF456C683C87D9667DA20BE1B3F92 |
| experiments/doll_pickplace_act_v1/training/common.py | 3376 | E76DE5B1F673BB0983BDED84790D1838C010663F784AA752B72F89A8FCB0AE9B |
| experiments/doll_pickplace_act_v1/training/prepare.py | 10523 | 960F0BC0B10E1D128511429024938BFFF9FB36E346244D088BE9F50573CA0328 |
| experiments/doll_pickplace_act_v1/training/train.py | 20532 | 476A206DDC21ECF3D6ABB8DE9EDDE693DE148D0F977FDDFE0A2E75F2B421CD26 |
| experiments/doll_pickplace_act_v2/README.md | 9179 | 20633ACCC3C3BE361A1D446C50794264D44738389E34BF734D45A0D9B5D21FEB |
| experiments/doll_pickplace_act_v2/training/test_train.py | 6279 | 093D0A2B4A37D9500773FFA9B491C4F397E441DF2749D61EB8F63B7C68ED8824 |
| experiments/doll_pickplace_act_v2/training/train.py | 39099 | 626FB4C9609C26F716D6BD4A3F8432C84C60B0A157FBFA343FC0A5F9F2D7F7D1 |
| experiments/doll_pickplace_act_v2/training/__pycache__/test_train.cpython-312.pyc | 14334 | C73A0D0637545A65F04023DEB242CB554682934062149B5048333069708C0818 |
| experiments/doll_pickplace_act_v2/training/__pycache__/train.cpython-312.pyc | 63190 | D737C89CBD251219997AC4C81D60631D2C12F2E1E1466024F13FCCB1DDF4B2CD |

## 삭제 완료 확인

2026-10-14: 지정한 네 폴더를 삭제하고 각 경로가 존재하지 않음을 확인했다. doll_B200_act의 삭제 전후 파일 수는 573 개로 같고 selected_checkpoint.json의 SHA-256도 동일했다.

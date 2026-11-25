# Sorting + no-HOME pick-and-place ACT v1

서버 실행: 2026-10-24 20:27 KST 본 학습 시작.

- 기존 sorting 전용 모델은 그대로 보존한다.
- 새 출력: `/NHNHOME/workspace/lerobot/outputs/act_sorting_pickplace_nohome_mix_v1_20261024_202619`.
- 서버 코드: `/NHNHOME/workspace/lerobot/experiments/act/sorting_pickplace_nohome_mix_v1`.
- 서버 파생 데이터: `/NHNHOME/workspace/lerobot/datasets/pickplace_nohome_v1`.
- 로컬 파생 데이터: `robot_datasets/derived/pickplace_nohome_v1`.

## 학습 구성

50,000 step, batch 8, seed 1000, ACT chunk 100, TOP/SIDE RGB + 관절 6축. 기존 baseline과 같은 새 ACT 초기화 및 ImageNet ResNet18 backbone을 사용한다. 기존 checkpoint에서 이어 학습하지 않는다.

학습 에피소드: sorting 120, HOME 제외 인형 449, HOME 제외 컵 200, 총 769개 / 448,699프레임. 인형 검증 50개·컵 검증 50개·sorting 검증 30개는 학습에서 제외한다. 매 배치에서 sorting 4 / 인형 2 / 컵 2 프레임을 source 내부 균등 복원추출한다. 단일 GPU·batch 8용 구성이다.

단독 데이터는 접근·파지·운반·놓기·필요한 짧은 이탈까지만 사용한다. sorting은 두 물체 분류와 최종 HOME까지 전체를 사용한다. 데이터 source 비중을 조절하는 방식이며 별도 파지 손실이나 추론 단계별 제어를 추가하지 않는다.

정규화 통계는 각 source의 train 에피소드 통계만 공식 aggregate_stats로 합산한다. 원본 프레임 수에 따른 통계 집계이며, sampler의 50/25/25 비중으로 통계를 재가중하지 않는다. 검증에도 같은 train 통계를 사용한다.

2,000 step마다 sorting 검증 30개 전체를 평가·저장하고, 유한한 검증 손실 최솟값을 `best.json` 및 `checkpoints/best`로 가리킨다. 혼합 통계는 baseline과 다르므로 정규화 검증 손실 숫자만으로 두 모델의 실제 성능을 비교하면 안 된다.

## 구현과 확인

공식 LeRobot 개별 데이터 로더와 ACT 학습·손실·평가·저장 루프를 재사용한다. `MixedDataset`이 학습 source 3개를 연결하고 `BalancedSampler`가 source 비중을 정한다. 설치된 LeRobot 파일은 수정하지 않는다. `baseline_reference.py`의 통계 집계 함수를 재사용한다.

`prepare.py`는 업로드 파일 SHA-256, 서버 원본과 749개 action/state prefix 일치, RGB 원본 파일 크기 및 하드링크 동일성을 확인한다. 전체 영상 바이트 SHA-256을 다시 검사한 것은 아니다. 로컬 경계 검토와 전수 로더 검사 결과는 데이터의 `validation_report.json`에 있다.

payload SHA-256: `8890669b828d162ab86d7b357316e0af647bffd82fbe6b29bda9dc42f525533d`.

10-step smoke test에서 source별 배치 비율, 4-worker 학습, sorting 1개 에피소드 검증, checkpoint 및 best 저장을 확인했다. smoke 출력은 `smoke_sorting_pickplace_nohome_mix_v1_20261024_202619`이며 최종 모델과 분리되어 있다. 본 학습은 sorting 검증 30개를 사용한다.

상태: `pipeline_status.json`. 로그: `prepare.log`, `smoke.log`, `training.log`. 파이프라인은 중복 실행을 잠금으로 막으며 검사 실패 시 본 학습을 시작하지 않는다. 실행 중 같은 폴더에서 중복 실행하지 않는다.

`train.py --output <새 경로>`는 새 학습을 실행한다. `pipeline.py`는 검증·짧은 검사 후 새 학습을 실행한다. 재시작/복구용 CLI는 제공하지 않으며 resume을 임의로 적용하지 않는다.

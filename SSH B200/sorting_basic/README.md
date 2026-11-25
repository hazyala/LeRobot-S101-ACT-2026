# Sorting ACT — sorting 150개 전용

## 데이터와 분할

- 서버 데이터: `/NHNHOME/workspace/lerobot/datasets/sorting/dataset`
- 로컬 원본: `robot_datasets/tasks/sort_doll_cup/dataset`
- 기존 pick_doll / pick_paper_cup 데이터와 모델 가중치는 사용하지 않습니다.
- sorting 150개 중 학습 120개 / 검증 30개, seed 1000.
- 수집 조건과 시간 순서 구간을 반영해 매 5개 중 1개를 검증으로 고정합니다.
- 학습 에피소드만의 통계를 학습·검증에 공통 적용합니다.
- 원본 depth·연구 항목은 보존하고 정책 입력에서 제외합니다.

| 조건 | 학습 | 검증 |
|---|---:|---:|
| 인형 우선 첫 세션 | 20 | 5 |
| 인형 우선 두 번째 세션 | 20 | 5 |
| 컵 우선 | 40 | 10 |
| 나란히 인형 왼쪽 | 16 | 4 |
| 나란히 인형 오른쪽 | 16 | 4 |
| 인형 외곽 | 8 | 2 |

## 학습 설정

기존 종이컵 ACT 설정을 기준으로 사용합니다.
ACT / ResNet18 ImageNet 초기 가중치, TOP·SIDE RGB + 관절 6축,
50,000 steps, batch 8, workers 4, prefetch 2, FP32, seed 1000,
chunk_size / n_action_steps 100 / 100, 공식 ACT optimizer preset(학습률 1e-5).
평가·저장은 2,000 step마다 실행하며 검증 30개 전체를 사용합니다.

## 실행 순서

`pipeline.py`는 파일 크기 기준 전송 완료를 기다린 뒤 전체 SHA-256 비교,
10-step 학습·검증 2개·best 저장 검사, 50,000-step 본 학습 순서로 실행합니다.
무결성 검사나 짧은 학습에 실패하면 본 학습을 시작하지 않습니다.
검사 모델은 본 학습 초기 가중치나 최종 모델로 사용하지 않습니다.

서버 tmux 세션: `sorting_act_150`. SSH 연결이 끊겨도 서버 작업은 계속됩니다.
진행 상태: `pipeline_status.json`.
로그: `verify_transfer.log`, `smoke_test.log`, `training.log`.
기존 결과는 덮어쓰지 않습니다. 재실행은 자동 이어 학습이 아닙니다.

## 결과

- 출력: `/NHNHOME/workspace/lerobot/outputs/act_sorting_basic_날짜_시각/`
- best 모델: `checkpoints/best/pretrained_model/`
- 선택 기록: `best.json`
- 최신 모델: `checkpoints/last/`
- 재현 자료: `split.json`, `train_stats.json`, 공식 학습 설정과 체크포인트 상태

유한한 검증 손실이 가장 낮은 저장 모델을 best로 선택합니다.
실물 성공률 기준 best는 아니며, 모든 단계별 체크포인트를 보존합니다.
학습 완료 후 실제 로봇에서 조건별 성공률을 따로 평가해야 합니다.

## 전송

`transfer_manifest.json`에 데이터셋 전체 파일 크기·SHA-256을 기록합니다.
서버 검증 성공 시에만 `TRANSFER_VERIFIED.json`을 생성해 학습을 허용합니다.
수집 백업·삭제 원본·recovery_snapshot은 전송하지 않습니다.

## 완료 결과와 로컬 실행

본 학습은 50,000 step까지 완료됐습니다. 최저 검증 손실 best는 46,000 step,
검증 손실 0.15885090827941895입니다.
서버 출력은 `/NHNHOME/workspace/lerobot/outputs/act_sorting_basic_20261023_215050_815728/`입니다.

로컬 실행은 프로젝트의 `sorting_B200_act/run.py`를 사용합니다.
모델·processor·통계·분할을 서버 원본과 SHA-256 비교했고,
로컬 RTX 3080에서 장비 미연결 strict 로딩과 검증 10개·30시점 표본 추론을 통과했습니다.
실제 로봇 성공률은 아직 측정하지 않았습니다.

초기 검사에서 발견한 자식 프로세스 중복 실행 문제는 `smoke_test.py`와
`pipeline.py`의 실행 진입점 보호로 수정했습니다. 자식 프로세스 import 검사와
10-step 학습·검증·best 저장 검사를 통과한 뒤 본 학습을 실행했습니다.

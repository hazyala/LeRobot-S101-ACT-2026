# Sorting B200 best 모델 로컬 실행

## 실행

VS Code에서 `sorting_B200_act/run.py`를 열고 Run Python File 버튼을 누릅니다.
프로젝트 가상환경 `D:/lerobot-2026/.venv/Scripts/python.exe`로 자동 전환합니다.
모델·정규화·데이터 메타정보·보정 파일 확인 후 Follower와 TOP/SIDE RGB 카메라에 연결합니다.
미리보기 창에 초점을 두고 로봇이 HOME 근처에 있을 때 SPACE를 누르면 동작합니다.

- SPACE: 시작 / 일시정지 후 재개
- P: 현재 자세에서 일시정지
- Q: HOME 복귀 후 종료
- E: 긴급 토크 해제
- 1회 실행, 최대 60초. 다시 시도하려면 프로그램을 재실행합니다.

인형·컵을 한 에피소드에서 연속 처리하는 sorting 정책입니다.
첫 물체를 놓았다고 별도의 HOME 복귀를 끼워 넣지 않습니다.
기존 실행기와 같이 HOME에서 벗어난 뒤 HOME으로 돌아와 2초 안정되면 종료합니다.
이는 로봇 자세에 따른 종료 조건이며, 두 물체가 올바르게 분류됐는지는 사람이 평가해야 합니다.

## 모델 및 입력

- B200 sorting 150개 전용 ACT, 단일 물체 데이터는 섞지 않았습니다.
- 학습 120개 / 검증 30개. 검증 손실 best는 46,000 step, 0.1588509083.
- 모델: `checkpoints/046000/pretrained_model/`
- 선택 기준과 분할: `best.json`, `split.json`
- 정규화: 체크포인트에 저장된 processor 사용
- 행동 범위: 학습 120개만의 `train_stats.json` 사용
- 입력: TOP/SIDE RGB 640x480 + 관절 6축. depth·부하·전류는 사용하지 않습니다.
- 로컬 데이터: `robot_datasets/tasks/sort_doll_cup/dataset` (150개, 184,183프레임)
- 현재 `collection/settings.json`의 포트·카메라·HOME 설정 사용

CUDA FP32, 30Hz 제어, 60프레임 재계획, 8프레임 전환 보간을 사용합니다.
기존 인형·컵 공통 실행기의 속도·관절 범위·추적오차·멈춤 감지를 유지합니다.
인형 전용 그리퍼 조기 닫힘 보정은 끕니다.
학습 시 카메라·작업대·물체 목적지 배치에 맞춰 사용합니다.

## 장비 없이 검사

`check_model.py`는 장비를 연결하지 않고 strict 모델 로딩과 저장 파일 SHA-256,
보정 파일·입출력·행동 범위를 확인합니다. 검증 30개 중 고르게 선택한 10개에서
각 3시점, 총 30개 관측을 추론합니다. 결과는 `model_check_result.json`에 기록합니다.
표본 추론 검사이며 전체 검증 재평가나 실제 sorting 성공률 측정은 아닙니다.

`run.py --preflight-only`도 장비를 연결하지 않고 모델·설정을 확인합니다.

## 파일 원본 및 학습 코드

서버 원본:
`/NHNHOME/workspace/lerobot/outputs/act_sorting_basic_20261023_215050_815728/`
모델·processor·선택 기록·통계·분할 총 10개 파일은 서버 원본의 SHA-256과 비교합니다.
큰 모델 파일은 Git 제외 대상입니다.

학습 실행 코드는 `SSH B200/sorting_basic/train.py`에 있습니다.
이 로컬 실행 준비 과정에서는 학습을 다시 시작하지 않습니다.

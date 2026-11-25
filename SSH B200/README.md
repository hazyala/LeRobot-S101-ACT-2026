# B200 서버 ACT 학습 코드

2026-10-19에 학습 서버의 `/NHNHOME/workspace/lerobot`에서 가져온 원본입니다.

- `train.py`: `experiments/act/doll_basic/train.py`의 학습 진입점
- `split.json`: 같은 폴더의 학습/검증 에피소드 분할
- `act-local-packages.txt`: `docs/`의 추가 패키지 기록
- `act-constraints.txt`: `docs/`의 PyTorch·TorchCodec 버전 제약

`train.py`와 `split.json`은 같은 폴더에 두어야 합니다. 기본 데이터·출력 경로는
서버의 `/NHNHOME/workspace/lerobot`을 기준으로 합니다. 실행 옵션은
`python train.py --help`로 확인합니다. 서버의 NVIDIA PyTorch와 직접 빌드한
TorchCodec을 사용한 환경 기록이므로 Windows에 패키지 목록을 그대로 설치하지 않습니다.

데이터셋, 가상환경, 빌드 파일, 체크포인트와 로그는 가져오지 않았습니다.
이번 동기화에서는 학습을 실행하지 않았습니다.

## 종이컵 본 학습

`paper_cup_basic/`은 종이컵 ACT 본 학습과 best 선택 코드입니다. SSH 서버에서 해당 `train.py`를 실행 버튼으로 시작합니다. 위의 루트 `train.py`는 인형 학습 원본 기록입니다. 종이컵 모델의 로컬 실행과 검사 기록은 저장소 최상위 `paper_cup_B200_act/`에 있습니다.

## Sorting 150개 전용 ACT

`sorting_basic/`은 기존 단일 물체 데이터를 섞지 않는 sorting 학습 코드입니다.
조건별 학습 120개·검증 30개를 고정하고, 기존 컵 ACT 설정과 최저 검증 손실 best 선택 방식을 사용합니다.
`pipeline.py`는 전체 전송 해시 확인 → 짧은 학습·best 저장 검사 → 본 학습 순서로 진행합니다.
서버 tmux 세션은 `sorting_act_150`이며, 실제 진행 상태는 서버의 `pipeline_status.json`에서 확인합니다.
상세 설정과 경로는 [sorting_basic/README.md](sorting_basic/README.md)에 있습니다.

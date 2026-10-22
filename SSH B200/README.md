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

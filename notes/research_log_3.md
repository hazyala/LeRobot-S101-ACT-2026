# LeRobot SO-101 Research Log 3 — B200 서버 환경 및 ACT 학습

## 2026-10-12~13 : 서버 연결, 환경 구축, 인형 ACT 공식 파이프라인 준비

기준: 사용자가 서버 터미널에서 실행해 공유한 결과, 로컬 데이터·수집 기록·학습 코드 확인 결과. 명령은 사용자가 직접 실행했다. 기존 로컬 Python 환경은 유지했으며 비밀번호와 개인키 내용은 기록하지 않는다.

### 1. SSH 연결과 서버 확인

Windows VS Code의 Microsoft Remote - SSH 확장에서 SSH 호스트를 등록했다. 개인키는 프로젝트 밖의 사용자 `.ssh` 폴더에 보관하고, SSH 설정에 키 경로·서버 주소·지정 SSH 포트·사용자 ID를 등록했다. 이후 원격 Linux 창과 터미널로 작업했다. 접속 시 비밀번호 입력은 없었으나 인증 로그까지 확인한 것은 아니다.

`whoami`, `hostname`, `uname -s`, `nvidia-smi`로 사용자 `jungsu`, 호스트 `kbj00-robot`, Linux, NVIDIA B200 1개를 확인했다. 접속 안내에는 Clunix Container Terminal이 표시됐다. 추가 오픈 포트 4개는 이번 학습에 사용하지 않았다.

| 항목 | 실제 확인 결과 |
|---|---|
| Python | 3.12.3, 기본 실행 파일 `/usr/bin/python3` |
| PyTorch | `2.10.0a0+b4e4ee81d3.nv25.12` — NVIDIA 빌드 |
| torchvision | `0.25.0a0+ca221243` |
| CUDA Toolkit | 13.1.80 (`nvcc`) |
| PyTorch CUDA | 13.1 |
| 드라이버 | 580.95.05 |
| GPU | NVIDIA B200, 표시 메모리 183,359 MiB |

`nvidia-smi`의 CUDA 표시는 13.0이었다. Toolkit과 PyTorch CUDA의 13.1 표시는 별도로 확인했으며 GPU 순전파·역전파도 통과했다. 드라이버와 Toolkit을 교체하지 않았다.

### 2. ACT 환경 구축과 TorchCodec 해결

일반 `lerobot[training]==0.6.1` 구성을 기준으로 의존성을 검토했다. torch·torchvision의 NVIDIA 버전을 constraints로 고정했다. 시스템 Python은 PEP 668 보호 때문에 단독 `--dry-run`을 차단했으며, 시스템 pip 25.3에서 `--dry-run --report`를 함께 사용해 설치 없이 해결 계획을 확인했다. 기존 torch·torchvision은 유지되는 계획이었다.

`--system-site-packages` 가상환경을 만들어 기존 NVIDIA PyTorch를 공유하고, 추가 의존성은 가상환경 안에 설치했다. 이 환경은 추가 패키지를 분리하지만 시스템 Python 패키지는 공유한다.

| 주요 패키지 | 확인된 버전 |
|---|---|
| LeRobot | 0.6.1, training extra |
| datasets / huggingface-hub | 4.8.5 / 1.33.0 |
| PyAV / accelerate | 15.1.0 / 1.15.0 |
| OpenCV headless | 4.13.0.92 |
| NumPy / Pillow / pyarrow | 2.1.0 / 12.0.0 / 22.0.0 |
| 최종 TorchCodec | 패키지 버전 `0.10.0a0`, import 버전 `0.10.0a0+0b261b9` |

배포된 TorchCodec 0.10.0은 FFmpeg 6용 라이브러리에서 PyTorch 내부 심볼을 찾지 못해 import에 실패했다. FFmpeg 실행용 라이브러리는 있었지만 개발 파일은 없었다. 개발 패키지를 관리자 설치하지 않고 `.deb`로 다운로드·압축 해제한 후 홈 폴더의 헤더·pkg-config 경로와 시스템 공유 라이브러리 링크를 맞췄다. 준비한 개발 파일은 avcodec, avformat, avutil, swscale, swresample, avdevice, avfilter, postproc이다.

TorchCodec 공식 `v0.10.0` 소스를 현재 NVIDIA PyTorch에 맞춰 CPU 디코딩용으로 빌드했다. `--no-build-isolation --no-deps`로 별도 torch 설치를 막고 wheel을 생성한 뒤 가상환경의 TorchCodec만 교체했다. wheel SHA-256은 `22aa98f26e8ecc9b8fff662645283926faa3699ea67d633b308eeba9b8351401`이다. VideoDecoder import와 LeRobot 기본 백엔드 `torchcodec`을 확인했다. ACT 모델 계산은 B200 GPU에서 수행한다.

`pip check`에는 설치 전부터 존재한 `yt-dlp 2024.4.9 → websockets>=12.0` 불일치만 남았다. 현재 websockets는 10.4이며 이번 작업에서 수정하지 않았다.

### 3. workspace로 작업 위치 통일

홈 폴더는 overlay 200 GiB여서 인형 데이터 230.53 GiB를 담을 수 없었다. `/NHNHOME/workspace`는 별도 Lustre 저장소로 약 4.9 TiB 여유 공간과 계정 쓰기 권한을 확인했다. `/workspace`는 별도 링크가 아닌 overlay의 일반 폴더로, 같은 200 GiB 제한이므로 사용하지 않았다.

가상환경은 절대 경로를 포함하므로 폴더를 단순 이동하지 않았다. 홈 환경의 로컬 패키지 목록을 기록하고 workspace에서 같은 환경을 재구성했으며, 빌드한 TorchCodec wheel을 재사용했다. ACT·공식 trainer·TorchCodec import 및 GPU 역전파를 확인한 후 홈의 `/home/jungsu/lerobot`을 삭제했다. 삭제 전 소스·FFmpeg 개발 자료를 압축 보관했다. 시스템 PyTorch·CUDA 및 다른 홈 파일은 유지했다. ResNet 가중치 캐시는 이후 `~/.cache/torch`에 생성됐다.

```text
/NHNHOME/workspace/lerobot/
├── lerobot-act/                         # 최종 가상환경
├── build/wheels/                        # TorchCodec wheel
├── build/source-archives/               # 소스·개발 파일 보관본
├── docs/act-local-packages.txt          # 가상환경 추가 패키지 목록
├── docs/act-constraints.txt             # 기존 핵심 패키지 고정 버전
├── datasets/doll/dataset/               # 인형 데이터
├── experiments/act/doll_basic/
│   ├── train.py
│   ├── split.json
│   └── train.py.bak_…                   # 수정 전 백업
└── outputs/                            # 모델·통계·분할·체크포인트
```

constraints는 이후 설치 명령에서 `--constraint`로 지정할 때만 적용된다. 학습 실행에는 필요하지 않다.

### 4. 인형 데이터 전송과 무결성 범위

로컬 `robot_datasets/tasks/pick_doll/dataset`의 `meta`, `data`, `videos`만 scp로 전송했다. 종이컵(`pick_paper_cup`), 다른 작업, 백업, 임시 폴더 및 `sessions`는 제외했다. Hugging Face Hub 업로드는 하지 않았으며 로컬 root 경로로 학습한다.

| 항목 | 서버 확인 결과 |
|---|---:|
| 전체 파일 | 2,498개 |
| meta / data / videos | 502 / 499 / 1,497개 |
| 전체 바이트 | 247,528,770,428 |
| 전체 크기 | 약 247.529 GB = 230.53 GiB |
| TOP / SIDE / TOP_DEPTH 영상 | 각각 499개 |
| 데이터 형식 / FPS | LeRobot v3.0 / 30 |
| 에피소드 / 프레임 | 499 / 291,869 |

로컬 파일별 상대 경로·바이트 수 manifest와 서버를 비교한 결과 누락·추가·크기 불일치 모두 0개, 빈 파일 0개였다. 전체 파일 해시 비교는 하지 않았다.

공식 LeRobotDataset 로더로 샘플 0, 145934, 291868을 읽었다. 관절·행동은 `(6,)`, TOP/SIDE는 `(3,480,640)`, depth는 `(1,480,640)`이며 검사한 값은 모두 유한했다. RGB는 TorchCodec, depth는 공식 depth 처리 경로로 읽는다. 전체 영상의 모든 프레임을 무결성 검사한 것은 아니다.

### 5. 공식 파이프라인 및 두 실험의 정의

ACT는 공식 모델 `ACTPolicy`와 `ACTConfig`, 학습은 공식 `lerobot.scripts.lerobot_train.train()`을 사용한다. 공식 로더가 미래 행동 100프레임과 에피소드 끝 padding을 구성하고, 공식 전처리·sampler·optimizer·gradient clipping·체크포인트를 사용한다. v2의 자체 학습 루프·그리퍼 주변 샘플링·조명 증강·선택 점수는 적용하지 않았다.

기존 성공한 100개 에피소드 실험(`episode_sample_dataset/doll_pickplace_act/train_act.py`)도 공식 train()을 호출했다. 기존은 100개/56,768프레임 전체 학습, 배치 4, 20,000단계, AMP 사용이었다. 현재는 499개 데이터, 학습/검증 분리와 학습 전용 통계를 추가하고 서버에서 검증한 FP32 설정을 사용한다.

계획된 두 모델은 별도 학습 파일·출력·체크포인트로 관리한다. **두 모델 모두 관절 위치 6축을 포함**하며, 차이는 모터 부하 입력 유무다. `research.motor_load_raw`는 별도 6축 값으로 실제 Parquet 저장을 확인했다. 모터 전류와 다르며 N·m로 환산된 토크가 아니다. 현재 준비한 `doll_basic`은 부하 제외 구성이고, 부하 포함 모델은 아직 구현·검증하지 않았다.

### 6. 분할과 정규화 수정

공식 `eval_split=0.1`만 사용하면 작업별 마지막 50개가 검증에 배정되므로 이를 대체했다. 로컬 `sessions`의 실제 13개 기록 그룹(서 있는/누운/혼합 자세 및 섹션 묶음) 안에서 순서를 유지하고 약 10개씩 구간을 나눠 하나를 seed 1000으로 선택했다. 총 학습 449개, 검증 50개이며 `split.json`으로 고정했다. 개별 섹션 번호를 임의로 추정하지 않고 기록된 섹션 묶음을 사용했다.

학습 에피소드의 저장된 개별 통계를 공식 `aggregate_stats`로 합산하고, 학습·검증 로더 양쪽에 동일한 학습 전용 통계를 전달했다. 현재 RGB도 학습 데이터 통계를 사용하도록 `use_imagenet_stats=False`로 지정했다. 원본 `meta/stats.json`은 변경하지 않았다. 분할 함수 연결은 실행 프로세스 안에서만 바꾸며 설치된 LeRobot 파일은 수정하지 않았다.

공식 설정 검사를 통과하도록 `eval_split=0.1`을 명시하되, 실제 데이터 선택은 고정 목록을 사용한다. `--check-config`에서 분할 및 통계 검사를 통과했다. 관절 표준편차는 약 `[36.1723,51.1642,45.0530,41.2708,25.3400,11.1813]`, 행동은 `[36.2338,50.6803,45.5416,41.4151,25.6582,11.6388]`이었다.

### 7. 동작 검증과 속도 문제 해결 범위

1. 공식 trainer 설정에 존재하지 않는 `eval_freq`를 넣은 오류를 제거했다. 설정 생성 단계에서 중단됐으므로 학습은 없었다.
2. 터미널 heredoc 실행에 작업자 2를 사용하면 spawn이 `<stdin>` 파일을 찾지 못했다. 작업자 0으로 전체 데이터 10단계 학습과 체크포인트 저장을 완료했다.
3. 분할·통계를 연결한 뒤 `eval_steps>0`이 요구하는 `eval_split` 누락을 수정했다.
4. 수정된 분할로 배치 2·작업자 0에서 10단계 학습은 약 8초에 끝났으나, 검증 29,262프레임 전체 읽기가 오래 걸렸다. 당시 CPU 평균 약 789%, GPU 메모리 약 2.5 GiB였다. GPU 사용률 0% 한 번의 측정으로 정지 여부를 판정하지 않았다.
5. 사용자 선택에 따라 depth 읽기는 유지하고 작업자 수만 4로 변경했다. 첫 배치 준비 약 12초 후 미리 읽은 배치에서 `data_s≈0.001초`였다. 10개 배치만으로 장기 처리량을 확정하지 않았다.
6. 2026-10-13 15:16:55, 전체 검증 `eval_loss=0.7549`, 10단계 체크포인트 저장, `End of training`을 확인했다. 전체 약 5분 19초였으며 대부분 검증 시간이었다.

마지막 검증 결과는 `outputs/act_doll_basic_workers4`에 있다. `0.7549`는 동작 검증 결과이지 파지 성공률이 아니다. ACT 학습/평가 경로가 달라 학습 loss와 검증 loss의 절대값을 직접 같은 의미로 비교하지 않는다. 체크포인트 재로딩·재개 및 실로봇 평가는 아직 확인하지 않았다.

현재 모델 입력에서는 depth가 제외되지만 공식 로더는 depth 영상도 읽는다. 이는 알려진 비용이며 이번 단계에서는 제거하지 않았다. CPU 디코딩 병렬화는 적용됐으나 B200을 최대로 활용하는 배치·정밀도·작업자 수의 최적값은 아직 측정하지 않았다.

### 8. 본 학습 실행 구성과 현재 상태

서버 파일 `experiments/act/doll_basic/train.py`에 실행 버튼용 기본값을 넣었다. VS Code 원격 창에 Microsoft Python 확장을 설치하고 인터프리터를 `/NHNHOME/workspace/lerobot/lerobot-act/bin/python`으로 선택한 뒤 **Run Python File in Terminal**로 실행하는 방식이다.

| 항목 | 현재 본 학습 기본값 |
|---|---|
| 입력 / 출력 | TOP/SIDE RGB + 관절 위치 6축 / action 6축 × 100프레임 |
| 제외 모델 입력 | 모터 부하, 전류, depth |
| 데이터 분할 | 449개 train / 50개 validation, 고정 목록 |
| 모델 | 공식 ACT, ImageNet ResNet-18, CVAE |
| 정밀도 / 장치 | use_amp=False / CUDA B200 |
| steps / batch / workers | 50,000 / 2 / 4 |
| seed | 1000 |
| 로그 / 평가 / 저장 | 100 / 1,000 / 1,000단계 |
| 업로드 | WandB 및 모델 Hub 업로드 비활성화 |
| 결과 | `/NHNHOME/workspace/lerobot/outputs/act_doll_basic` |

코드 실행 시 공식 ACT optimizer preset을 사용한다. 결과 폴더가 이미 있으면 중단하며 덮어쓰지 않는다. 학습 결과에 `split.json`, `train_stats.json` 및 공식 체크포인트를 보존한다. 현재 래퍼에는 재개 옵션이 연결되어 있지 않고 VS Code 터미널 실행은 SSH 종료 후 지속 실행을 보장하지 않는다.

**본 학습 실행 준비와 사용자가 공유한 최종 코드 설정은 확인했다. 50,000단계 본 학습의 실제 시작 로그·진행·완료 로그는 아직 공유되지 않았다.** 완료된 것으로 확인한 실행은 위 10단계 검증이다. 검증 1회가 약 5분이었던 결과를 기준으로 하면 50회 평가만 약 4시간이 추가될 수 있으나, 이는 동일 속도 가정의 추정이며 본 학습 전체 ETA는 아니다.

### 2026-10-14 : RealSense 교체 반영

연결된 장치를 실제 열거해 D405 시리얼 `262422273645`를 확인했다. 기존 실행 설정은 `352122273503`이었다. `collection/settings.json`을 새 시리얼로 수정하고, 자동/수동 수집 및 노출 검사 코드의 하드코딩을 해당 설정 참조로 변경했다. `run_selected.py`, `run_act.py`, 카메라 진단 및 현재 수집기는 이미 설정을 참조하므로 함께 반영된다. 과거 dataset·sessions·환경 보고서는 당시 장비 기록으로 유지했다.

새 시리얼로 카메라만 검사한 결과 RGB 단독과 RGB+depth 모두 640×480 스트림 수신에 성공했다. 로봇·모터 연결 및 USB 리셋은 수행하지 않았다. 수정한 Python 파일의 문법 검사도 통과했다.

### 공식 출처

- 학습: https://github.com/huggingface/lerobot/blob/v0.6.1/src/lerobot/scripts/lerobot_train.py
- ACT: https://github.com/huggingface/lerobot/blob/v0.6.1/src/lerobot/policies/act/modeling_act.py
- 데이터 구성/분할: https://github.com/huggingface/lerobot/blob/v0.6.1/src/lerobot/datasets/factory.py
- 영상 읽기: https://github.com/huggingface/lerobot/blob/v0.6.1/src/lerobot/datasets/dataset_reader.py
- TorchCodec 소스 빌드: https://github.com/pytorch/torchcodec/tree/v0.10.0

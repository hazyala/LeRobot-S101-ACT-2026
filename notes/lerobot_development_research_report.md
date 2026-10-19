# SO-101 LeRobot 모방학습 개발 과정 연구 보고서

## 논문·자료 학습에서 인형 ACT 실물 성공까지: 관찰, 실패, 진단, 수정, 검증의 기록

작성 기준일: 2026-10-15, 한국 시간. 대상 작업 공간: `D:\lerobot-2026`.

**프로젝트 범위:** 이 문서는 김해민이 Codex와 함께 진행한 SO-101 LeRobot 모방학습 개인 개발·실험 과정만 다룬다.

이 문서는 이력서 문안을 대신 쓰는 문서가 아니다. 이후 이력서·포트폴리오·면접 답변을 만들 때, 어떤 문제를 어떤 근거로 해결했는지 찾아볼 수 있는 개발 과정 원장이다. 핵심은 모델 파일의 존재보다 **관찰한 결과 → 원인 후보 → 확인 방법 → 수정 이유 → 재검증 → 남은 한계**다.

## 0. 이 문서의 근거와 읽는 방법

### 0.1 복원 범위

다음 자료를 교차 확인했다.

- 환경 기록, 세 편의 연구 로그, 초기 실험 폐기 전 분석 문서.
- 현재 수집기·품질 검사기·수동 및 자동 수집기·학습 및 실행 코드.
- 로컬 LeRobot 소스의 실제 변경 사항, 보정 JSON, 데이터 메타정보, 측정 보고서.
- 100시연 ACT 학습·평가·실행 분석 보고서, B200 체크포인트 감사 및 선택 결과.
- 이전 채팅 「B200에서 LeRobot ACT 학습 준비」 및 「실행 코드 표준 파이프라인 구성」의 사용자 실행 로그와 답변.
- 사용자가 직접 제공한 위키독스 칼리브레이션 자료, 공식 ACT/LeRobot 자료.
- 지원 회사 홈페이지는 지원 맥락을 확인하는 용도로만 참고했다.

확인한 범위에서 최대한 상세하게 복원했다. 저장되지 않은 모든 대화·터미널 명령·하드웨어 조작까지 완전히 재현했다는 뜻은 아니다. 논문을 처음 읽은 날짜, 페이지별 개인 분석 노트, 일부 초기 장비 조작, 삭제된 자체 실험의 전체 코드는 확인 범위에 한계가 있다. 그러한 빈칸을 그럴듯한 경험으로 채우지 않았다.

### 0.2 근거 수준

| 표기 | 의미 | 사례 |
|---|---|---|
| 직접 확인 | 현재 파일·설정·측정 결과로 확인 | 047000 선택, 50개 번호 체크포인트, 최종 batch 64 |
| 당시 기록 | 연구 로그 또는 과거 대화에 남음 | 20회 Ping, 초기 전압 측정, 서버에서 실행한 명령 |
| 사용자 확인 | 사용자가 결과를 직접 설명 | B200 인형 실험의 실물 성공 |
| 해석·가설 | 관측에서 도출한 설명으로 추가 실험 필요 | 해상도 축소가 객체 추적 저하에 기여했을 가능성 |
| 미확인·미완료 | 근거가 없거나 계획에 머묾 | 미실시 VLA 학습, 독립 실물 성공률, v2 본 학습 |

본문 명령은 **당시 기록 명령**, **현재 코드에 맞춘 재현 명령**, **개념 설명용 의사코드**를 구분한다. 명령을 문서에 기재한 것이 이번 문서 작성 중 장비·학습을 다시 실행했다는 뜻은 아니다. 이번 작업에서는 로봇을 움직이거나 재학습하지 않았다.

### 0.3 시점이 다른 기록을 읽는 원칙

`environment.md`의 “ACT 아직 안 함”, `research_log_3.md`의 “본 학습 완료 로그 미공유”, 실행 README의 “실물 미실행”은 각 문서를 작성했을 당시 상태다. 이후의 체크포인트 감사와 사용자 성공 확인을 함께 봐야 한다.

최종 상태는 다음처럼 정리된다.

1. 100시연 ACT는 RTX 3080에서 20,000단계까지 완료했고 성공 영상에 대한 당시 분석이 있다.
2. 499시연 자체 v1은 오프라인 지표를 확보했으나 실물 객체 추적 저하가 보고됐다.
3. v2는 AMP 문제 수정·작은 검증까지 진행했으며 본 학습 완료 실험은 아니다.
4. B200 공식 학습은 실제 저장 결과 기준 50,000단계, batch 64, workers 7이다.
5. 동일 검증 관측으로 비교해 047000을 선택했고 사용자가 B200 실험 성공을 확인했다.
6. 성공 횟수·전체 시도 수를 기록한 실물 평가표가 없어 성공률 백분율은 산출하지 않는다.

### 0.4 목차

1. 연구 질문과 개발 방향
2. 자료 탐색과 ACT 구조 이해
3. Windows 개발환경 구축
4. 모터·전원·통신·보정·텔레오퍼레이션
5. 카메라와 관측 설계
6. 수동 수집에서 HOME 자동 수집으로
7. depth 단위·영상 저장·무결성 문제
8. 본 수집기와 품질·성능 개선
9. 100시연 ACT 학습과 실물 분석
10. 499시연 v1·v2 실험과 실패에서 얻은 판단
11. B200 서버 환경·전송·학습 개선
12. 체크포인트 감사·선택·실행·카메라 교체
13. 성공을 만든 과정의 해석과 한계
14. 후속 수집 개선과 현재 코드 구조
15. LeRobot 개발 역량과 프로젝트 범위
16. 시행착오 통합표·명령 목록·증거·출처

## 1. 연구 질문과 개발 방향

### 1.1 실제로 해결하려던 문제

사람이 SO-101 Leader 팔로 보여 준 인형 집기·운반·놓기 동작을 기록하고, Follower가 카메라와 자기 관절 상태를 보고 같은 작업을 수행하도록 만드는 것이 중심 과제였다.

개발 과정의 질문은 단계마다 달라졌다.

| 단계 | 질문 | 다음 단계로 넘어가기 위한 증거 |
|---|---|---|
| 환경 | 이 Python에서 로봇 SDK·영상·GPU가 모두 작동하는가? | 실행 경로·SDK import·실제 영상 Tensor·CUDA 확인 |
| 하드웨어 | 기대한 모터에 올바른 명령을 보내고 있는가? | 포트·ID·baudrate·전압·보정값·추종 확인 |
| 수집 | 보기 좋은 시연을 빠짐없이 다시 쓸 수 있는가? | 수치·영상 구간·프레임 수·시간·복구 검증 |
| 학습 | 기록이 ACT의 올바른 입력·정답으로 연결되는가? | feature·미래 chunk·정규화·smoke test·저장 |
| 평가 | loss 감소가 실제 집기와 연결되는가? | 오프라인 예측과 실물 행동을 분리해 분석 |
| 운영 | 저장·영상 읽기·원격 실행 병목은 어디인가? | 구간별 시간·프로세스·처리량·데이터 무결성 |

### 1.2 단계적으로 범위를 넓힌 이유

초기 로드맵은 SO-101 → ACT → 다중 작업 → SmolVLA → DOFBOT 확장이었다. 그러나 실제 수행에서는 먼저 단일 작업 ACT와 장비·수집·실행 경로를 안정화했다. 단일 작업에서도 전원, 보정, 영상 큐, 데이터 단위, 모델 선택, 제어 시점의 문제가 각각 발생했기 때문이다.

분류·상자 쌓기용 수집 선택지와 자연어 instruction은 준비했지만, 이것만으로 다중 작업 정책이나 언어 이해 모델을 완성했다고 보지 않는다. 실제 성공 근거는 인형 ACT 경로에 집중한다. 관련 로드맵은 [roadmap.md](roadmap.md)를 참고하되, 체크 표시보다 후속 실험 산출물을 우선한다.

## 2. 자료 탐색과 ACT 구조 이해

### 2.1 출처를 실제 장비와 코드로 연결한 방식

자료를 찾는 활동은 설치 절차 복사에서 끝나지 않았다. 설명을 실제 CLI 옵션, 장치 포트, 보정 JSON, 데이터 feature, 모델 설정과 대조했다.

| 학습 대상 | 확인한 자료 | 프로젝트에서 연결한 지점 |
|---|---|---|
| Leader/Follower 보정 | 사용자 제공 [위키독스 2.5 칼리브레이션](https://wikidocs.net/385994) | 중간 자세·가동 범위·ID·파일 저장·기존 보정 사용 |
| 보정 실습 | 위 페이지에 연결된 [실습 영상](https://www.youtube.com/watch?v=vDS5eLKd9lM) | 자세와 절차를 대조하는 보조 자료. 영상 자체의 상세 내용은 이번 조사에서 재검증하지 못함 |
| 로봇과 정책 연결 | [LeRobot SO-101 공식 문서](https://huggingface.co/docs/lerobot/so101), 설치된 v0.6.1 소스 | teleoperate, record, rollout의 실제 옵션 |
| ACT 원리 | [Zhao 외, Learning Fine-Grained Bimanual Manipulation with Low-Cost Hardware](https://tonyzhaozh.github.io/aloha/) | 여러 시점 영상·관절에서 미래 행동 묶음 예측 |
| 학습 구현 | [LeRobot ACT 문서](https://huggingface.co/docs/lerobot/act), 로컬 `ACTConfig`·`ACTPolicy` | 100행동 chunk, ResNet18, CVAE, 공식 trainer |
| 영상 디코딩 | [TorchCodec v0.10.0 소스](https://github.com/meta-pytorch/torchcodec/tree/v0.10.0) | NVIDIA PyTorch에 맞춘 서버 wheel 빌드 |

위키독스의 보정 자료를 참고했다는 사실은 사용자 제공 링크로 확인됐다. 반면 논문을 언제 어떤 순서로 몇 회 정독했는지에 대한 원본 기록은 없다. 아래 이론 설명은 **구현과 연결해 복원한 기술 분석**이며 과거에 작성한 논문 리뷰를 발견한 것처럼 서술하지 않는다.

### 2.2 ACT에서 이해해야 했던 구조

ACT는 한 번의 관측에서 행동 하나 대신 미래 행동 시퀀스를 예측한다. 이 프로젝트에서는 두 RGB 영상과 현재 6축 상태가 입력이고, 출력은 `100 × 6` 관절 목표다. 논문은 이러한 chunk 예측을 통해 모방학습의 장기 오차 누적 문제를 다룬다. 학습에는 CVAE를 사용하고 추론은 잠재값 `z=0`으로 수행한다. [원 논문 프로젝트 페이지](https://tonyzhaozh.github.io/aloha/)

실제로 사용한 설정은 논문의 모든 실험 설정을 복제한 것이 아니다. 로컬 checkpoint의 설정값으로 확인하면 ResNet18, 모델 폭 512, attention head 8개, Transformer encoder 4층/decoder 1층, latent 32, KL 가중치 10이다. 파라미터 수는 51,668,614개다. 일반 소개 자료의 다른 파라미터 수를 이 모델 수치로 옮겨 적지 않았다.

개념상 학습 흐름은 다음과 같다.

```text
현재 TOP/SIDE RGB + 현재 관절 상태
                     │
        영상 특징·관절 특징·학습 중 잠재변수
                     │
              ACT Transformer
                     │
       미래 100시점 × 6축 절대 목표
                     │
       행동 재구성 오차 + KL 관련 항
```

정확한 padding·손실 집계·train/eval 동작은 사용한 [로컬 공식 ACT 구현](../lerobot/src/lerobot/policies/act/modeling_act.py)을 기준으로 한다. 학습 loss와 `z=0` 추론 오차를 동일한 수치로 취급하지 않는다.

### 2.3 이론에서 실험 판단으로 이어진 부분

- **관절값도 입력해야 한다.** 영상만으로 현재 로봇 자세를 추측하게 하지 않고 `observation.state` 6축을 전달했다.
- **행동은 즉시 송신할 단일 좌표가 아니다.** 100프레임 계획을 언제 새 관측으로 갱신할지 별도 실행 로직이 필요했다.
- **학습 데이터 시각과 실행 속도가 연결된다.** 30 FPS로 학습한 chunk 100은 명목상 약 3.33초다. FPS 숫자를 바꾸면 계획의 시간 의미도 달라진다.
- **depth를 저장했다고 RGB ACT가 자동 사용하지 않는다.** 별도 1채널 depth 입력을 모델에 넣는 설계 없이 RGB 정책의 성과라고 주장할 수 없다.
- **언어 문장 저장과 언어 조건 정책은 다르다.** 이 ACT checkpoint는 RGB·관절 입력이며 task 문장을 저장한 것만으로 VLA 학습이라고 하지 않는다.
- **논문에 있는 시간적 앙상블과 현재 실행기의 계획 혼합은 구분한다.** 저장 config의 `temporal_ensemble_coeff`는 null이며, 실제 사용 경로의 8프레임 crossfade를 논문 앙상블 구현이라고 바꿔 부르지 않는다.

## 3. Windows 개발환경 구축: 설치보다 실행 경로를 검증

주요 근거: [environment.md](environment.md), [실행 명령 기록](so101_run_commands.md), [환경 검증 스크립트](../scripts/verify_environment.py).

### 3.1 기준 환경

| 구성 | 기록된 값 |
|---|---|
| OS | Windows 11 |
| GPU | RTX 3080, VRAM 10,240 MiB |
| Python | 3.12.13, 프로젝트 `.venv` |
| uv | 0.10.8 |
| PyTorch | 2.11.0+cu130 |
| torchvision / torchaudio | 0.26.0+cu130 / 2.11.0+cu130 |
| LeRobot | v0.6.1, editable 설치 |
| LeRobot 기준 commit | `7e241bd630a3719a56157a497ce5d08f244784f1` |
| extras | training, core_scripts, feetech |
| Feetech SDK / pyserial | 1.0.0 / 3.5 |
| TorchCodec | 0.11.1+cpu |
| RealSense Python SDK | pyrealsense2 2.58.4 |
| 영상 | FFmpeg 7.1 shared 계열, PyAV·TorchCodec |

버전은 당시 성공 환경의 기록이다. 현재 날짜의 최신 조합 또는 모든 PC에 대한 권장 설치 조합을 뜻하지 않는다.

### 3.2 첫 실패: 설치했다는데 SDK를 못 찾음

**관찰.** `feetech-servo-sdk is required but not installed`가 발생했다. 프롬프트에 `(base)`와 프로젝트 환경이 겹쳐 있었고, `python`은 프로젝트 venv였지만 단독 `pip`는 Anaconda base에 설치했다. 프로젝트 venv에는 pip 자체가 없었다.

**진단.** 패키지를 다시 설치하기 전에 실행 파일과 설치 위치를 확인했다. 다음은 당시 기록된 확인 명령이다.

```powershell
python -c "import sys; print('PYTHON =', sys.executable); import pip; print('PIP =', pip.__file__)"
python -c "import scservo_sdk; print(scservo_sdk.__file__)"
```

**왜 바꿨나.** 설치 유무가 아니라 설치 대상 Python이 달랐다. 환경 이름만 믿으면 같은 장애를 반복하므로 인터프리터를 절대 경로로 지정했다.

```powershell
D:\lerobot-2026\.venv\Scripts\python.exe -m ensurepip --upgrade
uv pip install --python D:\lerobot-2026\.venv\Scripts\python.exe -e "D:\lerobot-2026\lerobot[feetech]"
```

Conda base 자동 활성화도 껐다. 수정 후 SDK가 프로젝트 `.venv\Lib\site-packages\scservo_sdk`에서 import되고 모터 스캔으로 이어지는지 확인했다. 이것은 Python 패키지 오류와 실제 시리얼 통신 오류를 분리하는 출발점이 됐다.

### 3.3 두 번째 실패: 최신 PyTorch가 LeRobot 의존성과 불일치

처음 설치된 `torch 2.14.0+cu130`은 LeRobot v0.6.1의 `torch>=2.7,<2.12.0` 범위를 벗어났다. GPU 모델만 보고 최신 패키지를 선택하는 대신, LeRobot이 허용하는 범위 안에서 torch·torchvision·torchaudio 버전을 함께 맞췄다.

또한 uv가 PyTorch index에 있는 오래된 `requests` 후보를 우선하면서 의존성 해결에 실패했다. 당시 기록에서는 PyPI와 CUDA index 후보를 함께 비교하도록 `--index-strategy unsafe-best-match`를 사용해 해결했다. 전체 최초 설치 명령은 남은 기록만으로 완전히 재구성하지 않고, 확인된 옵션과 확정 버전을 기록한다.

GPU 검증의 핵심은 다음과 같은 값이었다. 아래는 기록과 같은 항목을 확인하는 재현 명령이다.

```powershell
& D:\lerobot-2026\.venv\Scripts\python.exe -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
```

당시 `torch.cuda.is_available()`는 True이고 RTX 3080이 확인됐다. 로컬에서는 PyTorch가 포함한 CUDA runtime으로 필요한 연산을 수행했기 때문에 별도 CUDA Toolkit/nvcc를 설치하지 않았다. 서버의 소스 빌드 환경과 구분할 부분이다.

### 3.4 세 번째 실패: 영상 DLL을 찾지 못함

TorchCodec은 Python 패키지만 설치해도 끝나는 구성 요소가 아니었다. Windows에서 FFmpeg 공유 DLL을 찾아야 실제 영상을 읽을 수 있었다.

1. FFmpeg shared 빌드와 `avcodec-61.dll`, `avformat-61.dll`, `avutil-59.dll`을 확인했다.
2. 사용자 PATH에 DLL 폴더를 등록했다.
3. Python 3.12 프로세스에서 PATH만으로 부족한 경우를 처리하려고 `os.add_dll_directory(...)`를 환경 검사기에 넣었다.
4. import 성공뿐 아니라 실제 공개 영상 프레임을 읽어 검증했다.

TorchCodec의 CPU 표기는 영상 디코딩 백엔드의 성격이지 ACT가 CPU에서만 학습된다는 뜻이 아니다. 모델 연산은 CUDA에서 수행했다.

### 3.5 공개 데이터로 전체 경로를 먼저 검증

자체 시연을 모으기 전에 `lerobot/svla_so101_pickplace`를 공식 `LeRobotDataset`으로 읽었다.

| 항목 | 결과 |
|---|---|
| episode / frame | 50 / 11,939 |
| FPS | 30 |
| 영상 | `up`, `side`, 640×480 |
| 영상 Tensor | float32, `[3,480,640]` |
| state / action | 각각 6차원 |
| 샘플 확인 | 인덱스 0과 5969, 이미지 PNG 저장 |

이 검증은 “패키지 설치 성공”보다 강한 확인이었다. 데이터 다운로드, FFmpeg/TorchCodec, 영상 디코딩, Tensor 변환, 메타정보와 feature 해석이 함께 작동해야 성공하기 때문이다. 공개 데이터와 자체 데이터를 혼동하지 않도록 캐시를 `hf_pickplace_reference`, 자체 데이터를 별도 폴더로 분리했다.

```powershell
$env:HF_HOME = "D:\lerobot-2026\hf_pickplace_reference"
& D:\lerobot-2026\.venv\Scripts\python.exe D:\lerobot-2026\scripts\verify_environment.py
```

이 명령은 실제 데이터 로딩을 포함하는 환경 재검사다. 최초 자료 확보에 네트워크가 필요할 수 있으며, 모터 동작이나 모델 학습 명령은 아니다.

## 4. 하드웨어 세팅: 모터·전원·통신·보정을 순서대로 분리

주요 근거: [Research Log 1](research_log_1.md), [Follower 보정](../robot_calibration/robots/so_follower/follower.json), [Leader 보정](../robot_calibration/teleoperators/so_leader/leader.json).

### 4.1 포트와 모터 ID 확인

당시 확인된 매핑은 Leader `COM4`, Follower `COM3`이다. 다음 명령은 기록에 실제 남아 있다.

```powershell
python -c "from lerobot.motors.feetech import FeetechMotorsBus; print(FeetechMotorsBus.scan_port('COM3'))"
python -c "from lerobot.motors.feetech import FeetechMotorsBus; print(FeetechMotorsBus.scan_port('COM4'))"
```

9월 8일 연구 로그에는 양쪽 모두 다음 결과가 기록돼 있다.

```text
{1000000: [1, 2, 3, 4, 5, 6]}
```

baudrate 1,000,000에서 6개 ID가 응답한 것이다. 다만 초기 환경 메모에는 Follower가 `[1,2,3,4,5]`만 응답한 스캔도 남아 있다. 이 차이를 지워서 처음부터 항상 정상이었다고 쓰지 않는다. 후속 로그와 현재 보정 파일은 6개를 확인해 주지만, 초기 ID 6 미검출의 정확한 해결 조작은 남아 있지 않다.

| ID | 관절 | 확인해야 할 이유 |
|---|---|---|
| 1 | shoulder_pan | 기준 회전축 |
| 2 | shoulder_lift | 어깨 들림 |
| 3 | elbow_flex | 팔꿈치 굽힘 |
| 4 | wrist_flex | 손목 굽힘 |
| 5 | wrist_roll | 손목 회전 |
| 6 | gripper | 집게 |

ID를 읽었다는 사실과 새 ID를 써 넣었다는 사실은 다르다. 모터 ID 재설정 명령을 실행한 증거는 확인되지 않아 임의의 `setup-motors` 실행 이력을 추가하지 않았다.

### 4.2 전력 문제와 통신 문제를 함께 보되 섞지 않음

단순 포트 열기 성공만으로 전원 상태를 확신하지 않고, SDK로 모터 레지스터를 읽었다. 당시 기록 명령은 다음과 같다.

```powershell
python -c "from scservo_sdk import PortHandler, PacketHandler;
for port in ['COM3','COM4']:
    p=PortHandler(port);
    ok=p.openPort();
    p.setBaudRate(1000000);
    ph=PacketHandler(0);
    v,comm,err=ph.read1ByteTxRx(p,1,62);
    print(port, 'raw_voltage=', v, '=>', v/10, 'V', 'comm=', comm, 'error=', err);
    p.closePort()"
```

기록 결과는 Leader 5V, Follower 12V다. 이는 각 포트의 ID 1에서 읽은 전압 피드백이며, 전원 장치 전체의 부하 성능·전류 여유나 여섯 모터 모두의 전압을 측정했다는 뜻은 아니다. 통신 결과 `comm`, 장치 오류 `err`도 함께 출력한 것이 중요하다. 값만 읽고 정상이라고 판단하지 않기 위해서다.

### 4.3 CLI가 실제 하드웨어 타입을 지원하는지 확인

```powershell
lerobot-teleoperate --help
lerobot-teleoperate --teleop.type=so101_leader --robot.type=so101_follower --help
```

설명 자료의 명령을 무조건 복사하기보다 설치 버전에서 `so101_leader`, `so101_follower`, `port`, `id` 옵션을 확인했다. 위키독스 예제의 Linux `/dev/so101_*` 경로는 이 PC의 `COM4`·`COM3`로 대응시켜야 했다.

### 4.4 보정 절차를 실제 값으로 확인

사용자가 제공한 [위키독스 보정 자료](https://wikidocs.net/385994)는 중간 자세 설정 후 관절 범위를 기록하고, Leader/Follower의 ID를 이후에도 일관되게 사용하는 절차를 설명한다. 프로젝트는 이 절차를 실제 Windows 포트와 보정 파일에 연결했다.

당시 로그의 실행 진입점은 다음 teleoperate 명령이다. 필요 보정 절차를 거쳐 추종을 확인했다.

```powershell
lerobot-teleoperate --teleop.type=so101_leader --teleop.port=COM4 --teleop.id=leader --robot.type=so101_follower --robot.port=COM3 --robot.id=follower
```

저장된 실제 범위는 다음과 같다. 현재 JSON 기준으로 `id`, `drive_mode`, `homing_offset`, `range_min`, `range_max`가 보존돼 있다.

| 관절 | Leader min~max | Follower min~max |
|---|---:|---:|
| shoulder_pan | 672~3274 | 677~3423 |
| shoulder_lift | 853~3236 | 743~3348 |
| elbow_flex | 780~3149 | 682~3095 |
| wrist_flex | 956~3232 | 808~3175 |
| wrist_roll | 0~4095 | 0~4095 |
| gripper | 2030~3264 | 2031~3546 |

각 장치의 기구적 영점·가동 범위가 다르므로 raw 모터 수치가 같아야 하는 것은 아니다. 보정은 서로 다른 raw 값을 동일한 관절 의미로 다루기 위한 기반이다. 이 보정값을 다른 장비에 그대로 복사해서 사용하는 것은 프로젝트가 검증한 절차에 포함되지 않는다.

### 4.5 간헐적 패킷 오류: 고장 확정 전에 범위 좁히기

**현상.** `There is no status packet!`, `Incorrect status packet!`가 간헐적으로 발생했다. 5분 연속 추종은 가능했지만 shoulder_lift·wrist_flex 부근 오류가 관찰됐다.

**진단 결과.** 기록상 1~6번 개별 통신과 20회 연속 Ping은 정상이었다. 따라서 “특정 모터 완전 고장”으로 확정할 근거가 약했고, Follower 통신·USB·케이블·전원 연결을 점검할 필요가 있었다. Ping에 사용한 전체 반복 명령은 원본 기록이 없어 새로 만들어 당시 명령처럼 넣지 않았다.

**수정.** 읽기·쓰기 재시도와 상대 목표 제한을 적용했다.

```powershell
lerobot-teleoperate --teleop.type=so101_leader --teleop.port=COM4 --teleop.id=leader --robot.type=so101_follower --robot.port=COM3 --robot.id=follower --fps=30 --robot.num_read_retries=10 --robot.max_relative_target=5
```

현재 로컬 LeRobot에서는 configure 단계의 operating mode·PID·그리퍼 보호 설정과 `Goal_Position` 송신에도 `num_write_retries`를 전달하도록 변경돼 있다. [Follower 소스](../lerobot/src/lerobot/robots/so_follower/so_follower.py)에서 확인할 수 있다. 재시도는 일시적 오류에 대한 복구 수단이며 물리 원인을 제거했다는 증명은 아니다.

### 4.6 캐시 경로 변경이 보정 장애로 이어짐

9월 22일 캐시를 `hf_pickplace_reference`로 바꾼 뒤 기존 PowerShell의 `HF_HOME`은 옛 경로를 유지했다. 프로그램이 정상 보정 파일을 못 찾아 신규 보정 화면으로 들어갔고, 관절을 움직이지 않은 상태에서 전 관절 `MIN/POS/MAX=2047`이 나타났다.

여기서 중요한 판단은 **파일을 못 찾는 오류를 장비 재보정으로 해결하지 않은 것**이다. 값이 모두 같으면 정상 가동 범위 측정이 아니므로 사용하지 않았다. 이후 `c`를 입력해 재보정으로 진입한 사례도 있었지만 중간 자세 확인 전에 중단했다.

재발 방지 로직은 다음과 같다.

```text
프로젝트 고정 보정 경로 결정
→ JSON 존재·6관절·유효 min/max 검사
→ 대화형 재보정 없이 검증된 JSON 적용
→ 모터 내부 적용값과 파일 비교
→ 불일치하면 수집 시작 전 종료
```

Hugging Face 캐시와 장비 고유 보정값을 분리한 이유는 데이터 다운로드 경로 변경이 로봇 자세 해석까지 바꾸지 않게 하기 위해서다. 구현 근거는 [validate_calibration_files / connect_with_saved_calibration](../episode_sample_dataset/auto_home_collection/auto_home_record.py)다.

## 5. 카메라와 관측 설계

### 5.1 먼저 카메라 자체를 검사

RealSense SDK는 winget에서 원하는 별도 패키지를 찾지 못해 Python venv에 `pyrealsense2`를 설치하는 경로를 사용했다. D405의 장치명·serial·firmware·USB 정보를 열거하고 color/depth 수신을 확인했다.

현재 남은 [camera_test.py](../scripts/camera_test.py)는 RealSense 장치 선택, 요청 stream 시작, 실패 시 기본 stream 재시도, 일반 웹캠 검사 기능을 담고 있다. 초기 문서는 과거 파일명 `realsense_D405_test.py`를 가리키지만 현재 확인된 도구는 `camera_test.py`다. 과거 파일명을 현재 존재하는 명령처럼 그대로 안내하지 않는다.

당시 장치 기록은 D405 serial `352122273503`, firmware `5.15.1.55`, USB 3.2다. 10월 교체 장치의 serial은 다르므로 과거 firmware를 새 카메라 값이라고 쓰지 않는다.

### 5.2 TOP+FRONT에서 TOP+SIDE로

초기에는 TOP D405와 박스 입구 정면 웹캠이었다. 실제 시연을 보니 물체 높이, 그리퍼 접근, 파지, 내려놓기를 확인하는 데 측면이 유리해 웹캠을 SIDE로 바꿨다.

| 관측 | 역할 | 저장 feature |
|---|---|---|
| D405 TOP RGB | 작업대·물체 위치·전체 이동 | `observation.images.top` |
| Webcam SIDE RGB | 높이·그리퍼·파지·가림·안착 | `observation.images.side` |
| D405 TOP depth | 거리 정보 보존·후속 입력 연구 | `observation.images.top_depth` |

해상도는 640×480, 목표는 30 FPS다. 박스·베이스·카메라는 고정하고 시작 물체 위치를 바꾸는 방식으로 시연 다양성을 통제했다. 단순히 장면을 많이 찍는 대신 TOP과 SIDE 양쪽에서 물체가 보이는지, 과노출·가림이 없는지를 기준으로 배치를 정했다.

### 5.3 feature 이름까지 실제 의미와 맞춤

시야는 SIDE인데 파일 key가 `front`로 남아 있으면 이후 학습·실행 연결에 혼동이 생긴다. 기존 25시연에 대해 다음 전체 참조를 함께 변경했다.

- `info.json` feature.
- `stats.json` 통계.
- episode Parquet의 영상 참조 열.
- `videos/observation.images.front` 폴더.
- 수집 코드·문서.

변경 후 공식 로더로 25시연·13,647프레임, 처음과 마지막 SIDE 영상 shape `(3,480,640)`을 확인했다. 이름 변경을 단순 폴더 rename으로 끝내지 않고 메타정보·통계·실제 로딩까지 검증한 사례다.

## 6. 데이터 수집: 수동 5시연에서 HOME 자동 반복으로

주요 근거: [수동 수집기](../episode_sample_dataset/manual_data_collection/record_5_episodes.py), [수동 검증기](../episode_sample_dataset/manual_data_collection/validate_dataset.py), [자동 HOME 수집기](../episode_sample_dataset/auto_home_collection/auto_home_record.py), [Research Log 1](research_log_1.md).

### 6.1 작은 데이터로 먼저 수집 계약을 검증

첫 목표는 고정 박스에 물체를 넣는 성공 시연 5개였다. 시작 위치를 중앙·좌·우·가까운 곳·먼 곳으로 바꾸고, 접근 → 잡기 → 들기 → 이동 → 내려놓기 → 열기 → 팔 빼기의 흐름을 기록했다.

확인 대상은 영상이 재생되는지만이 아니었다.

1. episode가 실제 저장됐는가.
2. Follower 상태와 action이 모두 존재하는가.
3. 두 카메라가 같은 시연 구간을 나타내는가.
4. timestamp와 인덱스가 연속적인가.
5. 누락 프레임이 있는가.

이 단계의 목적은 수집 경로 검증이다. “5개로 성능을 입증했다” 또는 “계획된 5개 배치를 전부 동일하게 완료했다”로 확대하지 않는다. 당시 로그에는 구성과 확인 항목이 남아 있다.

### 6.2 반복 수집에서 발견한 사용성 문제

시연마다 키 입력과 저장 대기가 길면 물체를 놓고 Leader를 잡는 작업이 끊긴다. 저장 버튼 조작 자체가 시연의 시작·종료 품질을 흔들 수 있다. 이를 줄이기 위해 작업 종료 후 HOME 자세로 돌아오는 행동을 저장 신호로 사용했다.

초기 자동 흐름은 다음과 같이 발전했다.

```text
PREP 5초
→ START 1초
→ 기록
→ 시연 후 HOME 복귀
→ HOME 2초 유지
→ 저장·검증
→ 다음 PREP
```

실패하면 `f`로 폐기하고 10초 뒤 같은 번호로 재시도한다. `q`는 현재 미저장 버퍼를 버리고 종료한다. 수집기에는 최대 시연 시간 제한을 두지 않았고, 현재 본 수집의 최소 시연 시간은 8초다. 실행 정책의 60초 제한과 구분해야 한다.

### 6.3 HOME 감지의 오작동을 막는 조건

현재 [AutoHomeCycle](../collection/core.py)은 카메라·파일 저장과 분리된 상태기계다. 시작할 때 이미 HOME이므로 “HOME 2초”만 검사하면 아무 작업 없이 바로 저장될 수 있다. 이를 막기 위해 **HOME을 한 번 떠났는지**, **최소 시연 시간이 지났는지**, **복귀 후 안정 시간이 지났는지**를 함께 확인한다.

개념 설명용 의사코드:

```python
if command == "q":
    return "quit"
if recording and command == "f":
    discard_and_retry_same_number()
if left_home and elapsed >= 8 and home_stable >= 2:
    return "discard" if quality_failed else "save"
```

현재 코드에서는 같은 프레임에 HOME 완료와 `f`/`q`가 겹치면 종료·폐기를 우선한다. 저장 중에는 다음 기록을 시작하지 않는다. 이런 조건은 데이터 수집의 편의와 저장 일관성을 동시에 다룬다.

현재 HOME 기준은 shoulder_pan -5.8, shoulder_lift -99.3, elbow_flex 101.05, wrist_flex 74.86, gripper 1.32다. 팔 기준은 도, gripper는 정규화 단위다. 허용폭은 순서대로 12,12,12,18,20이며 wrist_roll은 이 HOME 판정 표에 포함되지 않는다. 반면 학습 state/action은 wrist_roll을 포함한 6축이다. HOME 판정 축 수와 모델 입력 축 수를 혼동하지 않는다.

### 6.4 파일럿 25시연에서 확보한 증거

9월 21일 기록은 25시연·13,647프레임, 평균 545.88프레임/약 18.2초였다. TOP·SIDE·depth 영상 75개의 프레임 수가 각 시연 길이와 일치했다.

저장량 분석에서는 전체 약 2.95GB 중 depth가 약 2.74GB로 영상 용량의 약 93%를 차지했다. 이 결과 때문에 데이터 목표를 “2TB 채우기”에서 “유효한 성공 시연·위치 다양성 확보”로 바꿨다. 저장 공간을 많이 사용하는 것과 학습 정보를 많이 확보하는 것은 같은 일이 아니었다.

## 7. 저장 파이프라인의 시행착오: 단위·큐·파일 구조

### 7.1 depth 값이 보인다고 단위가 맞는 것은 아님

D405 초기 장치의 depth scale은 0.0001m/unit, 즉 raw 1이 0.1mm였다. LeRobot encoder가 mm로 해석하는 입력에 raw를 그대로 보내면 거리 의미가 달라진다.

초기 수정:

```text
depth_mm = round(depth_raw × 0.1)
```

현재 일반화된 [convert_depth](../collection/quality.py)는 장치에서 실제 scale을 읽어 다음 계산을 한다.

```text
mm = round(raw × depth_scale_m × 1000)
0~2000 mm 범위 제한 → uint16
선형 12비트 코드 → HEVC gray12le 무손실 인코딩
```

**왜 수정했나.** 초기 장치의 scale을 상수로 기억하는 대신 교체 장치에서도 의미가 맞도록 장치 값을 사용하기 위해서다. 단위·범위·양자화 방식은 manifest에 기록한다.

중요한 한계는 세 가지다.

- 무손실은 변환된 코드/정수 mm 기준이다. 센서 raw의 0.1mm 정밀도를 전부 보존한다는 뜻이 아니다.
- 2m 초과 값은 제한되므로 원래 범위 밖 값은 복원되지 않는다.
- depth 0은 물체까지 거리 0m가 아니라 invalid 값이다.

일반 플레이어에서 depth가 이상하게 보인다는 이유만으로 데이터가 망가졌다고 판단하지 않았다. PyAV/공식 depth 경로로 실제 프레임 수·dtype·픽셀을 확인해야 했다.

### 7.2 종료 후 인코딩 대기 → 녹화 중 스트리밍 인코딩

기존에는 종료 후 프레임을 영상으로 만들면서 긴 대기가 생길 수 있었다. `streaming_encoding=True`로 RGB·depth를 녹화 중 인코딩하고, `save_episode(parallel_encoding=True)`를 백그라운드로 처리했다. 영구적인 임시 PNG 폴더와 종료 직후 일괄 인코딩 부담을 줄이기 위한 변경이다.

그러나 스트리밍으로 바꾸면 문제가 사라지는 것이 아니라 인코딩 처리량과 큐 압력 문제가 생긴다. 다음 실패가 그 사실을 보여 준다.

### 7.3 실제 depth 유실: 메타정보를 믿지 않고 디코딩

9월 22일 추가 수집 후 26~44번 시연 depth가 각각 3~11프레임 부족했다. 컨테이너 표시뿐 아니라 실제 디코딩 결과도 부족해 검사기의 착각이 아닌 실제 유실로 판단했다.

**원인.** `StreamingVideoEncoder`에서 depth HEVC 큐가 가득 찰 때 `queue.Full`로 프레임을 버리는 경로가 있었다.

**개선 순서와 이유.**

1. RGB를 NVENC로 옮겨 CPU 여유를 확보하려 했지만, 코덱 목록에는 보여도 `avcodec_open2`에서 실제 초기화가 실패했다.
2. 이 시점에는 GPU 경로에 의존하지 않고 RGB를 CPU H.264 `ultrafast`로 바꿨다.
3. 카메라별 큐를 60 → 300프레임으로 늘려 순간적인 지연 여유를 확보했다.
4. drop이 하나라도 감지되면 해당 시연을 정상 저장하지 않고 같은 번호로 재시도했다.
5. 장기 처리량 부족은 큰 큐만으로 해결되지 않으므로 저장 후 프레임 검사를 유지했다.

당시 사용자 확인 후 공식 `delete_episodes` 경로로 26~44번을 제외했다. 뒤의 정상 시연을 재인덱싱해 33시연·17,943프레임, 오류 0건으로 복구했다. CPU RGB+depth 동시 인코딩 작은 시험에서는 세 스트림 각각 3/3프레임을 확인했다. 3프레임 통과가 장시간 성능 검증은 아니라는 범위도 남긴다.

### 7.4 이번에는 검사기 오판: MP4 하나가 episode 하나라는 가정

복구 후 34~49번을 추가했는데, RGB MP4 전체 9,196프레임을 각 시연 길이와 비교해 오류가 발생했다.

조사 결과 복구 도구가 `video_files_size_in_mb`를 기본 200MB로 바꿔 여러 시연을 한 MP4에 저장했다. 각 episode의 `from_timestamp`·`to_timestamp`는 정확했다. 따라서 앞의 실제 유실과 달리 이번에는 검사 로직이 LeRobot 파일 패킹 구조를 잘못 가정한 것이었다.

수정한 검사 계약:

```text
episode 메타정보의 시작/끝 시각 → FPS 기준 frame 구간
→ 구간 길이와 episode length 비교
→ 공유 파일 내 구간의 겹침·간격 확인
→ 마지막 구간 끝과 실제 파일 frame 수 대조
```

이후 목표 파일 크기를 1MB로 복원하고, 미커밋 tail 642행과 임시 폴더 3개를 정리했다. 49시연·27,139프레임, 오류 0건과 경계 프레임 실제 로딩을 확인했다.

이 과정의 핵심은 “검사 실패면 데이터 삭제”가 아니었다. 저장된 구조를 먼저 읽고, 데이터가 틀린 것과 검사 가정이 틀린 것을 구분했다.

### 7.5 중단 후 재개가 데이터를 손상시키지 않게 함

새 수집 전에는 episode/frame 개수, 연속 인덱스, 영상 참조, depth 단위, 미커밋 꼬리를 확인했다. 불완전한 미커밋 꼬리는 정상 데이터와 분리하고, 이미 커밋된 데이터에 오류가 있으면 이어쓰기를 차단했다.

100시연에 도달하기 전에도 미커밋 tail 367행과 임시 폴더 3개를 정리한 기록이 있다. 정상 커밋 기준으로 100시연·56,768프레임, 오류 0건이 확인돼 학습으로 넘어갔다.

## 8. 본 수집기: 499시연을 모으기 위한 품질·속도 개선

주요 근거: [collection README](../collection/README.md), [core.py](../collection/core.py), [quality.py](../collection/quality.py), [Research Log 2](research_log_2.md).

### 8.1 작업을 고르고 이어 수집하는 구조

본 수집은 `collection/collect.py`의 창에서 작업을 고르는 구조로 확장했다. 인형·종이컵 집기, 인형/컵 분류, 2·3·4개 상자 쌓기 선택지가 있다. 작업별 저장 위치는 다음과 같다.

```text
robot_datasets/tasks/<task>/
├── dataset/
│   ├── meta/
│   ├── data/
│   └── videos/
├── collection_manifest.json
├── sessions/
└── 복구·검사 관련 파일
```

작업 문장·장비 설정·보정 hash·depth scale을 manifest에 남기고, 조건이 다른 데이터를 조용히 섞어 이어쓰지 않게 했다. 작업별 데이터셋의 `task_index=0`은 각 데이터셋 내부 인덱스라 정상이다.

GUI와 수집 worker를 분리하고 명령 전달·상태 알림을 연결했다. 카메라·수집 루프가 바쁘더라도 창의 시작·종료·실패 처리와 진행 상태를 별도로 다루기 위한 구조다. 실제 구현 범위는 [CollectionWindow / worker](../collection/collect.py)에서 확인할 수 있다.

### 8.2 데이터의 정답을 더 엄밀하게 정의

| feature | 저장 의미 | 모델 연결 시 주의 |
|---|---|---|
| `observation.state` | Follower 실제 6축 위치 | 팔 도·그리퍼 정규화 단위 |
| `action` | 이동량 제한 적용 후 실제 송신 목표 | Leader 원본과 다를 수 있음 |
| `research.leader_action_raw` | 제한·전처리 전 Leader 값 | 비교·원인 추적용 |
| `research.motor_load_raw` | 부호 해석한 6축 load | 실제 N·m 힘 측정 아님 |
| `research.motor_current_raw` | 6축 전류 피드백 원시값 | 물리 단위 환산과 구분 |
| `research.motor_torque_limit_raw` | 토크 제한 설정값 | 현재 발생 토크와 구분 |
| `research.capture_timing_s` | 호스트 수신·읽기·송신 시각 | 센서 노출 시각이 아님 |
| `research.camera_frame_numbers` | TOP 장치 번호·SIDE 호스트 순번 | 하드웨어 동기화 아님 |

**왜 action 정의를 바꿨나.** 사람이 Leader로 요구한 값이 안전 제한으로 잘렸다면 로봇이 실제 수행한 시연과 원본 Leader 목표가 달라진다. 학습 정답은 최종 전달 action으로 두고 원본을 별도 보존하면, 후속 분석에서 이 차이를 설명할 수 있다.

`research.*`를 기본 학습 feature와 분리한 이유도 같다. 저장했다고 자동으로 모든 입력을 모델에 넣지 않고, baseline과 모터 피드백 실험을 구분할 수 있도록 했다. 새 저장 계약은 schema version 4로 이전 계약과 혼합하지 않았다.

### 8.3 모터 피드백 추가가 수집 속도를 해치지 않게 함

위치·load·current·torque limit을 각각 읽으면 통신 왕복이 늘어난다. 로컬 Feetech bus에 `sync_read_registers`를 추가해 주소 48~70의 연속 23바이트를 모터별 한 번에 읽고 각 필드를 해석했다.

구현은 동일 레지스터 주소인지 확인하고, 완전한 응답인지 검사하고, 부호 해석과 위치 정규화를 적용한다. 읽기 실패를 가짜 0으로 채우지 않고 오류로 처리한다.

정지 상태 장비 측정 결과:

| 방식 | 평균 | 최대 |
|---|---:|---:|
| 4개 항목 분리 읽기 | 4.011ms | 4.277ms |
| 연속 블록 읽기 | 2.413ms | 2.534ms |

평균 읽기 시간은 약 39.8% 줄었다. 이 개선율은 모터 읽기 구간만의 수치이며 전체 수집 시간이 39.8% 빨라졌다는 뜻은 아니다. 근거: [motor_read_profile.json](../collection/reports/motor_read_profile.json).

검증에서는 부호 있는 load, 위치 정규화, 원시 전류, 토크 제한의 분해를 검사했다. 불완전 응답 재시도 후 오류도 확인한다. [test_motor_feedback.py](../collection/tests/test_motor_feedback.py)

### 8.4 22FPS 웹캠 때문에 정상 시연이 계속 폐기됨

초기 본 수집기는 매 제어 주기 TOP·SIDE 각각의 새 영상을 기다렸다. 웹캠 실제 공급이 약 22.2FPS라 전체 루프도 느려지고 최소 27FPS 기준을 통과하지 못해 시연이 반복 폐기됐다.

**분리한 두 현상.**

1. 인코더가 이미 수집한 프레임을 버림: 저장 누락, 정상 데이터로 쓰면 안 됨.
2. 30Hz 제어 시점에 새 SIDE 영상이 없어 최신 프레임을 재사용: 독립 장치 속도 차이, 따로 기록해야 함.

**수정.** 카메라별 background capture에서 최신 영상을 받아 제어 시계에 재표본화했다. 카메라 새 프레임 대기가 전체 모터 루프를 항상 제한하지 않도록 했다. 반복·건너뜀을 통계로 남기고, 오래된 영상·인코더 drop·시간 초과·저장 개수 불일치는 계속 실패 처리했다.

카메라와 Follower 읽기 90주기 측정은 다음과 같다.

| 측정 | 결과 |
|---|---:|
| 실제 루프 FPS | 29.9924 |
| SIDE 반복 | 24회 |
| 최대 TOP–SIDE 호스트 수신 차이 | 24.43ms |
| 모터 snapshot 평균 | 2.408ms |
| 품질 오류 | 0건 |

이 측정에는 모터 이동 명령·GUI·실시간 영상 인코딩을 포함하지 않았다. 전체 시연 30FPS 달성 결과로 과장하지 않는다. [capture_read_profile.json](../collection/reports/capture_read_profile.json)

### 8.5 실제 분포를 보고 시간차 기준을 조정

약 29.7FPS, 인코더 누락 0개인 시연도 TOP–SIDE 수신 차이 52~57ms 때문에 폐기됐다. 기존 50ms 허용값이 독립 카메라의 실제 변동에 비해 엄격한 것으로 판단해 100ms로 완화했다.

동시에 다음 기준은 유지했다.

| 항목 | 기준 |
|---|---:|
| 목표 수집 속도 | 30FPS |
| 실제 평균 최소 | 27FPS |
| 최대 프레임 간격 | 200ms |
| 최대 카메라 수신 차이 | 100ms |
| 전체 표본 시각 폭 | 150ms |
| 최대 프레임 나이 | 100ms |

이것은 카메라를 하드웨어 동기화한 작업이 아니다. 호스트 기준 품질 허용값을 실제 관측에 맞춘 것이다. 허용값 변경 시 이전 manifest를 보존해 어떤 기준으로 수집했는지 추적할 수 있게 했다.

### 8.6 저장할 때마다 모든 과거 데이터를 검사하는 병목

57개 시연이 있을 때 이전 시연 전체를 다시 검사하는 데만 11.219초가 걸렸다. 시연이 늘수록 매번 대기가 늘어나는 구조였다.

**수정 이유.** 이미 시작 때 검사한 과거 데이터와 방금 새로 저장한 데이터의 검증 범위를 분리하면, 검증 항목을 버리지 않고 중복 작업을 줄일 수 있었다.

- 수집 시작 때 전체 무결성 검사 유지.
- 저장 후 새 episode의 수치·인덱스·시간·작업 문장·메타 개수만 읽음.
- TOP·SIDE·depth 검사 병렬화.
- depth 변환 결과표 재사용.
- 저장·검사·재개 시간을 `save_seconds`로 분리 기록.

514프레임인 마지막 시연의 새 검사는 4.938초, 오류 0건이었다. 비교한 두 작업의 범위가 다르므로 “전체 저장 속도 56% 개선”으로 쓰지 않는다. 같은 347개 보호 파일의 SHA-256 비교에서 변경 0개를 확인해 최적화가 기존 데이터를 바꾸지 않았는지 점검했다. 당시 저장·복구·HEVC 검사를 포함한 테스트 41개 통과 기록도 있다.

### 8.7 웹캠 제한 원인을 코드 탓으로 단정하지 않음

10월 진단에서 카메라 단독 측정과 USB 포트 변경 후에도 공급률이 약 22.2FPS였다. 인형 499개·종이컵 102개 시간 기록의 약 22.23FPS와 SIDE 약 26% 반복도 같은 경향이었다. 장치·드라이버·영상 모드 중 정확한 원인은 확정하지 못했다.

또한 10월 7일 노출 진단에서 숫자만 원복하고 자동/수동 모드 복원 검증이 부족해 과노출이 발생했다. 자동 노출을 켜서 밝기를 복구하고 재연결 후 화면도 확인했다. 해당 인형·종이컵 데이터는 노출 진단 이전에 수집됐다.

이 사건에서 얻은 운영 기준은 설정의 숫자뿐 아니라 **모드와 실제 영상까지 복원 확인**하는 것이다. 기존 데이터의 FPS metadata만 22로 바꾸거나 전량 폐기하지 않았다. 모델 성공에 미친 영향은 별도 실험이 없기 때문이다.

## 9. 첫 ACT: 100시연 학습에서 실물 행동의 시간 구조 분석까지

주요 근거: [학습 코드](../episode_sample_dataset/doll_pickplace_act/train_act.py), [학습 보고서](../episode_sample_dataset/doll_pickplace_act/doll_pickplace_act_testreport/01_model_training.md), [평가 보고서](../episode_sample_dataset/doll_pickplace_act/doll_pickplace_act_testreport/02_model_evaluation.md), [실행 분석](../episode_sample_dataset/doll_pickplace_act/doll_pickplace_act_testreport/03_execution_analysis.md).

### 9.1 한 번의 작은 학습·저장부터 확인

수집 완료 직후 긴 학습부터 하지 않았다. 공식 `TrainPipelineConfig`, `ACTConfig`, `train()`을 연결하고 1단계 smoke test에서 GPU 업데이트와 checkpoint 저장을 확인했다.

당시 README에 남은 명령:

```powershell
& D:\lerobot-2026\.venv\Scripts\python.exe `
  D:\lerobot-2026\episode_sample_dataset\doll_pickplace_act\train_act.py `
  --steps 1 --save-freq 1 `
  --output-dir D:\lerobot-2026\episode_sample_dataset\doll_pickplace_act\outputs\smoke_test
```

본 학습은 같은 경로에서 `--steps 20000 --batch-size 4`로 진행했다. smoke test 결과 폴더가 남아 있으면 재사용 전 출력 경로를 새로 정해야 한다. 문서 작성 중 이 명령을 다시 실행한 것은 아니다.

### 9.2 입출력을 명시적으로 제한

100시연·56,768프레임, 총 명목 기록 시간 31분 32.27초를 사용했다. 원본 크기 12.751GB 중 depth가 11.536GB/90.47%였다.

모델 입력은 state 6축·TOP RGB·SIDE RGB다. depth는 데이터에 보존하되 RGB ACT 입력에서는 제외했다. action은 미래 100프레임의 6축 절대 목표다. 원본 데이터 크기 대부분이 depth이므로 “12.75GB 전부를 모델 영상 입력으로 썼다”는 설명은 틀리다.

설정은 batch 4, AMP, workers 2, 20,000단계, 2,000단계마다 저장, AdamW 1e-5다. 전체 100시연을 학습에 사용했고 별도 미사용 검증 세트는 없었다.

### 9.3 loss 감소 중 Windows symlink에서 중단

초기 속도 약 6.8step/s, GPU 메모리 약 2.13GB였고 loss는 step 200의 4.10에서 560의 2.88로 내려갔다. 그러나 2,000단계 저장 뒤 `checkpoints/last` directory symlink 권한 오류로 학습이 중단됐다.

**진단.** 모델 저장 자체가 실패했는지, 마지막 포인터만 실패했는지 분리했다. 번호 checkpoint `002000`에는 약 207MB 모델, 약 413MB optimizer, RNG·step 상태가 정상 저장돼 있었다.

**수정 이유.** 선택적 last 링크 때문에 이미 저장된 학습을 폐기할 필요가 없었다. 로컬 LeRobot의 `update_last_checkpoint`에서 Windows symlink 실패가 본 학습을 중단시키지 않게 처리했다. 구현은 [common/train_utils.py](../lerobot/src/lerobot/common/train_utils.py)에 남아 있다.

**재검증.** 002000에서 optimizer와 데이터 진행 상태를 포함해 재개했고 020000까지 완료했다. 당시 전체 재개 명령 문자열은 본문 자료에서 확인되지 않으므로 임의로 복원하지 않는다. 증거는 `train_resume_stderr.log`, 학습 보고서와 `training_step.json`이다.

### 9.4 학습 완료와 행동 품질을 분리

최종 training loss는 0.198이었다. 그러나 이것만으로 집기 성공을 판정하지 않았다. 학습에 포함된 12개 시연/1,200프레임에서 행동 예측을 확인한 결과:

| 항목 | 값 | 해석 |
|---|---:|---|
| 6축 평균 MAE | 4.981 | 팔 도·그리퍼 별도 단위가 섞인 요약값 |
| 행동 범위 이탈률 | 7.33% | 예측을 실제 송신 전에 제한할 근거 |
| 그리퍼 범위 이탈률 | 25.92% | 전체 평균으로 가려지는 축별 문제 |

이는 학습 데이터 내 검사다. 독립 test 성능이나 실물 성공률이 아니다. 그래서 모델 구조·곡선·관절별 오차·카메라 표본·100행동 예측을 [validate_act_model.ipynb](../episode_sample_dataset/doll_pickplace_act/validate_act_model.ipynb)로 확인하고 별도 실습 행동을 분석했다.

### 9.5 추론이 제어 루프를 멈추지 않도록 분리

[run_act_pickplace_safe.py](../episode_sample_dataset/doll_pickplace_act/run_act_pickplace_safe.py)는 현재 관측으로 100×6 chunk를 만들고, 모터 제어는 목표 30Hz로 이어가며 비동기 추론으로 기본 60제어프레임마다 계획을 갱신한다. 새 팔 계획의 첫 8프레임을 이전 계획과 혼합해 전환 급변을 완화한다.

왜 이 구조가 필요한가? 추론이 끝날 때까지 제어를 매번 막으면 모터 명령이 주기적으로 끊길 수 있고, 반대로 100행동을 관측 갱신 없이 전부 실행하면 물체가 움직이거나 첫 파지가 빗나가도 대응이 늦어진다. 비동기 재계획은 이 두 문제 사이에서 선택한 실행 설계다. 실제 30Hz 유지율은 당시 동기화된 실행 로그가 없어 확정하지 않는다.

### 9.6 “올라가면서 집는다”를 관절 데이터와 영상으로 분석

초기 실행기는 그리퍼 닫기 목표를 8프레임, 명목 약 0.267초 앞당겼다. 그렇지만 이는 팔을 멈추고 접촉을 확인하는 제어가 아니었다. 팔 목표와 그리퍼 목표는 같은 제어프레임에 계속 송신된다.

100시연 action에서 gripper가 15 이상으로 넘어가는 시점을 대리 기준으로 잡아 분석했다. 닫기 시작 후 10프레임 동안 팔 5축 목표 벡터 변화량 중앙값은 17.94°였고, 88/100시연이 5°를 넘었다. 따라서 시연 자체에도 닫기와 팔 움직임이 겹치는 경우가 많았다.

이 수치는 손끝 높이나 접촉력이 아니다. threshold 15도 실제 접촉 라벨이 아니다. 다만 “정지 → 파지 완료 확인 → 상승”이라는 독립 단계가 데이터·실행에 보장돼 있지 않다는 판단을 뒷받침했다.

당시 분석된 성공 영상 두 개에서는 첫 접근에 선 인형을 넘어뜨리고, 누운 인형을 재접근해 잡아 상자에 넣는 회복 행동이 보였다.

| 당시 영상 분석 | 첫 접근/넘어짐 | 재파지 | 상자 안착 |
|---|---|---|---|
| 성공 영상 1 | 약 6.5~7.4초 | 약 17.3초 | 약 23.2초 |
| 성공 영상 2 | 약 17.7~18.3초 | 약 32.3초 | 약 37.0초 |

이는 당시 보고서에 기록된 영상 분석이며 이번 작성 중 원본 영상을 새로 모두 판독한 결과는 아니다. 두 영상이 정확히 어느 코드 리비전인지 확인되지 않아 gripper 선행 수정 효과로 귀속하지 않는다. 성공 영상만으로 `2/2=100%`라고 계산하지도 않는다.

### 9.7 안전 제한도 행동을 바꾸므로 분석 대상

실제 송신 전에는 시연 action min/max, 프레임당 변화량, 현재 상태 대비 추종 제한을 적용했다. 팔이 아직 못 따라갔는데 목표만 누적되지 않도록 제한하고, 지속 stall·NaN/Inf·비정상 상태·추론 지연을 감시했다.

이것은 단순 부가 기능이 아니다. 모델 원시 예측과 최종 송신이 달라질 수 있으므로, 파지가 늦을 때 모델·보간·범위 제한·모터 추종 중 어디서 지연됐는지 함께 봐야 한다. 당시 보고서는 동기화 로그가 없어 단일 원인을 확정하지 않았다.

## 10. 499시연 실험 v1·v2: 실패를 다음 설계의 근거로 사용

주요 근거: 삭제 전에 작성한 [초기 실험 분석과 원본 코드 보존 문서](act_failed_experiments_review.md). 해당 실험 폴더 일부는 이미 삭제돼 현재 직접 다시 실행할 수 없다. 문서 안의 원본 코드·해시·당시 지표로 복원한다.

### 10.1 실험 계보를 정확하게 분리

| 실험 | 실제 확인 범위 | 판단 |
|---|---|---|
| 100시연 ACT | 공식 trainer, 20,000단계, 성공 영상 분석 | 첫 학습·실행 경로 |
| doll_pickplace_act_v1 | 자체 준비·학습·실행, 두 모델 046000 | 실물 객체 추적 저하 보고 |
| doll_pickplace_act_v2 | 수치 안정성 수정, 작은 업데이트·저장·재로딩 | 본 학습 미완료 |
| doll_pickplace_act_official | 빈 폴더 | 실패 원인 판단 불가 |
| doll_basic | B200 공식 학습 준비 래퍼·분할 | 성공 경로 준비 단계 |
| doll_B200_act | 50,000단계·선택 평가·실행 | 사용자 성공 확인 |

“초기 폴더 네 개를 버렸다”를 “네 종류 모델이 모두 파지에 실패했다”로 바꾸면 실제 경험을 왜곡한다. 미실험과 실패를 구분한다.

### 10.2 v1에서 모터 피드백의 효과를 비교

원본은 499시연·291,869프레임이다. train 355, validation 48, test 48, embargo 48로 나눴다. embargo는 분할 사이에 두어 학습·평가에 사용하지 않은 완충 시연이다.

두 입력 구성을 비교했다.

- baseline: TOP/SIDE RGB + 관절 6축.
- motor_feedback: RGB + 관절·load·current 총 18차원.

영상은 640×480 → 320×240으로 줄였다. batch 4, 목표 50,000단계, AMP, AdamW 1e-5, chunk 100, KL 10이었다. RGB는 ImageNet 통계, 수치·행동은 train 통계로 정규화했고, 검증 MAE로 둘 다 046000을 골랐다.

| 보존 지표 | baseline | motor_feedback |
|---|---:|---:|
| test 정규화 MAE | 0.24401 | 0.23272 |
| 그리퍼 전체 MAE | 4.053 | 3.993 |
| 닫기 시작 후 0.5초 MAE | 11.136 | 10.420 |
| 단일 관측 추론 p95 | 36.6ms | 35.6ms |

모터 입력 모델의 test MAE가 약 4.63% 낮았다. 그러나 실물 성공률을 개선했다고 입증한 자료는 없다. 그리퍼 닫힘 구간 오차가 전체 오차보다 훨씬 컸다는 점이 다음 설계의 중요한 근거였다.

### 10.3 실물 객체 추적 저하를 보고 의심한 것

실제 실행에서는 물체 추적이 나빠졌다는 사용자 보고가 있었다. 다음은 원인 후보이며 확정 원인은 아니다.

| 관측/설정 | 가설 | 단정할 수 없는 이유 |
|---|---|---|
| 영상 픽셀 수 1/4 | 작은 인형·그리퍼 위치 정보 감소 | 해상도만 바꾼 통제 실물 비교 없음 |
| 닫힘 구간 MAE가 큼 | 전체 평균이 짧은 중요 동작 오차를 가림 | 접촉·실제 파지 라벨 아님 |
| 오프라인 검사 통과·실물 저하 | 자기 행동으로 상태가 달라지는 폐루프 오차 | 동일 초기 조건 반복 평가표 없음 |
| 자체 코드·다른 전처리·재계획 | 학습/실행 계약 차이 가능성 | 실제 정규화 버그가 확인된 것은 아님 |
| SIDE 약 22FPS | 접근 순간 시각 정보 부족 가능성 | B200 성공 실험도 같은 원본을 사용 |

즉 “모터 입력이 소용없다”나 “해상도가 유일한 원인이다”가 결론이 아니었다. 관절 평균 오차만으로 실제 집기 행동을 설명할 수 없다는 것이 확인 가능한 학습이었다.

### 10.4 v2에서 제안한 개선은 왜 나왔나

v1의 결과를 보고 다음을 설계했다.

1. 원본 640×480 입력: 작은 물체 정보를 유지하려는 목적.
2. 그리퍼 변화 주변 추가 샘플링: 짧은 파지 구간의 학습 비중을 높이려는 목적.
3. 밝기·대비 ±8% 증강: 조명 변화에 대한 의존을 낮추려는 목적.
4. 파지 주변 오차를 포함한 모델 선택: 전체 MAE 중심 선택의 한계를 보완하려는 목적.
5. batch 2 × gradient accumulation 4: 메모리와 실효 배치 사이의 절충.

계획은 train 347/validation 50/test 50/embargo 52, 100,000업데이트 시도였다. 하지만 계획된 설정과 실제 완료를 분리해야 한다.

### 10.5 AMP 초기 배율에서 비정상 기울기 발생

초기 AMP scale 65536에서 첫 단계 비정상 기울기가 재현됐다. 해결책은 단순 loss 감소를 기다리는 것이 아니라 수치 업데이트 경로를 다루는 것이었다.

- 초기 scale을 1024로 낮춤.
- nonfinite gradient 업데이트는 건너뜀.
- 10회 연속이면 중단하도록 처리.
- 작은 업데이트·저장·재로딩과 회귀 검사로 수정 경로 확인.

10월 8일 기록은 임시 업데이트 2회와 검사 8개 통과다. 이것은 수치 문제 수정 검증이며 v2의 본 학습·실물 성능 개선을 뜻하지 않는다. 파지 샘플링·증강도 아직 검증된 성공 요인이 아니다.

### 10.6 공식 파이프라인을 기준으로 다시 세운 이유

여러 요소를 직접 바꾸면 실패했을 때 모델 원리·데이터·로더·전처리·수치 정밀도·실행 중 어디가 문제인지 구분이 어려워진다. B200 경로는 공식 ACT·trainer·processor를 기준으로 하고 고정 분할·train 통계 연결을 명시해 변경 지점을 좁혔다.

중요한 점은 “B200에서 처음 공식 trainer를 썼다”가 아니라는 것이다. 100시연 실험도 공식 `train()`을 사용했다. 실제 변화는 499시연을 대상으로 자체 v1/v2 경로에서 공식 로딩·학습·정규화 계약을 다시 기준으로 잡고 검증 체계를 보강한 것이다.

## 11. B200 서버: 환경·대용량 전송·정규화·병목을 차례로 해결

주요 근거: [Research Log 3](research_log_3.md), [폐기 전 준비 코드 보존](act_failed_experiments_review.md), 최종 [train_config.json](../experiments/doll_B200_act/act_doll_basic/checkpoints/050000/pretrained_model/train_config.json), 이전 채팅 「B200에서 LeRobot ACT 학습 준비」.

### 11.1 원격 환경에 접속했다고 바로 설치하지 않음

VS Code Microsoft Remote - SSH로 서버를 등록하고 원격 Linux 터미널에서 작업했다. 개인키는 프로젝트 밖 `.ssh`에 두고 서버 주소·포트·사용자·키 경로를 SSH 설정으로 관리했다. 보고서에는 키 내용·비밀번호·접속 주소를 담지 않는다.

당시 실행한 확인 명령:

```bash
whoami
hostname
uname -s
nvidia-smi
```

사용자 `jungsu`, 호스트 `kbj00-robot`, Linux, B200 1개, Clunix Container Terminal 안내가 확인됐다. 별도로 제공된 오픈 포트 네 개는 이 ACT 학습에 사용하지 않았다. 원격 터미널과 파일 전송이면 학습을 수행할 수 있었기 때문이다.

| 항목 | 서버 확인 결과 |
|---|---|
| Python | 3.12.3, `/usr/bin/python3` |
| torch | 2.10.0a0+b4e4ee81d3.nv25.12, NVIDIA 빌드 |
| torchvision | 0.25.0a0+ca221243 |
| Toolkit/nvcc | 13.1.80 |
| torch CUDA | 13.1 |
| driver | 580.95.05 |
| GPU memory | B200, 183,359 MiB 표시 |

`nvidia-smi`의 CUDA 표시는 13.0이었다. 이 표시와 설치 Toolkit·torch CUDA 숫자가 다르다는 이유만으로 드라이버를 교체하지 않고 실제 GPU 순전파·역전파로 확인했다. 핵심은 표기 일치보다 이 프로젝트의 연산이 동작하는지였다.

### 11.2 기존 NVIDIA PyTorch를 보존해야 했던 이유

서버에 일반 torch wheel을 덮어쓰면 이미 B200용으로 준비된 NVIDIA 환경과 달라질 수 있었다. torch·torchvision을 constraints로 고정해 LeRobot 설치 계획을 검토하고, `--system-site-packages` venv로 시스템 torch를 공유했다.

당시 시스템 Python은 PEP 668 보호 때문에 단독 dry-run을 막았다. pip 25.3에서 `--dry-run --report` 조합으로 실제 설치 없이 해결 계획을 확인한 기록이 있다. 전체 설치 명령은 생략된 부분이 있어 옵션만을 완전한 재현 스크립트로 제시하지 않는다.

환경 설계의 핵심을 나타내는 재구성 명령은 다음과 같다. 이미 구축된 환경에 무심코 다시 실행하기 위한 명령은 아니다.

```bash
python3 -m venv --system-site-packages /NHNHOME/workspace/lerobot/lerobot-act
source /NHNHOME/workspace/lerobot/lerobot-act/bin/activate
```

추가 패키지는 venv에, 기존 torch는 시스템에 남기는 구조다. 완전히 독립적인 환경은 아니므로 시스템 패키지 변경의 영향은 공유한다. constraints도 이후 설치 명령에서 `--constraint`로 지정해야 효력이 있다.

### 11.3 TorchCodec import 실패: Python 버전 문제가 아니라 바이너리 연결 문제

배포 TorchCodec 0.10.0은 FFmpeg 6용 라이브러리를 열다가 PyTorch 내부 심볼을 찾지 못했다. 패키지가 설치돼 있어도 현재 NVIDIA torch와 native 바이너리 계약이 맞지 않은 상황이었다.

**확인한 조건.** 실행용 FFmpeg 라이브러리는 있었지만 소스 빌드에 필요한 개발 헤더·pkg-config 파일이 없었다.

**해결 과정.**

1. 관리자 설치 대신 필요한 FFmpeg 개발 `.deb`를 다운로드해 사용자 공간에 압축 해제했다.
2. avcodec·avformat·avutil·swscale·swresample·avdevice·avfilter·postproc 헤더와 pkg-config 경로를 준비했다.
3. 시스템에 이미 존재하는 공유 라이브러리와 링크를 맞췄다.
4. 공식 TorchCodec `v0.10.0` 소스를 현재 NVIDIA torch에 맞춰 빌드했다.
5. `--no-build-isolation --no-deps`로 빌드 중 별도 torch가 설치되지 않게 했다.
6. 생성 wheel로 venv TorchCodec만 교체했다.
7. `VideoDecoder` import와 LeRobot `torchcodec` 백엔드, GPU 모델 계산을 따로 확인했다.

최종 패키지 표기는 `0.10.0a0`, import 버전은 `0.10.0a0+0b261b9`다. CPU 디코딩용 빌드이며 ACT 계산은 B200 GPU다. 보존 wheel의 SHA-256은 다음과 같다.

```text
22aa98f26e8ecc9b8fff662645283926faa3699ea67d633b308eeba9b8351401
```

이는 “버전을 낮춰서 됐다”보다 구체적인 해결이다. 사용 중 torch ABI에 맞춰 codec을 다시 만들고 나머지 핵심 환경은 보존했다. `pip check`에는 기존 yt-dlp와 websockets 불일치가 남았고 이번 범위에서는 수정하지 않았다. 따라서 시스템 모든 의존성을 완전히 정리했다고 쓰지 않는다.

### 11.4 저장 공간이 없어 경로를 다시 설계

홈 overlay는 200GiB인데 인형 데이터만 230.53GiB였다. `/workspace`도 별도 스토리지가 아니라 같은 overlay의 일반 폴더라 해결책이 아니었다. `/NHNHOME/workspace`의 Lustre 저장소 약 4.9TiB 여유와 쓰기 권한을 확인하고 작업 기준을 그곳으로 옮겼다.

**왜 venv 폴더를 그냥 이동하지 않았나.** 가상환경 실행 스크립트는 절대 경로를 포함하기 때문이다. 기존 추가 패키지 목록을 보존하고 새 경로에 환경을 재구성했으며, 빌드한 TorchCodec wheel은 재사용했다. import·GPU 역전파를 확인한 뒤 옛 홈 작업 폴더를 정리했다. 소스·FFmpeg 개발 자료는 압축 보존했다.

```text
/NHNHOME/workspace/lerobot/
├── lerobot-act/                  # venv
├── build/wheels/                 # 빌드 wheel
├── build/source-archives/        # 소스·개발 자료
├── docs/act-local-packages.txt
├── docs/act-constraints.txt
├── datasets/doll/dataset/
├── experiments/act/doll_basic/  # 서버 학습 준비 코드
└── outputs/act_doll_basic/       # 학습 산출물
```

### 11.5 230GiB 데이터 전송: 크기 검증과 내용 해시를 구분

로컬 `robot_datasets/tasks/pick_doll/dataset`의 `meta`, `data`, `videos`만 scp로 전송했다. 종이컵·다른 작업·sessions·백업·임시 폴더는 제외했고 Hub 업로드는 하지 않았다.

| 전송 결과 | 확인 수치 |
|---|---:|
| 파일 수 | 2,498 |
| meta/data/videos | 502 / 499 / 1,497 |
| 전체 바이트 | 247,528,770,428 |
| 크기 | 247.529GB = 약 230.53GiB |
| 시연/프레임 | 499 / 291,869 |
| 영상별 파일 | TOP/SIDE/depth 각각 499 |
| 누락·추가·크기 불일치·빈 파일 | 모두 0 |

비교 기준은 상대 경로와 바이트 수 manifest였다. 전체 파일 SHA-256까지 대조한 것은 아니다. [doll_transfer_manifest.json](../doll_transfer_manifest.json)이 로컬 근거다.

공식 로더로 0, 145934, 291868번째 샘플도 확인했다. state/action `(6,)`, RGB `(3,480,640)`, depth `(1,480,640)`이고 검사 값은 유한했다. 세 위치 샘플 정상은 전체 모든 영상 frame의 무결성 보증과 다르다.

### 11.6 449/50 분할: 기본 마지막 10% 대신 실제 수집 그룹 사용

공식 `eval_split=0.1`만 쓰면 작업 마지막 50개가 검증으로 잡힌다. 수집 순서에 자세·섹션 변화가 있다면 단순 마지막 구간이 전체 조건을 대표하지 못할 수 있었다.

따라서 로컬 sessions의 실제 13개 기록 그룹을 사용했다. 서 있는/누운/혼합 자세와 섹션 묶음 내부 순서를 유지하고 약 10개씩 구간을 나눠 seed 1000으로 검증 구간을 선택했다. 결과는 학습 449/검증 50, `split.json` 고정이다.

존재하지 않는 개별 섹션 라벨을 추정해 붙이지 않았고, 기록된 그룹을 사용했다. 이 분할은 동일 수집 환경 내 검증이며 새로운 카메라·날짜·배경에 대한 외부 일반화 시험은 아니다. B200에는 별도 독립 test split이 없다.

### 11.7 정규화 통계 누출을 피하고 실행에도 같은 계약을 남김

전체 데이터 통계를 그대로 쓰면 검증의 분포 정보가 정규화에 들어갈 수 있다. 학습 episode별 통계를 공식 `aggregate_stats`로 합산하고 train/validation에 같은 train 통계를 넣었다. RGB도 `use_imagenet_stats=False`로 학습 영상 통계를 사용했다.

```text
고정 train episode 목록
→ train episode stats만 aggregate
→ train_stats.json
→ 학습/검증 공통 processor
→ checkpoint에 processor·정규화 Tensor 저장
→ 추론 시 같은 checkpoint processor 재로딩
```

원본 `meta/stats.json`은 바꾸지 않았다. 분할 factory 연결은 프로세스 내부에서 바꾸고 설치 LeRobot 소스를 서버에서 직접 수정하는 방식은 피했다. 분할·통계 계약의 검사에는 `--check-config` 경로를 사용했다.

관절 표준편차 약 `[36.17,51.16,45.05,41.27,25.34,11.18]`, action 약 `[36.23,50.68,45.54,41.42,25.66,11.64]`가 기록돼 있다. 수치의 존재뿐 아니라 train 통계가 실제 로더에 연결되는지 검증한 과정이다.

### 11.8 작은 검증 중 발견한 설정·프로세스 오류

| 발생한 문제 | 어디서 확인 | 수정 및 이유 |
|---|---|---|
| 존재하지 않는 `eval_freq` 인자 | config 생성 오류 | 공식 trainer 실제 필드에 맞게 제거 |
| heredoc+작업자 2의 spawn 실패 | `<stdin>` 파일을 찾지 못함 | 우선 workers 0으로 실제 파일 경로 문제 분리 |
| eval 설정 누락 | `eval_steps>0`인데 `eval_split` 없음 | 0.1 명시, 실제 분할은 고정 목록 유지 |
| 학습 100% 뒤 오랫동안 멈춰 보임 | 29,262 검증 frame 디코딩 | 학습 10단계와 전체 검증 시간을 구분 |

잘못된 config에서 중단된 것은 학습 실패 모델을 만든 일이 아니다. 설정 단계 실패, 데이터 로딩 실패, 수치 업데이트 실패, 실물 실패를 각기 다른 층으로 분류한 이유다.

### 11.9 GPU가 한 번 0%였다는 이유로 멈췄다고 판단하지 않음

batch 2/workers 0의 10단계 학습은 약 8초였지만 검증이 길었다. 당시 CPU 평균 약 789%, GPU 메모리 약 2.5GiB였고, 한 순간의 GPU 0%는 데이터 준비나 검증 구간일 수 있었다.

먼저 depth를 유지한 채 workers만 0→4로 바꿨다. 당시 실제 안내 명령:

```bash
source /NHNHOME/workspace/lerobot/lerobot-act/bin/activate
python /NHNHOME/workspace/lerobot/experiments/act/doll_basic/train.py \
  --steps 10 --batch-size 2 --num-workers 4 \
  --eval-steps 10 --save-freq 10 --log-freq 1 \
  --output-dir /NHNHOME/workspace/lerobot/outputs/act_doll_basic_workers4
```

첫 배치 준비 약 12초 뒤 미리 읽은 배치의 `data_s`가 약 0.001초였다. 하지만 10배치만으로 장기 처리량은 판단하지 않았다. 2026-10-13 15:16:55에는 `eval_loss=0.7549`, checkpoint 저장과 `End of training`을 확인했다. 전체 약 5분 19초로 대부분이 검증이었다.

0.7549는 학습·평가·저장 경로가 돈다는 증거이며 인형 성공률이 아니다. 진행 막대의 `31.94s/step`도 검증 포함 총 시간을 10단계로 나눈 값이므로 순수 GPU 학습 속도로 해석하면 안 됐다.

### 11.10 모델에서 제외한 depth가 로더에서는 계속 읽혔음

처음에는 모델 입력만 depth에서 제외했지만 공식 로더는 원본 feature의 depth도 디코딩했다. 초기 연구 로그는 이 비용을 남겨 둔 상태로 작성됐다.

이후 사용자가 depth 로딩도 빼 달라고 요청했다. 과거 대화에서 안내한 수정은 `make_dataset(selected_cfg)` 뒤 메모리의 depth feature와 관련 delta 목록에서 depth를 제거하는 것이었다.

핵심 수정 개념은 다음과 같다. 실제 공식 API 구조에 맞춘 당시 패치에서 가져온 부분이며, 원본 파일 삭제 명령이 아니다.

```python
depth_keys = list(dataset.meta.depth_keys)
for key in depth_keys:
    dataset.meta.features.pop(key, None)
    if dataset.reader.delta_indices is not None:
        dataset.reader.delta_indices.pop(key, None)
    if dataset.delta_timestamps is not None:
        dataset.delta_timestamps.pop(key, None)
```

원본 depth와 메타정보는 보존하고, train/validation 로더의 영상 목록을 출력해 TOP/SIDE만 남는지 확인하도록 했다. 당시 패치 안내 직후 답변에는 서버 적용·실행 결과는 아직 미확인이라고 기록돼 있다. 후속 본 학습은 확인되지만, 최종 로컬 checkpoint 설정만으로 로더 내부 메모리 패치 적용까지 증명되지는 않는다. 현재 선택 평가 코드는 depth feature를 제거하는 경로가 직접 확인된다.

이 사례는 “모델이 안 쓰는 입력”과 “데이터 로더가 안 읽는 입력”이 다르다는 성능 분석상의 중요한 구분이다.

### 11.11 실행 버튼을 위한 개발환경도 정리

서버 train.py에 steps 기본값 50,000, workers 4를 넣고 VS Code 원격 Python 확장·인터프리터를 지정했다. 로컬 확장 설치와 SSH 호스트 확장 설치는 다르므로 원격 창의 Python 실행 기능을 확인해야 했다.

사용 인터프리터:

```text
/NHNHOME/workspace/lerobot/lerobot-act/bin/python
```

파일 수정 시에는 기존 내용을 읽고, 수정 대상 문자열이 정확히 하나인지 확인하고, `ast.parse`로 문법을 검사한 뒤 timestamp 백업을 남겼다. 원격 코드를 빠르게 수정하면서도 잘못된 위치 치환·중복 패치를 막기 위한 방식이었다.

다만 당시 래퍼에는 학습 재개 옵션이 연결되지 않았고, Run Python File in Terminal이 SSH 종료 후 지속 실행을 보장하지 않았다. 이 한계는 뒤의 중복 프로세스 문제와도 연결된다.

### 11.12 중복 학습을 확인한 뒤 한 프로세스만 유지

batch 64 실행 중 `nvidia-smi`에 Python 두 개가 각각 약 30GiB를 사용했다. 두 프로세스가 보인다는 이유만으로 작업자라고 가정하거나 곧바로 종료하지 않았다. 전체 명령과 부모 PID를 확인했다.

당시 기록 명령:

```bash
ps -ww -p 3567325,3923664 -o pid,ppid,etime,stat,args
```

두 개 모두 같은 `experiments/act/doll_basic/train.py`를 실행했고, 앞선 3567325는 PPID 1, 현재 3923664는 터미널 부모를 가졌다. 학습 본체 중복을 확인한 뒤 과거 실행에 `kill -TERM 3567325`를 안내했고, 사용자 후속 결과에서 3923664만 남은 것을 확인했다.

PID는 당시 기록이며 지금 실행할 명령의 대상이 아니다. 같은 결과 경로를 공유했을 가능성이 있어 저장 산출물은 후속 감사가 필요했다. 한편 현재 수집기에는 별도 잠금을 두어 중복 장비 사용·마이그레이션을 막는다.

### 11.13 batch 2보다 64가 느리게 느껴지는 이유를 로그로 해석

사용자가 5,000단계 부근 로그를 공유했다.

```text
step:5K  smpl:320K  epch:1.22  loss:0.196
updt_s:0.139  data_s:0.242  smp/s:168  mem_gb:25.66
l1_loss:0.160  kld_loss:0.004  lr:1.0e-05
```

앞선 두 줄도 초당 162~170샘플, update 약 0.138초, data 약 0.239~0.256초였다.

**판단.**

- batch 64는 한 단계에서 batch 2의 32배 샘플을 처리하므로 step/s만으로 비교하면 오해한다.
- 같은 50,000단계도 batch 2면 10만, batch 64면 320만 샘플 제시다.
- update보다 data 대기가 커 영상 공급·디코딩·스토리지 비용을 함께 봐야 한다.
- batch 2의 57~105샘플/s는 10단계의 미리 읽은 구간 측정이라 본 학습 장기 평균과 동등 비교가 아니다.
- 검증·저장 구간이 진행 막대 ETA를 흔들 수 있다.

이는 “GPU가 크니 배치를 늘리면 무조건 빨라진다”에서 “한 번에 처리한 샘플과 데이터/계산 구간을 나눠 판단한다”로 관점이 바뀐 사례다. batch 64가 최적값임을 입증한 체계적 탐색은 하지 않았다.

### 11.14 계획값과 실제 최종 설정을 구분

초기 연구 로그의 batch 2/workers 4는 검증·실행 준비 시점 값이다. 로컬로 가져온 최종 설정은 다음과 같다.

| 항목 | 실제 저장된 본 학습 설정 |
|---|---|
| steps / batch / workers | 50,000 / 64 / 7 |
| prefetch / persistent workers | 4 / True |
| multiprocessing | spawn |
| 정밀도 | FP32, use_amp=False |
| seed | 1000 |
| 학습/검증 | 449 / 50 |
| 입력 | TOP/SIDE RGB 원본 640×480 + 관절 6축 |
| 출력 | 100×6 action chunk |
| 이미지 증강 | enable=False |
| RGB 통계 | train 통계, use_imagenet_stats=False |
| optimizer | 공식 ACT preset, AdamW lr=1e-5, wd=1e-4 |
| gradient clip norm | 10 |
| eval/save/log 주기 | 1000 / 1000 / 100단계 |
| Hub/WandB | 비활성화 |

최종 설정 파일에 증강 후보 목록이 있더라도 `enable=False`면 실제 증강 적용으로 쓰지 않는다. batch/workers를 최종 값으로 바꾼 모든 중간 수정 명령은 남은 자료로 완전히 추적하지 못했지만, 완료 산출물의 값은 직접 확인된다.

## 12. 학습 종료 뒤: 체크포인트 감사·선택·로컬 실행

### 12.1 폴더가 많다는 질문을 구조 검사로 전환

서버 결과 전체를 로컬로 복사해 `experiments/doll_B200_act/act_doll_basic`에 보관했다. 가중치 하나만 가져오면 정규화·분할·재개 상태를 잃으므로 폴더 단위 보존을 선택했다.

[checkpoint_audit.json](../experiments/doll_B200_act/checkpoint_audit.json)에 남은 결과:

- 001000~050000의 번호 checkpoint 50개, 누락 없음.
- 최종 training state는 50,000단계·batch 64·process 1.
- 필수 파일 구조 오류 없음.
- 최종 모델·processor·optimizer·RNG 검사 대상에 nonfinite tensor 없음.
- train 449/validation 50, 중복 0, 전체 시연 포괄.
- 초기 가중치와 최종 가중치가 서로 다름.
- local `last`와 050000의 필수 파일 hash 일치.
- 결과 전체 약 29.43GiB, 번호 checkpoint 합 약 28.85GiB.

`pretrained_model`에는 추론용 모델·설정·정규화가, `training_state`에는 optimizer·RNG·step이 있다. 중간 checkpoint가 많은 이유는 1,000단계마다 저장했기 때문이다. `last`는 최고 성능 모델이 아니라 마지막 모델이다.

감사 당시 결과 폴더에는 학습·검증 loss 곡선 로그가 없었다. 과거 채팅의 일부 학습 로그와 checkpoint는 있지만 전체 곡선을 복원할 자료는 부족하다. 따라서 파일 구조 정상만으로 과적합이 없다고 하지 않았다.

### 12.2 마지막 모델을 최선이라고 가정하지 않고 동일 표본 비교

새로 만든 [select_checkpoint.py](../experiments/doll_B200_act/select_checkpoint.py)는 고정 split의 검증 50시연에서 각 10개 시점을 균등하게 선택해 총 500관측으로 비교했다.

평가 계약은 다음과 같다.

1. train과 겹치지 않는 검증 episode만 사용.
2. 같은 500관측을 모든 번호 checkpoint에 제공.
3. 저장된 train 정규화와 공식 processor 사용.
4. RGB는 0~1 변환 후 processor, 현재 관절 6축 결합.
5. FP32, 실제 추론처럼 CVAE `z=0`으로 미래 100행동 예측.
6. episode 끝 padding을 마스크로 제외.
7. 정규화 6축 L1을 유효 미래 frame에 집계하고 episode별 동일 비중으로 평균.
8. `scores.csv`, `anchors.json`, `selected_checkpoint.json` 보존.

코드 상단에는 초기의 “간이 선별 후 상위 후보 재평가” 설명도 남아 있다. 최종 수행은 `--full-comparison`으로 50개 전체를 같은 500관측에서 평가한 것이며, README·선택 JSON·CSV를 함께 기준으로 한다.

```powershell
& D:\lerobot-2026\.venv\Scripts\python.exe D:\lerobot-2026\experiments\doll_B200_act\select_checkpoint.py --full-comparison
```

위 명령은 GPU 평가와 결과 파일 쓰기를 수행하지만 하드웨어를 연결하지 않는다. 이번 보고서 작성에서는 재평가하지 않고 보존 결과를 읽었다.

### 12.3 선택 결과와 해석 한계

| checkpoint | 정규화 action MAE | 판단 |
|---|---:|---|
| 047000 | **0.19671549** | 이 검증 표본의 최저 오차 |
| 046000 | 0.198786 | 다음 후보 |
| 038000 | 0.199013 | 다음 후보 |
| 050000 | 0.201622 | 마지막 모델 |

선택 모델은 마지막 모델보다 해당 지표가 약 2.43% 낮았다. 근거: [선택 JSON](../experiments/doll_B200_act/selection/selected_checkpoint.json), [전체 점수](../experiments/doll_B200_act/selection/scores.csv).

이 숫자는 단위 없는 정규화 오차다. 성공률 19.67%도 아니고, 실물 성공률이 2.43% 개선됐다는 뜻도 아니다. 모델 선택에 사용한 validation이므로 독립 test 성능으로 쓰지 않는다. v1의 test MAE와도 분할·통계·표본·집계가 달라 개선율을 직접 계산하지 않는다.

### 12.4 표준 실행기와 선택 모델 실행기의 차이

실행 경로를 두 가지로 정리했다.

| 파일 | 목적 | 실제 동작 시작 조건 |
|---|---|---|
| [run_act.py](../experiments/doll_B200_act/run_act.py) | 공식 `lerobot-rollout`, sync/base 경로 | `--execute`이면 연결 후 제어 시작 |
| [run_selected.py](../experiments/doll_B200_act/run_selected.py) | 선택 JSON을 읽고 기존 안전 실행기 재사용 | `--run`으로 연결 허용 후 SPACE |

둘 다 기본은 장비 미연결 검사다. 그러나 제어 구조와 시작 조건이 다르므로 “어느 실행기든 SPACE로 시작한다”고 설명하면 안 된다.

표준 실행기는 관절 순서, 입출력 shape, 보정, 카메라 해상도/FPS, LeRobot 버전과 모델·processor 로딩을 확인하고 공식 rollout에 인자를 전달한다. 초기에는 공용 scripts에 배치했다가 사용자 요청에 따라 실험 전용 `experiments/doll_B200_act`로 옮겼다. 파일 위치도 모델 실험의 책임과 맞춘 것이다.

최종 선택 모델 실행 경로는 다음과 같다.

```text
선택 번호 047000 읽기
→ 해당 checkpoint 모델·공식 processor 함께 로딩
→ dataset 499시연/291869프레임·관절 순서 확인
→ TOP/SIDE + state를 공식 inference frame으로 구성
→ FP32 ACT 100×6 예측
→ 같은 checkpoint postprocessor로 역정규화
→ train action 범위·관절별 속도·추종 제한
→ 비동기 재계획·계획 전환 혼합
→ Follower 송신
```

사전 검사 중 수집 모듈 import 경로 문제를 발견해 필요한 장비 설정을 JSON에서 직접 읽는 방향으로 수정한 이력도 있다. 수집 UI import에 추론 실행이 불필요하게 의존하지 않도록 한 조정이다.

### 12.5 B200 checkpoint를 로컬 RTX 3080에서 재사용

학습 장치는 B200, 실물 실행 장치는 로컬 RTX 3080이다. 실행 코드의 기본값으로 다른 정규화를 새로 만들지 않고 선택 checkpoint의 `make_pre_post_processors(..., pretrained_path=...)`를 사용했다.

현재 선택 실행기에서는 과거 실행기의 FP16 강제 대신 FP32 추론을 사용하고, 예측 shape `(100,6)`·유한값을 검사한다. 모델 가중치를 이미 읽으므로 ResNet 초기 가중치를 추가 다운로드하지 않도록 설정했다. 실제 추론 시각을 GPU 동기화 전후로 측정한다.

기존 초기 모델 전용 gripper 8프레임 조기 닫기는 **0으로 끈다**. B200 모델에도 같은 수동 타이밍 보정이 필요하다는 근거가 없기 때문이다. 안전 제어기의 기본 60프레임 재계획과 8프레임 팔 crossfade는 재사용한다.

### 12.6 안전 동작은 모델 외부 제어 로직과 함께 구성

선택 실행 경로는 다음 항목을 유지한다.

- 관절별 train action min/max 제한.
- 프레임당 변화량: shoulder_pan 2, shoulder_lift/elbow 3, wrist_flex/wrist_roll 4도, gripper 5정규화 단위.
- 측정 관절보다 목표가 무제한 앞서지 않도록 10도 추종 제한.
- shoulder_lift·elbow_flex·wrist_flex의 지속 4초 stall 감시.
- 정상 정지·타임아웃·복구 가능한 오류 시 HOME 복귀와 안정화 후 torque 해제.
- HOME 실패 시 팔 지지를 확인한 다음 해제하는 경로.
- `Q` 종료, `P` 일시정지, `E` 긴급 torque-off.
- 기본 한 시연, 최대 60초.

이것은 산업용 안전 인증이나 충돌 완전 방지를 의미하지 않는다. 실제 코드가 제한하는 항목과 그 범위를 설명하는 것이다. gripper의 0~100 단위를 팔 각도와 섞어 “모두 2~5도”로 표현하지 않는다.

현재 코드에 맞춘 실행 명령:

```powershell
# 모델·데이터·보정 사전 검사: 장비 미연결
& D:\lerobot-2026\.venv\Scripts\python.exe D:\lerobot-2026\experiments\doll_B200_act\run_selected.py

# 실제 장비 연결 허용. 미리보기에서 SPACE 이후 움직임
& D:\lerobot-2026\.venv\Scripts\python.exe D:\lerobot-2026\experiments\doll_B200_act\run_selected.py --run
```

### 12.7 모델은 정상인데 카메라 연결에서 실패

실행 로그에서 선택 047000과 모델 로딩은 성공했지만 `RealSenseCamera(352122273503)` open에 실패했다. 팔 동작 시작 전 장치 연결 단계였다.

처음에는 카메라 점유·USB·RGB 단독 모드 호환성도 후보였다. 원인을 확정하기 전에 [check_realsense.py](../experiments/doll_B200_act/check_realsense.py)로 장치 열거, RGB 단독, RGB+depth를 나눠 검사하도록 했다. 로봇을 다시 움직여 확인할 필요가 없는 장애였다.

사용자가 교수님이 카메라를 교체했을 가능성을 알려 줬고, 실제 장치 열거 결과 새 D405 serial은 `262422273645`였다.

**수정.**

1. `collection/settings.json`의 serial을 새 장치로 갱신.
2. 자동 수집·수동 수집·노출 검사 코드의 하드코딩을 설정 참조로 변경.
3. 현재 실행기가 동일 설정을 읽도록 유지.
4. 과거 dataset/session의 장치 기록은 변경하지 않음.
5. 새 serial로 640×480 RGB 단독·RGB+depth 수신 확인.
6. 변경 Python 파일 문법 검사 통과.

당시 진단 명령:

```powershell
& D:\lerobot-2026\.venv\Scripts\python.exe D:\lerobot-2026\experiments\doll_B200_act\check_realsense.py
```

이 단계에서 로봇 연결·모터 동작이나 USB reset은 하지 않았다. “모델 실행 실패”를 모델 품질 문제로 오인하지 않고 실제 실패 단계인 장치 식별로 좁힌 사례다.

### 12.8 최종 성공의 근거를 어떻게 적을 것인가

10월 14일 초기 실험 정리 문서는 사용자가 `doll_B200_act`를 완전히 성공한 실험으로 확인했다고 기록한다. 이번 사용자 요청도 `doll_act` 성공까지의 과정을 정리해 달라는 맥락이다.

따라서 이 보고서에서는 **B200 학습·선택 모델을 기반으로 인형 집기 작업의 실물 성공을 사용자 확인 결과로 기록**한다. 로컬 선택 JSON의 `robot_success_rate_measured=false`는 자동 평가 당시 실물 성공률을 측정하지 않았다는 뜻이다. 후속 성공 진술을 부정하는 값도 아니고 정량 성공률로 바꿔 쓸 값도 아니다.

다만 성공 시점의 전체 실행 로그·시도 수·시작 위치별 표·정확한 실행기/리비전 대응이 부족하다. 따라서 성공 횟수, 100% 성공률, 첫 시도 성공률, 속도 개선율, 어떤 한 변경의 기여도를 새로 만들어 넣지 않는다.

## 13. 성공까지의 변화는 무엇을 설명하고 무엇을 설명하지 못하는가

### 13.1 전 과정을 관통하는 개선 방식

처음부터 모델 하이퍼파라미터만 바꾸지 않았다. 문제를 발생 위치별로 나누고 해당 구간을 측정해 수정했다.

```text
SDK가 없다 → Python과 pip가 같은 환경인지 확인
모터가 불안정하다 → ID·전압·개별 통신과 연속 추종 분리
보정이 사라졌다 → 기구보다 파일 경로·환경변수 점검
영상이 부족하다 → 실제 디코딩과 인코더 큐 확인
검사기가 실패한다 → shared MP4의 episode 구간 확인
시연이 계속 폐기된다 → 제어 FPS와 카메라 신규 FPS 분리
오프라인 점수는 좋다 → 닫힘 순간과 실물 폐루프를 따로 분석
GPU가 놀아 보인다 → 데이터 준비·평가·중복 프로세스 확인
학습은 끝났다 → 가중치·정규화·상태·분할 감사
마지막 모델이 있다 → 같은 관측으로 중간 모델 비교
모델 실행이 안 된다 → checkpoint 로딩과 카메라 연결 단계 분리
```

이 흐름에서 프로그래밍 역량을 보여 주는 부분은 원인 후보를 코드와 측정으로 줄이고, 수정이 다음 실패를 막도록 검증·기록 구조에 남긴 것이다.

### 13.2 v1과 B200을 비교할 때 말할 수 있는 범위

| 비교 축 | v1 | B200 성공 경로 |
|---|---|---|
| RGB | 320×240 | 640×480 |
| 수치 입력 | 6축/18차원 비교 | 관절 6축 |
| trainer/전처리 | 자체 경로, AMP | 공식 경로, FP32 |
| RGB 정규화 | ImageNet 통계 | train episode 통계 |
| batch | 4 | 최종 64 |
| train/validation | 355/48 + test·embargo | 449/50 |
| 선택 | 검증 MAE 046000 | 50개×동일 500관측 비교, 047000 |
| 재계획 | 기본 30프레임 | 선택 실행기는 60프레임·crossfade |
| 실물 결과 | 추적 저하 보고 | 사용자 성공 확인 |

여러 조건이 함께 달라졌다. 따라서 “해상도 복원 덕분에 성공”, “B200이라 성공”, “모터 입력을 빼서 성공” 중 하나를 확정할 수 없다. 더 큰 batch는 같은 step에서 총 제시량도 바꾸므로 GPU 종류만의 비교도 아니다.

보다 정확한 설명은 **실패한 자체 실험의 결과를 바탕으로 관측 정보·학습 계약·수치 안정성·모델 선택·실행 일관성을 재정비했고, 공식 경로의 후속 실험에서 사용자 확인 실물 성공에 도달했다**는 것이다.

### 13.3 다음 개선을 위해 이미 도출된 질문

다음 항목은 완료 성과가 아니라 현재 증거의 빈칸을 메우는 후속 연구 설계다.

1. 성공 조건을 파지·운반·안착·HOME으로 나누고 전체 시도 수를 기록한다.
2. 고정 초기 위치·자세에서 checkpoint/설정별 실물 비교를 반복한다.
3. 영상 수신, raw 예측, 제한 후 송신, 실제 관절을 같은 시계에 묶어 파지 지연을 분해한다.
4. 원본 해상도·train 정규화·FP32 등 한 요소씩 바꿔 기여를 확인한다.
5. 모터 load만 추가한 공식 경로를 만들면 입력 이득과 구현 차이를 분리할 수 있다. 아직 완료 모델은 아니다.
6. 22Hz 소규모 수집·학습·실행 비교를 해 보면 SIDE 재표본화의 영향에 접근할 수 있다. 기존 metadata FPS 숫자만 바꾸는 작업과는 다르다.
7. 새 장비·조명·날짜·배경으로 나눈 독립 평가가 있어야 일반화 범위를 말할 수 있다.

## 14. 성공 이후에도 이어진 수집기 개선

이 절은 현재 코드·README·측정 보고서에 남은 후속 개선이다. 이 변경들이 이미 끝난 B200 학습의 원인이었다고 역순으로 서술하지 않는다. 특히 기존 RGB를 이후 무손실 형식으로 바꿨다고 과거 학습이 처음부터 원본 무손실 영상으로 수행됐다고 쓰면 안 된다.

### 14.1 빠른 저장과 검증 수준을 분리

초기에는 모든 depth frame의 코드·mm 픽셀을 매 저장 후 비교했다. 데이터가 커지고 대기가 길어지면서 현재 구현은 저장 직후 검사·종료 시 확대 검사·pending 기록을 구분하는 방향으로 바뀌었다.

- 저장 직후: 수치·인덱스·작업 문장·영상 패킷 순서, 처음·끝·중간 포함 10개 영상 표본 디코딩.
- depth: 선택된 표본의 모든 픽셀 코드·mm 비교.
- 종료 시: 장비 해제 후 각 영상 최대 50개 표본과 패킷 순서 검사.
- 원본 hash와 미완료 검사는 `verification_pending`에 남겨 다음 시작 전 이어 처리.
- 검사 실패는 수집 재개 차단 및 시연 번호 기록.

표본 검사로 바뀐 현재 상태를 과거의 전수 검사와 동일하게 “전체 무결성 통과”라고 표시하지 않는다. 미검사 frame의 손상 가능성은 남는다. 설정의 `full_check_on_exit`라는 이름만 보고 매 픽셀 전수 디코딩이라고 해석하지 않고 실제 `exit_video_samples=50`과 구현 범위를 함께 본다.

이 구분의 중요성은 [종이컵 저장 검사](../collection/reports/pick_paper_cup_storage_audit.md)에서도 보인다. 102시연·58,182프레임 RGB 전체 디코딩과 depth packet count/시연당 5개 frame 검사에서 오류는 없었지만, depth pending 101개가 기록돼 있다. “오류 없음”과 “모든 depth 픽셀 검증 완료”는 다른 상태다.

### 14.2 복구 때문에 데이터 전체를 계속 복사하지 않게 함

현재 복구 구조는 불변 영상은 같은 디스크 hard link로 재사용하고, 마지막 변경 가능한 영상은 별도 사본을 둔다. 정상 복구 기준의 수치·메타·경로·크기를 확인하며, 기존 검증을 마친 전체 영상을 매번 다시 디코딩하지 않는다.

진행 표시와 단계별 취소를 넣어 복구 중 프로그램이 멈춘 것처럼 보이는 문제도 줄였다. 실패 원본은 격리 보존하고 복구 실패 시 새 시연을 시작하지 않는다. `exclusive`, `pending_guard`, `snapshot`, `recover`, `safe_child`가 잠금·진행 상태·경로 범위를 담당한다.

### 14.3 무손실 RGB: 코덱 이름이 아니라 실제 픽셀로 확인

현재 RGB 설정은 GPU `h264_nvenc`, GBRP 입력, preset p1, GOP 2, `tune=lossless`다. CPU `libx264rgb` 경로와 비교했고, 60프레임 시험에서 픽셀 불일치 0개를 확인했다.

| 후보 | 60프레임 encode 시간 | 파일 크기 | RGB 완전 일치 |
|---|---:|---:|---|
| libx264rgb | 0.740초 | 86,478,650B | True |
| h264_nvenc | 0.496초 | 86,350,371B | True |
| hevc_nvenc | 0.411초 | 73,899,904B | True |

근거: [lossless_gpu_profile.json](../collection/reports/lossless_gpu_profile.json). 세 후보 시험에서 HEVC가 빠르더라도 현재 채택 설정은 H.264다. 남은 기록만으로 최종 선택의 모든 판단을 새로 추측하지 않는다. 이 작은 시험의 encode 시간과 전체 장비 수집 속도를 구분한다.

9월의 NVENC 초기화 실패와 현재 NVENC 시험 성공은 서로 다른 시점의 결과다. 초기 실패를 숨기거나 “NVENC는 원래 안 됨”으로 고정하지 않고, 런타임 초기화·실제 저장·픽셀 복원을 다시 검증한 뒤 설정을 바꾼 이력으로 남긴다.

### 14.4 이미 손실 압축된 영상을 변환할 때 지킨 기준

[migrate_rgb_lossless.py](../scripts/migrate_rgb_lossless.py)는 기존 RGB를 디코딩하고 `libx264rgb`로 변환한 뒤, 모든 디코딩 RGB 픽셀의 hash와 frame timestamp 목록이 같은지 검사한다. staged 파일 검증 뒤에만 교체하고 원본을 백업한다. 마이그레이션 잠금과 pending marker, rollback도 있다.

```powershell
# 현재 도구의 사용 명령. 원본 변경·백업을 수행하는 작업이다.
& D:\lerobot-2026\.venv\Scripts\python.exe D:\lerobot-2026\scripts\migrate_rgb_lossless.py

# 중단된 pick_doll 변환을 복원하는 명령
& D:\lerobot-2026\.venv\Scripts\python.exe D:\lerobot-2026\scripts\migrate_rgb_lossless.py --rollback pick_doll
```

이 명령은 이번 보고서 작성에서 실행하지 않았다. 이전 손실 압축으로 사라진 원래 센서 화질을 되살리는 기능이 아니다. **현재 디코딩 가능한 영상을 추가 픽셀 손실 없이 보존하는 형식 변환**이다. 스크립트의 `restores_original_camera_quality=False`도 이 의미를 명시한다.

### 14.5 depth 속도를 실제 코드 일치와 함께 측정

depth 120프레임 시험:

| preset | 시간 | 바이트 | depth 코드 일치 |
|---|---:|---:|---|
| fast | 9.495초 | 23,821,255 | True |
| ultrafast | 2.792초 | 32,173,090 | True |

encode 시간은 약 70.6% 줄고 파일은 약 35.1% 커졌다. 압축률과 CPU 시간을 교환하되 depth 코드는 유지된다는 측정에 따라 현재 `depth_encoder_preset=ultrafast`를 사용한다. [depth_encoding_profile.json](../collection/reports/depth_encoding_profile.json)

이 역시 120프레임 오프라인 encode 비교이며 30FPS 전체 수집을 보장하는 결과는 아니다.

### 14.6 GPU 초기화와 오래된 카메라 버퍼 때문에 첫 시연이 폐기됨

encoder 초기화를 첫 녹화 frame에서 수행하면 GPU 준비 지연이 첫 두 frame 사이로 들어가 품질 기준을 위반할 수 있었다. 현재는 PREP 단계에서 초기화하고 완료 후 START 1초를 표시한다. 더미 frame을 녹화 파일에 넣어 프레임 수를 맞추는 방식은 쓰지 않는다.

저장·검사 직후 background capture가 잠시 밀리면 버퍼가 오래될 수도 있다. 현재는 오래된 영상을 바로 쓰거나 즉시 전체 프로그램을 종료하지 않고, 총 200ms 대기 안에서 새 영상으로 갱신한다. 그래도 오래되면 TOP/SIDE 이름과 나이가 포함된 오류를 낸다.

카메라 버퍼 수락 나이는 80ms로 품질 기준 100ms보다 짧게 잡아 모터 읽기·송신에 20ms 여유를 둔다. SIDE를 기다리는 동안 TOP이 낡으면 두 개를 다시 검사한다. encoder별 스레드 수도 제한해 카메라 처리에 CPU 여유를 남긴다.

### 14.7 절대 시계 제어와 저장 객체 재사용

현재 `wait_capture_tick`는 목표 deadline 기준으로 잠들고, 긴 지연 뒤 밀린 frame을 한꺼번에 생성하지 않는다. busy wait를 줄여 카메라·encoder thread가 실행될 여유를 준다. 미리보기는 최대 15FPS지만 녹화 목표는 30FPS다. 화면 갱신과 기록 주기를 분리한 것이다.

저장 때 Parquet footer를 닫아 즉시 읽을 수 있게 하되 수집 객체 전체를 매번 재생성하지 않는다. 다음 시연은 새 shard로 회전해 닫힌 기존 파일을 덮어쓰지 않는다. 실제 변경은 `checkpoint_recording`, metadata shard 회전, 영상만 있을 때 불필요한 `embed_images`와 PNG 저장 thread 생략 등에 남아 있다.

이러한 변경은 현재 코드 구현과 작은 검사에 대한 근거가 있다. 전체 장비를 실제로 움직인 장시간 속도·저장 대기는 후속 수집 session의 측정으로 확인해야 한다.

## 15. 어떤 종류의 프로그래밍 역량을 설명할 수 있는가

### 15.1 LeRobot 과정에서 직접 근거를 찾을 수 있는 역량

이력서를 쓸 때 기술명만 나열하기보다 아래처럼 구현 근거와 연결하면 경험을 설명하기 쉽다.

| 분야 | 이 프로젝트에서의 구체적 활동 | 증거 |
|---|---|---|
| Python 시스템 개발 | 상태기계, CLI, GUI/worker, 데이터 검증·복구 | collection core/collect/quality |
| 장비·통신 연동 | Feetech SDK, serial scan, 레지스터·전압·ID, 재시도, block read | Research Log 1, 로컬 bus 변경 |
| 영상·센서 처리 | D405 RGB-D, OpenCV 웹캠, frame timestamp, 단위 변환 | camera/quality 코드 |
| 데이터 엔지니어링 | Parquet·MP4·metadata, episode 구간, manifest·hash·복구 | 수집기·전송 manifest |
| 딥러닝 실험 | ACT feature, 공식 trainer, 고정 분할, train 통계, AMP 진단 | train config·실험 분석 |
| 모델 평가 | padding 제외·동일 관측·episode 동등 집계·checkpoint 선택 | select_checkpoint.py·scores.csv |
| 실행 제어 | 비동기 재계획, 계획 혼합, 속도/범위/추종 감시 | safe runner·run_selected.py |
| Linux/GPU 환경 | SSH, venv, constraints, TorchCodec native build | Research Log 3·과거 실행 기록 |
| 성능 분석 | 구간별 ms, sample/s, camera 신규율, I/O와 compute 분리 | collection/reports·B200 로그 |
| 실험 문서화 | 실패 가설·측정 범위·미완료 상태·산출물 보존 | 연구 로그·본 보고서 |

이 프로젝트에서 김해민은 Codex와 함께 자료 해석, 코드 구성·수정, 오류 분석 및 검증을 진행했다. 실제 장비 연결·조작, 시연 수집과 실행 결과 확인을 포함한 LeRobot 개발 과정을 개인 프로젝트의 이력으로 정리한다. 공식 LeRobot·ACT를 활용한 부분과 프로젝트에 맞게 추가·수정한 부분은 구분한다.

### 15.2 추천받은 회사와 연결되는 기술 범위

2026-10-15 확인한 [IR Solutions 공식 홈페이지](https://ir-solutions.co.kr/)는 사람의 기술 학습, Physical AI, 로봇팔·그리퍼·센서 통합, 산업 현장 자동화를 소개한다. 따라서 LeRobot의 센서·시연·정책·실물 제어 경험과 연결할 근거는 있다.

그러나 해당 회사의 이번 추천 직무·채용요건·주력 개발 언어·개발팀 환경은 확인되지 않았다. C++/ROS2/PLC 등이 필수라고 추정하거나 사용 경험이 확인되지 않은 기술을 경력으로 추가하지 않는다. 이 LeRobot 프로젝트에서 직접 설명할 수 있는 축은 Python 기반 로봇·영상·수집·학습·평가·실행 파이프라인이다.

## 16. 시행착오 통합표

| 번호 | 관찰/실패 | 확인 방법 | 수정 이유·조치 | 결과·한계 |
|---:|---|---|---|---|
| 1 | SDK 설치했는데 import 실패 | sys.executable·pip 위치 | 환경 혼선을 절대 Python 지정으로 해소 | 프로젝트 venv SDK import·scan |
| 2 | venv pip 없음 | pip import·경로 | ensurepip 후 대상 venv에 설치 | 복구 기록 |
| 3 | torch가 LeRobot 범위 밖 | pyproject 의존성 | torch 2.11 계열로 맞춤 | CUDA 확인 |
| 4 | uv index 의존성 충돌 | resolver 결과 | index 후보 비교 옵션 변경 | 설치 성공 기록 |
| 5 | TorchCodec DLL 경고 | shared DLL·실제 영상 로딩 | DLL 디렉터리 직접 등록 | 공개 frame Tensor 확인 |
| 6 | 초기 모터 ID 6 미검출 기록 | 시점별 scan 대조 | 후속 6ID 재확인 | 정확한 초기 원인은 미확인 |
| 7 | 간헐 status packet 오류 | 개별 통신·20회 Ping·연속 조작 | retry·케이블/USB/전원 점검 | 추종 가능, 물리 원인 확정 아님 |
| 8 | 보정 파일 못 찾음 | HF_HOME·JSON 경로 | 캐시와 보정 분리·명시 경로 | 시작 전 파일 검사 |
| 9 | 모든 보정 범위 2047 | calibration 출력 | 잘못된 신규 측정 폐기 | 정상 기존 JSON 유지 |
| 10 | c 입력으로 재보정 진입 | CLI 동작 | 저장값 자동 적용·일치 검사 | 오입력 방지 |
| 11 | FRONT 이름과 SIDE 구도 불일치 | 실제 영상·feature | 폴더·stats·Parquet 참조 통합 변경 | 25시연 실제 loader 확인 |
| 12 | depth raw/mm 불일치 | 실제 depth_scale·encoder 계약 | raw→mm 변환 | 현재 장치 scale 사용 |
| 13 | 저장 후 긴 영상 변환 | 저장 흐름 | streaming·백그라운드 save | 큐 처리량 문제를 후속 발견 |
| 14 | depth 3~11frame 부족 | 실제 디코딩·큐 코드 | CPU 여유·queue 300·drop 폐기 | 불량 시연 제거·재인덱싱 |
| 15 | NVENC 목록은 있으나 open 실패 | avcodec_open2 | 당시 CPU ultrafast로 우회 | 작은 세 스트림 시험 통과 |
| 16 | 정상 shared MP4를 불량 판정 | episode timestamp 구간 | 파일 전체 아닌 구간 검사 | 49시연 오류 0 |
| 17 | 중단 꼬리 row 존재 | 커밋 meta와 actual row 대조 | 미커밋 tail 정리 | 100시연 정상 기준 확정 |
| 18 | 손으로 매번 녹화 조작 | 시연 운영 흐름 | HOME 상태기계·f/q·자동 반복 | 시작 HOME 즉시 저장 차단 |
| 19 | 모터 피드백 읽기 비용 | ms 프로파일 | 연속 23B block read | 4.011→2.413ms |
| 20 | 22FPS 때문에 반복 폐기 | 카메라 신규율·루프 FPS | 최신 영상 재표본화 | 반복 통계와 저장 누락 분리 |
| 21 | 52~57ms skew로 정상 시연 폐기 | 시연 품질 통계 | 50→100ms 허용 | 나이·FPS·누락 기준 유지 |
| 22 | 과거 전체 검사 대기 증가 | 57시연 검사 시간 | 새 episode 선택 검사·병렬화 | 514frame 검사 4.938초 |
| 23 | 노출 시험 뒤 과노출 | 모드·실제 화면·재연결 | 자동 노출 복원 | 원래 모드 보존 필요 학습 |
| 24 | 2K 저장 뒤 Windows 중단 | 번호 checkpoint 파일 검사 | last symlink 실패 비치명 처리 | 20K까지 재개 완료 |
| 25 | 평균 오차 뒤 gripper 문제 | 축별 범위·구간 MAE | 중요 구간 분석·안전 제한 | 독립 성능 검증 아님 |
| 26 | 상승과 닫힘 중첩 | action 정렬·실습 영상 | 데이터/실행의 동시 목표 구조 분석 | 힘·접촉 확인 제어는 없음 |
| 27 | v1 실물 추적 저하 | 사용자 보고·오프라인 대비 | 원본 해상도·파지 지표 등 재설계 | 단일 실패 원인 미확정 |
| 28 | v2 첫 AMP gradient 비정상 | 작은 update 재현 | scale 65536→1024·skip·중단 | 2update/8검사, 본 학습 아님 |
| 29 | 서버 TorchCodec ABI 실패 | 내부 심볼·FFmpeg 개발 파일 | 현재 torch 대상 소스 wheel build | VideoDecoder·GPU 검증 |
| 30 | 홈 200GiB로 데이터 수용 불가 | 파일시스템·권한·용량 | Lustre workspace·venv 재구성 | 230GiB 전송 경로 확보 |
| 31 | 마지막 구간 편중 val 우려 | sessions 13그룹 | 고정 그룹 내 분할 | 449/50, 중복 0 |
| 32 | val 통계 유입 가능 | stats 연결 | train 전용 aggregate | train_stats 보존 |
| 33 | config/spawn 오류 | 공식 필드·stdin 경로 | 옵션 수정·workers0 | 작은 공식 학습 성공 |
| 34 | 검증이 멈춘 듯 보임 | CPU·GPU·평가 frame 수 | workers4·학습/평가 시간 분리 | 10step+전체 val 완료 |
| 35 | 모델 미사용 depth I/O | 로더 feature 목록 | 메모리 depth 제거 패치 안내 | 서버 최종 적용 로그는 불충분 |
| 36 | GPU 프로세스 2개 | ps 전체 명령·PPID | 과거 학습 TERM 후 재확인 | 본체 1개 유지 |
| 37 | 큰 batch도 느린 체감 | data_s/updt_s/smp/s | step당 시간 대신 처리량·학습량 해석 | 162~170sample/s 일부 로그 |
| 38 | checkpoint가 많아 최선 불명 | 50개 구조·hash 감사 | last와 best 구분·동일 표본 평가 | 047000 선택 |
| 39 | 카메라 open 실패 | 장치 열거·모드 분리 | 교체 serial 설정 통합 | RGB·RGBD 수신 확인 |
| 40 | 무손실 전환 위험 | 모든 pixel hash·timestamp | staged 변환·원본 backup·rollback | 과거 손실 복원은 아님 |
| 41 | encoder 초기화로 첫 frame 지연 | 시작 흐름·코드 | PREP에서 초기화 | 장기 장비 성능은 후속 확인 |
| 42 | 저장 후 stale camera | host 나이·source 이름 | 80ms 여유·200ms 갱신 대기 | 오래된 영상 기록 차단 |
| 43 | 복구·저장 객체 반복 비용 | 파일 수·writer 흐름 | hard link·shard 회전·객체 재사용 | 현재 구현, 전체 수집 실측 필요 |

## 17. 명령·스크립트 찾아보기

실제 실행 조건과 출력 경로를 확인하며 사용한다. 아래는 이번 문서 작성 중 실행한 작업 목록이 아니라 **프로젝트를 설명하기 위한 명령 색인**이다.

| 목적 | 명령/도구 | 부작용·확인 범위 |
|---|---|---|
| Python 위치 | `python -c "import sys; print(sys.executable)"` | 읽기 |
| SDK 위치 | `python -c "import scservo_sdk; print(scservo_sdk.__file__)"` | 읽기 |
| venv pip 복구 | `.venv\Scripts\python.exe -m ensurepip --upgrade` | 환경 변경 |
| 대상 venv 설치 | `uv pip install --python ... -e "...lerobot[feetech]"` | 패키지 변경 |
| 전체 환경 | `scripts/verify_environment.py` | 데이터 로딩·샘플 출력, 최초 다운로드 가능 |
| 모터 ID/baud | `FeetechMotorsBus.scan_port('COM3'/'COM4')` | serial 장치 열기·읽기 |
| 전압 | `read1ByteTxRx(port, 1, 62)` 및 `v/10` | 당시 ID1 전압 피드백 |
| 조작 옵션 | `lerobot-teleoperate ... --help` | CLI 문서 확인 |
| 실제 원격 조작 | 본문 4.5의 teleoperate 명령 | 실제 모터 동작 |
| 일반 카메라 점검 | `scripts/camera_test.py` | 카메라 연결, 인자는 help 확인 |
| B200 카메라 점검 | `experiments/doll_B200_act/check_realsense.py` | 카메라 연결, 모터 미연결 |
| 수동 시연 | `manual_data_collection/record_5_episodes.py` | 장비·파일 변경, 초기 단계 도구 |
| 초기 자동 수집 | `auto_home_collection/auto_home_record.py` | 장비·데이터 쓰기, 현재 본 수집과 동시 실행 금지 |
| 현재 본 수집 | `.venv\Scripts\python.exe collection\collect.py` | 작업 선택 GUI·장비·저장 |
| 수집 품질 | `collection/quality.py` | 독립 CLI 아닌 내부 검증 모듈 |
| 용량 집계 | `scripts/dataset_sizes.py` | 데이터 유형별 저장량 읽기 |
| 무손실 이전 | `scripts/migrate_rgb_lossless.py` | 영상 교체·backup·rollback |
| 첫 ACT smoke | `train_act.py --steps 1 --save-freq 1 --output-dir ...` | 실제 GPU update·저장 |
| 첫 ACT 본 학습 | `train_act.py --steps 20000 --batch-size 4` | 실제 학습·출력 쓰기 |
| 100시연 평가 | `validate_act_model.ipynb` | 모델·영상·오차 분석 |
| 서버 자원 | `nvidia-smi`, `whoami`, `hostname`, `uname -s` | 시스템 읽기 |
| 서버 본체 확인 | `ps -ww -p <확인한PID들> -o pid,ppid,etime,stat,args` | 프로세스 읽기, PID는 현재 값 확인 |
| B200 모델 선택 | `select_checkpoint.py --full-comparison` | 50모델 GPU 평가·결과 쓰기 |
| 선택 모델 preflight | `run_selected.py` | 모델·메타·보정 읽기, 모터 미연결 |
| 선택 모델 실물 | `run_selected.py --run` | 연결 후 SPACE로 동작 |
| 공식 rollout | `run_act.py --model ... --dataset ... --execute` | 연결 후 제어 시작, SPACE 대기 아님 |

과거 서버 주소·SSH 포트·개인키는 보고서에 넣지 않았다. scp도 실제 설정에 맞는 SSH 별칭을 사용해야 한다. 데이터 전송과 모델 결과 반환은 수행 이력이 확인되지만, 당시 전체 명령의 민감한 접속 인자를 공개 문서에 재현하지 않는다.

## 18. 시간순 이력

| 시점 | 확인된 주요 진행 |
|---|---|
| 9월 7~8일 기록 | Windows/venv/LeRobot·공개 데이터 확인, SO-101 serial·전압·보정·추종 |
| 9월 11일 | TOP/FRONT 두 카메라와 teleoperation 통합, 작은 시연 수집 설계·검증 |
| 9월 15~21일 | SIDE 전환, RGB-D 자동 수집, depth 단위·streaming·HOME·재개 검사 |
| 9월 21일 | 25시연/13,647frame 파일럿 검증·용량 분석 |
| 9월 22일 | SIDE key migration, 보정 경로 수정, depth 누락 복구·shared MP4 검사 수정 |
| 9월 22일 이후 | 100시연/56,768frame, ACT 20K 학습, 2K symlink 복구 |
| 9월 23일 기준 보고서 | 학습·오프라인·실습 영상 및 파지 시점 분석 |
| 10월 1일 | 초기 ACT 결과 요약·본 수집 schema4 정리 |
| 10월 2일 | block read·재표본화·skew 기준·저장 검사 비용 개선 |
| 10월 초~8일 기록 | 인형499·컵102 데이터, v1 비교·실물 저하, v2 수치 진단·작은 검사 |
| 10월 7~8일 | 웹캠22FPS·반복·노출 복원 문제 분석 |
| 10월 12~13일 | B200 SSH·NVIDIA torch 보존·TorchCodec build·workspace·전송·분할·정규화 |
| 10월 13일 | 10step+전체 val 검증, depth 로딩 제거 요청, batch64 로그·중복 본체 정리 |
| 10월 14일 | 50K 산출물 감사·동일500관측 50모델 비교·047000 선택·새 D405 반영 |
| 10월 14일 기록 | 사용자 B200 성공 확인·폐기 전 초기 실험 근거 보존 |
| 현재 코드 기준 | 무손실 RGB·검사 분리·복구·encoder 초기화·저장 객체 재사용 개선 |

날짜는 파일 작성 시각만으로 조작 수행일을 만들어 넣지 않고 연구 로그·대화에 명시된 범위를 따른다. 특히 “9월 23일 기준 보고서”와 “10월 1일 요약”은 동일 초기 실험의 서로 다른 기록 시점이다.

## 19. 근거 자료 색인

### 19.1 로컬 주요 문서

| ID | 자료 | 본문에서 쓰인 근거 |
|---|---|---|
| E01 | [environment.md](environment.md) | 로컬 설치 버전·실패·공개 데이터 |
| E02 | [so101_run_commands.md](so101_run_commands.md) | 환경·SDK·포트·복구 명령 |
| E03 | [research_log_1.md](research_log_1.md) | 하드웨어·파일럿·depth·초기ACT |
| E04 | [research_log_2.md](research_log_2.md) | 본 수집·품질·성능·웹캠 |
| E05 | [research_log_3.md](research_log_3.md) | B200 환경·전송·검증 준비 |
| E06 | [act_failed_experiments_review.md](act_failed_experiments_review.md) | 삭제 전 v1/v2·준비 코드·hash·성공 확인 |
| E07 | [01_model_training.md](../episode_sample_dataset/doll_pickplace_act/doll_pickplace_act_testreport/01_model_training.md) | 초기100시연 구성·학습 |
| E08 | [02_model_evaluation.md](../episode_sample_dataset/doll_pickplace_act/doll_pickplace_act_testreport/02_model_evaluation.md) | 초기 오프라인 검사 |
| E09 | [03_execution_analysis.md](../episode_sample_dataset/doll_pickplace_act/doll_pickplace_act_testreport/03_execution_analysis.md) | 실습 영상·닫힘 시점·인과 한계 |
| E10 | [collection/README.md](../collection/README.md) | 현재 수집 흐름·후속 개선 |
| E11 | [B200 README](../experiments/doll_B200_act/README.md) | 선택 평가·실행 계약 |

### 19.2 코드·설정·측정 결과

| ID | 자료 | 확인할 항목 |
|---|---|---|
| E12 | [collection/core.py](../collection/core.py) | 상태기계·manifest·잠금·복구·run |
| E13 | [collection/quality.py](../collection/quality.py) | capture·시간·depth·영상 검사 |
| E14 | [collection/collect.py](../collection/collect.py) | GUI·worker·명령·상태 |
| E15 | [collection/settings.json](../collection/settings.json) | 현재 장비·HOME·시간·codec |
| E16 | [Follower JSON](../robot_calibration/robots/so_follower/follower.json), [Leader JSON](../robot_calibration/teleoperators/so_leader/leader.json) | 6축 id·offset·range |
| E17 | [Feetech bus](../lerobot/src/lerobot/motors/feetech/feetech.py) | sync_read_registers |
| E18 | [Follower driver](../lerobot/src/lerobot/robots/so_follower/so_follower.py) | 설정·송신 재시도 |
| E19 | [video_utils.py](../lerobot/src/lerobot/datasets/video_utils.py) | streaming·encoder·drop |
| E20 | [dataset_writer.py](../lerobot/src/lerobot/datasets/dataset_writer.py) | streaming 준비·shard·checkpoint_recording |
| E21 | [train_utils.py](../lerobot/src/lerobot/common/train_utils.py) | 저장·재개·last symlink |
| E22 | [motor_read_profile.json](../collection/reports/motor_read_profile.json) | 4.011→2.413ms |
| E23 | [capture_read_profile.json](../collection/reports/capture_read_profile.json) | 90주기29.99FPS·범위 |
| E24 | [save_validation_before.json](../collection/reports/save_validation_before.json), [after.json](../collection/reports/save_validation_after.json) | 검사 비용·347파일 불변 |
| E25 | [depth_encoding_profile.json](../collection/reports/depth_encoding_profile.json) | depth120frame encode |
| E26 | [lossless_gpu_profile.json](../collection/reports/lossless_gpu_profile.json) | RGB60frame pixel 비교 |
| E27 | [latest_tests.txt](../collection/reports/latest_tests.txt) | 당시 41검사 통과 기록 |
| E28 | [doll_transfer_manifest.json](../doll_transfer_manifest.json) | 전송 파일 경로·바이트 |
| E29 | [checkpoint_audit.json](../experiments/doll_B200_act/checkpoint_audit.json) | 50K·50모델·최종설정·구조 |
| E30 | [split.json](../experiments/doll_B200_act/act_doll_basic/split.json), [train_stats.json](../experiments/doll_B200_act/act_doll_basic/train_stats.json) | 고정 분할·train 통계 |
| E31 | [최종 train_config.json](../experiments/doll_B200_act/act_doll_basic/checkpoints/050000/pretrained_model/train_config.json) | 실제 batch64/workers7/FP32 |
| E32 | [select_checkpoint.py](../experiments/doll_B200_act/select_checkpoint.py) | 평가 sample·mask·집계 |
| E33 | [anchors.json](../experiments/doll_B200_act/selection/anchors.json), [scores.csv](../experiments/doll_B200_act/selection/scores.csv), [selected_checkpoint.json](../experiments/doll_B200_act/selection/selected_checkpoint.json) | 동일 관측·평가·선택 |
| E34 | [run_selected.py](../experiments/doll_B200_act/run_selected.py) | 선택·processor·FP32·장비 설정 |
| E35 | [run_act.py](../experiments/doll_B200_act/run_act.py) | 공식 rollout 경로 |
| E36 | [run_act_pickplace_safe.py](../episode_sample_dataset/doll_pickplace_act/run_act_pickplace_safe.py) | 비동기 계획·제한·HOME |
| E37 | [migrate_rgb_lossless.py](../scripts/migrate_rgb_lossless.py) | 픽셀·시간·백업·rollback |
| E38 | [종이컵 저장 감사](../collection/reports/pick_paper_cup_storage_audit.md) | RGB전수/depth표본·pending 구분 |

### 19.3 이전 대화 근거

| 채팅 | ID | 보완한 내용 |
|---|---|---|
| B200에서 LeRobot ACT 학습 준비 | `01a12e84-3ef5-7d52-b17a-fb4cfa008a2c` | depth 로더 제거 패치 안내, 실제 batch64 로그, 중복 PID 확인·종료, 감사·선택·카메라 교체 |
| 실행 코드 표준 파이프라인 구성 | `01a1340a-6425-74d2-afa8-ebdb9e04efc9` | 공식 rollout 설계·검사·실험 폴더로 이동 |

대화 전체를 보고서에 복사하지 않았고, 접속 주소·키 같은 불필요한 정보는 재기재하지 않았다. 당시 기록의 완료 범위와 사용자 제공 로그만을 해당 주장에 사용했다.

### 19.4 외부 출처

- 사용자 실제 참고 자료: [위키독스 2.5 칼리브레이션](https://wikidocs.net/385994). 해당 페이지에 연결된 [실습 영상](https://www.youtube.com/watch?v=vDS5eLKd9lM).
- 이론 연결: [ACT 원 논문 프로젝트 페이지](https://tonyzhaozh.github.io/aloha/), [논문 arXiv](https://arxiv.org/abs/2304.13705).
- 구현 자료: [LeRobot ACT 안내](https://huggingface.co/docs/lerobot/act), [SO-101 안내](https://huggingface.co/docs/lerobot/so101). 웹 문서는 변할 수 있으므로 실제 설정은 로컬 v0.6.1을 우선했다.
- 버전 고정 소스: [LeRobot v0.6.1 ACT](https://github.com/huggingface/lerobot/blob/v0.6.1/src/lerobot/policies/act/modeling_act.py), [공식 trainer](https://github.com/huggingface/lerobot/blob/v0.6.1/src/lerobot/scripts/lerobot_train.py), [데이터 factory](https://github.com/huggingface/lerobot/blob/v0.6.1/src/lerobot/datasets/factory.py).
- 바이너리 대응: [TorchCodec v0.10.0](https://github.com/meta-pytorch/torchcodec/tree/v0.10.0).
- 회사 맥락: [IR Solutions](https://ir-solutions.co.kr/), 2026-10-15 조회. 직무 공고는 확인하지 못함.

## 20. 아직 문서로 확정할 수 없는 내용

이 문서는 확인 가능한 사실을 충분히 모아 다음 이력서의 근거를 만드는 것이 목적이다. 아래 항목은 사실을 과장하지 않기 위한 구체적인 공백 목록이다.

- 최초 논문 분석의 날짜·발췌·개인 해석 원문. ACT 설명은 구현에 연결한 복원 분석이다.
- 위키독스 연결 영상 외 추가로 시청한 모든 영상의 목록·순서.
- 초기 Follower ID6 미검출을 해결한 정확한 조작·모터 ID 재설정 여부.
- 모든 모터의 개별 전압·부하 전류·전원 장치 계측. 남은 전압 명령은 포트별 ID1 읽기다.
- 간헐 패킷 오류의 케이블·USB·전원 중 최종 물리 원인.
- 삭제된 v1/v2 코드 전체의 현재 실행 검증. 보존 문서의 설정·일부 코드·hash를 근거로 했다.
- 서버 본 학습에서 depth 메모리 제거 패치의 최종 적용 화면·현재 서버 파일 확인.
- 모든 중간 batch/workers 수정 명령과 전체 학습·검증 loss 곡선.
- 로컬 전송 데이터 전체 내용 hash 일치. 당시 비교는 상대 경로·크기다.
- 최종 성공 시도별 위치·영상·명령·코드 리비전·checkpoint 대응표.
- 전체 시도 수가 있는 성공률, first-attempt 성공률, 장기 고장률.
- 모터 입력 추가·해상도·FP32·배치·재계획 중 단일 요소의 성공 기여도.
- 현재 후속 수집 최적화의 장시간 실장비 30FPS·저장 대기 결과.
- SmolVLA·GR00T·Isaac·다중 작업 정책·DOFBOT 정책 이식의 완료 성과. 현재 자료로는 계획 또는 별도 관련 경험이다.

이 공백이 남아 있어도, 환경을 재현하고 장비를 확인하고 수집·학습·실행을 관측 결과에 따라 계속 고쳐 온 과정은 충분히 구체적으로 설명할 수 있다. 앞으로 새 실험을 할 때는 위 공백을 줄이는 기록을 먼저 남기면 같은 시행착오가 다음 개선의 더 강한 근거가 된다.




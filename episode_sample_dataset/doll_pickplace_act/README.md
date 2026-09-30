# SO-101 Doll Pick-and-Place ACT

현재 로컬 SO-101 인형 픽앤플레이스 데이터셋으로 LeRobot ACT 정책을 학습하는 샘플이다.

## 검증된 데이터

- dataset: `../auto_home_collection/auto_home_dataset`
- episodes: 100
- frames: 56,768
- fps: 30
- task: 인형을 집어 지정 영역에 놓고 홈 자세로 복귀

## ACT 입출력

- input: `observation.state`, `observation.images.top`, `observation.images.side`
- output: `action` (SO-101 6 joints)
- `observation.images.top_depth`는 원본 데이터에 보존되지만, 기본 ResNet18 ACT가 동일한 3채널 영상 입력을 전제로 하므로 이번 학습 입력에서는 제외한다.

## 권장 학습

```powershell
& D:\lerobot-2026\.venv\Scripts\python.exe `
  D:\lerobot-2026\episode_sample_dataset\doll_pickplace_act\train_act.py `
  --steps 20000 `
  --batch-size 4
```

기본 출력은 `outputs/act_100ep_20k`이며 2,000 step마다 체크포인트를 저장한다. 외부 Hub나 WandB에는 업로드하지 않는다.

## 빠른 동작 확인

```powershell
& D:\lerobot-2026\.venv\Scripts\python.exe `
  D:\lerobot-2026\episode_sample_dataset\doll_pickplace_act\train_act.py `
  --steps 1 `
  --save-freq 1 `
  --output-dir D:\lerobot-2026\episode_sample_dataset\doll_pickplace_act\outputs\smoke_test
```

## 모델 검증

실행 결과가 저장된 노트북은 `validate_act_model.ipynb`이다. 체크포인트 무결성,
학습 곡선, 카메라 표본, 관절별 오차와 100-frame 예측 궤적을 포함한다.

## 안전 실행

실행 코드는 `run_act_pickplace_safe.py`이다. 인자 없이 실행하면 로봇과
RGB 카메라가 연결된다. OpenCV 창에서 `SPACE`를 누르면 실제 모터 동작이 시작된다.
`Q`는 HOME 복귀 후 종료, `E`는 즉시 토크 해제이다.

```powershell
& D:\lerobot-2026\.venv\Scripts\python.exe `
  D:\lerobot-2026\episode_sample_dataset\doll_pickplace_act\run_act_pickplace_safe.py
```

모델·데이터·보정 파일만 확인할 때는 사전점검을 실행한다. 이 옵션은
로봇을 연결하지 않는다.

```powershell
& D:\lerobot-2026\.venv\Scripts\python.exe `
  D:\lerobot-2026\episode_sample_dataset\doll_pickplace_act\run_act_pickplace_safe.py `
  --preflight-only
```

안전 장치:

- 기본 60 frame마다 GPU 백그라운드에서 새 관측으로 비동기 재추론
- 추론 중에도 30 FPS 모터 제어를 계속해 주기적인 멈춤 제거
- 새 action chunk로 전환할 때 팔 관절은 처음 8 frame만 보간
- 그리퍼 닫힘은 기본 8 frame 선행시키고, 열림은 원래 예측 시점에 실행
- `--replan-every` 조정 범위는 50~75 frame
- 데이터셋에서 시연된 관절별 최소·최대 범위로 절대 명령 제한
- 관절별 한 프레임 최대 이동량을 2~5도로 완화
- 이전 전송 목표를 기준으로 명령을 누적하되 실제 관절보다 최대 10도까지만 앞서도록 제한
- shoulder lift, elbow flex, wrist flex에 완화된 4초 stall 감지 적용
- stall 감지 시 토크를 끄지 않고 현재 자세 유지 상태로 일시정지
- `Q`, 타임아웃, stall 종료 및 복구 가능한 오류는 고정 HOME 복귀 후 토크 해제
- HOME 복귀 실패 시 현재 자세를 유지하고 사용자가 팔을 받친 뒤에만 토크 해제
- 통신 불능 또는 `E` 비상정지는 HOME 복귀 없이 즉시 토크 해제
- NaN/Inf, 과도한 범위 이탈, 비정상 관절 상태, 추론 지연 감시
- 시작 HOME 확인과 최대 60초 타임아웃
- `P` 일시정지, `Q` 정지, `E` 즉시 토크 해제

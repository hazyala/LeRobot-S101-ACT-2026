# Episode Sample Dataset

SO-101으로 첫 Pick & Place 샘플 데이터를 수집하기 위한 폴더입니다.

## 폴더 구조

```text
D:\lerobot-2026\episode_sample_dataset
├─ manual_data_collection
│  ├─ dataset
│  ├─ validation_frames
│  ├─ record_5_episodes.py
│  └─ validate_dataset.py
├─ auto_home_collection
│  └─ auto_home_record.py
├─ test_top_exposure.py
└─ README.md
```

- `manual_data_collection`: Enter로 시작/종료해서 수동으로 만든 5 episode 샘플 데이터
- `auto_home_collection`: 고정 홈 포지션 복귀를 기준으로 자동 저장/폐기하는 RGB-D 수집 폴더
- `test_top_exposure.py`: TOP 카메라 노출 확인용 스크립트

## Episode 설계

- 작업 목표: 테이블 위 물건을 집어서 고정된 박스 안에 넣기
- 박스: 5개 episode 동안 같은 위치에 고정
- 물건: episode마다 시작 위치를 조금씩 바꾸기
- TOP 카메라: 물건 위치, gripper 접근, grasp, 이동 경로 확인
- SIDE 카메라: 그리퍼의 접근·파지와 물체의 높이·안착 상태 확인

## 추천 5 Episode

1. 물건을 로봇 정면 중앙의 닿기 쉬운 위치에 둡니다.
2. 물건을 중앙보다 약간 왼쪽에 둡니다.
3. 물건을 중앙보다 약간 오른쪽에 둡니다.
4. 물건을 박스에 조금 가까운 위치에 둡니다.
5. 물건을 박스에서 조금 먼 위치에 둡니다. 단, 로봇이 무리 없이 닿아야 합니다.

## 실행 방법

PowerShell에서 실행합니다.

수동 5 episode 수집:

```powershell
cd "D:\lerobot-2026\episode_sample_dataset\manual_data_collection"
D:\lerobot-2026\.venv\Scripts\python.exe .\record_5_episodes.py
```

홈 포지션 복귀를 기준으로 자동 수집하려면:

```powershell
cd "D:\lerobot-2026\episode_sample_dataset\auto_home_collection"
D:\lerobot-2026\.venv\Scripts\python.exe .\auto_home_record.py
```

자동 수집 모드는 스크립트에 고정된 홈 포지션을 기준으로 동작합니다. D405 TOP 카메라는 RGB와 depth를 함께 저장하고, SIDE webcam은 RGB만 저장합니다. D405의 0.1 mm raw depth는 LeRobot이 기대하는 mm 단위로 변환되며, 세 영상 스트림은 녹화 중 실시간으로 인코딩되어 episode 종료 후 저장 대기 시간을 줄입니다. 이후에는 `5초 준비 -> START 1초 -> 녹화 -> 홈 복귀 2초 감지 -> 저장/폐기`를 반복합니다.

Leader/Follower 보정값은 Hugging Face 캐시와 분리된 `D:\lerobot-2026\robot_calibration`에서 읽습니다. 수집기는 장비 연결 전에 보정 파일의 존재와 관절 범위를 검사하며, 파일이 없거나 손상된 경우 자동 calibration으로 넘어가지 않고 종료합니다.

기존 `auto_home_dataset`이 있으면 실행 초기에 선택합니다.

```text
y     = 기존 데이터셋을 검증하고 다음 episode부터 이어서 수집
reset = 기존 데이터셋을 전부 삭제하고 1번 episode부터 새로 수집
```

`y`로 이어서 수집하면 먼저 미완성 마지막 저장 흔적을 자동 정리하고, episode 메타데이터, 수치 프레임, TOP/SIDE/depth 영상 존재 여부와 프레임 수를 검사합니다. 이상이 있으면 해당 episode와 원인을 출력하고 장비 연결 전에 종료합니다. 검사를 통과하면 저장된 episode 수 다음 번호부터 시작합니다. 예를 들어 이미 8개가 저장되어 있으면 다음 화면은 `EP 9`로 시작합니다.

depth feature가 없는 RGB-only 데이터셋이나 D405 depth 단위 보정 이전 데이터셋은 `y` 검증에서 구체적인 원인을 출력하고 중단됩니다. 전부 지우고 새 RGB-D 데이터셋을 만들 때만 `reset`을 입력합니다.

OpenCV 창에서:

```text
f = 현재 episode 즉시 폐기, 10초 준비 후 같은 episode 번호로 재시작
q = 종료
```

조작 방식:

```text
Episode 1 시작: 물건 배치 후 Enter
Episode 1 종료/저장: 다시 Enter
Episode 2 시작: 물건 배치 후 Enter
Episode 2 종료/저장: 다시 Enter
...
Episode 5까지 반복
```

데이터셋 저장 위치:

```text
수동 수집:
D:\lerobot-2026\episode_sample_dataset\manual_data_collection\dataset

자동 홈 수집:
D:\lerobot-2026\episode_sample_dataset\auto_home_collection\auto_home_dataset
```

자동 홈 수집 데이터에는 다음 이미지 feature가 들어갑니다.

```text
observation.images.top        # D405 RGB
observation.images.top_depth  # D405 depth
observation.images.side       # SIDE webcam RGB
```

## 성공 기준

- 5개 episode가 저장됩니다.
- 각 episode에 `observation.images.top`, `observation.images.side`, `observation.images.top_depth`, `observation.state`, `action`이 들어 있습니다.
- 모든 episode는 성공 시연이어야 합니다.
- 중요한 순간에 gripper, 물건, 박스가 TOP/SIDE 카메라 중 적어도 필요한 화면에 보여야 합니다.

## 한 Episode의 흐름

1. 물건을 박스 밖 테이블 위에 둡니다.
2. 녹화가 시작되면 Leader로 Follower를 조작해 물건에 접근합니다.
3. gripper로 물건을 잡습니다.
4. 물건을 들어 올려 박스 쪽으로 이동합니다.
5. 박스 안에 물건을 내려놓습니다.
6. gripper를 열어 물건을 놓습니다.
7. 로봇팔을 박스 밖으로 살짝 빼고 episode를 끝냅니다.

## 주의사항

- 처음부터 물건을 박스 안에 두지 않습니다.
- 박스 위치는 바꾸지 않습니다.
- 물건 시작 위치만 조금씩 바꿉니다.
- 실패한 시연은 학습 데이터로 쓰지 않는 것이 좋습니다.
- TOP 카메라에는 집는 과정이 보여야 합니다.
- SIDE 카메라에는 접근·파지·들어 올림과 목표 영역 안착 과정이 보여야 합니다.

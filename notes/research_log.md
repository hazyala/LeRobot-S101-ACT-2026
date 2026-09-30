# LeRobot SO101 Research Log

## 2026-09-08 : Robot Hardware & Teleoperation Check

### 1. Leader / Follower 연결
- Leader 연결
- Follower 연결

### 2. 시리얼 포트 확인
- Leader : `COM4`
- Follower : `COM3`

### 3. 모터 통신 확인

Follower:

```powershell
python -c "from lerobot.motors.feetech import FeetechMotorsBus; print(FeetechMotorsBus.scan_port('COM3'))"
```

결과:

```text
{1000000: [1, 2, 3, 4, 5, 6]}
```

Leader:

```powershell
python -c "from lerobot.motors.feetech import FeetechMotorsBus; print(FeetechMotorsBus.scan_port('COM4'))"
```

결과:

```text
{1000000: [1, 2, 3, 4, 5, 6]}
```

### 4. 관절 ID 확인

| Motor ID | Joint |
|---|---|
| 1 | `shoulder_pan` |
| 2 | `shoulder_lift` |
| 3 | `elbow_flex` |
| 4 | `wrist_flex` |
| 5 | `wrist_roll` |
| 6 | `gripper` |

### 5. 전압 확인

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

확인 결과:

- Leader `COM4` : `5V`
- Follower `COM3` : `12V`

### 6. SO101 Teleoperation 지원 확인

```powershell
lerobot-teleoperate --help
```

확인 결과:

- `so101_leader` 지원
- `so101_follower` 지원

### 7. Leader / Follower Teleoperation 옵션 확인

```powershell
lerobot-teleoperate --teleop.type=so101_leader --robot.type=so101_follower --help
```

확인된 옵션:

```text
Leader
--teleop.type=so101_leader
--teleop.port=...

Follower
--robot.type=so101_follower
--robot.port=...
```

### 8. Leader / Follower ID 지정

```text
COM4 = leader
COM3 = follower
```

### 9. Calibration 및 Teleoperation 테스트

```powershell
lerobot-teleoperate --teleop.type=so101_leader --teleop.port=COM4 --teleop.id=leader --robot.type=so101_follower --robot.port=COM3 --robot.id=follower
```

#### Leader Calibration 결과

```text
-------------------------------------------
NAME            |    MIN |    POS |    MAX
shoulder_pan    |    672 |   2067 |   3274
shoulder_lift   |    853 |    946 |   3236
elbow_flex      |    780 |   3146 |   3149
wrist_flex      |    956 |   2830 |   3232
gripper         |   2030 |   2040 |   3264
```

#### Follower Calibration 결과

```text
-------------------------------------------
NAME            |    MIN |    POS |    MAX
shoulder_pan    |    677 |   2026 |   3423
shoulder_lift   |    743 |    918 |   3348
elbow_flex      |    682 |   3095 |   3095
wrist_flex      |    808 |   2692 |   3175
gripper         |   2031 |   2042 |   3546
```

### 10. Leader → Follower 가동 테스트

```powershell
lerobot-teleoperate --teleop.type=so101_leader --teleop.port=COM4 --teleop.id=leader --robot.type=so101_follower --robot.port=COM3 --robot.id=follower --fps=30 --robot.num_read_retries=10 --robot.max_relative_target=5
```

확인 결과:

- Leader 입력 정상
- Follower 추종 정상
- Teleoperation 동작 확인 완료

### 11. Calibration JSON 확인

Leader:

```powershell
Get-Content D:\lerobot-2026\robot_calibration\teleoperators\so_leader\leader.json
```

Follower:

```powershell
Get-Content D:\lerobot-2026\robot_calibration\robots\so_follower\follower.json
```

### 발견된 문제

Follower 동작 중 간헐적으로 통신 불안정 발생.

주요 오류:

```text
There is no status packet!
Incorrect status packet!
```

추가 확인 결과:

- 모터 ID `1~6` 개별 통신 정상
- 20회 연속 Ping 정상
- 특정 모터 고장보다는 Follower 측 통신 불안정 가능성 있음
- 케이블, USB 포트, 전원 연결 상태 추가 점검 필요

---

## 2026-09-11 : Camera Input & Dataset Recording Test

### 12. Teleoperation 통신 안정성 확인
- 일정 시간 연속 조작 : 5분간 통신 했을때 연속 조작 가능 확인
- 통신 오류 재발 여부 확인 : shoulder_lift와 wrist_flex 에 간헐적 오류 확인

### 13. 카메라 세팅 : Dual-camera setup
1. TOP - View : Realsense D405
```
해상도: 640 x 480
FPS: 30
Color: BGR8 (uint8)
Depth: Z16 (uint16)
깊이 범위: 0.37m ~ 3.13m
깊이 스케일: 0.0001 m/unit
```

2. Front - View (박스 입구를 정면에서 보는 뷰) : Webcam
```
해상도: 640 x 480
FPS: ~30 (자동 감지)
Color: BGR8 (uint8)
```

### 14. Camera + Teleoperation 동시 연결 확인

- Leader 조작: 정상 연결 및 입력 확인
- Follower 추종: 정상 작동 확인
- Camera frame 동시 입력 확인: 정상 확인
  - TOP view: RealSense D405 color frame 입력 확인
  - Front view: Webcam color frame 입력 확인
- LeRobot 통합 실행 확인:
  - `lerobot-teleoperate`에서 SO-101 Leader/Follower + dual camera 동시 연결 성공
  - 30Hz teleoperation loop 3초간 정상 실행
- 비고:
  - Follower 통신 불안정 대응을 위해 `num_read_retries=10`, `num_write_retries=10` 사용
  - 이 단계에서는 Depth를 데이터 수집에 사용하지 않았으며, 이후 자동 RGB-D 수집기에서 활성화함


### 15. Sample Dataset Recording

목표:
- 테이블 위 다양한 위치에 놓인 물건을 집어 고정된 박스 안에 넣는 작업을 5 episode 수집한다.

카메라 역할:
- TOP view: 물건 위치, gripper 접근, grasp, 이동 경로 확인
- Front view: 박스 입구, place 동작, 박스 내부 안착 확인

5 Episode 구성:
- 시작: 박스는 고정 위치, 물건은 episode마다 다른 테이블 위치, gripper는 열린 시작 자세
- 동작: 접근 -> 잡기 -> 들어올리기 -> 박스 방향으로 이동 -> 박스 안에 내려놓기 -> gripper 열기 -> 팔 빼기
- 종료: 물건이 박스 안에 있고 gripper가 물건을 놓은 상태

```
Episode 1: 물건을 로봇 정면 중앙에 둠
Episode 2: 물건을 중앙보다 약간 왼쪽에 둠
Episode 3: 물건을 중앙보다 약간 오른쪽에 둠
Episode 4: 물건을 박스에서 가까운 쪽에 둠
Episode 5: 물건을 박스에서 먼 쪽에 둠
```

Variation:
- 박스 위치는 고정
- 물건 시작 위치만 5개 정도로 변경
- 모든 episode는 성공 시연만 저장

### 16. Sample Dataset 검증
- Episode 저장 여부 확인
- Joint state / action 확인
- Camera frame 확인
- Timestamp 및 데이터 누락 여부 확인

---

## 2026-09-15~21 : RGB-D 자동 수집 환경 안정화

### 17. 카메라 구도 변경

초기 구성은 D405 TOP view와 박스 입구를 정면에서 보는 Webcam FRONT view였다. 실제 Pick & Place 동작을 확인하면서 Webcam을 그리퍼와 물체의 높이, 파지 상태, 목표 영역 안착이 더 잘 보이는 SIDE view로 변경했다.

현재 구성:

| 카메라 | 실제 구도 | LeRobot feature | 역할 |
|---|---|---|---|
| Intel RealSense D405 | TOP | `observation.images.top` | 전체 작업 공간, 시작 위치, 이동 경로, 목표 영역 |
| Intel RealSense D405 | TOP depth | `observation.images.top_depth` | 거리·높이 정보, RGB-D 학습 입력 후보 |
| Webcam | SIDE | `observation.images.side` | 접근, 파지, 들어 올림, 안착, 가림 확인 |

초기에는 `observation.images.front`라는 key를 사용했지만 실제 구도와 맞지 않아, 25개 파일럿 전체의 영상 폴더·메타데이터·episode parquet를 `observation.images.side`로 마이그레이션했다. 수집 코드와 문서도 같은 이름으로 통일했다.

카메라 공통 설정:

```text
해상도: 640 × 480
FPS: 30
TOP RGB: H.264, CRF 23, preset fast
SIDE RGB: H.264, CRF 23, preset fast
TOP depth: HEVC gray12le, lossless, mm, 0~2 m
```

### 18. 물체 배치와 구도 기준

- 로봇 베이스, 목표 컨테이너와 카메라 위치는 고정한다.
- TOP 화면에는 로봇, 시작 물체, 빨간 테이프 영역과 목표 컨테이너가 함께 보여야 한다.
- SIDE 화면에는 그리퍼와 물체가 겹쳐 사라지지 않고, 파지와 안착 여부가 보여야 한다.
- 종이컵 시작 위치는 현재 화면 가장자리보다 TOP·SIDE 양쪽에서 안정적으로 보이는 빨간 테이프 영역 중심으로 통제하는 방향으로 결정했다.
- 본 수집 전 5 episode를 다시 촬영해 물체 가림, 과노출, 목표 영역 이탈을 확인한다.

### 19. Depth 저장 형식 수정

D405는 현재 설정에서 `uint16` raw depth를 0.1 mm 단위로 반환한다. LeRobot depth encoder는 입력을 mm로 해석하므로 저장 전에 다음 변환을 적용했다.

```text
depth_mm = round(depth_raw × 0.1)
```

현재 depth metadata:

```text
depth_unit: mm
video.codec: hevc
video.pix_fmt: gray12le
video.depth_min: 0.0
video.depth_max: 2.0
x265-params: lossless=1
```

일반 미디어 플레이어는 12-bit lossless depth 영상을 정상적인 컬러 영상처럼 재생하지 못할 수 있다. 데이터 자체의 이상 여부는 LeRobot/PyAV로 frame 수와 `uint16` depth 값을 읽어 검증한다.

### 20. 저장 시간 개선

기존 방식은 episode 종료 후 이미지 프레임을 영상으로 변환하면서 대기 시간이 길어질 수 있었다. 현재는 `streaming_encoding=True`를 사용해 녹화 중 RGB와 depth를 바로 인코딩한다.

적용 결과:

- 영구적인 임시 PNG 폴더를 만들지 않음
- episode 종료 후 대량 프레임 인코딩 대기 감소
- RGB는 H.264 `preset=fast`
- depth는 HEVC lossless `preset=fast`
- `save_episode(parallel_encoding=True)`를 백그라운드에서 실행

### 21. 자동 episode 흐름 개선

현재 자동 수집 흐름:

```text
PREP 5초
→ 화면 중앙에 START 1초 표시
→ state/action/TOP/SIDE/depth 기록
→ 작업 후 HOME 복귀
→ HOME 2초 유지 감지
→ 정상 episode 저장
→ 다음 PREP
```

실패 처리:

- `f`: 현재 episode 즉시 폐기
- 실패 episode는 저장하지 않고 10초 준비 후 같은 번호로 재수집
- `q`: 현재 기록 buffer를 정리하고 종료

### 22. 기존 데이터 이어쓰기 안전성 강화

실행 시 선택:

```text
y     = 기존 데이터셋 검증 후 이어서 수집
reset = 기존 데이터셋을 삭제하고 새로 수집
```

`y` 선택 시 장비 연결 전에 다음을 검사한다.

1. `info.json`의 episode/frame 수
2. episode index와 frame index 연속성
3. TOP·SIDE·depth feature와 영상 파일 존재 여부
4. 각 영상의 실제 frame 수와 episode 길이 일치 여부
5. depth 단위와 0~2 m metadata
6. 커밋되지 않은 마지막 episode의 수치 row·영상·임시 폴더

불완전한 마지막 저장 흔적은 자동 정리한다. 이미 커밋된 episode에 이상이 있으면 해당 번호와 원인을 출력하고 이어쓰기를 중단한다. RGB-only 또는 구형 depth-scale 데이터도 자동 이어쓰기하지 않는다.

---

## 2026-09-21 : 25 Episode Pilot Validation

### 23. 수집 결과

현재 자동 Pick & Place 데이터셋:

```text
경로: D:\lerobot-2026\episode_sample_dataset\auto_home_collection\auto_home_dataset
LeRobot codebase version: v3.0
Episodes: 25
Frames: 13,647
FPS: 30
Tasks: 1
평균 episode: 545.88 frames, 약 18.2초
```

저장 feature:

```text
action                          float32 × 6
observation.state               float32 × 6
observation.images.top          RGB video
observation.images.side         SIDE RGB video
observation.images.top_depth    depth video in mm
timestamp / frame_index / episode_index / task_index
```

### 24. 영상·수치 데이터 검증 결과

- 25 episode 모두 메타데이터와 수치 row 확인
- TOP RGB 25개, SIDE RGB 25개, TOP depth 25개 확인
- 총 영상 파일 75개
- 모든 영상의 frame 수가 episode 길이와 일치
- 누락 frame 및 dropped frame 0
- 불완전하게 남아 있던 마지막 추가 episode 흔적 정리 완료

판단: 현재 25개는 수집 파이프라인 검증용 정상 데모로 사용할 수 있다. 다만 본 학습 데이터로 확대하기 전에 종이컵 시작 위치와 SIDE 구도를 완전히 고정해야 한다.

### 25. 저장 용량 분석

```text
전체 데이터셋: 약 2.95 GB
episode당 평균: 약 118.1 MB
TOP RGB 영상: 약 92.68 MB
SIDE RGB 영상: 약 118.61 MB
TOP depth 영상: 약 2,740.22 MB
```

depth가 전체 영상 용량의 약 93%를 차지한다. 현재 품질 검증 단계에서는 lossless depth를 유지하고, 장기 수집 전에 다음 선택지를 별도 비교한다.

1. lossless depth 유지 + 충분한 저장 공간 확보
2. depth 해상도/FPS 축소
3. 필요한 task만 depth 저장
4. 학습 성능 비교 후 depth 제외 여부 결정

2 TB를 현재 구성으로 채울 경우 단순 환산치는 약 16,900 episodes다. 목표는 용량을 채우는 것이 아니라 task 다양성과 성공률에 필요한 유효 episode 수를 확보하는 것으로 수정한다.

### 26. 데이터 폴더 구분

공개 참조 데이터와 자체 수집 데이터가 섞이지 않도록 경로를 분리했다.

```text
Hugging Face 공개 Pick & Place 참조·캐시:
D:\lerobot-2026\hf_pickplace_reference

자체 수집 데이터:
D:\lerobot-2026\episode_sample_dataset
```

`HF_HOME`과 관련 문서·환경 검증 코드도 새 공개 참조 경로로 변경했다.

### 27. 다음 개발 방향

1. 카메라·박스·HOME 자세와 종이컵 시작 영역 최종 고정
2. 동일 조건 5 episode 재시험
3. 현재 25개로 ACT 학습·checkpoint·inference 파이프라인 우선 확인
4. Pick & Place를 50~100개까지 확대하며 25개 단위 검증
5. ACT 실패 유형을 기준으로 필요한 위치만 추가 수집
6. Sorting·Stacking과 고정 language instruction으로 확장
7. 다중 task가 확보되면 SmolVLA 학습 및 ACT와 비교
8. SO101 정책 안정화 후 DOFBOT 이식 여부 결정

---

## 2026-09-22 : SIDE Key Migration & Calibration Path Fix

### 28. 카메라 feature 이름 통일

실제 Webcam 구도는 SIDE인데 기존 자동 수집 데이터에는 `observation.images.front`로 저장되어 있었다. 본 수집 전에 의미를 명확히 하기 위해 기존 25개 전체를 다음과 같이 마이그레이션했다.

```text
observation.images.front
→ observation.images.side
```

변경 범위:

- `meta/info.json` feature key
- `meta/stats.json` 통계 key
- `meta/episodes/...parquet`의 video 참조 열
- `videos/observation.images.front` 폴더
- 자동 수집 코드의 camera/observation key
- README, 로드맵과 리서치 로그

마이그레이션 후 공식 `LeRobotDataset`으로 25 episodes, 13,647 frames와 첫·마지막 SIDE 프레임 `(3, 480, 640)`을 다시 확인했다.

### 29. 캘리브레이션 경로 장애와 수정

`datasets`를 `hf_pickplace_reference`로 변경한 뒤 기존 PowerShell 세션의 `HF_HOME`이 옛 경로를 계속 가리켜, 실행 시 Leader 보정 파일을 찾지 못하고 자동 calibration 화면으로 진입했다. 이때 표시된 모든 관절의 `MIN/POS/MAX = 2047`은 관절 범위를 움직이지 않은 잘못된 신규 측정값이며 사용하지 않았다.

재발 방지 조치:

1. 장비 보정값을 Hugging Face 캐시에서 분리해 `D:\lerobot-2026\robot_calibration`으로 이동
2. 자동 수집 코드에서 Leader/Follower `calibration_dir`을 명시적으로 지정
3. 수집 코드 시작 시 `HF_HOME`, `HF_LEROBOT_HOME`, `HF_LEROBOT_CALIBRATION`을 프로젝트 경로로 고정
4. 장비 연결 전에 leader/follower JSON의 존재, 관절 목록과 min/max 범위를 검사
5. 보정 파일이 없거나 손상되면 자동 재보정을 시작하지 않고 오류를 출력한 뒤 종료
6. 연결 시 LeRobot의 대화형 재보정 질문을 비활성화하고, 검증된 JSON 값을 Leader/Follower 모터에 자동 적용
7. 적용 직후 모터값과 JSON이 일치하는지 다시 검사하며, 불일치하면 데이터 수집 전에 종료

정상 보정 파일은 기존 2026-09-14 측정값을 그대로 유지했다.

2026-09-22 18:58 실행에서는 LeRobot 질문에 `c`를 입력해 신규 보정 절차로 진입했다. 해당 입력은 기존 calibration 사용이 아니라 recalibration 시작을 의미한다. 관절 중앙 위치 확인 전에 `Ctrl+C`로 중단하고, 이후에는 위 자동 적용 로직으로 같은 오입력이 발생하지 않도록 수정했다.

### 30. 26~44번 depth 프레임 유실 확인

2026-09-22 추가 수집 후 재개 검증에서 26~44번 에피소드의 `observation.images.top_depth`가 각 에피소드 기준 3~11프레임 부족한 것을 확인했다. 컨테이너 메타데이터뿐 아니라 실제 디코딩 프레임 수도 동일하게 부족해 단순 검사 오류가 아닌 실데이터 유실이다. RGB top/side와 1~25번, 45~52번의 세 영상 프레임 수는 일치한다.

원인은 LeRobot `StreamingVideoEncoder`의 depth HEVC 인코딩 큐가 가득 찰 때 `queue.Full` 프레임을 버리는 동작이다. 재발 방지로 다음을 반영했다.

1. 최초에는 NVIDIA `h264_nvenc`를 선택했으나 FFmpeg 목록 탐지는 통과하고 실제 `avcodec_open2`에서 실패했다. 런타임 의존성을 제거하기 위해 RGB top/side를 CPU `h264`의 `ultrafast` preset으로 변경해 depth HEVC에 CPU 여유를 확보
2. 카메라별 encoder queue를 60에서 300프레임으로 확대
3. 실행 중 한 프레임이라도 drop이 감지되면 해당 에피소드를 저장하지 않고 같은 번호로 자동 재시도
4. 기존 무결성 검사는 유지해 불완전한 에피소드가 있는 데이터셋의 재개를 차단

사용자 확인 후 LeRobot 공식 `delete_episodes` 경로로 26~44번을 제외하고 재구성했다. 기존 45~52번은 새 26~33번으로 재인덱싱됐으며, 활성 데이터셋은 33 episodes / 17,943 frames / 전수 무결성 오류 0건이다. 활성 경로는 기존과 동일한 `auto_home_dataset`이므로 다음 수집은 34번부터 이어진다.

교체 과정의 원본 영상 백업 `auto_home_dataset_bad_26_44_backup`은 메타데이터가 제거된 영상 전용 사본(약 5.15 GB)으로 남아 있다. 정상 에피소드 영상 사본도 함께 포함하므로 별도 최종 삭제 확인 후 제거한다.

34번 재개 시도에서 위 NVENC 초기화 실패가 발생했으나 episode metadata/frame/video는 커밋되지 않았다. 남은 임시 폴더 2개를 제거한 후 활성 데이터셋은 다시 33 episodes / 17,943 frames / 오류 0건으로 확인했다. 수정된 CPU H.264 ultrafast + depth HEVC 동시 인코딩 시험은 세 스트림 모두 3/3프레임으로 통과했다.

### 31. 공유 MP4 구조에 대한 재개 검사 수정

34~49번 추가 수집 후 검사기가 RGB 파일의 전체 9,196프레임을 각 에피소드 길이와 직접 비교해 모두 오류로 판단했다. 실제로는 재구성 과정에서 `video_files_size_in_mb`가 LeRobot 기본값 200MB로 바뀌면서 여러 에피소드가 하나의 MP4에 연속 저장됐고, 각 episode metadata의 `from_timestamp`/`to_timestamp` 구간은 정확했다. depth 파일의 993·984프레임도 각각 공유된 두 에피소드 길이의 합과 일치했다.

검사기를 다음과 같이 수정했다.

1. MP4 전체 프레임 수와 episode length를 직접 비교하지 않음
2. episode별 `from_timestamp`/`to_timestamp`를 FPS 기준 프레임 구간으로 변환해 length와 비교
3. 같은 파일을 공유하는 구간의 간격·중복과 마지막 구간 끝이 실제 파일 프레임 수와 일치하는지 확인
4. 저장 시간을 일정하게 유지하기 위해 `video_files_size_in_mb`를 다시 1MB로 복원

중단된 미커밋 tail 642 frame rows와 임시 폴더 3개를 제거했다. 최종 상태는 49 episodes / 27,139 frames / 검사 오류 0건이며, 34번 첫 프레임과 49번 마지막 프레임에서 top `(3,480,640)`, top_depth `(1,480,640)`, side `(3,480,640)` 실제 로딩까지 확인했다.

### 32. 100 episodes ACT 학습 시작

수집 완료 후 미커밋 tail 367 frame rows와 임시 폴더 3개를 제거했다. 커밋된 데이터는 100 episodes / 56,768 frames이며 전체 무결성 오류는 0건이다.

LeRobot 공식 ACT tutorial과 `lerobot-train` 파이프라인을 기준으로 `episode_sample_dataset/doll_pickplace_act` 학습 샘플을 구성했다. 기본 ResNet18 ACT는 동일한 3채널 영상 입력을 전제로 하므로 입력은 `observation.state + observation.images.top + observation.images.side`, 출력은 6축 `action`으로 설정했다. 1채널 `top_depth`는 데이터셋에 유지하되 이번 ACT 입력에서는 제외했다.

RTX 3080에서 1-step smoke test와 checkpoint 저장을 통과한 뒤 20,000-step 본 학습을 시작했다. batch size 4, AMP, ImageNet pretrained ResNet18, checkpoint 2,000-step 간격이며 초기 속도 약 6.8 steps/s, GPU memory 2.13 GB, loss는 step 200의 4.10에서 step 560의 2.88로 감소했다.

2,000-step checkpoint 본 저장에서는 Windows가 `checkpoints/last` directory symlink 생성을 거부해 저장 완료 직후 학습이 중단됐다. 번호가 붙은 `002000` checkpoint의 모델(약 207 MB), optimizer(약 413 MB), RNG와 step state는 정상이다. LeRobot의 `update_last_checkpoint`를 수정해 Windows에서 선택적 `last` symlink 실패가 학습을 중단하지 않도록 했고, `002000`에서 optimizer와 데이터 순서를 포함해 정상 재개했다.

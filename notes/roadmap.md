# LeRobot SO101 → ACT → SmolVLA → DOFBOT 로드맵

최종 업데이트: 2026-09-21

상태 표기: ✅ 완료 · 🟡 진행 중 · ⬜ 예정

## 전체 개발 방향

```text
SO101 하드웨어·Teleoperation
→ TOP RGB-D + SIDE RGB 수집 환경 고정
→ LeRobot v3 데이터셋 반복 수집·검증
→ ACT baseline
→ 다중 task 및 language instruction 확장
→ SmolVLA
→ DOFBOT 이식
→ 정책별 성공률·속도 비교 및 최종 데모
```

개발 원칙:

1. 카메라, 박스, HOME 자세와 시작 영역을 먼저 고정한 뒤 데이터 양을 늘린다.
2. 데이터는 25개 단위로 수집하고 수치 프레임과 TOP·SIDE·depth 영상을 함께 검증한다.
3. 현재 Pick & Place에서 ACT baseline을 먼저 확보한 뒤 Sorting·Stacking과 SmolVLA로 확장한다.
4. Hugging Face 공개 참조 데이터와 자체 수집 데이터는 물리적으로 분리한다.

## 현재 진행 상황 요약

| 구분 | 상태 | 현재 결과 |
|---|---:|---|
| SO101 Leader/Follower 연결·보정 | ✅ | Leader `COM4`, Follower `COM3`, 30 Hz teleoperation 확인 |
| 카메라 구성 확정 | ✅ | D405 TOP RGB-D + Webcam SIDE RGB, 640×480, 30 FPS |
| 자동 수집기 안정화 | ✅ | HOME 기반 자동 종료, `START` 표시, 실패 폐기, 이어쓰기 사전 검증 |
| RGB-D LeRobot 데이터 구조 | ✅ | state/action + TOP RGB + SIDE RGB + TOP depth(mm) |
| Pick & Place 파일럿 | ✅ | 25 episodes, 13,647 frames, 영상 75개 |
| 데이터 무결성 검사 | ✅ | TOP·SIDE·depth 프레임 일치, 누락·dropped frame 0 |
| 수집 환경 최종 고정 | 🟡 | 종이컵 시작 위치와 SIDE 시야를 고정한 뒤 본 수집 전환 |
| ACT baseline | ⬜ | 환경 고정 후 25개로 파이프라인 시험, 50~100개로 본 학습 |
| SmolVLA | ⬜ | 다중 task와 language instruction 데이터 확보 후 진행 |
| DOFBOT | ⬜ | SO101 정책 검증 뒤 이식 가능성 평가 |

## 현재 카메라 구도

### TOP — Intel RealSense D405

- 역할: 전체 작업 공간, 물체 시작 위치, 로봇 이동 경로, 목표 영역 확인
- 저장: `observation.images.top` + `observation.images.top_depth`
- 형식: RGB H.264 + depth HEVC lossless
- depth: D405 raw 값을 mm로 변환, 저장 범위 0~2 m
- 구도: 위에서 아래를 보는 탑뷰로 로봇, 시작 물체, 빨간 테이프 영역, 목표 컨테이너가 함께 보이도록 고정

### SIDE — Webcam

- 기존 정면 박스 입구 중심 구도에서 그리퍼와 물체의 높이·파지 상태를 보기 쉬운 사이드뷰로 변경
- 저장 key도 실제 구도에 맞춰 `observation.images.side`로 통일
- 역할: 접근, 파지, 들어 올림, 목표 영역 안착과 가림 여부 확인
- 종이컵 시작 위치는 TOP과 SIDE 양쪽에서 안정적으로 보이는 빨간 테이프 영역 중심으로 통제

카메라 고정 후에는 높이·각도·초점·노출을 바꾸지 않는다. 위치를 변경하면 기존 데이터와 분포가 달라지므로 별도 배치로 기록하고 재검증한다.

## 완료된 단계

### 09-08 — SO101 하드웨어 확인 ✅

1. Leader / Follower 연결 및 포트 확인
2. 모터 1~6 통신 및 관절 ID 확인
3. 전압과 calibration 확인
4. SO101 teleoperation 가동 테스트
5. Follower 통신 재시도 설정 적용

### 09-11 — 카메라 및 수동 샘플 수집 ✅

1. D405 RGB/depth와 Webcam RGB 입력 확인
2. Camera + teleoperation 동시 동작 확인
3. 수동 5 episode 샘플 수집
4. LeRobot 데이터 구조와 영상 재생 검증

### 09-15~09-21 — 자동 RGB-D 수집기 및 파일럿 ✅

1. HOME 복귀 2초 감지 기반 자동 episode 종료
2. 다음 episode 시작 전에 큰 `START` 표시
3. `f` 실패 폐기 및 같은 번호 재수집
4. 녹화 중 streaming encoding으로 종료 후 저장 대기 감소
5. RGB-only·구형 depth 데이터와 불완전 마지막 episode 검출
6. 이어쓰기 시 문제 episode와 원인을 출력하고 안전하게 중단
7. 25개 Pick & Place episode 수집 및 전체 검증

## 다음 단계

### 09-21~09-23 — 수집 조건 최종 고정 🟡

1. 종이컵 시작 위치를 빨간 테이프 영역 안에서 일정하게 유지
2. 목표 컨테이너, 로봇 베이스, 카메라 지지대 위치 표시
3. SIDE 화면에서 시작 물체와 최종 안착이 모두 보이는지 재확인
4. 조명·노출과 HOME 자세 고정
5. 본 수집 전 5 episode 재시험 후 프레임 검증

완료 조건:

- 5/5 성공 시연
- TOP·SIDE·depth 영상 누락 0
- 화면 가림, 과노출, 목표 영역 이탈 없음
- episode 종료 후 다음 수집까지 대기 시간이 작업 흐름을 방해하지 않음

### 09-24~09-30 — Pick & Place 데이터 확대 ⬜

1. 현재 25개를 유지하고 동일 조건으로 50~100개까지 확대
2. 쉬운 중앙 위치에 편중되지 않도록 빨간 영역 내부에서 시작 위치 변화
3. 실패 시연은 즉시 폐기하고 정상 episode만 누적
4. 25개마다 데이터셋 무결성·영상·성공 여부 점검
5. 수집 배치별 카메라/조명/작업 조건 기록 및 백업

### 10-01~10-10 — ACT baseline ⬜

1. 현재 25개 데이터로 학습·checkpoint·inference 파이프라인 우선 검증
2. 50~100개 데이터로 ACT 본 학습
3. 고정된 평가 시작 위치에서 성공률 측정
4. 실패 원인을 접근·파지·이동·안착·복귀로 구분
5. 부족한 상황만 표적 추가 수집

ACT 진행 기준:

- 학습과 checkpoint 재로드 성공
- 실로봇 inference 안전 제한 확인
- 동일 평가 조건에서 반복 성공률 산출 가능

### 10-11~10-20 — 다중 task 데이터 확장 ⬜

1. 인형 Pick & Place와 종이컵 Pick & Place 분리 관리
2. Sorting 및 2·3·4개 Stacking 수집 규칙 확정
3. task별 성공 조건과 실패 폐기 기준 문서화
4. 고정된 language instruction과 `task_index` 연결 검증
5. task별 ACT baseline 비교

### 10-21~10-31 — SmolVLA 준비 및 학습 ⬜

1. language-conditioned 데이터 로딩 확인
2. GPU 학습 환경과 메모리 요구량 점검
3. 소규모 overfit 테스트 후 전체 데이터 학습
4. 문장별 동작 전환, inference latency, 성공률 평가
5. ACT와 SmolVLA의 데이터 효율·성공률·지연 비교

### 11월 — DOFBOT 이식 및 최종 데모 ⬜

1. DOFBOT 관절·카메라·제어 주기 확인
2. SO101 데이터 구조와 DOFBOT observation/action 차이 정리
3. 경량 정책 또는 재수집 필요 여부 판단
4. ACT·SmolVLA·DOFBOT 결과 비교
5. 최종 데모 영상과 코드·README·실험 로그 정리

## 데이터 관리 기준

- Hugging Face 공개 참조 데이터: `D:\lerobot-2026\hf_pickplace_reference`
- SO-101 장비 보정값: `D:\lerobot-2026\robot_calibration`
- 자동 수집기는 대화형 재보정을 금지하고, 위 경로의 검증된 Leader/Follower 보정값을 모터에 자동 복원한 뒤 일치 여부를 확인한다.
- 자체 수집 실험 데이터: `D:\lerobot-2026\episode_sample_dataset`
- 현재 자동 수집 데이터: `D:\lerobot-2026\episode_sample_dataset\auto_home_collection\auto_home_dataset`
- 현재 활성 저장본: 100 episodes / 56,768 frames, 공유 MP4의 episode 구간을 포함한 전수 무결성 오류 0건
- ACT 학습 샘플: `episode_sample_dataset/doll_pickplace_act`, RTX 3080에서 20,000-step 학습 진행(2,000-step마다 checkpoint)
- 실시간 저장은 RGB를 CPU H.264 `ultrafast`로 경량화하고 encoder queue를 300으로 확대했으며, 이후 frame drop 에피소드는 자동 폐기·재시도한다. NVENC는 이 PC에서 목록 탐지만 통과하고 실제 초기화가 실패해 사용하지 않는다.
- 용량의 약 93%가 depth 영상이므로 장기 수집 전 저장 공간과 백업 정책을 함께 확정한다.

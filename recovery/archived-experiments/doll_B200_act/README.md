# B200 인형 ACT 체크포인트 선택과 로컬 실행

학습 결과: `act_doll_basic/`. 원본 체크포인트는 수정하거나 삭제하지 않는다.

## 2026-10-14 선택 결과

50개 체크포인트 모두 같은 검증 50개 에피소드 × 10개 시점(500개 관측)에서 비교했다. 선택 모델은 **047000**, 정규화 행동 MAE **0.196715**다. 다음은 046000(0.198786), 038000(0.199013)이며 마지막 050000은 0.201622였다. 선택 모델은 마지막 모델보다 해당 표본 오차가 약 2.43% 낮았다. 이 수치는 단위 없는 정규화 오차이며 실제 로봇 성공률이 아니다.

로컬 RTX 3080에서 선택 모델·공식 정규화 processor·데이터 메타정보·행동 범위·저장 calibration 검사(PREFLIGHT PASS)를 통과했다. 모델 비교 중 실제 관측에 대한 추론도 수행했다. 실물 로봇은 연결하거나 움직이지 않았다.

## 체크포인트 선택

`select_checkpoint.py --full-comparison`은 저장된 `split.json`의 검증 50개 에피소드에서 각 10개 시점을 균등하게 선택한다. 총 500개 시점에서 모든 번호 체크포인트를 같은 조건으로 비교한다. 원본 TOP/SIDE RGB와 현재 관절 6축을 사용하고 depth는 읽지 않는다.

평가 기준은 정규화된 미래 100프레임 행동의 평균 절대오차(MAE)다. padding은 제외하고 에피소드별 오차를 동일 비중으로 평균한다. CVAE 잠재값은 실제 추론과 같은 z=0, 계산은 FP32다. 저장된 공식 전처리와 학습 통계를 사용한다. 학습 데이터는 모델 선택에 사용하지 않는다.

결과는 `selection/scores.csv`, 평가 시점은 `selection/anchors.json`, 선택 모델은 `selection/selected_checkpoint.json`에 저장한다. 이 결과는 고정 검증 표본에서의 비교이며 실제 파지 성공률이나 전체 프레임에서의 최적성을 보장하지 않는다. 검증 데이터로 모델을 골랐으므로 그 점수를 독립 테스트 성능으로 해석하지 않는다.

```powershell
& D:\lerobot-2026\.venv\Scripts\python.exe D:\lerobot-2026\experiments\doll_B200_act\select_checkpoint.py --full-comparison
```

## 선택 모델 실행

`run_selected.py`는 선택 파일의 체크포인트 번호를 읽고 현재 프로젝트에서 모델을 찾는다. 모델과 정규화 파일을 같은 체크포인트에서 읽으며 학습 데이터의 action min/max로 범위를 제한한다. 관절 축 순서, 데이터 개수, 모델 입출력과 저장된 calibration을 검사한다.

기존 `episode_sample_dataset/doll_pickplace_act/run_act_pickplace_safe.py`의 안전 제어기를 재사용한다. 속도·범위·추적오차 제한, 멈춤 감지, HOME 복귀, SPACE 시작, Q 정지 및 E 긴급 torque-off를 유지한다. 카메라/포트/HOME은 현재 `collection/settings.json`을 따른다. 이전 모델 전용 그리퍼 조기 닫힘은 끄고 FP32 추론을 사용한다. 제어기는 30 Hz, 기존 60프레임 재계획과 전환 보간을 사용하며, 이 제어 설정의 실제 성공률은 별도 실물 평가가 필요하다.

기본 실행은 장비를 연결하지 않는 사전 검사다.

```powershell
& D:\lerobot-2026\.venv\Scripts\python.exe D:\lerobot-2026\experiments\doll_B200_act\run_selected.py
```

실물 실행은 명시적으로 `--run`을 사용한다. 연결 후에도 미리보기 창의 SPACE를 눌러야 움직인다. 이 작업에서 실제 로봇 연결/동작은 수행하지 않았다.

```powershell
& D:\lerobot-2026\.venv\Scripts\python.exe D:\lerobot-2026\experiments\doll_B200_act\run_selected.py --run
```

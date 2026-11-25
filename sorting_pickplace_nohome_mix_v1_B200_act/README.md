# 혼합 Sorting ACT 로컬 추론

VS Code에서 이 폴더의 **run.py**를 열고 우측 상단 **Run Python File(재생 버튼)**을 누른다. 프로젝트의 `.venv/Scripts/python.exe`로 자동 전환하므로 별도 인자가 필요 없다.

모델 검사 후 Follower와 TOP/SIDE 카메라를 연결한다. 미리보기 창을 선택하고 HOME 근처에서 **SPACE**를 누르면 동작한다.

- SPACE: 시작 / 일시정지 후 재개
- P: 현재 자세에서 일시정지
- Q: HOME 복귀 후 종료
- E: 긴급 토크 해제

1회 최대 60초이며 다시 시도하려면 재실행한다. 기존 실행기의 속도·관절 범위·추적오차 제한과 종료 처리를 사용한다. 현재 `collection/settings.json`의 포트·카메라·HOME 설정을 읽는다. 이 준비 과정에서 실제 로봇 동작은 실행하지 않는다.

## 선택된 모델

- sorting + HOME 제외 pick-and-place 혼합 ACT v1.
- 50,000 step 학습 완료, best 46,000 step, sorting 검증 손실 0.14948374032974243.
- 학습 에피소드 sorting 120 / 인형 449 / 컵 200. 매 배치 4 / 2 / 2.
- sorting 검증 30개는 학습에서 제외. 단독 인형·컵의 HOME 복귀는 보조 학습 데이터에서 제외.
- 체크포인트: `checkpoints/046000/pretrained_model`.
- 정규화: 이 체크포인트의 pre/post processor. 행동 범위: 혼합 train 통계 `train_stats.json`.
- 입력: TOP/SIDE RGB 640×480 및 관절 6축, FP32 CUDA, 30Hz 제어.
- 기존 sorting 전용 모델은 `sorting_B200_act`에 보존되어 있다.

첫 물체를 놓은 뒤 별도의 HOME 복귀를 삽입하지 않는다. HOME에 돌아온 자세로 종료를 판단하며, 두 물체의 분류 성공 여부는 사람이 확인해야 한다.

## 검사 및 원본

서버 모델·processor·기록 10개 파일은 SHA-256을 대조한다. 기록은 `artifact_sha256.json`과 `server_sha256.txt`에 있다. `run.py`도 매 실행 시 무결성을 확인한다.

`check_model.py`는 장비 연결 없이 모델 strict 로딩과 검증 에피소드 10개의 관측 30개 추론을 확인하고 `model_check_result.json`을 저장한다. 전체 검증 재평가나 실물 성공률 검사가 아니다. `run.py --preflight-only`는 장비 연결 없이 모델·설정을 확인한다.

서버 원본: `/NHNHOME/workspace/lerobot/outputs/act_sorting_pickplace_nohome_mix_v1_20261024_202619`.

이 `run.py`는 **추론 실행 파일**이다. 학습을 다시 시작하는 파일은 `SSH B200/sorting_pickplace_nohome_mix_v1/train.py`이며 서버용이다.

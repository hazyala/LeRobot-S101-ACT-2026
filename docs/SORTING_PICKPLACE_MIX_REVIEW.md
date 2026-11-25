# Sorting + 단독 Pick-and-place 혼합 ACT 검토

검토일: 2026-10-24. 이번 작업은 데이터와 파이프라인 검토만 수행했다.
새 학습·체크포인트 변경·원본 데이터 변경·장비 동작은 하지 않았다.

## 결론

데이터 형식은 호환되며, 단독 작업의 접근 → 잡기 → 운반 → 놓기 구간을
sorting 전체 시연과 함께 학습할 수 있다. 기존 ACT 구조와 공식 손실 함수를 바꿀 필요는 없다.
다만 단독 원본을 통째로 합치는 방식과, 임의로 마지막 몇 초를 제거하는 방식은 권하지 않는다.
놓기 완료 경계 확정, 100프레임 chunk의 경계 처리, 데이터별 샘플링, 분할·통계 처리가 필요하다.
현재 749개 전체의 놓기 완료 경계가 확정된 상태는 아니다.

## 확인한 원본

| 원본 | 에피소드 | 프레임 | 길이 최소 / 중앙 / 최대(초) |
|---|---:|---:|---|
| 인형 pick-and-place | 499 | 291,869 | 13.30 / 19.13 / 42.40 |
| 컵 pick-and-place | 250 | 152,131 | 14.47 / 19.73 / 45.03 |
| Sorting | 150 | 184,183 | 31.50 / 40.75 / 53.80 |
| 합계 | 899 | 628,183 | — |

- 전체 899개에 대해 action·observation.state의 유한성, 에피소드 길이와 총 프레임 수를 확인했다.
- 전체의 frame_index, 절대 index 연속성, 30 FPS timestamp를 확인했고 오류는 없었다.
- 30 FPS, SO-101 follower, RGB 640×480×3, 관절·action 6축 순서와 action 정의가 같다.
- 세 수집 manifest의 leader/follower calibration SHA-256이 같다.
- B200 서버에서도 공식 `features_equal_for_merge`로 세 원본의 스키마 호환성을 확인했다.
- 서버 원본의 개수·프레임 수는 로컬과 같다. 기존 서버 데이터를 재사용할 수 있다.
- 인형 데이터 TOP 카메라 serial은 교체 전 장치이고, 컵·sorting은 교체 후 장치다.
  영상 표본에는 인형 데이터 내 밝기 차이도 보인다. 동일 카메라 serial까지 같다고 해석하면 안 된다.

정책 입력은 기존대로 TOP/SIDE RGB와 관절 상태만 사용하고, depth·load·current는 제외하는 것이 비교에 적절하다.

## 영상 검토 범위와 경계 후보

인형 12개·컵 12개에서 시작·동작 중·놓기 후보 전후·최종 HOME의 TOP 영상 프레임을 확인했다.
그중 각 6개는 SIDE에서도 후보 전후를 확인했다. 전체 749개의 전체 영상을 재생한 검토는 아니다.
표본에서 목적지는 현재 sorting과 같은 왼쪽 투명 인형 상자 / 오른쪽 빨간 컵 영역이다.
인형은 서 있는 자세와 누운 자세가 포함되어 있다. 컵 기록에는 여러 차례 개폐가 있는 시연도 있다.

그리퍼 마지막 개방 이벤트와 HOME 위치 기록으로 749개 모두에서 종료 후보를 만들었다.
이는 의미적으로 검증된 놓기 완료 라벨이 아니다. 후보 파일 이름에도 `NOT_APPROVED`를 표시했다.
그리퍼 개방만으로 물체가 실제로 목적지에 안착했는지, 완전히 놓였는지를 보장할 수 없다.
후보 주변의 TOP/SIDE를 확인하여 다음을 만족하는 끝 프레임을 확정해야 한다.

1. 물체가 목적지에 놓인다.
2. 손가락이 물체를 놓았고, 필요한 짧은 이탈 구간까지 포함한다.
3. 본격적인 HOME 복귀 구간은 포함하지 않는다.

단독 원본의 마지막 HOME 유지 구간 중앙값은 인형 약 2.03초, 컵 약 2.07초다.
이 유지 구간만 제거해도 그 전에 HOME으로 이동하던 동작은 남는다.
자동 후보 기준 제외 길이 중앙값은 인형 약 3.87초, 컵 약 5.20초이나,
이 수치는 후보에 따른 값으로 확정된 crop 길이나 품질 지표가 아니다.

## 실제 설치된 LeRobot / ACT에서 확인한 사항

B200 설치 버전은 LeRobot 0.6.1이다. 실제 설치 모듈의 소스와 동작을 확인했다.

### 여러 데이터셋 이름을 넣는 기본 옵션은 사용할 수 없음

`lerobot.datasets.factory.make_dataset`의 다중 repo_id 분기는
`NotImplementedError("The MultiLeRobotDataset isn't supported for now.")`를 발생시킨다.
따라서 데이터셋 이름 3개만 나열해 기본 CLI로 실행하는 방식을 사용하면 안 된다.
공식 `aggregate_datasets` / `merge_datasets`로 별도 단일 데이터셋을 만들거나,
호환되는 dataset wrapper를 연결해야 한다. 권장은 별도 파생 데이터셋이다.

공식 merge는 에피소드·프레임·task 인덱스를 재배치하는 기능이지,
놓기 완료 시점을 찾아내거나 단독 HOME을 제거하는 기능은 아니다.
`concatenate_videos=False`는 재인코딩 없이 원본 파일별 영상 보존을 지원하지만,
설치 구현은 영상 복사를 수행하므로 저장 공간을 추가 사용한다.
원본 영상 링크 재사용은 별도의 파생 데이터셋 생성기에서 관리해야 하며 기본 옵션으로 가정하면 안 된다.

### 에피소드 경계와 action_is_pad로 HOME 목표 제외 가능

`DatasetReader._get_query_indices`는 episode의 `dataset_to_index`를 끝으로 삼고,
미래 query를 마지막 유효 프레임에 clamp하며 범위 밖에 `action_is_pad=True`를 붙인다.

실제 컵 원본 episode_index 249에서 놓기 후보 frame 375를 메모리상 끝으로 지정하여 검사했다.
경계 20프레임 전에서 100프레임 action을 읽었을 때:

- 앞의 유효 20프레임은 원본과 완전히 같다.
- 이후 80프레임은 마지막 유효 action으로 채워지고 padding으로 표시된다.
- 원래 그 뒤에 읽혔던 action은 supervision에서 제외할 수 있다.
- TOP/SIDE는 각각 3×480×640으로 정상 디코딩된다.

이는 경계 처리의 동작 검증이지 frame 375가 올바른 놓기 완료 시점이라는 승인 검증은 아니다.
실험은 원본 파일 변경 없이 메모리 metadata만 사용했다. 전체 에피소드 인덱스 표는 보존했다.

`ACTPolicy.forward`의 L1 loss는 `action_is_pad`를 제외한다.
실제 forward 함수에 고정 예측을 주고 padding target만 매우 큰 값으로 바꾼 검사에서도
유효 target에 따른 loss=1.0을 유지했다. ACT VAE encoder 역시 같은 padding mask를 사용한다.
따라서 경계와 padding을 정확히 만들면 기본 ACT 손실을 바꾸지 않고 적용할 수 있다.

시작 프레임만 제한하고 미래 100프레임 target은 원본에서 그대로 가져오는 방식은 불충분하다.
영상·수치·episode 경계 또는 wrapper의 action clamp/padding을 함께 맞춰야 한다.
원본에 있는 HOME을 단순 0 action으로 바꿔 학습시키면 안 된다.

### 50 / 25 / 25는 기본 sampler가 자동 적용하지 않음

공식 학습은 `EpisodeAwareSampler`를 직접 생성한다. 그 기본 동작은 유효 프레임 셔플이다.
세 원본을 합친다고 sorting 50%, 인형 25%, 컵 25%가 되는 것은 아니다.
50/25/25로 시작하려면 데이터 source를 아는 별도 sampler를 학습 래퍼에서 연결해야 한다.
batch 8인 단일 B200 실험에서는 sorting 4개·인형 2개·컵 2개 시작 프레임을 뽑도록 구성할 수 있다.
이 비율은 합리적인 첫 실험 설정이지 최적 비율이 입증된 결과는 아니다.

일반 `sample_weighting` 옵션을 바로 켜는 방식도 권하지 않는다.
공식 weighted-loss 경로는 `policy.forward(batch, reduction="none")`를 요구하지만,
설치된 ACTPolicy.forward는 그 인자를 받지 않는다. source별 비중은 sampler로 처리하는 쪽이 적합하다.

## 권장 적용 순서

1. 단독 시연마다 놓기 완료 + 필요한 짧은 이탈까지의 경계를 확인한다.
2. 원본과 기존 sorting 모델을 유지하고 `sorting_pickplace_nohome_mix_v1` 전용 파생 데이터셋을 만든다.
   단독 749개는 확정 경계까지만, sorting 150개는 두 물체와 최종 HOME까지 전체를 사용한다.
   에피소드 source·원본 ID·새 ID·crop 프레임 매핑을 저장한다.
3. 기존 train/validation 분할을 유지한다. 인형 449개·컵 200개·sorting 120개를 학습 후보로 사용한다.
   단독 작업의 검증 100개와 sorting 검증 30개를 학습에 넣지 않는다.
   best 선택은 기존과 같은 sorting 검증 30개 전체로 한다.
4. 유효 학습 구간만으로 정규화 통계를 다시 계산하고 저장 processor에 함께 보존한다.
   기존 단독 에피소드 전체 통계에는 HOME이 포함되어 있으므로 그대로 합산하지 않는다.
   통계가 바뀌면 두 모델의 정규화된 검증 손실 숫자는 직접 성능 비교가 아니다.
   동일 sorting 영상의 원래 관절 단위 오차 및 실물 성공률을 함께 비교한다.
5. 기존 ACT 구조·100 action chunk·optimizer·공식 loss·검증·체크포인트 저장은 유지한다.
   dataset 생성과 source-balanced sampler 연결만 실험 래퍼에서 추가하고,
   설치된 LeRobot 자체 파일은 수정하지 않는다.
6. 본 학습 전에 경계 누출 검사, source별 샘플 수, train/validation 교집합,
   다중 worker import, 짧은 학습·검증·best 저장을 확인한다.

새 학습은 기존 50,000-step baseline과 같은 초기화 조건에서 시작하는 편이
혼합 데이터 효과를 비교하기 쉽다. 기존 best에서 이어 학습하면 다른 실험으로 명시해야 한다.

폴더는 기존 `SSH B200/sorting_basic` / `sorting_B200_act`를 baseline으로 보존하고,
새 실험은 `SSH B200/sorting_pickplace_nohome_mix_v1` /
`sorting_pickplace_nohome_mix_v1_B200_act`처럼 구분하는 것을 권한다.
이번 검토에서는 새 실험 학습 코드를 완성하거나 학습을 시작하지 않았다.

## 해석상의 한계

단독 데이터는 개별 물체의 접근·파지·놓기를 보강할 수 있지만,
다른 물체를 피하는 접근과 첫 물체 뒤 두 번째 물체로 이어지는 동작을 대신 가르치지는 못한다.
그 연결 동작과 최종 HOME은 sorting 데이터가 담당해야 한다.
이 구성은 중간 HOME 복귀 감독을 제거하는 방법이지, 추론에서 중간 HOME을 논리적으로 금지하는 제어기는 아니다.
혼합 학습으로 파지와 전체 성공률이 개선되는지는 실제 비교 평가가 필요하다.

## 검토 산출물

- `collection/reports/pickplace_sorting_review_20261024/numeric_review.json`
- `collection/reports/pickplace_sorting_review_20261024/frame_index_checks.json`
- `collection/reports/pickplace_sorting_review_20261024/pipeline_review_evidence.json`
- `collection/reports/pickplace_sorting_review_20261024/release_candidates_NOT_APPROVED.json`
- 같은 폴더의 TOP/SIDE 표본 이미지

원본 899개를 모두 영상 검수했다고 해석하지 않는다.

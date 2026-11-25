from pathlib import Path
from html import escape
import zipfile

data = r'''LeRobot과 SO 101을 활용한 Pick and Place
로봇 연결부터 시범 설계 데이터 수집 학습과 추론까지

# 문서의 목적과 범위
이 문서는 SO-101 로봇팔과 LeRobot을 이용하여 종이컵을 집어 목표 위치에 놓는 전체 과정을 설명한다. Windows PC에서 로봇과 카메라를 연결하고 데이터를 수집한 뒤 B200 서버에서 ACT 모델을 학습하고, 학습된 모델을 로컬 PC에서 실행한다.
내용은 실제 프로젝트 기록을 기준으로 한다. 장치 이름과 경로는 당시 설정이며 다른 PC에서는 달라질 수 있다. 문서 작성 중 로봇과 서버를 다시 실행하지 않았으므로 실제 장비에서의 재현 확인은 필요하다. 권장하는 동작 예시는 실제 기록과 구분한다.

# 1 로봇 학습 방법
로봇은 카메라 영상이나 관절 상태 등으로 현재 상황을 관찰하고, 그 상황에서 수행할 행동을 정한다. 종이컵 작업이라면 컵과 그리퍼의 위치를 보고 접근하거나 그리퍼를 닫는 행동을 선택한다.
지도학습은 입력과 정답이 짝지어진 데이터를 이용한다. 강화학습은 환경에서 행동한 결과에 따른 보상을 활용해 장기적으로 좋은 행동을 학습한다. 모방학습은 사람이 수행한 시범으로부터 행동을 배운다.
이 사례에서는 각 시점의 영상과 로봇 상태를 입력, 시범에서 수행한 행동을 목표로 이용한다. 이런 행동 복제는 지도학습 방식으로 구현할 수 있으므로 모방학습과 지도학습을 완전히 별개의 범주로 오해하지 않는다.
모방학습에서는 시범의 품질이 중요하다. 성공한 영상이라도 컵을 밀거나 손이 화면에 들어오고, 불필요한 움직임이 포함된다면 그 행동도 학습에 영향을 줄 수 있다.

# 2 LeRobot 프레임워크
LeRobot은 로봇의 원격 조작과 카메라 관찰, 데이터 기록, 정책 모델의 학습과 실행을 돕는 오픈소스 프레임워크이다. 데이터를 일정한 형태로 관리하고 로봇 데이터와 모델을 연결할 수 있어 실험 과정을 구성하기 편리하다.
전체 흐름은 장비 연결 → 텔레오퍼레이션 → 데이터 수집 → 학습 → 추론이다. 이 프로젝트는 LeRobot을 기반으로 별도의 수집 GUI, B200 학습 코드와 안전 추론 스크립트를 작성해 사용한다. 프레임워크만 설치하면 프로젝트 전용 코드가 자동으로 만들어지는 것은 아니다.
로봇이 실제 작업을 수행할 때는 모델의 성능뿐 아니라 보정 상태, 시범의 일관성, 카메라 배치와 작업 환경도 함께 영향을 준다.

# 3 장비와 전체 환경
Leader는 사람이 손으로 조작하는 로봇이며 Follower는 Leader를 따라 움직이고 실제 작업을 수행한다. TOP 카메라는 RealSense D405이고 SIDE 카메라는 웹캠이다. Windows PC는 로봇 제어와 데이터 수집을 담당하고 B200 서버는 모델 학습을 담당한다. 학습 후에는 모델을 Windows PC에서 실행한다.
이 프로젝트의 작업 폴더는 D:\lerobot-2026, Python 가상환경 폴더 이름은 .venv이다. 로봇 포트의 기록값은 Leader COM4, Follower COM3이다. 로봇 ID는 각각 leader와 follower이다. 모터 ID는 관절마다 부여된 번호이며 COM 포트나 로봇 ID와 서로 다르다.
작업 전에는 로봇을 고정하고 회전 범위에서 손, 장애물, 케이블을 치운다. 예상 밖의 동작이 발생하면 즉시 중단할 수 있도록 준비한다.

# 4 가상환경과 LeRobot 확인
PowerShell을 열고 프로젝트 폴더로 이동한 뒤 .venv를 활성화한다.
> cd D:\lerobot-2026
> .\.venv\Scripts\Activate.ps1
> python -c "import sys; print(sys.executable)"
마지막 명령은 실제 사용 중인 Python 경로를 출력한다. 결과가 D:\lerobot-2026\.venv\Scripts\python.exe를 가리키는지 확인한다. 가상환경 표시가 보이더라도 실제 Python 경로를 함께 확인한다.
> python -c "import lerobot; print(lerobot.__file__)"
이 명령은 LeRobot 모듈을 불러올 수 있는지 확인한다. 설치 버전은 python -m pip show lerobot으로 확인한다. 새 PC에 설치할 때는 Python, PyTorch, LeRobot 버전과 운영체제 호환성을 별도로 확인한다.

# 5 포트와 모터 확인
USB를 연결하고 Windows 장치 관리자에서 포트를 확인한다. COM3과 COM4는 기록 당시 컴퓨터에서 사용한 값이다. 장치를 다시 연결하거나 다른 컴퓨터를 사용하면 바뀔 수 있다.
Follower에서 모터를 스캔한다.
> python -c "from lerobot.motors.feetech import FeetechMotorsBus; print(FeetechMotorsBus.scan_port('COM3'))"
Leader를 확인할 때는 COM3을 COM4로 바꾼다. 이전 기록에는 1000000 baud에서 1~6번 모터가 확인된 결과가 있다. 별도 시점의 문서에는 1~5번만 나타난 결과도 있으므로 현재 장비에서 직접 확인해야 한다.
모터 ID는 1 shoulder_pan, 2 shoulder_lift, 3 elbow_flex, 4 wrist_flex, 5 wrist_roll, 6 gripper로 기록되어 있다. 모터가 보이지 않으면 전원, 케이블, 포트, 연결 상태와 ID를 확인한다. 이미 정상 인식된 모터의 ID를 무작정 다시 설정하지 않는다.

# 6 로봇 ID와 캘리브레이션
leader와 follower는 LeRobot에서 각 로봇의 설정과 보정값을 구분하는 ID이다. COM4와 COM3은 통신 포트이며, 1~6은 개별 모터 번호다. 같은 단어인 ID라도 사용하는 대상을 구분한다.
캘리브레이션은 관절의 기준과 이동 범위를 올바르게 해석하도록 맞추는 과정이다. 로봇과 설치된 LeRobot 버전의 절차에 따라 각 관절을 무리 없이 움직이고, 기구물이 걸리는 상태에서 힘을 가하지 않는다.
프로젝트의 보정값은 robot_calibration 폴더에 별도 보관된다. 기존 값을 삭제하거나 다른 로봇의 값으로 덮어쓰기 전에 장치와 설정이 맞는지 확인하고 백업한다.

# 7 카메라 배치
TOP 카메라는 컵, 그리퍼, 목표 영역이 작업 전 과정에서 보이도록 고정한다. SIDE 카메라는 높이와 파지 과정을 보완한다. 정지 화면만 보지 말고 실제로 접근하고 들어 올릴 때 컵이 로봇 뒤에 가려지거나 화면 밖으로 벗어나는지 확인한다.
프로젝트 설정에는 해상도 640×480과 목표 30 FPS가 기록되어 있다. SIDE 카메라 인덱스는 0으로 설정되어 있으나 다른 PC에서는 달라질 수 있다. 카메라 거치대를 흔들리지 않게 고정하고 밝기 변화, 그림자와 반사도 살펴본다.
수집 프로그램은 TOP RGB와 depth, SIDE RGB 및 상태와 행동을 기록한다. 종이컵 ACT 모델의 입력은 TOP/SIDE RGB와 관절 상태이며 depth는 정책 입력으로 사용하지 않았다.

# 8 텔레오퍼레이션
Leader를 움직이면 Follower가 추종하는지 확인한다. 다음은 기록된 PowerShell 명령이다.
> lerobot-teleoperate --teleop.type=so101_leader --teleop.port=COM4 --robot.type=so101_follower --robot.port=COM3 --teleop.id=leader --robot.id=follower
teleop.port는 Leader의 포트, robot.port는 Follower의 포트다. teleop.id와 robot.id는 로봇을 구분하는 이름이다. 명령 옵션과 보정 경로는 설치된 버전에 맞추어 확인한다.
처음에는 물체 없이 관절별로 천천히 움직여 방향과 범위를 확인한다. 그리퍼의 열림과 닫힘, 관절 추종 지연, 반복되는 범위 제한 경고를 살펴본다. 움직임이 어색하면 데이터 수집 전에 보정과 연결 상태를 점검한다.

# 9 작업의 성공 기준과 동작 설계
종이컵을 시작 위치에서 집어 지정된 목표 영역에 안정적으로 놓는 작업을 정의한다. 수집 전에 컵의 시작 방향, 목표 영역, 시작 및 종료 자세를 정하고, 컵이 쓰러지거나 목표 밖에 놓이는 경우를 어떻게 처리할지 정한다.
작업을 시작 자세 → 컵 접근 → 파지 위치 도착 → 그리퍼 닫기 → 파지 확인 → 들어 올리기 → 목표로 이동 → 내려놓기 → 그리퍼 열기 → 종료 자세로 나눈다. 각 단계의 방향과 높이, 경로, 속도를 명확히 정해 시범 간 불필요한 차이를 줄인다.
사람이 무의식적으로 반복하는 규칙도 확인한다. 컵을 잡기 전에 그리퍼를 충분히 벌리는지, 어느 높이를 잡는지, 목표 위치에 닿기 전에 그리퍼를 여는지 영상을 보며 구체적인 기준으로 바꾼다.

# 10 파지 동작 예시
1 그리퍼를 충분히 열고 정해진 방향과 높이에서 천천히 컵에 접근한다.
2 파지 위치에 도착하면 약 1초 유지해 컵과 그리퍼가 안정된 상태를 만든다.
3 컵을 밀거나 심하게 찌그러뜨리지 않도록 그리퍼를 천천히 닫는다.
4 닫은 상태로 약 1초 기다려 파지가 안정됐는지 확인한 뒤 천천히 들어 올린다.
5 정해진 경로로 이동하고 컵이 목표 위치에 닿은 뒤 그리퍼를 연다.
여기서 1초는 설계 방법을 설명하기 위한 예시다. 기존 데이터가 모두 동일한 대기 시간을 사용했다는 의미는 아니다. 시험 수집 영상을 보고 실제 작업에 맞는 기준을 정한다. 정지 시간이 지나치게 길면 정지 행동의 비중이 커질 수도 있다. 실제 힘을 측정하지 않았다면 파지력을 수치로 단정하지 않는다.

# 11 작업 영역과 물체 위치 분포
책상 위 로봇이 안전하게 도달할 수 있는 영역을 여러 섹션으로 나누고 각 섹션에 종이컵을 놓아 고르게 수집한다. 실제 데이터 수집에 사용한 방식이다. 특정 위치에 시범이 몰리는 것을 줄이고 여러 위치에서의 작업을 학습할 기회를 확보한다.
섹션별 목표 수량, 성공 시범 수와 제외 수를 기록한다. 정확한 섹션 개수와 구역별 수량은 자료에서 확인한 뒤 채운다. 수집 위치는 다양하게 바꾸되 파지 방향과 동작 순서 등 작업 기준은 일관되게 유지한다.
영역별로 고르게 수집하더라도 모든 위치에서 성공이 보장되는 것은 아니다. 학습 후 각 섹션에서 별도로 시도해 성공 여부와 실패 단계를 기록한다.

# 12 시험 수집과 품질 검수
본격 수집 전에 여러 섹션에서 소량의 시범을 녹화하고 TOP과 SIDE 영상을 함께 살펴본다. 컵이 밀리는 구간, 그리퍼에 가려지는 순간, 파지 전후 움직임과 예상하지 못한 멈춤을 확인한다. 확인된 문제는 관찰 가능한 규칙으로 구체화한다.
성공 여부 외에도 영상 손상, 검은 화면, 프레임 누락, 화면 밖 움직임, 수동 복구 및 파지 실패를 확인한다. 파지 실패 후 우연히 성공한 시범과 안정적으로 수행한 시범을 구분한다.
잘못된 에피소드는 원인을 기록하고 재수집하거나 데이터셋 도구를 이용해 제외한다. 데이터셋의 영상과 메타데이터는 연결되어 있으므로 영상 파일만 임의로 삭제하면 불일치가 생길 수 있다. 먼저 원본을 보존하고 수정 후 무결성을 확인한다.

# 13 데이터 수집 프로그램 실행
프로젝트는 collection/collect.py와 collection/settings.json을 사용한다. Windows PowerShell에서 프로젝트 가상환경을 활성화한 후 실행한다.
> cd D:\lerobot-2026
> .\.venv\Scripts\Activate.ps1
> python .\collection\collect.py
수집 창에서 종이컵 작업을 선택하고 로봇을 HOME 근처에 둔 뒤 시작한다. 프로젝트 설정에는 준비 5초, 최소 녹화 8초, HOME 복귀 후 2초 유지 조건이 기록되어 있다. 실행 중인 설정과 화면 안내를 우선 확인한다.
실패 시 자동 저장 조건에 도달하기 전에 취소 버튼 또는 f를 사용해 폐기한다. 성공한 시범은 작업별 데이터셋에 저장된다. 저장 중에 프로그램을 강제 종료하거나 파일을 임의로 삭제하지 않는다.

# 14 데이터 구조와 분할
에피소드는 한 번의 작업 시범이고 프레임은 그 안의 한 시점이다. 카메라 영상, 로봇 상태, 행동과 시간 정보가 올바르게 대응해야 한다. 어떤 정보를 저장하는지와 모델에 실제로 입력하는 정보를 분리해 확인한다.
종이컵 프로젝트 기록에는 전체 250개 에피소드와 152,131프레임이 있으며, 200개를 학습에, 50개를 검증에 사용했다. 같은 에피소드가 양쪽에 중복되지 않도록 나눈다.
같은 시범의 인접 프레임은 서로 비슷하므로 프레임만 무작위로 나누면 학습과 검증이 지나치게 유사해질 수 있다. 에피소드 기준으로 분리하고 섹션과 수집 세션의 분포도 함께 확인한다. 별도의 테스트 조건을 두면 일반화 성능을 더 엄격하게 살펴볼 수 있다.

# 15 ACT 모델 학습
ACT는 카메라 영상과 로봇 상태를 받아 앞으로 수행할 행동의 묶음인 action chunk를 예측하는 정책 모델이다. 이 사례에서는 TOP/SIDE RGB와 관절 상태를 입력으로 사용한다.
학습 시 시범의 행동과 모델이 예측한 행동의 차이를 줄이도록 모델 가중치를 조정한다. 검증용 에피소드는 학습 중 선택한 모델을 비교하는 데 사용한다. 학습 시범의 통계로 정규화하고 검증 시범의 정보가 학습 통계에 섞이지 않도록 한다.
손실이 낮다고 실제 로봇의 파지가 반드시 성공하는 것은 아니다. 로봇이 움직이면 모델의 작은 오차가 다음 관찰에도 영향을 주므로 실제 환경에서 별도로 평가해야 한다.

# 16 B200 학습 환경
기록상 B200 서버에 VS Code SSH 원격 창으로 접속하고 /NHNHOME/workspace/lerobot/lerobot-act/bin/python을 Python 인터프리터로 사용했다. 학습 코드는 /NHNHOME/workspace/lerobot/experiments/act/paper_cup_basic/train.py이다.
원격 창에서 train.py를 열고 Run Python File을 누르면 본 학습이 시작된다. 터미널에서는 실제 서버에 해당 경로가 존재하는지 확인하고 다음과 같이 실행할 수 있다.
> /NHNHOME/workspace/lerobot/lerobot-act/bin/python /NHNHOME/workspace/lerobot/experiments/act/paper_cup_basic/train.py
실행은 50,000 step 실제 학습이다. 먼저 데이터와 모델 출력 경로, GPU와 저장 공간을 확인한다. 기록상 SSH 연결이 끊겨도 학습이 유지된다는 보장은 없고, 재실행은 자동 재개가 아닌 새 학습이다. 현재 서버의 파일과 접속 상태는 다시 확인해야 한다.

# 17 학습 설정과 결과
기록된 학습 설정은 ACT, ResNet18, batch 8, 50,000 step, 학습률 1e-5, FP32이며 검증과 저장은 2,000 step마다 수행했다. 이 설정은 이 사례의 기록이며 다른 작업에서도 최적임을 뜻하지 않는다.
최저 검증 손실 기준 best는 44,000 step이고 검증 손실은 약 0.18899로 기록되어 있다. 마지막 50,000 step과 best는 다를 수 있다. 모델과 해당 전처리·정규화 정보, 입력 카메라 설정을 함께 보존한다.
프로젝트에는 종이컵 파지가 잘 된다는 사용자 확인이 있지만, 정해진 시도 횟수로 측정한 실물 성공률은 없다. 손실과 실제 작업 성공률을 동일한 지표로 설명하지 않는다.

# 18 추론 환경과 실행
추론은 학습된 모델이 카메라와 관절 상태를 보고 행동을 예측하여 Follower를 움직이는 과정이다. 이 사례는 B200에서 학습한 뒤 Windows PC에서 모델을 실행한다. B200에 실시간으로 원격 연결해 추론한 사례로 해석하지 않는다.
모델과 처리기 파일, Follower 캘리브레이션, 카메라 이름과 화면 방향, 작업 공간을 확인한다. 학습 시 입력과 추론 시 입력이 맞아야 한다. 작업 범위를 비우고 중단 키를 확인한 뒤 시작한다.
> cd D:\lerobot-2026
> .\.venv\Scripts\Activate.ps1
> python .\paper_cup_B200_act\run.py
프로젝트 기록상 미리보기와 HOME 확인 후 SPACE로 시작한다. P는 일시정지, Q는 HOME 복귀 후 종료, E는 즉시 torque-off다. torque-off 시 자세가 유지되지 않을 수 있으므로 주변을 비우고 실제 장비와 코드의 동작을 먼저 확인한다. 문서 작성 중 실물 추론을 다시 수행하지 않았다.

# 19 위치별 평가와 개선
각 섹션에서 여러 차례 실행해 위치, 시도 횟수, 성공 여부와 실패 단계를 기록한다. 성공률은 성공 횟수를 전체 시도 횟수로 나눈 값이며 시도 횟수와 조건을 함께 표시한다.
컵을 미는 경우 접근 방향과 파지 위치, 카메라 가림과 시범을 확인한다. 컵을 놓치면 파지 구간, 그리퍼 상태, 이동 속도와 관련 시범을 살펴본다. 특정 위치에서만 실패하면 해당 섹션의 데이터 분포와 도달 가능 범위를 점검한다.
원인을 하나로 단정하지 말고 수집 데이터, 환경, 보정, 모델 설정을 하나씩 비교한다. 데이터를 보완해 재학습한다면 기존 평가와 같은 조건에서 비교한다.

# 20 자주 확인할 문제
포트가 없으면 전원과 USB 케이블, 장치 관리자를 확인한다. 일부 모터만 검색되면 배선과 모터 ID를 확인한다. 카메라가 열리지 않으면 다른 프로그램의 사용 여부, 장치 인덱스와 연결을 점검한다.
학습이 시작되지 않으면 서버 인터프리터, 데이터 경로와 저장 공간을 확인한다. 추론에서 입력이 맞지 않으면 체크포인트의 카메라 이름, 영상 크기, 관절 상태와 처리기를 비교한다.
실행 전 확인 목록: 가상환경 경로 / 포트와 로봇 ID / 캘리브레이션 / TOP·SIDE 화면 / 작업 공간 / 모델 파일 / 중단 방법 / 평가 기록.

# 21 용어와 참고 자료
텔레오퍼레이션: 사람이 조작 장치를 이용해 로봇을 움직이는 방식. 에피소드: 한 번의 시범 기록. 프레임: 시범의 한 시점. 정책: 관찰에 따라 행동을 결정하는 모델. 체크포인트: 특정 학습 단계에 저장된 모델과 관련 정보. 추론: 학습된 모델을 사용해 행동을 계산하는 과정.
프로젝트 자료: notes/so101_run_commands.md, notes/environment.md, collection/README.md, collection/settings.json, docs/PIPELINE.md, SSH B200/paper_cup_basic/README.md, paper_cup_B200_act/README.md.
공식 문서: https://huggingface.co/docs/lerobot/il_robots 와 https://huggingface.co/docs/lerobot/getting_started_real_world_robot. 명령과 옵션은 LeRobot 버전에 따라 달라질 수 있다.
추가할 시각 자료: 실제 연결 사진, 작업대 섹션 사진, TOP/SIDE 화면, 수집 GUI, 파지 성공·실패 장면, 학습 로그, 실물 추론 장면.
'''

def p(txt, style='Normal'):
    return '<w:p><w:pPr><w:pStyle w:val="'+style+'"/></w:pPr><w:r><w:t xml:space="preserve">'+escape(txt)+'</w:t></w:r></w:p>'
lines=data.strip().splitlines(); body=p(lines[0],'Title')+p(lines[1],'Subtitle')
for l in lines[2:]:
    if not l.strip(): continue
    body+=p(l[2:],'Heading1') if l.startswith('# ') else p(l[2:],'Code') if l.startswith('> ') else p(l,'Normal')
body+='<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr>'
doc='<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+body+'</w:body></w:document>'
styles='''<?xml version="1.0" encoding="UTF-8"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Malgun Gothic" w:eastAsia="Malgun Gothic"/><w:sz w:val="22"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="340" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults><w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style><w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:rPr><w:b/><w:sz w:val="38"/><w:color w:val="000000"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:rPr><w:sz w:val="24"/><w:color w:val="000000"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:pPr><w:keepNext/><w:spacing w:before="300" w:after="140"/></w:pPr><w:rPr><w:b/><w:sz w:val="28"/><w:color w:val="000000"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Code"><w:name w:val="Code"/><w:pPr><w:ind w:left="240"/></w:pPr><w:rPr><w:rFonts w:ascii="Consolas" w:eastAsia="Malgun Gothic"/><w:sz w:val="19"/></w:rPr></w:style></w:styles>'''
out=Path(r'D:\lerobot-2026\SO101_LeRobot_Manual.docx')
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
 z.writestr('[Content_Types].xml','''<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>''')
 z.writestr('_rels/.rels','''<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>''')
 z.writestr('word/_rels/document.xml.rels','''<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>''')
 z.writestr('word/document.xml',doc); z.writestr('word/styles.xml',styles)
print(out, out.stat().st_size)


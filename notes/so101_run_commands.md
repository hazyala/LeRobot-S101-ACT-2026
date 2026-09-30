# SO-101 실행 주의사항과 명령어

이 문서는 `D:\lerobot-2026` 프로젝트에서 SO-101을 연결하거나 LeRobot 명령을 실행할 때 환경이 섞이지 않도록 보기 위한 짧은 체크리스트입니다.

## 핵심 원칙

- 이 프로젝트의 Python은 `D:\lerobot-2026\.venv\Scripts\python.exe`입니다.
- 패키지 관리는 LeRobot 소스의 `uv.lock`에 맞춰 `uv`를 우선 사용합니다.
- `pip install ...` 단독 실행은 피합니다. Anaconda base 쪽에 설치될 수 있습니다.
- PowerShell 프롬프트에 `(base)`가 보여도 이 프로젝트가 정상이라는 뜻은 아닙니다. 실제 Python 경로를 꼭 확인합니다.
- Conda base 자동 활성화는 꺼둔 상태입니다. 새 터미널에서는 프로젝트 venv만 직접 켭니다.

## 새 PowerShell에서 시작

```powershell
cd D:\lerobot-2026
.\.venv\Scripts\Activate.ps1
cd .\lerobot
```

정상이라면 프롬프트에 `(.venv)` 또는 venv 표시가 보이고, 아래 확인 명령에서 `D:\lerobot-2026\.venv` 경로가 나와야 합니다.

```powershell
python -c "import sys; print(sys.executable)"
```

기대 결과:

```text
D:\lerobot-2026\.venv\Scripts\python.exe
```

## 환경 확인

```powershell
python -c "import sys; print('PYTHON =', sys.executable); import pip; print('PIP =', pip.__file__)"
```

기대 결과:

```text
PYTHON = D:\lerobot-2026\.venv\Scripts\python.exe
PIP = D:\lerobot-2026\.venv\Lib\site-packages\pip\__init__.py
```

Feetech SDK 확인:

```powershell
python -c "import scservo_sdk; print(scservo_sdk.__file__)"
```

기대 결과:

```text
D:\lerobot-2026\.venv\Lib\site-packages\scservo_sdk\__init__.py
```

## SO-101 포트 확인

현재 기록:

- Follower: `COM3`
- Leader: `COM4`

Follower 모터 스캔:

```powershell
python -c "from lerobot.motors.feetech import FeetechMotorsBus; print(FeetechMotorsBus.scan_port('COM3'))"
```

현재 성공했던 결과:

```text
{1000000: [1, 2, 3, 4, 5]}
```

Leader 모터 스캔:

```powershell
python -c "from lerobot.motors.feetech import FeetechMotorsBus; print(FeetechMotorsBus.scan_port('COM4'))"
```

## 패키지 설치 또는 복구

가능하면 LeRobot 프로젝트 기준으로 실행합니다.

```powershell
cd D:\lerobot-2026\lerobot
uv pip install --python D:\lerobot-2026\.venv\Scripts\python.exe -e "D:\lerobot-2026\lerobot[feetech]"
```

pip가 venv 안에서 사라졌을 때만 아래 명령으로 복구합니다.

```powershell
D:\lerobot-2026\.venv\Scripts\python.exe -m ensurepip --upgrade
```

그 다음 다시 Feetech extra를 설치합니다.

```powershell
uv pip install --python D:\lerobot-2026\.venv\Scripts\python.exe -e "D:\lerobot-2026\lerobot[feetech]"
```

## 피해야 할 명령

아래 명령은 현재 PC에서 Anaconda base에 설치될 수 있으므로 피합니다.

```powershell
pip install "lerobot[feetech]"
```

대신 venv가 켜진 상태에서 꼭 필요할 때만 아래처럼 실행합니다.

```powershell
python -m pip install "패키지이름"
```

## 전체 환경 재검사

데이터셋, PyTorch, FFmpeg까지 다시 확인하려면:

```powershell
cd D:\lerobot-2026
$env:HF_HOME = "D:\lerobot-2026\hf_pickplace_reference"
.\.venv\Scripts\python.exe .\scripts\verify_environment.py
```

SO-101 보정값은 `D:\lerobot-2026\robot_calibration`에 별도로 보관합니다. 자동 수집기는 이 경로를 직접 사용하므로 이전 PowerShell 세션의 `HF_HOME` 값과 무관합니다. 모터 내부 값과 파일 값이 다르다는 안내 뒤 기존 calibration 사용 여부를 묻는다면 `c`를 입력하지 말고 Enter를 눌러 저장된 정상 값을 모터에 다시 적용합니다.

이 검사는 학습을 하지 않습니다. 설치된 도구와 공개 Pick & Place 데이터셋 로딩만 확인합니다.

## 문제가 생겼을 때 먼저 볼 것

1. `python -c "import sys; print(sys.executable)"`가 `.venv`를 가리키는지 확인합니다.
2. `python -c "import scservo_sdk; print(scservo_sdk.__file__)"`가 성공하는지 확인합니다.
3. 실패하면 `pip install ...`을 반복하지 말고 위의 `uv pip install --python ...` 명령으로 복구합니다.
4. SDK import는 되는데 모터 스캔이 실패하면 환경보다 전원, 케이블, 포트 번호, 모터 ID, baudrate를 먼저 봅니다.

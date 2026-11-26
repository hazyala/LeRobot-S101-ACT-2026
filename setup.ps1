# Windows 실습 가상환경 생성 및 패키지 설치
$ErrorActionPreference = 'Stop'
$projectDir = $PSScriptRoot
$venvDir = Join-Path $projectDir 'lerobot'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "명령 실행 실패: $Executable (종료 코드: $LASTEXITCODE)"
    }
}

try {
    if (Test-Path -LiteralPath $venvDir) {
        throw "lerobot 폴더가 이미 있습니다. 기존 가상환경을 백업하거나 이름을 바꾼 뒤 다시 실행하세요: $venvDir"
    }

    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if (-not $launcher) {
        throw 'Python Launcher를 찾을 수 없습니다. Python 3.12 (64비트)를 설치하고 다시 실행하세요.'
    }
    $basePython = & $launcher.Source -3.12 -c 'import struct,sys; print(sys.executable); assert struct.calcsize("P") == 8'
    if ($LASTEXITCODE -ne 0 -or -not $basePython) {
        throw '64비트 Python 3.12를 찾을 수 없습니다. Python 3.12를 설치하고 다시 실행하세요.'
    }
    Write-Host "Python: $basePython"
    Write-Host '1/4 가상환경 생성'
    Invoke-Checked $launcher.Source @('-3.12', '-m', 'venv', $venvDir)

    Write-Host '2/4 pip와 실습 패키지 설치'
    Invoke-Checked $venvPython @('-m', 'pip', 'install', '--upgrade', 'pip')
    Invoke-Checked $venvPython @('-m', 'pip', 'install', 'lerobot[feetech,training,viz]==0.6.1', 'pyrealsense2==2.58.4.10922', 'av==15.1.0', 'rerun-sdk==0.33.1')

    Write-Host '3/4 CUDA용 PyTorch 설치'
    Invoke-Checked $venvPython @('-m', 'pip', 'install', 'torch==2.11.0+cu130', 'torchvision==0.26.0+cu130', '--index-url', 'https://download.pytorch.org/whl/cu130')

    Write-Host '4/4 설치 상태 확인'
    Invoke-Checked $venvPython @('-m', 'pip', 'check')
    Invoke-Checked $venvPython @('-c', 'import tkinter, cv2, pyrealsense2, torch; import lerobot; print("PyTorch:", torch.__version__); print("CUDA:", torch.version.cuda); print("GPU 사용 가능:", torch.cuda.is_available())')
    Write-Host ''
    Write-Host '설치 완료. 새 PowerShell 창에서 아래 명령으로 가상환경을 활성화하세요.'
    Write-Host '  .\lerobot\Scripts\Activate.ps1'
    Write-Host 'GPU 사용 가능이 False라면 NVIDIA 드라이버와 GPU 환경을 확인하세요.'
}
catch {
    Write-Error "설치 중단: $_"
    exit 1
}

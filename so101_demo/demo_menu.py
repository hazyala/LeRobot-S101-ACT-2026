"""Terminal menu; each operating mode runs in a separate process."""
import subprocess
import sys
import fcntl
from contextlib import ExitStack
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def main():
    with ExitStack() as resources:
        lock = resources.enter_context((ROOT / '.demo-menu.lock').open('a'))
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('이미 실행 중인 lerobot 메뉴가 있습니다. 기존 터미널을 사용하세요.', flush=True)
            return
        from local_act_demo import preload
        worker = None
        print('종이컵과 인형 모델을 미리 준비합니다.', flush=True)
        try:
            worker = preload()
            resources.callback(worker.close)
        except Exception as exc:
            print(f'모델 사전 준비 실패. 선택한 모델을 개별 실행합니다. {exc}', flush=True)
        menu(worker)

def menu(worker):
    from local_act_demo import run
    while True:
        print('\n===== SO-101 시연 =====\n\n1. 텔레오퍼레이션\n2. 인형 Pick & Place\n3. 종이컵 Pick & Place\n4. 카메라 구도 맞추기\n0. 종료\n', flush=True)
        try:
            choice = input('번호를 입력하세요: ').strip()
        except (EOFError, KeyboardInterrupt):
            print('\n종료합니다.')
            return
        if choice not in ('0','1','2','3','4'):
            print('0~4 중에서 입력하세요.')
            continue
        try:
            if choice in ('2','3'):
                model = 'doll' if choice == '2' else 'cup'
                if worker and worker.process and worker.process.poll() is None:
                    worker.selected_model = model
                    run(model, prepared=worker)
                else:
                    run(model)
                continue
            result = subprocess.run([sys.executable, str(ROOT/'demo_mode.py'), choice], check=False)
            if choice == '0' and result.returncode == 0:
                return
            if result.returncode:
                print('기능이 중지됐습니다. 위 오류와 장치 상태를 확인하세요.', flush=True)
        except KeyboardInterrupt:
            print('\n기능 중지 요청을 받았습니다.', flush=True)
        except Exception as exc:
            print(f'중지됨: {exc}', flush=True)

if __name__ == '__main__': main()

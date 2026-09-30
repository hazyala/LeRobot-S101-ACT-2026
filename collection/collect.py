"""실행 버튼 또는 '수집 실행' 바로가기로 여는 수집 창."""
from __future__ import annotations

import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import traceback
from datetime import datetime

BASE = Path(__file__).resolve().parent
PYTHON = BASE.parent / ".venv/Scripts/pythonw.exe"
LABELS = ["인형 집어 담기", "종이컵 집어 담기", "인형·종이컵 분류", "상자 2개 쌓기", "상자 3개 쌓기", "상자 4개 쌓기"]
STATES = {"CONNECTING": "환경 확인 및 장비 연결 중…", "RECOVERING": "이전 중단 기록 복구 중…",
          "LOADING": "수집 라이브러리 불러오는 중…",
          "VALIDATING": "보정 파일·저장 경로·기존 데이터 확인 중…",
          "LEADER": "Leader 연결 및 보정값 확인 중…",
          "FOLLOWER": "Follower·카메라 연결 중…",
          "PREP": "다음 시연 준비 중 · 영상 창의 카운트다운을 확인하세요.",
          "START": "START · 1초 뒤 녹화가 시작됩니다.",
          "RECORDING": "녹화 중 · HOME으로 돌아와 2초 유지하면 자동 저장됩니다.",
          "SAVING": "자동 저장·검사 중 · 다음 시연을 준비하세요."}


def receive_commands(commands, stopped, stream=None):
    """Read only available pipe bytes, never block a Windows CRT stdin lock.

    NumPy initializes stdin's binary mode. A concurrent TextIO readline can
    hold the same CRT lock indefinitely while the GUI keeps its pipe open.
    """
    stream = sys.stdin if stream is None else stream
    fd = stream.fileno()
    pending = b""
    if os.name == "nt":
        import ctypes
        import msvcrt
        from ctypes import wintypes
        peek = ctypes.WinDLL("kernel32", use_last_error=True).PeekNamedPipe
        peek.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                         ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        peek.restype = wintypes.BOOL
        handle = msvcrt.get_osfhandle(fd)
    try:
        while not stopped.is_set():
            if os.name == "nt":
                available = wintypes.DWORD()
                if not peek(handle, None, 0, None, ctypes.byref(available), None):
                    # Includes a closed parent pipe: stop collection safely.
                    commands.put("q")
                    return
                size = min(available.value, 4096)
                if size == 0:
                    stopped.wait(0.05)
                    continue
            else:
                import select
                if not select.select([fd], [], [], 0.05)[0]:
                    continue
                size = 4096
            data = os.read(fd, size)
            if not data:
                commands.put("q")
                return
            pending += data
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                command = line.strip().decode("ascii", errors="ignore")
                if command in ("f", "q"):
                    commands.put(command)
                    if command == "q":
                        return
            if len(pending) > 4096:
                pending = b""
    except (OSError, ValueError):
        commands.put("q")


def worker(task_id, session):
    import core
    commands = queue.Queue()
    stopped = threading.Event()
    listener = threading.Thread(target=receive_commands, args=(commands, stopped), daemon=True)
    listener.start()
    def notify(state):
        print("@STATE:" + state, flush=True)
    task = core.task_for(task_id)
    notify("CONNECTING")
    try:
        if (core.task_dir(task) / "pending_episode.json").exists():
            notify("RECOVERING")
            core.recover(task)
        core.run(task, session, commands=commands, notify=notify)
        print("@DONE", flush=True)
        return 0
    except BaseException as exc:
        traceback.print_exc()
        print("@ERROR:" + str(exc).replace("\n", " / "), flush=True)
        return 1
    finally:
        stopped.set()
        listener.join(timeout=1)


class CollectionWindow:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk
        from tkinter.scrolledtext import ScrolledText
        import core
        self.root, self.core = root, core
        self.process = None
        self.events = queue.Queue()
        self.closing = False
        self.stopping = False
        self.error = None
        self.timer = None
        root.title("SO-101 데이터 수집")
        root.geometry("820x640")
        root.minsize(720, 580)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TLabel", font=("맑은 고딕", 10))
        style.configure("TButton", font=("맑은 고딕", 11), padding=10)
        panel = ttk.Frame(root, padding=24)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="로봇 데이터 수집", font=("맑은 고딕", 20, "bold")).pack(anchor="w")
        ttk.Label(panel, text="작업을 고르고 ‘수집 시작’을 누르세요. 기존 데이터는 이어서 저장합니다.").pack(anchor="w", pady=(5, 18))
        self.choice = ttk.Combobox(panel, state="readonly", values=[f"{i} · {v}" for i, v in enumerate(LABELS)], font=("맑은 고딕", 12))
        self.choice.current(0)
        self.choice.pack(fill="x")
        self.choice.bind("<<ComboboxSelected>>", self.refresh)
        self.sentence = tk.StringVar()
        self.destination = tk.StringVar()
        ttk.Label(panel, textvariable=self.sentence, wraplength=730).pack(anchor="w", pady=(8, 3))
        ttk.Label(panel, textvariable=self.destination, wraplength=730, foreground="#55606c").pack(anchor="w")
        ttk.Label(panel, text="수집 메모 (선택)").pack(anchor="w", pady=(16, 4))
        self.note = ttk.Entry(panel, font=("맑은 고딕", 11))
        self.note.insert(0, datetime.now().strftime("%Y-%m-%d"))
        self.note.pack(fill="x")
        row = ttk.Frame(panel)
        row.pack(fill="x", pady=(18, 12))
        self.start_button = ttk.Button(row, text="▶  수집 시작", command=self.start)
        self.start_button.pack(side="left")
        self.discard_button = ttk.Button(row, text="폐기", command=lambda: self.send("f"), state="disabled")
        self.discard_button.pack(side="left", padx=8)
        self.stop_button = ttk.Button(row, text="종료", command=lambda: self.send("q"), state="disabled")
        self.stop_button.pack(side="left")
        self.status = tk.StringVar(value="준비됨 · 로봇을 HOME 근처에 두고 시작하세요.")
        ttk.Label(panel, textvariable=self.status, wraplength=730, font=("맑은 고딕", 11, "bold")).pack(anchor="w", pady=(0, 8))
        ttk.Label(panel, text="준비 5초 → START 1초 → 녹화 → HOME 2초 유지 → 자동 저장\n폐기 시 10초 뒤 같은 번호로 재시도합니다. 영상 창에서도 f / q를 사용할 수 있습니다.", wraplength=730).pack(anchor="w")
        details = ttk.LabelFrame(panel, text="진행 기록", padding=5)
        details.pack(fill="both", expand=True, pady=(12, 0))
        self.log = ScrolledText(details, height=7, font=("맑은 고딕", 9), state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()
        self.timer = root.after(100, self.poll)

    def refresh(self, event=None):
        task = self.core.task_for(self.choice.current())
        self.sentence.set(task["instruction"])
        path = self.core.data_root(task)
        try:
            count = self.core.read_json(path / "meta/info.json")["total_episodes"]
        except (OSError, ValueError, KeyError):
            count = 0
        self.destination.set(f"저장된 시연 {count}개  ·  {path}")

    def start(self):
        if self.process is not None:
            return
        self.error, self.stopping = None, False
        session = self.note.get().strip() or datetime.now().strftime("%Y-%m-%d")
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        try:
            process = subprocess.Popen([str(PYTHON), "-u", str(Path(__file__).resolve()), "--worker", str(self.choice.current()), session],
                                       cwd=BASE, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, encoding="utf-8", errors="replace", env=env,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as exc:
            self.status.set(f"시작하지 못했습니다: {exc}")
            return
        self.process = process
        self.choice.configure(state="disabled")
        self.note.configure(state="disabled")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status.set(STATES["CONNECTING"])
        def read_output():
            log_dir = BASE / "reports"
            log_dir.mkdir(exist_ok=True)
            with (log_dir / f"collection_{datetime.now():%Y%m%d_%H%M%S_%f}.log").open("w", encoding="utf-8") as f:
                for line in process.stdout:
                    f.write(line)
                    f.flush()
                    self.events.put(("line", line.rstrip()))
            self.events.put(("exit", process.wait()))
        threading.Thread(target=read_output, daemon=True).start()

    def send(self, command):
        if command not in ("f", "q"):
            return
        if self.process is None or self.process.poll() is not None:
            return
        try:
            self.process.stdin.write(command + "\n")
            self.process.stdin.flush()
        except (OSError, ValueError):
            return
        if command == "q":
            self.stopping = True
            self.stop_button.configure(state="disabled")
            self.discard_button.configure(state="disabled")
            self.status.set("종료 중 · 저장 또는 자원 정리가 끝날 때까지 기다려 주세요.")

    def poll(self):
        for _ in range(150):
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "exit":
                if self.process:
                    self.process.stdin.close()
                    self.process.stdout.close()
                self.process = None
                if self.closing:
                    self.destroy()
                    return
                self.choice.configure(state="readonly")
                self.note.configure(state="normal")
                self.start_button.configure(state="normal")
                for button in (self.discard_button, self.stop_button):
                    button.configure(state="disabled")
                self.status.set("수집 종료 · 저장된 데이터는 보존됩니다." if value == 0 else "중단됨 · " + (self.error or "진행 기록에서 오류를 확인해 주세요."))
                self.refresh()
            elif value.startswith("@STATE:"):
                state = value.partition(":")[2]
                if not self.stopping:
                    self.status.set(STATES.get(state, state))
                    self.discard_button.configure(state="normal" if state == "RECORDING" else "disabled")
                if state == "PREP":
                    self.refresh()
            elif value.startswith("@ERROR:"):
                self.error = value.partition(":")[2]
            elif not value.startswith("@DONE"):
                self.log.configure(state="normal")
                self.log.insert("end", value + "\n")
                if int(self.log.index("end-1c").split(".")[0]) > 150:
                    self.log.delete("1.0", "30.0")
                self.log.see("end")
                self.log.configure(state="disabled")
        self.timer = self.root.after(100, self.poll)

    def close(self):
        if self.process is not None:
            self.closing = True
            self.send("q")
        else:
            self.destroy()

    def destroy(self):
        if self.timer:
            self.root.after_cancel(self.timer)
            self.timer = None
        self.root.destroy()


def main():
    # Editor Run buttons can use a different interpreter; select this project's venv.
    if Path(sys.prefix).resolve() != PYTHON.parent.parent.resolve():
        subprocess.Popen([str(PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]], cwd=BASE,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return 0
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        return worker(int(sys.argv[2]), sys.argv[3])
    import tkinter as tk
    root = tk.Tk()
    CollectionWindow(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

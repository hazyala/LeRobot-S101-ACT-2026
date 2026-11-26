"""SO-101 데이터셋 관리 및 수집 실행 화면."""

from datetime import datetime
import json
import os
import hashlib
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
from collections import deque
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from data_inspection import (
    dataset_size,
    episode_rows,
    inspect_episode,
    read_info,
    remove_episode,
)


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
DATASETS_DIR = PROJECT_ROOT / "datasets"  # 기본 저장 폴더를 바꾸려면 수정
HISTORY_DIR = PROJECT_ROOT / "docs" / "data_collect"
os.environ["HF_DATASETS_CACHE"] = str(PROJECT_ROOT / ".cache" / "huggingface" / "datasets")


def history_path(dataset_path):
    """데이터셋 경로별 이력 파일. 같은 폴더 이름도 경로로 구분."""
    path = Path(dataset_path)
    digest = hashlib.sha256(str(path.resolve()).casefold().encode("utf-8")).hexdigest()[:12]
    name = re.sub(r"[^A-Za-z0-9_-]", "_", path.name) or "dataset"
    return HISTORY_DIR / f"{name}_{digest}.json"


def load_catalog():
    catalog = {}
    if not HISTORY_DIR.exists():
        return catalog
    for path in sorted(HISTORY_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        key = data["dataset_path"]
        if key in catalog:
            raise ValueError(f"동일한 데이터셋 이력 파일이 중복되었습니다: {key}")
        catalog[key] = data["history"]
    return catalog


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def display_time(value):
    return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M:%S") if value else "—"


def display_size(value):
    if value is None:
        return "—"
    if abs(value) >= 1024**3:
        return f"{value / 1024**3:.2f} GiB"
    return f"{value / 1024**2:.2f} MiB"


def dataset_summary(root):
    if not root.exists():
        return 0, 0
    return read_info(root)["total_episodes"], dataset_size(root)


def make_table(parent, columns, height):
    panel = ttk.Frame(parent)
    panel.pack(fill="both", expand=True, padx=12, pady=(0, 8))
    panel.rowconfigure(0, weight=1)
    panel.columnconfigure(0, weight=1)

    names = [name for name, _ in columns]
    table = ttk.Treeview(
        panel, columns=names, show="headings",
        height=height, selectmode="browse",
    )
    vertical = ttk.Scrollbar(panel, command=table.yview)
    horizontal = ttk.Scrollbar(panel, orient="horizontal", command=table.xview)
    table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    table.grid(row=0, column=0, sticky="nsew")
    vertical.grid(row=0, column=1, sticky="ns")
    horizontal.grid(row=1, column=0, sticky="ew")

    for name, width in columns:
        table.heading(name, text=name)
        table.column(name, width=width, stretch=False)
    return table


def ask_fields(parent, title, fields, description=""):
    """필드 입력 창. 취소 시 None 반환."""
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.transient(parent)
    dialog.columnconfigure(0, weight=1)
    result = None
    widgets = {}

    row = 0
    if description:
        ttk.Label(dialog, text=description, wraplength=660, justify="left").grid(
            row=row, column=0, sticky="ew", padx=12, pady=(12, 0)
        )
        row += 1

    for key, label, initial, kind in fields:
        ttk.Label(dialog, text=label).grid(
            row=row, column=0, sticky="w", padx=12, pady=(12, 3)
        )
        row += 1
        if kind == "memo":
            widget = tk.Text(dialog, width=78, height=5, wrap="word")
            widget.insert("1.0", initial)
            widget.grid(row=row, column=0, sticky="ew", padx=12)
        else:
            line = ttk.Frame(dialog)
            line.grid(row=row, column=0, sticky="ew", padx=12)
            widget = ttk.Entry(line, width=74)
            widget.insert(0, initial)
            widget.pack(side="left", fill="x", expand=True)

            if kind == "folder":
                def browse(entry=widget):
                    chosen = filedialog.askdirectory(parent=dialog)
                    if chosen:
                        entry.delete(0, "end")
                        entry.insert(0, chosen)

                ttk.Button(line, text="찾아보기", command=browse).pack(
                    side="right", padx=(6, 0)
                )
        widgets[key] = (widget, kind)
        row += 1

    def accept():
        nonlocal result
        result = {
            key: (
                widget.get("1.0", "end-1c") if kind == "memo" else widget.get()
            ).strip()
            for key, (widget, kind) in widgets.items()
        }
        if title == "새 데이터셋 만들기":
            if not all(result.values()):
                messagebox.showwarning("입력 확인", "모든 항목을 입력해 주세요.", parent=dialog)
                result = None
                return
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", result["slug"]):
                messagebox.showwarning("폴더 이름 확인",
                    "새 폴더 이름에는 영문, 숫자, 밑줄, 하이픈을 사용해 주세요.", parent=dialog)
                result = None
                return
        dialog.destroy()

    buttons = ttk.Frame(dialog)
    buttons.grid(row=row, column=0, sticky="e", padx=12, pady=12)
    ttk.Button(buttons, text="취소", command=dialog.destroy).pack(side="right")
    ttk.Button(buttons, text="확인", command=accept).pack(side="right", padx=6)
    dialog.grab_set()
    next(iter(widgets.values()))[0].focus_set()
    parent.wait_window(dialog)
    return result


class CollectionGUI:
    def __init__(self, window):
        self.window = window
        self.catalog = load_catalog()
        self.events = queue.Queue()
        self.process = None
        self.active_session = None
        self.busy = False
        self.closing = False
        self.actions = []
        self.process_output = deque(maxlen=60)
        self.started_at = None
        self.status = tk.StringVar(value="데이터셋을 선택하거나 새로 만드세요.")
        self.detail = tk.StringVar()

        window.title("SO-101 데이터 수집")
        window.geometry("1200x760")
        window.minsize(950, 650)

        heading = ttk.Frame(window, padding=(16, 12, 16, 4))
        heading.pack(fill="x")
        ttk.Label(heading, text="SO-101 데이터 수집", font=("Malgun Gothic", 16, "bold")).pack(anchor="w")
        ttk.Label(heading, text="1. 데이터셋 선택 또는 만들기   →   2. 수집 시작   →   3. 영상 확인",
                  padding=(0, 5)).pack(anchor="w")

        state_frame = ttk.LabelFrame(window, text="현재 진행 상태", padding=10)
        state_frame.pack(fill="x", padx=16, pady=5)
        ttk.Label(state_frame, textvariable=self.status, wraplength=1080,
                  font=("Malgun Gothic", 10, "bold")).pack(anchor="w")
        ttk.Label(state_frame, text="실패한 시연은 카메라 화면을 선택한 뒤 F 키를 눌러 폐기하세요.",
                  wraplength=1080, padding=(0, 5, 0, 0)).pack(anchor="w")

        toolbar = ttk.Frame(window, padding=(16, 6))
        toolbar.pack(fill="x")
        for label, action in (
            ("새 데이터셋", self.create_dataset),
            ("수집 시작", self.start_collection),
            ("영상 확인 · 삭제", self.show_episodes),
        ):
            button = ttk.Button(toolbar, text=label,
                                command=lambda fn=action: self.run_action(fn))
            button.pack(side="left", padx=(0, 6))
            self.actions.append(button)

        self.stop_button = ttk.Button(toolbar, text="수집 종료", command=lambda: self.send("q"))
        self.stop_button.pack(side="right", padx=(6, 0))

        dataset_panel = ttk.LabelFrame(window, text="데이터셋 목록 · 수집할 데이터셋을 선택하세요")
        dataset_panel.pack(fill="both", expand=True, padx=16, pady=(4, 5))
        self.datasets = make_table(dataset_panel, (
            ("데이터셋", 200), ("최근 종료", 150),
            ("총 에피소드", 100), ("총용량", 100), ("작업 설명", 440),
        ), height=5)
        self.datasets.bind("<<TreeviewSelect>>", lambda _: self.refresh_history())

        ttk.Label(window, textvariable=self.detail, padding=(18, 4), wraplength=1100).pack(fill="x")
        history_panel = ttk.LabelFrame(window, text="수집 이력 · 항목을 두 번 누르면 메모 확인")
        history_panel.pack(fill="both", expand=True, padx=16, pady=(4, 12))
        self.history = make_table(history_panel, (
            ("수집 일시", 300), ("수집 에피소드", 100), ("총 에피소드", 100),
            ("수집 용량", 100), ("총용량", 100),
            ("시작 메모", 190), ("종료 메모", 190),
        ), height=6)
        self.history.bind("<Double-1>", lambda _: self.show_session())

        window.protocol("WM_DELETE_WINDOW", self.close)

        self.set_busy(False)
        self.refresh()
        window.after(100, self.poll_events)

    def run_action(self, action):
        try:
            action()
        except Exception as error:
            messagebox.showerror("오류", str(error), parent=self.window)

    def save_catalog(self):
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        for dataset_path, entry in self.catalog.items():
            path = history_path(dataset_path)
            temp = path.with_suffix(".tmp")
            temp.write_text(
                json.dumps({"dataset_path": dataset_path, "history": entry},
                           ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temp.replace(path)

    def selected_key(self):
        selected = self.datasets.selection()
        return selected[0] if selected else None

    def set_busy(self, busy):
        self.busy = busy
        for button in self.actions:
            button.configure(state="disabled" if busy else "normal")
        state = "normal" if self.process is not None else "disabled"
        self.stop_button.configure(state=state)

    def refresh(self, key=None):
        key = key or self.selected_key()
        self.datasets.delete(*self.datasets.get_children())
        for path, entry in self.catalog.items():
            try:
                count, size = dataset_summary(Path(path))
            except (OSError, ValueError, KeyError):
                count, size = "확인 필요", None
            latest = next(
                (session for session in reversed(entry["sessions"]) if session.get("end")),
                {},
            )
            self.datasets.insert("", "end", iid=path, values=(
                entry["name"], display_time(latest.get("end")),
                count, display_size(size), entry["task"],
            ))

        if key in self.catalog:
            self.datasets.selection_set(key)
            self.datasets.see(key)
        self.refresh_history()

    def refresh_history(self):
        self.history.delete(*self.history.get_children())
        key = self.selected_key()
        if key is None:
            self.detail.set("")
            return

        entry = self.catalog[key]
        self.detail.set(f"저장 경로  {key}\n작업 설명  {entry['task']}")
        for index, session in enumerate(entry["sessions"]):
            start = display_time(session["start"])
            end = display_time(session.get("end"))
            self.history.insert("", "end", iid=str(index), values=(
                f"{start} ~ {end}",
                session.get("added", "—"),
                session.get("total", "—"),
                display_size(session.get("added_bytes")),
                display_size(session.get("total_bytes")),
                session["start_note"],
                session.get("end_note", ""),
            ))

    def show_session(self):
        key = self.selected_key()
        selected = self.history.selection()
        if key is None or not selected:
            return

        session = self.catalog[key]["sessions"][int(selected[0])]
        messagebox.showinfo(
            "수집 세션",
            f"시작  {display_time(session['start'])}\n"
            f"종료  {display_time(session.get('end'))}\n"
            f"저장 당시 에피소드 번호  {session.get('episode_range', '—')}\n\n"
            f"시작 메모\n{session['start_note'] or '—'}\n\n"
            f"종료 메모\n{session.get('end_note') or '—'}",
            parent=self.window,
        )

    def create_dataset(self):
        values = ask_fields(self.window, "새 데이터셋 만들기", (
            ("name", "데이터셋 이름 · 목록에서 구분할 이름", "", "text"),
            ("parent", "저장할 위치 · 필요하면 찾아보기로 변경", str(DATASETS_DIR), "folder"),
            ("slug", "새 폴더 이름 · 영문, 숫자, _ 또는 -", "", "text"),
            ("task", "작업 설명 · 로봇이 수행할 작업", "", "text"),
        ))
        if values is None:
            return
        if not all(values.values()):
            raise ValueError("모든 항목을 입력해 주세요.")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", values["slug"]):
            raise ValueError("새 폴더 이름에는 영문, 숫자, 밑줄, 하이픈을 사용해 주세요.")

        root = (Path(values["parent"]) / values["slug"]).resolve()
        if root.exists() or str(root) in self.catalog:
            raise ValueError("이미 사용 중인 경로입니다. 새 폴더 이름을 지정해 주세요.")
        self.add_dataset(root, values["name"], values["task"])

    def add_dataset(self, root, name, task):
        key = str(root)
        self.catalog[key] = {"name": name, "task": task, "sessions": []}
        self.save_catalog()
        self.refresh(key)
        self.status.set("데이터셋 등록 완료")

    def start_collection(self):
        key = self.selected_key()
        if key is None:
            self.status.set("수집할 데이터셋을 먼저 선택하세요.")
            return

        root = Path(key)
        entry = self.catalog[key]
        count, size = dataset_summary(root)
        previous = next(
            (session for session in reversed(entry["sessions"]) if session.get("end")),
            {},
        )
        fields = ask_fields(
            self.window, "수집 시작",
            (("note", "시작 메모", "", "memo"),),
            description=(
                f"{entry['name']}\n{root}\n{entry['task']}\n"
                f"현재 {count}개 · {display_size(size)}\n"
                f"직전 종료 메모  {previous.get('end_note') or '—'}"
            ),
        )
        if fields is None:
            return

        self.process_output.clear()
        self.started_at = time.monotonic()
        self.process = subprocess.Popen(
            [
                sys.executable, "-X", "utf8", "-u",
                "-m", "scripts.collection.data_collection", key, entry["task"],
            ],
            cwd=PROJECT_ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        session = {
            "start": now(),
            "start_note": fields["note"],
            "before_count": count,
            "before_bytes": size,
        }
        self.active_session = key, session
        entry["sessions"].append(session)
        self.set_busy(True)
        self.status.set("수집 프로그램 시작 중 · 필요한 기능을 불러오고 있습니다")
        threading.Thread(
            target=self.read_process, args=(self.process,), daemon=True
        ).start()
        self.save_catalog()
        self.refresh_history()

    def read_process(self, process):
        for line in process.stdout:
            line = line.strip()
            if line:
                self.process_output.append(line)
                self.events.put(("status", line))
        self.events.put(("finished", process.wait()))

    def send(self, command):
        if self.process is None or self.process.poll() is not None:
            return
        try:
            self.process.stdin.write(command + "\n")
            self.process.stdin.flush()
        except (OSError, ValueError):
            self.status.set("수집 프로그램 종료 대기 중")
        if command == "q":
            self.stop_button.configure(state="disabled")
            self.status.set("수집 종료 요청 · 현재 작업을 정리하는 중")

    def finish_collection(self, exit_code):
        key, session = self.active_session
        last_status = self.status.get()
        self.process = None
        self.active_session = None
        root = Path(key)

        try:
            count, size = dataset_summary(root)
            added = count - session["before_count"]
            added_bytes = size - session["before_bytes"]
            episode_range = (
                f"{session['before_count']}–{count - 1}" if added > 0 else "—"
            )
        except (OSError, ValueError, KeyError):
            count = size = added = added_bytes = None
            episode_range = "확인 필요"

        session.update(
            end=now(), added=added, total=count,
            added_bytes=added_bytes, total_bytes=size,
            episode_range=episode_range, exit_code=exit_code,
        )
        self.save_catalog()

        result_text = (
            f"이번 저장  {added if added is not None else '확인 필요'}개"
            f" · {display_size(added_bytes)}\n"
            f"전체  {count if count is not None else '확인 필요'}개"
            f" · {display_size(size)}"
        )
        if exit_code != 0:
            details = "\n".join(self.process_output)
            if "datasets" in details and "required but not installed" in details:
                error_text = ("데이터셋 처리 패키지가 설치되지 않았습니다.\n"
                              "가상환경에서 아래 명령을 실행한 뒤 다시 시작하세요.\n\n"
                              "python -m pip install \"lerobot[feetech,training]==0.6.1\"")
            else:
                error_text = details[-2500:] or last_status
            messagebox.showerror("수집을 시작하거나 진행하지 못했습니다", error_text, parent=self.window)
            result_text += f"\n수집 오류 · 종료 코드 {exit_code}"

        fields = ask_fields(
            self.window, "수집 종료",
            (("note", "종료 메모", "", "memo"),),
            description=result_text,
        )
        session["end_note"] = fields["note"] if fields else ""
        self.save_catalog()
        self.set_busy(False)
        self.refresh(key)
        self.status.set(result_text.replace("\n", " | "))
        if self.closing:
            self.window.destroy()

    def poll_events(self):
        try:
            while True:
                event, value = self.events.get_nowait()
                if event == "status":
                    self.status.set(value)
                elif event == "finished":
                    self.run_action(lambda: self.finish_collection(value))
                    if self.closing:
                        return
                elif event == "delete_done":
                    self.set_busy(False)
                    self.refresh()
                    self.status.set("에피소드 삭제 완료")
                elif event == "delete_error":
                    self.set_busy(False)
                    messagebox.showerror("삭제 실패", value, parent=self.window)
        except queue.Empty:
            pass
        self.window.after(100, self.poll_events)

    def show_episodes(self):
        key = self.selected_key()
        if key is None:
            self.status.set("확인할 데이터셋을 먼저 선택하세요.")
            return

        root = Path(key)
        rows = episode_rows(root)
        if not rows:
            messagebox.showinfo("에피소드 확인", "저장된 에피소드가 없습니다.", parent=self.window)
            return

        dialog = tk.Toplevel(self.window)
        dialog.title("에피소드 확인")
        dialog.transient(self.window)
        dialog.grab_set()
        table = make_table(dialog, (
            ("에피소드 번호", 150), ("프레임 수", 130), ("길이", 120),
        ), height=12)
        fps = read_info(root)["fps"]
        for row in rows:
            index = row["episode_index"]
            length = row["length"]
            table.insert("", "end", iid=str(index), values=(
                index, length, f"{length / fps:.2f}초",
            ))

        def selected_index():
            selected = table.selection()
            return int(selected[0]) if selected else None

        def inspect():
            index = selected_index()
            if index is None:
                return
            result = inspect_episode(root, index)
            issues = result["issues"]
            lines = [
                f"{index}번 · {result['frames']}프레임 · {result['seconds']:.2f}초",
                f"검사 알림 {len(issues)}건",
                *result.get("notes", []),
                *issues[:20],
            ]
            if len(issues) > 20:
                lines.append(f"외 {len(issues) - 20}건")
            messagebox.showinfo("프레임 검사", "\n".join(lines), parent=dialog)

        def play():
            index = selected_index()
            if index is None:
                return
            subprocess.Popen(
                [
                    sys.executable, "-X", "utf8",
                    str(SCRIPT_DIR / "data_inspection.py"),
                    key, str(index), "--play",
                ],
                cwd=PROJECT_ROOT,
            )

        def delete():
            index = selected_index()
            if index is None:
                return
            if not messagebox.askyesno(
                "에피소드 삭제",
                f"{index}번 에피소드를 삭제할까요?\n"
                "이후 에피소드 번호가 바뀔 수 있습니다.\n"
                "삭제한 에피소드는 복구할 수 없습니다.",
                parent=dialog,
            ):
                return

            dialog.destroy()
            self.set_busy(True)
            self.status.set("데이터셋 재구성 중")

            def worker():
                try:
                    remove_episode(root, index)
                    self.events.put(("delete_done", ""))
                except Exception as error:
                    self.events.put(("delete_error", str(error)))

            threading.Thread(target=worker, daemon=True).start()

        toolbar = ttk.Frame(dialog, padding=12)
        toolbar.pack(fill="x")
        for label, action in (
            ("프레임 검사", inspect),
            ("TOP·SIDE 재생", play),
            ("선택 에피소드 삭제", delete),
        ):
            ttk.Button(
                toolbar, text=label,
                command=lambda fn=action: self.run_action(fn),
            ).pack(side="left", padx=3)

    def close(self):
        if self.process is not None:
            self.closing = True
            self.send("q")
        elif not self.busy:
            self.window.destroy()


def main():
    window = tk.Tk()
    try:
        CollectionGUI(window)
    except Exception as error:
        messagebox.showerror("GUI 시작 실패", str(error), parent=window)
        window.destroy()
        return
    window.mainloop()


if __name__ == "__main__":
    main()
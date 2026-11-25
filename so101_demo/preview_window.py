"""Separate-process ACT preview so GUI stalls cannot block motor control."""
import multiprocessing as mp
import queue
import re
import subprocess
import time
from functools import lru_cache
import cv2
import numpy as np

WINDOW = 'SO-101 local ACT'

@lru_cache(maxsize=1)
def screen_size():
    try:
        outputs = subprocess.check_output(['xrandr', '--query'], text=True, timeout=2)
        modes = re.findall(r'^\S+ connected (primary )?(\d+)x(\d+)[+-]\d+[+-]\d+', outputs, re.M)
        if modes:
            _, width, height = max(modes, key=lambda mode: bool(mode[0]))
            return int(width), int(height)
    except (OSError, subprocess.SubprocessError):
        pass
    return 1920, 1080

def show_fullscreen(title, view):
    cv2.imshow(title, cv2.resize(view, screen_size(), interpolation=cv2.INTER_LINEAR))

def open_fullscreen(title):
    cv2.namedWindow(title, cv2.WINDOW_NORMAL | cv2.WINDOW_FREERATIO | cv2.WINDOW_GUI_NORMAL)
    show_fullscreen(title, np.zeros((1, 1, 3), np.uint8))
    cv2.waitKey(30)
    cv2.setWindowProperty(title, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

def _display(frame_queue, ready, stopped, closing):
    try:
        open_fullscreen(WINDOW)
        cv2.waitKey(1)
        ready.set()
        while not closing.is_set():
            try:
                left, right, status = frame_queue.get(timeout=0.02)
                view = np.hstack((left, right))
                cv2.putText(view, status, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, .5, (0,255,255), 1)
                show_fullscreen(WINDOW, view)
            except queue.Empty:
                pass
            key = cv2.waitKey(1) & 255
            if key in (ord('q'), ord('Q'), 27):
                stopped.set()
                break
            if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                stopped.set()
                break
    finally:
        cv2.destroyAllWindows()

class PreviewWindow:
    def __init__(self):
        ctx = mp.get_context('spawn')
        self.frames = ctx.Queue(maxsize=1)
        self.ready = ctx.Event()
        self.stopped = ctx.Event()
        self.closing = ctx.Event()
        self.process = ctx.Process(target=_display, args=(self.frames, self.ready, self.stopped, self.closing), daemon=True)
        self.last_submit = 0.
        self.process.start()
        if not self.ready.wait(10) or not self.process.is_alive():
            self.close()
            raise RuntimeError('영상 표시 창을 시작하지 못했습니다.')

    def show(self, images, status):
        if not self.process.is_alive():
            raise RuntimeError('영상 표시 창이 종료됐습니다.')
        now = time.monotonic()
        if now-self.last_submit >= 0.1:
            self.last_submit = now
            left = cv2.resize(images[0], (320, 240), interpolation=cv2.INTER_AREA)
            right = cv2.resize(images[1], (320, 240), interpolation=cv2.INTER_AREA)
            try:
                self.frames.put_nowait((left, right, status))
            except queue.Full:
                pass
        return ord('q') if self.stopped.is_set() else -1

    def close(self):
        self.closing.set()
        if self.process.is_alive():
            self.process.join(timeout=2)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=2)
        self.frames.cancel_join_thread()
        self.frames.close()

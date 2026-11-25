"""ACT action-chunk operations adapted from the existing safe runner.

This module does not command motors. Input bounds/watchdogs must be applied by
the calling controller; these helpers alone do not make a plan safe.
"""
from collections import deque
import numpy as np


class DollGripHold:
    """Ease sustained closing demand when the measured opening stops changing."""

    HOLD_MARGIN = 2.0  # Gripper position units on its normalized 0–100 scale.

    def __init__(self):
        self.since = None
        self.anchor = None
        self.contact = None

    def target(self, now, opening, requested):
        if self.contact is not None:
            if requested < self.contact:
                return max(requested, max(self.contact, opening) - self.HOLD_MARGIN)
            self.contact = None
        if opening - requested < 3.5:
            self.since = None
        elif self.since is None or abs(opening - self.anchor) > .75:
            self.since = now
            self.anchor = opening
        elif now - self.since >= .30:
            self.contact = opening
            self.since = None
            return max(requested, opening - self.HOLD_MARGIN)
        return requested

def switch_action_plans(old_remaining, new_chunk, elapsed_steps, blend_frames=8):
    old = np.asarray(old_remaining, dtype=np.float32)
    new = np.asarray(new_chunk, dtype=np.float32)
    if old.ndim != 2 or old.shape[1] != 6 or new.shape != (100,6):
        raise ValueError('invalid plan shape')
    if not np.isfinite(old).all() or not np.isfinite(new).all():
        raise ValueError('non-finite plan')
    offset = min(max(int(elapsed_steps), 0), len(new)-1)
    switched = new[offset:].copy()
    blend = min(blend_frames, len(old), len(switched))
    if blend:
        alpha = (np.arange(1, blend+1, dtype=np.float32)/(blend+1))[:,None]
        switched[:blend] = (1-alpha)*old[:blend] + alpha*switched[:blend]
        switched[:blend, 5] = np.maximum(switched[:blend, 5], new[offset:offset+blend, 5])
    return switched

def action_with_early_gripper_close(plan, index, lead_frames):
    plan = np.asarray(plan, dtype=np.float32)
    if plan.ndim != 2 or plan.shape[1] != 6 or not 0 <= index < len(plan):
        raise ValueError('invalid action plan or index')
    if not 0 <= lead_frames <= 8: raise ValueError('invalid gripper lead')
    result = plan[index].copy()
    if lead_frames:
        result[5] = max(float(result[5]), float(plan[min(index+lead_frames,len(plan)-1),5]))
    return result

class StallMonitor:
    def __init__(self):
        self.history = deque()
    def reset(self):
        self.history.clear()
    def update(self, now, current, command):
        current = np.asarray(current, dtype=np.float32)
        command = np.asarray(command, dtype=np.float32)
        if current.shape != (6,) or command.shape != (6,) or not np.isfinite(current).all() or not np.isfinite(command).all():
            raise ValueError('invalid state or command')
        self.history.append((now, current.copy()))
        while self.history and now-self.history[0][0] > 4.0: self.history.popleft()
        if len(self.history) < 2 or now-self.history[0][0] < 3.2: return
        old = self.history[0][1]
        for i in (1,2,3):
            if abs(float(command[i]-current[i])) >= 8.0:
                samples = [float(pos[i]) for _, pos in self.history]
                if max(samples)-min(samples) >= 0.15:
                    continue
                name = ('shoulder_lift', 'elbow_flex', 'wrist_flex')[i-1]
                raise RuntimeError('{} 정지 감지: 현재 {:.2f}°, 제한 전 목표 {:.2f}°, '
                                   '{:.2f}초 동안 시작/끝 차이 {:.2f}°, 전체 이동폭 {:.2f}°'.format(
                                       name, current[i], command[i], now-self.history[0][0],
                                       abs(current[i]-old[i]), max(samples)-min(samples)))

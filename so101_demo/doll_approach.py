"""Top-view feedback for the orange demo doll and purple SO-101 gripper."""
import cv2
import numpy as np


def locate(top):
    # Work in the same 320x240 coordinates as the recorded approach previews.
    hsv = cv2.cvtColor(top[::2, ::2], cv2.COLOR_BGR2HSV)
    orange = cv2.inRange(hsv, (5, 150, 130), (24, 255, 255))
    count, _, stats, centers = cv2.connectedComponentsWithStats(orange)
    dolls = [i for i in range(1, count)
             if 60 <= stats[i, 4] <= 650 and 6 <= stats[i, 2] <= 42
             and 6 <= stats[i, 3] <= 42 and centers[i, 1] > 55]
    if len(dolls) != 1:
        return None
    purple = cv2.inRange(hsv, (120, 55, 18), (160, 255, 220))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(purple)
    if count < 2:
        return None
    arm = 1 + np.argmax(stats[1:, 4])
    x, y, w, h, area = stats[arm]
    if area < 800 or y > 50 or h < 50 or x == 0 or x+w >= hsv.shape[1]:
        return None
    tip_y = y+h-1
    _, xs = np.where(labels[tip_y-9:tip_y+1] == arm)
    tip_x = (xs.min()+xs.max()) / 2
    return centers[dolls[0]], np.array([tip_x, tip_y])


class DollApproach:
    def __init__(self):
        self.target = None
        self.offset = 0.
        self.confirmations = 0
        self.refreshed = False
        self.opened = False
        self.closed_samples = 0
        self.completed = False
        self.error_x = 0.
        self.close_target = None
        self.saw_close = False
        self.separated = 0
        self.missed = False
        self.pose_samples = 0
        self.wide_samples = 0
        self.lying = False
        self.bias_scale = 1.
        self.last_closed = False
        self.empty_cycles = 0
        self.close_center = None

    def side_observation(self, side, opening):
        hsv = cv2.cvtColor(side[::2, ::2], cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, (4,115,100), (23,255,255))
        _, _, stats, centers = cv2.connectedComponentsWithStats(mask)
        candidates = [i for i in range(1,len(stats)) if 450 <= stats[i,4] <= 3000
                      and min(stats[i,2:4]) >= 18 and stats[i,0] > 0
                      and stats[i,0]+stats[i,2] < hsv.shape[1]]
        if len(candidates) != 1:
            return
        i = candidates[0]
        if self.pose_samples < 8:
            self.pose_samples += 1
            self.wide_samples += int(stats[i,2] >= 1.04*stats[i,3])
            self.lying = self.pose_samples == 8 and self.wide_samples >= 7
        if not self.lying or not self.opened:
            return
        center = centers[i]
        if self.close_center is not None and np.linalg.norm(self.close_center-center) > 8:
            self.close_center = None
            self.empty_cycles = 0
        if opening < 12 and not self.last_closed:
            self.last_closed = True
            self.close_center = center.copy()
        elif opening > 20 and self.last_closed:
            self.last_closed = False
            if self.close_center is not None:
                self.empty_cycles += 1

    def observe(self, top, opening, finished, side=None):
        """Called at 10 Hz. Request at most one extra ACT plan per first reach."""
        if opening > 20:
            if self.closed_samples:
                self.completed = True
            self.opened = True
        if self.opened and opening < 12:
            self.closed_samples += 1
            if self.closed_samples >= 10:
                self.completed = True
        if side is not None and (self.pose_samples < 8 or self.lying):
            self.side_observation(side, opening)
        observation = locate(top)
        self.error_x = 0.
        if observation is not None:
            target, tip = observation
            if self.opened and opening < 12 and not self.saw_close:
                self.close_target = target.copy()
                self.saw_close = True
            # An empty close followed by reopening: the doll stayed on the
            # table while the gripper moved away. Do not continue the transfer.
            if self.close_target is not None and np.linalg.norm(target-self.close_target) > 8:
                self.close_target = None
            stationary_miss = (self.close_target is not None and opening > 20
                               and np.linalg.norm(target-tip) > 32)
            self.separated = self.separated+1 if stationary_miss else 0
            self.missed = self.separated >= 6
        else:
            self.separated = 0
        if self.empty_cycles >= 2:
            self.missed = True
        if observation is None or finished or self.completed:
            self.confirmations = 0
            self.offset -= float(np.clip(self.offset, -.3, .3))
            return False
        target, tip = observation
        if self.target is None:
            self.target = target.copy()
        dx, dy = target - tip
        if self.lying and self.opened and opening >= 15 and abs(dy) < 24:
            # Negative pan pushes to image right. Fade that bias when the
            # horizontal image error no longer calls for rightward motion.
            self.bias_scale = float(np.clip((dx+2)/8, 0., 1.))
        if self.opened and opening >= 15 and abs(dy) < 24 and 8 < abs(dx) < 65:
            self.error_x = dx
        if opening < 15:
            self.confirmations = 0
            return False
        # On this camera, increasing shoulder_pan moves the tips to image left.
        # Limit feedback to the open approach near the target.
        if abs(dy) < 36 and abs(dx) < 65 and abs(dx) > 5:
            self.offset = float(np.clip(self.offset-np.clip(dx*.015, -.3, .3), -3., 3.))
        moved = np.linalg.norm(target-self.target) > 12
        passed = dy < -10 and abs(dx) < 40
        self.confirmations = self.confirmations+1 if moved or passed else 0
        if self.confirmations >= 3 and not self.refreshed:
            self.refreshed = True
            return True
        return False

    def limit_pan(self, desired, measured):
        # Once the tips are near the doll's depth in the top image, prevent
        # ACT from commanding still more yaw away from the visible target.
        if self.error_x:
            # Ask for a small move toward the doll, including when ACT is
            # holding the yaw that left a lying doll just outside the fingers.
            nudge = float(np.clip((abs(self.error_x)-8)*.04, 0., .45))
            if self.error_x > 0:
                return min(desired, measured-nudge)
            return max(desired, measured+nudge)
        return desired

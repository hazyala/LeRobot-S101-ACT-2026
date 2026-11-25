"""Pure safety checks for the future Jetson controller; no motor or network IO."""
import math
import numpy as np

# The limits are inherited from the existing ACT runner.
MAX_DELTA = np.array([2, 3, 3, 4, 4, 5], dtype=float)
MAX_TRACKING = np.array([6, 10, 10, 10, 8, 10], dtype=float)
STATE_MARGIN = np.array([20, 20, 20, 25, 30, 20], dtype=float)

def vector(value, name):
    x = np.asarray(value, dtype=float)
    if x.shape != (6,) or not np.isfinite(x).all():
        raise ValueError(name + ' must contain six finite values')
    return x

def safe_action(raw, current, previous, lower, upper):
    raw, current = vector(raw, 'action'), vector(current, 'state')
    lower, upper = vector(lower, 'lower bound'), vector(upper, 'upper bound')
    if np.any(lower >= upper):
        raise ValueError('invalid action bounds')
    if np.any(current < lower - STATE_MARGIN) or np.any(current > upper + STATE_MARGIN):
        raise RuntimeError('robot state outside watchdog bounds')
    violation = (np.maximum(lower - raw, 0) + np.maximum(raw - upper, 0)) / (upper - lower)
    if np.any(violation > 0.25):
        raise RuntimeError('predicted action outside demonstrated range')
    target = np.clip(raw, lower, upper)
    prior = current if previous is None else vector(previous, 'previous command')
    target = prior + np.clip(target - prior, -MAX_DELTA, MAX_DELTA)
    target = np.clip(target, current - MAX_TRACKING, current + MAX_TRACKING)
    return np.clip(target, lower, upper)

def valid_reply(request_id, reply, elapsed_s, deadline_s):
    """Reject late, mismatched, non-finite and malformed action plans."""
    if not math.isfinite(elapsed_s) or elapsed_s < 0 or elapsed_s > deadline_s:
        raise TimeoutError('inference response expired')
    if reply.get('id') != request_id:
        raise ValueError('inference response id mismatch')
    actions = np.asarray(reply.get('actions'), dtype=float)
    if actions.shape != (100, 6) or not np.isfinite(actions).all():
        raise ValueError('invalid action plan')
    return actions

class PlanGate:
    """For controller integration: a lost connection invalidates all actions."""
    def __init__(self):
        self.plan = None
        self.index = 0
        self.connected = False

    def install(self, request_id, reply, elapsed_s, deadline_s):
        self.plan = None
        self.connected = False
        plan = valid_reply(request_id, reply, elapsed_s, deadline_s)
        self.plan = plan
        self.index = 0
        self.connected = True

    def disconnect(self):
        self.connected = False
        self.plan = None
        self.index = 0

    def next_action(self):
        if not self.connected or self.plan is None or self.index >= len(self.plan):
            raise RuntimeError('no current inference plan')
        action = self.plan[self.index].copy()
        self.index += 1
        return action

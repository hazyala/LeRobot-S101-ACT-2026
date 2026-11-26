"""Interactive calibration helpers are deliberately unavailable in the demo."""
def enter_pressed():
    raise RuntimeError('Interactive calibration is not supported')

def move_cursor_up(lines):
    raise RuntimeError('Interactive calibration is not supported')

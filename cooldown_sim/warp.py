"""Sim Control's speed slider: position 0-100 <-> clock speed (Elena Long, 2026-11-04).

Like a time-warp control: the slider clicks at 0 (paused) and at 1x, and
slides smoothly otherwise -- logarithmically, 0.1x to 1x below the 1x click and
1x to 600x above it.

    position  0 .. 2     paused (snaps to 0)
              2 .. 8     0.1x .. 1x
              8 .. 12    1x (snaps to 10)
             12 .. 100   1x .. 600x
"""

from __future__ import annotations

import math

from .clock import MAX_SPEED, MIN_SPEED

PAUSE_BELOW = 2.0
ONE_LO, ONE_HI, ONE = 8.0, 12.0, 10.0
TOP = 100.0
#: slider positions of the scale marks
MARKS = {"pause": 0.0, "0.1x": PAUSE_BELOW, "1x": ONE}


def snap(pos: float) -> float:
    """The position the slider clicks to (0 or the 1x mark), else ``pos``."""
    pos = min(max(float(pos), 0.0), TOP)
    if pos < PAUSE_BELOW:
        return 0.0
    if ONE_LO <= pos <= ONE_HI:
        return ONE
    return pos


def to_speed(pos: float) -> float:
    """Clock speed for a slider position; 0 means paused."""
    pos = snap(pos)
    if pos == 0.0:
        return 0.0
    if pos == ONE:
        return 1.0
    if pos < ONE_LO:
        frac = (pos - PAUSE_BELOW) / (ONE_LO - PAUSE_BELOW)
        return MIN_SPEED * (1.0 / MIN_SPEED) ** frac
    frac = (pos - ONE_HI) / (TOP - ONE_HI)
    return min(MAX_SPEED ** frac, MAX_SPEED)


def to_pos(speed: float, running: bool = True) -> float:
    """Slider position showing ``speed`` (0 when paused)."""
    if not running or speed <= 0:
        return 0.0
    speed = min(max(float(speed), MIN_SPEED), MAX_SPEED)
    if abs(speed - 1.0) < 1e-9:
        return ONE
    if speed < 1.0:
        return PAUSE_BELOW + (ONE_LO - PAUSE_BELOW) * math.log(speed / MIN_SPEED) / math.log(1.0 / MIN_SPEED)
    return ONE_HI + (TOP - ONE_HI) * math.log(speed) / math.log(MAX_SPEED)


for _label, _speed in (("10x", 10.0), ("100x", 100.0), ("600x", MAX_SPEED)):
    MARKS[_label] = to_pos(_speed)

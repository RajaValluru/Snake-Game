"""Tiny pure-math helpers shared by the game-logic modules.

These functions must stay pygame-free so they can be unit-tested headless.
"""

from __future__ import annotations

import math
from typing import Tuple

Point = Tuple[float, float]


def dist(ax: float, ay: float, bx: float, by: float) -> float:
    """Euclidean distance between two points."""
    return math.hypot(bx - ax, by - ay)


def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp `value` into [lo, hi]."""
    return max(lo, min(hi, value))


def lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation from `a` to `b` by fraction `t`."""
    return a + (b - a) * t


def wrap_pi(angle: float) -> float:
    """Normalize an angle in radians into [-pi, pi]."""
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def angle_towards(dx: float, dy: float) -> float:
    """Heading (radians) that points from the origin toward (dx, dy)."""
    return math.atan2(dy, dx)


def point_at_angle(x: float, y: float, heading_rad: float, distance: float) -> Point:
    """Point `distance` away from (x, y) along direction `heading_rad`."""
    return (x + math.cos(heading_rad) * distance, y + math.sin(heading_rad) * distance)

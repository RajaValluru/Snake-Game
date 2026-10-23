"""Arc-length parameterized history of the snake head's path (pure math).

The :class:`TrailBuffer` records where the head has been, ordered oldest ->
newest, together with cumulative arc lengths.  Any point "N px behind the
head" can then be recovered in O(log n) by binary search over the cumulative
lengths plus linear interpolation between two neighboring points.

This buffer is what makes the snake's body follow every curve the mouse drew:
body segments are simply resamples of this shared history, offset in arc
length behind one another.
"""

from __future__ import annotations

import bisect
import math
from typing import List, Optional, Tuple

from .geom import Point


class TrailBuffer:
    """Ordered list of recorded points with cumulative arc lengths."""

    def __init__(self) -> None:
        # points[i] is the i-th recorded position (oldest first).
        self.points: List[Point] = []
        # cum[i] is the arc length from points[0] to points[i]; cum[0] == 0.
        self.cum: List[float] = []

    # -- basic properties ----------------------------------------------------

    @property
    def head(self) -> Optional[Point]:
        """Most recent recorded position (None if empty)."""
        return self.points[-1] if self.points else None

    @property
    def total_length(self) -> float:
        """Arc length of the whole recorded history."""
        return self.cum[-1] if self.cum else 0.0

    # -- recording -------------------------------------------------------------

    def add_point(self, x: float, y: float, min_step: float = 3.0) -> bool:
        """Record (x, y), unless it is closer than `min_step` to the last
        *recorded* point.  Returns True if a new point was stored."""
        px, py = self.points[-1] if self.points else (x, y)
        d = math.hypot(x - px, y - py)
        if self.points and d < min_step:
            return False
        self.points.append((x, y))
        self.cum.append(self.total_length + d if self.cum else 0.0)
        return True

    def seed_straight_back(
        self, x: float, y: float, heading_rad: float, length: float, step: float = 3.0
    ) -> None:
        """Create an initial history: a straight line of `length` px ending at
        (x, y), extending *behind* the head opposite to its travel direction.

        Used at game start so the full body already exists on frame one.
        """
        n = max(1, int(math.ceil(length / step)))
        points: List[Point] = []
        cums: List[float] = [0.0]
        prev: Optional[Point] = None
        for i in range(n + 1):
            back = max(0.0, length - i * step)
            p = (x - math.cos(heading_rad) * back, y - math.sin(heading_rad) * back)
            if prev is not None:
                cums.append(cums[-1] + math.hypot(p[0] - prev[0], p[1] - prev[1]))
            points.append(p)
            prev = p
        self.points, self.cum = points, cums

    # -- querying ---------------------------------------------------------------

    def sample(self, distance_behind: float) -> Point:
        """Point on the trail `distance_behind` px behind the newest point.

        The request is clamped to the available history: asking for more than
        ``total_length`` returns the oldest recorded point (the tail simply
        "waits" there until enough history has been recorded).
        """
        if not self.points:
            raise ValueError("trail is empty; seed it or add points first")
        if len(self.points) == 1:
            return self.points[0]
        target = max(0.0, self.cum[-1] - min(distance_behind, self.total_length))
        i = bisect.bisect_left(self.cum, target)
        if i == 0:
            return self.points[0]
        c0, c1 = self.cum[i - 1], self.cum[i]
        if c1 - c0 < 1e-9:
            return self.points[i]
        t = (target - c0) / (c1 - c0)
        p0, p1 = self.points[i - 1], self.points[i]
        return (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)

    # -- maintenance ------------------------------------------------------------

    def trim(self, max_keep_length: float) -> None:
        """Drop oldest points so the remaining history spans at most
        `max_keep_length` px.  The cumulative lengths are rebased to start at 0."""
        if len(self.points) < 3 or self.total_length - max_keep_length <= 0:
            return
        need = self.total_length - max_keep_length
        i = bisect.bisect_left(self.cum, need)
        if i == 0:
            return
        del self.points[:i]
        del self.cum[:i]
        offset = self.cum[0]
        if offset != 0.0:
            self.cum = [c - offset for c in self.cum]

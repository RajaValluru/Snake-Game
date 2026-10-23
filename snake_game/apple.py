"""Apple spawning and eating rules (pure logic, no pygame)."""

from __future__ import annotations

import random
from typing import List, Tuple

from .config import GameConfig
from .geom import Point, dist
from .snake import Snake


class Apple:
    """A static food item with a position and radius."""

    def __init__(self, pos: Point, radius: float) -> None:
        self.pos: Point = (float(pos[0]), float(pos[1]))
        self.radius: float = float(radius)

    @property
    def x(self) -> float:
        return self.pos[0]

    @property
    def y(self) -> float:
        return self.pos[1]

    def is_eaten(self, snake: Snake) -> bool:
        """True when the head overlaps the apple."""
        reach = self.radius + 0.7 * snake.head_radius
        return dist(self.x, self.y, snake.pos[0], snake.pos[1]) < reach


def spawn_apple(
    cfg: GameConfig, rng: random.Random, snake: Snake, tries: int = 250
) -> Apple:
    """Pick an apple position that is inside the margins, at least
    ``min_apple_dist_from_head_px`` from the head, and not sitting on top of
    the body.

    If no candidate passes (e.g. a very long snake filling most of the window),
    falls back to a plain random position so the game never stalls.
    """
    m = cfg.apple_spawn_margin
    x_min, x_max = float(m), max(float(m + 1), float(cfg.width - m))
    y_min, y_max = float(m), max(float(m + 1), float(cfg.height - m))

    # Body samples to keep clear of (every third one is dense enough).
    body: List[Tuple[Point, float]] = snake.body_samples_with_radii()

    def valid(x: float, y: float) -> bool:
        if dist(x, y, snake.pos[0], snake.pos[1]) < cfg.min_apple_dist_from_head_px:
            return False
        for i in range(2, len(body), 3):
            p, r = body[i]
            if dist(x, y, p[0], p[1]) < cfg.apple_radius + r + 8.0:
                return False
        return True

    for _ in range(tries):
        x, y = rng.uniform(x_min, x_max), rng.uniform(y_min, y_max)
        if valid(x, y):
            return Apple((x, y), cfg.apple_radius)
    return Apple((rng.uniform(x_min, x_max), rng.uniform(y_min, y_max)), cfg.apple_radius)

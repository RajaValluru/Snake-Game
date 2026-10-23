"""Visual-effect state shared between game logic and the renderer (no pygame).

Two families of effect live here.  Both are *pure data* owned by
:class:`~snake_game.game.Game`; this module only defines what a particle /
patch IS, not when they appear — spawning/expiring/slowing rules stay in
``game.py`` so they remain unit-testable headless:

- :class:`FlameParticle`  -- one puff of nitro flame trailing off the tail tip
  while the player holds LEFT click.  The renderer paints them as layered,
  flickering, fading circles (see ``Renderer._paint_flames_and_head_fx``).
- :class:`IcePatch`       -- a frozen disc dropped in front of the head by a
  RIGHT click.  While the head stays inside an active patch, top speed is
  scaled down by ``GameConfig.ice_speed_factor`` (the "slowing down" effect);
  patches melt after their lifetime.

Precomputed per-patch speckle offsets keep the renderer deterministic and free
of any RNG of its own.
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

# A speckle: (dx, dy) in *unit-disc* coordinates relative to the patch center,
# radius as a fraction of the patch radius, and a twinkle phase (radians).
Speckle = Tuple[float, float, float, float]


def step_flames(flames: List["FlameParticle"], dt: float) -> None:
    """Advance every particle by ``dt`` seconds in place and drop the dead ones.

    Mutates the list; call it once per frame from :meth:`Game.update`."""
    if not flames or dt <= 0.0:
        return
    for p in flames:
        p.x += p.vx * dt
        p.y += p.vy * dt
        p.life -= dt
    alive = [p for p in flames if p.life > 0.0]
    flames[:] = alive


class FlameParticle:
    """One nitro flame puff (pure data; the renderer draws it)."""

    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size", "phase")

    def __init__(self, x: float, y: float, vx: float, vy: float, life_s: float, size_px: float, phase: float) -> None:
        self.x = x            # current world position
        self.y = y
        self.vx = vx          # px/s drift (mostly backward along the tail's travel direction)
        self.vy = vy
        self.life = life_s    # seconds remaining
        self.max_life = life_s
        self.size = size_px   # starting radius, px; the renderer shrinks it over life
        self.phase = phase    # random offset driving the per-frame flicker

    @property
    def age_fraction(self) -> float:
        """0 at birth -> 1 just before death (drives color/size fade)."""
        if self.max_life <= 0.0:
            return 1.0
        f = 1.0 - self.life / self.max_life
        return max(0.0, min(1.0, f))


class IcePatch:
    """A frozen disc on the playfield that slows the head while it is inside."""

    __slots__ = ("x", "y", "radius", "lifetime_s", "age", "speckles")

    def __init__(self, x: float, y: float, radius: float, lifetime_s: float, speckles: Optional[List[Speckle]] = None) -> None:
        self.x = x                  # patch center (world px)
        self.y = y
        self.radius = radius        # px
        self.lifetime_s = lifetime_s
        self.age = 0.0              # seconds since the patch was dropped
        self.speckles: List[Speckle] = list(speckles or [])

    @property
    def time_left(self) -> float:
        return max(0.0, self.lifetime_s - self.age)

    def contains(self, x: float, y: float) -> bool:
        """True when a point at (x, y) is inside this still-active patch."""
        if self.time_left <= 0.0:
            return False
        dx, dy = x - self.x, y - self.y
        r2 = self.radius * self.radius
        return dx * dx + dy * dy <= r2

    def age_by(self, dt: float) -> None:
        if dt > 0.0:
            self.age += dt

    def alpha_scale(self) -> float:
        """Visual strength in [0, 1]: quick fade-in, gentle melt-out during the
        final second of life."""
        if self.time_left <= 0.0 or self.lifetime_s <= 0.0:
            return 0.0
        ramp_in = min(1.0, self.age / 0.25)
        fade_out = max(0.0, min(1.0, self.time_left))  # full strength until the last second
        return ramp_in * fade_out


def make_patch_speckles(rng, count: int = 8) -> List[Speckle]:
    """Random-but-stable frost speckles for a patch (unit-disc coordinates)."""
    out: List[Speckle] = []
    for _ in range(count):
        a = rng.uniform(0.0, math.tau)
        d = rng.uniform(0.12, 0.85)
        out.append((math.cos(a) * d, math.sin(a) * d, rng.uniform(0.035, 0.075), rng.uniform(0.0, math.tau)))
    return out

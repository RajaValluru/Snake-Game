"""The snake: head kinematics plus body sampling from the shared trail.

This module is pure math (no pygame) so it can be simulated and unit-tested
headless.  Key ideas:

- The head chases a target point (the mouse cursor) at a limited speed with a
  limited turn rate, which is what produces smooth curves instead of snaps.
- The body is not steered segment-by-segment; every sample is a resample of
  the head's recorded path (a :class:`~snake_game.trail.TrailBuffer`) taken at
  fixed arc-length spacing behind the head.  That makes the body follow every
  curve the cursor drew, by construction.
- Growth is continuous: eating raises a *target* length and the real body
  eases toward it, so new tail slides out along whatever curved path already
  exists there.
- Speed multipliers (nitro boost / ice slowdown) scale both the desired speed
  and the top-speed cap, so they ease in/out with the same ``speed_ease``
  ramp instead of teleporting the head's velocity.
"""

from __future__ import annotations

import math
from typing import List, Tuple

from .config import GameConfig
from .geom import Point, angle_towards, clamp, dist, lerp, wrap_pi
from .trail import TrailBuffer


class Snake:
    """A mouse-steered snake with a continuous (non-blocky) body."""

    def __init__(self, cfg: GameConfig, start: Point, heading_rad: float) -> None:
        self.cfg = cfg
        self.pos: Point = (float(start[0]), float(start[1]))
        self.heading: float = heading_rad  # radians; 0 = +x axis
        self.speed: float = 0.0           # current forward speed, px/s

        self.length_px: float = float(cfg.initial_length_px)         # real body length
        self.target_length_px: float = float(cfg.initial_length_px)  # where growth is heading

        self.boost_factor: float = 1.0  # eased nitro multiplier (1.0 -> cfg.nitro_speed_multiplier)

        # Seed enough straight history that the whole starting body exists at once.
        self.trail = TrailBuffer()
        self.trail.seed_straight_back(
            self.pos[0], self.pos[1], heading_rad,
            cfg.initial_length_px + 2 * cfg.segment_spacing,
            cfg.trail_min_step,
        )

    # -- convenience ---------------------------------------------------------

    @property
    def head_radius(self) -> float:
        return self.cfg.head_radius

    @property
    def segment_count(self) -> int:
        """Number of body samples behind the head (for HUD display)."""
        return max(0, int(self.length_px // self.cfg.segment_spacing))

    def grow_by(self, px: float) -> None:
        """Add `px` to the *target* length.  The real body extends toward it at
        most ``max_growth_rate_px_s`` inside :meth:`update`, so growth is a
        smooth slide out of the tail rather than an instant block."""
        self.target_length_px = min(self.cfg.max_length_px, self.target_length_px + px)

    @property
    def boost_level(self) -> float:
        """Normalized nitro strength in [0, 1] (drives flame spawn rate)."""
        cfg = self.cfg
        span = max(1e-6, cfg.nitro_speed_multiplier - 1.0)
        return clamp((self.boost_factor - 1.0) / span, 0.0, 1.0)

    # -- simulation ------------------------------------------------------------

    def _desired_speed(self, target: Point, speed_mult: float) -> float:
        """Cruise speed: full (multiplied) speed far from the cursor,
        crawling/stopped right on top of it (so a parked cursor does not drag
        the snake into a wall).  `speed_mult` scales the top-speed term only;
        the cursor-proximity term is untouched, so nitro can never break
        "parked cursor = stopped"."""
        d = dist(self.pos[0], self.pos[1], target[0], target[1])
        if d < 2.0:
            return 0.0
        cfg = self.cfg
        return min(cfg.head_speed * speed_mult, d * cfg.cursor_chase_gain)

    def update(
        self,
        dt: float,
        target: Point,
        *,
        boost_active: bool = False,
        ice_speed_factor: float = 1.0,
    ) -> None:
        """Advance the head toward `target` by `dt` seconds and record its path.

        `boost_active` (nitro held) eases :attr:`boost_factor` up to
        ``cfg.nitro_speed_multiplier``; `ice_speed_factor` (< 1.0 while the head
        is on an ice patch) scales speed down.  Both affect desired speed and
        the top-speed cap, so the change rides the existing ease curve.
        """
        if dt <= 0.0:
            return
        cfg = self.cfg

        # --- nitro: ease the boost multiplier toward on/off ------------------
        want_boost = cfg.nitro_speed_multiplier if boost_active else 1.0
        ramp_k = min(1.0, cfg.nitro_ramp_rate * dt)
        self.boost_factor += (want_boost - self.boost_factor) * ramp_k
        speed_mult = self.boost_factor * max(ice_speed_factor, 0.05)

        # --- speed: ease toward the cursor-chase speed ----------------------
        want = self._desired_speed(target, speed_mult)
        step_size = cfg.speed_ease * dt
        cap = cfg.head_speed * max(cfg.nitro_speed_multiplier, 1.0)  # allow full nitro top speed
        self.speed = clamp(
            self.speed + clamp(want - self.speed, -step_size, step_size), 0.0, cap
        )

        # --- steering: turn toward the target at a limited rate -------------
        dx = target[0] - self.pos[0]
        dy = target[1] - self.pos[1]
        if math.hypot(dx, dy) > 1e-3:
            desired = angle_towards(dx, dy)
            max_turn = cfg.turn_rate * dt
            self.heading += clamp(wrap_pi(desired - self.heading), -max_turn, max_turn)

        # --- advance the head and record where it went ------------------------
        move = self.speed * dt
        if move > 1e-6:
            x = self.pos[0] + math.cos(self.heading) * move
            y = self.pos[1] + math.sin(self.heading) * move
            r, w, h = cfg.head_radius, cfg.width, cfg.height
            # soft wall: the head is kept inside the playfield instead of dying on edges
            self.pos = (clamp(x, r, max(r, w - r)), clamp(y, r, max(r, h - r)))
        self.trail.add_point(self.pos[0], self.pos[1], cfg.trail_min_step)

        # --- smooth growth toward the target length ---------------------------
        if self.length_px < self.target_length_px:
            self.length_px = min(
                self.target_length_px, self.length_px + cfg.max_growth_rate_px_s * dt
            )

        # keep just enough path history for the current body (plus a little slack)
        self.trail.trim(self.length_px + 2.0 * cfg.segment_spacing)

    # -- body geometry ----------------------------------------------------------

    def body_samples_with_radii(self) -> List[Tuple[Point, float]]:
        """Return ``(position, radius)`` for every body sample, index 0 first (head).

        Sample k sits exactly ``k * segment_spacing`` of arc length behind the
        head on the recorded path; the radius tapers from ``head_radius`` to
        ``tail_radius`` toward the tail.
        """
        cfg = self.cfg
        n = int(self.length_px // cfg.segment_spacing)
        samples: List[Tuple[Point, float]] = [(self.pos, cfg.head_radius)]
        for k in range(1, n + 1):
            p = self.trail.sample(k * cfg.segment_spacing)
            t = (k - 0.5) / n if n >= 1 else 0.0
            r = lerp(cfg.head_radius, cfg.tail_radius, min(1.0, t))
            samples.append((p, r))
        return samples

    def tail_point(self) -> Point:
        """World position of the very end (tip) of the body."""
        if not self.trail.points:
            return self.pos
        return self.trail.sample(self.length_px)

    def tail_travel_dir(self) -> Tuple[float, float]:
        """Unit vector along which the tail tip is currently moving.

        Estimated from two nearby trail samples (a short chord of the recorded
        path), so flames emitted at the tail trail correctly even through
        curves.  Falls back to the head's forward direction when history is
        too short to measure.
        """
        if len(self.trail.points) < 2 or self.trail.total_length <= 1e-6:
            return (math.cos(self.heading), math.sin(self.heading))
        total = self.trail.total_length
        tip_d = min(self.length_px, max(0.0, total))          # the tail tip
        ahead_d = max(0.0, tip_d - 12.0)                      # slightly toward the head
        behind_d = min(total, tip_d + 12.0)                   # slightly past the tip (older path)
        a = self.trail.sample(ahead_d)
        b = self.trail.sample(behind_d)
        dx, dy = a[0] - b[0], a[1] - b[1]
        m = math.hypot(dx, dy)
        if m < 1e-3:
            return (math.cos(self.heading), math.sin(self.heading))
        return (dx / m, dy / m)

    # -- collision ------------------------------------------------------------------

    def has_self_collision(self) -> bool:
        """True when the head is on top of a non-adjacent body sample."""
        cfg = self.cfg
        if not cfg.self_collision_enabled:
            return False
        samples = self.body_samples_with_radii()
        # Skip the head sample (index 0) and the ones that are always "near"
        # just because they are adjacent to the head.
        start = max(1, min(cfg.collision_skip_samples, len(samples) - 1))
        for k in range(start, len(samples), 2):
            p, r = samples[k]
            if dist(self.pos[0], self.pos[1], p[0], p[1]) < (cfg.head_radius + r) * cfg.collision_factor:
                return True
        return False

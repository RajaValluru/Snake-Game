"""Game state machine and per-frame rules (pure logic, no pygame).

Events are fed in as semantic calls (:meth:`Game.handle_click`,
:meth:`Game.handle_key`, :meth:`Game.add_ice_patch`) so this module stays
decoupled from pygame: the main loop is responsible for translating raw
events into these calls.

Effect state (nitro flame particles, ice patches) lives here as plain data
(see :mod:`snake_game.fx`); only *rendering* touches pygame:

- ``update(dt, mouse_pos, boost_held=...)``: the main loop reports whether the
  LEFT button is currently held; boosting eases the snake's top speed to
  ``nitro_speed_multiplier``x and spawns red flames at the tail tip.  Releasing
  the button ramps the multiplier back down and lets existing flames die out.
- :meth:`add_ice_patch` (RIGHT click): drops a frozen disc in front of the
  head; while the head is inside it, top speed is scaled by ``ice_speed_factor``
  so the snake "slides" through at reduced pace.  Patches melt after their
  lifetime.
- :meth:`Game.update` returns the semantic events that happened this frame
  (e.g. an apple was eaten, flames just started, head entered ice).  The main
  loop uses those to play sound effects — this module itself stays free of any
  audio/pygame dependency.
"""

from __future__ import annotations

import math
import random
from enum import Enum
from typing import List, Optional, Tuple

from .apple import Apple, spawn_apple
from .config import GameConfig
from .fx import FlameParticle, IcePatch, make_patch_speckles, step_flames
from .geom import Point, clamp, dist, point_at_angle
from .snake import Snake


class GameState(Enum):
    MENU = 0
    PLAYING = 1
    GAME_OVER = 2


# Semantic key names understood by :meth:`Game.handle_key`.
RESTART_KEYS: Tuple[str, ...] = ("r",)
CONFIRM_KEYS: Tuple[str, ...] = ("return", "space")

# -- sound-effect event names (returned by :meth:`Game.update`) -----------------
# Each is emitted exactly once per occurrence (transition-based), and the main
# loop maps them to generated SFX from :mod:`snake_game.audio_fx`.
EVENT_APPLE_EATEN = "apple_eaten"    # an apple was eaten (+1 score)
EVENT_FLAME_ON = "flame_on"          # nitro flame particles just started emitting
EVENT_ICE_ENTERED = "ice_entered"    # head entered ice (top speed now reduced)


class Game:
    """Owns the snake, apple, score and state; advanced once per frame."""

    def __init__(self, config: GameConfig, seed: Optional[int] = None) -> None:
        self.config = config
        self.rng = random.Random(seed)  # injected RNG keeps spawns reproducible
        self.state = GameState.MENU
        self.score = 0
        self.time = 0.0  # simulated seconds (drives animations like the apple pulse)

        spawn: Point = (config.width / 2.0, config.height / 2.0)
        self.snake = Snake(config, spawn, math.pi)  # start facing left
        self.apple: Apple = spawn_apple(config, self.rng, self.snake)

        # Effect state (plain data; the renderer paints it each frame).
        self.flames: List[FlameParticle] = []
        self.ice_patches: List[IcePatch] = []
        self._flame_acc = 0.0   # fractional flame-emission accumulator
        self._ice_seq = 0       # stable id per patch (drives speckle layout)
        self._on_ice = False            # was the head on ice last frame?
        self._flame_emitting = False    # are flames emitting right now?

    # -- state transitions ------------------------------------------------------

    def _make_fresh_snake(self) -> Snake:
        return Snake(
            self.config, (self.config.width / 2.0, self.config.height / 2.0), math.pi
        )

    def start(self) -> None:
        """Start (or restart) a game from MENU or GAME_OVER."""
        self.score = 0
        self.snake = self._make_fresh_snake()
        self.apple = spawn_apple(self.config, self.rng, self.snake)
        self.flames.clear()  # no lingering effects in a fresh run
        self.ice_patches.clear()
        self._flame_acc = 0.0
        self._on_ice = False
        self._flame_emitting = False
        self.state = GameState.PLAYING

    def handle_click(self) -> None:
        """A left mouse button click (from the main loop)."""
        if self.state in (GameState.MENU, GameState.GAME_OVER):
            self.start()

    def handle_key(self, name: str) -> None:
        """:meth:`Game.handle_key` receives semantic key names such as 'r',
        'return' or 'space' (mapped from pygame key codes by the main loop)."""
        if name in RESTART_KEYS:
            self.start()  # R restarts even mid-game
        elif name in CONFIRM_KEYS and self.state in (GameState.MENU, GameState.GAME_OVER):
            self.start()

    # -- effects --------------------------------------------------------------------

    def add_ice_patch(self) -> None:
        """A right mouse click: drop a frozen disc in front of the head.

        The patch centers ``ice_spawn_ahead_px`` ahead of the head along its
        current heading (clamped so it stays on screen).  While the head is
        inside any active patch, top speed is scaled by ``ice_speed_factor``,
        i.e. the snake slides through ice at reduced pace.  No-op outside PLAYING.
        """
        if self.state is not GameState.PLAYING:
            return
        cfg = self.config
        cx, cy = point_at_angle(
            self.snake.pos[0], self.snake.pos[1], self.snake.heading, cfg.ice_spawn_ahead_px
        )
        m = cfg.ice_patch_radius + 2.0
        cx = clamp(cx, m, max(m, cfg.width - m))
        cy = clamp(cy, m, max(m, cfg.height - m))
        if len(self.ice_patches) >= cfg.ice_max_patches:
            self.ice_patches.pop(0)  # oldest patch melts early
        self._ice_seq += 1
        speckles = make_patch_speckles(random.Random(self._ice_seq * 7919 + 1))
        self.ice_patches.append(IcePatch(cx, cy, cfg.ice_patch_radius, cfg.ice_lifetime_s, speckles))

    def ice_speed_factor_at(self, pos: Point) -> float:
        """Top-speed multiplier for a playfield point (1.0 = no effect).

        Multiple overlapping patches combine by taking the strongest slowdown.
        Used both by :meth:`update` (to slow the head) and by the renderer (to
        frost the head while it is on ice).
        """
        factor = 1.0
        for p in self.ice_patches:
            if p.contains(pos[0], pos[1]):
                factor = min(factor, self.config.ice_speed_factor)
        return factor

    def _spawn_flames(self, snake: Snake, dt: float) -> bool:
        """Emit nitro flame particles at the tail tip while boosting.

        Gated on both boost strength and actual head speed, so a parked cursor
        produces no flames; emission rate scales with ``boost_level``.  Returns
        True when the gate is open (flames are emitting right now).
        """
        cfg = self.config
        level = snake.boost_level
        if level < 0.15 or snake.speed < 60.0:
            return False
        self._flame_acc += cfg.flame_spawn_per_second * dt * (0.3 + 0.7 * level)
        while self._flame_acc >= 1.0 and len(self.flames) < cfg.flame_max_count:
            self._flame_acc -= 1.0
            tx, ty = snake.tail_point()
            dx, dy = snake.tail_travel_dir()  # direction the tail tip is moving
            px, py = -dy, dx                # perpendicular for lateral spread
            rng = self.rng
            jx, jy = (rng.uniform(-4.0, 4.0), rng.uniform(-4.0, 4.0))
            back = cfg.flame_speed_away + rng.uniform(0.0, 25.0)
            lat = rng.uniform(-cfg.flame_spread, cfg.flame_spread)
            life = rng.uniform(
                cfg.flame_lifetime_min_s,
                max(cfg.flame_lifetime_min_s, cfg.flame_lifetime_max_s),
            )
            self.flames.append(
                FlameParticle(
                    tx + jx, ty + jy,
                    -dx * back + px * lat, -dy * back + py * lat,
                    life,
                    cfg.flame_size_max * rng.uniform(0.7, 1.35),
                    rng.uniform(0.0, math.tau),
                )
            )
        return True

    def _update_fx(self, dt: float) -> None:
        """Age out effect state (runs in every game state so flames melt and ice
        fades even on the GAME OVER screen)."""
        step_flames(self.flames, dt)
        if self.ice_patches:
            for p in self.ice_patches:
                p.age_by(dt)
            self.ice_patches[:] = [p for p in self.ice_patches if p.time_left > 0.0]

    # -- per-frame update -----------------------------------------------------------

    def update(
        self, dt: float, mouse_pos: Point, *, boost_held: bool = False
    ) -> List[str]:
        """Advance one frame and return the semantic events that happened in it.

        Only the PLAYING state moves the world; other states keep animating
        (``self.time``, flames and ice always advance) and yield no events.  The
        returned list may contain :data:`EVENT_APPLE_EATEN`,
        :data:`EVENT_FLAME_ON` or :data:`EVENT_ICE_ENTERED` — each at most once
        per occurrence, so the main loop can map them to one-shot sound effects.

        `boost_held` reports whether the player is holding LEFT click right now
        (nitro); it only matters while PLAYING.
        """
        self.time += dt
        if self.state is not GameState.PLAYING:
            self._update_fx(dt)
            return []

        snake = self.snake
        events: List[str] = []

        ice_factor = self.ice_speed_factor_at(snake.pos)
        on_ice = ice_factor < 1.0
        if on_ice and not self._on_ice:
            events.append(EVENT_ICE_ENTERED)   # entering a patch (once per entry)
        self._on_ice = on_ice

        snake.update(dt, mouse_pos, boost_active=boost_held, ice_speed_factor=ice_factor)

        if self.apple.is_eaten(snake):
            self.score += 1
            snake.grow_by(self.config.grow_per_apple_px)
            self.apple = spawn_apple(self.config, self.rng, snake)
            events.append(EVENT_APPLE_EATEN)

        if snake.has_self_collision():
            self.state = GameState.GAME_OVER

        emitting = self._spawn_flames(snake, dt)
        if emitting and not self._flame_emitting:
            events.append(EVENT_FLAME_ON)      # the frame flames first kick in
        self._flame_emitting = emitting

        self._update_fx(dt)
        return events

"""Central configuration for Mouse Snake.

Every tunable value of the game lives here so that gameplay feel can be tuned
without touching logic or rendering code. The dataclass is frozen: build one
instance (or a modified copy via :meth:`with_changes`) and share it with all
modules.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Tuple

Color = Tuple[int, int, int]


@dataclass(frozen=True)
class GameConfig:
    # -- window & loop ------------------------------------------------------
    width: int = 900
    height: int = 640
    fps: int = 60
    title: str = "Mouse Snake"

    # -- head kinematics (how the head chases the cursor) --------------------
    # The head runs at `head_speed` while far from the cursor and slows to a
    # stop as it reaches it: desired speed = min(head_speed,
    # cursor_chase_gain * distance_to_cursor).  A limited turn rate means the
    # snake bends in smooth arcs (minimum turning radius ~ head_speed/turn_rate)
    # instead of snapping its direction.
    head_speed: float = 260.0        # px/s, top forward speed
    turn_rate: float = 5.0          # rad/s, max heading change per second
    cursor_chase_gain: float = 4.0  # desired speed (px/s) per px of distance to the cursor
    speed_ease: float = 600.0       # px/s^2, how fast actual speed approaches the desired one

    # -- trail & body geometry -----------------------------------------------
    # The head's path is recorded in a TrailBuffer at least `trail_min_step`
    # apart; body samples are then taken from that history every
    # `segment_spacing` of arc length.  Body radius tapers head -> tail.
    trail_min_step: float = 3.0     # px, minimum distance between recorded path points
    segment_spacing: float = 7.0    # px (arc length) between body samples
    head_radius: float = 12.0       # px
    tail_radius: float = 5.0        # px

    initial_length_px: float = 140.0  # starting body length, in arc-length px

    # -- growth (continuous, not blocky) --------------------------------------
    # Eating an apple adds to the *target* length; the real body then extends
    # toward it at most `max_growth_rate_px_s`, so new length slides smoothly
    # out of the (possibly curved) tail instead of popping in as one block.
    grow_per_apple_px: float = 60.0
    max_growth_rate_px_s: float = 90.0
    max_length_px: float = 2600.0

    # -- self collision --------------------------------------------------------
    # The head kills the game when it comes within `collision_factor *
    # (head_radius + sample_radius)` of a body sample, ignoring the
    # `collision_skip_samples` samples closest to the head (the ones that are
    # always "near" just because they are adjacent).
    self_collision_enabled: bool = True
    collision_skip_samples: int = 5
    collision_factor: float = 0.8

    # -- nitro boost (hold LEFT mouse) ------------------------------------------
    # While boosting, the top speed and speed cap are multiplied by this factor,
    # so the snake sprints faster; red flame particles trail off the tail tip.
    # The actual multiplier eases in/out at `nitro_ramp_rate` per second (see
    # Snake.boost_factor), so entering/leaving nitro is a smooth ramp, not a jump.
    nitro_speed_multiplier: float = 1.5   # 1.5x top speed while boosting
    nitro_ramp_rate: float = 6.0          # per second; ~0.3 s to reach full boost
    flame_spawn_per_second: int = 90      # particles emitted per second at full boost
    flame_lifetime_min_s: float = 0.22    # a particle's life (seconds), randomized within this...
    flame_lifetime_max_s: float = 0.45    # ...and this range; releasing the button lets them die out
    flame_size_max: float = 7.0          # px, starting radius of a fresh particle (jittered +/-)
    flame_speed_away: float = 35.0       # px/s backward drift relative to the tail's travel direction
    flame_spread: float = 26.0           # px/s lateral jitter of emitted particles
    flame_max_count: int = 80            # hard cap on live flame particles

    # -- ice patches (RIGHT click drops one in front of the head) ----------------
    # A right click freezes a disc `ice_spawn_ahead_px` ahead of the head along
    # its heading. While the head is inside any active patch, top speed is
    # multiplied by `ice_speed_factor` (< 1 slows you down). Patches melt after
    # their lifetime; at most `ice_max_patches` live at once (oldest melts first).
    ice_patch_radius: float = 46.0       # px, radius of a patch
    ice_lifetime_s: float = 6.0          # seconds before a patch melts away
    ice_speed_factor: float = 0.35       # top-speed multiplier while the head is on ice
    ice_spawn_ahead_px: float = 80.0     # distance in front of the head where new patches center
    ice_max_patches: int = 6             # oldest patch melts early beyond this cap

    # -- apple ------------------------------------------------------------------
    apple_radius: float = 10.0
    apple_spawn_margin: int = 50      # spawns stay this far inside the window edges
    min_apple_dist_from_head_px: float = 140.0

    # -- colors (R, G, B) ----------------------------------------------------------
    bg_color_a: Color = (22, 25, 31)
    bg_color_b: Color = (27, 30, 37)
    border_color: Color = (46, 53, 68)
    snake_head_color: Color = (96, 224, 138)
    snake_tail_color: Color = (24, 92, 60)
    snake_stripe_boost: int = 14     # brightness bump of alternating body segments
    snake_outline_color: Color = (12, 32, 22)
    apple_color: Color = (235, 71, 84)
    apple_highlight: Color = (255, 146, 156)
    leaf_color: Color = (98, 205, 92)
    stem_color: Color = (122, 84, 54)
    text_color: Color = (235, 238, 243)
    dim_text_color: Color = (150, 158, 170)

    # -- effect colors -------------------------------------------------------------
    flame_core_color: Color = (255, 236, 150)   # hottest inner part of a flame particle
    flame_mid_color: Color = (255, 128, 42)     # orange body of the flame
    flame_tip_color: Color = (209, 42, 42)      # deep red outer edge ("red flames")
    ice_patch_color: Color = (160, 214, 255)    # fill of a frozen patch
    ice_ring_color: Color = (224, 244, 255)     # bright rim + sparkles of a patch

    def __post_init__(self) -> None:
        if self.width < 2 * self.apple_spawn_margin + 2 or self.height < 2 * self.apple_spawn_margin + 2:
            raise ValueError("window too small for the apple spawn margin")
        if self.segment_spacing <= 0 or self.trail_min_step <= 0:
            raise ValueError("segment_spacing and trail_min_step must be positive")
        if not (0 < self.tail_radius <= self.head_radius):
            raise ValueError("require tail_radius <= head_radius, both > 0")
        if self.nitro_speed_multiplier < 1.0:
            raise ValueError("nitro must speed the snake up (multiplier >= 1)")
        if not (0.0 < self.ice_speed_factor < 1.0):
            raise ValueError("ice_speed_factor must be in (0, 1) to slow the snake down")
        if not (self.flame_lifetime_min_s <= self.flame_lifetime_max_s and self.flame_lifetime_max_s > 0):
            raise ValueError("require 0 < flame_lifetime_min_s <= flame_lifetime_max_s")
        if self.ice_patch_radius <= 0 or self.ice_spawn_ahead_px < 0:
            raise ValueError("ice patch radius must be positive, spawn distance non-negative")

    def with_changes(self, **overrides) -> "GameConfig":
        """Return a copy of this config with the given fields overridden."""
        return replace(self, **overrides)

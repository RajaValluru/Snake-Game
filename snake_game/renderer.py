"""All pygame drawing for Mouse Snake (the only module that imports pygame).

Presentation only: the renderer takes a :class:`Game` snapshot and paints it;
it never changes game state.  The snake is rendered as a tapered "tube" of
overlapping circles sampled from the body, which stays smooth through tight
curves without any polygon math.
"""

from __future__ import annotations

import math
from typing import List, Tuple

import pygame

from .config import GameConfig
from .game import Game, GameState
from .snake import Snake


def _lerp_color(c1: Tuple[int, int, int], c2: Tuple[int, int, int], t: float) -> Tuple[int, int, int]:
    """Interpolate two RGB colors by fraction `t`."""
    return tuple(max(0, min(255, int(a + (b - a) * t))) for a, b in zip(c1, c2))  # type: ignore[return-value]


class Renderer:
    def __init__(self, config: GameConfig) -> None:
        self.cfg = config
        pygame.font.init()
        self.font_big = pygame.font.Font(None, 84)
        self.font_mid = pygame.font.Font(None, 36)
        self.font_small = pygame.font.Font(None, 24)
        self._background = self._make_background()
        # Reused per-pixel-alpha canvas for translucent effects (ice patches,
        # flame particles, head rings).  Cleared + blitted once per layer.
        self._fx_overlay = pygame.Surface((config.width, config.height), pygame.SRCALPHA)

    # -- background (pre-rendered once; it never changes) ------------------------

    def _make_background(self) -> pygame.Surface:
        cfg = self.cfg
        tile = 32
        bg = pygame.Surface((cfg.width, cfg.height))
        for gy in range(0, cfg.height, tile):
            for gx in range(0, cfg.width, tile):
                color = (
                    cfg.bg_color_a if ((gx // tile) + (gy // tile)) % 2 == 0 else cfg.bg_color_b
                )
                pygame.draw.rect(
                    bg, color, (gx, gy, min(tile, cfg.width - gx), min(tile, cfg.height - gy))
                )
        pygame.draw.rect(bg, cfg.border_color, (0, 0, cfg.width, cfg.height), width=3)
        return bg

    # -- frame ------------------------------------------------------------------

    def draw(self, screen: pygame.Surface, game: Game) -> None:
        """Paint one full frame for the current game state."""
        cfg = self.cfg
        screen.blit(self._background, (0, 0))
        self._paint_ice_patches(screen, game)   # ground layer: under apple + snake
        self._draw_apple(screen, game.apple, game.time)
        self._draw_snake(screen, game.snake)
        self._paint_flames_and_head_fx(screen, game)  # over the body: flames + rings

        if game.state is not GameState.MENU:
            self._draw_hud(screen, game)
        if game.state is GameState.MENU:
            self._draw_overlay(
                screen,
                "MOUSE SNAKE",
                [
                    "Steer the snake with your mouse.",
                    "Eat apples to grow. Don't bite yourself.",
                    "Hold LEFT click: NITRO flames (1.5x speed).",
                    "RIGHT click drops ice ahead - slide on it to slow down.",
                ],
                "Click or press SPACE to start",
            )
        elif game.state is GameState.GAME_OVER:
            self._draw_overlay(
                screen,
                "GAME OVER",
                [f"Apples eaten: {game.score}", f"Length: {game.snake.segment_count} segments"],
                "Click or press R to play again",
            )

    # -- pieces --------------------------------------------------------------------

    def _text(self, font: pygame.font.Font, text: str, color: Tuple[int, int, int]) -> pygame.Surface:
        return font.render(text, True, color)

    def _draw_hud(self, screen: pygame.Surface, game) -> None:
        cfg = self.cfg
        score_s = self._text(self.font_small, f"Apples: {game.score}", cfg.text_color)
        length_s = self._text(
            self.font_small, f"Length: {game.snake.segment_count}", cfg.dim_text_color
        )
        screen.blit(score_s, (16, 12))
        screen.blit(length_s, (16 + score_s.get_width() + 24, 12))
        if game.state is GameState.PLAYING and game.snake.boost_level > 0.25:
            nitro_s = self._text(
                self.font_small, "NITRO", cfg.flame_mid_color
            )
            screen.blit(nitro_s, (16, 40))
        hint = self._text(
            self.font_small,
            "steer with mouse - hold LEFT click: nitro flames - RIGHT click: ice patch",
            cfg.dim_text_color,
        )
        screen.blit(hint, (16, cfg.height - hint.get_height() - 12))

    def _draw_snake(self, screen: pygame.Surface, snake: Snake) -> None:
        samples = snake.body_samples_with_radii()
        if not samples:
            return
        n = len(samples)
        cfg = self.cfg
        # Paint tail -> head so the head always ends up on top.
        order = list(reversed(range(n)))

        for i in order:  # pass 1: dark outline (slightly larger than the body)
            p, r = samples[i]
            pygame.draw.circle(screen, cfg.snake_outline_color, (int(p[0]), int(p[1])), max(2, int(r) + 2))

        for i in order:  # pass 2: tapered gradient fill with subtle stripes
            t = i / max(n - 1, 1)  # 0 at head -> 1 at tail
            color = _lerp_color(cfg.snake_head_color, cfg.snake_tail_color, t)
            if i % 2 == 1:
                color = tuple(min(255, c + cfg.snake_stripe_boost) for c in color)
            p, r = samples[i]
            pygame.draw.circle(screen, color, (int(p[0]), int(p[1])), max(1, int(r)))

        self._draw_head_details(screen, snake)

    def _draw_head_details(self, screen: pygame.Surface, snake: Snake) -> None:
        """Direction-aware eyes on the head."""
        cfg = self.cfg
        x, y = int(snake.pos[0]), int(snake.pos[1])
        r = cfg.head_radius
        fx, fy = math.cos(snake.heading), math.sin(snake.heading)  # forward unit vector
        sx, sy = -fy, fx                                          # side unit vector
        for sgn in (-1.0, 1.0):
            ex = x + fx * r * 0.45 + sx * sgn * r * 0.55
            ey = y + fy * r * 0.45 + sy * sgn * r * 0.55
            pygame.draw.circle(screen, (250, 252, 255), (int(ex), int(ey)), max(2, int(r * 0.34)))
            pygame.draw.circle(
                screen, (16, 20, 26), (int(ex + fx * 1.8), int(ey + fy * 1.8)), max(1, int(r * 0.17))
            )

    # -- effect layers (translucent, painted through the shared overlay) ----------

    def _paint_ice_patches(self, screen: pygame.Surface, game: Game) -> None:
        """Frost discs on the ground layer: fill, brighter inner zone, rim and
        twinkling speckles.  Alpha follows each patch's fade-in/melt-out."""
        cfg = self.cfg
        visible = [p for p in game.ice_patches if p.alpha_scale() > 0.01]
        if not visible:
            return
        ov = self._fx_overlay
        ov.fill((0, 0, 0, 0))
        t = game.time
        for p in visible:
            a = p.alpha_scale()
            x, y, r = int(p.x), int(p.y), max(2, int(p.radius))
            pygame.draw.circle(ov, (*cfg.ice_patch_color, int(84 * a)), (x, y), r)
            pygame.draw.circle(
                ov, (*cfg.ice_ring_color, int(36 * a)), (x, y), max(2, int(r * 0.6))
            )
            pygame.draw.circle(ov, (*cfg.ice_ring_color, int(135 * a)), (x, y), r, width=2)
            for dx, dy, rf, ph in p.speckles:
                tw = 0.5 + 0.5 * math.sin(t * 2.6 + ph)
                pygame.draw.circle(
                    ov,
                    (*cfg.ice_ring_color, int((85 + 105 * tw) * a)),
                    (int(x + dx * p.radius), int(y + dy * p.radius)),
                    max(1, int(r * rf)),
                )
        screen.blit(ov, (0, 0))

    def _paint_flames_and_head_fx(self, screen: pygame.Surface, game: Game) -> None:
        """Nitro flames at the tail tip plus head rings: a warm heat ring while
        boosting and a frost ring while the head is sliding on ice."""
        cfg = self.cfg
        snake = game.snake
        playing = game.state is GameState.PLAYING
        has_heat_ring = playing and snake.boost_level > 0.25
        on_ice = playing and game.ice_speed_factor_at(snake.pos) < 1.0
        if not game.flames and not has_heat_ring and not on_ice:
            return
        ov = self._fx_overlay
        ov.fill((0, 0, 0, 0))
        t = game.time

        if has_heat_ring or on_ice:
            x, y = int(snake.pos[0]), int(snake.pos[1])
            ring_r = max(4, int(cfg.head_radius + 5))
            if has_heat_ring:
                a = int(75 * snake.boost_level)
                pygame.draw.circle(ov, (*cfg.flame_tip_color, a), (x, y), ring_r + 3, width=2)
                pygame.draw.circle(ov, (*cfg.flame_mid_color, max(0, a - 35)), (x, y), ring_r)
            if on_ice:
                pygame.draw.circle(ov, (*cfg.ice_ring_color, 96), (x, y), ring_r + 2, width=2)
                for i in range(3):  # little orbiting sparkles
                    a = t * 2.0 + i * math.tau / 3.0
                    pygame.draw.circle(
                        ov,
                        (*cfg.ice_ring_color, 150),
                        (int(x + math.cos(a) * (ring_r + 6)), int(y + math.sin(a) * (ring_r + 6))),
                        2,
                    )

        # Flame particles: oldest first so the newest (brightest) sit on top.
        for f in sorted(game.flames, key=lambda p: -p.age_fraction):
            u = f.age_fraction  # 0 at birth -> 1 just before death
            grow_in = min(1.0, (f.max_life - f.life) / 0.07 + 0.35)  # pop in over ~70 ms
            flicker = 0.82 + 0.28 * math.sin(f.phase + t * 26.0 + u * 9.0)
            r_out = int(f.size * grow_in * (1.0 - u) ** 0.75 * flicker)
            if r_out < 1:
                continue
            fade = max(0.0, min(1.0, 1.0 - u))
            x, y = int(f.x), int(f.y)
            pygame.draw.circle(ov, (*cfg.flame_tip_color, int(60 * fade)), (x, y), r_out + 4)  # soft bloom
            pygame.draw.circle(
                ov, (*cfg.flame_tip_color, int(175 * grow_in * max(fade, 0.15))), (x, y), r_out
            )
            r2 = max(1, int(r_out * 0.66))
            pygame.draw.circle(
                ov, (*cfg.flame_mid_color, int(235 * grow_in * max(fade, 0.15))), (x, y), r2
            )
            # Fully opaque white-hot core: stays readable even over the bright body.
            r3 = max(1, int(r_out * 0.38))
            pygame.draw.circle(
                ov, (*cfg.flame_core_color, int(255 * grow_in * max(fade, 0.1))), (x, y), r3
            )
        screen.blit(ov, (0, 0))

    def _draw_apple(self, screen: pygame.Surface, apple, t: float) -> None:
        cfg = self.cfg
        pulse = 1.0 + 0.06 * math.sin(t * 3.5)
        r = max(4, int(apple.radius * pulse))
        x, y = int(apple.x), int(apple.y)

        pygame.draw.circle(screen, cfg.apple_color, (x, y), r)
        pygame.draw.circle(screen, cfg.apple_highlight, (x - r // 3, y - r // 3), max(2, r // 4))
        # stem + leaf
        pygame.draw.line(screen, cfg.stem_color, (x + r // 5, y - r + 1), (x + r // 4, y - r - 6), 2)
        leaf = pygame.Rect(0, 0, max(4, int(r * 0.9)), max(3, int(r * 0.45))).move((x + r // 8, y - r - 12))
        pygame.draw.ellipse(screen, cfg.leaf_color, leaf)

    def _draw_overlay(
        self, screen: pygame.Surface, title: str, lines: List[str], footer: str
    ) -> None:
        """Dim the scene and center a title / info lines / action hint."""
        cfg = self.cfg
        veil = pygame.Surface((cfg.width, cfg.height), pygame.SRCALPHA)
        veil.fill((10, 12, 16, 178))
        screen.blit(veil, (0, 0))

        def center(surface: pygame.Surface, y_pos: int) -> None:
            screen.blit(surface, ((cfg.width - surface.get_width()) // 2, y_pos))

        y = cfg.height // 4
        title_s = self._text(self.font_big, title, cfg.text_color)
        center(title_s, y)
        y += title_s.get_height() + 18
        for line in lines:
            s = self._text(self.font_small, line, cfg.dim_text_color)
            center(s, y)
            y += s.get_height() + 6
        footer_s = self._text(self.font_mid, footer, cfg.snake_head_color)
        center(footer_s, int(cfg.height * 0.72))

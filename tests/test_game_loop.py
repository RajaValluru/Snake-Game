"""Smoke test: drive the real Game + Renderer through every state using
pygame's dummy video driver, so no display is needed."""

import math
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from snake_game.apple import Apple  # noqa: E402
from snake_game.config import GameConfig  # noqa: E402
from snake_game.game import GameState, Game  # noqa: E402
from snake_game.renderer import Renderer  # noqa: E402


def _make_harness():
    cfg = GameConfig()
    pygame.init()
    screen = pygame.display.set_mode((cfg.width, cfg.height))
    game = Game(cfg, seed=1)
    renderer = Renderer(cfg)
    return screen, game, renderer


def test_full_loop_all_states():
    screen, game, renderer = _make_harness()
    try:
        dt = 1.0 / 60.0

        def orbit(t):
            cfg = game.config
            return (
                cfg.width / 2 + 80 * math.cos(1.5 * t),
                cfg.height / 2 + 80 * math.sin(1.5 * t),
            )

        # -- MENU renders for a few frames -----------------------------------
        t = 0.0
        for _ in range(30):
            game.update(dt, (450.0, 320.0))
            renderer.draw(screen, game)
            t += dt
        assert game.state is GameState.MENU

        # -- start playing ------------------------------------------------------
        game.handle_click()
        assert game.state is GameState.PLAYING

        # PLAYING: orbit the cursor; drop an apple in front of the head a few times.
        for i in range(900):
            if i % 90 == 45 and game.score < 3:
                fx = math.cos(game.snake.heading)
                fy = math.sin(game.snake.heading)
                game.apple = Apple(
                    (game.snake.pos[0] + fx * 40.0, game.snake.pos[1] + fy * 40.0),
                    game.config.apple_radius,
                )
            game.update(dt, orbit(t))
            renderer.draw(screen, game)
            t += dt
        assert game.score >= 3
        assert game.state is GameState.PLAYING

        # -- force a self-collision by coiling the trail into a small loop -----
        cfg = game.config
        snake = game.snake
        cx, cy, r, arc_len = 460.0, 320.0, 15.0, 92.0
        n_pts = int(arc_len / cfg.trail_min_step) + 1
        span = arc_len / r
        pts, cums, prev = [], [0.0], None
        for i in range(n_pts):
            a = -span * (i / (n_pts - 1))
            p = (cx + r * math.cos(a), cy + r * math.sin(a))
            if prev is not None:
                cums.append(cums[-1] + math.hypot(p[0] - prev[0], p[1] - prev[1]))
            pts.append(p)
            prev = p
        snake.trail.points, snake.trail.cum = pts, cums
        snake.pos = (cx + r, cy)
        snake.length_px = snake.target_length_px = arc_len

        game.update(dt, orbit(t))
        renderer.draw(screen, game)
        t += dt
        assert game.state is GameState.GAME_OVER

        # -- GAME OVER renders; R restarts cleanly ------------------------------
        for _ in range(30):
            game.update(dt, (450.0, 320.0))
            renderer.draw(screen, game)
        assert game.score >= 1
        game.handle_key("r")
        assert game.state is GameState.PLAYING
        assert game.score == 0
    finally:
        pygame.quit()

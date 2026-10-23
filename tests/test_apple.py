"""Headless unit tests for apple spawning and eating."""

from random import Random

from snake_game.apple import Apple, spawn_apple
from snake_game.config import GameConfig
from snake_game.geom import dist
from snake_game.snake import Snake

CFG = GameConfig()


def make_snake(cfg: GameConfig = CFG) -> Snake:
    return Snake(cfg, (cfg.width / 2.0, cfg.height / 2.0), 0.0)


def test_spawn_respects_margin_and_head_distance():
    for seed in (1, 7, 42):
        snake = make_snake()
        apple = spawn_apple(CFG, Random(seed), snake)
        m = CFG.apple_spawn_margin
        assert m <= apple.x <= CFG.width - m
        assert m <= apple.y <= CFG.height - m
        assert dist(apple.x, apple.y, *snake.pos) >= CFG.min_apple_dist_from_head_px


def test_spawn_avoids_sitting_on_the_body():
    snake = make_snake()
    for _ in range(120):  # drive a straight line toward the right side of the window
        snake.update(1.0 / 60.0, (CFG.width - 60.0, CFG.height / 2.0))
    samples = snake.body_samples_with_radii()

    apple = spawn_apple(CFG, Random(3), snake)
    for i in range(2, len(samples), 3):  # exactly the check used by spawn_apple
        p, r = samples[i]
        assert dist(apple.x, apple.y, p[0], p[1]) >= CFG.apple_radius + r + 8.0 - 1e-9


def test_is_eaten_threshold():
    snake = make_snake()
    reach = CFG.apple_radius + 0.7 * CFG.head_radius
    far = Apple((snake.pos[0] + 60.0, snake.pos[1]), CFG.apple_radius)
    near = Apple((snake.pos[0] + reach / 2.0, snake.pos[1]), CFG.apple_radius)
    assert not far.is_eaten(snake)
    assert near.is_eaten(snake)


def test_spawn_is_deterministic_with_seed():
    a = spawn_apple(CFG, Random(9), make_snake())
    b = spawn_apple(CFG, Random(9), make_snake())
    assert (a.x, a.y) == (b.x, b.y)


def test_spawn_fallback_never_fails():
    # Tiny window: the 20x20 spawn box is always too close to the head, so every
    # candidate fails and the fallback path must still return a valid apple.
    cfg = CFG.with_changes(width=120, height=120)
    snake = Snake(cfg, (60.0, 60.0), 0.0)
    apple = spawn_apple(cfg, Random(0), snake, tries=3)
    assert cfg.apple_spawn_margin <= apple.x <= cfg.width - cfg.apple_spawn_margin
    assert cfg.apple_spawn_margin <= apple.y <= cfg.height - cfg.apple_spawn_margin

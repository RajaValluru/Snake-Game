"""Headless unit tests for Snake kinematics, growth and self-collision."""

import math

from snake_game.config import GameConfig
from snake_game.geom import dist
from snake_game.snake import Snake

CFG = GameConfig()


def make_snake(cfg: GameConfig = CFG) -> Snake:
    """Fresh snake at the center of a 900x640 window, facing left."""
    return Snake(cfg, (450.0, 320.0), math.pi)


def simulate(snake: Snake, seconds: float, target_fn, dt: float = 1.0 / 60.0) -> None:
    t = 0.0
    while t < seconds - 1e-9:
        snake.update(dt, target_fn(t))
        t += dt


def test_initial_body_exists_and_has_expected_count():
    snake = make_snake()
    assert snake.segment_count == int(CFG.initial_length_px // CFG.segment_spacing)
    samples = snake.body_samples_with_radii()
    # Every sample is already placed on the seeded straight history.
    for i, (p, _r) in enumerate(samples[1:], start=1):
        # The snake faces left (heading pi), so its body trails behind it on the +x side.
        expected_x = 450.0 + i * CFG.segment_spacing
        assert abs(p[0] - expected_x) < CFG.trail_min_step + 0.6


def test_head_moves_toward_target():
    snake = make_snake()
    simulate(snake, 2.5, lambda t: (880.0, 320.0))
    assert snake.pos[0] > 700.0  # turned around and drove to the right side
    assert abs(snake.pos[1] - 320.0) < 40.0


def test_speed_eases_to_zero_at_parked_cursor():
    snake = make_snake()
    simulate(snake, 1.5, lambda t: (860.0, 320.0))  # reach cruising speed
    assert snake.speed > CFG.head_speed * 0.9

    frozen = (snake.pos[0], snake.pos[1])
    simulate(snake, 4.0, lambda t: frozen)  # cursor parks -> the snake settles there
    assert snake.speed < 6.0
    assert dist(*snake.pos, *frozen) < 30.0


def test_heading_change_is_capped_by_turn_rate():
    dt = 1.0 / 120.0
    snake = make_snake()
    max_delta = 0.0
    for _ in range(60):
        before = snake.heading
        snake.update(dt, (450.0, 80.0))  # target straight up -> wants a big turn
        max_delta = max(max_delta, abs(snake.heading - before))
    assert max_delta <= CFG.turn_rate * dt + 1e-9


def test_growth_is_continuous_not_blocky():
    snake = make_snake()
    start_len = snake.length_px
    apples = 3
    for _ in range(apples):
        snake.grow_by(CFG.grow_per_apple_px)
    target = min(start_len + apples * CFG.grow_per_apple_px, CFG.max_length_px)

    dt = 1.0 / 60.0
    prev_len = snake.length_px
    max_step = 0.0
    counts = set()
    for _ in range(int(8.0 / dt)):  # 8 seconds: plenty of time to fully grow
        snake.update(dt, (900.0, 320.0))
        max_step = max(max_step, snake.length_px - prev_len)
        prev_len = snake.length_px
        counts.add(snake.segment_count)

    # Never jumps by more than one frame's worth of growth...
    assert max_step <= CFG.max_growth_rate_px_s * dt + 1e-9
    # ...and passes through many intermediate lengths (not a single block).
    assert len(counts) >= 5
    assert abs(snake.length_px - target) < 1e-6


def test_body_samples_follow_the_head_path():
    snake = make_snake()

    def orbit_target(t: float):
        return (450.0 + 120.0 * math.cos(1.6 * t), 320.0 + 120.0 * math.sin(1.6 * t))

    simulate(snake, 5.0, orbit_target)  # orbit a while so the body is in steady curve
    samples = snake.body_samples_with_radii()
    # head plus the full starting body (140 px / 7 px spacing == 20 samples)
    assert len(samples) == int(CFG.initial_length_px // CFG.segment_spacing) + 1

    pts = [p for p, _r in samples]
    gaps = [dist(*pts[i], *pts[i + 1]) for i in range(1, len(pts) - 1)]
    for g in gaps:
        assert CFG.segment_spacing * 0.8 < g < CFG.segment_spacing * 1.2

    radii = [r_ for _p, r_ in samples]
    assert all(a >= b - 1e-9 for a, b in zip(radii, radii[1:]))  # tapers head -> tail


def _coil_trail(snake: Snake, cx: float = 460.0, cy: float = 320.0) -> None:
    """Overwrite the trail with a near-complete small circle ending at the head."""
    r, arc_len = 15.0, 92.0  # circumference ~94px: just short of one full loop
    n_pts = int(arc_len / CFG.trail_min_step) + 1
    span = arc_len / r
    pts, cums, prev = [], [0.0], None
    for i in range(n_pts):
        a = -span * (i / (n_pts - 1))
        p = (cx + r * math.cos(a), cy + r * math.sin(a))
        if prev is not None:
            cums.append(cums[-1] + dist(prev[0], prev[1], p[0], p[1]))
        pts.append(p)
        prev = p
    snake.trail.points, snake.trail.cum = pts, cums


def test_self_collision_when_head_loops_into_tail():
    snake = make_snake()
    _coil_trail(snake)
    snake.pos = (460.0 + 15.0, 320.0)  # head at the end of the coil (angle 0)
    snake.heading = math.pi / 2       # tangent direction
    snake.length_px = snake.target_length_px = 92.0
    assert snake.has_self_collision()


def test_no_self_collision_on_a_straight_body():
    snake = make_snake()
    simulate(snake, 2.0, lambda t: (890.0, 320.0))  # a U-turn at cruising speed
    assert not snake.has_self_collision()


def test_self_collision_can_be_disabled():
    cfg = CFG.with_changes(self_collision_enabled=False)
    snake = make_snake(cfg)
    _coil_trail(snake)
    snake.pos = (460.0 + 15.0, 320.0)
    snake.length_px = snake.target_length_px = 92.0
    assert not snake.has_self_collision()

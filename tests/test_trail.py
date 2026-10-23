"""Headless unit tests for TrailBuffer (no pygame required)."""

import math

from snake_game.geom import dist
from snake_game.trail import TrailBuffer


def test_seed_straight_back_and_sample():
    trail = TrailBuffer()
    # Head at (500, 300) moving right (+x); the body trails behind to the left.
    trail.seed_straight_back(500.0, 300.0, heading_rad=0.0, length=100.0, step=5.0)
    assert abs(trail.total_length - 100.0) < 1e-6

    x0, y0 = trail.sample(0.0)
    assert dist(x0, y0, 500.0, 300.0) < 1e-9
    x50, _y50 = trail.sample(50.0)
    assert abs(x50 - 450.0) < 0.6  # halfway back along the straight seed

    clamped = trail.sample(10_000.0)  # more than available -> oldest point
    assert dist(*clamped, 400.0, 300.0) < 0.6


def test_min_step_is_respected():
    trail = TrailBuffer()
    assert trail.add_point(0.0, 0.0)
    assert not trail.add_point(1.0, 0.0, min_step=3.0)  # too close -> skipped
    assert len(trail.points) == 1
    # Distance is measured against the last *recorded* point, so this appends.
    assert trail.add_point(4.0, 0.0, min_step=3.0)
    assert len(trail.points) == 2


def test_sample_follows_a_curved_path():
    # Walk a quarter circle of radius 50 around (100, 100), angle 0 -> -90 deg.
    trail = TrailBuffer()
    r, n_steps = 50.0, 48
    for i in range(n_steps + 1):
        a = (-math.pi / 2) * (i / n_steps)
        trail.add_point(100.0 + r * math.cos(a), 100.0 + r * math.sin(a), min_step=0.5)

    for d in (10.0, 30.0, 60.0):
        a = -math.pi / 2 + d / r  # walk back along the arc by distance d
        expected = (100.0 + r * math.cos(a), 100.0 + r * math.sin(a))
        got = trail.sample(d)
        assert dist(*got, *expected) < 2.5, f"sample at {d}px behind was off"


def test_trim_keeps_span_and_clamps():
    trail = TrailBuffer()
    trail.seed_straight_back(600.0, 300.0, 0.0, length=600.0, step=4.0)
    before_10 = trail.sample(10.0)

    trail.trim(max_keep_length=50.0)
    assert trail.total_length <= 50.0 + 1e-9
    after_10 = trail.sample(10.0)
    assert dist(*before_10, *after_10) < 0.7  # points near the head must not move

    clamped = trail.sample(1e6)  # now clamps to the *new* oldest point
    assert dist(*clamped, *trail.points[0]) < 1e-9


def test_empty_trail_raises_on_sample():
    import pytest

    with pytest.raises(ValueError):
        TrailBuffer().sample(1.0)

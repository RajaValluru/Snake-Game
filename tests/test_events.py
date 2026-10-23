"""Tests for the semantic events that ``Game.update`` returns each frame.

These are the hooks the main loop uses to play sound effects (apple eaten,
nitro flames igniting, head entering ice), so they must fire *exactly once*
per occurrence and stay out of non-PLAYING states.
"""

import math

from snake_game.config import GameConfig
from snake_game.fx import IcePatch
from snake_game.game import (
    EVENT_APPLE_EATEN,
    EVENT_FLAME_ON,
    EVENT_ICE_ENTERED,
    GameState,
    Game,
)
from snake_game.apple import Apple

CFG = GameConfig()
DT = 1.0 / 60.0

# A target far outside the window keeps `cursor_chase_gain` from capping speed:
# the head pins to the soft wall but its speed state eases to full cruise, so
# the flame-emission gate (speed >= 60) opens reliably.
_FAR_TARGET = (20_000.0, 320.0)


def play(game: Game) -> None:
    game.handle_click()
    assert game.state is GameState.PLAYING


def _collect(game: Game, frames: int, target, **kwargs):
    """Run `frames` updates and return every event emitted (in order)."""
    events = []
    for _ in range(frames):
        events.extend(game.update(DT, target, **kwargs))
    return events


# -- update() contract -----------------------------------------------------------

def test_update_returns_an_event_list_in_every_state():
    game = Game(CFG, seed=1)
    assert game.update(DT, (450.0, 320.0)) == []      # MENU: no events
    play(game)
    for _ in range(60):                               # nothing special happens
        evts = game.update(DT, (450.0, 320.0))
        assert isinstance(evts, list)
        assert evts == []                             # parked cursor: no events


# -- apple eaten -----------------------------------------------------------------

def test_apple_eaten_event_fires_once_per_apple():
    game = Game(CFG, seed=1)
    play(game)

    t = 0.0
    seen = []
    for i in range(1500):
        # Every 90 frames, drop an apple right in front of the head (the snake
        # orbits a small circle around the window center and runs over it).
        if i % 90 == 45:
            fx = math.cos(game.snake.heading)
            fy = math.sin(game.snake.heading)
            game.apple = Apple(
                (game.snake.pos[0] + fx * 40.0, game.snake.pos[1] + fy * 40.0),
                CFG.apple_radius,
            )
        seen.extend(game.update(DT, _orbit(t)))
        t += DT

    assert game.score >= 3
    # One event per apple eaten -- exactly in sync with the score counter.
    assert seen.count(EVENT_APPLE_EATEN) == game.score


def _orbit(t):
    return (450.0 + 80 * math.cos(1.5 * t), 320.0 + 80 * math.sin(1.5 * t))


# -- flame ignition ----------------------------------------------------------------

def test_flame_on_fires_exactly_once_per_boost_session():
    game = Game(CFG, seed=1)
    play(game)

    # Hold nitro: the emission gate (boost_level >= 0.15 and speed >= 60) opens
    # after a fraction of a second -> exactly one EVENT_FLAME_ON per session.
    events = _collect(game, int(3.0 / DT), _FAR_TARGET, boost_held=True)
    assert events.count(EVENT_FLAME_ON) == 1

    # Release and let the gate close, then boost again -> exactly one more.
    events = _collect(game, int(2.0 / DT), _FAR_TARGET)
    assert events == []                               # no spurious re-trigger while off
    events = _collect(game, int(3.0 / DT), _FAR_TARGET, boost_held=True)
    assert events.count(EVENT_FLAME_ON) == 1


def test_flame_on_waits_for_the_ramp_to_reach_the_gate():
    game = Game(CFG, seed=1)
    play(game)
    # Speed eases up at speed_ease (60 px/s after frame 6) and boost_level needs
    # a couple of ramp frames: the gate cannot be open on the very first frames.
    for _ in range(4):
        assert game.update(DT, _FAR_TARGET, boost_held=True) == []
    fired = None
    for frame in range(5, 30):                        # gate must open within ~0.5 s
        if EVENT_FLAME_ON in game.update(DT, _FAR_TARGET, boost_held=True):
            fired = frame
            break
    assert fired is not None


def test_restart_resets_flame_on_tracking():
    game = Game(CFG, seed=1)
    play(game)
    assert _collect(game, int(2.0 / DT), _FAR_TARGET, boost_held=True).count(EVENT_FLAME_ON) == 1

    game.handle_key("r")                              # restart mid-boost session
    assert game._flame_emitting is False              # tracking flag was reset
    assert _collect(game, int(2.0 / DT), _FAR_TARGET, boost_held=True).count(EVENT_FLAME_ON) == 1


# -- ice entry -----------------------------------------------------------------------

def test_ice_entered_fires_on_entry_and_not_while_staying():
    game = Game(CFG, seed=1)
    play(game)

    assert _collect(game, int(1.0 / DT), _FAR_TARGET) == []      # no patches yet
    # A giant patch covers the whole field: from now on the head is always inside it.
    game.ice_patches.append(IcePatch(450.0, 320.0, 800.0, CFG.ice_lifetime_s))

    events = _collect(game, int(1.0 / DT), _FAR_TARGET)
    assert events.count(EVENT_ICE_ENTERED) == 1          # fired exactly once, on entry

    # Leave all ice (patches cleared): the "on ice" flag resets silently...
    game.ice_patches.clear()
    assert _collect(game, int(0.5 / DT), _FAR_TARGET) == []
    # ...and a *new* entry fires again.
    game.ice_patches.append(IcePatch(450.0, 320.0, 800.0, CFG.ice_lifetime_s))
    events = _collect(game, int(1.0 / DT), _FAR_TARGET)
    assert events.count(EVENT_ICE_ENTERED) == 1


def test_restart_resets_ice_tracking():
    game = Game(CFG, seed=1)
    play(game)
    game.ice_patches.append(IcePatch(450.0, 320.0, 800.0, CFG.ice_lifetime_s))
    assert _collect(game, int(1.0 / DT), _FAR_TARGET).count(EVENT_ICE_ENTERED) == 1

    game.handle_key("r")                              # restart clears the patches too
    assert game._on_ice is False                      # and the tracking flag with them
    assert game.ice_patches == []


def test_no_sound_events_outside_playing():
    game = Game(CFG, seed=1)                          # MENU
    game.update(DT, (450.0, 320.0))
    play(game)
    _collect(game, int(1.0 / DT), _FAR_TARGET, boost_held=True)   # flames + score may happen
    # Force GAME OVER by coiling the trail into a tiny loop (same trick as test_game_loop).
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

    evts = game.update(DT, _FAR_TARGET)               # the frame that kills the run
    assert game.state is GameState.GAME_OVER
    for _ in range(30):                               # GAME OVER screen: silence
        assert game.update(DT, (450.0, 320.0)) == []

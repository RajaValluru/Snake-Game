"""Headless tests for the effect systems: nitro boost (flames) and ice patches."""

import math

from snake_game.config import GameConfig
from snake_game.fx import IcePatch
from snake_game.game import GameState, Game
from snake_game.geom import dist
from snake_game.snake import Snake

CFG = GameConfig()
DT = 1.0 / 60.0


def make_snake(cfg: GameConfig = CFG) -> Snake:
    return Snake(cfg, (450.0, 320.0), math.pi)  # center of a 900x640 window, facing left


def play(game: Game) -> None:
    game.handle_click()
    assert game.state is GameState.PLAYING


# -- nitro boost ------------------------------------------------------------

# A target far outside the window keeps `cursor_chase_gain` from capping speed:
# the head pins to the soft wall but its speed state still eases to full cruise.
_FAR_TARGET = (20000.0, 320.0)


def test_nitro_speeds_up_to_1_5x_head_speed():
    snake = make_snake()
    for _ in range(int(1.0 / DT)):  # warm up to normal cruise first
        snake.update(DT, _FAR_TARGET)
    assert abs(snake.speed - CFG.head_speed) < 40

    for _ in range(int(1.0 / DT)):  # hold nitro: speed eases toward the boosted cap
        snake.update(DT, _FAR_TARGET, boost_active=True)
    cap = CFG.head_speed * CFG.nitro_speed_multiplier
    assert snake.speed > cap - 30
    assert snake.speed <= cap + 1e-6


def test_nitro_fades_out_when_released():
    snake = make_snake()
    for _ in range(int(1.5 / DT)):
        snake.update(DT, _FAR_TARGET, boost_active=True)
    assert snake.boost_factor > CFG.nitro_speed_multiplier - 0.05
    assert snake.boost_level > 0.9

    for _ in range(int(1.0 / DT)):  # release the button: multiplier eases back to 1
        snake.update(DT, _FAR_TARGET)
    assert abs(snake.boost_factor - 1.0) < 0.02
    assert snake.boost_level < 2e-3


# -- ice patches --------------------------------------------------------------

def test_ice_patch_spawns_ahead_of_head():
    game = Game(CFG, seed=7)
    play(game)
    hx, hy = game.snake.pos
    game.add_ice_patch()
    assert len(game.ice_patches) == 1
    p = game.ice_patches[0]
    assert abs(dist(p.x, p.y, hx, hy) - CFG.ice_spawn_ahead_px) < 2.0
    assert p.x < hx  # the head faces left (heading pi), so "ahead" is to its left


def test_ice_speed_factor_inside_and_outside():
    game = Game(CFG, seed=7)
    play(game)
    game.add_ice_patch()
    p = game.ice_patches[0]
    assert game.ice_speed_factor_at((p.x, p.y)) == CFG.ice_speed_factor  # dead center
    far = (10.0, 630.0)  # nowhere near the patch (which sits left of center)
    assert dist(far[0], far[1], p.x, p.y) > p.radius
    assert game.ice_speed_factor_at(far) == 1.0


def test_snake_slows_while_on_ice():
    def peak_speed(with_ice: bool) -> float:
        game = Game(CFG, seed=3)
        play(game)
        if with_ice:
            # one giant patch covering the whole field (corners are ~554 px from center)
            game.ice_patches.append(IcePatch(450.0, 320.0, 800.0, CFG.ice_lifetime_s))
        peak = 0.0
        for _ in range(int(1.2 / DT)):
            game.update(DT, (890.0, 320.0))
            if game.state is GameState.PLAYING:
                peak = max(peak, game.snake.speed)
        return peak

    normal = peak_speed(with_ice=False)
    icy = peak_speed(with_ice=True)
    assert normal > CFG.head_speed * 0.8          # sanity: full cruise reached
    floor = CFG.head_speed * CFG.ice_speed_factor
    assert icy < normal * 0.5                    # clearly slowed on ice
    assert icy >= floor - 30                     # ...but not below the ice-cruise floor


def test_ice_patches_melt_after_lifetime():
    game = Game(CFG, seed=1)
    play(game)
    game.add_ice_patch()
    assert len(game.ice_patches) == 1
    for _ in range(int((CFG.ice_lifetime_s + 0.5) / DT)):
        game.update(DT, (450.0, 320.0))          # park the cursor; world keeps aging fx
    assert game.ice_patches == []


def test_ice_patch_cap_drops_oldest():
    game = Game(CFG, seed=1)
    play(game)
    for _ in range(CFG.ice_max_patches + 2):
        game.add_ice_patch()
    assert len(game.ice_patches) == CFG.ice_max_patches


def test_add_ice_patch_is_noop_outside_playing():
    game = Game(CFG, seed=1)
    game.add_ice_patch()  # still on the MENU: ignored
    assert game.ice_patches == []


# -- nitro flames --------------------------------------------------------------

def test_flames_spawn_while_boosting_and_clear_after_release():
    game = Game(CFG, seed=1)
    play(game)
    for _ in range(int(1.5 / DT)):  # sprint right while holding LEFT click
        game.update(DT, (890.0, 320.0), boost_held=True)
    assert len(game.flames) > 10

    # Release: no new spawns; existing particles die out within their max lifetime.
    for _ in range(int((CFG.flame_lifetime_max_s + 0.5) / DT)):
        game.update(DT, (890.0, 320.0))
    assert game.flames == []


def test_no_flames_without_boost_or_motion():
    game = Game(CFG, seed=1)
    play(game)
    for _ in range(int(1.0 / DT)):
        game.update(DT, (450.0, 320.0))          # parked cursor: no boost, head stopped
    assert game.flames == []


def test_flame_particles_stay_near_the_tail():
    game = Game(CFG, seed=1)
    play(game)
    for _ in range(int(1.5 / DT)):
        game.update(DT, (890.0, 320.0), boost_held=True)
    assert game.flames
    tail = game.snake.tail_point()
    for f in game.flames:
        # particles drift at most a few dozen px past where they were emitted
        assert dist(f.x, f.y, tail[0], tail[1]) < 250.0


# -- restart semantics ----------------------------------------------------------

def test_restart_clears_effects():
    game = Game(CFG, seed=1)
    play(game)
    for _ in range(int(1.0 / DT)):
        game.update(DT, (890.0, 320.0), boost_held=True)
    assert game.flames
    game.add_ice_patch()
    assert game.ice_patches

    game.handle_key("r")  # restart mid-game
    assert game.state is GameState.PLAYING
    assert game.score == 0
    assert game.flames == []
    assert game.ice_patches == []


# -- rendering smoke test (dummy video driver, no display needed) ---------------

def test_renderer_paints_flames_and_ice_headless():
    import os

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    import pygame

    cfg = GameConfig()
    pygame.init()
    screen = pygame.display.set_mode((cfg.width, cfg.height))
    try:
        game = Game(cfg, seed=5)
        from snake_game.renderer import Renderer

        renderer = Renderer(cfg)
        play(game)

        # Orbit a moving cursor while boosting: the snake keeps sprinting, so
        # flame particles stay alive and the flame layer gets painted each frame.
        t = 0.0
        for _ in range(90):
            target = (450.0 + 260.0 * math.cos(1.2 * t), 320.0 + 260.0 * math.sin(1.2 * t))
            game.update(DT, target, boost_held=True)
            renderer.draw(screen, game)
            t += DT
        assert len(game.flames) > 10

        # Drop ice ahead of the head and keep orbiting without boost: the head
        # slides through the patch at reduced speed while it is painted.
        game.add_ice_patch()
        was_on_ice = False
        for _ in range(240):
            target = (450.0 + 260.0 * math.cos(1.2 * t), 320.0 + 260.0 * math.sin(1.2 * t))
            game.update(DT, target)
            renderer.draw(screen, game)
            if game.ice_speed_factor_at(game.snake.pos) < 1.0:
                was_on_ice = True
            t += DT
        assert was_on_ice  # the orbit crossed at least one patch while it lasted

        # Flames have died by now (boost released long ago); final frame still paints.
        assert len(game.flames) == 0
        renderer.draw(screen, game)
    finally:
        pygame.quit()

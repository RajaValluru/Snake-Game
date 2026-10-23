"""Mouse Snake - entry point.

Run with:  python main.py          (optionally: --seed N for reproducible apples)

All game rules live in the ``snake_game`` package; this file only wires
pygame (window, events, clock, mixer) to the :class:`Game` and
:class:`Renderer`: raw mouse buttons/keys are translated into the Game's semantic
calls (``handle_click``, ``add_ice_patch``, ``boost_held=...``), and the
semantic events that ``Game.update`` returns each frame are mapped onto the
procedurally generated sound effects from :mod:`snake_game.audio_fx`.
"""

from __future__ import annotations

import argparse
from typing import Optional

import pygame

from snake_game import audio_fx
from snake_game.config import GameConfig
from snake_game.game import (
    EVENT_APPLE_EATEN,
    EVENT_FLAME_ON,
    EVENT_ICE_ENTERED,
    Game,
)
from snake_game.renderer import Renderer

# Interesting pygame key codes -> semantic names understood by Game.handle_key.
_KEY_NAMES = {
    pygame.K_RETURN: "return",
    pygame.K_SPACE: "space",
    pygame.K_r: "r",
}


def _build_sounds() -> dict:
    """Create the one-shot SFX from generated PCM ({} when no audio device).

    Each effect is synthesized once at startup by :mod:`snake_game.audio_fx`
    (pure Python, deterministic) and handed to pygame as a raw mixer buffer --
    there are no audio files anywhere in the project or the exe.  If the mixer
    failed to initialize (headless/CI boxes, broken sound card), we simply run
    without sound rather than crash.
    """
    if pygame.mixer.get_init() is None:
        return {}
    builders = {
        EVENT_APPLE_EATEN: audio_fx.make_apple_eat_sound,
        EVENT_FLAME_ON: audio_fx.make_flame_ignite_sound,
        EVENT_ICE_ENTERED: audio_fx.make_ice_slide_sound,
    }
    sounds: dict = {}
    for name, build in builders.items():
        try:
            pcm = build()
            sounds[name] = pygame.mixer.Sound(buffer=pcm.samples)
        except (pygame.error, ValueError):
            continue  # mixer format mismatch or device hiccup -> skip that SFX
    return sounds


def _play(sounds: dict, name: str) -> None:
    snd = sounds.get(name)
    if snd is not None:
        try:
            snd.play()
        except pygame.error:
            pass  # audio device went away mid-session; keep the game running


def run(config: Optional[GameConfig] = None, seed: Optional[int] = None) -> int:
    config = config or GameConfig()

    # Pin the mixer format before pygame.init() so generated PCM (44.1 kHz,
    # 16-bit stereo) plays back at its intended pitch.
    try:
        pygame.mixer.pre_init(audio_fx.SAMPLE_RATE, -16, 2)
    except pygame.error:
        pass
    pygame.init()
    screen = pygame.display.set_mode((config.width, config.height))
    pygame.display.set_caption(config.title)
    clock = pygame.time.Clock()

    sounds = _build_sounds()
    renderer = Renderer(config)
    game = Game(config, seed=seed)

    running = True
    while running:
        # Clamp dt so a hiccup (window drag, debugger pause) can't teleport the snake.
        dt = min(clock.tick(config.fps) / 1000.0, 0.05)

        for evt in pygame.event.get():
            if evt.type == pygame.QUIT:
                running = False
                break
            if evt.type == pygame.MOUSEBUTTONDOWN and evt.button == 1:
                game.handle_click()  # also starts/restarts from MENU / GAME_OVER
            elif evt.type == pygame.MOUSEBUTTONDOWN and evt.button == 3:
                game.add_ice_patch()  # RIGHT click: freeze a disc ahead of the head (no-op outside PLAYING)
            elif evt.type == pygame.KEYDOWN:
                if evt.key == pygame.K_ESCAPE:
                    running = False
                    break
                name = _KEY_NAMES.get(evt.key)
                if name is not None:
                    game.handle_key(name)

        mouse_pos = pygame.mouse.get_pos()
        # Nitro is "hold to boost": report whether LEFT is currently pressed.
        buttons = pygame.mouse.get_pressed()
        boost_held = bool(buttons[0]) if buttons else False
        events = game.update(dt, mouse_pos, boost_held=boost_held)
        for name in events:  # semantic event -> one-shot generated SFX
            _play(sounds, name)
        renderer.draw(screen, game)
        pygame.display.flip()

    pygame.quit()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mouse Snake - a snake that follows your cursor"
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="RNG seed for apple spawns (reproducible games)"
    )
    args = parser.parse_args()
    raise SystemExit(run(seed=args.seed))


if __name__ == "__main__":
    main()

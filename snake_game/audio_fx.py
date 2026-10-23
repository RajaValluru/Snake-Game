"""Procedural sound-effect synthesis (pure Python, no pygame).

The game's one-shot SFX are *generated* as raw PCM at startup instead of being
loaded from audio files, so neither the repo nor the single-file exe carries a
binary asset.  Playback is wired in ``main.py`` via
``pygame.mixer.Sound(buffer=pcm.samples)`` — the only place that touches pygame
audio; everything here stays plain Python so it can be unit-tested headless:

- :func:`make_apple_eat_sound`    -- short "pop + crunch" when an apple is eaten
- :func:`make_flame_ignite_sound` -- rising whoosh + low rumble as nitro flames kick in
- :func:`make_ice_slide_sound`    -- soft shhh-slide with faint ice crackle

All generators are deterministic (fixed local seeds; they never touch
``Game.rng``, so game simulation stays reproducible) and cheap enough to run
once at startup.  Output is signed 16-bit little-endian, interleaved stereo at
:data:`SAMPLE_RATE` — exactly what ``pygame.mixer.Sound(buffer=...)`` consumes.
"""

from __future__ import annotations

import math
import random
import struct
from dataclasses import dataclass

#: Sample rate (Hz) of every generated effect; main.py inits the mixer to match.
SAMPLE_RATE = 44_100

_TWO_PI = math.tau


@dataclass(frozen=True)
class PcmSound:
    """Raw audio: signed 16-bit little-endian, interleaved stereo samples."""

    samples: bytes
    sample_rate: int = SAMPLE_RATE
    channels: int = 2

    @property
    def frames(self) -> int:
        """Number of stereo frames (samples per channel)."""
        return len(self.samples) // (self.channels * 2)

    @property
    def duration_s(self) -> float:
        return self.frames / self.sample_rate


# -- small DSP helpers ----------------------------------------------------------


def _clamp_unit(v: float) -> float:
    if v < -1.0:
        return -1.0
    if v > 1.0:
        return 1.0
    return v


def _smoothstep(x: float) -> float:
    """C1-smooth 0->1 ramp over x in [0, 1] (holds at the ends)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    return x * x * (3.0 - 2.0 * x)


def _white(seed: int, n: int) -> list[float]:
    """n deterministic uniform white-noise samples in [-1, 1)."""
    rng = random.Random(seed)
    return [rng.uniform(-1.0, 1.0) for _ in range(n)]


def _one_pole_lp(stream, alpha: float) -> list[float]:
    """First-order low-pass (``y += (x - y) * alpha``); small alpha = smoother."""
    out = []
    append = out.append
    y = 0.0
    for x in stream:
        y += (x - y) * alpha
        append(y)
    return out


def _pack_stereo(pairs, scale: float = 1.0) -> bytes:
    """Pack (left, right) float pairs into int16 little-endian stereo PCM."""
    out = bytearray(len(pairs) * 4)
    off = 0
    for l, r in pairs:
        struct.pack_into(
            "<hh", out, off,
            int(_clamp_unit(l * scale) * 32767),
            int(_clamp_unit(r * scale) * 32767),
        )
        off += 4
    return bytes(out)


# -- the three game effects -----------------------------------------------------


def make_apple_eat_sound() -> PcmSound:
    """~0.25 s "pop + crunch" for eating an apple.

    Three layered parts, all decaying fast enough that the sound is silent by
    the end of its buffer: a broadband bite transient (the skin cracking), a
    descending sine pop with a touch of harmonic (the fruit giving way), and a
    short low thump (it going down).  Panned dead center.
    """
    n = int(round(0.25 * SAMPLE_RATE))
    noise = _white(1234, n)
    pairs: list[tuple[float, float]] = []
    append = pairs.append
    phase_pop = 0.0
    phase_thump = 0.0
    for i in range(n):
        t = i / SAMPLE_RATE
        # "Crunch": white noise, very fast decay (~30 ms).
        bite = noise[i] * math.exp(-t / 0.008) * 0.9
        # Pop body: sine gliding down 380 -> 110 Hz with a quick exponential
        # envelope; +30 % second harmonic rounds it off.
        phase_pop += (110.0 + 270.0 * math.exp(-t / 0.03)) / SAMPLE_RATE
        pop_env = _smoothstep(t / 0.006) * math.exp(-t / 0.05)
        p = _TWO_PI * phase_pop
        pop = (math.sin(p) + 0.3 * math.sin(2.0 * p)) * pop_env * 0.7
        # Low thump starting just after the bite, like weight landing.
        thump = 0.0
        if t >= 0.018:
            phase_thump += 74.0 / SAMPLE_RATE
            thump = math.sin(_TWO_PI * phase_thump) * math.exp(-(t - 0.018) / 0.05) * 0.35
        v = bite + pop + thump
        append((v, v))
    return PcmSound(_pack_stereo(pairs))


def make_flame_ignite_sound() -> PcmSound:
    """~0.6 s "whoosh" for nitro flames kicking in.

    Two independent noise streams are pushed through a one-pole low-pass whose
    cutoff *rises* over time (alpha 0.06 -> 0.5): the whoosh starts dark and
    muffled, then brightens as if the flame catches — while a low two-tone
    rumble gives it engine-like body and a faint broadband tick marks the very
    start of ignition.  Channels are slightly different (width) with the rumble
    panned a touch toward the right.
    """
    n = int(round(0.6 * SAMPLE_RATE))
    noise_l = _white(2718, n)
    noise_r = _white(9173, n)

    # Brightness sweep: per-sample low-pass alpha grows from 0.06 (dark) to
    # 0.5 (bright) over the first 0.45 s of the effect.
    def bright_lp(stream):
        out = []
        append = out.append
        y = 0.0
        for i in range(n):
            a = 0.06 + 0.44 * _smoothstep((i / SAMPLE_RATE) / 0.45)
            y += (stream[i] - y) * a
            append(y)
        return out

    whoosh_l, whoosh_r = bright_lp(noise_l), bright_lp(noise_r)

    pairs: list[tuple[float, float]] = []
    append = pairs.append
    phase_1 = 0.0
    phase_2 = 0.0
    for i in range(n):
        t = i / SAMPLE_RATE
        # Whoosh envelope: ramp up over 0.22 s, hold, blow out after 0.42 s.
        env = _smoothstep(t / 0.22) * math.exp(-max(0.0, t - 0.42) / 0.11)
        w_l = whoosh_l[i] * env * 1.7
        w_r = whoosh_r[i] * env * 1.7
        # Low rumble under the whoosh (fundamental + offset harmonic).
        phase_1 += 46.0 / SAMPLE_RATE
        phase_2 += 92.0 / SAMPLE_RATE
        rumble_env = _smoothstep(t / 0.35) * math.exp(-max(0.0, t - 0.45) / 0.13)
        r = (math.sin(_TWO_PI * phase_1) * 0.7 + math.sin(_TWO_PI * phase_2 + 1.3) * 0.3) \
            * rumble_env * 0.5
        # Faint ignition tick at t=0 (raw noise, different decay per channel).
        tick_l = noise_l[i] * math.exp(-t / 0.018) * 0.22
        tick_r = noise_r[i] * math.exp(-t / 0.014) * 0.22
        append((w_l + r + tick_l, w_r + r * 0.9 + tick_r))
    return PcmSound(_pack_stereo(pairs, scale=0.95))


def make_ice_slide_sound() -> PcmSound:
    """~0.75 s "shhh" for sliding through ice.

    Two independent noise streams are high-emphasized (sample minus a mild
    low-pass of itself) so they read as air hissing past the head, under a
    heavily low-passed "airy whoom" that carries the onset; three faint sine
    "tinks" at fixed times add ice-crackle detail, panned alternately left and
    right.  Envelope: fast attack, short sustain, long release.
    """
    n = int(round(0.75 * SAMPLE_RATE))
    noise_l = _white(4242, n)
    noise_r = _white(8675, n)

    lp_l, lp_r = _one_pole_lp(noise_l, 0.30), _one_pole_lp(noise_r, 0.30)
    air = _one_pole_lp(noise_l, 0.06)  # heavily smoothed: the low "whoom" bed

    # (time_s, frequency_hz) of the ice-crackle tinks; deterministic by design.
    crackles = ((0.16, 2350.0), (0.34, 1800.0), (0.53, 2750.0))
    crackle_phases = [0.0] * len(crackles)

    pairs: list[tuple[float, float]] = []
    append = pairs.append
    for i in range(n):
        t = i / SAMPLE_RATE
        env = _smoothstep(t / 0.07) * math.exp(-max(0.0, t - 0.38) / 0.22)
        slide_l = (noise_l[i] - 0.9 * lp_l[i]) * env * 1.3
        slide_r = (noise_r[i] - 0.9 * lp_r[i]) * env * 1.3
        whoom = air[i] * _smoothstep(t / 0.12) * math.exp(-max(0.0, t - 0.30) / 0.28) * 0.4

        c_l = c_r = 0.0
        for k, (t_c, f) in enumerate(crackles):
            tau = t - t_c
            if tau > 0.0:
                crackle_phases[k] += f / SAMPLE_RATE
                s = math.sin(_TWO_PI * crackle_phases[k]) * math.exp(-tau / 0.013) * 0.24
                c_l += s if k % 2 == 0 else 0.4 * s
                c_r += 0.4 * s if k % 2 == 0 else s

        append((slide_l + whoom + c_l, slide_r + whoom + c_r))
    return PcmSound(_pack_stereo(pairs, scale=0.95))

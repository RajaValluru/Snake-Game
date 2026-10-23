"""Headless tests for the procedural SFX synthesizer (snake_game/audio_fx).

The generators are pure Python (no pygame), so we assert on the raw PCM:
deterministic bytes, correct 16-bit stereo layout and sane loudness.
"""

import struct

from snake_game.audio_fx import (
    PcmSound,
    SAMPLE_RATE,
    make_apple_eat_sound,
    make_flame_ignite_sound,
    make_ice_slide_sound,
)


def _int16(pcm: PcmSound):
    """Unpack a PcmSound into its raw int16 sample list (little-endian)."""
    return struct.unpack(f"<{pcm.frames * pcm.channels}h", pcm.samples)


ALL_BUILDERS = {
    "apple": make_apple_eat_sound,
    "flame": make_flame_ignite_sound,
    "ice": make_ice_slide_sound,
}


def test_generators_return_pcm_sounds_at_the_mixer_sample_rate():
    for build in ALL_BUILDERS.values():
        pcm = build()
        assert isinstance(pcm, PcmSound)
        assert pcm.sample_rate == SAMPLE_RATE
        assert pcm.channels == 2


def test_generated_sound_is_deterministic_bytes():
    for name, build in ALL_BUILDERS.items():
        a, b = build(), build()
        assert a.samples == b.samples, f"{name} sound is not reproducible"
        # ...and never touches the game RNG stream: same result on every call.
        c = build()
        assert a.samples == c.samples


def test_pcm_layout_is_valid_stereo_int16():
    for name, build in ALL_BUILDERS.items():
        pcm = build()
        # int16 stereo frames are 4 bytes each; buffer must be an exact multiple.
        assert len(pcm.samples) % (pcm.channels * 2) == 0
        vals = _int16(pcm)
        assert len(vals) == pcm.frames * pcm.channels
        for v in vals:
            assert -32768 <= v <= 32767


def test_durations_match_the_design():
    # ~0.25 s pop, ~0.6 s whoosh, ~0.75 s slide (see audio_fx docstrings).
    expected = {
        "apple": 0.25,
        "flame": 0.60,
        "ice": 0.75,
    }
    for name, build in ALL_BUILDERS.items():
        assert abs(build().duration_s - expected[name]) < 1e-9


def test_no_sound_is_silent_and_none_clips_hard():
    for name, build in ALL_BUILDERS.items():
        vals = _int16(build())
        peak = max(abs(v) for v in vals) / 32768.0
        assert peak > 0.3, f"{name} sound is unexpectedly quiet (peak {peak:.2f})"
        # A little headroom: only a small fraction of samples may sit at the wall.
        clipped = sum(1 for v in vals if abs(v) >= 32760)
        assert clipped < len(vals) * 0.05, f"{name} sound clips too hard"

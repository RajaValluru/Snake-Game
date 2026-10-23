"""Mouse Snake - a pygame snake game steered by the mouse cursor.

The package is split into small, single-purpose modules:

- config:   all tunable values (frozen dataclass)
- geom:     pure math helpers (no pygame)
- trail:    arc-length path-history buffer for the head (pure)
- snake:    head kinematics + body sampling from the trail (pure)
- apple:    apple spawning / eating rules (pure)
- fx:       effect data: nitro flame particles + ice patches (pure)
- audio_fx: procedural one-shot SFX synthesis -> raw PCM (pure; played by main)
- game:     state machine, per-frame rules and effect ownership (pure)
- renderer: all pygame drawing

Only `renderer` imports pygame, so every gameplay rule can be unit-tested
headless (no display required).
"""

__version__ = "1.0.0"

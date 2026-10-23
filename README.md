# Mouse Snake 🐍🖱️

A pygame snake game where **you steer the snake with your mouse cursor** — not a
grid, not arrow keys. The snake's head chases your cursor and its body traces
*every curve, zig-zag and loop the path it took*. Eat apples to grow: new length
slides smoothly out of the (possibly curved) tail instead of popping in as a
square block.

Two extra tricks: **hold left click for nitro** — red flames trail off the tail
while you sprint at 1.5× speed, dying out when you let go — and **right-click
drops an ice patch ahead of your head**, so you slide through it slowed to a
crawl.

The game also *sounds* like what's happening: eating an apple gives a short
pop-and-crunch, igniting nitro is a rising whoosh with a low rumble, and
gliding across ice is a soft shhh-slide with faint crackle. All of these are
procedurally synthesized at startup (no audio files — not even in the exe);
boxes without a sound card simply run silent.

## Run it

### Option A — build & run the standalone .exe (no Python needed to play)

```bash
pip install pyinstaller     # one-time, on the machine doing the building
python build_exe.py         # -> dist/MouseSnake.exe
```

The result is a **single self-contained file** (`dist/MouseSnake.exe`):
Python + pygame are bundled inside, so you can copy it to any Windows machine
and double-click — no Python installation required. First launch takes a
moment while the exe unpacks itself into a temp dir. Command-line flags still
work: `MouseSnake.exe --seed N` gives reproducible apple spawns.

Tips:
- Set `MOUSE_SNAKE_CONSOLE=1` in the environment before building to attach a
  console window (startup errors become visible instead of a dialog).
- To brand the exe, drop an `icon.ico` into the repo root and add
  `icon="icon.ico"` to the `EXE(...)` call in `MouseSnake.spec`.

### Option B — run from source

Requires Python 3.9+ (developed on 3.12).

```bash
pip install -r requirements.txt
python main.py            # optional: --seed N for reproducible apple spawns
```

`pygame-ce` is a drop-in replacement if you prefer it over `pygame`.

### Controls

| Input | Action |
|---|---|
| Move mouse | Steer — the head chases the cursor |
| **Hold** left click | Nitro: 1.5× top speed, red flames trail the tail (they burn out when you release) |
| Right click | Drop an ice patch in front of the head — sliding through it slows you to ~35 % pace until it melts |
| Click / Space / Enter | Start (menu) or play again (game over) |
| R | Restart anytime, even mid-game |
| Esc | Quit |

Rules: eat apples to grow; if your head touches any non-adjacent part of your
body it's game over. The head slows and stops when it reaches a *parked*
cursor (so you can't be dragged into a wall), and a soft clamp keeps the head
inside the window — the only way to die is biting yourself.

Nitro and ice are pure effects on top of those rules: flames never block or
damage anything, and ice only slows you while your head is inside a patch
(patches melt after ~6 s; at most 6 exist at once, oldest melts first).

## Project layout

```
Snake-Game/
├── main.py               # entry point: pygame window, events, clock, mixer -> Game + Renderer
├── build_exe.py          # one-command standalone .exe build (drives PyInstaller)
├── MouseSnake.spec       # PyInstaller recipe: single-file, no-console dist/MouseSnake.exe
├── requirements.txt      # pygame (pytest for dev; pyinstaller to build the exe)
├── conftest.py           # makes the repo root importable for pytest
├── snake_game/
│   ├── config.py         # GameConfig: every tunable value in one frozen dataclass
│   ├── geom.py           # pure math helpers (dist, clamp, lerp, wrap_pi, ...)
│   ├── trail.py          # TrailBuffer: arc-length path history of the head  [no pygame]
│   ├── snake.py          # Snake: head kinematics + body resampling + growth + nitro easing [no pygame]
│   ├── apple.py          # Apple spawning / eating rules                     [no pygame]
│   ├── fx.py             # effect data: flame particles + ice patches        [no pygame]
│   ├── audio_fx.py       # procedural SFX synthesis -> raw 16-bit stereo PCM [no pygame]
│   ├── game.py           # state machine (MENU/PLAYING/GAME_OVER) + per-frame rules; owns nitro/ice state, emits SFX events [no pygame]
│   └── renderer.py       # all drawing: tube snake, apple, flames, ice, HUD, overlays  [pygame only here]
├── tests/
│   ├── test_trail.py     # arc-length sampling, trimming, clamping (headless)
│   ├── test_snake.py     # kinematics caps, smooth growth, curve following, self-collision, nitro speed (headless)
│   ├── test_apple.py     # spawn rules, determinism, fallback (headless)
│   ├── test_effects.py   # nitro/ice/flames: spawning, gating, melting, capping + renderer pixel check
│   ├── test_audio_fx.py  # synthesized SFX: determinism, PCM layout, loudness (headless)
│   ├── test_events.py    # semantic events from Game.update that drive the sound effects
│   └── test_game_loop.py # full Game+Renderer smoke test via SDL's dummy video driver
├── README.md             # this file: what it is + how the curving works
└── DEVELOPERS.md         # agent read-me: architecture, effect pipelines, extension recipes
```

Only `renderer.py` and `main.py` touch pygame — everything else is pure math,
which is why the whole rule set can be unit-tested headlessly:

```bash
pip install pytest
python -m pytest tests/
```

## How it works — how the curving works

The classic snake game lives on a grid and turns 90° at intersections. This one
has no grid at all; "curve consistency" is achieved by construction, in four
layers:

### 1. Head kinematics: chase + turn-rate limit (`snake.py`)

Each frame the head computes where it *wants* to face — directly at the cursor:

```
desired = atan2(cursor − head)
heading += clamp(wrap_pi(desired − heading), ±turn_rate · dt)
pos     += (cos(heading), sin(heading)) · speed · dt
```

Because the per-frame turn is capped (`turn_rate` rad/s, default 5.0) while the
head keeps moving, it can never snap its direction: the minimum turning radius
is `speed / turn_rate ≈ 260/5 ≈ 52 px`. Wave your mouse and the snake draws a
matching smooth arc; jerk it around and you get tight spirals — which is also
how you kill yourself.

Speed isn't constant either: `want = min(head_speed, cursor_chase_gain ·
distance_to_cursor)`, eased toward at `speed_ease` px/s². Far from the cursor
you cruise at 260 px/s; on top of a parked cursor you slow to a stop instead of
rattling against the wall.

### 2. Trail buffer: arc-length path history (`trail.py`)

Every frame, if the head moved ≥ `trail_min_step` (3 px), its position is
appended to a `TrailBuffer`: an ordered list of points plus **cumulative arc
lengths** (`cum[i]` = distance from point 0 to point i). The buffer is trimmed
from the front each frame so it only holds the current body length + slack.

### 3. Body = resampling that path (the key idea)

Body segments are *not* steered individually — they're just **resamples of the
head's recorded path at fixed arc-length spacing**:

```
sample k  =  the trail point k · segment_spacing px behind the head   (k = 1..n, n = length / spacing)
```

`TrailBuffer.sample(d)` finds that point by binary search over `cum` and linear
interpolation between two neighboring points. Since every segment sits on the
*very same path the cursor drew*, merely offset in arc length behind the head:

- the body automatically follows **all paths the mouse went into** — curves,
  zig-zags, full loops — with zero per-segment steering and no drift,
- adjacent samples are exactly `segment_spacing` (7 px) apart along any shape,
  so tight curls stay consistent instead of stretching or shearing.

This is also why self-collision exists in the first place: head and tail share
one coordinate history, so a fast enough full loop puts your head inside your
own body. (`has_self_collision` compares the head against every other body
sample, skipping the `collision_skip_samples` nearest ones that are "close" just
by being adjacent.)

### 4. Smooth growth — why it's not one block (`snake.py`)

Eating an apple doesn't append a segment; it raises a **target length** by
`grow_per_apple_px` (60 px). The real body then eases toward that target at most
`max_growth_rate_px_s` (90 px/s) each frame. Because the tail is just "the
trail sample furthest back", extra length means the tail tip **slides backward
along the curved history that already exists there** — over ~0.7 s per apple you
watch the snake visibly stretch out of its own curve, with no block appearing
anywhere. (Growth is rate-capped: eating ten apples quickly still grows at 90
px/s, it just targets a longer body.)

### 5. Rendering the tube (`renderer.py`)

The body is painted as a dense chain of overlapping circles in two passes —
a dark outline circle per sample, then a gradient-filled circle (head green →
tail teal) with subtly brighter alternating "scales" — ordered tail-to-head so
the head lands on top. Because the radius tapers `12 px → 5 px` and samples are
only 7 px apart, the overlap hides every joint: even through a hairpin turn the
snake reads as one continuous tube. The head adds direction-aware eyes (offset
along/side of the heading vector).

## Tuning

Everything lives in `GameConfig` (`snake_game/config.py`). The knobs that most
affect feel:

| Field | Default | Effect |
|---|---|---|
| `head_speed` / `turn_rate` | 260 px/s, 5.0 rad/s | top speed; min turning radius = speed/turn_rate (≈52 px) |
| `cursor_chase_gain` | 4.0 | how eagerly the head closes on a far cursor |
| `segment_spacing` / `trail_min_step` | 7 px / 3 px | body sample density vs path recording resolution |
| `head_radius` / `tail_radius` | 12 / 5 px | tube thickness and taper |
| `grow_per_apple_px` / `max_growth_rate_px_s` | 60 / 90 | length per apple, and how fast that length slides out |
| `collision_skip_samples` / `collision_factor` | 5 / 0.8 | which body parts can kill you (≈ first 35 px of neck is safe) |
| `initial_length_px`, `max_length_px` | 140 / 2600 | starting size and hard cap |

Nitro & ice knobs: `nitro_speed_multiplier` (1.5×), `nitro_ramp_rate`,
`flame_spawn_per_second` / `flame_lifetime_*_s` / `flame_size_max` /
`flame_spread` / `flame_speed_away` / `flame_max_count`, and
`ice_patch_radius` (46 px) / `ice_lifetime_s` (6 s) / `ice_speed_factor`
(0.35×) / `ice_spawn_ahead_px` (80 px ahead of the head) /
`ice_max_patches` (6). Effect colors (`flame_*_color`, `ice_patch_color`,
`ice_ring_color`) are plain RGB tuples in the same dataclass.

Make a variant with `GameConfig().with_changes(head_speed=320, ...)`.

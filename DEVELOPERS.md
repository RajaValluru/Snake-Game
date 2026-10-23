# Mouse Snake — Developer Read-Me

Orientation doc for agents (or humans) adding features **without re-learning the
architecture from scratch**. Read this first, then `README.md` for the
player-facing "how it works" narrative.

## 1. The golden rules

Everything in this repo hangs on four rules:

1. **The core is pure.** `snake_game/` contains no pygame except
   `renderer.py`. All game logic (`config`, `geom`, `trail`, `snake`, `apple`,
   `fx`, `game`) is plain Python + math, so the entire rule set runs and can be
   unit-tested **headless** (SDL's dummy video driver — see `conftest.py`).
2. **`main.py` is the only place raw pygame events become meaning.** It
   translates mouse buttons / keys into *semantic calls* on `Game`
   (`handle_click`, `add_ice_patch`, `boost_held=...`, `handle_key(name)`).
   Never feed a pygame event object into the core.
3. **Determinism via injected RNG + dt-based simulation.** One
   `random.Random(seed)` lives on `Game`; all randomness (apple spawns, flame
   jitter) flows through it. All motion is integrated with real-time deltas in
   seconds (`dt`), never frame counts — so a 60/144 Hz screen behaves the same.
4. **Always rebuild the exe when you're done.** `dist/MouseSnake.exe` is a
   shipped artifact, not a build byproduct: whenever your work is complete and
   tests pass, run `python build_exe.py` so the exe matches the current code,
   then smoke-test it (see *Definition of done* below). A finished feature that
   exists only in source is **not** finished.

Keep 1–3 intact and every new feature stays testable the same way; rule 4 keeps
the playable artifact honest.

## 2. Module map

| File | Responsibility | pygame? | Key API |
|---|---|---|---|
| `main.py` | Window, event loop, clock; maps events → semantic calls | yes (only here + renderer) | `run(config=None, seed=None)` |
| `snake_game/config.py` | **Every tunable** in one frozen dataclass + validation | no | `GameConfig`, `.with_changes(**kw)` |
| `snake_game/geom.py` | Pure math helpers (`dist`, `clamp`, `lerp`, `wrap_pi`, `point_at_angle`) | no | functions |
| `snake_game/trail.py` | Arc-length path history of the head; O(log n) resampling | no | `TrailBuffer.append/sample/total_length` |
| `snake_game/snake.py` | Head kinematics (chase + turn cap), body = trail resamples, growth, self-collision, **boost easing** | no | `Snake.update(dt, target, *, boost_active=False, ice_speed_factor=1.0)`, `.body_samples_with_radii()`, `.tail_point()`, `.tail_travel_dir()`, `.boost_level` |
| `snake_game/apple.py` | Apple spawn (min distance from head, in-bounds) + eating test | no | `spawn_apple(cfg, rng, snake)` → `Apple.is_eaten(snake)` |
| `snake_game/fx.py` | **Effect data only**: flame particles + ice patches; aging helper | no | `FlameParticle`, `IcePatch`, `step_flames(list, dt)`, `make_patch_speckles(rng)` |
| `snake_game/audio_fx.py` | Procedural SFX synthesis: apple pop / nitro whoosh / ice slide as raw 16-bit stereo PCM (deterministic; no audio files anywhere in the project or the exe) | no | `make_apple_eat_sound()`, `make_flame_ignite_sound()`, `make_ice_slide_sound()` → `PcmSound` |
| `snake_game/game.py` | State machine (MENU/PLAYING/GAME_OVER), per-frame rules, **owns all effect state**, spawning/expiring/slowing rules; emits semantic SFX events | no | `Game.update(dt, mouse_pos, *, boost_held=False) -> List[str]`, `.handle_click()`, `.handle_key(name)`, `.add_ice_patch()`, `.ice_speed_factor_at(pos)`; state: `.flames`, `.ice_patches`; events: `EVENT_APPLE_EATEN`, `EVENT_FLAME_ON`, `EVENT_ICE_ENTERED` |
| `snake_game/renderer.py` | All drawing: background, ice ground layer, apple, tube snake, flames + head rings, HUD, menu/game-over overlays. **Must never mutate game state.** | yes (only here + main) | `Renderer(cfg).draw(screen, game)` |

Tests mirror the modules: `tests/test_{trail,snake,apple,game_loop,effects,audio_fx}.py`
plus `tests/test_events.py` for the semantic events that drive sound playback.

## 3. Per-frame flow

```
main.py loop
 ├─ dt = min(clock.tick(fps)/1000, 0.05)        # hiccup clamp
 ├─ events → semantic calls:
 │    LMB down          → game.handle_click()      (start/restart from MENU/GAME_OVER)
 │    RMB down          → game.add_ice_patch()     (no-op outside PLAYING)
 │    keys r / space / return → game.handle_key(name)   (r = restart anytime)
 │    Esc               → quit
 ├─ boost_held = pygame.mouse.get_pressed()[0]  # nitro is HOLD-to-boost, polled per frame
 └─ events = game.update(dt, mouse_pos, boost_held=boost_held)
      ├─ self.time += dt                        (drives pulses/animation clocks)
      ├─ if PLAYING: snake.update(...) with ice_speed_factor_at(head)
      │    apple eat? → score++, grow_by(), new spawn_apple()
      │    head hits non-adjacent body? → GAME_OVER
      └─ _spawn_flames() + _update_fx(dt)  — effect aging runs in EVERY state,
                                          so flames/ice keep melting on the
                                          game-over screen too
 for name in events: play generated SFX     # main.py maps the event names to the
                                           # audio_fx sounds via pygame.mixer (no-op without a device)

renderer.draw(screen, game)   # layer order (bottom → top):
   pre-rendered background → ice patches (ground) → apple → snake tube
   → flame particles + head rings (heat/frost) → HUD → menu/game-over overlay
```

Note the split: **rules** for effects live in `game.py`, **data shapes** in
`fx.py`, **looks** in `renderer.py`. A new effect touches exactly those three
layers plus a config field or two.

Sound follows the same split with one extra layer of indirection:
`Game.update` returns the semantic events that happened this frame
(`EVENT_APPLE_EATEN`, `EVENT_FLAME_ON`, `EVENT_ICE_ENTERED`); `main.py` maps those names to the procedurally generated one-shot SFX from `audio_fx.py` (synthesized once at startup into raw PCM, played through `pygame.mixer.Sound(buffer=...)`). The core never touches pygame audio — a machine with no sound card simply runs silently (`_build_sounds` returns `{}` when the mixer fails to init).

## 4. Movement model (short version)

The head chases the cursor with a turn-rate cap and eased speed:

- heading eases toward `atan2(cursor − head)` at ≤ `turn_rate` rad/s,
- target speed `want = min(head_speed · boost_factor · ice_factor, cursor_chase_gain · d_to_cursor)`,
  approached at `speed_ease` px/s² (parked cursor ⇒ smooth stop),
- body samples resample the head's trail history every `segment_spacing` px.

Full explanation in `README.md`. For feature work you mostly need:
`snake.speed`, `snake.boost_level ∈ [0,1]` (normalized nitro strength),
`game.ice_speed_factor_at(pos) ∈ (0,1]` (1 = no ice slowdown).

## 5. The effects system (nitro + ice)

### Nitro (hold LEFT click → red flames at the tail, 1.5× speed)

Pipeline, one per frame while PLAYING:

1. `main.py` polls `get_pressed()[0]` and passes `boost_held` into
   `Game.update`.
2. `Snake.update(..., boost_active=...)` eases `boost_factor` toward
   `nitro_speed_multiplier` (1.5) or back to 1.0 at ~6/s exponential rate — the
   snake *accelerates into* nitro rather than jumping; `want` **and** the speed
   cap both scale with it, so top speed becomes `head_speed · 1.5`.
3. `Game._spawn_flames`: emits particles at `snake.tail_point()` drifting along
   `-tail_travel_dir()`, gated on `boost_level ≥ 0.15` **and** `speed ≥ 60`
   (no flames while parked), rate `flame_spawn_per_second · (0.3 + 0.7·level)`,
   hard cap `flame_max_count`. Jitter/drift/lifetime/size come from `game.rng`.
4. `_update_fx` → `step_flames()` moves particles, ages them out, prunes dead —
   **every state**, so flames die out naturally after you release the button
   (and even on game over).
5. Renderer: flame circles are painted *above* the body through a shared
   SRCALPHA overlay blitted with `BLEND_RGBA_ADD` (colors must be premultiplied
   against zero-black for that to work); plus a warm "heat ring" around the head
   while `boost_level > 0.25`, and an orange **NITRO** tag in the HUD.

### Ice (RIGHT click → frozen disc ahead of the head, sliding slowdown)

1. RMB down → `Game.add_ice_patch()` (PLAYING only): centers a disc
   `ice_spawn_ahead_px` (80 px) ahead along the current heading, clamped on
   screen; if at capacity (`ice_max_patches`) the **oldest** patch melts early;
   speckles come from a *separate* RNG stream keyed by `_ice_seq` so patches are
   unique but reproducible.
2. Each frame `Game.update` asks `ice_speed_factor_at(snake.pos)` → the strongest
   slowdown (min) among patches containing the head, multiplied into the snake's
   target speed ⇒ the head visibly **slides** through at ~35 % pace while the
   tail keeps its own inertia.
3. Patches age (`IcePatch.age_by`), melt after `ice_lifetime_s`, and their alpha
   follows `alpha_scale()` (quick fade-in, 1 s melt-out).
4. Renderer: discs are painted as a **ground layer under** the apple/snake
   (fill + inner glow + rim + twinkling speckles); while the head is on ice the
   same renderer pass adds a frost ring + orbiting sparkles around the head.

### Where to look when something feels wrong

| Symptom | First place to check |
|---|---|
| Nitro not fast enough / not smooth | `nitro_speed_multiplier`, `nitro_ramp_rate` (config); easing in `snake.py` |
| Flames too sparse / too lingering | `flame_spawn_per_second`, `flame_lifetime_*_s`, gates in `Game._spawn_flames`; alphas in `_paint_flames_and_head_fx` |
| Ice barely slows you | `ice_speed_factor` (0.35); make sure the head is actually inside a disc (`IcePatch.contains`) |
| Patches too small / short-lived | `ice_patch_radius`, `ice_lifetime_s`, `ice_spawn_ahead_px` |

## 6. Config: the only tuning surface

All gameplay numbers live in `GameConfig` (`config.py`) — frozen dataclass,
validated in `__post_init__` (raises on nonsense values), variants via
`.with_changes(...)`. Groups relevant to effects:

- **Nitro:** `nitro_speed_multiplier`, `nitro_ramp_rate`, `flame_spawn_per_second`,
  `flame_lifetime_min_s/max_s`, `flame_size_max`, `flame_spread`,
  `flame_speed_away`, `flame_max_count`.
- **Ice:** `ice_patch_radius`, `ice_lifetime_s`, `ice_speed_factor`,
  `ice_spawn_ahead_px`, `ice_max_patches`.
- **Effect colors:** `flame_mid_color`, `flame_core_color`, `flame_tip_color`,
  `ice_patch_color`, `ice_ring_color` (plain RGB tuples; the renderer adds alpha).

**Rule: never hard-code a gameplay number in logic or rendering code — put it
in config and validate it.** Visual-only constants (ring widths, overlay alphas)
may live in `renderer.py`.

## 7. Testing strategy

- `conftest.py` forces SDL's **dummy video driver** so the whole pipeline runs
  headless; tests import normally. No display needed on CI.
- Pattern: build a `Game(cfg, seed=N)` (+ optionally `Renderer(cfg)`) and drive
  it with plain floats — no events involved:

```python
game = Game(cfg, seed=5); game.handle_click()      # MENU -> PLAYING
for _ in range(60):                                # one second at 60 fps
    game.update(DT, (450.0, 320.0), boost_held=True)
```

- Coverage map: `test_trail` (sampling math), `test_snake` (kinematics/growth/
  self-collision + nitro speed cap/fade), `test_apple` (spawn rules/determinism),
  `test_game_loop` (state machine + full Game+Renderer smoke), **`test_effects`**
  (nitro/ice/flames: spawning, gating, melting, capping, no-ops outside PLAYING,
  restart cleanup, and a pixel-level renderer check that flame colors actually
  reach the screen).

When adding a feature: prefer state assertions (`len(game.flames)`,
`game.state`, `snake.boost_factor`) over pixel checks; use exact config colors
for the rare pixel assertion (blending changes with what's underneath). Keep
tests deterministic — pin seeds, avoid wall-clock time.

## 8. Recipes for common changes

**New mouse-button effect** (e.g. middle-click "dash"):
`main.py` event → new semantic method on `Game` (validate state) → rule/state in
`game.py` (+ data shape in a pure module like `fx.py`) → visuals in one of the
renderer's layer passes → config fields + validation → tests in `tests/`.

**New food type / power-up:** extend `apple.py` spawn logic (or add a sibling
module) returning a small dataclass; detect pickup in `Game.update`; apply the
effect through snake/config knobs or new effect state; render in the apple layer.

**Change how you die / win:** only `game.py` (+ config). E.g. walls kill: check
head position vs bounds in `update`. Keep it a pure rule so tests can reach the
state without rendering.

**New HUD element:** `renderer.draw` (after the snake layers, before overlays);
any data it needs must already be on `Game`/`Snake` — never compute gameplay
facts inside the renderer.

**New game state** (e.g. PAUSED): add to `GameState`, handle in
`Game.handle_key` + a branch at the top of `update`; give the renderer an
overlay pass; remember `_update_fx(dt)` should (or shouldn't!) run there — decide
explicitly and test it.

## 9. Gotchas & conventions

- **Renderer is read-only.** If you find yourself assigning to `Game` inside
  `renderer.py`, move the rule into `game.py`.
- **The shared `_fx_overlay`** is cleared *per layer batch*, not per frame:
  ice patches and flames each get their own clear + single blit. Add a new
  translucent effect = another clear/blit pair, or join an existing pass.
- **`BLEND_RGBA_ADD` needs zero-black bases:** draw only colored pixels onto the
  freshly cleared overlay (no opaque fills) or the whole window lights up.
- **Effect aging is state-independent** (`_update_fx` runs in MENU/GAME_OVER too).
  That's intentional (flames die out on the game-over screen); new persistent
  effects should follow suit unless there's a reason not to.
- **RNG order matters for determinism:** `game.rng` feeds apple spawns *and*
  flame jitter in a fixed call order; ice speckles deliberately use their own
  stream (`_ice_seq`). If you add new RNG consumers, decide which stream they
  belong to and keep the per-frame call order stable.
- **Frozen config:** `GameConfig` is immutable — build variants with
  `.with_changes(...)`, don't assign attributes in tests.
- **dt is clamped at 0.05 s** in `main.py`; simulation code may assume a sane
  dt but should still guard against `dt <= 0`.
- **Soft walls:** the head is position-clamped to the window; speed keeps easing
  (a target beyond the wall still reads "far"). Tests exploit this: point at a
  far-off coordinate for guaranteed full-speed straight-line runs.
- **New top-level module?** PyInstaller picks up anything importable from
  `main.py` automatically, but after adding one, confirm it made it into the
  bundle: `grep -l "snake_game.<newmodule>" build/MouseSnake/*.toc` should hit
  both `Analysis-00.toc` and `PYZ-00.toc`.
- **Sound is generated, not loaded.** The SFX in `audio_fx.py` are pure-Python
  synthesis (deterministic local seeds — never `Game.rng`, so simulation stays
  reproducible) packed into int16 little-endian stereo PCM at 44.1 kHz; there
  are no audio data files to ship with the exe or test against. Keep it that
  way: if you add an SFX, synthesize it in `audio_fx.py`, emit its semantic
  event from `game.py` (transition-based, once per occurrence), and map name →
  sound only in `main.py`.

## 10. Definition of done (run this before calling work complete)

```bash
# 1) full headless suite — must be all-green
python -m pytest tests/ -q

# 2) rebuild the shipped exe (requires pyinstaller: pip install pyinstaller)
python build_exe.py          # -> dist/MouseSnake.exe (single file, ~15 MB)

# 3) boot-smoke-test the EXE itself headless (~15 s): launch it, let it run,
#    then confirm it is STILL alive (a crashing exe exits on its own):
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy ./dist/MouseSnake.exe --seed 5 &
EXE_PID=$!
sleep 12
if kill -0 "$EXE_PID" 2>/dev/null; then echo "boot OK (game loop still running)"; kill "$EXE_PID";
else wait "$EXE_PID"; echo "exe exited early with $? -> investigate"; fi
```

Step 3 passes when the process is *still alive* after ~12 s: that means it
unpacked, initialized pygame, and kept executing the game loop. (Single-file
mode unpacks to a temp dir on first launch — allow for that wait time.) An early
exit means a startup failure: rebuild with `MOUSE_SNAKE_CONSOLE=1` set so the
traceback prints in a console window instead of a modal dialog.

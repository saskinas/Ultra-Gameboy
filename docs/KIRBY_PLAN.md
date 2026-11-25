# Kirby's Dream Land: the special preset

Kirby gets the full treatment. Unlike the other games, Kirby-specific code is
allowed: custom backgrounds, vibrant colours, per-enemy colours, effects. Two
rules stay:

- **Original look, no copied art.** Backgrounds and effects are drawn by code
  (gradients, procedural hills, clouds, stars) in our own colours. Nothing is
  traced or sampled from later Kirby games.
- **It must stay fast.** See the budget below. Every step is measured before
  the next one starts.

## Speed budget

Under the generic enhancer Kirby renders at 6.4 ms mean, 9 ms worst, on the
first stage. The preset must keep:

| Measure | Limit |
| --- | --- |
| Mean render time | ≤ 8 ms |
| Slowest 5% of frames | ≤ 14 ms |
| Worst frame on a scroll or room change | ≤ 25 ms |

How we keep it:

1. **Fix the engine first.** The status-bar fast path (changed score digits
   redraw only themselves), the flipbook for tiles that animate in place, and
   the cheaper settle pass all apply before any Kirby work.
2. **Backgrounds are pre-rendered.** Each stage's sky and parallax layers are
   built once when the stage loads, as wide strips. Each frame only shifts
   them by the scroll register (a slice and a copy, well under 1 ms). Nothing
   procedural runs per frame.
3. **Sky replacement is a mask, not a redraw.** Pixels the map marks as open sky
   take the background strip, so the cached map layer never redraws for
   parallax.
4. **Sprites from a cache.** Kirby and each enemy are recoloured once per
   animation frame (keyed by tile pixels) and reused.
5. **Effects are cheap overlays.** Glows and sparkles are small pre-made
   sprites added on top, with a fixed cap per frame.
6. **Measure every step:** `tools/spikes.py` on a scripted run through each
   stage, plus `tools/seamcheck.py` for leftovers.

## Stages and their looks

| Stage | Look |
| --- | --- |
| Green Greens | Bright morning: deep blue to pale sky, soft rolling hills in two parallax layers, puffy clouds, lush greens, warm path |
| Castle Lololo | Warm stone and brick with torchlit gradients, deep red carpets, shadowy arches behind |
| Float Islands | Tropical sea: turquoise water with animated sparkle, sand, palms, low sun with a warm horizon |
| Bubbly Clouds | High altitude: pastel pink-lavender sky, layered cloud banks, faint stars |
| Mt. Dedede | Dusk to night: purple-orange sky, distant peaks, a moonlit arena for the final fight |

Bosses (Whispy Woods, Lololo & Lalala, Kaboola, Kracko, King Dedede) get
their own colours and a backdrop tweak per arena.

## Characters

- **Kirby:** pink body with soft round shading, rosy cheeks, red feet, a
  highlight on top; the puffed (floating) and inhale frames are shaded as
  spheres.
- **Enemies:** each species coloured by its tile pixels: Waddle Dee orange,
  Bronto Burt pink-purple wings, Gordo dark with a highlight, Scarfy, Twizzy,
  Poppy Bros, Broom Hatter, etc.
- **Items:** warp star gold with a glow, Maxim Tomato red, Pep Brew, Mint Leaf
  green, Spicy Curry, Sparkling Star.

## Interface

- Score, lives and health in a SNES-style bar: filled digits (the original
  draws them hollow), pink health pips, the Kirby lives icon in colour.
- Title screen and stage intros get the stage palettes.

## Steps

1. **Engine prep:** the status-bar fast path, then measure (Mario and Kirby).
2. **Map the game:** find the RAM for stage, room and boss; build level jumps
   by memory edits like `tools/mario_levels.py`; record states for every room.
3. **Label tiles** per stage with `tools/hash_sheet.py` (sky, ground, grass,
   blocks, star blocks, water, clouds, castle stone…).
4. **Green Greens first:** palette, background strips, Kirby and its enemies.
   Show it to you before going on.
5. **The other four stages,** one at a time, each measured.
6. **Effects pass:** glows, sparkles, water shimmer, star trails, within the
   budget.
7. **Extra Game** (the harder second loop) re-uses the stages with tweaks.

## Open questions

- Kirby pink (as in every later game), or a palette option for the original
  greenish look?
- How strong should the backgrounds be: full parallax scenes, or calmer
  gradients that keep the original's open feel?

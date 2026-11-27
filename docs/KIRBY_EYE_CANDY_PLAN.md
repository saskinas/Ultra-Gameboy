# Kirby: eye candy plan

All five stages and the ending have their look. This plan adds motion and
sparkle on top, without changing what the game draws. The same rules as
docs/KIRBY_PLAN.md apply:

- **Original art, drawn by code:** gradients, noise, small procedural
  particles. Nothing traced from other Kirby games.
- **Fast:** each effect gets a budget. Effects that run every frame work on a
  few hundred pixels at most, or on pre-made strips that only shift.
- **Generic where it can be:** each item says whether it's an engine feature
  (any game's preset can turn it on) or Kirby-only (flagged **Kirby**).

What exists to build on: `anim` per pixel in the layer (1 water, 2 flowers,
3 shimmer, 4 backdrop), backdrop layers with parallax (`kx`, `ky`), the
solved kinds per area (water 12, cloth 13, night 15...), lit sprites with
soft shadows, and per-stage ramps.

## Tier 1: the world breathes (cheap, everywhere)

| # | Effect | Where | How | Cost | Engine / Kirby |
| --- | --- | --- | --- | --- | --- |
| 1 | **Drifting clouds**: the backdrop's far cloud layer creeps sideways on its own, slower than the scroll parallax | Green Greens, Float Islands, Bubbly Clouds, ending | A `drift` (pixels per frame) per backdrop layer, added to its scroll offset. The layer is already a pre-made strip | < 0.1 ms | Engine |
| 2 | **Twinkling stars**: the game's stars and the backdrop's tiny stars pulse in brightness, each on its own phase | Starry areas of Bubbly Clouds, Mt. DeDeDe's starry route, Extra Game twilight | A new `anim` type: per-pixel phase from a hash of the position, brightness picked from the 'star' ramp each frame | ~0.2 ms (only star pixels) | Engine (anim type), Kirby (which tiles) |
| 3 | **Sea sparkle**: glints on the sea's surface and wave crests that flash and fade, plus the sun's streaks on the backdrop sea flickering | Float Islands, Castle Lololo's flooded rooms | Extends anim 1/3: a few random crest pixels per frame light to the ramp's top colour for 4 frames | ~0.2 ms | Engine |
| 4 | **Underwater caustics**: soft bright ripples sliding over water (kind 12) | Float Islands' shaft, flooded rooms | Two moving sine bands (as the shimmer does), adding light rather than darkening | ~0.3 ms | Engine |
| 5 | **Swaying grass and leaves**: tall grass tips and palm fronds sway a pixel left and right in a slow wave | Green Greens, Float Islands, Whispy's route | A new `anim` type that shifts the top rows of those tiles' pixels by a sine of x and time (a copy from the cached layer, not a redraw) | ~0.4 ms | Engine (anim type), Kirby (tiles) |

## Tier 2: things react (particles; needs a few RAM reads)

Small pre-made particle sprites drawn after the game's sprites, capped at 24
per frame, each with a short life. This needs a tiny particle system in
ugb.render (generic). What triggers each particle is preset data.

| # | Effect | Trigger | Cost | Engine / Kirby |
| --- | --- | --- | --- | --- |
| 6 | **Landing dust**: two little puffs at Kirby's feet when he lands | Kirby's Y speed going from falling to 0 (RAM; to find) | ~0.1 ms | Particles engine, trigger **Kirby** |
| 7 | **Pop sparkles**: a burst of 4-6 stars where an enemy is swallowed or a star block breaks | A sprite vanishing / a star-block tile turning to sky (tile diff, generic) | ~0.2 ms | Engine |
| 8 | **Inhale streaks**: wind lines flowing into Kirby's mouth while he inhales | Kirby's inhale state (RAM; to find) | ~0.1 ms | **Kirby** |
| 9 | **Warp star trail**: glittering stars trailing the warp star between stages, and a glow around it | The warp star sprite's tiles | ~0.2 ms | **Kirby** |
| 10 | **Ambient motes**: a few slow falling leaves (Green Greens), sea spray drifting up (Float Islands), pollen-like specks in sunbeams (Bubbly Clouds) | Always, per stage, a handful on screen | ~0.2 ms | Engine (spawner), Kirby (which, where) |

## Tier 3: light and air (screen-space, last pass)

| # | Effect | Where | How | Cost | Engine / Kirby |
| --- | --- | --- | --- | --- | --- |
| 11 | **Soft glow**: a gentle bloom around the brightest things (the sun, stars, the warp star, glowing doorways) | All, strongest at night | Threshold the final 160x144, blur small, add. Done once per frame on the small picture | ~0.6 ms | Engine |
| 12 | **Underwater wobble**: lines under the water's surface sway sideways a pixel | Float Islands' shaft | Per-line offset of the kind-12 region in the final picture | ~0.2 ms | Engine |
| 13 | **Night glow around Kirby**: a faint warm light around him in night areas, lighting nearby walls | Starry areas, the hollow tree | A radial tint centred on Kirby's sprite, only on 'night' style areas | ~0.3 ms | **Kirby** |
| 14 | **Time of day per stage**: each stage's backdrop slowly shifts along its own gradient as you go deeper (Green Greens morning to noon, Castle Lololo afternoon to sunset, Mt. DeDeDe dusk to night) | Per area | A small set of pre-made backdrop variants per stage, picked by area: no per-frame work | 0 ms per frame | **Kirby** |

## Order and how you judge them

1. **Tier 1 first,** one effect at a time. For each, a side-by-side preview
   (off / subtle / strong) as a short clip or frame strip from the same save,
   with its measured cost. You pick the strength (or drop it).
2. **Tier 2 next:** finding Kirby's landing and inhale RAM is the only
   research step. Pop sparkles and motes don't need it, so they go first.
3. **Tier 3 last,** because a bloom changes the overall look the most. It
   gets an on/off key in the app (like Tab) so you can compare while playing.
4. Each effect is measured with `tools/spikes.py` against the budget in
   docs/KIRBY_PLAN.md (mean ≤ 8 ms, 95th percentile ≤ 14 ms). If the total
   goes over, the most expensive Tier 3 item gives way first.

My suggestion for a first batch: **1 (drifting clouds), 2 (twinkling stars)
and 3 (sea sparkle).** They're the cheapest, they touch every stage, and they
change nothing about the art you've already approved, only add life to it.

## Status (first batch, built)

Chosen: Tier 1 #2-5, Tier 2 #9-10, Tier 3 #12. All on by default, the
**E** key in the app turns them off and on, and the strengths are numbers in
`EYE_CANDY` (ugb/presets/kirby_dream_land.py; 0 turns one off):

| Effect | Key | How it's marked | Where it shows |
| --- | --- | --- | --- |
| Twinkling stars | `twinkle` | anim 5 on STAR_TILES in 'night' areas | Bubbly Clouds' and Mt. DeDeDe's starry areas |
| Glints | `glint`, `glint_on` | anim 6 on still crest pixels (SEA_TILES), and over animated water (anims 1, 3) | Float Islands' sea, the flooded rooms |
| Light ripples / wobble | `caustics`, `wobble` | anim 7 on underwater (kind 12) | Float Islands' shaft, flooded rooms |
| Sway | `sway` | anim 8 (9 for the sky in those tiles) on tall grass 'G' and palm fronds 'T' | Green Greens, Float Islands, Whispy's route |
| Motes | `motes` | MOTES per backdrop (leaves, spray, specks) | Green Greens, Float Islands, Bubbly Clouds, the ending |
| Warp star trail | `trail` | TRAIL_SPRITES (the star's spinning halves) | Stage intros, and Kirby's spit stars |

The engine parts are generic: anim codes 5-9 and `_eye_candy` in
`Enhancer._animate`, and `_motes` and `_trail` before the sprites. They're
off for presets without EYE_CANDY, MOTES or TRAIL_SPRITES. Measured: no
cost above noise. Previews (eye candy off on the left, on on the right) are
in out/eye_candy/*.gif (out/_kgif.py makes them).

## Open questions

- Should effects follow the original's restraint (subtle, mostly in the
  backgrounds), or go further, like later games (particles on every action)?
- Is a global on/off key for eye candy worth having, so the plain enhanced
  look stays one keypress away?

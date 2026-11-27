# Kirby: techniques that worked

A working guide for bringing each new Kirby level up to the look of Green
Greens. KIRBY_SHAPES_PLAN.md has the reasoning behind each technique; this file
is the checklist.

## The pipeline (it already works for any area)

1. **Capture the whole area in a background copy** (`ugb/atlas.py`, SWEEP in
   the preset).
   - Steer Kirby by pinning his screen X/Y next to the scroll point, never past
     it. The game scrolls only as he walks across that point, and pinning him
     inside a beam or the floor stops the scroll.
   - Try each direction high and low. Try "up" at three places across the
     screen. Free-flight passes run in tall areas, and drops at every 16 px run
     in narrow areas.
   - Repeat the rounds while they find new rows: climbs first, then descents.
   - Lose a life first, so the area restarts at its start: the game can't
     scroll back past its 256 px ring of columns. Keep the restart only if the
     game comes back to the same area.
   - Let go of all buttons and let the game settle for 90 frames: a state saved
     at a door may have Up held. Give up (LeftArea) if the game leaves the area.
2. **Solve it once, per pixel** (`ugb/lineart.py`), into kinds: sky, cloud,
   hill, rim, trunk, cloud edge, room wall, pillar, doorway, trim.
3. **Look it up every frame** by world position (`render._area_camera`).
   - Follow the camera with the scroll registers frame to frame. The game's
     counters wrap in tall areas.
   - When the camera has to be found afresh, try the counter's reading 256 px
     either way and keep the one whose tiles match the capture.
   - The map's phase (camera minus SCX) changes after doors.
4. **Never pop:**
   - Capture the first area from the title screen.
   - Keep solved areas in `cache/areas`, named by a hash of the code.
   - Recapture and merge when the player reaches parts the capture lacks: an
     area that starts on a locked screen, like a mini-boss fight.

5. **Capture what's behind doors ahead of the player.**
   - While sweeping, keep a snapshot whenever Kirby passes a door arch
     (DOOR_TILES).
   - Afterwards, `through_door` loads each snapshot and hovers him just above
     the door. A pinned spot may not be a real place: let go there and he can
     fall out of the world. It drops him, presses Up (retrying up to four
     times, because enemies knock him away), and captures the new area.
   - Each door is tried once; its result is stored and saved to disk.
6. **Two workers.** One captures the area the player is in; the other goes
   through doors ahead of the player (nearest door first) and skips areas
   already in the cache. A capture never waits behind a door.
   The screen the player is on is recorded before the life-loss restart
   (which takes the copy back to the area's start, from where a sweep may
   never get there: Float Islands' cave is reached by dropping down). The
   camera is anchored afresh from the counters after the restart, and those
   first tiles are dropped if they disagree where the sweep sees them again.
   The life-loss restart is skipped when the camera starts within 96 px of
   the area's start (the 256 px ring still holds it): a third of a capture.
   After any change to the solver or the preset the cache is unusable; refill
   it with `tools/kirby_warm.py <states...>`.
7. **Areas that loop sideways** (Castle Lololo's hall, 320 px): the game's
   camera counter jumps back by the loop's width while the scroll moves on.
   The capture takes that jump as a candidate width, keeps it only if the
   screen's tiles repeat one lap away, then folds everything to one lap and
   stops a move once nothing new appears. The solver solves three laps side by
   side and keeps the middle. The renderer looks positions up modulo the width,
   and re-finds the camera with loop-width offsets: 320 isn't a multiple of
   the map's 256 px ring, so each lap shifts the map's phase.
8. **When the screen matches the capture nowhere**, draw the per-frame way and
   recapture from the player's position. The merge places the new capture
   where its tiles agree with the old one, trying 256 px steps.

## Facts about the game (RAM and modes)

- D03B is the stage (0 Green Greens, 1 Castle Lololo, 2 Float Islands,
  3 Bubbly Clouds, 4 Mt. DeDeDe) and D03E the area.
  D039 is not the stage: writing it only renames the area.
- Play modes (D03C): 0x0D side-scrolling, 0x08 up-and-down, 0x10 Castle
  Lololo's. Title is 0x00.
- Health D086, boss health shown at D093. Writing the boss's health makes the
  game hang after the fight; beat him properly (tools: out/_kboss.py).
- Keep Kirby alive in background copies (SWEEP 'each_frame'), but not while
  entering a door. Holding his X as he lands stops him from going in.
- `tools/kirby_explore.py <state> <prefix>` explores a stage through its doors
  and saves an arrival state and a sheet for each area.

## Float Islands (stage 2)

- Play mode 0x0E (add a stage's mode to `area_key`, or nothing gets captured).
  Getting there: from the after-boss save, pin Kirby onto the warp star's
  sprite, then let the intro run; pressing Start on it is fine.
- Island slabs are 'E' (ground), not 'L': LEDGE_FROM_LINE draws ledge tiles
  above their line as a hill, and these slabs have their line at the bottom.
- The sea is in the backdrop: `_float_islands` has the sky above the
  horizon's haze (screen y 68; the haze tile is labelled sky) and a turquoise
  sea below it, with the sun's path in streaks. The sea at the bottom is 'W',
  so it shimmers with the generic water animation.
- Cloud banks are outlines only and reach the horizon: `post_solve` cuts the
  white at the haze row, then a region lying mostly under cloud outlines is
  cloud. A few banks among dense palms still come out as sky.
- The cave (area 1): ROOM_STYLE 'cave' (`_cave`, a dark stone wall), rock 'K'
  with white rims and stalactites, plank ledges 'O'.
- The same tile can mean different things here too: `7c1976` is a row of
  spikes (rock), not a palm trunk.
- Only areas 0, 5 and 6 have the sea's horizon (SEA_AREAS); the rest get
  'float_sky', the sky all the way down with a low sun.
- Water: `_underwater` (in post_solve, every stage) makes white lying under
  wave crests (WAVE_TILES, Float Islands' and Castle Lololo's) kind 12,
  painted as water by paint_tiles. Each stage needs a 'water' ramp.
- The ship (area 3) and the wooden tower (area 5): planks 'F', rails and
  posts 'O', rigging 'R' (roof isn't solid, so the white between the ropes
  stays sky), the mast 'V'; the tower's dark windows are ROOM_STYLE 'tree'.
- Kaboola's sky (area 7) scrolls by itself, so it is drawn the per-frame way
  (its capture is one screen). Cloud platforms 'M', striped pillars 'P'. No
  outlined hills on this stage: its 'hill' ramp is cloud white, which covers
  the per-frame path too; post_solve turns hill readings into cloud.
- Palm frond tiles are solid, so their white would be sky in front of a
  cloud bank: post_solve joins it to the cloud it touches.
- White between two palm trunks one tile apart solves as a tree trunk (kind
  6, drawn as bark): post_solve makes kind 6 sky on this stage.
- The ship's sea: the dotted water tile below the waves along its side
  (`4ac3b1`, SEA_FILL) is also the cabin's plank wall, so it stays 'F' and
  post_solve makes the tiles below the ship's waves (SHIP_WAVES) water.
- The cave's black between stalactites and beside rock edges
  (CAVE_VOID_TILES) is painted as the cave wall, not dark rock.
- The cobblestone columns (`0161d1`, `c7ca5e`) are the same tiles as the
  towers' walls: stone, not water.
- The wall paint (kind 8) never covers rock or ground tiles: in a cave full of
  look-alike ledges the area camera can briefly match a twin spot, and the
  wall would hide a ledge.

## Bubbly Clouds (stage 3)

- Play mode 0x0F. Getting there: as for Float Islands, from
  states/kirby_after_float.state (out/_kstage4.py, then out/_kintro.py).
- The sky is the solid grey tile (`4f8671`, 'Y' here) and white is cloud:
  the other way round from the earlier stages. `_bubbly` (post_solve) turns
  white into cloud (only in areas where the grey sky shows), makes grey that
  reaches the sky tile through cloud and balustrade tiles open sky (kind 1),
  drops the cloud-edge kind so outlines use the tiles' own shades (bold on
  the platforms), and turns hill readings into cloud or sky.
- Cloud outlines, dither and bubbles 'Z'; the temple: columns 'V',
  balustrades and friezes 'M', marble walls 'S' (the 'sign' ramp), the floor
  'F'; framed blocks 'Q'.
- Backdrop 'bubbly': a deep blue noon sky with the sun's glow in the top
  corner. Not a sun disc: behind the game's clouds it showed as a crescent.
- Spikes (SPIKE_TILES) are labelled wall 'S', so their background is the
  wall's lattice; paint_tiles draws their darker shades as steel.
- The starry sky (area 5): ROOM_STYLE 'night'. The black is space (`_night`,
  a 'night' ramp), not a room's wall; the stars (STAR_TILES) glow on it, and
  the dithered band where night meets day (DUSK_TILES) is lilac.
- White between columns can solve as a tree trunk (bark): kind 6 is sky here.
- Every area with a star field (3 to 7) is 'night'. Open sky above a dusk band
  is night too (kind 15). The moon in area 7 (MOON_TILES) shares its tiles
  with a door's arch elsewhere, so it glows only there.
- Curtains (areas 4, 7) are the columns' striped tiles: post_solve tells them
  apart by position. Anything above a rope swag (ROPE_TILES) in the same
  pixel column, through drape tiles, is cloth (kind 13, white like the
  temple), and the rope is gold (kind 14).

## Mt. DeDeDe (stage 4)

- Play mode 0x12 (the intro with the mountain is 0x11). Getting there: from
  states/kirby_after_bubbly.state with out/_kstage5b.py, then
  out/_kintro2.py.
- Indoors throughout: post_solve turns every sky, cloud and hill reading into
  plain material (no backdrop, key 'dedede'). The parquet wall is 'S' (honey
  wood), striped stone 'H' (slate blue), King DeDeDe's portraits 'C' (royal
  red), and the bosses' doors 'O' (mahogany).
- Its doors aren't DOOR_TILES, so the areas behind them aren't captured
  ahead of time yet.
- Boss rush: the doors lead back into earlier stages' areas under stage 4's
  number, and each keeps its home stage's play mode (MODE_STAGE: 0x0D Green
  Greens, 0x10 Castle Lololo, 0x0E Float Islands, 0x0F Bubbly Clouds).
  `look_stage` picks the labels (tile_keys_for) and the backdrop from that
  mode. Area labels (AREA_TILE_KEYS, INDOORS) still use the real stage.
- The hall (area 0) keeps the last route's mode when you return, so it and
  King DeDeDe's ring (area 5) stay stage 4's own (DEDEDE_OWN_AREAS). The ring
  plays in mode 0x11, which `area_key` accepts only there: 0x11 is also the
  stage's intro.
- Areas: Whispy's route 1, 6; Lololo's 2, 8; Kaboola's 3 (sea:
  DEDEDE_SEA_AREAS), 7; Kracko's 4 (under the stars: 'night', with the
  moon), 9; the ring 5.
- The ring: white wall 'S', vaulted corners 'H', posts 'V', ropes 'M'.
- Cache the hall from the stage start (states/kirby_s5_play2.state): a save
  after a boss captures only the screen around the closed doors.
- Coming through a door the play mode switches a few frames after the area:
  ugb.atlas reads the tile labels after the settle frames (generic), or a
  boss room got the hall's indoor labels.
- A beaten boss's door (CLOSED board) is wood 'O' like the others.
- Kaboola's sky on Mt. DeDeDe (4, 7) scrolls itself: SCROLLS_ITSELF makes
  area_key None, so it's drawn frame by frame. paint_tiles makes Kaboola's
  platforms' white cloud on Float Islands' look (the frame-by-frame solve has
  no post_solve).
- Don't capture from a save where Kirby is about to die: the capture runs 90
  settle frames and can catch the game-over text instead.

## Extra Game skies and the full sweep

- Extra Game backdrops (D03A = 1; `backdrop_key` adds '_extra' for
  EXTRA_BACKDROPS):
  - Green Greens: twilight;
  - Castle Lololo: a moonlit night with stars and a crescent moon;
  - Float Islands: a sunset over a dusky violet sea;
  - Bubbly Clouds: a violet-to-peach twilight with the first stars.

  Each has its own sky, cloud and water ramps. states/extra/*_x.state are
  the area saves with D03A set.
- Float Islands' sea backdrop is tall (FLOAT_H 344, horizon at FLOAT_HZ
  172). `backdrop_y` (a preset hook in Enhancer._backdrop, generic) slides
  it so its horizon sits on the game's haze tile row wherever that is on
  screen. Vertical areas scroll the horizon, and the fixed one showed the
  sun below the game's horizon.
- The sweep (out/_ksweep.py): every area, Extra flag set, captured, then
  Kirby flies pinned from one end to the other. Frames go to contact sheets
  in out/sweep, and unlabelled tiles are logged per area.
- Captures restart the area by costing a life (`_lose_life`). With no lives
  left that was game over, and the copy never moved, so Mt. DeDeDe's routes
  (played on low lives) were captured as one screen and misaligned.
  `_lose_life` tops up D089 (lives + 1) in the copy first.
- Green Greens' forest has no extra rule: under the canopy its dark blue is
  foliage and its white is sky, exactly as drawn. Fills tried there
  (`_forest_shade`, now unused) each got part of it wrong: a dark forest
  between the trunks (too much green), foliage holes, the background-trunk
  columns as sky. out/_kcmp.py checks such spots: it marks where the
  original is white but ours isn't sky, and where the original is dark blue
  but ours is sky.
- The hollow-tree rule also fills hill readings (a capture from further off
  reads the tree's inside as a hill).

## The ending

- Same stage, area and mode as the ring (4, 5, 0x11), but D160 is 0 (1 in
  play): `area_key` captures the ring only when D160 is 1, and `look_stage`
  returns ENDING (5) for the rest.
- Look: Bubbly Clouds' sky tiles and cloud edges (STAGE_TILE_KEYS[5]), the
  'ending' backdrop (the noon sky), all background white kept white, and the
  grey in cloud edges (ENDING_DITHER) is the sky behind. The credits'
  mountains are 'R'.
- Saves through the ending: states/kirby_end_NNNNN.state (frame numbers from
  the after-King-DeDeDe save; out/_kend.py).
- The credits switch the BG tile map mid-frame (LCDC bit 3) for the text
  band. PyBoy reports scroll per line but not LCDC, so `Frame.line_maps`
  (generic, every game) works out each line's map from the emulator's
  picture. Under the right map, each colour key (palette and index) lands on
  one screen colour. Lines are judged in runs sharing their scroll
  registers, the other map winning only with under a quarter of the
  conflicts. It samples every other pixel (about 2 ms a frame).
  `Enhancer.render` composes those lines from the other map's layer. No
  false switches in Pokemon Yellow, Super Mario Land or Link's Awakening
  saves.
- The credits' letters are 'X' (their paper is sky, so the text sits on the
  noon sky), the dithered bands sky 'Y', and mountains and ground 'R'. Their
  grey is the sky above the ridge (ENDING_LAND).
- Every ending scene's tiles are labelled (STAGE_TILE_KEYS[5], sorted by
  scene and shades with out/_kendtiles.py):
  - the ring as it fades (stage 4's labels, without its wall's white);
  - the balloon, ropes and grass 'Z' (their grey is the sky);
  - the castle in the basket 'M';
  - the last credit's trees 'R';
  - the box under "bye-bye" 'O' and the dark bumps 'H';
  - the Extra Game page's black-on-white tiles 'X' and the rest of its Game
    Boy drawing 'M'.
- The "balloon" is Kirby, puffed up and carrying the castle (KIRBY_BALLOON:
  his outline tiles). He's one soft pink ('kirby' ramp in 'ending', the
  in-between step), with a deep rose outline. His body is the white his
  outline closes off: away from the patch edges, at most 12000 px, and at
  least 70% of its border in his tiles. His tiles sit in the map, out of
  view, during the cloud scenes too, and a looser fill turned clouds pink.
- In the Extra Game (D03A = 1) the ending is 'ending_extra': Green Greens'
  twilight backdrop and its sky and cloud ramps. states/kirby_ending_extra.state
  is the normal ending save with D03A set.
- backdrop_key checks the ending before the title test: the title's logo
  tile is still loaded during the ending, and the title's look won.
- No status bar in the ending (`has_status_bar`, a preset hook in
  ugb.render). The credits' bands scroll apart from the mountains and read as
  one, turning parts of the sky into the pink panel as they scrolled.
  Generic: the status-bar check also skips lines drawn from the other map.
- A door standing in open sky between two trunk edges is a hollow tree
  (`_door_trees`, Whispy's route): the sky there is trunk (kind 6), and so
  are small pockets of sky beside it (a branch stub).
- The game also changes BGP mid-frame (the band's white is the sky's green
  above it), which the renderer doesn't follow either. Harmless here, since
  the band is drawn on the sky anyway.
- Area 2 (inside the clouds) is all white in the original as well: the
  solver can't tell open air from solid cloud there, so it stays white with
  blue outlines.

## Solid materials

When a level brings a new solid material (Castle Lololo's walls 'H' and marble
'M'), add it to two lists:
- the solver's solid list ('ELGKBUTSVQFOHM' in `lineart.py` and
  `tools/kirby_sheet.py`);
- the renderer's sky-fill exclusions (`render.py`, by "not a wall's mortar").

Otherwise the white in it (mortar, gaps in a balustrade) is solved or filled
as open sky, and the moving backdrop shows through it.

## Per-stage and per-area labels

The same tile can mean different things in different stages (Green Greens'
canopy fill is Castle Lololo's mountain body). STAGE_TILE_KEYS / tile_keys_for
put a stage's own labels over TILE_KEYS, in both the renderer and the solver.
AREA_TILE_KEYS does the same per (stage, area).

**White-walled interiors** (Castle Lololo's rooms): the blank white tile is
open sky outdoors but plaster indoors.
- The castle's rooms share one set of pieces: the same tiles make marble
  diamonds, striped wallpaper and a woven lattice. They are labelled for the
  whole stage (STAGE_TILE_KEYS[1]) as solid materials: marble/stripes 'S',
  columns 'V', beams and lattice strips 'M', garlands 'D', with the stage's
  colours in RAMP_BY_BACKDROP.
- Rooms with no open sky anywhere go in INDOORS. There the blank white (and
  the white inside big arches) is plaster 'D', and the dotted ground outside
  becomes a wooden floor 'F'. They get a backdrop key with no layers
  (nothing to compose each frame).
- TILE_FOLLOWS = {'D': 'S'} turns a plain tile into the material around it
  (three sides or more): the blank white is also the middle of each white
  diamond.
- NO_EAVES = 'DSM': the generic "eaves" fill (ground colour spreading one tile
  into buildings that touch the ground) would paint the plaster above a floor.
- Dark walls with arched windows (areas 3 and 7): ROOM_STYLE 'gallery' is
  stone in shadow (`_ashlar`), with tall arches showing the sky and short ones
  lit as doorways. 'arcade' makes every arch a window.
- INDOORS so far: areas 4, 8, 9, 10, 12 and 14 (the boss room). Outdoors:
  0, 1, 2, 5, 6, 11, 13, 15; 3 and 7 are galleries.
- Outdoors the game draws its own mountains and clouds, so the Lololo
  backdrop is only the sky gradient and a sun high on the right (a lilac
  halo, then a warm one: yellow straight on blue turns grey).
- A top-up capture merged with the earlier one must keep the area's tile
  labels (`_merge` sets tile_keys); without them the plaster is solved as sky.
- Areas 5 and 6: water under the wave lines (the water rule, see Float
  Islands), bubbles 'W', the turrets standing in it 'K'.

When labelling from `kirby_tiles`, read the tile in the red box, not its
surroundings: `dd3a2e` looked like ledge bricks but is a marble diamond.

## Checking tools (use them every time)

| Tool | What it checks |
|---|---|
| `tools/kirby_sheet.py <state> out.png [--debug x0] [--probe x y]` | The whole area: original, kinds, and the two blended. Judge every shape at once. |
| `tools/kirby_tiles.py <state> out.png --unlabelled` | Every unlabelled tile, with its surroundings (KT_SCALE=4 for bigger). |
| F12 in the app | A screenshot and the game state, both in `out/shots`. Start from the user's exact spot. |
| out/_kfresh.py, _kpx.py, _kalign.py, _kcross.py, _kspeed.py | One frame, one pixel's kind/tile/material, live alignment, capture against screen, and speed. |
| `tools/kirby_goto.py`, out/_kwalk.py | Get Kirby to a place and save a state there. |
| out/_kfly.py <state> out.png "right:80:a,left:60:-" | Natural play (no pinning), a frame after each step, render times. Don't pin Kirby's Y to move the camera: it can scroll past the area's edge. |
| out/_kregress.py <states...> | Re-solve areas and compare with the cached results (SAME / DIFF). |

## What fixed shapes (expect the same in later levels)

- **Implied contours:** a straight outline that stops is carried on downward
  until it meets something. Behind a cloud it carries on through the cloud.
  Afterwards, a contour line with hill on both sides becomes hill.
- **Votes, inner band against outer line:** decides hill or sky for each closed
  white region. Lines of things standing in front (FRONT_TILES: hoop legs,
  pillars) don't vote in rooms, but still count for tubes.
- **Clouds** are closed shapes with shading low inside. A cloud cut by the
  area's edge still counts if most of its pixels are in cloud tiles. A
  narrow upright slot is a hoop's inside, not a cloud.
- **Trunks:**
  - A white region walled by trunk-side tiles on both sides, and tall, is a
    trunk.
  - One cut off by the area's edge is a trunk if its other side is a trunk
    wall met on the wall's shaded side (the outline side faces outdoors).
  - A small wide shape against a trunk is a branch (Whispy's nose).
- **Rooms:** big black areas of ROOM_TILES are the back wall. Next to it, tall
  white strips are pillars, a white shape mostly enclosed by the wall is the
  doorway, and thin flat strips are trim. `paint_tiles` paints them, with a
  wall style per room (ROOM_STYLE).
- **Sky fill:** white reachable from open sky is sky, including the white at
  canopy edges. Otherwise edges come out in square steps.
- **Paint:** flat ramp steps for hills (body, rim one step darker, lit edge one
  step lighter), no noise or dither. Hill outlines in cloud-shared tiles belong
  to the hill they touch.

## Per level, in order

1. Get a state at each area's start. Check `area_key` and the mode byte (play
   is 0x0D; 0x08 in areas that scroll up and down).
2. Capture each area and look at the sheet. Fix capture first: an area too
   small means Kirby got stuck.
3. Label the unlabelled tiles (`kirby_tiles --unlabelled`), using existing
   materials where they fit.
4. Fix the solver's misreads on the sheet. Re-sheet every earlier area after
   any solver change (they must not move).
5. Give the level its own look: ramps, backdrop (`make_backdrop`, keyed in
   `backdrop_key`), room styles.
6. Run live: alignment over long flights, the speed check (about 8 ms a
   frame), and doors in and out.

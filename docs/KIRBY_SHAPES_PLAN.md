# Kirby: capturing the open background shapes

## The goal

Every background shape in Kirby's Dream Land should come out the way the artist
drew it: clouds white, domes, hoops and towers filled, and open sky clean. There
should be no squares, streaks or half-filled shapes, nothing should pop as you
scroll, and the result should be the same every time. It must also cost almost
nothing per frame.

## Why the current approach keeps failing

1. **It only sees a slice.** Each frame we only have the 256×256 piece of map
   the game has loaded. Shapes are cut off by the loading edge, the screen edge
   and the top of the level. A choice made from a slice changes as the slice
   moves, which causes pops, and it is often wrong near the edges.
2. **The shapes are open.** Domes stop above the grass. Towers run past the top
   of the level. Clouds float in front of domes, and arches sit inside them.
   Filling regions leaks through every gap, and the row and column rules misfire
   wherever two shapes meet.
3. **Tile labels are approximate.** Cloud outlines share arc tiles with hills,
   and one tile can play several roles. Any decision made per tile shows up as a
   square.
4. **It's worked out again on most frames.** That costs time, and it's another
   source of inconsistency.

Patching rules on top of a slice can't fix 1 and 2, so the plan changes the
input instead.

## The plan

### 1. Capture each area whole (the atlas)

- The level isn't kept anywhere in RAM. The ROM copy is compressed, and the game
  decompresses columns as the camera moves (checked: no raw or 2×2-block layout
  in RAM or ROM). So **let the game draw it**:
  - When an area starts, copy the emulator state into a hidden second emulator.
  - In that copy, move the camera across the area in 8 px steps by writing its
    position (`D053` follows SCX, and the high byte is still to be found), one
    step per frame.
  - The game streams each column as usual. Read the BG map and tiles back after
    each step, and assemble a world-space picture of the whole area.
- The real game is never touched. The copy is a separate emulator.
- **Found in practice:** the game decompresses the level forwards only, and the
  camera can't scroll back further than its 256 px ring of columns. A capture
  started mid-area therefore can't see the area's left part, and shapes cut
  there came out wrong (a cloud solved as a hill). So the copy first loses a
  life. The game then restarts the area at its start, and the sweep runs from
  there. The restart is kept only if the game comes back to the same area (a
  side room's restart goes back to the main area instead).
- **Driving the copy:** the game scrolls only as Kirby walks across its scroll
  point, so pinning him past it, inside a beam or inside the floor stops the
  scroll. The sweep tries each direction high and low. "Up" is tried at three
  places across the screen. Free-flight passes and drops at every 16 px are
  added for tall or narrow areas, and the whole round repeats while it finds
  new rows (the tree's climb takes five rounds, about 8 s). The capture stops
  if the game leaves the area.
- **The map's phase:** usually map pixel m shows world x ≡ m (mod 256), but
  after a door the game starts its map afresh elsewhere (back outside: camera
  at x 624 with SCX 0). The capture and the lookup both use phase = camera −
  SCX (the counter rounded to its 16 px steps).
- **Captures from a door:** the state may be saved with Up still held, which
  walks the copy straight back out. So the copy lets go of every button and
  settles for 90 frames. If it has left the area anyway, the capture is
  dropped and retried.
- **The outside beside a room:** a room's area includes strips of outdoor
  scenery, cut off at its ends. There, the double-line columns (hoop legs, the
  room's pillars) don't vote on what the shapes behind them are, but they
  still count for tubes. This is for rooms only; outdoors those lines help
  hold the open sky.
- **No pop at the start:**
  - While the title screen shows, a copy presses Start, plays the intro and
    captures the first area (SWEEP 'start_game'), so the area is solved on the
    first frame of play.
  - Solved areas are also kept in `cache/areas`, named by a hash of the solver
    and preset code, so later sessions load every visited area at once.
- **Areas that open up later:** the forest starts with a fight on a locked
  screen, so its first capture is one screen wide. When the screen, or the
  captured part beside it, shows tiles the capture lacks, the area is captured
  again from there (without the restart), merged, and solved again. This
  happens at most 8 times per area.
- **Camera Y:** D052 counts 16 px rows like D051 does columns. Rooms sit lower
  in the world (the tree's room is at y 512).
- **Rooms** (`lineart.interiors`): in an area with a big black region of room
  tiles, all that black is the back wall (quilted plum, or heartwood in the
  tree). Narrow tall white strips beside it are pillars, a white shape walled
  mostly by it is a lit doorway, and thin flat strips along it are trim.
  `paint_tiles` in the preset paints them.
- The capture reads VRAM directly rather than building a full frame. With that,
  an area takes about 1.3 s to capture and 0.1 s to solve. The worker process is
  started on the title screen so its imports are already done.
- Cost: a few hundred emulated frames per area, about 0.2–0.5 s. That runs in
  the background, during the "STAGE 1 / GREEN GREENS" intro or on area entry.
- Fallback if the camera sweep doesn't work: build the atlas from the columns
  as the player reaches them, with unseen columns marked unknown (closed off,
  as now).

### 2. Solve the shapes once per area, on the atlas

1. **Pixel classes:** white, dark line, light band (dithered or not), and land
   (ground, grass, rock). Tile labels are used only to tell land from line art.
   Every shape decision is per pixel, so nothing can come out square.
2. **Close the shapes before filling:**
   - the edges of the area (top, bottom, sides) count as walls
   - each dome leg continues straight down to the land
   - 1–2 px gaps where an outline ends beside another outline are bridged
3. **Clouds first.** They're closed shapes, shaded at the bottom. Mark them,
   then treat them as transparent, so the domes behind them are solved as if the
   clouds weren't there. That's the painter's order: domes, then arches on the
   domes, then clouds in front.
4. **Sort the closed white regions.** Each region votes over its whole border:
   touching mostly a light inner band means inside a hill; touching mostly a
   dark outer line means sky. With the area whole and closed, every region is
   complete, so the vote is reliable. It wasn't on a cut-off slice.
5. **Hoops and arches:** the white between the double lines is the tube's body.
   The space under an arch takes the kind of whatever surrounds it.
6. **Output:** a world-space map per area (sky, cloud, hill, hill's shaded rim,
   logo).

### 3. Render from the atlas

- Each frame, look up the kind at each pixel's world position, using the
  camera's world X. There's no region work per frame, so every frame of the
  same place is identical and nothing pops.
- When the game changes the map in play (broken blocks, doors), it only
  touches foreground tiles. If a line-art tile ever changes, re-solve just
  around it.

### 4. The look

- **Hills:** a flat fill with a gentle top-lit gradient. The game's inner band
  becomes one soft shaded rim tone, with no stripes. The outline stays dark.
- **Dither:** only in the 1–2 rows where a hill meets the land.
- **Clouds:** white with a lavender underside.
- **Arches:** solid tubes with their own rim.

### 5. Checking tools

- **Area sheet:** one image per area showing the original, the solved map and
  the enhanced render. Every shape in a level can then be judged at once, not
  frame by frame.
- **Consistency:** live and fresh renders must match (`tools/kirby_film.py`).
- **Snapshots:** one per area, for regressions, plus the seam and speed checks.

## To settle first (small experiments)

1. The camera's high byte, and whether writing the camera in a copy makes the
   game stream the right columns, or whether Kirby's X has to move instead.
2. RAM bytes for stage, area and area width, to know when to rebuild and how
   far to sweep.
3. Vertically scrolling areas (later stages): the same sweep, in Y.
4. Copy cost: loading a state into a second emulator and running ~300 frames.

## Order of work

1. Experiments 1–4 above.
2. The atlas builder, plus the area-sheet tool for Green Greens.
3. The shape solver on the atlas, tuned area by area using the sheets.
4. Rendering from the atlas, removing the per-frame region code.
5. The look pass, then consistency, speed and other-game checks.

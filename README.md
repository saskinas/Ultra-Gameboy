# Ultra Game Boy

Plays a Game Boy or Game Boy Color game and redraws it live in a 16-bit style,
the way the Super Game Boy added colour. There's no generative art and no
artwork is shipped. Each frame is rebuilt from the game's own video memory
(tiles, tile maps, palettes, sprites). A per-game **preset** adds knowledge where
one exists; every other game gets the **generic** enhancer.

## Setup

No ROMs are included. Dump your own cartridges and put the files in `input\`.
The short names `yellow`, `zelda`, `balloon` and `mario` match files containing
"Pokemon - Yellow", "Link's Awakening", "Balloon Kid" and "Super Mario Land".

```powershell
python -m venv .venv
```

```powershell
.venv\Scripts\python -m pip install -r requirements.txt
```

Save states (`states\`) aren't included either, because they contain the game's
memory. Make your own with F2 in the app, or with the scripts in `tools\`.

## Play

From this folder, in PowerShell. The first argument is a ROM in `input\`, by
short name or path:

```powershell
.venv\Scripts\python -m ugb.app yellow --state states\pallet_town.state
```

```powershell
.venv\Scripts\python -m ugb.app zelda --state states\zelda_mabe.state
```

```powershell
.venv\Scripts\python -m ugb.app balloon
```

```powershell
.venv\Scripts\python -m ugb.app mario
```

Leave out `--state` to boot the game from its title screen. The in-game save goes
to the ROM's `.ram` file in `input\`, and the previous one is kept as `.ram.bak`.

| Key | Action |
| --- | --- |
| Arrows | D-pad |
| Z / X | A / B |
| Enter / Backspace | Start / Select |
| Tab | Switch between enhanced and original |
| G | Generic shading strength: subtle / strong |
| Space (hold) | Fast-forward |
| F2 / F4 | Quick save / load state (`states\quick.state`) |
| F12 | Screenshot, original next to enhanced, saved in `out\shots` |
| Esc | Quit (prints how many audio gaps there were) |

## How it works

- `ugb/gb.py` reads both VRAM banks, both tile maps with their colour
  attributes, the palettes, the sprite table and the per-scanline scroll and
  window registers. Sprites come from the table the picture was actually drawn
  with, which is the previous frame's. Plain Game Boy games run in the Color's
  compatibility mode, where palettes can't be read. Their colours are learned by
  comparing decoded shades with the emulator's picture. `compose_original`
  rebuilds the normal frame from all of this as a check.
- `ugb/render.py` works on the 256×256 background map, kept between frames.
  When the game writes new tiles, only on-screen bands around them are redrawn.
  Texture is anchored to world position, so the window layer (menus, dialogue)
  matches the map under it.
  - **Generic, any game:** checkerboard dither becomes the in-between colour.
    Shapes enclosed by near-black outlines get soft volume lit from the top left,
    with warm highlights and cool shadows. Inner outlines take a dark tint of
    their neighbours. Sprites get the same treatment from their own palettes.
  - **Ramp presets (Pokémon Yellow):** tile number → material (ground, lawn,
    tall grass, water, tree, roof, wall, window…) painted with chosen colour
    ramps, lit objects, shadows, animated water and flowers, sprites coloured
    per character, and SNES-style text boxes.
  - **Game-colour presets (Link's Awakening DX):** the game's own colours, with
    light added by material: sphere-lit trees, cylinder-lit posts, roof
    gradients, ground texture, drop shadows. Tiles are recognised by a hash of
    their pixels, because the game moves graphics between VRAM slots.
- `ugb/presets/` holds `pokemon_yellow.py`, `zelda_ladx.py` and `generic.py`.
  Presets are chosen by cartridge title.
- `ugb/app.py` streams sound through an audio callback and paces the emulator by
  it, so a slow frame never cuts the music.

## Status

- **Pokémon Yellow:** every town, route and interior is labelled. The outdoor
  tileset has three tiles left (ledges, tile 01, a round sign on Route 8). All 16
  indoor graphics sets are labelled with indoor materials (floor, cloth, machines,
  furniture, earth, plants), except black voids and cave holes. Indigo Plateau and
  Route 23 (tileset 23) are still generic. Battles use the game's colours with
  SNES-style text boxes, and only framed text gets the box style.
- **Link's Awakening DX:** only the tiles around Tarin and Marin's house in
  Mabe Village are labelled. Everything else is generic.
- **Super Mario Land:** World 1 has a 16-bit platformer preset: gradient sky,
  filled outline hills, grassy ground over earth, gold ? blocks and coins, pipes
  lit as cylinders, soft clouds. Other worlds use the generic look until labelled
  (`tools/hash_sheet.py` makes the labelling sheet).
- **Balloon Kid:** generic only, as the no-preset test. For plain Game Boy
  games, generic mode also gives volume to compact shapes on the lightest colour
  (trees, bushes, hills) and lights large terrain from above with depth. Press G
  for the stronger setting.
- 60 fps with about 10–15 ms per frame. Link's Awakening's room-to-room scroll
  spikes to about 45 ms (a few dropped frames, no audio gaps).

**Jumping around Pokémon Yellow:** `tools/pokewarp.py` teleports with memory
edits. It writes the destination map and position, then jumps into the game's
own `EnterMap` routine from its overworld loop. `python tools/pokewarp.py
states\pallet_town.state survey` saves a state for every town and route in
`states\warp_XX.state`. `tools/survey_render.py` then renders them all and lists
the tiles that still have no material. `python tools/pokewarp.py
states\pallet_town.state indoor` does the same for all 191 interiors.
`tools/survey_tiles.py` makes a labelling sheet per graphics set, and
`tools/indoor_render.py` shows interiors original next to enhanced.

`tools/` holds the helpers used to build presets: scripted play (`drive.py`),
tile sheets and grids (`tilesheet.py`, `mapgrid.py`, `hashgrid.py`),
before/after renders (`rendertest.py`) and checks and timing (`spikes.py`,
`wincheck.py`, `menucheck.py`, `apptest.py`). Set `UGB_ROM=zelda` (or `balloon`)
to point any tool at another game.

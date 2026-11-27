# Ultra Game Boy

Plays a Game Boy or Game Boy Color game and redraws it live in a 16-bit style,
the way the Super Game Boy added colour. There's no generative art and no
artwork is shipped. Each frame is rebuilt from the game's own video memory
(tiles, tile maps, palettes, sprites). A per-game **preset** adds knowledge where
one exists; every other game gets the **generic** enhancer.

## Download for Windows (no setup)

Get **UltraGameBoy-windows.zip** from the
[latest release](https://github.com/saskinas/Ultra-Gameboy/releases/latest),
unzip it, double-click **Ultra Game Boy.exe** and choose a game file you own
(.gb or .gbc). Windows may say it protected your PC, because the app isn't
signed: click **More info**, then **Run anyway**. "How to play.txt" in the
folder has the controls. No games are included.

The rest of this page is for running it from source.

## Setup

No ROMs are included. Dump your own cartridges and put the files in `input\`.
The short names `yellow`, `zelda`, `balloon`, `mario` and `kirby` match files
containing "Pokemon - Yellow", "Link's Awakening", "Balloon Kid", "Super Mario
Land" and "Kirby's Dream Land".

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
| E | Eye candy on / off (presets with effects, like Kirby's) |
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
  - **Status bars, any game:** a band of up to 40 lines at the top or bottom
    that doesn't scroll with the level (a full-width window, or BG lines with
    their own scroll) is a status bar. Its text tiles get a SNES-style panel
    with cream lettering and a drop shadow, and a ticking counter redraws only
    its own tiles.
  - **Ramp presets (Pokémon Yellow):** tile number → material (ground, lawn,
    tall grass, water, tree, roof, wall, window…) painted with chosen colour
    ramps, lit objects, shadows, animated water and flowers, sprites coloured
    per character, and SNES-style text boxes.
  - **Game-colour presets (Link's Awakening DX):** the game's own colours, with
    light added by material: sphere-lit trees, cylinder-lit posts, roof
    gradients, ground texture, drop shadows. Tiles are recognised by a hash of
    their pixels, because the game moves graphics between VRAM slots.
  - **Line-art presets (Kirby's Dream Land):** `ugb/atlas.py` captures a
    whole area in a hidden copy of the game, and `ugb/lineart.py` sorts its
    outlined white shapes into sky, clouds, hills, trunks, walls and water.
    The renderer looks each pixel up by its world position. Solved areas are
    kept in `cache\` and rebuilt when the code changes.
  - **Mid-frame tile-map switches, any game:** `Frame.line_maps` works out
    which tile map each line was drawn from, by checking against the
    emulator's picture.
  - **Eye candy:** per-pixel effects (twinkle, glints, light ripples, sway),
    drifting motes and sprite trails, switched on by a preset's
    `EYE_CANDY`, `MOTES` and `TRAIL_SPRITES`.
- `ugb/presets/` holds `pokemon_yellow.py`, `zelda_ladx.py`,
  `mario_land.py`, `kirby_dream_land.py` and `generic.py`. Presets are chosen
  by cartridge title.
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
- **Super Mario Land:** all four worlds have a 16-bit platformer preset:
  gradient sky, filled outline hills, grassy ground over earth, gold ? blocks and
  coins, pipes lit as cylinders, clouds, the sea in World 2, stone and vines in
  World 3, bamboo and clouds in World 4. `tools/mario_levels.py` jumps to every
  level by memory edits on the title screen; `tools/hash_sheet.py` makes the
  labelling sheets.
- **Kirby's Dream Land:** the whole game has its own look
  (`docs/KIRBY_PLAN.md`, notes in `docs/KIRBY_TECHNIQUES.md`):
  - Green Greens' morning;
  - Castle Lololo's warm stone and arched galleries;
  - Float Islands' sea, ship and caves;
  - Bubbly Clouds' temple and starry sky;
  - Mt. DeDeDe's hall, boss rush and ring;
  - the ending and credits.

  The Extra Game has twilight and night skies for every stage. Eye candy
  (`docs/KIRBY_EYE_CANDY_PLAN.md`): twinkling stars, sea glints, underwater
  light, swaying grass, drifting motes and a warp star trail.
  `tools/kirby_warm.py` fills the area cache, and `tools/kirby_demo.py`
  records a demo video.
- **Balloon Kid:** generic only, as the no-preset test. For plain Game Boy
  games, generic mode also gives volume to compact shapes on the lightest colour
  (trees, bushes, hills) and lights large terrain from above with depth. Press G
  for the stronger setting.
- Tiles whose graphics cycle in place (flashing blocks, waterfalls) are kept as
  a flipbook, one finished drawing per animation frame.
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

## Build the Windows app

```powershell
.venv\Scripts\python -m pip install pyinstaller
```

```powershell
.venv\Scripts\python tools\build_windows.py
```

This makes `dist\Ultra Game Boy\` and `dist\UltraGameBoy-windows.zip`. The
app starts with a game picker (`ugb/launcher.py`) and keeps quick saves,
screenshots and the area cache in `%APPDATA%\Ultra Game Boy`. The
instructions for players are in `docs/PLAYERS.md`.

`tools/` holds the helpers used to build presets: scripted play (`drive.py`),
tile sheets and grids (`tilesheet.py`, `mapgrid.py`, `hashgrid.py`),
before/after renders (`rendertest.py`) and checks and timing (`spikes.py`,
`wincheck.py`, `menucheck.py`, `apptest.py`). Set `UGB_ROM=zelda` (or `balloon`)
to point any tool at another game.

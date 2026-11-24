"""Teleport in Pokémon Yellow with memory edits, to check locations without playing.

    python tools/pokewarp.py <in.state> <map> [x y] [--out out.state] [--shot name]
    python tools/pokewarp.py <in.state> survey      # every town and route, one sheet
    python tools/pokewarp.py <in.state> indoor      # every indoor map (0x25-0xF7)

How it works: write the destination map, coordinates and the map-view pointer to
RAM, then wait for the game's own overworld loop and jump into EnterMap (0x01D7),
the routine the game runs after every door and warp. Doing it from the overworld
loop means interrupts are on and nothing is half-finished.

The view pointer needs the destination map's width, which is only known after
the map is loaded, so the first jump loads the map and the second places the
player properly.
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import numpy as np   # noqa: E402
from PIL import Image, ImageDraw   # noqa: E402
from pyboy import PyBoy   # noqa: E402

from ugb.roms import rom_path   # noqa: E402

# pret/pokeyellow symbols
ENTER_MAP = 0x01D7
OVERWORLD_LOOP = 0x0242
W_OVERWORLD_MAP = 0xC6E8
W_CUR_MAP = 0xD35D
W_VIEW_PTR = 0xD35E
W_Y, W_X = 0xD360, 0xD361
W_YBLOCK, W_XBLOCK = 0xD362, 0xD363
W_HEIGHT, W_WIDTH = 0xD367, 0xD368
W_TILESET = 0xD366

# Gen 1 map numbers for the outdoor maps
MAPS = {
    0x00: 'Pallet Town', 0x01: 'Viridian City', 0x02: 'Pewter City', 0x03: 'Cerulean City',
    0x04: 'Lavender Town', 0x05: 'Vermilion City', 0x06: 'Celadon City', 0x07: 'Fuchsia City',
    0x08: 'Cinnabar Island', 0x09: 'Indigo Plateau', 0x0A: 'Saffron City',
    **{0x0C + i: 'Route %d' % (i + 1) for i in range(25)},
}


def _place(pb, map_id, x, y):
    m = pb.memory
    jumped = []

    def jump(_):
        # Write the destination only here: if the old map's scripts ran with the
        # new map number in RAM, they could read the wrong data and hang.
        if not jumped:
            m[W_CUR_MAP] = map_id
            m[W_Y], m[W_X] = y, x
            m[W_YBLOCK], m[W_XBLOCK] = y & 1, x & 1
            w = m[W_WIDTH]
            ptr = W_OVERWORLD_MAP + 7 + w + (w + 6) * (y >> 1) + (x >> 1)
            m[W_VIEW_PTR], m[W_VIEW_PTR + 1] = ptr & 0xFF, ptr >> 8
            pb.register_file.PC = ENTER_MAP
            jumped.append(True)

    pb.hook_register(0, OVERWORLD_LOOP, jump, None)
    for _ in range(600):
        pb.tick(1, False)
        if jumped:
            break
    pb.hook_deregister(0, OVERWORLD_LOOP)
    pb.tick(90, True)   # let the map load and the screen fade in
    return bool(jumped)


def warp(pb, map_id, x=None, y=None):
    """Load `map_id` with the player at (x, y) in 16-px steps (default: map centre)."""
    if not _place(pb, map_id, x or 0, y or 0):
        raise RuntimeError('never reached the overworld loop (in a menu or battle?)')
    m = pb.memory
    if x is None:
        x = m[W_WIDTH]      # width is in 2x2-step blocks, so this is the middle
    if y is None:
        y = m[W_HEIGHT]
    _place(pb, map_id, x, y)
    return m[W_CUR_MAP], m[W_TILESET], m[W_WIDTH], m[W_HEIGHT]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    opts = dict(a[2:].split('=', 1) for a in sys.argv[1:] if a.startswith('--') and '=' in a)
    pb = PyBoy(rom_path('yellow'), window='null', cgb=True, sound_emulated=False)
    with open(args[0], 'rb') as f:
        pb.load_state(f)
    pb.tick(2, True)
    base = os.path.join(HERE, 'states', '_warp_base.state')
    with open(base, 'wb') as f:
        pb.save_state(f)
    if args[1] in ('survey', 'indoor'):
        indoor = args[1] == 'indoor'
        cells = []
        todo = ({m: 'map %02X' % m for m in range(0x25, 0xF8)} if indoor else MAPS)
        for mid, name in todo.items():
            with open(base, 'rb') as f:
                pb.load_state(f)
            try:
                info = warp(pb, mid)
            except RuntimeError as e:
                print(name, e)
                continue
            if not (0 < info[2] <= 60 and 0 < info[3] <= 60) or info[1] > 24:
                print(name, 'skipped: unused map number')
                continue
            img = pb.screen.ndarray[:, :, :3].copy()
            cells.append((name, info, img))
            print('%-16s map %02X tileset %d size %dx%d' % (name, info[0], info[1], info[2], info[3]))
            prefix = 'indoor' if indoor else 'warp'
            with open(os.path.join(HERE, 'states', '%s_%02x.state' % (prefix, mid)), 'wb') as f:
                pb.save_state(f)
        cols = 6
        rows = (len(cells) + cols - 1) // cols
        sheet = Image.new('RGB', (cols * 170, rows * 160), (20, 20, 28))
        d = ImageDraw.Draw(sheet)
        for i, (name, info, img) in enumerate(cells):
            x, y = (i % cols) * 170, (i // cols) * 160
            sheet.paste(Image.fromarray(img), (x + 5, y + 14))
            d.text((x + 5, y + 2), '%02X %s (ts %d)' % (info[0], name, info[1]), fill=(230, 230, 230))
        name = 'survey_indoor.png' if indoor else 'survey.png'
        sheet.save(os.path.join(HERE, 'out', name))
        print('wrote out/%s' % name)
        return
    mid = int(args[1], 0)
    x = int(args[2]) if len(args) > 3 else None
    y = int(args[3]) if len(args) > 3 else None
    info = warp(pb, mid, x, y)
    print('map %02X tileset %d size %dx%d' % info)
    if 'out' in opts:
        with open(opts['out'], 'wb') as f:
            pb.save_state(f)
    Image.fromarray(pb.screen.ndarray[:, :, :3]).save(
        os.path.join(HERE, 'out', 'warp_%s.png' % opts.get('shot', '%02x' % mid)))


if __name__ == '__main__':
    main()

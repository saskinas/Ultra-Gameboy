"""Render the warp survey states enhanced, and list unlabelled tiles with context.

    python tools/survey_render.py          (after: python tools/pokewarp.py <state> survey)

Writes out/survey_enhanced.png (original | enhanced per location) and
out/unlabelled.png: each unlabelled overworld tile, enlarged, with the 3x3 tiles
around one place it appears, and how many visible cells use it.
"""
import glob
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import numpy as np   # noqa: E402
from PIL import Image, ImageDraw   # noqa: E402
from pyboy import PyBoy   # noqa: E402

from ugb import presets   # noqa: E402
from ugb.gb import Frame   # noqa: E402
from ugb.render import Enhancer   # noqa: E402
from ugb.roms import rom_path   # noqa: E402
from tools.pokewarp import MAPS   # noqa: E402

pb = PyBoy(rom_path('yellow'), window='null', cgb=True, sound_emulated=False)
preset = presets.for_title(pb.cartridge_title)
labelled = set(preset.TILESETS[0])
cells, counts, example = [], Counter(), {}
for path in sorted(glob.glob(os.path.join(HERE, 'states', 'warp_*.state'))):
    mid = int(os.path.basename(path)[5:7], 16)
    with open(path, 'rb') as fh:
        pb.load_state(fh)
    en = Enhancer(preset)
    for _ in range(4):
        pb.tick(1, True)
        f = Frame(pb)
    out = en.render(f)
    cells.append((MAPS.get(mid, hex(mid)), pb.screen.ndarray[:, :, :3].copy(), out))
    if pb.memory[preset.RAM['tileset']] != 0:
        continue
    m = f.maps[f.bg_map()]
    oy, ox = f.scy[0] // 8, f.scx[0] // 8
    rgb = f.bgpal[0][f.layer(f.bg_map())[0]]
    for r in range(18):
        for c in range(20):
            t = int(m[(oy + r) % 32, (ox + c) % 32])
            if t < preset.UI_FIRST_TILE and t not in labelled:
                counts[t] += 1
                if t not in example:
                    ys = (np.arange((oy + r - 1) * 8, (oy + r + 2) * 8)) % 256
                    xs = (np.arange((ox + c - 1) * 8, (ox + c + 2) * 8)) % 256
                    example[t] = (rgb[np.ix_(ys, xs)], MAPS.get(mid, ''))

# sheet of locations
cols = 4
rows = (len(cells) + cols - 1) // cols
sheet = Image.new('RGB', (cols * 330, rows * 160), (20, 20, 28))
d = ImageDraw.Draw(sheet)
for i, (name, o, e) in enumerate(cells):
    x, y = (i % cols) * 330, (i // cols) * 160
    sheet.paste(Image.fromarray(o), (x + 4, y + 14))
    sheet.paste(Image.fromarray(e), (x + 166, y + 14))
    d.text((x + 4, y + 2), name, fill=(230, 230, 230))
sheet.save(os.path.join(HERE, 'out', 'survey_enhanced.png'))

# unlabelled tiles with context
items = counts.most_common()
cols = 8
rows = (len(items) + cols - 1) // cols
S = 4
cw, chh = 24 * S + 8, 24 * S + 22
sheet = Image.new('RGB', (cols * cw, max(rows, 1) * chh), (255, 240, 240))
d = ImageDraw.Draw(sheet)
for i, (t, n) in enumerate(items):
    ctx, where = example[t]
    im = Image.fromarray(ctx.astype(np.uint8)).resize((24 * S, 24 * S), Image.NEAREST)
    x, y = (i % cols) * cw, (i // cols) * chh
    sheet.paste(im, (x + 4, y + 18))
    d.rectangle([x + 4 + 8 * S, y + 18 + 8 * S, x + 4 + 16 * S - 1, y + 18 + 16 * S - 1], outline=(255, 0, 0))
    d.text((x + 4, y + 2), '%02X x%d %s' % (t, n, where[:10]), fill=(160, 0, 0))
sheet.save(os.path.join(HERE, 'out', 'unlabelled.png'))
print(len(items), 'unlabelled tile ids:', ' '.join('%02X:%d' % kv for kv in items))

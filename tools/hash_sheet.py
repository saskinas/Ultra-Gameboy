"""Labelling sheet for presets keyed by pixel hash (TILE_KEYS).

    UGB_ROM=mario python tools/hash_sheet.py out/sheet.png state1 state2 ...

Collects every background tile on screen across the given states, shows each one
enlarged with the 3x3 tiles around one place it appears, its 24-bit pixel hash
(as used by TILE_KEYS), how often it appears, and its current label.
"""
import hashlib
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np   # noqa: E402
from PIL import Image, ImageDraw   # noqa: E402
from pyboy import PyBoy   # noqa: E402

from ugb import presets   # noqa: E402
from ugb.gb import Frame   # noqa: E402
from ugb.roms import rom_path   # noqa: E402

out_path, states = sys.argv[1], sys.argv[2:]
pb = PyBoy(rom_path(), window='null', cgb=True, sound_emulated=False)
preset = presets.for_title(pb.cartridge_title)
labels = getattr(preset, 'TILE_KEYS', {})
counts, example = Counter(), {}
for st in states:
    pb.load_state(open(st, 'rb'))
    for _ in range(3):
        pb.tick(1, True)
        f = Frame(pb)
    idx, pal, _, ids, bank = f.layer(f.bg_map())
    shade = np.array([255, 170, 85, 0], np.uint8)
    for y in range(144):
        pass
    by, bx, _, _ = np.broadcast_arrays(*f.screen_coords())
    seen = set()
    for r in range(18):
        y = r * 8
        R = (by[y, 0] // 8) % 32
        for c in range(20):
            C = ((bx[y, 0] + c * 8) // 8) % 32
            if (R, C) in seen:
                continue
            seen.add((R, C))
            h = int(hashlib.blake2b(f.tiles[bank[R, C], ids[R, C]].tobytes(), digest_size=3).hexdigest(), 16)
            counts[h] += 1
            if h not in example:
                ys = np.arange((R - 1) * 8, (R + 2) * 8) % 256
                xs = np.arange((C - 1) * 8, (C + 2) * 8) % 256
                example[h] = (shade[idx[np.ix_(ys, xs)]], int(ids[R, C]) & 0xFF)
items = counts.most_common()
S, cols = 3, 12
cw, chh = 24 * S + 6, 24 * S + 16
rows = (len(items) + cols - 1) // cols
sheet = Image.new('RGB', (cols * cw, rows * chh), (255, 240, 240))
d = ImageDraw.Draw(sheet)
for i, (h, n) in enumerate(items):
    ctx, tid = example[h]
    x, y = (i % cols) * cw, (i // cols) * chh
    sheet.paste(Image.fromarray(ctx).resize((24 * S, 24 * S), Image.NEAREST), (x + 3, y + 13))
    d.rectangle([x + 3 + 8 * S, y + 13 + 8 * S, x + 3 + 16 * S - 1, y + 13 + 16 * S - 1], outline=(255, 0, 0))
    d.text((x + 3, y + 1), '%06x %s x%d' % (h, labels.get(h, '?'), n), fill=(160, 0, 0))
sheet.save(out_path)
print(len(items), 'tiles;', 'unlabelled:', sum(1 for h, _ in items if h not in labels))
print(' '.join('%06x:%d' % (h, n) for h, n in items))

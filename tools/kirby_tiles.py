"""Labelling sheet for a whole Kirby area: every distinct tile in the area's atlas
(ugb.atlas) shown with the tiles around one place it appears, its hash, count
and current label.

    python tools/kirby_tiles.py <state> out/tiles.png [--unlabelled]
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np   # noqa: E402
from PIL import Image, ImageDraw   # noqa: E402

from ugb import atlas   # noqa: E402
from ugb.presets import kirby_dream_land as kirby   # noqa: E402
from ugb.roms import rom_path   # noqa: E402

at = atlas.capture(rom_path('kirby'), open(sys.argv[1], 'rb').read(), kirby.SWEEP)
cnt = Counter(at.hashes[at.hashes >= 0].tolist())
where = {}
for (r, c), h in np.ndenumerate(at.hashes):
    if h >= 0 and h not in where:
        where[h] = (r, c)
items = [(h, n) for h, n in cnt.most_common() if '--unlabelled' not in sys.argv or h not in (at.tile_keys or kirby.TILE_KEYS)]
S, cols = (int(os.environ.get("KT_SCALE", 3))), 12
cw, chh = 24 * S + 6, 24 * S + 16
rows = (len(items) + cols - 1) // cols
sheet = Image.new('RGB', (cols * cw, max(rows, 1) * chh), (255, 240, 240))
d = ImageDraw.Draw(sheet)
img = (255 - at.shade.astype(int) * 80).clip(0, 255).astype(np.uint8)
pad = np.pad(img, 8, constant_values=255)
for i, (h, n) in enumerate(items):
    r, c = where[h]
    ctx = pad[r * 8:r * 8 + 24, c * 8:c * 8 + 24]
    x, y = (i % cols) * cw, (i // cols) * chh
    sheet.paste(Image.fromarray(ctx).resize((24 * S, 24 * S), Image.NEAREST), (x + 3, y + 13))
    d.rectangle([x + 3 + 8 * S, y + 13 + 8 * S, x + 3 + 16 * S - 1, y + 13 + 16 * S - 1], outline=(255, 0, 0))
    d.text((x + 3, y + 1), '%06x %s x%d' % (h, (at.tile_keys or kirby.TILE_KEYS).get(h, '?'), n), fill=(160, 0, 0))
sheet.save(sys.argv[2])
print(len(items), 'tiles')

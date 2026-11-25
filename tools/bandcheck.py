"""Check that redrawing in bands gives the same result as drawing the map whole.

    python tools/bandcheck.py <state>

Draws the visible map once as a whole, then redraws bands whose edges cut through
it at every row and column offset, and reports pixels that differ. Catches
effects that leak across band edges (e.g. a fill that wraps around the band).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np   # noqa: E402
from PIL import Image   # noqa: E402
from pyboy import PyBoy   # noqa: E402

from ugb import presets   # noqa: E402
from ugb.gb import Frame   # noqa: E402
from ugb.render import Enhancer, MARGIN   # noqa: E402
from ugb.roms import rom_path   # noqa: E402

pb = PyBoy(rom_path(), window='null', cgb=True, sound_emulated=False)
pb.load_state(open(sys.argv[1], 'rb'))
pb.tick(2, True)
f = Frame(pb)
p = presets.for_title(pb.cartridge_title)
en = Enhancer(p)
en.render(f)                                        # sets tileset, tables
which = f.bg_map()
st = en._layers[which]
idx, pal, prio, ids, bank = f.layer(which)
gs = en.game_state(f)
table = p.TILESETS.get(gs['tileset'])
tkeys, tmat = en._materials(f, f.maps[which], ids, bank, table)
en._off = (0, 0)
en._render_into(st, f, idx, pal, tkeys, tmat, table, 0, 32, 0, 32)
whole = st.out.copy()
oy, ox = f.scy[0] // 8, f.scx[0] // 8
worst, total = (0, None), 0
for dr in range(0, 18, 2):                          # bands starting at many rows
    st.out[:] = whole
    en._render_into(st, f, idx, pal, tkeys, tmat, table, oy + dr - MARGIN, 4 + 2 * MARGIN, 0, 32)
    for dc in range(0, 20, 3):                      # and blocks at many columns
        en._render_into(st, f, idx, pal, tkeys, tmat, table, oy + dr - MARGIN, 4 + 2 * MARGIN,
                        ox + dc - MARGIN, 4 + 2 * MARGIN)
    d = np.abs(st.out - whole).max(-1) > 24
    n = int(d.sum())
    total += n
    if n > worst[0]:
        ys = (np.arange(144) + oy * 8) % 256
        xs = (np.arange(160) + ox * 8) % 256
        worst = (n, np.concatenate([whole[np.ix_(ys, xs)], st.out[np.ix_(ys, xs)],
                                    (d[np.ix_(ys, xs)][..., None] * 255).repeat(3, -1)], 1))
print('differing pixels across all bands:', total, 'worst band:', worst[0])
if worst[1] is not None:
    Image.fromarray(np.clip(worst[1], 0, 255).astype(np.uint8)).resize((480 * 3, 144 * 3), Image.NEAREST).save('out/bandcheck.png')

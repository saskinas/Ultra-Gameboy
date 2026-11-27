"""Area sheet: capture an area whole, solve its line art, and save one image with
the original (top), the solved kinds (middle) and the shapes coloured (bottom).

    python tools/kirby_sheet.py <state> out/sheet.png
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np   # noqa: E402
from PIL import Image   # noqa: E402

from ugb import atlas, lineart   # noqa: E402
from ugb.presets import kirby_dream_land as kirby   # noqa: E402
from ugb.render import M   # noqa: E402
from ugb.roms import rom_path   # noqa: E402

state = open(sys.argv[1], 'rb').read()
at = atlas.capture(rom_path('kirby'), state, kirby.SWEEP)
mt = np.full(at.hashes.shape, M['?'], np.uint8)
for k, v in (at.tile_keys or kirby.TILE_KEYS).items():
    mt[at.hashes == k] = M[v]
mat = np.repeat(np.repeat(mt, 8, 0), 8, 1)
seen = np.repeat(np.repeat(at.hashes >= 0, 8, 0), 8, 1)
if '--probe' in sys.argv:
    i = sys.argv.index('--probe')
    lineart.solve.probe = (int(sys.argv[i + 2]), int(sys.argv[i + 1]))
t = time.perf_counter()
edge = np.repeat(np.repeat(np.isin(at.hashes, kirby.LINE_EDGE_TILES), 8, 0), 8, 1)
front = None       # (as solve_area: rooms only)
if np.isin(at.hashes, getattr(kirby, 'ROOM_TILES', [])).sum() >= 12:
    front = np.repeat(np.repeat(np.isin(at.hashes, getattr(kirby, 'FRONT_TILES', [])), 8, 0), 8, 1)
kind = lineart.solve(at.shade, mat, seen, M, edge, front)
if getattr(kirby, 'ROOM_TILES', None):      # rooms behind doors, as solve_area does
    room = np.repeat(np.repeat(np.isin(at.hashes, kirby.ROOM_TILES), 8, 0), 8, 1)
    land = np.isin(mat, [M[c] for c in 'ELGKBUTSVQFOHMD']) & seen
    kind = lineart.interiors(kind, at.shade, room, land)
if hasattr(kirby, 'post_solve'):     # (as solve_atlas does)
    kind = kirby.post_solve(kind, at, mat, M)
print('area %d x %d, solved in %.2fs' % (at.width, at.height, time.perf_counter() - t))
orig = np.stack([(255 - at.shade.astype(int) * 80).clip(0, 255)] * 3, -1).astype(np.uint8)
pal = np.array([[60, 60, 60], [120, 170, 255], [255, 255, 255], [70, 190, 90], [0, 0, 0], [40, 120, 60],
                [150, 100, 50], [200, 200, 230], [90, 50, 120], [240, 200, 220], [255, 220, 120],
                [230, 160, 90]], np.uint8)     # (8 room wall, 9 pillar, 10 doorway, 11 trim)
kd = pal[kind]
mix = orig.copy()
m = kind > 0
mix[m] = (orig[m] * 0.35 + kd[m] * 0.65).astype(np.uint8)
Image.fromarray(np.concatenate([orig, kd, mix], 0)).resize((at.width * 2, at.height * 6), Image.NEAREST).save(sys.argv[2])
if '--debug' in sys.argv:
    inner, outer, lab, curtain = lineart.solve.debug
    x0 = int(sys.argv[sys.argv.index('--debug') + 1]) if len(sys.argv) > sys.argv.index('--debug') + 1 else 0
    main = lab > 0
    dbg = orig.copy()
    dbg[main] = (200, 220, 255)
    dbg[inner & main] = (0, 160, 0)
    dbg[outer & main] = (220, 0, 0)
    dbg[curtain] = (255, 0, 255)
    reg = lab[:, x0:x0 + 540]
    for r in np.unique(reg[reg > 0]):
        m = lab == r
        if m.sum() > 300:
            print('region', r, 'size', int(m.sum()), 'inner', int((inner & m).sum()), 'outer', int((outer & m).sum()))
    print('main region inner', int((inner & main).sum()), 'outer', int((outer & main).sum()))
    Image.fromarray(dbg[:, x0:x0 + 540]).resize((540 * 3, at.height * 3), Image.NEAREST).save('out/ksheet_dbg.png')

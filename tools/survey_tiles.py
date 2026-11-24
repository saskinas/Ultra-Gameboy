"""Per-tileset labelling sheets from the indoor warp survey.

    python tools/survey_tiles.py            (after: python tools/pokewarp.py <state> indoor)

For each graphics set (tilesets that share graphics are grouped), writes
out/ts_<name>.png: a few of its maps (original), then every tile used on screen,
enlarged with the 3x3 tiles around one place it appears, its id, how often it is
seen, and its current material ('?' if none).
"""
import glob
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import numpy as np   # noqa: E402
from PIL import Image, ImageDraw   # noqa: E402
from pyboy import PyBoy   # noqa: E402

from ugb import presets   # noqa: E402
from ugb.gb import Frame   # noqa: E402
from ugb.roms import rom_path   # noqa: E402

GROUPS = {   # Gen 1 tilesets that share graphics
    'house12': (1, 4), 'mart_center': (2, 6), 'forest': (3,), 'gym': (5, 7), 'house': (8,),
    'gate': (9, 10, 12), 'underground': (11,), 'ship': (13, 14), 'cemetery': (15,), 'interior': (16,),
    'cavern': (17,), 'lobby': (18,), 'mansion': (19,), 'lab': (20,), 'club': (21,), 'facility': (22,),
}

def main():
    pb = PyBoy(rom_path('yellow'), window='null', cgb=True, sound_emulated=False)
    preset = presets.for_title(pb.cartridge_title)
    by_ts = defaultdict(list)
    for path in sorted(glob.glob(os.path.join(HERE, 'states', 'indoor_*.state'))):
        with open(path, 'rb') as fh:
            pb.load_state(fh)
        for _ in range(3):
            pb.tick(1, True)
            f = Frame(pb)
        ts = pb.memory[preset.RAM['tileset']]
        by_ts[ts].append((os.path.basename(path)[7:9], f, pb.screen.ndarray[:, :, :3].copy()))

    only = sys.argv[1:]
    for gname, tss in GROUPS.items():
        if only and gname not in only:
            continue
        maps = [m for t in tss for m in by_ts.get(t, [])]
        if not maps:
            continue
        table = preset.TILESETS.get(tss[0], {})
        counts, example = Counter(), {}
        for mid, f, _ in maps:
            m = f.maps[f.bg_map()]
            oy, ox = f.scy[0] // 8, f.scx[0] // 8
            idx = f.layer(f.bg_map())[0]
            rgb = np.array([[255, 255, 255], [170, 170, 170], [85, 85, 85], [0, 0, 0]], np.uint8)[idx]
            for r in range(18):
                for c in range(20):
                    t = int(m[(oy + r) % 32, (ox + c) % 32])
                    if t >= preset.UI_FIRST_TILE:
                        continue
                    counts[t] += 1
                    if t not in example:
                        ys = np.arange((oy + r - 1) * 8, (oy + r + 2) * 8) % 256
                        xs = np.arange((ox + c - 1) * 8, (ox + c + 2) * 8) % 256
                        example[t] = (rgb[np.ix_(ys, xs)], mid)
        items = sorted(counts.items())
        S = 3
        cw, chh = 24 * S + 6, 24 * S + 16
        cols = 12
        prev = [img for _, _, img in maps[:6]]
        rows = (len(items) + cols - 1) // cols
        W = cols * cw
        Hh = 150 * ((len(prev) + 5) // 6) + rows * chh + 10
        sheet = Image.new('RGB', (max(W, 6 * 165), Hh), (255, 240, 240))
        d = ImageDraw.Draw(sheet)
        for i, img in enumerate(prev):
            sheet.paste(Image.fromarray(img), ((i % 6) * 165, (i // 6) * 150))
        y0 = 150 * ((len(prev) + 5) // 6) + 6
        for i, (t, n) in enumerate(items):
            ctx, mid = example[t]
            im = Image.fromarray(ctx).resize((24 * S, 24 * S), Image.NEAREST)
            x, y = (i % cols) * cw, y0 + (i // cols) * chh
            sheet.paste(im, (x + 3, y + 13))
            d.rectangle([x + 3 + 8 * S, y + 13 + 8 * S, x + 3 + 16 * S - 1, y + 13 + 16 * S - 1], outline=(255, 0, 0))
            d.text((x + 3, y + 1), '%02X %s x%d' % (t, table.get(t, '?'), n), fill=(160, 0, 0))
        sheet.save(os.path.join(HERE, 'out', 'ts_%s.png' % gname))
        print('%-12s tilesets %-10s maps %3d tiles %3d unlabelled %3d' % (
            gname, tss, len(maps), len(items), sum(1 for t, _ in items if t not in table)))


if __name__ == '__main__':
    main()

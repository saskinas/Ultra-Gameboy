"""Original | enhanced for sample indoor maps, two per graphics set (after the indoor survey)."""
import glob, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from PIL import Image, ImageDraw
from pyboy import PyBoy
from ugb import presets
from ugb.gb import Frame
from ugb.render import Enhancer
from ugb.roms import rom_path
from tools.survey_tiles import GROUPS
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pb = PyBoy(rom_path('yellow'), window='null', cgb=True, sound_emulated=False)
preset = presets.for_title(pb.cartridge_title)
want = sys.argv[1:] or list(GROUPS)
seen, cells = {}, []
for path in sorted(glob.glob(os.path.join(HERE, 'states', 'indoor_*.state'))):
    with open(path, 'rb') as fh:
        pb.load_state(fh)
    pb.tick(1, True)
    ts = pb.memory[preset.RAM['tileset']]
    g = next((k for k, v in GROUPS.items() if ts in v), None)
    if g not in want or seen.get(g, 0) >= 2:
        continue
    seen[g] = seen.get(g, 0) + 1
    en = Enhancer(preset)
    for _ in range(4):
        pb.tick(1, True); f = Frame(pb)
    cells.append(('%s %s' % (g, os.path.basename(path)[7:9]), pb.screen.ndarray[:, :, :3].copy(), en.render(f)))
cols = 3
rows = (len(cells) + cols - 1) // cols
sheet = Image.new('RGB', (cols * 330, rows * 160), (20, 20, 28))
d = ImageDraw.Draw(sheet)
for i, (name, o, e) in enumerate(cells):
    x, y = (i % cols) * 330, (i // cols) * 160
    sheet.paste(Image.fromarray(o), (x + 4, y + 14)); sheet.paste(Image.fromarray(e), (x + 166, y + 14))
    d.text((x + 4, y + 2), name, fill=(230, 230, 230))
sheet.save(os.path.join(HERE, 'out', 'indoor_enhanced.png'))
print(len(cells), 'maps')

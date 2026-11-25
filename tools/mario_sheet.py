"""Original | enhanced for the Super Mario Land run states (two columns)."""
import glob, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from PIL import Image
from pyboy import PyBoy
from ugb import presets
from ugb.gb import Frame
from ugb.render import Enhancer
from ugb.roms import rom_path
pb = PyBoy(rom_path('mario'), window='null', cgb=True, sound_emulated=False)
cells = []
pattern = sys.argv[2] if len(sys.argv) > 2 else 'states/mario_run_*.state'
for path in sorted(glob.glob(pattern))[:12]:
    pb.load_state(open(path, 'rb'))
    en = Enhancer(presets.for_title(pb.cartridge_title))
    for _ in range(12):
        pb.tick(1, True); out = en.render(Frame(pb))
    cells.append(np.concatenate([pb.screen.ndarray[:, :, :3], np.full((144, 2, 3), 20, np.uint8), out], 1))
if len(cells) % 2:
    cells.append(np.zeros_like(cells[0]))
rows = [np.concatenate(cells[i:i + 2], 1) for i in range(0, len(cells), 2)]
img = np.concatenate([np.concatenate([r, np.full((4, r.shape[1], 3), 20, np.uint8)], 0) for r in rows], 0)
Image.fromarray(img).save(sys.argv[1] if len(sys.argv) > 1 else 'out/mario_sheet_render.png')

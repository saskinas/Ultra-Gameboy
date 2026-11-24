"""Step a battle state with A presses; render original|enhanced at a few points."""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from pyboy import PyBoy
from PIL import Image
from ugb.roms import rom_path
from ugb.gb import Frame
from ugb.render import Enhancer
from ugb import presets
pb = PyBoy(rom_path('yellow'), window='null', cgb=True, sound_emulated=False)
pb.load_state(open(sys.argv[1], 'rb'))
en = Enhancer(presets.for_title(pb.cartridge_title))
rows = []
script = sys.argv[2].split()
for tok in script:
    kind, n = tok.split(':')
    for _ in range(int(n)):
        if kind == 'a':
            pb.button_press('a')
        pb.tick(1, True)
        f = Frame(pb)
        out = en.render(f)
        if kind == 'a':
            pb.button_release('a')
    if kind == 'shot':
        rows.append(np.concatenate([pb.screen.ndarray[:, :, :3], np.full((144, 4, 3), 20, np.uint8), out], 1))
    if kind == 'save':
        with open('states/battle_%s.state' % n, 'wb') as fh:
            pb.save_state(fh)
cols = 2
h = (len(rows) + 1) // cols
grid = [np.concatenate(rows[i * cols:(i + 1) * cols] + [np.zeros_like(rows[0])] * (cols - len(rows[i * cols:(i + 1) * cols])), 1) for i in range(h)]
Image.fromarray(np.concatenate(grid, 0)).resize((324 * cols * 2, 144 * h * 2), Image.NEAREST).save('out/battle_frames.png')
print(len(rows), 'shots, in battle:', pb.memory[0xD056])

"""Boot Yellow and render title -> new game -> Oak's intro, original | enhanced."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from PIL import Image
from pyboy import PyBoy
from ugb import presets
from ugb.gb import Frame
from ugb.render import Enhancer
from ugb.roms import rom_path
pb = PyBoy(rom_path('yellow'), window='null', cgb=True, sound_emulated=False)
en = Enhancer(presets.for_title(pb.cartridge_title))
rows, fr = [], 0
plan = {300: None, 620: 'shot', 680: 'start', 760: 'shot', 780: 'a', 860: 'shot', 880: 'a',
        1000: 'shot', 1030: 'a', 1120: 'shot', 1140: 'a', 1240: 'shot', 1260: 'a', 1380: 'shot'}
for fr in range(1, 1400):
    act = plan.get(fr)
    if act in ('start', 'a'):
        pb.button_press(act)
    pb.tick(1, True)
    if act in ('start', 'a'):
        pb.button_release(act)
    out = en.render(Frame(pb))
    if act == 'shot':
        rows.append(np.concatenate([pb.screen.ndarray[:, :, :3], np.full((144, 4, 3), 20, np.uint8), out], 1))
grid = [np.concatenate(rows[i:i + 2], 1) if i + 1 < len(rows) else np.concatenate([rows[i], np.zeros_like(rows[i])], 1)
        for i in range(0, len(rows), 2)]
Image.fromarray(np.concatenate(grid, 0)).resize((648 * 2, 144 * 2 * len(grid)), Image.NEAREST).save('out/intro.png')
print(len(rows), 'shots')

"""Like filmstrip, but each cell is original | enhanced. Script tokens: dir:frames."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from PIL import Image
from pyboy import PyBoy
from ugb import presets
from ugb.gb import Frame
from ugb.render import Enhancer
from ugb.roms import rom_path
st, script, every, outp = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
pb = PyBoy(rom_path(), window='null', cgb=True, sound_emulated=False)
pb.load_state(open(st, 'rb'))
en = Enhancer(presets.for_title(pb.cartridge_title))
for _ in range(3):
    pb.tick(1, True); en.render(Frame(pb))
shots, n = [], 0
for tok in script.split():
    d, k = tok.split(':')
    pb.button_press(d)
    for i in range(int(k)):
        pb.tick(1, True); out = en.render(Frame(pb)); n += 1
        if n % every == 0:
            shots.append(np.concatenate([pb.screen.ndarray[:, :, :3], np.full((144, 2, 3), 20, np.uint8), out], 1))
    pb.button_release(d)
cols = 2
rows = (len(shots) + cols - 1) // cols
sheet = np.full((rows * 148, cols * 326, 3), 20, np.uint8)
for i, s in enumerate(shots):
    y, x = (i // cols) * 148, (i % cols) * 326
    sheet[y:y + 144, x:x + 322] = s
Image.fromarray(sheet).resize((sheet.shape[1] * 2, sheet.shape[0] * 2), Image.NEAREST).save(outp)
print(len(shots), 'frames')

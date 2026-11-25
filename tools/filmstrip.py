"""Hold a direction and save consecutive enhanced frames as a contact sheet.

    python tools/filmstrip.py <state> <dir> <frames> <every> <out.png>
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from PIL import Image
from pyboy import PyBoy
from ugb import presets
from ugb.gb import Frame
from ugb.render import Enhancer
from ugb.roms import rom_path
st, d, n, every, outp = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
pb = PyBoy(rom_path(), window='null', cgb=True, sound_emulated=False)
pb.load_state(open(st, 'rb'))
en = Enhancer(presets.for_title(pb.cartridge_title))
for _ in range(3):
    pb.tick(1, True); en.render(Frame(pb))
pb.button_press(d)
shots = []
for i in range(n):
    pb.tick(1, True)
    out = en.render(Frame(pb))
    if i % every == 0:
        shots.append(out)
pb.button_release(d)
cols = 4
rows = (len(shots) + cols - 1) // cols
sheet = np.full((rows * 148, cols * 164, 3), 20, np.uint8)
for i, s in enumerate(shots):
    y, x = (i // cols) * 148, (i % cols) * 164
    sheet[y:y + 144, x:x + 160] = s
Image.fromarray(sheet).resize((sheet.shape[1] * 2, sheet.shape[0] * 2), Image.NEAREST).save(outp)
print(len(shots), 'frames')

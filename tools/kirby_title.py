"""Boot Kirby's Dream Land to the title screen, save states/kirby_title.state and
render original | enhanced to out/kirby_title.png (a few frames apart)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np   # noqa: E402
from PIL import Image   # noqa: E402
from pyboy import PyBoy   # noqa: E402

from ugb import presets   # noqa: E402
from ugb.gb import Frame   # noqa: E402
from ugb.render import Enhancer   # noqa: E402
from ugb.roms import rom_path   # noqa: E402

pb = PyBoy(rom_path('kirby'), window='null', cgb=True, sound_emulated=False)
if os.path.exists('states/kirby_title.state') and '--boot' not in sys.argv:
    pb.load_state(open('states/kirby_title.state', 'rb'))
else:
    pb.tick(300, True)
    pb.save_state(open('states/kirby_title.state', 'wb'))
en = Enhancer(presets.for_title(pb.cartridge_title))
rows = []
for i in range(120):
    pb.tick(1, True)
    o = en.render(Frame(pb))
    if i % 40 == 39:
        rows.append(np.concatenate([pb.screen.ndarray[:, :, :3], o], 1))
Image.fromarray(np.concatenate(rows, 0)).resize((640, 288 * len(rows)), Image.NEAREST).save('out/kirby_title.png')

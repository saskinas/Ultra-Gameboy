"""Walk in tall grass until a wild battle, use the first move, and time every frame.

    python tools/attackcheck.py <state in grass> [out.png]

Prints per-frame enhancer time during the attack, how many frames changed the
palette, and saves original | enhanced for frames in the attack animation.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np   # noqa: E402
from PIL import Image   # noqa: E402
from pyboy import PyBoy   # noqa: E402

from ugb import presets   # noqa: E402
from ugb.gb import Frame   # noqa: E402
from ugb.render import Enhancer   # noqa: E402
from ugb.roms import rom_path   # noqa: E402

pb = PyBoy(rom_path('yellow'), window='null', cgb=True, sound_emulated=False)
pb.load_state(open(sys.argv[1], 'rb'))
en = Enhancer(presets.for_title(pb.cartridge_title))
W_BATTLE = 0xD056


def frame():
    pb.tick(1, True)
    f = Frame(pb)
    t = time.perf_counter()
    out = en.render(f)
    return f, out, time.perf_counter() - t


def press(b, n=6, wait=30):
    pb.button_press(b)
    for _ in range(n):
        frame()
    pb.button_release(b)
    for _ in range(wait):
        frame()


# pace up and down in the grass until a battle starts
for i in range(60):
    if pb.memory[W_BATTLE]:
        break
    press('up' if i % 2 else 'down', 16, 4)
print('in battle:', pb.memory[W_BATTLE])
with open('states/wild_battle.state', 'wb') as fh:
    pb.save_state(fh)
for _ in range(8):                     # through "Wild X appeared!" / "Go! Y!"
    press('a', 6, 60)
press('a', 6, 40)                      # FIGHT
press('a', 6, 10)                      # first move
times, shots, pal_changes, prev_pal = [], [], 0, None
for i in range(240):
    f, out, dt = frame()
    times.append(dt)
    if prev_pal is not None and not np.array_equal(prev_pal, f.bgpal):
        pal_changes += 1
    prev_pal = f.bgpal.copy()
    if i % 6 == 0 and len(shots) < 16:
        shots.append(np.concatenate([pb.screen.ndarray[:, :, :3], np.full((144, 2, 3), 20, np.uint8), out], 1))
t = np.array(times) * 1000
print('attack frames %d, palette changed on %d of them' % (len(t), pal_changes))
print('render ms: mean %.1f p95 %.1f max %.1f; frames over 16 ms: %d' % (
    t.mean(), np.percentile(t, 95), t.max(), (t > 16).sum()))
cols = 2
rows = (len(shots) + 1) // 2
sheet = np.full((rows * 148, cols * 326, 3), 20, np.uint8)
for i, s in enumerate(shots):
    sheet[(i // 2) * 148:(i // 2) * 148 + 144, (i % 2) * 326:(i % 2) * 326 + 322] = s
Image.fromarray(sheet).resize((sheet.shape[1] * 2, sheet.shape[0] * 2), Image.NEAREST).save(
    sys.argv[2] if len(sys.argv) > 2 else 'out/attack.png')

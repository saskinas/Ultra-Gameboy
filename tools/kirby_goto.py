"""Move Kirby to a world X (memory edits: pin his screen position so the camera
scrolls), drop him to the ground there and optionally press Up (doors).

    python tools/kirby_goto.py <state> <world x> <out.state> [--door]
Saves the resulting state and out/kirby_goto.png (before | after).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np   # noqa: E402
from PIL import Image   # noqa: E402
from pyboy import PyBoy   # noqa: E402

from ugb.presets import kirby_dream_land as kirby   # noqa: E402
from ugb.roms import rom_path   # noqa: E402

src, target, dst = sys.argv[1], int(sys.argv[2]), sys.argv[3]
pb = PyBoy(rom_path('kirby'), window='null', cgb=True, sound_emulated=False)
pb.load_state(open(src, 'rb'))
m = pb.memory
sw = {'pin_x': 0xD05C, 'pin_y': 0xD05D, 'y': 0x18, 'left': 0x40, 'right': 0x50}
shots = [pb.screen.ndarray[:, :, :3].copy()]
# fly high toward the target, letting the camera scroll
for i in range(3000):
    x = kirby.camera_x(m) + m[sw['pin_x']]
    if abs(x - target) < 4:
        break
    d = 'right' if x < target else 'left'
    pb.button_press(d)
    m[sw['pin_y']] = sw['y']
    if abs(x - target) > 40:      # far: hold him past the scroll threshold
        m[sw['pin_x']] = sw[d]
    if i % 8 == 0:
        pb.button_press('a')
    if i % 8 == 4:
        pb.button_release('a')
    pb.tick(1, True)
    pb.button_release(d)
print('reached world x', kirby.camera_x(m) + m[sw['pin_x']], 'camera', kirby.camera_x(m))
pb.button_release('a')
shots.append(pb.screen.ndarray[:, :, :3].copy())
pb.tick(12, True)
pb.button_press('b')          # exhale (a puffed-up Kirby can't use doors) and land
pb.tick(4, True)
pb.button_release('b')
pb.tick(60, True)
shots.append(pb.screen.ndarray[:, :, :3].copy())
pb.button_press('down')       # swallow anything in his mouth
pb.tick(6, True)
pb.button_release('down')
pb.tick(30, True)
shots.append(pb.screen.ndarray[:, :, :3].copy())
if '--door' in sys.argv:
    pb.button_press('up')
    pb.tick(6, True)
    pb.button_release('up')
    pb.tick(150, True)
shots.append(pb.screen.ndarray[:, :, :3].copy())
pb.save_state(open(dst, 'wb'))
Image.fromarray(np.concatenate(shots, 1)).resize((320 * len(shots), 288), Image.NEAREST).save('out/kirby_goto.png')

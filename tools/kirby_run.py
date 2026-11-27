"""Scripted run through Kirby's Dream Land: hold right, tap A to float.

    python tools/kirby_run.py <start.state> <prefix> [frames]

Saves states/<prefix>_NN.state every 240 frames, out/<prefix>.png (a strip of
screens) and prints RAM bytes in D000-DFFF that changed only a few times, as
candidates for stage and room numbers.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np   # noqa: E402
from PIL import Image   # noqa: E402
from pyboy import PyBoy   # noqa: E402

from ugb.roms import rom_path   # noqa: E402

start, prefix = sys.argv[1], sys.argv[2]
frames = int(sys.argv[3]) if len(sys.argv) > 3 else 2400
TAP = int(sys.argv[4]) if len(sys.argv) > 4 else 8   # frames between A taps (flying)
pb = PyBoy(rom_path('Kirby'), window='null', cgb=True, sound_emulated=False)
pb.load_state(open(start, 'rb'))
ram = lambda: np.array([pb.memory[a] for a in range(0xD000, 0xE000)], np.uint8)
prev = ram()
changes = np.zeros(0x1000, int)
hist = {}
shots = []
pb.button_press('right')
for i in range(frames):
    if i % TAP == 0:
        pb.button_press('a')
    if i % TAP == TAP // 2:
        pb.button_release('a')
    if i % 240 == 30:           # spit out anything swallowed (can't fly with a full mouth)
        pb.button_press('b')
    if i % 240 == 34:
        pb.button_release('b')
    if i % 200 == 100:          # sometimes press Up (doors)
        pb.button_press('up')
    if i % 200 == 110:
        pb.button_release('up')
    pb.tick(1, True)
    if i % 4 == 0:
        r = ram()
        d = r != prev
        changes += d
        for a in np.nonzero(d)[0]:
            hist.setdefault(a, []).append((i, int(r[a])))
        prev = r
    if i % 240 == 239:
        n = i // 240
        pb.save_state(open('states/%s_%02d.state' % (prefix, n), 'wb'))
        shots.append(pb.screen.ndarray[:, :, :3].copy())
cols = 5
rows = (len(shots) + cols - 1) // cols
sheet = np.full((rows * 144, cols * 160, 3), 255, np.uint8)
for k, s in enumerate(shots):
    sheet[(k // cols) * 144:(k // cols + 1) * 144, (k % cols) * 160:(k % cols + 1) * 160] = s
Image.fromarray(sheet).save('out/%s.png' % prefix)
for a in np.nonzero((changes >= 1) & (changes <= 6))[0]:
    print('%04X' % (0xD000 + a), hist[a])

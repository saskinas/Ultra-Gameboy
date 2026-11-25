"""Jump to every Super Mario Land level by memory edit and record a run through each.

    python tools/mario_levels.py

For each level: on the title screen set the win count ($FF9A, so START begins at the
selected level), hWorldAndLevel ($FFB4) and hLevelIndex ($FFE4), press START, then
hold right and jump regularly, saving a state every 150 frames (states/mario_L<world><level>_NN.state).
Writes out/mario_levels_orig.png with one frame per level.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np   # noqa: E402
from PIL import Image   # noqa: E402
from pyboy import PyBoy   # noqa: E402

from ugb.roms import rom_path   # noqa: E402

pb = PyBoy(rom_path('mario'), window='null', cgb=True, sound_emulated=True)
pb.tick(300, False)
import io
title = io.BytesIO()
pb.save_state(title)                             # the title screen
firsts = []
for k in range(12):
    world, level = k // 3 + 1, k % 3 + 1
    title.seek(0)
    pb.load_state(title)
    m = pb.memory
    # After two wins the game lets START begin at the selected level (expert mode);
    # it then takes the normal level-start path, which loads the world's tiles.
    m[0xFF9A] = 2
    m[0xC0E1] = 2
    m[0xFFB4] = (world << 4) | level
    m[0xFFE4] = k
    pb.button_press('start'); pb.tick(5, False); pb.button_release('start')
    pb.tick(240, True)
    m[0xDA15] = 0x09
    pb.button_press('right')
    shots = 0
    for i in range(1500):
        if i % 44 == 10:
            pb.button_press('a')
        if i % 44 == 34:
            pb.button_release('a')
        pb.tick(1, True)
        if i % 150 == 149:
            with open('states/mario_L%d%d_%02d.state' % (world, level, i // 150), 'wb') as fh:
                pb.save_state(fh)
            if i // 150 == 2:
                firsts.append(pb.screen.ndarray[:, :, :3].copy())
            shots += 1
    pb.button_release('right')
    print('level %d-%d: hud %02x index %d lives %02x' % (world, level, m[0xFFB4], m[0xFFE4], m[0xDA15]))
grid = np.concatenate([np.concatenate(firsts[i:i + 3], 1) for i in range(0, 12, 3)], 0)
Image.fromarray(grid).save('out/mario_levels_orig.png')

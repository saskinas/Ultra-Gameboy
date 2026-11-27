"""Capture a Kirby's Dream Land area whole (ugb.atlas) and save it as an image.

    python tools/kirby_atlas.py <state> out/area.png
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np   # noqa: E402
from PIL import Image   # noqa: E402

from ugb import atlas   # noqa: E402
from ugb.presets import kirby_dream_land as kirby   # noqa: E402
from ugb.roms import rom_path   # noqa: E402

state = open(sys.argv[1], 'rb').read()
t = time.perf_counter()
at = atlas.capture(rom_path('kirby'), state, kirby.SWEEP)
print('captured %d x %d px from world (%d, %d) in %.2fs' % (at.width, at.height, at.x0, at.y0,
                                                             time.perf_counter() - t))
print('unseen tiles:', int((at.hashes < 0).sum()))
img = (255 - at.shade.astype(np.int32) * 80).clip(0, 255).astype(np.uint8)
img[np.repeat(np.repeat(at.hashes < 0, 8, 0), 8, 1)] = 200
Image.fromarray(img).resize((at.width * 2, at.height * 2), Image.NEAREST).save(sys.argv[2])

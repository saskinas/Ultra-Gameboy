"""Play Kirby's Dream Land with the flying script and save a strip of enhanced frames.

    python tools/kirby_film.py <state> <frames> <every> out.png

Also compares each saved frame with a freshly made renderer (as seamcheck does)
and prints how many pixels differ, to find leftovers from incremental redraws.
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


def main():
    state, frames, every, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    walk = '--walk' in sys.argv     # walk right and hop now and then, instead of flying
    pb = PyBoy(rom_path('kirby'), window='null', cgb=True, sound_emulated=False)
    pb.load_state(open(state, 'rb'))
    preset = presets.for_title(pb.cartridge_title)
    en = Enhancer(preset)
    shots = []
    pb.button_press('right')
    for i in range(frames):
        tap = 90 if walk else 8
        if i % tap == 0:
            pb.button_press('a')
        if i % tap == 4:
            pb.button_release('a')
        if i % 240 == 30:
            pb.button_press('b')
        if i % 240 == 34:
            pb.button_release('b')
        pb.tick(1, True)
        f = Frame(pb)
        o = en.render(f)
        time.sleep(0.004 if not en._areas else 0)          # (give the area worker time, as in play)
        if i % every == every - 1 and en._areas:
            fresh = Enhancer(preset)
            fresh.frame_no = en.frame_no - 1
            fresh._bd_key, fresh._bd_layers = en._bd_key, en._bd_layers
            fresh._bd_cam, fresh._bd_scroll = en._bd_cam.copy(), en._bd_scroll
            fresh._areas = en._areas            # (solved whole areas: shared, not recomputed)
            ref = fresh.render(f)
            d = np.abs(o.astype(int) - ref.astype(int)).max(-1) > 24
            print(i, 'differ', int(d.sum()))
            if d.sum() > 30 or not walk:
                shots.append(np.concatenate([o, ref], 1))
    if not shots:
        shots.append(np.concatenate([o, ref], 1))
    cols = 2
    rows = (len(shots) + cols - 1) // cols
    sheet = np.zeros((rows * 144, cols * 320, 3), np.uint8)
    for k, s in enumerate(shots):
        sheet[(k // cols) * 144:(k // cols + 1) * 144, (k % cols) * 320:(k % cols + 1) * 320] = s
    Image.fromarray(sheet).save(out)


if __name__ == '__main__':
    main()

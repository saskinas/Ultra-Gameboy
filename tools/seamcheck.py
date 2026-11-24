"""Find leftovers from incremental redraws: compare the live render with a fresh one.

    python tools/seamcheck.py <state> "<script>"

Script tokens: up:16 / down:16 / left:16 / right:16 (hold, frames), a:N (press A,
wait N frames), w:N (wait). Every 8 frames the incremental render is compared with
a brand-new Enhancer's render of the same frame (ignoring animated water/flowers).
Writes out/seams.png with the worst frame: incremental | fresh | difference.
"""
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

pb = PyBoy(rom_path(), window='null', cgb=True, sound_emulated=False)
pb.load_state(open(sys.argv[1], 'rb'))
preset = presets.for_title(pb.cartridge_title)
live = Enhancer(preset)
worst = (0, None)
fr = 0
bad_frames = []


def step(n, btn=None):
    global fr, worst
    if btn:
        pb.button_press(btn)
    for i in range(n):
        if btn == 'a' and i == 4:
            pb.button_release('a')
        pb.tick(1, True)
        f = Frame(pb)
        out = live.render(f)
        fr += 1
        if fr % 8 == 0:
            fresh = Enhancer(preset)
            fresh.frame_no = live.frame_no - 1
            ref = fresh.render(f)
            d = np.abs(out.astype(int) - ref.astype(int)).max(-1) > 24
            # animated tiles can legitimately differ by shimmer phase
            n_bad = int(d.sum())
            if n_bad > 30:
                bad_frames.append((fr, n_bad))
            if n_bad > worst[0]:
                worst = (n_bad, np.concatenate([out, ref, (d[..., None] * 255).repeat(3, -1).astype(np.uint8)], 1))
    if btn and btn != 'a':
        pb.button_release(btn)


for tok in sys.argv[2].split():
    k, n = tok.split(':')
    n = int(n)
    if k == 'w':
        step(n)
    elif k == 'a':
        step(max(n, 6), 'a')
    else:
        step(n, k)

print('frames', fr, 'frames with >30 differing px:', len(bad_frames), bad_frames[:12])
if worst[1] is not None:
    Image.fromarray(worst[1]).resize((480 * 3, 144 * 3), Image.NEAREST).save('out/seams.png')
    print('worst', worst[0])

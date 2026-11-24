"""Find frames where sprites in our rebuilt frame disagree with the emulator's picture.

    python tools/blinkcheck.py <state> "<script>"     (script as in seamcheck: a:N, w:N, up:N ...)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from PIL import Image
from pyboy import PyBoy
from ugb.gb import Frame, compose_original
from ugb.roms import rom_path
pb = PyBoy(rom_path(), window='null', cgb=True, sound_emulated=False)
pb.load_state(open(sys.argv[1], 'rb'))
bad, fr, shots = [], 0, []
def step(n, btn=None):
    global fr
    if btn: pb.button_press(btn)
    for i in range(n):
        if btn == 'a' and i == 4: pb.button_release('a')
        pb.tick(1, True); f = Frame(pb); fr += 1
        mine, _ = compose_original(f)
        scr = pb.screen.ndarray[:, :, :3]
        d = (np.abs(mine.astype(int) - scr.astype(int)).max(-1) > 40)
        if d.sum() > 20:
            bad.append((fr, int(d.sum()), f.oam_exact))
            if len(shots) < 3:
                shots.append(np.concatenate([scr, mine, (d[..., None] * 255).repeat(3, -1).astype(np.uint8)], 1))
    if btn and btn != 'a': pb.button_release(btn)
for tok in sys.argv[2].split():
    k, n = tok.split(':'); n = int(n)
    step(n) if k == 'w' else step(max(n, 6), 'a') if k == 'a' else step(n, k)
print('frames', fr, 'mismatching frames', len(bad), bad[:20])
if shots:
    Image.fromarray(np.concatenate(shots, 0)).resize((480 * 2, 144 * 2 * len(shots)), Image.NEAREST).save('out/blink.png')

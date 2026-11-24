"""From Oak stopping you at the tall grass, mash A until the rival battle starts; save it."""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pyboy import PyBoy
from PIL import Image
from ugb.roms import rom_path
pb = PyBoy(rom_path('yellow'), window='null', cgb=True, sound_emulated=True)
pb.load_state(open('states/oak.state', 'rb'))
W_BATTLE = 0xD056
for step in range(3000):
    if step % 3 == 0:
        pb.button_press('a'); pb.tick(4, False); pb.button_release('a')
    # nudge down now and then so Link... the player walks out of the lab if needed
    if step % 97 == 50:
        pb.button_press('down'); pb.tick(16, False); pb.button_release('down')
    pb.tick(12, False)
    if pb.memory[W_BATTLE]:
        pb.tick(240, True)
        break
print('in battle:', pb.memory[W_BATTLE], 'after steps', step)
pb.tick(1, True)
Image.fromarray(pb.screen.ndarray[:, :, :3]).save('out/battle0.png')
with open('states/battle.state', 'wb') as f:
    pb.save_state(f)

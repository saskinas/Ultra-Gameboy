"""Open the start menu and check the map around it renders the same as before the menu."""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from pyboy import PyBoy
from ugb.roms import rom_path
from PIL import Image
from ugb.gb import Frame
from ugb.render import Enhancer
from ugb import presets
pb=PyBoy(rom_path(),window='null',cgb=True,sound_emulated=False)
pb.load_state(open(sys.argv[1] if len(sys.argv)>1 else 'states/pallet_town.state','rb'))
en=Enhancer(presets.for_title(pb.cartridge_title))
for _ in range(30): pb.tick(1,True); before=en.render(Frame(pb))
pb.button_press('start'); pb.tick(6,True); pb.button_release('start')
worst=0; shot=None
for i in range(40):
    pb.tick(1,True); f=Frame(pb); out=en.render(f)
    raw=pb.screen.ndarray[:,:,:3]
    if f.window_mask().any() or i==39:
        # compare only where the original game picture is unchanged (outside the menu)
        same=(np.abs(raw.astype(int)-ref.astype(int)).max(-1)==0) if 'ref' in dir() else None
    ref0=raw
d=(np.abs(out.astype(int)-before.astype(int)).max(-1)>0)
print('window on at end:', f.window_mask().any(), 'changed px vs before menu:', d.sum())
Image.fromarray(np.concatenate([before,out,(d[...,None]*255).repeat(3,-1).astype(np.uint8)],1)).resize((480*3,144*3),Image.NEAREST).save('out/menucheck.png')

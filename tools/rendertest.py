"""Render a save state through the enhancer and save original | enhanced side by side."""
import sys, os, time; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from pyboy import PyBoy
from ugb.roms import rom_path
from PIL import Image
from ugb.gb import Frame, compose_original
from ugb.render import Enhancer
from ugb import presets
pb=PyBoy(rom_path(),window='null',cgb=True,sound_emulated=False)
pb.load_state(open(sys.argv[1],'rb')); pb.tick(int(sys.argv[3]) if len(sys.argv)>3 else 1)
en=Enhancer(presets.for_title(pb.cartridge_title))
for _ in range(12): pb.tick(1, True); f=Frame(pb)
t=time.time(); out=en.render(f); t1=time.time(); out=en.render(f); t2=time.time()
print('first %.0fms cached %.0fms'%((t1-t)*1000,(t2-t1)*1000))
orig,_=compose_original(f)
Image.fromarray(np.concatenate([orig, np.full((144,6,3),20,np.uint8), out],1)).resize((326*4,144*4),Image.NEAREST).save(sys.argv[2])

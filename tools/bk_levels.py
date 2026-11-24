"""Balloon Kid: original | generic subtle | generic strong."""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from pyboy import PyBoy
from PIL import Image
from ugb.roms import rom_path
from ugb.gb import Frame, compose_original
from ugb.render import Enhancer
from ugb import presets
pb=PyBoy(rom_path('balloon'),window='null',cgb=True,sound_emulated=False)
pb.load_state(open(sys.argv[1] if len(sys.argv)>1 else 'states/bk3.state','rb'))
for _ in range(12): pb.tick(1,True); f=Frame(pb)
outs=[compose_original(f)[0]]
for lv in (1,2):
    en=Enhancer(presets.for_title(pb.cartridge_title)); en.generic_level=lv; outs.append(en.render(f))
gap=np.full((144,4,3),20,np.uint8)
Image.fromarray(np.concatenate([outs[0],gap,outs[1],gap,outs[2]],1)).resize((488*3,432),Image.NEAREST).save('out/bk_levels.png')

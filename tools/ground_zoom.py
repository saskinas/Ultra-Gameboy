"""Close-ups of speckled ground: Balloon Kid turf (subtle, strong) and Link's Awakening path."""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from pyboy import PyBoy
from PIL import Image
from ugb.roms import rom_path
from ugb.gb import Frame, compose_original
from ugb.render import Enhancer
from ugb import presets
rows=[]
for rom, st, crop in (('balloon','states/bk3.state',(96,144,0,96)), ('zelda','states/zelda_mabe.state',(64,128,0,96))):
    pb=PyBoy(rom_path(rom),window='null',cgb=True,sound_emulated=False)
    pb.load_state(open(st,'rb'))
    for _ in range(12): pb.tick(1,True); f=Frame(pb)
    y0,y1,x0,x1=crop
    outs=[compose_original(f)[0]]
    for lv in (1,2):
        en=Enhancer(presets.for_title(pb.cartridge_title)); en.generic_level=lv; outs.append(en.render(f))
    gap=np.full((y1-y0,3,3),20,np.uint8)
    rows.append(np.concatenate([outs[0][y0:y1,x0:x1],gap,outs[1][y0:y1,x0:x1],gap,outs[2][y0:y1,x0:x1]],1))
img=np.concatenate([rows[0], np.full((3,rows[0].shape[1],3),20,np.uint8), rows[1]],0)
Image.fromarray(img).resize((img.shape[1]*5,img.shape[0]*5),Image.NEAREST).save('out/ground_zoom.png')

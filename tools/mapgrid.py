"""Render the full 256x256 BG layer with tile ids overlaid, to label materials in context."""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from pyboy import PyBoy
from ugb.roms import rom_path
from PIL import Image, ImageDraw
from ugb.gb import Frame
pb=PyBoy(rom_path(),window='null',cgb=True,sound_emulated=False)
pb.load_state(open(sys.argv[1],'rb')); pb.tick(1)
f=Frame(pb)
idx,pal,_,ids,_=f.layer(f.bg_map())
rgb=f.bgpal[pal,idx]
y0,y1,x0,x1=[int(v) for v in sys.argv[3].split(',')] if len(sys.argv)>3 else (0,32,0,32)
S=5
img=Image.fromarray(rgb[y0*8:y1*8,x0*8:x1*8]).resize(((x1-x0)*8*S,(y1-y0)*8*S),Image.NEAREST); d=ImageDraw.Draw(img)
raw=f.maps[f.bg_map()]
for ty in range(y0,y1):
    for tx in range(x0,x1):
        X,Y=(tx-x0)*8*S,(ty-y0)*8*S
        d.rectangle([X,Y,X+8*S,Y+8*S],outline=(255,0,0))
        d.text((X+2,Y+1),'%02X'%raw[ty,tx],fill=(220,0,0))
img.save(sys.argv[2])

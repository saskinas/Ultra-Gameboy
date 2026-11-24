"""Screen grid of tiles with short pixel-hash labels, and a sheet of each unique tile."""
import sys, os, hashlib; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from pyboy import PyBoy
from PIL import Image, ImageDraw
from ugb.roms import rom_path
from ugb.gb import Frame
pb=PyBoy(rom_path(),window='null',cgb=True,sound_emulated=False)
pb.load_state(open(sys.argv[1],'rb'))
for _ in range(3): pb.tick(1,True); f=Frame(pb)
idx,pal,_,ids,bank=f.layer(f.bg_map())
def h(b,i): return hashlib.blake2b(f.tiles[b,i].tobytes(),digest_size=3).hexdigest()
oy,ox=f.scy[0]//8, f.scx[0]//8
names={}; grid=[]
for r in range(18):
    row=[]
    for c in range(20):
        R,C=(oy+r)%32,(ox+c)%32
        k=h(bank[R,C],ids[R,C]); names.setdefault(k,(bank[R,C],ids[R,C],pal[R*8,C*8])); row.append(k)
    grid.append(row)
rgb=f.bgpal[pal,idx]
S=6; img=Image.fromarray(np.roll(rgb,(-oy*8,-ox*8),(0,1))[:144,:160]).resize((160*S,144*S),Image.NEAREST); d=ImageDraw.Draw(img)
for r in range(18):
    for c in range(20):
        d.rectangle([c*8*S,r*8*S,(c+1)*8*S,(r+1)*8*S],outline=(255,0,0)); d.text((c*8*S+2,r*8*S+2),grid[r][c][:4],fill=(255,0,0))
img.save(sys.argv[2])
print(len(names),'unique tiles')
for r in range(18): print('%2d '%r+' '.join(grid[r]))

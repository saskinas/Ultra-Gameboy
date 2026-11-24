"""Dump the current BG tileset (tile ids 0..127 as the map uses them) as a numbered sheet."""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from pyboy import PyBoy
from ugb.roms import rom_path
from PIL import Image, ImageDraw
from ugb.gb import Frame
pb=PyBoy(rom_path(),window='null',cgb=True,sound_emulated=False)
pb.load_state(open(sys.argv[1],'rb')); pb.tick(1)
f=Frame(pb)
shades=np.array([[255,255,255],[170,170,170],[85,85,85],[0,0,0]],np.uint8)
S=5; cell=8*S+14
img=Image.new('RGB',(16*cell,8*cell),(255,230,230)); d=ImageDraw.Draw(img)
used=set(np.unique(f.maps[f.bg_map()]).tolist())
for t in range(128):
    ti=f.tile_index(t)
    px=shades[f.tiles[0,int(ti)]]
    im=Image.fromarray(px).resize((8*S,8*S),Image.NEAREST)
    x,y=(t%16)*cell,(t//16)*cell
    img.paste(im,(x+2,y+12)); d.text((x+2,y),'%02X%s'%(t,'*' if t in used else ''),fill=(200,0,0))
img.save(sys.argv[2])
print('used',sorted(hex(u) for u in used))

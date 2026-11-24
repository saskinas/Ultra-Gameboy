import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, time
from pyboy import PyBoy
from ugb.roms import rom_path
from PIL import Image
from ugb.gb import Frame, compose_original
pb=PyBoy(rom_path(),window='null',cgb=True,sound_emulated=False)
pb.load_state(open(sys.argv[1],'rb')); pb.tick(1)
t=time.time(); f=Frame(pb); t1=time.time()
mine,_=compose_original(f); t2=time.time()
ref=pb.screen.ndarray[:,:,:3]
d=np.abs(mine.astype(int)-ref.astype(int)).sum(-1)
print('read %.1fms compose %.1fms'%((t1-t)*1000,(t2-t1)*1000))
print('lcdc',bin(f.lcdc),'scx',set(f.scx.tolist()),'scy',set(f.scy.tolist()),'wy',f.wy_reg,'wx',set(f.wx.tolist()))
print('mismatch px',(d>0).sum(),'bg pals used',np.unique(f.attrs[f.bg_map()]&7))
print('bgpal',f.bgpal[:3].tolist()); print('objpal',f.objpal[:4].tolist())
Image.fromarray(np.concatenate([mine,ref],1)).resize((640,288),Image.NEAREST).save('out/vram_check.png')

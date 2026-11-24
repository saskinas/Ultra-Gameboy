"""Walk around for a while and time the enhancer per frame; save a few frames."""
import sys, os, time; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from pyboy import PyBoy
from ugb.roms import rom_path
from PIL import Image
from ugb.gb import Frame
from ugb.render import Enhancer
from ugb import presets
pb=PyBoy(rom_path(),window='null',cgb=True,sound_emulated=False)
pb.load_state(open(sys.argv[1],'rb')); pb.tick(1)
en=Enhancer(presets.for_title(pb.cartridge_title))
moves=sys.argv[2].split()   # e.g. right:64 down:48
times=[]; shots=[]
fr=0
for mv in moves:
    d,n=mv.split(':'); n=int(n)
    pb.button_press(d)
    for i in range(n):
        pb.tick(1); t=time.perf_counter(); out=en.render(Frame(pb)); times.append(time.perf_counter()-t)
        fr+=1
        if fr%40==0: shots.append(out)
    pb.button_release(d)
t=np.array(times)*1000
print('frames',len(t),'mean %.1f p50 %.1f p95 %.1f max %.1f ms'%(t.mean(),np.median(t),np.percentile(t,95),t.max()))
print(en.stats)
if shots:
    Image.fromarray(np.concatenate(shots[:4],1)).resize((160*4*2,144*2),Image.NEAREST).save('out/bench.png')

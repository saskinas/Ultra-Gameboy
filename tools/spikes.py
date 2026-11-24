"""Play a button script, time every enhanced frame, report spikes and save the worst frames."""
import sys, os, time; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from pyboy import PyBoy
from ugb.roms import rom_path
from PIL import Image
from ugb.gb import Frame, compose_original
from ugb.render import Enhancer
from ugb import presets
pb=PyBoy(rom_path(),window='null',cgb=True,sound_emulated=True)
pb.load_state(open(sys.argv[1],'rb')); pb.tick(1)
en=Enhancer(presets.for_title(pb.cartridge_title)); times=[]; frames=[]
def step(n, btn=None):
    if btn: pb.button_press(btn)
    for _ in range(n):
        pb.tick(1, True)
        f=Frame(pb); t=time.perf_counter(); out=en.render(f); dt=time.perf_counter()-t
        times.append(dt); frames.append((dt, len(times), compose_original(f)[0], out, dict(en.stats)))
        if len(frames)>400: frames.pop(0)
    if btn: pb.button_release(btn)
for tok in sys.argv[2].split():
    b,n=tok.split(':') if ':' in tok else (None, tok)
    step(int(n), None if b in (None,'w') else b)
t=np.array(times)*1000
print('frames',len(t),'mean %.1f p95 %.1f max %.1f'%(t.mean(),np.percentile(t,95),t.max()))
print('spikes >16ms', [(i,round(v)) for i,v in enumerate(t) if v>16][:40])
print(en.stats)
worst=sorted(frames,key=lambda x:-x[0])[:2]
Image.fromarray(np.concatenate([np.concatenate([w[2],w[3]],1) for w in worst],0)).resize((640,576),Image.NEAREST).save('out/spikes.png')

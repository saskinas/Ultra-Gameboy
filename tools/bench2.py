import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from pyboy import PyBoy
from ugb.roms import rom_path
from PIL import Image
from ugb.gb import Frame, compose_original
from ugb.render import Enhancer
from ugb import presets
pb=PyBoy(rom_path(),window='null',cgb=True,sound_emulated=False)
pb.load_state(open(sys.argv[1],'rb')); pb.tick(1)
en=Enhancer(presets.for_title(pb.cartridge_title)); fr=0; rows=[]
want=set(int(v) for v in sys.argv[3].split(','))
for mv in sys.argv[2].split():
    d,n=mv.split(':'); pb.button_press(d)
    for i in range(int(n)):
        pb.tick(1); f=Frame(pb); out=en.render(f); fr+=1
        if fr in want:
            o,_=compose_original(f); rows.append(np.concatenate([o,out],1))
    pb.button_release(d)
Image.fromarray(np.concatenate(rows,0)).resize((640,288*len(rows)),Image.NEAREST).save(sys.argv[4])

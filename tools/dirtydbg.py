import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from pyboy import PyBoy
from ugb.roms import rom_path
from ugb.gb import Frame
pb=PyBoy(rom_path(),window='null',cgb=True,sound_emulated=True)
pb.load_state(open('states/pallet_town.state','rb')); pb.tick(1)
prev=None; fr=0
def run(n,btn=None):
    global prev, fr
    if btn: pb.button_press(btn)
    for i in range(n):
        pb.tick(1,True); f=Frame(pb); fr+=1
        idx,_,_,_,_=f.layer(f.bg_map()); raw=f.maps[f.bg_map()].copy()
        if prev is not None:
            d=(raw!=prev[0]) | (idx!=prev[1]).reshape(32,8,32,8).any(axis=(1,3))
            if d.sum()>0 and fr>185:
                rows=np.nonzero(d.any(1))[0]; cols=np.nonzero(d.any(0))[0]
                print(fr,'dirty',d.sum(),'rows',rows.tolist(),'cols',cols.min(),cols.max(),'px-only',((idx!=prev[1]).reshape(32,8,32,8).any(axis=(1,3)) & (raw==prev[0])).sum(),'ids',sorted(set(raw[d].tolist()))[:12])
        prev=(raw,idx)
    if btn: pb.button_release(btn)
run(80,'right'); run(120,'up'); run(200)

"""Walk into Oak's dialogue and compare our rebuilt frame to PyBoy's whenever the window is on."""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from pyboy import PyBoy
from ugb.roms import rom_path
from PIL import Image
from ugb.gb import Frame, compose_original
from ugb.render import Enhancer
from ugb import presets
pb=PyBoy(rom_path(),window='null',cgb=True,sound_emulated=False)
pb.load_state(open('states/pallet_town.state','rb')); pb.tick(1)
en=Enhancer(presets.for_title(pb.cartridge_title)); fr=0; win_frames=0; bad=0; saved=[]
def run(n,b=None):
    global fr, win_frames, bad
    if b: pb.button_press(b)
    for i in range(n):
        pb.tick(1,True); f=Frame(pb); fr+=1; out=en.render(f)
        if f.window_mask().any():
            win_frames+=1
            mine,_=compose_original(f); ref=pb.screen.ndarray[:,:,:3]
            d=(np.abs(mine.astype(int)-ref.astype(int)).max(-1)>24).sum()
            if d>0: bad+=1
            if len(saved)<2 and fr%10==0: saved.append(np.concatenate([ref,out],1))
    if b: pb.button_release(b)
run(80,'right'); run(120,'up'); run(150)
for k in range(6): run(3,'a'); run(60)
print('frames with window', win_frames, 'mismatching', bad)
if saved: Image.fromarray(np.concatenate(saved,0)).resize((640,288*len(saved)),Image.NEAREST).save('out/wincheck.png')
# second pass: dump the first mismatching frame with a diff mask
pb.load_state(open('states/pallet_town.state','rb')); pb.tick(1)
done=[False]
def run2(n,b=None):
    if b: pb.button_press(b)
    for i in range(n):
        pb.tick(1,True); f=Frame(pb)
        if not done[0] and f.window_mask().any():
            mine,_=compose_original(f); ref=pb.screen.ndarray[:,:,:3]
            m=(np.abs(mine.astype(int)-ref.astype(int)).max(-1)>24)
            if m.any():
                ys,xs=np.nonzero(m)
                print('diff rows',ys.min(),ys.max(),'cols',xs.min(),xs.max(),'count',m.sum(),'wy',f.wy_reg,'wx',set(f.wx.tolist()),'lcdc',bin(f.lcdc),'scy',set(f.scy.tolist()),'scx',set(f.scx.tolist()))
                vis=np.concatenate([ref,mine,(m[...,None]*255).repeat(3,-1).astype(np.uint8)],1)
                Image.fromarray(vis).resize((480*3,144*3),Image.NEAREST).save('out/windiff.png'); done[0]=True
    if b: pb.button_release(b)
run2(80,'right'); run2(120,'up'); run2(150)
for k in range(6): run2(3,'a'); run2(60)

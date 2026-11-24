import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pyboy import PyBoy
from ugb.roms import rom_path
from ugb.gb import Frame
pb=PyBoy(rom_path(),window='null',cgb=True,sound_emulated=True)
pb.load_state(open('states/pallet_town.state','rb')); pb.tick(1)
prev=None
def run(n,btn=None):
    global prev
    if btn: pb.button_press(btn)
    for i in range(n):
        pb.tick(1,True); f=Frame(pb)
        k=(f.bgpal.tobytes(), f.lcdc&0x10, f.bg_map(), f.lcdc)
        if prev and k!=prev: print('frame change: pal', k[0]!=prev[0], 'lcdc', hex(prev[3]),'->',hex(k[3]))
        prev=k
    if btn: pb.button_release(btn)
run(80,'right'); run(120,'up'); run(200)

import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pyboy import PyBoy
from ugb.roms import rom_path
from ugb.gb import Frame
from ugb.render import Enhancer
from ugb import presets
pb=PyBoy(rom_path(),window='null',cgb=True,sound_emulated=True)
pb.load_state(open('states/pallet_town.state','rb')); pb.tick(1)
en=Enhancer(presets.for_title(pb.cartridge_title)); fr=0; prevk=None
def run(n,b=None):
    global fr, prevk
    if b: pb.button_press(b)
    for i in range(n):
        pb.tick(1,True); f=Frame(pb); fr+=1
        gs=en.game_state(f); k=(f.bgpal.tobytes(), f.lcdc&0x10, gs['tileset'], gs['battle'], f.bg_map())
        if prevk and k!=prevk: print(fr,'pal',k[0]!=prevk[0],'lcdc4',prevk[1],k[1],'tileset',prevk[2],k[2],'battle',prevk[3],k[3],'map',prevk[4],k[4])
        prevk=k; en.render(f)
    if b: pb.button_release(b)
run(80,'right'); run(120,'up'); run(200)
print(en.stats)

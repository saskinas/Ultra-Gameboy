import sys, os, cProfile, pstats; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pyboy import PyBoy
from ugb.roms import rom_path
from ugb.gb import Frame
from ugb.render import Enhancer
from ugb import presets
pb=PyBoy(rom_path(),window='null',cgb=True,sound_emulated=False)
pb.load_state(open(sys.argv[1] if len(sys.argv)>1 else 'states/pallet_town.state','rb')); pb.tick(1)
en=Enhancer(presets.for_title(pb.cartridge_title))
def run(n,b=None):
    if b: pb.button_press(b)
    for i in range(n): pb.tick(1,True); en.render(Frame(pb))
    if b: pb.button_release(b)
run(60)
pr=cProfile.Profile(); pr.enable()
for i in range(30): pb.tick(1,True); en.render(Frame(pb))
pr.disable(); pstats.Stats(pr).sort_stats('cumtime').print_stats(18)

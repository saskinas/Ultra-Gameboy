import sys, os, cProfile, pstats; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pyboy import PyBoy
from ugb.roms import rom_path
from ugb.gb import Frame
from ugb.render import Enhancer
from ugb import presets
pb=PyBoy(rom_path(),window='null',cgb=True,sound_emulated=False)
pb.load_state(open(sys.argv[1],'rb')); pb.tick(1)
en=Enhancer(presets.for_title(pb.cartridge_title))
for _ in range(5): pb.tick(1,True); en.render(Frame(pb))
pr=cProfile.Profile(); pr.enable()
for mv in sys.argv[2].split():
    d,n=mv.split(':'); pb.button_press(d)
    for _ in range(int(n)): pb.tick(1,True); en.render(Frame(pb))
    pb.button_release(d)
pr.disable(); pstats.Stats(pr).sort_stats('tottime').print_stats(14)

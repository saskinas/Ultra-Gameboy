"""Drive Pokémon Yellow headless with a button script, saving screenshots and a save state.

Usage: python tools/drive.py <in_state|-> <out_state> <script>
Script: space-separated steps. 'a', 'b', 'start', 'up', ... press a button for 1 frame then
wait 20 frames; 'a*30' repeats; 'w120' waits 120 frames; 'shot:name' saves out/drive_name.png;
'hold:up:16' holds a button 16 frames (one step is 16 frames).
"""
import os
import sys
from pyboy import PyBoy

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from ugb.roms import rom_path
ROM = rom_path()


def run(in_state, out_state, script):
    pb = PyBoy(ROM, window='null', cgb=True, sound_emulated=True)
    pb.set_emulation_speed(0)
    if in_state != '-':
        with open(in_state, 'rb') as f:
            pb.load_state(f)
    else:
        pb.tick(60)
    for step in script.split():
        if step.startswith('w'):
            pb.tick(int(step[1:]))
        elif step.startswith('shot:'):
            pb.screen.image.convert('RGB').save(os.path.join(HERE, 'out', 'drive_' + step[5:] + '.png'))
        elif step.startswith('hold:'):
            _, btn, n = step.split(':')
            pb.button_press(btn)
            pb.tick(int(n))
            pb.button_release(btn)
            pb.tick(2)
        else:
            btn, _, n = step.partition('*')
            for _ in range(int(n or 1)):
                pb.button(btn)
                pb.tick(20)
    with open(out_state, 'wb') as f:
        pb.save_state(f)
    if 'YELLOW' in pb.cartridge_title:
        m = pb.memory
        print('map', m[0xD35D], 'tileset', m[0xD366], 'y', m[0xD360], 'x', m[0xD361],
              'battle', m[0xD056], 'grass', hex(m[0xD534]))
    pb.stop(save=False)


if __name__ == '__main__':
    run(*sys.argv[1:4])

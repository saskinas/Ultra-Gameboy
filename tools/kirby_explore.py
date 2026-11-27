"""Explore a Kirby stage through its doors in background copies: capture an area,
go through each door it has (ugb.lineart.through_door), capture what's behind,
and so on. Saves an arrival state and an area sheet for each new area.

    python tools/kirby_explore.py <state> <name prefix> [depth]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ugb import lineart   # noqa: E402
from ugb.presets import kirby_dream_land as kirby   # noqa: E402
from ugb.roms import rom_path   # noqa: E402

P = kirby.__name__
rom = rom_path('kirby')
state = open(sys.argv[1], 'rb').read()
prefix = sys.argv[2]
depth = int(sys.argv[3]) if len(sys.argv) > 3 else 6
from pyboy import PyBoy   # noqa: E402
import io   # noqa: E402
pb = PyBoy(rom, window='null', cgb=True, sound_emulated=False)
pb.load_state(io.BytesIO(state))
key0 = kirby.area_key(pb.memory)
pb.stop(save=False)
todo = [(key0, state, 0)]
seen = {key0}
while todo:
    key, st, d = todo.pop(0)
    res = lineart.solve_area(rom, st, P)
    name = '%s_%s' % (prefix, '-'.join(map(str, key)))
    open('states/%s.state' % name, 'wb').write(st)
    os.system('"%s" tools/kirby_sheet.py states/%s.state out/sheet_%s.png > NUL 2>&1' % (sys.executable, name, name))
    print('area', key, 'size', res[0].shape, 'at', (res[1], res[2]), 'doors', [(x[1], x[2]) for x in res[5]],
          '-> states/%s.state, out/sheet_%s.png' % (name, name), flush=True)
    if d >= depth:
        continue
    for door in res[5]:
        r = lineart.through_door(rom, door, P, known=tuple(seen))
        if r is None:
            continue
        seen.add(r[0])
        todo.append((r[0], lineart.through_door.entry, d + 1))

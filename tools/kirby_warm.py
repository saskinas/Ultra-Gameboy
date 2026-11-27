"""Fill the area cache (cache/areas) for the current code, so areas are ready the
moment the player gets there: capture the area in each state given, then go
through its doors (ugb.lineart.through_door) and on, as far as `--depth`.
Any change to the solver or the preset makes the old cache unusable; run this
after one.

    python tools/kirby_warm.py <state> [<state> ...] [--depth N] [--states prefix]

With --states, an arrival state is kept for each area: states/<prefix>_<key>.state
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pyboy import PyBoy   # noqa: E402

from ugb import atlas, lineart   # noqa: E402
from ugb.presets import kirby_dream_land as kirby   # noqa: E402
from ugb.render import Enhancer   # noqa: E402
from ugb.roms import rom_path   # noqa: E402

if __name__ == '__main__':
    args = sys.argv[1:]
    depth, prefix = 4, None
    if '--depth' in args:
        i = args.index('--depth')
        depth = int(args[i + 1])
        del args[i:i + 2]
    if '--states' in args:
        i = args.index('--states')
        prefix = args[i + 1]
        del args[i:i + 2]
    P, rom = kirby.__name__, rom_path('kirby')
    en = Enhancer(kirby)
    done = set(en._disk_keys())
    print('already cached:', sorted(done))
    todo = []
    for path in args:
        st = open(path, 'rb').read()
        pb = PyBoy(rom, window='null', cgb=True, sound_emulated=False)
        pb.load_state(io.BytesIO(st))
        key = kirby.area_key(pb.memory)
        pb.stop(save=False)
        if key is not None:
            todo.append((key, st, None, 0))
    while todo:
        key, st, res, d = todo.pop(0)
        if res is None:
            if key in done:
                continue
            try:
                res = lineart.solve_area(rom, st, P)
            except atlas.LeftArea:
                print('left the area:', key)
                continue
        if key not in done:
            en._area_save(key, res)
            done.add(key)
            print('cached', key, 'size', res[0].shape, 'doors', len(res[5]), flush=True)
            if prefix:
                open('states/%s_%s.state' % (prefix, '-'.join(map(str, key))), 'wb').write(st)
        if d >= depth:
            continue
        for door in res[5]:
            r = lineart.through_door(rom, door, P, known=tuple(done))
            if r is not None and r[0] not in done:
                todo.append((r[0], lineart.through_door.entry, r[1], d + 1))
    print('cached now:', sorted(done))

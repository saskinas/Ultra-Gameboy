"""Print ANCHORS for the Pokemon preset: per tileset, two labelled tiles' pixel hashes.

A preset's tile labels are only used when these tiles in VRAM look as expected, so
title screens, intros and other screens that leave the tileset number unchanged
don't get overworld materials painted on them.
"""
import glob, hashlib, os, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pyboy import PyBoy
from ugb import presets
from ugb.gb import Frame
from ugb.roms import rom_path
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pb = PyBoy(rom_path('yellow'), window='null', cgb=True, sound_emulated=False)
p = presets.for_title(pb.cartridge_title)
found = {}
for path in sorted(glob.glob(os.path.join(HERE, 'states', 'warp_*.state')) + glob.glob(os.path.join(HERE, 'states', 'indoor_*.state'))):
    pb.load_state(open(path, 'rb')); pb.tick(2, True); f = Frame(pb)
    ts = pb.memory[p.RAM['tileset']]
    table = p.TILESETS.get(ts)
    if not table or ts in found:
        continue
    raw = f.maps[f.bg_map()]
    def detailed(t):
        px = f.tiles[0, f.tile_index(t)]
        counts = Counter(px.ravel().tolist())
        return len(counts) >= 3 and max(counts.values()) <= 48   # not plain or nearly plain
    used = Counter(int(t) for t in raw.ravel() if int(t) in table and table[int(t)] not in 'Wf')
    picks = [t for t, _ in used.most_common() if detailed(t)][:2]
    if len(picks) < 2:
        continue
    found[ts] = [(t, hashlib.blake2b(f.tiles[0, f.tile_index(t)].tobytes(), digest_size=4).hexdigest()) for t in picks]
print('ANCHORS = {')
for ts in sorted(found):
    print('    %d: %r,' % (ts, found[ts]))
print('}')

"""Whole-area background capture ("atlas") by letting the game draw it.

A game streams its level into the 32x32 tile map a row or column at a time as
the camera moves, so the renderer only ever sees a slice. To see a whole area,
copy the emulator into a hidden second one and drive the camera there with a
few memory writes: left, up, right and down to the area's edges, recording every
tile that appears on screen. The real game is never touched.

The camera's world position is anchored once from the preset's camera function,
then followed exactly by unwrapping the scroll registers frame to frame.

The preset supplies how to drive it (see SWEEP in presets/kirby_dream_land.py).
"""
import hashlib
import io

import numpy as np
from pyboy import PyBoy

from ugb.gb import decode_tiles


class LeftArea(Exception):
    """The copy of the game was no longer in the area it was asked to capture
    (try again from a later moment)."""


class Atlas:
    """A captured area: tile hashes and pixel shades by world tile (rows, columns),
    hash -1 where a tile was never on screen. (x0, y0) is the world position of
    the top-left tile, in pixels."""

    def __init__(self, rows, cols):
        self.hashes = np.full((rows, cols), -1, np.int64)
        self.shade = np.zeros((rows * 8, cols * 8), np.uint8)   # 0 white .. 3 black
        self.x0 = self.y0 = 0
        self.wrap = 0            # an area that loops sideways: its width in px (else 0)
        self.doors = []          # (snapshot with the player by a door, door's top row, left column)

    @property
    def width(self):
        return self.shade.shape[1]

    @property
    def height(self):
        return self.shade.shape[0]


def _hash(tile):
    return int(hashlib.blake2b(tile.tobytes(), digest_size=3).hexdigest(), 16)


def capture(rom, state, sweep, max_frames=1500, check=None, playfield=128, trace=None):
    """Build an Atlas of the area in `state` (bytes of a save state).

    sweep: dict with
      'camera'  memory -> (world x, world y) of the camera, to anchor it
      'pin_x', 'pin_y'  the player's screen X and Y bytes
      'moves'   [(name, buttons held, pin x, pin y, tap A? ('b': B once)[, 'tall'])], run in
                order, each until the camera stops; 'tall' moves only once the
                camera has moved vertically (areas taller than the screen),
                'narrow' ones only in areas at most two screens wide,
                'descend' ones only after the climbing rounds are done
      'door_tiles'  tile hashes of door arches: a snapshot is kept whenever the
                player passes in front of one (Atlas.doors)
      'each_frame'  called with the memory before each frame of the moves
                (Kirby: keep his health up, so enemies can't end the sweep)
      'tile_keys'  memory -> the tile labels for this place (Atlas.tile_keys)
      'settle'  frames to run before anything (the player may not be
                controllable yet)
      'rounds'  how many times at most to run the moves (again only while a
                round finds new rows)
      'restart', 'key'  optional: restart(memory) makes the game restart the
                area from its start (games that can't scroll back); kept only
                if key(memory) comes back the same, further left
    check(pb, x, y) is called each recorded frame (for testing)."""
    pb = PyBoy(rom, window='null', cgb=True, sound_emulated=False)
    pb.load_state(io.BytesIO(state))
    mem = pb.memory
    pos = {}
    seen = {}                    # (world row, world column) -> (hash, 8x8 shades)

    def cam():
        scx, scy = mem[0xFF43], mem[0xFF42]
        if not pos:
            # anchored from the game's counter, snapped to agree with the scroll
            # registers (world x = SCX mod 256), as the renderer's camera is
            # the game's counter for the coarse part (its 16 px steps), the scroll
            # registers for the rest. Usually world x = SCX mod 256, but a game
            # may start its map afresh elsewhere (Kirby, back out of a door)
            x, y = sweep['camera'](mem)
            pos['x'] = scx + int(round((x - scx) / 16.0)) * 16
            pos['y'] = scy + int(round((y - scy) / 16.0)) * 16
            pos['off'] = pos['x'] - x
        else:
            pos['x'] += (scx - pos['scx'] + 128) % 256 - 128
            pos['y'] += (scy - pos['scy'] + 128) % 256 - 128
            # an area that loops sideways: the game's counter jumps back by the
            # loop's width while the scroll moves on smoothly (record() checks
            # the tiles repeat before the capture is folded to one lap)
            off = pos['x'] - sweep['camera'](mem)[0]
            if abs(off - pos['off']) >= 160 and not wrap['px']:
                wrap['cand'] = int(round(abs(off - pos['off']) / 8.0)) * 8
            pos['off'] = off
        pos['scx'], pos['scy'] = scx, scy
        return pos['x'], pos['y']

    wrap = {'px': 0, 'cand': 0}

    def fold(wc):
        return wc % (wrap['px'] // 8) if wrap['px'] else wc

    def check_wrap(wrs, wcs, sh):
        """A candidate loop width: accept it if the screen's tiles repeat one
        lap away from what was seen, then fold everything seen to one lap."""
        n = (wrap['cand'] // 8)
        agree = total = 0
        for i, wr in enumerate(wrs.tolist()):
            for j, wc in enumerate(wcs.tolist()):
                for o in (wc - n, wc + n):
                    s = seen.get((wr, o))
                    if s is not None:
                        total += 1
                        agree += int(np.array_equal(s[1], sh[i, j]))
                        break
        wrap['cand'] = 0
        if total >= 40 and agree >= 0.9 * total:
            wrap['px'] = n * 8
            folded = {(r, c % n): v for (r, c), v in seen.items()}
            seen.clear()
            seen.update(folded)
            folded = {(c % n) // 2: (r, c % n) for r, c in doors.values()}
            doors.clear()
            doors.update(folded)

    dmg = not (mem[0x0143] & 0x80)
    last = {}
    door_tiles = set(sweep.get('door_tiles', ()))
    hcache = {}
    doors = {}                   # door (world column // 2) -> where its arch was seen
    door_states = {}             # door -> a snapshot with Kirby in front of it

    def record(x, y):
        # tiles wholly on the playfield (further out the map may hold stale
        # rows and columns), kept as last seen there: the game may show a tile a
        # frame before it has written it, never after. Read straight from VRAM
        # (a full ugb.gb.Frame costs ten times as much).
        if last.get('at') == (x, y):
            last['n'] += 1
            if last['n'] > 3:       # (still: a few frames for late column writes)
                return
        else:
            last['at'], last['n'] = (x, y), 0
        v0 = mem[0, 0x8000:0x9FFF] + [mem[0, 0x9FFF]]
        lcdc = mem[0xFF40]
        base = 0x1C00 if lcdc & 0x08 else 0x1800
        tiles = [decode_tiles(v0[:0x1800])]
        tmap = np.array(v0[base:base + 0x400], int).reshape(32, 32)
        if dmg:
            attr = np.zeros((32, 32), int)
            tiles.append(tiles[0])
        else:
            v1 = mem[1, 0x8000:0x9FFF] + [mem[1, 0x9FFF]]
            tiles.append(decode_tiles(v1[:0x1800]))
            attr = np.array(v1[base:base + 0x400], int).reshape(32, 32)
        tiles = np.stack(tiles)
        ids = tmap if lcdc & 0x10 else np.where(tmap < 128, tmap + 256, tmap)
        bgp = mem[0xFF47]
        lut = np.array([(bgp >> (2 * i)) & 3 for i in range(4)], np.uint8) if dmg else np.arange(4, dtype=np.uint8)
        wrs = np.arange((y + 7) // 8, (y + playfield) // 8)
        wcs = np.arange((x + 7) // 8, (x + 160) // 8)
        # map column = world column - phase (the map's start, see cam())
        mr, mc = (wrs - (y - mem[0xFF42]) // 8) % 32, (wcs - (x - mem[0xFF43]) // 8) % 32
        b = (attr[np.ix_(mr, mc)] >> 3) & 1
        raw = tiles[b, ids[np.ix_(mr, mc)]]                 # (rows, cols, 8, 8) as stored
        a = attr[np.ix_(mr, mc)][..., None, None]
        pix = np.where((a >> 5) & 1, raw[..., :, ::-1], raw)
        pix = np.where((a >> 6) & 1, pix[..., ::-1, :], pix)
        sh = lut[pix]
        if wrap['cand']:
            check_wrap(wrs, wcs, sh)
        if wrap['px']:
            wcs = wcs % (wrap['px'] // 8)
        for i, wr in enumerate(wrs.tolist()):
            for j, wc in enumerate(wcs.tolist()):
                if door_tiles and (wr, wc) not in seen:      # (doors: see 'door_tiles')
                    rb = raw[i, j].tobytes()
                    h = hcache.get(rb)
                    if h is None:
                        h = hcache[rb] = _hash(raw[i, j])
                    if h in door_tiles:
                        doors.setdefault(wc // 2, (wr, wc))
                seen[(wr, wc)] = (raw[i, j], sh[i, j])

    def restart():
        key, (x, _) = sweep['key'](mem), sweep['camera'](mem)
        # (the game keeps a 256 px ring of columns, so a camera at most 96 px
        # from the start can still scroll back to it: no need)
        if key is None or x <= 256 - 160:
            return
        buf = io.BytesIO()
        pb.save_state(buf)
        sweep['restart'](mem)
        moved = None
        for i in range(1200):
            pb.tick(1, False)
            if moved is None and abs(sweep['camera'](mem)[0] - x) > 16:     # (not the death wobble)
                moved = i
            if moved is not None and i > moved + 30:
                break
        if moved is None or sweep['key'](mem) != key or sweep['camera'](mem)[0] >= x:
            buf.seek(0)
            pb.load_state(buf)

    def run(buttons, px, py, tap):
        for b in buttons:
            pb.button_press(b)
        last, still = None, 0
        grew = {'n': len(seen), 'at': 0}
        for i in range(max_frames):
            if px is not None:
                mem[sweep['pin_x']] = px
            if py is not None:
                mem[sweep['pin_y']] = py
            if tap == 'b':              # one tap of B first (Kirby: let the air out)
                if i == 0:
                    pb.button_press('b')
                if i == 4:
                    pb.button_release('b')
            elif tap and i % 8 == 0:
                pb.button_press('a')
            elif tap and i % 8 == 4:
                pb.button_release('a')
            if 'each_frame' in sweep:           # (e.g. keep the player alive)
                sweep['each_frame'](mem)
            pb.tick(1, check is not None)       # (draw only when checking)
            if 'key' in sweep and sweep['key'](mem) != home['key']:
                home['left'] = True         # (out of the area, e.g. through its exit: stop)
                break
            c = cam()
            record(*c)
            if doors:
                # Kirby in front of a door seen so far: keep a snapshot there
                # (lineart.through_door tries it later)
                # (the lowest pass by it wins: from there he lands in front of it)
                kx, ky = c[0] + mem[sweep['pin_x']], mem[sweep['pin_y']]
                if wrap['px']:
                    kx %= wrap['px']
                for dk, (wr, wc) in doors.items():
                    if abs(kx - (wc // 2 * 16 + 8)) <= 3 and ky < 0xA0 and                             (dk not in door_states or ky > door_states[dk][0] + 8):
                        buf = io.BytesIO()
                        pb.save_state(buf)
                        door_states[dk] = (ky, (buf.getvalue(), wr, wc // 2 * 2))
            if check is not None:
                check(pb, *c)
            still = still + 1 if c == last else 0
            last = c
            if still > 40:          # the camera stopped: the area's edge
                break
            if len(seen) != grew['n']:
                grew['n'], grew['at'] = len(seen), i
            elif wrap['px'] and i - grew['at'] > 150:   # round and round a loop, nothing new
                break
        for b in buttons:
            pb.button_release(b)
        pb.button_release('a')

    # let the game settle first: a capture may start the moment an area counts
    # as in play, while the player is still coming through a door
    # (with every button let go: the state may have been saved mid-press, and
    # a held Up at a door walks straight back out)
    for b in ('up', 'down', 'left', 'right', 'a', 'b', 'start', 'select'):
        pb.button_release(b)
    key0 = sweep['key'](mem) if 'key' in sweep else None
    pb.tick(sweep.get('settle', 0), False)
    if 'key' in sweep and sweep['key'](mem) != key0:
        pb.stop(save=False)
        raise LeftArea('the game left the area before the capture began')
    # (labels once settled: coming through a door, the game can switch what
    # decides them, such as Kirby's play mode, a few frames after the area)
    tile_keys = sweep['tile_keys'](mem) if 'tile_keys' in sweep else None
    pre = {}
    if 'restart' in sweep:
        # the screen the player is on first: the restart takes the copy back to
        # the area's start, and from there the sweep may never get here (a cave
        # whose lower part is reached by dropping down). The camera is anchored
        # afresh after the restart, from the game's counters both times.
        cam()
        record(pos['x'], pos['y'])
        pre = dict(seen)
        restart()
        pos.clear()
        last.clear()
    cam()
    record(pos['x'], pos['y'])
    home = {'key': sweep['key'](mem) if 'key' in sweep else None, 'left': False}
    # rounds of the moves while each finds new rows: first without the
    # 'descend' moves (climbing), then with them (going down floor by floor)
    rnd = 0
    top0 = min(r for r, _ in seen)
    for phase in ('climb', 'descend'):
        if phase == 'descend':
            # only for narrow areas the climb never took upwards (the descents)
            if not any('descend' in m[5:] for m in sweep['moves']) or home['left']:
                break
            if len({c for _, c in seen}) > 40 or min(r for r, _ in seen) < top0:
                break
        for _ in range(sweep.get('rounds', 1)):
            rows0 = len({r for r, _ in seen})
            for name, buttons, px, py, tap, *cond in sweep['moves']:
                if home['left']:
                    break
                if 'descend' in cond and phase == 'climb':
                    continue
                if 'tall' in cond and len({r for r, _ in seen}) <= playfield // 8:
                    continue
                if 'narrow' in cond and len({c for _, c in seen}) > 40:     # (two screens)
                    continue
                run(buttons, px, py, tap)
                if trace is not None:
                    trace.append((rnd, name, pos['x'], pos['y'], mem[sweep['pin_x']], mem[sweep['pin_y']],
                                  pb.frame_count))
            rnd += 1
            if home['left'] or len({r for r, _ in seen}) == rows0:
                break
    pb.stop(save=False)
    # the first screen's tiles stay only if they agree where the sweep saw the
    # same places again (else the two anchors disagreed: drop the ones never seen again)
    again = [k for k, v in pre.items() if seen.get(k) is not v]
    if len(again) >= 20:
        agree = sum(np.array_equal(pre[k][1], seen[k][1]) for k in again)
        if agree < 0.8 * len(again):
            for k, v in pre.items():
                if seen.get(k) is v:
                    del seen[k]
    r0 = min(r for r, _ in seen)
    r1 = max(r for r, _ in seen)
    c0 = min(c for _, c in seen)
    c1 = max(c for _, c in seen)
    if wrap['px']:                  # one whole lap, from the loop's start
        c0, c1 = 0, wrap['px'] // 8 - 1
    at = Atlas(r1 - r0 + 1, c1 - c0 + 1)
    at.x0, at.y0 = c0 * 8, r0 * 8
    for (r, c), (raw, sh) in seen.items():
        at.hashes[r - r0, c - c0] = _hash(raw)
        at.shade[(r - r0) * 8:(r - r0) * 8 + 8, (c - c0) * 8:(c - c0) * 8 + 8] = sh
    at.wrap = wrap['px']
    at.doors = [st for _, st in door_states.values()]
    at.tile_keys = tile_keys
    return at

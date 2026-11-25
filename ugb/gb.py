"""Read the Game Boy Color's video state from PyBoy each frame.

Everything the enhancer needs is here: tile pixels (both VRAM banks), the two
tile maps with their colour attributes, the colour palettes, the sprite table
(OAM) and the scroll and window registers. `compose_original` rebuilds the
normal frame from these, which proves the reading is right.
"""
import collections

import numpy as np

LCDC, SCY, SCX, WY, WX = 0xFF40, 0xFF42, 0xFF43, 0xFF4A, 0xFF4B
BCPS, BCPD, OCPS, OCPD = 0xFF68, 0xFF69, 0xFF6A, 0xFF6B


def decode_tiles(raw):
    """0x1800 bytes of 2bpp tile data -> (384, 8, 8) colour indices 0..3."""
    b = np.frombuffer(bytes(raw), np.uint8).reshape(384, 8, 2)
    bits = 7 - np.arange(8)
    lo = (b[:, :, 0:1] >> bits) & 1
    hi = (b[:, :, 1:2] >> bits) & 1
    return (lo | (hi << 1)).astype(np.uint8)


def read_palettes(mem, sel, data):
    """Read 8 palettes x 4 colours (RGB555 -> RGB888) through the CGB palette ports."""
    old = mem[sel]
    raw = []
    for i in range(64):
        mem[sel] = i
        raw.append(mem[data])
    mem[sel] = old
    w = np.array(raw, np.uint16).reshape(8, 4, 2)
    c = w[..., 0] | (w[..., 1] << 8)
    r, g, b = c & 31, (c >> 5) & 31, (c >> 10) & 31
    rgb = np.stack([r, g, b], -1).astype(np.uint16)
    return ((rgb << 3) | (rgb >> 2)).astype(np.uint8)


class Frame:
    """One frame's video state."""

    def __init__(self, pb):
        mem = pb.memory
        # Plain Game Boy games run in the Color's compatibility mode: one VRAM bank,
        # no attributes, and colours chosen by the boot ROM per game.
        self.dmg = not (mem[0x0143] & 0x80)
        # PyBoy's bank reads stop one byte short of 0xA000, so add the last byte.
        v0 = mem[0, 0x8000:0x9FFF] + [mem[0, 0x9FFF]]
        v1 = [0] * 0x2000 if self.dmg else mem[1, 0x8000:0x9FFF] + [mem[1, 0x9FFF]]
        self.tiles = np.stack([decode_tiles(v0[:0x1800]), decode_tiles(v1[:0x1800])])  # (2,384,8,8)
        self.maps = np.array([v0[0x1800:0x1C00], v0[0x1C00:0x2000]], np.uint8).reshape(2, 32, 32)
        self.attrs = np.array([v1[0x1800:0x1C00], v1[0x1C00:0x2000]], np.uint8).reshape(2, 32, 32)
        # Games copy next frame's sprites into OAM during vertical blank, which has
        # already happened when tick() returns. The picture on screen was drawn with
        # the OAM we saw after the previous tick, so use that when we have it.
        cur = note_tick(pb)
        prev = _OAM_HIST.get(id(pb), {}).get(pb.frame_count - 1)
        self.oam = prev if prev is not None else cur
        self.oam_exact = prev is not None
        self.lcdc = mem[LCDC]
        # Per-scanline scroll and window position, as the screen was drawn.
        lines = pb.screen.tilemap_position_list
        self.scx = np.array([l[0] for l in lines], int)
        self.scy = np.array([l[1] for l in lines], int)
        # PyBoy reports WX - 7 per line; store the real WX register value.
        self.wx = np.array([l[2] for l in lines], int) + 7
        self.wy = np.array([l[3] for l in lines], int)
        self.wy_reg = mem[WY]
        self.ram = mem  # for game-state lookups
        if self.dmg:
            self.bgp, self.obp = mem[0xFF47], (mem[0xFF48], mem[0xFF49])
            learn = _DMG_COLOURS.setdefault(id(pb), DmgColours())
            learn.update(self, pb.screen.ndarray[:, :, :3])
            self.bgpal, self.objpal = learn.palettes(self)
        else:
            self.bgpal = read_palettes(mem, BCPS, BCPD)
            self.objpal = read_palettes(mem, OCPS, OCPD)
        # Usually the previous tick's OAM is what was drawn, but games sometimes
        # rewrite or briefly clear it at other points in the frame (Pokemon does
        # while printing text). When the last three ticks' tables differ, keep
        # whichever matches the emulator's picture best.
        hist = _OAM_HIST.get(id(pb), {})
        cands = [hist[k] for k in (pb.frame_count - 1, pb.frame_count, pb.frame_count - 2) if k in hist]
        if len(cands) > 1 and any(not np.array_equal(cands[0], c) for c in cands[1:]):
            scr = pb.screen.ndarray[:, :, :3]
            fits = [self._sprite_fit(c, scr) for c in cands]
            self.oam = cands[int(np.argmax(fits))]   # ties keep the previous tick's

    def _sprite_fit(self, oam, scr):
        """How well an OAM table explains the picture: matching opaque sprite pixels
        minus mismatching ones (sampled), using the sprite palettes."""
        keep = self.oam
        self.oam = oam
        score = 0
        try:
            for s in self.sprites():
                px = s['px']
                ys, xs = np.nonzero(px)
                y, x = ys + s['y'], xs + s['x']
                ok = (y >= 0) & (y < 144) & (x >= 0) & (x < 160)
                if not ok.any():
                    continue
                y, x, c = y[ok], x[ok], px[ys[ok], xs[ok]]
                want = self.objpal[s['pal']][c].astype(int)
                hit = np.abs(scr[y, x].astype(int) - want).max(-1) <= 40
                score += int(hit.sum()) - int((~hit).sum())
        finally:
            self.oam = keep
        return score

    # ---- layer helpers -------------------------------------------------
    def tile_index(self, tid):
        """Map a tile-map byte to an index into the 384-tile table (LCDC bit 4)."""
        tid = np.asarray(tid, int)
        if self.lcdc & 0x10:
            return tid
        return np.where(tid < 128, tid + 256, tid)

    def layer(self, which):
        """Full 256x256 layer for map `which` (0 = $9800, 1 = $9C00).

        Returns colour index (256,256), palette number (256,256), BG-priority
        flag (256,256), tile number (32,32) and VRAM bank (32,32).
        """
        ids = self.tile_index(self.maps[which])
        at = self.attrs[which]
        bank = (at >> 3) & 1
        pal = at & 7
        xflip = (at >> 5) & 1
        yflip = (at >> 6) & 1
        prio = (at >> 7) & 1
        t = self.tiles[bank, ids]                      # (32,32,8,8)
        t = np.where(xflip[..., None, None] == 1, t[..., :, ::-1], t)
        t = np.where(yflip[..., None, None] == 1, t[..., ::-1, :], t)
        idx = t.transpose(0, 2, 1, 3).reshape(256, 256)
        up = lambda a: np.repeat(np.repeat(a, 8, 0), 8, 1)
        return idx, up(pal), up(prio), ids, bank

    def bg_map(self):
        return (self.lcdc >> 3) & 1

    def win_map(self):
        return (self.lcdc >> 6) & 1

    def _window_lines(self):
        """Per screen line: is the window drawn, and which window row does it show.

        Uses WX/WY as they were while each line was drawn (games move the window
        between frames, so the end-of-frame registers can be wrong). Like the
        hardware, the window keeps its own row counter that only advances on lines
        where it is drawn.
        """
        on = np.zeros(144, bool)
        row = np.zeros(144, int)
        if self.lcdc & 0x20:
            n = 0
            for y in range(144):
                if y >= self.wy[y] and self.wx[y] <= 166 and self.wy[y] < 144:
                    on[y] = True
                    row[y] = n
                    n += 1
        return on, row

    def window_mask(self):
        """(144,160) True where the window covers the screen."""
        on, _ = self._window_lines()
        xs = np.arange(160)[None, :]
        return on[:, None] & (xs >= self.wx[:, None] - 7)

    def screen_coords(self):
        """For every screen pixel, its BG-layer coordinate and window-layer coordinate."""
        ys = np.arange(144)[:, None]
        xs = np.arange(160)[None, :]
        by = (ys + self.scy[:, None]) & 255
        bx = (xs + self.scx[:, None]) & 255
        _, row = self._window_lines()
        wy = (row[:, None] + 0 * xs) & 255
        wx = np.clip(xs - (self.wx[:, None] - 7), 0, 255)
        return by, bx, wy, wx

    def sprites(self):
        """Visible sprites as dicts with screen position, pixels and flags (8x16 aware)."""
        tall = bool(self.lcdc & 0x04)
        h = 16 if tall else 8
        out = []
        for i, (y, x, tile, fl) in enumerate(self.oam):
            sy, sx = int(y) - 16, int(x) - 8
            if sy <= -h or sy >= 144 or sx <= -8 or sx >= 160:
                continue
            bank = 0 if self.dmg else (fl >> 3) & 1
            if tall:
                t = tile & 0xFE
                px = np.concatenate([self.tiles[bank, t], self.tiles[bank, t + 1]])
            else:
                px = self.tiles[bank, tile].copy()
            if fl & 0x20:
                px = px[:, ::-1]
            if fl & 0x40:
                px = px[::-1]
            pal = (fl >> 4) & 1 if self.dmg else fl & 7
            out.append(dict(i=i, y=sy, x=sx, px=px, pal=pal, behind=bool(fl & 0x80),
                            tile=int(tile), flags=int(fl), bank=int(bank)))
        return out


_DMG_COLOURS = {}
_OAM_HIST = {}


def note_tick(pb):
    """Record OAM after a tick. Call after every tick that isn't followed by Frame(pb)."""
    cur = np.array(pb.memory[0xFE00:0xFEA0], np.uint8).reshape(40, 4)
    h = _OAM_HIST.setdefault(id(pb), {})
    h[pb.frame_count] = cur
    for k in [k for k in h if k < pb.frame_count - 3]:
        del h[k]
    return cur


def _shades(reg):
    return np.array([(reg >> (2 * i)) & 3 for i in range(4)])


class DmgColours:
    """Learn the colour of each shade (0..3) for BG and both sprite palettes.

    The Color's boot ROM picks these per game and they can't be read back in
    compatibility mode, so compare the shades we decode with the emulator's
    picture. Each sampled frame casts one vote per shade (that frame's most
    common colour for it), and only the last WINDOW votes count. The boot
    animation and fades therefore can't stick: they are soon outvoted.
    Sampling continues slowly for the whole session.
    """

    GREY = np.array([[255, 255, 255], [170, 170, 170], [85, 85, 85], [0, 0, 0]], np.uint8)
    WINDOW = 24     # votes remembered per shade
    SETTLED = 8     # votes per shade before sampling slows down

    def __init__(self):
        self.votes = {}     # (layer, shade) -> deque of rgb tuples; layer 'bg', 0 or 1
        self.n = 0

    def _vote(self, key, colours):
        c = colours.reshape(-1, 3)
        if len(c) > 256:                      # a sample is plenty for the mode
            c = c[:: len(c) // 256]
        packed = (c[:, 0].astype(np.int32) << 16) | (c[:, 1].astype(np.int32) << 8) | c[:, 2]
        vals, counts = np.unique(packed, return_counts=True)
        v = int(vals[np.argmax(counts)])
        best = ((v >> 16) & 255, (v >> 8) & 255, v & 255)
        self.votes.setdefault(key, collections.deque(maxlen=self.WINDOW)).append(best)

    def _best(self, key):
        v = self.votes.get(key)
        if not v:
            return None
        c = collections.Counter(v)
        return np.array(c.most_common(1)[0][0], np.uint8)

    def complete(self):
        keys = [('bg', k) for k in range(4)] + [(p, k) for p in (0, 1) for k in range(4)]
        return all(len(self.votes.get(k, ())) >= self.SETTLED for k in keys)

    def update(self, f, scr):
        self.n += 1
        if not f.oam_exact or not (f.lcdc & 0x80):
            return
        # sample often until settled; games that never show some shade/palette
        # combination would otherwise keep sampling at the fast rate forever
        every = 16 if self.complete() else (4 if self.n < 600 else 32)
        if self.n % every:
            return
        by, bx, wy, wx = f.screen_coords()
        bidx = f.layer(f.bg_map())[0]
        widx = f.layer(f.win_map())[0]
        win = f.window_mask()
        idx = np.where(win, widx[wy, wx], bidx[by, bx])
        shade = _shades(f.bgp)[idx]
        spr = f.sprites()
        cover = np.zeros((144, 160), np.int32)
        bbox = np.zeros((144, 160), bool)
        for s in spr:
            ys = np.arange(s['y'], s['y'] + s['px'].shape[0])
            xs = np.arange(s['x'], s['x'] + 8)
            oky, okx = (ys >= 0) & (ys < 144), (xs >= 0) & (xs < 160)
            sub = (s['px'] != 0)[np.ix_(oky, okx)]
            cover[np.ix_(ys[oky], xs[okx])] += sub
            bbox[np.ix_(ys[oky], xs[okx])] = True
        if f.lcdc & 1:
            for k in range(4):
                m = ~bbox & (shade == k)
                if m.any():
                    self._vote(('bg', k), scr[m])
        for s in spr:
            ys = np.arange(s['y'], s['y'] + s['px'].shape[0])
            xs = np.arange(s['x'], s['x'] + 8)
            oky, okx = (ys >= 0) & (ys < 144), (xs >= 0) & (xs < 160)
            if not oky.any() or not okx.any():
                continue
            px = s['px'][np.ix_(oky, okx)]
            Y, X = np.ix_(ys[oky], xs[okx])
            ok = (px != 0) & (cover[Y, X] == 1)
            if s['behind']:
                ok &= idx[Y, X] == 0
            sh = _shades(f.obp[s['pal']])[px]
            for k in range(4):
                m = ok & (sh == k)
                if m.any():
                    self._vote((s['pal'], k), scr[Y, X][m])

    def palettes(self, f):
        """8x4 BG and sprite palettes indexed by raw colour number, like CGB palettes."""
        def colours(layer):
            return np.array([c if (c := self._best((layer, i))) is not None else self.GREY[i]
                             for i in range(4)], np.uint8)
        bg = colours('bg')[_shades(f.bgp)]
        bgpal = np.repeat(bg[None], 8, 0)
        objpal = np.repeat(colours(0)[_shades(f.obp[0])][None], 8, 0)
        objpal[1] = colours(1)[_shades(f.obp[1])]
        return bgpal, objpal


def compose_original(f):
    """Rebuild the normal CGB frame from the video state (no enhancement)."""
    by, bx, wy, wx = f.screen_coords()
    bidx, bpal, bprio, _, _ = f.layer(f.bg_map())
    widx, wpal, wprio, _, _ = f.layer(f.win_map())
    win = f.window_mask()
    idx = np.where(win, widx[wy, wx], bidx[by, bx])
    pal = np.where(win, wpal[wy, wx], bpal[by, bx])
    prio = np.where(win, wprio[wy, wx], bprio[by, bx])
    out = f.bgpal[pal, idx].copy()
    # Sprites: lower OAM index wins, so draw in reverse order.
    for s in reversed(f.sprites()):
        hgt = s['px'].shape[0]
        for yy in range(hgt):
            y = s['y'] + yy
            if not 0 <= y < 144:
                continue
            for xx in range(8):
                x = s['x'] + xx
                if not 0 <= x < 160:
                    continue
                c = s['px'][yy, xx]
                if c == 0:
                    continue
                if (f.lcdc & 1) and (s['behind'] or prio[y, x]) and idx[y, x] != 0:
                    continue
                out[y, x] = f.objpal[s['pal'], c]
    return out, idx

"""Ultra Game Boy renderer: turns one frame of Game Boy video state into a 16-bit-style image.

Work happens in two spaces:
  * BG-layer space (the Game Boy's 256x256 wrapping tile map). Materials, objects,
    lighting and shadows are computed here and kept between frames. When the game
    writes new tiles (every step, as it scrolls), only a band around the changed
    tiles is redrawn. Animated tiles (water, flowers) are recoloured each frame
    from stored parameters, which is cheap.
  * Screen space (160x144): compose the layer with the scroll registers, then add
    sprites (lit, with soft shadows) and SNES-style text boxes.
"""
import hashlib

import numpy as np
from scipy import ndimage as ndi

from ugb import fx

N = 256
SY, SX = np.mgrid[0:144, 0:160]
L = np.array([-1.0, -1.0, 1.0], np.float32) / np.sqrt(3)   # light from the top left
GROUND = ['g', 'l', 'f', 'G', 'F', 'C', 'E']        # receive shadows
BUILDING = ['R', 'H', 'N', 'D', 'S', 'O', 'M', 'L']   # cast shadows
ANIM = ['W', 'f']
M = {c: ord(c) for c in 'glfGWTPBRHNDSKFCMOELU?'}   # material codes as bytes (fast compares)


def _set_lut(chars):
    t = np.zeros(256, bool)
    for c in chars:
        t[ord(c)] = True
    return t


IS_GROUND = _set_lut(GROUND)
IS_BUILDING = _set_lut(BUILDING)
IS_ANIM = _set_lut(ANIM)
IS_GL = _set_lut('gl')
MARGIN = 3   # tiles of context around a redrawn band (stamps, shadows, shore)
SETTLE_FRAMES = 12   # still frames before the on-screen area is redrawn from scratch

WATER_T = np.array([0.80, 0.42, 0.30, 0.10], np.float32)
PETAL_T = np.array([0.0, 0.95, 0.6, 0.15], np.float32)


def _interval(dirty_1d):
    """Smallest circular interval (start, length) of a 32-cell ring covering all dirty cells."""
    d = np.nonzero(dirty_1d)[0]
    if len(d) == 0:
        return None
    gaps = np.diff(np.concatenate([d, [d[0] + 32]]))
    k = int(np.argmax(gaps))
    start = int(d[(k + 1) % len(d)])
    length = 32 - (int(gaps[k]) - 1)
    return start, length


def _border_rows(t):
    """Top and bottom box borders (Gen 1 tiles), including a title written into one.

    Works on any array of tile numbers (tile grid or per-pixel); rows run along
    axis 0. Side bars (0x7C) are not included, so text rows don't count.
    """
    hz = np.isin(t, (0x79, 0x7A, 0x7B, 0x7D, 0x7E))
    acc = np.maximum.accumulate
    between = acc(hz, 1) & acc(hz[:, ::-1], 1)[:, ::-1]
    return hz | ((t >= 0x80) & between)


def _pack(rgb):
    c = np.clip(rgb, 0, 255).astype(np.int32)
    return (c[..., 0] << 16) | (c[..., 1] << 8) | c[..., 2]


NB8 = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


def ground_texture(base, out, mask, wrap, noise, amount=1.0):
    """Turn a speckled field (sparse dots on a solid colour) into 16-bit ground.

    Game Boy ground is often one colour with a regular grid of single-pixel dots
    (Balloon Kid's turf, Link's Awakening's paths). 16-bit ground instead has:
      1. the base colour mottled into a few tonal clumps with hard pixel edges,
         which also hides the 8-pixel tile repetition;
      2. pebbles scattered irregularly, of different sizes and tones, lit from
         the top left: lighter ones cast a shadow, darker ones sit in a pit
         with a lit rim;
      3. sparse single-pixel grain.
    All tones are steps along a hue-shifted ramp (fx.ramp_step), the way pixel
    artists shade: shadows turn cooler and richer, light turns warm.
    `noise` = (big, grain, px, bayer) fields anchored to world position, so the
    texture moves with the map. Pixels outside the speckle field are untouched.
    """
    nb, ng, npx, bay = noise
    key = _pack(base)
    nk = [np.roll(key, d, (0, 1)) for d in NB8]
    same = sum((k == key) for k in nk)
    right = nk[4]
    around = sum((k == right) for k in nk)
    speck = mask & (same <= 1) & (around >= 6) & (right != key)
    if speck.sum() < 3:
        return out
    near = ndi.maximum_filter(speck, size=11, mode='wrap' if wrap else 'constant') & mask
    field = near & ~speck & (same >= 6)               # uniform base around the dots
    if not field.any():
        return out
    a = amount
    out = out.copy()
    H, W = speck.shape
    frac = lambda x: x - np.floor(x)

    # base colour under each pixel: its own, or for a dot the colour beside it
    A = np.where(speck[..., None], np.roll(out, (0, -1), (0, 1)), out)
    area = field | speck

    # 1. mottling: tonal clumps, mostly hard edges, a little ordered dither
    v = 0.55 * nb + 0.3 * ng + 0.15 * npx
    lo, hi = v[area].min(), v[area].max()
    v = (v - lo) / max(float(hi - lo), 1e-3)
    lvl = np.clip(np.floor(v * 4 + (bay - 0.5) * 0.5), 0, 3).astype(np.int32)
    ksteps = np.array([-0.9, -0.4, 0.0, 0.45], np.float32) * min(a, 1.4)
    kk = ksteps[lvl]
    local = A.copy()
    local[area] = fx.ramp_step(A[area], kk[area])
    out[area] = local[area]

    # 2. pebbles: each dot moves up to a pixel off the tile grid and varies
    jy = np.floor(frac(npx * 7.31) * 3).astype(np.int32) - 1
    jx = np.floor(frac(npx * 13.7) * 3).astype(np.int32) - 1
    ys, xs = np.nonzero(speck)
    ty, tx = ys + jy[ys, xs], xs + jx[ys, xs]
    if wrap:
        ty, tx = ty % H, tx % W
    ok = (ty >= 0) & (ty < H) & (tx >= 0) & (tx < W)
    ys, xs, ty, tx = ys[ok], xs[ok], ty[ok], tx[ok]
    ok = area[ty, tx]
    ys, xs, ty, tx = ys[ok], xs[ok], ty[ok], tx[ok]
    peb = np.zeros((H, W), bool)
    peb[ty, tx] = True
    colB = np.zeros((H, W, 3), np.float32)
    colB[ty, tx] = base[ys, xs]
    wide = np.zeros((H, W), bool)
    wide[ty, tx] = frac(npx * 3.7)[ys, xs] > 0.55        # some pebbles are 2 pixels wide
    second = fx.shift(wide, 0, 1, False, wrap) & area & ~peb
    colB = np.where(second[..., None], np.roll(colB, (0, 1), (0, 1)), colB)
    peb2 = peb | second
    lum = lambda c: c @ np.array([0.299, 0.587, 0.114], np.float32)
    lighter = peb2 & (lum(colB) > lum(A))
    darker = peb2 & ~lighter
    vary = (frac(npx * 5.3) - 0.5) * 0.8
    # lighter pebbles: lit left pixel, body, and a shadow on the ground below right
    if lighter.any():
        kb = np.where(second, -0.35, 0.25) + vary
        out[lighter] = fx.ramp_step(colB[lighter], kb[lighter])
        sh = fx.shift(lighter, 1, 1, False, wrap) & area & ~peb2
        out[sh] = fx.ramp_step(local[sh], -1.5 * a)
        sh2 = fx.shift(lighter & ~second, 1, 0, False, wrap) & area & ~peb2 & ~sh
        out[sh2] = fx.ramp_step(local[sh2], -0.7 * a)
    # darker dots: a pit, its upper-left lip in shade, its lower-right rim catching light
    if darker.any():
        out[darker] = fx.ramp_step(colB[darker], -0.3 + vary[darker])
        lip = fx.shift(darker, -1, -1, False, wrap) & area & ~peb2
        out[lip] = fx.ramp_step(local[lip], -0.8 * a)
        rim = fx.shift(darker, 1, 1, False, wrap) & area & ~peb2 & ~lip
        out[rim] = fx.ramp_step(local[rim], 1.1 * a)

    # 3. grain
    g = frac(npx * 29.1)
    free = area & ~peb2 & ~fx.dilate(peb2, wrap)
    gl = free & (g > 0.965)
    gd = free & (g < 0.035)
    out[gl] = fx.ramp_step(local[gl], 0.8 * a)
    out[gd] = fx.ramp_step(local[gd], -0.8 * a)
    return out


def water_tiles(rgb, anim_px, wrap):
    """Tiles that look like water: mostly blue, and animated or made of horizontal strokes.

    Works on tile-aligned patches (8x8 blocks). `anim_px` marks pixels of tiles whose
    graphics the game keeps rewriting, which is how most Game Boy games move water.
    """
    H, W, _ = rgb.shape
    th, tw = H // 8, W // 8
    h, s, v = fx.rgb_to_hsv(rgb)
    blue = (h >= 170) & (h <= 265) & (s > 0.3) & (v > 0.15)
    t = lambda m: m.reshape(th, 8, tw, 8).mean(axis=(1, 3))
    blue_t = t(blue.astype(np.float32)) >= 0.3
    key = _pack(rgb)
    hs = (key == np.roll(key, 1, 1)).astype(np.float32)
    vs = (key == np.roll(key, 1, 0)).astype(np.float32)
    varied = t((key != np.roll(key, 1, 1)).astype(np.float32)) > 0.05
    aniso = (t(hs) >= 1.35 * t(vs) + 0.02) & varied
    anim_t = t(anim_px.astype(np.float32)) > 0.5 if anim_px is not None else np.zeros_like(blue_t)
    # water is a tile repeated many times; text and one-off details are not
    blocks = key.reshape(th, 8, tw, 8).transpose(0, 2, 1, 3).reshape(th * tw, 64)
    _, inv, cnt = np.unique(blocks, axis=0, return_inverse=True, return_counts=True)
    repeated = (cnt[inv.ravel()] >= 3).reshape(th, tw)
    wt = blue_t & (anim_t | (aniso & repeated))
    # and water is a body of several tiles, not a lone letter or ornament
    lab, n = ndi.label(wt)
    if n:
        sizes = np.bincount(lab.ravel())
        wt = wt & (sizes[lab] >= 4)
    return np.repeat(np.repeat(wt, 8, 0), 8, 1)


def water_shade(rgb, water, wrap, noise):
    """Recolour water along one hue-shifted ramp: foam and highlight strokes on top,
    a lit surface band, deepening toward the bottom of each body of water."""
    nb, ng, npx, bay = noise
    H, W, _ = rgb.shape
    h, s, v = fx.rgb_to_hsv(rgb)
    bluepx = water & (h >= 170) & (h <= 265) & (s > 0.3)
    if not bluepx.any():
        return rgb
    base = np.median(rgb[bluepx], axis=0).astype(np.float32)
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    lb = float(base @ np.array([0.299, 0.587, 0.114], np.float32))
    k = np.where(lum > lb + 45, 2.4, np.where(lum < lb - 45, -1.6, 0.0))
    rows = np.arange(H, dtype=np.float32)[:, None] + np.zeros((1, W), np.float32)
    top = np.maximum.accumulate(np.where(~water, rows, -1e9), axis=0)
    dy = np.minimum(np.where(water, rows - top, 0), 64)
    k = k + 0.9 * np.exp(-(dy - 1) / 2.0) - 1.4 * np.minimum(dy / 36, 1) + 0.6 * (nb - 0.5)
    k = np.round(k * 2 + (bay - 0.5) * 0.9) / 2           # stepped, with a little dither
    out = rgb.copy()
    out[water] = fx.ramp_step(np.broadcast_to(base, rgb.shape)[water], k[water])
    return out


def generic_shade(rgb, wrap, solid=None, tex=None, strength=0.5, dmg=False, level=1, shade=None,
                  noise=None, anim_px=None, want_water=False):
    """16-bit-style shading from colours alone, for any game.

    1. True checkerboard dither becomes the colour between its two colours.
    2. Speckled fields become ground texture (see ground_texture).
    3. Outlined shapes get soft volume: distance from the outline makes a small
       height map, lit from the top left. Outlines are near-black pixels, or for
       plain Game Boy games (`shade` given) the darkest shade in each shape, since
       there everything is drawn in shades and colour comes from the palette.
       Open areas (floors, sky) are left alone.
    4. Lit pixels lean warm, shaded ones cool.
    5. Ink between two coloured areas takes a dark tint of its neighbours
       ("selective outline"); ink against the lightest colour stays dark.
    `solid` limits the work to a mask (sprites).
    """
    H, W, _ = rgb.shape
    if solid is None:
        solid = np.ones((H, W), bool)
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    if shade is not None:
        smin = shade[solid].min() if solid.any() else 0
        paper = solid & (shade == smin)
    else:
        lmax = np.where(solid, lum, -1).max()
        paper = solid & (lum >= lmax - 1)

    # 1. dither
    key = _pack(rgb)
    diff4 = sum((key != np.roll(key, d, a)) for a, d in ((0, 1), (0, -1), (1, 1), (1, -1)))
    same_diag = ((key == np.roll(key, (1, 1), (0, 1))) & (key == np.roll(key, (-1, -1), (0, 1)))
                 & (key == np.roll(key, (1, -1), (0, 1))) & (key == np.roll(key, (-1, 1), (0, 1))))
    chk = (diff4 == 4) & same_diag & solid
    dith = (fx.box_blur(chk.astype(np.float32), 1, wrap) > 0.75)
    dith = fx.dilate(dith, wrap) & solid
    smooth = np.stack([fx.box_blur(rgb[..., k], 1, wrap) for k in range(3)], -1)
    out = np.where(dith[..., None], smooth, rgb)

    # shape components (plain Game Boy games) and outlines
    lab, n = (ndi.label(solid & ~paper) if (dmg or shade is not None) else (None, 0))
    small = np.zeros(n + 1, bool)
    if n:
        for i, sl in enumerate(ndi.find_objects(lab), 1):
            hh, ww = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
            touches = sl[0].start == 0 or sl[1].start == 0 or sl[0].stop == H or sl[1].stop == W
            small[i] = hh <= 48 and ww <= 48 and not touches
    if shade is not None and n:
        idxs = np.arange(n + 1)
        cmax = np.asarray(ndi.maximum(shade, lab, idxs))
        cmin = np.asarray(ndi.minimum(shade, lab, idxs))
        in_small = small[lab] & (lab > 0)
        ink = ((in_small & (shade == cmax[lab]) & (cmin[lab] < cmax[lab]))
               | (~in_small & (lab > 0) & (shade == 3)))
    else:
        ink = solid & (lum < 56)
    ink &= ~dith

    # water (tile-aligned patches only) is coloured on its own ramp and kept out of
    # the other passes
    water = np.zeros((H, W), bool)
    if noise is not None and H % 8 == 0 and W % 8 == 0:
        water = water_tiles(rgb, anim_px, wrap) & solid
        if water.any():
            out = water_shade(out, water, wrap, noise)
            ink &= ~water
            paper = paper & ~water

    # 2. speckles
    if noise is not None:
        out = ground_texture(rgb, out, solid & ~dith & ~paper & ~water, wrap, noise,
                             amount=1.0 + 0.3 * (level - 1))

    # 3. volume
    vol = np.zeros((H, W), bool)
    h = np.zeros((H, W), np.float32)
    if ink.any():
        enclosed = ndi.binary_fill_holes(ink) & ~ink & solid
        d = ndi.distance_transform_cdt(~ink, metric='chessboard').astype(np.float32)
        h = np.where(enclosed, np.minimum(d, 4), 0)
        vol |= enclosed
    terrain = np.zeros((H, W), bool)
    if dmg and n:
        island = small[lab] & (lab > 0) & ~vol & ~ink & ~water
        terrain = (lab > 0) & ~small[lab] & ~water
        if island.any():
            d = ndi.distance_transform_cdt(island, metric='chessboard').astype(np.float32)
            h = np.where(island, np.minimum(d, 4), h)
            vol |= island
    if vol.any():
        h = fx.box_blur(h, 1, wrap)
        gy, gx = np.gradient(h)
        nrm = np.stack([-gx, -gy, np.ones_like(h)], -1)
        nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
        lam = nrm @ L - L[2]
        k = np.where(vol & ~paper, strength * (1 + 0.8 * (level - 1)) * lam, 0)[..., None]
        warm = np.array([18, 10, -14], np.float32)
        cool = np.array([-14, -6, 22], np.float32)
        out = out * (1 + k) + np.where(k > 0, k * warm * 3, -k * cool * 3)

    # 3b. terrain (plain Game Boy games): lit from above, darker with depth, and
    #     slow variation to break up tile repetition. Pixels stay crisp.
    if terrain.any():
        rows = np.arange(H, dtype=np.float32)[:, None] + np.zeros((1, W), np.float32)
        last_open = np.maximum.accumulate(np.where(~terrain, rows, -1e9), axis=0)
        dy = np.where(terrain, rows - last_open, 0)
        dy = np.minimum(dy, 64)
        rim, depth, var = (0.2, 0.1, 0.1) if level == 1 else (0.32, 0.2, 0.18)
        fac = 1 + rim * np.exp(-(dy - 1) / 2.5) - depth * np.minimum(dy / 40, 1)
        if tex is not None:
            fac = fac + var * (tex - 0.5)
        F = fac[..., None]
        up = out + (np.array([255, 248, 210], np.float32) - out) * np.clip(F - 1, 0, 1) * 0.9
        down = out * np.clip(F, 0, 1) + (1 - np.clip(F, 0, 1)) * np.array([-6, 0, 40], np.float32)
        out = np.where((terrain & ~ink)[..., None], np.where(F > 1, up, down), out)

    # gentle texture inside large flat areas
    if tex is not None:
        flat = solid & ~ink & ~dith & ~paper & (fx.box_blur((lum == np.roll(lum, 1, 1)).astype(np.float32)
                                                   + (lum == np.roll(lum, 1, 0)), 2, wrap) > 1.9)
        out = np.where(flat[..., None], out * (1 + 0.08 * (tex[..., None] - 0.5)), out)

    # 5. selective outline
    body = solid & ~ink & ~paper & ~water
    col_sum = np.zeros((H, W, 3), np.float32)
    cnt = np.zeros((H, W), np.float32)
    touches_paper = np.zeros((H, W), bool)
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        b = fx.shift(body, dy, dx, False, wrap)
        col_sum += np.roll(out, (dy, dx), (0, 1)) * b[..., None]
        cnt += b
        touches_paper |= fx.shift(paper, dy, dx, False, wrap)
    sel = ink & (cnt >= 2) & ~touches_paper
    tint = col_sum / np.maximum(cnt, 1)[..., None] * 0.42 + np.array([4, 0, 12], np.float32)
    out = np.where(sel[..., None], tint, out)
    out = np.clip(out, 0, 255)
    return (out, water) if want_water else out


class LayerState:
    """Everything kept for one BG map between frames."""

    def __init__(self):
        self.key = None
        self.raw = None
        self.attrs = None
        self.idx = None
        self.out = np.zeros((N, N, 3), np.float32)
        self.stale = np.zeros((32, 32), bool)
        self.idle = 0              # frames since the map last changed
        self.settled = False       # whether the settle pass has run since
        self.anim = np.zeros((N, N), np.int8)      # 0 none, 1 water, 2 flower bloom/bed
        self.extra = np.zeros((N, N), np.float32)  # material-specific tone offset
        self.over = np.full((N, N), np.nan, np.float32)  # fixed tone (foam)
        self.mul = np.ones((N, N, 3), np.float32)  # shadow multiplier


class Enhancer:
    def __init__(self, preset):
        self.p = preset
        self.n_big = fx.tile_noise(N, 16, 1)
        self.n_mid = fx.tile_noise(N, 48, 2)
        self.n_grain = fx.tile_noise(N, 128, 4)
        self.n_px = np.random.default_rng(3).random((N, N)).astype(np.float32)
        self.bay = fx.bayer(N, N)
        self._stamp_cache = {}
        self._hash_cache = {}
        self._sprite_cache = {}
        self._mat_cache = {}
        self.generic_level = 1   # 1 subtle, 2 strong (generic shading only)
        self._anim_keys = set()  # tile keys seen animating in place
        self.frame_no = 0
        self._tileset = None
        self._last_cols = {}
        self._layers = {0: LayerState(), 1: LayerState()}
        self.stats = {'full': 0, 'band': 0, 'cached': 0}

    def game_state(self, f):
        ram = f.ram
        r = self.p.RAM
        if 'tileset' not in r:
            return dict(tileset=None, battle=0)
        return dict(tileset=ram[r['tileset']], battle=ram[r['in_battle']])

    def _lut(self, table):
        lut = np.full(256, M['?'], np.uint8)
        if table:
            for t, m in table.items():
                lut[t] = M[m]
        lut[self.p.UI_FIRST_TILE:] = M['U']
        return lut

    def _tile_keys(self, f, ids, bank):
        """Key for each map cell: a 24-bit hash of the tile's pixels.

        Games that load the same graphics into different VRAM slots per area
        (Link's Awakening) are recognised by what a tile looks like, not where it is.
        """
        keys = np.zeros((32, 32), np.int64)
        cache = self._hash_cache
        pairs = np.unique(bank.astype(np.int64) * 1024 + ids)
        for pr in pairs.tolist():
            b, i = divmod(pr, 1024)
            raw = f.tiles[b, i].tobytes()
            h = cache.get(raw)
            if h is None:
                h = int(hashlib.blake2b(raw, digest_size=3).hexdigest(), 16)
                cache[raw] = h
            keys[(bank == b) & (ids == i)] = h
        return keys

    def _materials(self, f, raw, ids, bank, table):
        """(keys, material codes) for the 32x32 map."""
        if getattr(self.p, 'TILE_KEYS', None) and table is not None:
            ck = (ids.tobytes(), bank.tobytes(), hashlib.blake2b(f.tiles.tobytes(), digest_size=8).digest())
            hit = self._mat_cache.get(ck)
            if hit is not None:
                return hit
            keys = self._tile_keys(f, ids, bank)
            tmat = np.full((32, 32), M['?'], np.uint8)
            for k, m in self.p.TILE_KEYS.items():
                tmat[keys == k] = M[m]
            if len(self._mat_cache) > 8:
                self._mat_cache.clear()
            self._mat_cache[ck] = (keys, tmat)
            return keys, tmat
        lut = self._lut(table)
        return raw.astype(np.int64), lut[raw]

    # ------------------------------------------------------------------ BG layer
    def layer(self, f, which, table, vis, off=(0, 0)):
        """Bring the stored layer up to date. `vis` is the 32x32 mask of tiles on screen (plus a
        tile of slack); changes elsewhere are only marked stale and drawn once they scroll in."""
        st = self._layers[which]
        idx, pal, prio, ids, bank = f.layer(which)
        raw = f.maps[which]
        attrs = f.attrs[which]
        tkeys, tmat = self._materials(f, raw, ids, bank, table)
        # `off` anchors texture noise to the world: the window layer shows a copy of
        # part of the screen at another map position, and should get the same texture.
        key = (f.bgpal.tobytes(), f.lcdc & 0x10, id(table), off, self.generic_level)
        self._off = off
        st.off = off
        fresh = st.key != key or st.raw is None
        if fresh:
            # new map, palette or tileset: everything is stale, draw what is on screen
            st.stale = np.ones((32, 32), bool)
            st.raw = np.full_like(raw, -1, dtype=np.int16)
            st.attrs = attrs.copy()
            st.idx = idx.copy()
            self.stats['full'] += 1
        ui_tile = tmat == M['U']
        px_changed = (idx != st.idx).reshape(32, 8, 32, 8).any(axis=(1, 3))
        changed = (raw != st.raw) | (attrs != st.attrs) | (px_changed & ~IS_ANIM[tmat])
        # tiles whose graphics change in place are animated (water, flowers...)
        anim_now = px_changed & (raw == st.raw) & ~fresh
        if anim_now.any():
            self._anim_keys.update(np.unique(tkeys[anim_now]).tolist())
        # Text box tiles are styled in screen space: just store their raw colours.
        ui_new = changed & ui_tile
        if ui_new.any():
            pm = np.repeat(np.repeat(ui_new, 8, 0), 8, 1)
            st.out[pm] = f.bgpal[pal[pm], idx[pm]]
            st.anim[pm] = 0
            st.mul[pm] = 1
        if fresh:
            changed[:] = True
        # A changed tile also changes how its neighbours look: objects up to two
        # tiles tall take colour from the tile below them, shadows fall onto the
        # next row, shore foam reaches into the water. Redraw two tiles around it.
        grow = changed & ~ui_tile
        if grow.any() and not grow.all():
            # at least two tiles, more for this tileset's biggest object (4x4 trees)
            stamps = self.p.STAMPS.get(self._tileset, []) if isinstance(self.p.STAMPS, dict) else self.p.STAMPS
            rad = max([2] + [max(len(rows), len(rows[0])) for rows, _ in stamps])
            g = grow.copy()
            for dy in range(-rad, rad + 1):          # the tile map wraps, so roll
                for dx in range(-rad, rad + 1):
                    g |= np.roll(grow, (dy, dx), (0, 1))
            grow = g
        st.stale |= grow
        # Settle pass: once nothing has changed for a moment, redraw what is on
        # screen from scratch. Anything drawn earlier from stale context (tiles the
        # game hadn't reloaded yet) is cleared, whatever game or effect caused it.
        if grow.any() or fresh:
            st.idle, st.settled = 0, False
        else:
            st.idle += 1
            if st.idle >= SETTLE_FRAMES and not st.settled:
                st.stale |= vis
                st.settled = True
        need = st.stale & vis
        if need.any():
            for r0, rl, c0, cl in self._bands(need):
                self._render_into(st, f, idx, pal, tkeys, tmat, table, r0, rl, c0, cl)
                rr = np.arange(r0 + (0 if rl == 32 else MARGIN), r0 + rl - (0 if rl == 32 else MARGIN)) % 32
                cc = np.arange(c0 + (0 if cl == 32 else MARGIN), c0 + cl - (0 if cl == 32 else MARGIN)) % 32
                st.stale[np.ix_(rr, cc)] = False
                self.stats['band'] += 1
        else:
            self.stats['cached'] += 1
        st.key, st.raw, st.attrs, st.idx = key, raw.copy(), attrs.copy(), idx.copy()
        return st, idx, prio, raw

    @staticmethod
    def _bands(need):
        """Split the tiles to redraw into row groups, each with its own column range."""
        rows = need.any(1)
        bands = []
        if rows.all():
            groups = [(0, 32)]
        else:
            # circular runs of needed rows; runs closer than 2*MARGIN are merged
            start = int(np.argmin(rows))          # a row that is not needed
            order = (np.arange(32) + start) % 32
            groups, cur = [], None
            gap = 0
            for r in order:
                if rows[r]:
                    if cur is not None and gap <= 2 * MARGIN:
                        cur[1] = r
                    else:
                        if cur:
                            groups.append(cur)
                        cur = [r, r]
                    gap = 0
                else:
                    gap += 1
            if cur:
                groups.append(cur)
            groups = [(a, (b - a) % 32 + 1) for a, b in groups]
        for a, n in groups:
            rr = (np.arange(a, a + n)) % 32
            ci = _interval(need[rr].any(0))
            r0, rl = a - MARGIN, n + 2 * MARGIN
            c0, cl = ci[0] - MARGIN, ci[1] + 2 * MARGIN
            if rl >= 32:
                r0, rl = 0, 32
            if cl >= 32:
                c0, cl = 0, 32
            bands.append((r0, rl, c0, cl))
        return bands

    def _animate(self, rgb, st, idx_s, ys, xs):
        """Recolour water and flowers on screen from the current tile pixels."""
        if not st.anim.any():
            return
        a = st.anim[ys, xs]
        if not a.any():
            return
        oy, ox = getattr(st, 'off', (0, 0))
        bay = self.bay[(ys + oy) % N, (xs + ox) % N]
        R = self.p.RAMPS
        w = a == 1
        if w.any():
            yy, xx = ys[w], xs[w]
            t = WATER_T[idx_s[w]] + st.extra[yy, xx]
            o = st.over[yy, xx]
            t = np.where(np.isnan(o), t, o)
            rgb[w] = fx.pick(R['water'], t, bay[w], 0.5) * st.mul[yy, xx]
        w3 = a == 3
        if w3.any():   # generic water: a slow travelling shimmer
            yy, xx = ys[w3] + oy, xs[w3] + ox
            ph = self.frame_no * 0.12
            wave = np.sin(0.55 * yy + 0.21 * xx - ph) + 0.6 * np.sin(0.23 * yy - 0.37 * xx + 0.7 * ph)
            rgb[w3] = rgb[w3] * (1 + 0.045 * wave)[:, None]
        fl = a == 2
        if fl.any():
            yy, xx = ys[fl], xs[fl]
            i = idx_s[fl]
            bed = fx.pick(R['lawn'], st.extra[yy, xx], bay[fl], 0.8)
            bloom = fx.pick(R['petal'], PETAL_T[i])
            rgb[fl] = np.where((i != 0)[:, None], bloom, bed) * st.mul[yy, xx]

    def _stamp_mask(self, idx_patch):
        k = idx_patch.tobytes()
        m = self._stamp_cache.get(k)
        if m is None:
            m = fx.solid_from_outline(idx_patch == 3)
            self._stamp_cache[k] = m
        return m

    def _render_into(self, st, f, idx_full, pal_full, keys_full, tmat_full, table, r0, rl, c0, cl):
        """Render tiles rows r0..r0+rl, cols c0..c0+cl (wrapping) and paste the interior."""
        trows = np.arange(r0, r0 + rl) % 32
        tcols = np.arange(c0, c0 + cl) % 32
        ys = (trows[:, None] * 8 + np.arange(8)).ravel()
        xs = (tcols[:, None] * 8 + np.arange(8)).ravel()
        T = np.ix_(trows, tcols)
        res = self._render_patch(f, idx_full[np.ix_(ys, xs)], pal_full[np.ix_(ys, xs)],
                                 keys_full[T], tmat_full[T], table, ys, xs)
        # keep the margin out unless the patch already spans the whole ring
        my = 0 if rl == 32 else MARGIN * 8
        mx = 0 if cl == 32 else MARGIN * 8
        iy = slice(my, len(ys) - my)
        ix = slice(mx, len(xs) - mx)
        gy, gx = np.ix_(ys[iy], xs[ix])
        for name in ('out', 'anim', 'extra', 'over', 'mul'):
            getattr(st, name)[gy, gx] = res[name][iy, ix]

    def _render_patch(self, f, idx, pal, keys, tmat, table, ys, xs):
        p = self.p
        R = dict(p.RAMPS, **getattr(p, 'RAMP_OVERRIDES', {}).get(self._tileset, {}))
        H, W = idx.shape
        YY = ys[:, None] + 0 * xs[None, :]
        XX = xs[None, :] + 0 * ys[:, None]
        off_y, off_x = self._off
        sel = np.ix_((ys + off_y) % N, (xs + off_x) % N)
        nb, nm, ng, npx, bay = (self.n_big[sel], self.n_mid[sel], self.n_grain[sel],
                                self.n_px[sel], self.bay[sel])
        th, tw = tmat.shape
        mat = np.repeat(np.repeat(tmat, 8, 0), 8, 1)
        tile_mat = mat.copy()
        ch = lambda vals: np.choose(idx, vals)
        wrap = True

        # objects from stamps ------------------------------------------------
        obj = np.zeros((H, W), bool)
        fringe = np.zeros((H, W), bool)
        cx = np.zeros((H, W), np.float32)
        cy = np.zeros((H, W), np.float32)
        rx = np.ones((H, W), np.float32)
        ry = np.ones((H, W), np.float32)
        if table:
            stamps = p.STAMPS.get(self._tileset, []) if isinstance(p.STAMPS, dict) else p.STAMPS
            for rows, code in stamps:
                h, w = len(rows), len(rows[0])
                hit = np.ones((th, tw), bool)
                for dy in range(h):
                    for dx in range(w):
                        hit &= np.roll(keys, (-dy, -dx), (0, 1)) == rows[dy][dx]
                for r, c in zip(*np.nonzero(hit)):
                    py = np.arange(r * 8, r * 8 + h * 8) % H
                    px_ = np.arange(c * 8, c * 8 + w * 8) % W
                    S = np.ix_(py, px_)
                    patch = idx[S]
                    msk = self._stamp_mask(patch)
                    # the ground around an object comes from the tile below it, but
                    # only real floor (not tall grass or flowers growing on it)
                    under = tmat[(r + h) % th, c]
                    under = under if chr(under) in 'glFEC' else M['g']
                    sub = mat[S]
                    sub[~msk] = under
                    mat[S] = sub
                    obj[S] = obj[S] | msk
                    fringe[S] = fringe[S] | (~msk & (patch != 0))
                    oy, ox = np.nonzero(msk)
                    cx[S] = c * 8 + ox.mean()
                    cy[S] = r * 8 + oy.mean()
                    rx[S] = max((ox.max() - ox.min() + 1) / 2, 1)
                    ry[S] = max((oy.max() - oy.min() + 1) / 2, 1)
        # local coordinates for object lighting
        LY, LX = np.mgrid[0:H, 0:W].astype(np.float32)

        # building tiles include ground around the shape (roof corners, eaves)
        game_colours = getattr(p, 'GAME_COLOURS', False)
        if game_colours:
            return self._game_colours(f, idx, pal, mat, obj, fringe, cx, cy, rx, ry,
                                      LY, LX, YY, nb, ng, wrap, npx, bay)
        bld = IS_BUILDING[mat] | ((mat == M['T']) & ~obj)   # plants in pots too
        if bld.any():
            # Only tiles that touch a ground tile, and only one tile deep: this is
            # for roof corners and eaves. A long fill would let far-away tiles
            # (even stale ones not yet reloaded by the game) recolour whole walls.
            g_t = IS_GROUND[tmat]
            near_t = g_t.copy()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    near_t |= fx.shift(g_t, dy, dx, False, wrap)
            near = np.repeat(np.repeat(near_t, 8, 0), 8, 1)
            free = bld & (idx == 0) & near
            reach = fx.dilate(IS_GROUND[mat], wrap) & free
            for _ in range(8):
                n = fx.dilate(reach, wrap) & free
                n = (reach | (n & (fx.shift(reach, 1, 0, False, wrap) | fx.shift(reach, -1, 0, False, wrap)
                                   | fx.shift(reach, 0, 1, False, wrap) | fx.shift(reach, 0, -1, False, wrap))))
                if (n == reach).all():
                    break
                reach = n
            gcodes = mat[IS_GROUND[mat]]
            fill = np.bincount(gcodes, minlength=256).argmax() if gcodes.size else M['g']
            mat[reach] = fill

        out = np.zeros((H, W, 3), np.float32)
        anim = np.zeros((H, W), np.int8)
        extra = np.zeros((H, W), np.float32)
        over = np.full((H, W), np.nan, np.float32)

        # flat materials -------------------------------------------------------
        m = mat == M['g']
        if m.any():
            t = 0.6 + 0.3 * (nb - 0.5) + 0.14 * (nm - 0.5)
            out[m] = fx.pick(R['ground'], t, bay, 0.7)[m]
            speck = m & (tile_mat == M['g']) & (idx != 0) & (npx > 0.35)
            out[speck] = fx.pick(R['specks'], (npx > 0.75).astype(np.float32))[speck]
        lawn_t = 0.5 + 0.35 * (nb - 0.5) + 0.25 * (ng - 0.5) + 0.12 * (npx - 0.5)
        m = mat == M['l']
        if m.any():
            out[m] = fx.pick(R['lawn'], lawn_t, bay, 0.8)[m]
        m = mat == M['f']
        if m.any():
            anim[m] = 2
            extra[m] = lawn_t[m]
        m = mat == M['G']
        if m.any():
            t = ch([0.06, 0.82, 0.52, 0.0]) - 0.07 * ((YY % 8) - 3.5) / 3.5 + 0.10 * (nm - 0.5)
            out[m] = fx.pick(R['tallgrass'], t)[m]
        m = mat == M['W']
        if m.any():
            land = ~m
            n1 = fx.dilate(land, wrap) & m
            n2 = fx.dilate(fx.dilate(land, wrap), wrap) & m & ~n1
            anim[m] = 1
            extra[m] = (0.18 * (nb - 0.5) + 0.14 * n2)[m]
            over[n1] = 0.98
            bank = fx.dilate(m, wrap) & IS_GL[mat]
            out[bank] = fx.pick(R['ground'], np.full((H, W), 0.05, np.float32))[bank]

        # buildings ------------------------------------------------------------
        for code, ramp, vals, noise in (('R', 'roof', [0.86, 0.6, 0.38, 0.04], 0.08),
                                        ('H', 'wall', [0.85, 0.55, 0.35, 0.04], 0.04),
                                        ('N', 'glass', [0.95, 0.68, 0.45, 0.0], 0.0),
                                        ('D', 'door', [0.92, 0.66, 0.42, 0.0], 0.06),
                                        ('S', 'sign', [0.86, 0.62, 0.4, 0.0], 0.06),
                                        ('K', 'rock', [0.85, 0.6, 0.38, 0.05], 0.12),
                                        ('F', 'floor', [0.84, 0.62, 0.44, 0.12], 0.06),
                                        ('C', 'cloth', [0.86, 0.62, 0.42, 0.1], 0.05),
                                        ('M', 'metal', [0.92, 0.64, 0.4, 0.05], 0.03),
                                        ('O', 'furniture', [0.88, 0.64, 0.42, 0.06], 0.08),
                                        ('E', 'earth', [0.8, 0.6, 0.42, 0.12], 0.14),
                                        ('T', 'tree', [0.86, 0.62, 0.42, 0.1], 0.1),
                                        ('P', 'post', [0.9, 0.62, 0.4, 0.0], 0.0)):
            m = mat == M[code]
            if code in 'TP':
                m = m & ~obj      # stamped trees and posts are lit as objects below
            if m.any():
                t = ch(vals) + noise * (ng - 0.5)
                if code == 'N':   # a diagonal glint across windows
                    t = np.where(((XX + off_x + YY + off_y) % 7 < 2) & (idx != 3), t + 0.25, t)
                out[m] = fx.pick(R[ramp], t)[m]

        # ledges: a lit grassy lip, a short dirt face, a shadow below (cast later)
        m = mat == M['L']
        if m.any():
            row = (YY % 8).astype(np.float32)
            lip = row < 3
            tg = ch([0.98, 0.8, 0.6, 0.3]) + 0.06 * (ng - 0.5)
            td = ch([0.7, 0.55, 0.4, 0.12]) - 0.05 * (row - 3) + 0.05 * (ng - 0.5)
            tg = np.where(row == 2, tg + 0.1, tg)          # the lit edge of the lip
            out[m & lip] = fx.pick(R['ground'], tg)[m & lip]
            out[m & ~lip] = fx.pick(R['dirt'], td)[m & ~lip]

        # lit objects ----------------------------------------------------------
        edge = obj & ~fx.erode(obj, wrap)
        lit_edge = edge & ~fx.shift(obj, 1, 1, wrap=wrap)
        nx = np.clip((LX - cx) / rx, -1, 1)
        ny = np.clip((LY - cy) / ry, -1, 1)
        m = obj & (mat == M['T'])
        if m.any():
            nz = np.sqrt(np.clip(1 - nx ** 2 - (ny * 0.9) ** 2, 0, 1))
            lam = np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0, 1)
            leaf = 0.22 * (ng - 0.5) + 0.12 * (npx - 0.5)
            t = 0.42 * ch([0.95, 0.7, 0.5, 0.1]) + 0.62 * lam - 0.06 + leaf
            t = np.where(edge & (idx == 3), np.where(lit_edge, 0.12, 0.0), t)
            out[m] = fx.pick(R['tree'], t)[m]
            trunk = m & (LY - cy > ry * 0.62) & (np.abs(LX - cx) < rx * 0.45)
            out[trunk] = fx.pick(R['trunk'], ch([0.9, 0.6, 0.4, 0.0]))[trunk]
        m = obj & (mat == M['B'])
        if m.any():   # boulders: lit spheres in rock colours
            nz = np.sqrt(np.clip(1 - nx ** 2 - ny ** 2, 0, 1))
            lam = np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0, 1)
            t = 0.4 * ch([0.95, 0.7, 0.5, 0.1]) + 0.6 * lam - 0.05 + 0.1 * (ng - 0.5)
            t = np.where(edge & (idx == 3), np.where(lit_edge, 0.12, 0.0), t)
            out[m] = fx.pick(R['rock'], t)[m]
        m = obj & (mat == M['P'])
        if m.any():
            nz = np.sqrt(np.clip(1 - nx ** 2, 0, 1))
            lam = np.clip((nx * L[0] + nz * L[2] + 0.6) / 1.2, 0, 1)
            t = ch([0.9, 0.62, 0.4, 0.0]) + 0.5 * (lam - 0.5)
            t = np.where(edge & (idx == 3), np.where(lit_edge, 0.15, 0.0), t)
            out[m] = fx.pick(R['post'], t)[m]

        # unknown tiles: the game's own colours, with dither smoothed out --------
        m = mat == M['?']
        if m.any():
            raw_rgb = f.bgpal[pal, idx].astype(np.float32)
            flat = (raw_rgb[m] == raw_rgb[m][0]).all()
            if flat:
                # e.g. the black outside a room: nothing for the generic pass to do
                out[m] = raw_rgb[m]
            else:
                # run the generic pass only on the unlabelled area, plus a margin of
                # context, in tile-aligned steps (the water test works on tiles)
                ty, tx = np.nonzero(m[::8, ::8] | m[7::8, 7::8])
                r0, r1 = max(ty.min() - 2, 0) * 8, min(ty.max() + 3, H // 8) * 8
                c0, c1 = max(tx.min() - 2, 0) * 8, min(tx.max() + 3, W // 8) * 8
                whole = (r0, r1, c0, c1) == (0, H, 0, W)
                Y, X = slice(r0, r1), slice(c0, c1)
                tex = 0.6 * nb[Y, X] + 0.4 * ng[Y, X]
                shade = np.array([(f.bgp >> (2 * i)) & 3 for i in range(4)])[idx[Y, X]] if f.dmg else None
                anim_px = None
                if self._anim_keys:
                    at = np.isin(keys, np.fromiter(self._anim_keys, np.int64))
                    anim_px = np.repeat(np.repeat(at, 8, 0), 8, 1)[Y, X]
                # only the unlabelled pixels take part: their labelled neighbours
                # must not tint them (e.g. a black void's edge next to a forest)
                g_out, g_water = generic_shade(raw_rgb[Y, X], wrap and whole, solid=m[Y, X], tex=tex, dmg=f.dmg,
                                               level=self.generic_level, shade=shade,
                                               noise=(nb[Y, X], ng[Y, X], npx[Y, X], bay[Y, X]),
                                               anim_px=anim_px, want_water=True)
                sub = m[Y, X]
                o = out[Y, X]
                o[sub] = g_out[sub]
                out[Y, X] = o
                a_ = anim[Y, X]
                a_[g_water & sub] = 3      # shimmer each frame
                anim[Y, X] = a_

        # shadows and contact darkening -----------------------------------------
        solid = obj | IS_BUILDING[mat]
        ground_like = IS_GROUND[mat] & ~solid
        cast = (fx.shift(solid, 2, 2, wrap=wrap) | fx.shift(solid, 1, 2, wrap=wrap)
                | fx.shift(solid, 2, 1, wrap=wrap) | fringe) & ground_like
        contact = fx.dilate(solid, wrap) & ground_like & ~cast
        mul = np.ones((H, W, 3), np.float32)
        mul[cast] = (0.62, 0.66, 0.86)
        mul[contact] = 0.86
        out *= mul

        m = mat == M['U']   # text boxes are styled in screen space
        out[m] = f.bgpal[pal, idx][m]
        return dict(out=out, anim=anim, extra=extra, over=over, mul=mul)

    def _game_colours(self, f, idx, pal, mat, obj, fringe, cx, cy, rx, ry, LY, LX, YY, nb, ng, wrap,
                      npx, bay):
        """Keep the game's own colours; add volume, texture and shadows by material.

        For games whose palettes are already good (Link's Awakening DX): what they
        lack next to 16-bit art is light. Objects made of several tiles (a tree is
        4x4) are found as connected regions of their material.
        """
        p = self.p
        H, W = idx.shape
        base = f.bgpal[pal, idx].astype(np.float32)
        # Colour 0 isn't "empty" in these palettes, so no artist-drawn shadow guess.
        fringe = np.zeros((H, W), bool)
        tgrid = mat[::8, ::8].copy()
        for code in getattr(p, 'REGION_OBJECTS', ''):
            lab, n = ndi.label(tgrid == M[code])
            for k in range(1, n + 1):
                tiles = lab == k
                region = np.repeat(np.repeat(tiles, 8, 0), 8, 1)
                ry_, rx_ = np.nonzero(tiles)
                Y = slice(ry_.min() * 8, ry_.max() * 8 + 8)
                X = slice(rx_.min() * 8, rx_.max() * 8 + 8)
                sub = region[Y, X]
                m = fx.solid_from_outline((idx[Y, X] == 3) & sub) & sub
                if m.sum() < 16:
                    m = sub
                full = np.zeros((H, W), bool)
                full[Y, X] = m
                obj |= full
                mat[region & ~full] = M['g']
                oy, ox = np.nonzero(m)
                cx[region] = X.start + ox.mean()
                cy[region] = Y.start + oy.mean()
                rx[region] = max((ox.max() - ox.min() + 1) / 2, 1)
                ry[region] = max((oy.max() - oy.min() + 1) / 2, 1)

        fac = np.ones((H, W), np.float32)
        lamv = np.full((H, W), np.nan, np.float32)
        nx = np.clip((LX - cx) / rx, -1, 1)
        ny = np.clip((LY - cy) / ry, -1, 1)
        g = mat == M['g']
        fac[g] = (1 + 0.12 * (nb - 0.5) + 0.07 * (ng - 0.5))[g]
        G = mat == M['G']
        fac[G] = (1 + 0.08 * (nb - 0.5) - 0.07 * ((YY % 8) - 3.5) / 3.5)[G]
        T = obj & (mat == M['T'])
        if T.any():
            nz = np.sqrt(np.clip(1 - nx ** 2 - ny ** 2, 0, 1))
            lam = np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0, 1)
            lamv[T] = lam[T]
            fac[T] = (0.68 + 0.62 * lam + 0.06 * (ng - 0.5))[T]
        P = obj & (mat == M['P'])
        if P.any():
            nz = np.sqrt(np.clip(1 - nx ** 2, 0, 1))
            lam = np.clip((nx * L[0] + nz * L[2] + 0.6) / 1.2, 0, 1)
            lamv[P] = lam[P]
            fac[P] = (0.78 + 0.45 * lam)[P]
        R = mat == M['R']
        fac[R] = (1.1 - 0.18 * ((LY % 16) / 15.0))[R]
        out = base * fac[..., None]
        out = ground_texture(base, out, g, wrap, (nb, ng, npx, bay))   # dirt paths, sand, turf
        lit = ~np.isnan(lamv)
        k = np.where(lit, lamv - 0.55, 0)[..., None]
        out += np.where(k > 0, k * np.array([30, 18, -20], np.float32), -k * np.array([-24, -10, 34], np.float32))

        unk = mat == M['?']
        if unk.any():
            out[unk] = generic_shade(base, wrap, tex=0.6 * nb + 0.4 * ng)[unk]

        solid = obj | IS_BUILDING[mat]
        ground_like = IS_GROUND[mat] & ~solid
        cast = (fx.shift(solid, 2, 2, wrap=wrap) | fx.shift(solid, 1, 2, wrap=wrap)
                | fx.shift(solid, 2, 1, wrap=wrap) | fringe) & ground_like
        contact = fx.dilate(solid, wrap) & ground_like & ~cast
        # shadows step down the ground's own hue-shifted ramp instead of greying it
        mul = np.ones((H, W, 3), np.float32)
        if cast.any():
            out[cast] = fx.ramp_step(out[cast], -1.6)
        if contact.any():
            out[contact] = fx.ramp_step(out[contact], -0.6)
        out = np.clip(out, 0, 255)
        return dict(out=out, anim=np.zeros((H, W), np.int8), extra=np.zeros((H, W), np.float32),
                    over=np.full((H, W), np.nan, np.float32), mul=mul)

    # ------------------------------------------------------------------ frame
    def render(self, f):
        self.frame_no += 1
        self._tileset = self.game_state(f)['tileset']
        gs = self.game_state(f)
        if getattr(self.p, 'TILE_KEYS', None):
            table = self.p.TILE_KEYS
        else:
            table = None if gs['battle'] else self.p.TILESETS.get(gs['tileset'])
            anchors = getattr(self.p, 'ANCHORS', {}).get(gs['tileset'])
            if table and anchors and not all(
                    hashlib.blake2b(f.tiles[0, int(f.tile_index(t))].tobytes(), digest_size=4).hexdigest() == h
                    for t, h in anchors):
                table = None      # not really this tileset on screen (title, intro...)
        by, bx, wy, wx = np.broadcast_arrays(*f.screen_coords())
        # tiles on screen plus one tile of slack, so scrolling never shows a stale tile
        # by depends only on the line and bx only on the line's SCX, so small sets do
        rows = np.unique(by[:, 0] // 8)
        cols = np.unique(np.concatenate([((np.arange(160) + sx) & 255) // 8
                                         for sx in np.unique(f.scx).tolist()]))
        vis = np.zeros((32, 32), bool)
        vis[np.ix_(np.unique(np.concatenate([rows - 1, rows, rows + 1])) % 32,
                   np.unique(np.concatenate([cols - 1, cols, cols + 1])) % 32)] = True
        bst, bidx, bprio, braw = self.layer(f, f.bg_map(), table, vis)
        win = f.window_mask()
        rgb = bst.out[by, bx]
        sidx = bidx[by, bx]
        self._animate(rgb, bst, sidx, by, bx)
        sprio = bprio[by, bx]
        stid = braw[by // 8, bx // 8]
        ui = self._ui_tiles(braw, by[0, 0] // 8, bx[0, 0] // 8)[by // 8, bx // 8]
        if win.any():
            wvis = np.zeros((32, 32), bool)
            wvis[np.ix_(np.unique(wy // 8), np.unique(wx // 8))] = True
            # world position of the window's top-left pixel (screen position + scroll)
            on, _ = f._window_lines()
            y0 = int(np.argmax(on))
            woff = (int(y0 + f.scy[y0]) % N, int(f.wx[y0] - 7 + f.scx[y0]) % N)
            wst, widx, wprio, wraw = self.layer(f, f.win_map(), table, wvis, woff)
            wrgb = wst.out[wy, wx]
            wsidx = widx[wy, wx]
            self._animate(wrgb, wst, wsidx, wy, wx)
            rgb = np.where(win[..., None], wrgb, rgb)
            sidx = np.where(win, wsidx, sidx)
            sprio = np.where(win, wprio[wy, wx], sprio)
            stid = np.where(win, wraw[wy // 8, wx // 8], stid)
            ui = np.where(win, self._ui_tiles(wraw, 0, 0)[wy // 8, wx // 8], ui)
        self._sprites(f, rgb, sidx, sprio, ui, overworld=table is not None)
        self._textbox(rgb, sidx, stid, ui)
        return fx.snes15(rgb)

    def _ui_tiles(self, raw, oy, ox):
        """Which tiles get the SNES text-box style.

        Border tiles (0x79-0x7E) do, and other text tiles (letters, blanks, HP-bar
        parts) only when a border lies on both sides of them in their row and column.
        So boxes stop at their frame, unframed text (a Pokemon's name in battle) and
        battle sprites that use high tile numbers keep the game's own look.
        Works in screen-aligned order (origin at oy, ox) so a box never wraps.
        """
        r = np.roll(raw, (-oy, -ox), (0, 1))
        ui = r >= self.p.UI_FIRST_TILE
        frame = (r >= 0x79) & (r <= 0x7E)
        acc = np.maximum.accumulate
        left = acc(frame, 1)
        right = acc(frame[:, ::-1], 1)[:, ::-1]
        hframe = _border_rows(r)
        up = acc(frame | hframe, 0)
        down = acc((frame | hframe)[::-1], 0)[::-1]
        inside = left & right & up & down
        ok = ui & (frame | inside)
        return np.roll(ok, (oy, ox), (0, 1))

    # ------------------------------------------------------------------ sprites
    def _sprite_colours(self, f, y, x):
        ram = f.ram
        if 'sprite_data1' not in self.p.RAM:
            return None   # no sprite knowledge: generic sprite shading
        base = self.p.RAM['sprite_data1']
        for n in range(16):
            a = base + 16 * n
            pic = ram[a]
            # NPC positions in RAM can lag the drawn sprite by a few pixels mid-step
            if pic and abs(ram[a + 4] - (y & 255)) <= 4 and abs(ram[a + 6] - (x & 255)) <= 4:
                if n in self.p.SPRITE_SLOT:
                    return self.p.SPRITE_SLOT[n]
                if pic in self.p.SPRITE_PIC:
                    return self.p.SPRITE_PIC[pic]
                cyc = self.p.NPC_CYCLE
                return cyc[pic % len(cyc)]
        return None

    def _sprites(self, f, rgb, sidx, sprio, ui, overworld):
        R = self.p.RAMPS
        groups = {}
        for s in f.sprites():
            groups.setdefault(s['i'] // 4, []).append(s)
        bg_on = f.lcdc & 1
        for g in sorted(groups, reverse=True):   # lower OAM groups end on top
            ss = groups[g]
            y0 = min(s['y'] for s in ss)
            x0 = min(s['x'] for s in ss)
            y1 = max(s['y'] + s['px'].shape[0] for s in ss)
            x1 = max(s['x'] + 8 for s in ss)
            h, w = y1 - y0, x1 - x0
            px = np.zeros((h, w), np.uint8)
            pal = np.zeros((h, w), np.uint8)
            behind = np.zeros((h, w), bool)
            for s in reversed(ss):   # lower OAM index on top, as on hardware
                sh = s['px'].shape[0]
                sl = (slice(s['y'] - y0, s['y'] - y0 + sh), slice(s['x'] - x0, s['x'] - x0 + 8))
                np.copyto(px[sl], s['px'], where=s['px'] != 0)
                np.copyto(pal[sl], s['pal'], where=s['px'] != 0)
                behind[sl] |= s['behind'] & (s['px'] != 0)
            mask = px != 0
            if not mask.any():
                continue
            cols = self._sprite_colours(f, y0, x0) if overworld else None
            # The game's sprite slots can lag a frame behind what's drawn; keep a
            # sprite's colours steady instead of flickering to the plain palette.
            last = self._last_cols.get(g)
            if cols is None and overworld and last and self.frame_no - last[1] < 90                     and abs(last[2] - y0) <= 16 and abs(last[3] - x0) <= 16:
                cols = last[0]
            if cols is not None:
                self._last_cols[g] = (cols, self.frame_no, y0, x0)
            ys, xs = np.mgrid[y0:y1, x0:x1]
            on = (ys >= 0) & (ys < 144) & (xs >= 0) & (xs < 160)
            if cols is None:
                ck = (px.tobytes(), pal.tobytes(), px.shape, f.objpal.tobytes(), getattr(f, 'obp', None))
                col = self._sprite_cache.get(ck)
                if col is None:
                    col = f.objpal[pal, px].astype(np.float32)
                    sh = None
                    if f.dmg:
                        obp = np.array([[(f.obp[k] >> (2 * i)) & 3 for i in range(4)] for k in (0, 1)])
                        sh = np.where(mask, obp[pal & 1, px], 0)
                    col = generic_shade(np.where(mask[..., None], col, 0), False, mask, strength=0.22,
                                        shade=sh)
                    if len(self._sprite_cache) > 1024:
                        self._sprite_cache.clear()
                    self._sprite_cache[ck] = col
            else:
                main, light = cols
                ck = (px.tobytes(), px.shape, main, light)
                col = self._sprite_cache.get(ck)
            if cols is not None and col is None:
                d = np.zeros((h, w), np.float32)
                mm = mask.copy()
                for _ in range(3):
                    mm = fx.erode(mm)
                    d += mm
                hgt = fx.box_blur(d, 1)
                gy, gx = np.gradient(hgt)
                nrm = np.stack([-gx, -gy, np.ones_like(hgt)], -1)
                nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
                shade = 0.55 * (nrm @ L - L[2])
                edge = mask & ~fx.erode(mask)
                lit = edge & ~fx.shift(mask, 1, 1)
                tm = np.choose(px, [0, 0.7, 0.5, 0.0]) + shade
                tm = np.where(px == 3, np.where(lit, 0.2, 0.0), tm)
                col = np.where((px == 1)[..., None], fx.pick(R[light], 0.72 + shade),
                               fx.pick(R[main], tm))
                self._sprite_cache[ck] = col
            if cols is not None and h >= 16:   # soft oval shadow under the feet
                cyy, cxx = y1 - 1.5, (x0 + x1) / 2 - 0.5
                sy0, sy1 = max(int(cyy - 3), 0), min(int(cyy + 4), 144)
                sx0, sx1 = max(int(cxx - 7), 0), min(int(cxx + 8), 160)
                if sy0 < sy1 and sx0 < sx1:
                    yy_, xx_ = np.mgrid[sy0:sy1, sx0:sx1]
                    shadow = ((((yy_ - cyy) / 2.2) ** 2 + ((xx_ - cxx) / 6.5) ** 2) < 1) & ~ui[sy0:sy1, sx0:sx1]
                    rgb[sy0:sy1, sx0:sx1][shadow] *= np.array([0.7, 0.72, 0.85], np.float32)
            hidden = np.zeros((h, w), bool)
            if bg_on:
                yy, xx = np.clip(ys, 0, 143), np.clip(xs, 0, 159)
                hidden = (behind | (sprio[yy, xx] == 1)) & (sidx[yy, xx] != 0)
            draw = mask & on & ~hidden
            rgb[ys[draw], xs[draw]] = col[draw]

    # ------------------------------------------------------------------ text boxes
    def _textbox(self, rgb, sidx, stid, ui):
        if not ui.any():
            return
        steps = fx.hx('#3a56c8', '#3048b8', '#283ca4', '#203090', '#1a267c', '#141e68')
        # vertical position inside each column's run of UI pixels -> stepped gradient
        u = ui.astype(np.int8)
        starts = np.vstack([u[:1], (np.diff(u, axis=0) == 1)])   # run starts
        run_id = np.cumsum(starts, axis=0) * u
        top = np.zeros((144, 160), np.int32)
        length = np.ones((144, 160), np.int32)
        for x in np.nonzero(u.any(0))[0]:
            ids = run_id[:, x]
            for r in np.unique(ids[ids > 0]):
                rows = np.nonzero(ids == r)[0]
                top[rows, x] = rows[0]
                length[rows, x] = len(rows)
        # Prefer each box's own top and bottom border rows, so stacked boxes (a
        # menu over a dialogue box) each get a whole gradient.
        hb = _border_rows(stid)
        rows = np.broadcast_to(SY, hb.shape)
        btop = np.maximum.accumulate(np.where(hb, rows, -1), axis=0)
        bbot = np.minimum.accumulate(np.where(hb, rows, 9999)[::-1], axis=0)[::-1]
        boxed = (btop >= 0) & (bbot < 9999) & (bbot > btop)
        top = np.where(boxed, btop, top)
        length = np.where(boxed, bbot - btop + 1, length)
        k = np.clip(((SY - top) * len(steps) // np.maximum(length, 1)), 0, len(steps) - 1)
        frame_tile = (stid >= 0x79) & (stid <= 0x7E)
        ink = ui & (sidx != 0)
        border = ink & frame_tile
        text = ink & ~frame_tile
        shadow = fx.shift(text, 1, 1) & ui & ~ink
        bg = ui & ~ink
        # Border tiles have a few pixels outside the frame line. Only what the
        # text area reaches without crossing the line is the box's inside.
        inside = bg & ~frame_tile
        for _ in range(8):
            grow = inside.copy()
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                grow |= fx.shift(inside, dy, dx)
            inside = grow & bg
        outside = bg & frame_tile & ~inside
        rgb[bg] = steps[k][bg]
        rgb[outside] = fx.hx('#0c1030')[0]
        bevel = fx.dilate(border) & bg
        rgb[bevel] = fx.hx('#7880c8')[0]
        rgb[shadow] = fx.hx('#060c38')[0]
        rgb[border] = fx.hx('#e8ecf8')[0]
        rgb[text] = fx.hx('#f8f8f8')[0]

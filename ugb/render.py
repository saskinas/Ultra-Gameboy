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
import math
import os

import numpy as np
from scipy import ndimage as ndi
from scipy import sparse as sp
from scipy.sparse import csgraph

from ugb import fx

N = 256
SY, SX = np.mgrid[0:144, 0:160]
L = np.array([-1.0, -1.0, 1.0], np.float32) / np.sqrt(3)   # light from the top left
GROUND = ['g', 'l', 'f', 'G', 'F', 'C', 'E']        # receive shadows
BUILDING = ['R', 'H', 'N', 'D', 'S', 'O', 'M', 'L']   # cast shadows
ANIM = ['W', 'f']
M = {c: ord(c) for c in 'glfGWTPBRHNDSKFCMOELUYhVQZAXJ?'}   # material codes as bytes (fast compares)


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
SKY_REGION = 2500   # line art: white regions bigger than this (pixels) are open sky
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


class _Ramps(dict):
    """A preset's colour ramps; a ramp it doesn't define falls back to neutral grey."""

    def __missing__(self, key):
        return self.get('neutral', fx.hx('#202028', '#505060', '#8a8a98', '#c8c8d0', '#f4f4f8'))


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


_CROSS = ndi.generate_binary_structure(2, 1)


def _wrap(res):
    """An area result's loop width in px (0: it doesn't loop sideways)."""
    return int(res[6]) if res is not None and len(res) > 6 else 0


def _grow4(seed, free, steps, wrap):
    """Grow `seed` through `free` pixels by up to `steps` 4-connected steps."""
    if not wrap:
        return ndi.binary_dilation(seed, _CROSS, iterations=steps, mask=free) | seed
    reach = seed
    for _ in range(steps):
        n = reach | ((fx.shift(reach, 1, 0, False, True) | fx.shift(reach, -1, 0, False, True)
                      | fx.shift(reach, 0, 1, False, True) | fx.shift(reach, 0, -1, False, True)) & free)
        if (n == reach).all():
            break
        reach = n
    return reach


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
        self.drawn = np.zeros((32, 32), bool)      # tiles drawn since the last settle pass
        self.flip_key = None       # graphics of the tiles that animate in place, right now
        self.bar = np.zeros((32, 32), bool)        # status-bar tiles seen in this map
        self.hud = np.zeros((32, 32), bool)        # of those, blank and two-colour (text) tiles
        self.icon = np.zeros((32, 32), bool)       # of those, the preset's HUD icons
        self.kind = None           # line-art regions per pixel (presets with LINE_ART)
        self.book = {}             # flipbook: those graphics -> (layer arrays, valid tiles)
        # 0 none, 1 water, 2 flower bloom/bed, 3 shimmer, 4 backdrop; eye candy
        # (presets' EYE_CANDY): 5 twinkle, 6 glint, 7 water light, 8/9 sway (9: a
        # sky pixel inside a swaying tile)
        self.anim = np.zeros((N, N), np.int8)
        self.extra = np.zeros((N, N), np.float32)  # material-specific tone offset
        self.over = np.full((N, N), np.nan, np.float32)  # fixed tone (foam)
        self.mul = np.ones((N, N, 3), np.float32)  # shadow multiplier


class Enhancer:
    def __init__(self, preset):
        global MARGIN
        MARGIN = getattr(preset, 'MARGIN', 3)     # (one game per process: the app, the tools)
        self._idle_jobs = {}        # map -> work left for idle(): tiles just off screen
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
        self._flip_count = {}    # VRAM tile -> times its graphics changed in place
        self._hud_cache = None   # last status bar: (its input, the styled result)
        self._kind = None        # line-art regions of the layer being drawn
        self._areas = {}         # area key -> (kind map, world x0, y0): solved whole areas
        self._area_job = None    # (key, future) of the area being captured
        self._pool = None
        # doors are gone through ahead of the player in a second worker, so the
        # area the player is in never waits behind one
        self._door_job = None
        self._door_pool = None
        self._refresh = {}        # area key -> {'n': recaptures so far, 'pos': camera at the last}
        self._track = {}          # the camera followed in an area's capture frame (_area_camera)
        self._title_done = False  # (the first area captured from the title screen)
        self._door_queue = []     # (area key, door): to go through ahead of the player (ugb.lineart.through_door)
        self._doors_tried = set()
        self._area_ver = None     # (hash of the code that solves areas: see _area_file)
        self.frame_no = 0
        self.eye_candy = True       # presets' EYE_CANDY effects (the app toggles it)
        # parallax backdrop (presets with make_backdrop): layers, camera, this frame's picture
        self._bd_key = None
        self._bd_layers = None
        self._bd_cam = np.zeros(2)
        self._bd_scroll = None
        self._bd_screen = None
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
            # (a preset may label tiles differently per stage: tile_keys_for)
            tk = self.p.tile_keys_for(f.ram) if hasattr(self.p, 'tile_keys_for') else self.p.TILE_KEYS
            ck = (ids.tobytes(), bank.tobytes(), hashlib.blake2b(f.tiles.tobytes(), digest_size=8).digest(), id(tk))
            hit = self._mat_cache.get(ck)
            if hit is not None:
                return hit
            keys = self._tile_keys(f, ids, bank)
            tmat = np.full((32, 32), M['?'], np.uint8)
            for k, m in tk.items():
                tmat[keys == k] = M[m]
            if len(self._mat_cache) > 8:
                self._mat_cache.clear()
            self._mat_cache[ck] = (keys, tmat)
            return keys, tmat
        lut = self._lut(table)
        return raw.astype(np.int64), lut[raw]

    # ------------------------------------------------------------------ BG layer
    def layer(self, f, which, table, vis, off=(0, 0), bar=None):
        """Bring the stored layer up to date. `vis` is the 32x32 mask of tiles on screen (plus a
        tile of slack); changes elsewhere are only marked stale and drawn once they scroll in."""
        st = self._layers[which]
        idx, pal, prio, ids, bank = f.layer(which)
        raw = f.maps[which]
        attrs = f.attrs[which]
        tkeys, tmat = self._materials(f, raw, ids, bank, table)
        # `off` anchors texture noise to the world: the window layer shows a copy of
        # part of the screen at another map position, and should get the same texture.
        key = (f.bgpal.tobytes(), f.lcdc & 0x10, id(table), off, self.generic_level, self._bd_key)
        self._off = off
        st.off = off
        fresh = st.key != key or st.raw is None
        # Status bar (score, time, lives): blank and two-colour tiles there are text.
        # They are stored as they are, like text boxes, and styled on screen, so a
        # ticking counter redraws only itself instead of a ring of tiles around it.
        hud_before = st.hud | st.icon
        bar_before = st.bar.copy()
        if fresh:
            st.bar[:] = False
        if bar is not None:
            st.bar |= bar
        brows = np.nonzero(st.bar.any(1))[0]              # only the bar's rows
        same = (not fresh and st.idx is not None and (st.bar == bar_before).all()
                and (raw[brows] == st.raw[brows]).all()
                and (idx.reshape(32, 8, 256)[brows] == st.idx.reshape(32, 8, 256)[brows]).all())
        if same:
            if st.hud.any() or st.icon.any():
                tmat = tmat.copy()
                tmat[st.hud | st.icon] = M['U']
        elif len(brows):
            sub = idx.reshape(32, 8, 256)[brows].astype(np.int32)
            bits = np.left_shift(1, sub).reshape(len(brows), 8, 32, 8)
            used = np.bitwise_or.reduce(np.bitwise_or.reduce(bits, axis=3), axis=1)
            ncol = (used & 1) + (used >> 1 & 1) + (used >> 2 & 1) + (used >> 3 & 1)
            st.hud[:] = False
            textish = tmat[brows] == M['?']
            if hasattr(self.p, 'HUD_STYLE'):   # a styled bar also takes labelled text tiles
                textish |= tmat[brows] == M['X']
            st.hud[brows] = st.bar[brows] & textish & (ncol <= 2)
            if st.hud.any():   # blank tiles (sky-like, or plain colour 0 whatever their label) too
                st.hud[brows] |= st.bar[brows] & (((tmat[brows] == M['Y']) & (ncol <= 2)) | (used == 1))
            icons = list(getattr(self.p, 'HUD_STYLE', {}).get('icons', {}))
            st.icon = st.bar & np.isin(raw, icons) if icons else np.zeros((32, 32), bool)
            st.hud &= ~st.icon
            if st.hud.any() or st.icon.any():
                tmat = tmat.copy()
                tmat[st.hud | st.icon] = M['U']
        else:
            st.hud[:] = False
            st.icon[:] = False
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
        changed |= (st.hud | st.icon) != hud_before   # tiles joining or leaving the status bar
        # tiles whose graphics change in place are animated (water, flowers...)
        anim_now = px_changed & (raw == st.raw) & (not fresh)
        tid = (bank.astype(np.int32) << 9) | ids
        if anim_now.any():
            self._anim_keys.update(np.unique(tkeys[anim_now]).tolist())
            for t in np.unique(tid[anim_now & ~IS_ANIM[tmat]]).tolist():
                self._flip_count[t] = self._flip_count.get(t, 0) + 1
        # Flipbook: tiles whose graphics keep changing in place (flashing blocks,
        # coins, waterfalls) would redraw a ring around every copy each time. Keep
        # one finished drawing per animation frame and swap it back in instead.
        flip_hit = None
        if fresh:
            st.book.clear()
            st.flip_key = None
        else:
            flip_ids = sorted(t for t, n in self._flip_count.items() if n >= 2)
            if flip_ids:
                skey = b''.join(f.tiles[t >> 9, t & 511].tobytes() for t in flip_ids)
                if st.flip_key is not None and skey != st.flip_key:
                    names = ('out', 'anim', 'extra', 'over', 'mul')
                    cur = {n: getattr(st, n) for n in names}
                    hit = st.book.pop(skey, None)
                    if hit is not None:
                        arrays, valid = hit
                        st.book[st.flip_key] = (cur, ~st.stale)
                        pm = np.repeat(np.repeat(ui_tile, 8, 0), 8, 1)
                        for n in names:          # text boxes always stay current
                            arrays[n][pm] = cur[n][pm]
                            setattr(st, n, arrays[n])
                        st.stale |= ~valid
                        flip_hit = np.isin(tid, flip_ids)
                    else:
                        st.book[st.flip_key] = ({n: a.copy() for n, a in cur.items()}, ~st.stale)
                    while len(st.book) > 6:
                        st.book.pop(next(iter(st.book)))
                st.flip_key = skey
        if flip_hit is not None:
            changed &= ~(flip_hit & anim_now)   # already drawn for these graphics
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
        grow = changed & ~ui_tile & ~st.bar
        bar_changed = changed & ~ui_tile & st.bar     # status-bar text: just the tile itself
        if grow.any() and not grow.all():
            # at least two tiles, more for this tileset's biggest object (4x4 trees)
            stamps = self.p.STAMPS.get(self._tileset, []) if isinstance(self.p.STAMPS, dict) else self.p.STAMPS
            rad = max([2] + [max(len(rows), len(rows[0])) for rows, _ in stamps])
            g = grow.copy()
            for d in range(1, rad + 1):              # the tile map wraps, so roll
                g |= np.roll(grow, d, 0) | np.roll(grow, -d, 0)
            g2 = g.copy()
            for d in range(1, rad + 1):
                g2 |= np.roll(g, d, 1) | np.roll(g, -d, 1)
            grow = g2
        grow |= bar_changed
        st.stale |= grow
        if grow.any():
            for _, valid in st.book.values():   # stored frames there are out of date
                valid &= ~grow
        # Settle pass: once nothing has changed for a moment, redraw what is on
        # screen from scratch. Anything drawn earlier from stale context (tiles the
        # game hadn't reloaded yet) is cleared, whatever game or effect caused it.
        # Only tiles drawn since the last settle can hold such leftovers, so a
        # scrolling game redraws its new columns, not the whole screen.
        settling = False
        if grow.any() or fresh:
            st.idle, st.settled = 0, False
        else:
            st.idle += 1
            if st.idle >= SETTLE_FRAMES and not st.settled:
                st.stale |= vis & st.drawn
                st.settled = settling = True
        # Line art (white shapes drawn with outlines on a white sky): which white
        # regions are open sky, cloud bodies or hills is a property of the whole
        # map. When it changes (a shape finishes loading), redraw where it changed.
        self._kind = None
        solved = (self._solved_area(f) if getattr(self.p, 'LINE_ART', False) and which == f.bg_map()
                  and off == (0, 0) else None)       # (the background layer only: it is the world)
        if solved is not None:
            cam = self._area_camera(f, solved, tkeys)
            if self._track.get('score', 1.0) < 0.5:
                # the screen isn't in the capture (a part it didn't reach): draw
                # it the per-frame way rather than with shapes from elsewhere
                # (and _area_refresh captures again from here)
                solved = None
        if solved is not None:
            # the area is solved whole (ugb.lineart): look each map pixel up by
            # its world position; redo it when the camera crosses a tile
            akind, ax0, ay0 = solved[:3]
            cx, cy, phx, phy = cam
            look = (id(akind), cx // 8, cy // 8, phx, phy)
            if look != getattr(st, 'kind_look', None) or fresh or st.kind is None:
                st.kind_look = look
                # map column i shows world columns = i + phase (mod 32)
                c0, r0 = cx // 8 - 6, cy // 8 - 6
                wc = c0 + (np.arange(32) + phx // 8 - c0) % 32
                wr = r0 + (np.arange(32) + phy // 8 - r0) % 32
                wx = (wc[:, None] * 8 + np.arange(8)).ravel() - ax0
                wy = (wr[:, None] * 8 + np.arange(8)).ravel() - ay0
                if _wrap(solved):                    # (an area that loops sideways)
                    wx %= _wrap(solved)
                okx = (wx >= 0) & (wx < akind.shape[1])
                oky = (wy >= 0) & (wy < akind.shape[0])
                kind = np.zeros((N, N), np.uint8)
                kind[np.ix_(oky, okx)] = akind[np.ix_(wy[oky], wx[okx])]
                if st.kind is not None and not fresh:
                    kch = (kind != st.kind).reshape(32, 8, 32, 8).any(axis=(1, 3))
                    st.stale |= kch
                    for _, valid in st.book.values():
                        valid &= ~kch
                st.kind = kind
            self._kind = st.kind
        elif getattr(self.p, 'LINE_ART', False):
            # only the screen and two tiles around it: further out the map holds
            # columns the game hasn't rewritten yet (half-loaded clouds and domes)
            area = vis.copy()
            for _ in range(2):
                area = area | np.roll(area, 1, 0) | np.roll(area, -1, 0) | np.roll(area, 1, 1) | np.roll(area, -1, 1)
            moved = area.tobytes() != getattr(st, 'kind_area', None)
            if grow.any() or fresh or st.kind is None or moved:
                st.kind_area = area.tobytes()
                kind = self._line_regions(f, idx, tmat, np.repeat(np.repeat(area, 8, 0), 8, 1))
                if st.kind is not None and not fresh:
                    kch = (kind != st.kind).reshape(32, 8, 32, 8).any(axis=(1, 3))
                    st.stale |= kch
                    for _, valid in st.book.values():   # flipbook frames drawn with the old map
                        valid &= ~kch
                st.kind = kind
            self._kind = st.kind
        need = st.stale & vis
        core = getattr(self, '_vis_core', {}).get(which)
        if core is not None:
            # tiles on screen are drawn now; those in the slack just off screen
            # wait for idle() (spare time between frames), or until they show
            later = need & ~core
            need = need & core
            self._idle_jobs[which] = (st, f, idx, pal, tkeys, tmat, table, later) if later.any() else None
        if need.any():
            for r0, rl, c0, cl in self._bands(need):
                self._render_into(st, f, idx, pal, tkeys, tmat, table, r0, rl, c0, cl)
                rr = np.arange(r0 + (0 if rl == 32 else MARGIN), r0 + rl - (0 if rl == 32 else MARGIN)) % 32
                cc = np.arange(c0 + (0 if cl == 32 else MARGIN), c0 + cl - (0 if cl == 32 else MARGIN)) % 32
                st.stale[np.ix_(rr, cc)] = False
                st.drawn[np.ix_(rr, cc)] = True
                self.stats['band'] += 1
        else:
            self.stats['cached'] += 1
        if settling:
            st.drawn[:] = False
        st.key, st.raw, st.attrs, st.idx = key, raw.copy(), attrs.copy(), idx.copy()
        return st, idx, prio, raw

    IDLE_ROWS = 4      # rows of tiles drawn per idle() call (a few ms of work)

    def idle(self):
        """Draw a few rows of the tiles just off screen that the last frame left
        (see layer); the app calls this in spare time between frames. True when
        it drew something, False when there was nothing left."""
        for which, job in list(self._idle_jobs.items()):
            if job is None:
                continue
            st, f, idx, pal, tkeys, tmat, table, later = job
            later = later & st.stale
            if not later.any():
                self._idle_jobs[which] = None
                continue
            for r0, rl, c0, cl in self._bands(later):
                m = 0 if rl == 32 else MARGIN
                cr = (np.arange(r0 + m, r0 + rl - m)) % 32          # the band's own rows
                cr = cr[later[cr].any(1)][:self.IDLE_ROWS]          # (the first few that need it)
                a = int(cr[0])
                n = int((cr[-1] - a) % 32) + 1
                rr0, rrl = (a - MARGIN, n + 2 * MARGIN) if n + 2 * MARGIN < 32 else (0, 32)
                self._render_into(st, f, idx, pal, tkeys, tmat, table, rr0, rrl, c0, cl)
                mc = 0 if cl == 32 else MARGIN
                rows = (np.arange(a, a + n)) % 32
                cols = np.arange(c0 + mc, c0 + cl - mc) % 32
                st.stale[np.ix_(rows, cols)] = False
                self.stats['idle'] = self.stats.get('idle', 0) + 1
                return True
        return False

    @staticmethod
    def _line_regions(f, idx, tmat, area=None):
        """Per pixel of the 256x256 map: 0 not white, 1 open sky, 2 cloud body, 3 hill,
        4 inside a logo's letters ('J' tiles).

        White pixels are joined into regions (4-connected), with every other
        colour as a wall. Big regions reaching the top of the screen are open
        sky; others are cloud bodies or hills, by which kind of tile ('Z' or 'h')
        holds more of their pixels. With `area` (the screen and a margin, a
        rectangle that may wrap), only that part of the map is looked at: the map
        is rolled so it starts at the corner, cut out, and the result put back."""
        shade = np.array([(f.bgp >> (2 * i)) & 3 for i in range(4)])[idx] if f.dmg else idx
        sy = int(np.bincount(f.scy).argmax())
        if area is None or area.all():
            return Enhancer._regions_core(shade, tmat, sy % N, False)
        rows, cols = area.any(1), area.any(0)
        r0 = int(np.argmax(rows & ~np.roll(rows, 1))) if not rows.all() else 0
        c0 = int(np.argmax(cols & ~np.roll(cols, 1))) if not cols.all() else 0
        h, w = int(rows.sum()), int(cols.sum())
        sub = np.roll(shade, (-r0, -c0), (0, 1))[:h, :w]
        tsub = np.roll(tmat, (-r0 // 8, -c0 // 8), (0, 1))[:h // 8, :w // 8]
        res = Enhancer._regions_core(sub, tsub, (sy - r0) % N, not cols.all())
        out = np.zeros((N, N), np.uint8)
        out[:h, :w] = res
        return np.roll(out, (r0, c0), (0, 1))

    @staticmethod
    def _regions_core(shade, tmat, sy, cut_sides):
        """_line_regions on a block of the map. Everything here is decided from
        the map as it is now (no history), so a redraw always gives the same.

        - Clouds ('Z') and logo letters ('J'): their inside is white that can't
          reach open sky, i.e. white more than two tiles from the shape's tiles. Past the block's edge counts as closed, so a cloud
          the game has only half loaded is not hollow.
        - Hills and domes ('h') are drawn with a dark outer line and a light
          inner band facing their inside, and are often open at the bottom. Sky
          is inside a dome when the nearest solid pixel above it (seen through
          clouds) is such a band, or when it lies between a long leg's band and
          the next outline. The fill runs down through the grass to the land, and
          only right above the land fades into the sky with an ordered dither.
        """
        H, W = shade.shape
        tm = np.repeat(np.repeat(tmat, 8, 0), 8, 1)
        up_ = lambda x, k=1: np.roll(x, k, 0)
        nb4 = lambda x: np.roll(x, 1, 0) | np.roll(x, -1, 0) | np.roll(x, 1, 1) | np.roll(x, -1, 1)
        white = (shade == 0) & (tm != M['U']) & (tm != M['G'])
        # line-art white, decided per pixel (a tile-by-tile choice would leave
        # square edges): white in connected areas of 12 pixels or more; the
        # ground's texture dots are smaller
        wl_, wn_ = ndi.label(white)
        big = np.bincount(wl_.ravel(), minlength=wn_ + 1) >= 12
        big[0] = False
        art = big[wl_] & ~np.isin(tm, [M['K'], M['E'], M['L'], M['B']])   # (not rock or ground texture)
        out = np.where(white & art, 1, 0).astype(np.uint8)  # it starts as open sky

        # ---- enclosed shapes: clouds and logo letters
        # (cloud outlines share their arc tiles with hills: an enclosed region that
        # is at least a quarter cloud-bottom ('Z') tiles is a cloud, else a hill
        # closed off by the ground)
        ty = tmat == M['Y']
        zpx = tm == M['Z']
        for codes, k in (('Zh', 2), ('J', 4)):
            shape_t = np.isin(tmat, [M[c] for c in codes])
            if not shape_t.any():
                continue
            near_t = shape_t.copy()              # sky tiles within two tiles of the shape
            for _ in range(2):
                near_t = near_t | np.roll(near_t, 1, 0) | np.roll(near_t, -1, 0)
                near_t = near_t | np.roll(near_t, 1, 1) | np.roll(near_t, -1, 1)
            zone = white & np.repeat(np.repeat(shape_t | (near_t & ty), 8, 0), 8, 1)
            lab, n = ndi.label(zone)
            if not n:
                continue
            leak = np.zeros(n + 1, bool)
            lk = lab[zone & nb4(white & ~zone)]
            leak[lk] = True
            leak[0] = True
            if k == 2:
                cz_ = np.bincount(lab[zone & zpx], minlength=n + 1)
                ch_ = np.bincount(lab[zone & ~zpx], minlength=n + 1)
                cloudy = cz_ >= 0.25 * (cz_ + ch_)
                out[(lab > 0) & ~leak[lab] & cloudy[lab]] = 2
                out[(lab > 0) & ~leak[lab] & ~cloudy[lab]] = 3
            else:
                out[(lab > 0) & ~leak[lab]] = k

        # ---- domes and hills: an oriented scanline fill
        # Every hill outline is a dark line with a light band on the shape's
        # inside. Along a row, each crossing of an outline (a short run of
        # non-white pixels) therefore says whether we enter (band right of the
        # line) or leave (band left of it). Counting from the left and from the
        # right (never below zero), white with an open shape on both sides is
        # inside. Long solid runs (ground, platforms) reset the counts.
        lit = (shade >= 2)
        bandpx = (shade == 1) & np.isin(tm, [M['h'], M['Z']])
        # crossings are made of non-white pixels; white that isn't line art (the
        # ground's dots) counts as part of the solid around it
        S = ~white | ~big[wl_]
        start = S & ~np.roll(S, 1, 1)
        rid_row = np.cumsum(start, axis=1)
        rid = np.where(S, rid_row + (np.arange(H) * (W + 1))[:, None], 0)
        nr = H * (W + 1) + 1
        xs = np.broadcast_to(np.arange(W, dtype=np.float64)[None, :], (H, W))
        cnt = np.bincount(rid.ravel(), minlength=nr)
        bc = np.bincount(rid.ravel(), weights=bandpx.ravel(), minlength=nr)
        bx = np.bincount(rid.ravel(), weights=(xs * bandpx).ravel(), minlength=nr)
        lc = np.bincount(rid.ravel(), weights=(lit & S).ravel(), minlength=nr)
        lx = np.bincount(rid.ravel(), weights=(xs * (lit & S)).ravel(), minlength=nr)
        with np.errstate(invalid='ignore', divide='ignore'):
            orient = np.sign(np.where((bc > 0) & (lc > 0), bx / np.maximum(bc, 1) - lx / np.maximum(lc, 1), 0))
        orient[0] = 0
        barrier_run = cnt > 24                    # ground, platforms, big blocks
        orient[barrier_run] = 0
        # clouds are settled already (above); their edges don't count here
        cl_touch = np.bincount(rid.ravel(), weights=nb4(out == 2).ravel(), minlength=nr) > 0.5 * cnt
        orient[cl_touch] = 0
        end = S & ~np.roll(S, -1, 1)
        o_px = orient[rid]
        bar_px = barrier_run[rid] & S
        def wind(contrib, bars):
            # running count that never drops below zero (a 'leave' without an
            # 'enter' is ignored), reset by long solid runs
            res = np.zeros((H, W), np.int16)
            w = np.zeros(H, np.int16)
            for x in range(W):
                w = np.maximum(w + contrib[:, x], 0)
                w[bars[:, x]] = 0
                res[:, x] = w
            return res
        wl = wind(np.where(end, o_px, 0), bar_px)
        wr = wind(np.where(start, -o_px, 0)[:, ::-1], bar_px[:, ::-1])[:, ::-1]
        # under a dome's arc: the nearest solid pixel above (seen through clouds)
        # is a band with the dark line 1-4 px above it
        rows_ = np.arange(H)[:, None]
        cols_ = np.arange(W)[None, :]
        bnd = (tm == M['h']) & (shade == 1)
        lin_up = np.zeros_like(bnd)
        for k in range(1, 5):
            lin_up |= np.roll(lit, k, 0)
        band_u = bnd & lin_up
        solid_up = ~white & (tm != M['Z']) & (out != 2)
        upi = np.maximum.accumulate(np.where(solid_up, rows_, -1), axis=0)
        under_arc = (upi >= 0) & band_u[np.maximum(upi, 0), cols_]
        # inside: entered on the left and left on the right; or under an arc with
        # one side agreeing (a shape cut off by the edge)
        inside = white & art & (out == 1) & (((wl > 0) & (wr > 0)) | (under_arc & ((wl > 0) | (wr > 0))))
        # one-row slips: keep what most of the rows around agree on
        inside = (ndi.uniform_filter(inside.astype(np.float32), (9, 1)) > 0.5) & white & art & (out == 1)
        # tidy by shape: drop inside fragments under 80 px; fill pockets of sky
        # that are bordered mostly by the fill (stripes inside a tall hill)
        li, ni = ndi.label(inside)
        if ni:
            keep = np.bincount(li.ravel(), minlength=ni + 1) >= 80
            keep[0] = False
            inside = keep[li]
        out[inside] = 3
        pocket = (out == 1)
        lp, npk = ndi.label(pocket)
        if npk:
            def nbc(mask):
                return sum(np.bincount(lp[pocket & np.roll(mask, sh, ax)], minlength=npk + 1)
                           for sh, ax in ((1, 0), (-1, 0), (1, 1), (-1, 1)))
            by_fill = nbc(out == 3)
            by_other = nbc((out != 3) & (out != 1))
            size = np.bincount(lp.ravel(), minlength=npk + 1)
            fill = (by_fill > by_other) & (size < 3000)
            fill[0] = False
            out[fill[lp]] = 3
        if os.environ.get('UGB_DEBUG_WIND'):
            Enhancer._dbg = (o_px * S, wl, wr, inside, bar_px)
        # dithered bands leave slivers of white beside a hill's inside: part of it
        sky = out == 1
        thin = sky & ~ndi.maximum_filter(ndi.minimum_filter(sky, (1, 4)), (1, 4))
        band = (tm == M['h']) & (shade == 1)
        near = (out == 3) | band
        near = near | np.roll(near, 1, 1) | np.roll(near, -1, 1) | np.roll(near, 2, 1) | np.roll(near, -2, 1)
        out[thin & near] = 3
        rows = np.arange(H)[:, None]
        cols = np.arange(W)[None, :]
        # grass standing on the ground: the white around its blades takes the
        # kind of the white just above it (sky, or the hill it stands in)
        wg = (shade == 0) & (tm == M['G'])
        if wg.any():
            # (the nearest pixel above that isn't this grass's white: if solid, none)
            cand = ~wg
            src = np.maximum.accumulate(np.where(cand, rows, -1), axis=0)
            above = np.where(src >= 0, out[np.maximum(src, 0), cols], 0)
            out[wg] = above[wg]
            # a hill reaches down through the grass to the land, and only there,
            # right above the land tiles, fades into the sky with a dither
            land = np.isin(tm, [M['E'], M['L']]) & (shade > 0)
            down = np.minimum.accumulate(np.where(land, rows, H + 64)[::-1], axis=0)[::-1] - rows
            alpha = np.clip((down - 1) / 6.0, 0, 1)
            out[wg & (above == 3) & (alpha <= fx.bayer(H, W))] = 1
        return out

    def _camera(self, f):
        """The camera's world position and the map's phase: map pixel m shows
        world x = phase + m (mod 256). Usually the phase is 0, but a game may
        start its map afresh somewhere else (Kirby, back out of a door: the
        camera at x 624 with SCX 0). The game's counter gives the coarse part,
        rounded to its 16 px steps; the scroll registers the rest."""
        x, y = self.p.camera(f.ram)
        sx = int(np.bincount(f.scx).argmax())
        sy = int(np.bincount(f.scy).argmax())
        px = int(round((x - sx) / 16.0)) * 16
        py = int(round((y - sy) / 16.0)) * 16
        return sx + px, sy + py, px % N, py % N

    def _area_camera(self, f, have, tkeys):
        """The camera in the frame of an area's capture. The game's counters wrap
        in a tall area (Kirby's tree: every 256 px), so the camera is followed by
        the scroll registers frame to frame, like the capture does. When it has
        to be found afresh (a new area, a loaded state) or stops matching (Kirby
        restarting the area), the counters' reading is tried 256 px either way
        and the one whose tiles match the capture is taken."""
        sx = int(np.bincount(f.scx).argmax())
        sy = int(np.bincount(f.scy).argmax())
        key = self.p.atlas_key(f)
        t = self._track
        wrap = _wrap(have)
        if t.get('key') == key and t.get('id') == id(have[3]):
            t['x'] += (sx - t['sx'] + 128) % N - 128
            t['y'] += (sy - t['sy'] + 128) % N - 128
            t['sx'], t['sy'] = sx, sy
            t['n'] += 1
            # the view can't leave the area: if it seems to, the game has moved
            # its map against the scroll registers (Kirby, dropping fast), so
            # find the camera afresh
            _, x0, y0, hs = have[:4]
            inside = (y0 <= t['y'] and t['y'] + 128 <= y0 + hs.shape[0] * 8
                      and (wrap or (x0 <= t['x'] and t['x'] + 160 <= x0 + hs.shape[1] * 8)))
            if t['n'] % 20 and (inside or t['n'] % 4):
                return t['x'], t['y'], (t['x'] - sx) % N, (t['y'] - sy) % N
            t['score'] = self._align(have, tkeys, t['x'], t['y'], sx, sy)
            if t['score'] >= 0.8 and inside:
                return t['x'], t['y'], (t['x'] - sx) % N, (t['y'] - sy) % N
        x, y = self._camera(f)[:2]
        # (the map's columns and rows sit on 8 px steps of the scroll registers)
        x, y = sx + int(round((x - sx) / 8.0)) * 8, sy + int(round((y - sy) / 8.0)) * 8
        # the counters are right modulo the map's 256 px ring, or in an area that
        # loops sideways, modulo its width (each lap moves the map's phase on)
        xs = [x + i * wrap for i in range(N // math.gcd(wrap, N))] if wrap else [x + i * N for i in (-1, 0, 1)]
        best = max(((self._align(have, tkeys, a, y + j * N, sx, sy), a, y + j * N)
                    for a in dict.fromkeys(xs) for j in (-2, -1, 0, 1, 2)), key=lambda c: c[0])
        if best[0] < 0.95:
            # a coarse counter lags while the camera moves fast: look nearby
            _, bx, by = best
            best = max([best] + [(self._align(have, tkeys, bx + dx, by + dy, sx, sy), bx + dx, by + dy)
                                 for dx in (-16, -8, 0, 8, 16) for dy in (-32, -24, -16, -8, 0, 8, 16, 24, 32)
                                 if dx or dy], key=lambda c: c[0])
        self._track = {'key': key, 'id': id(have[3]), 'x': best[1], 'y': best[2], 'sx': sx, 'sy': sy, 'n': 0,
                       'score': best[0]}
        return best[1], best[2], (best[1] - sx) % N, (best[2] - sy) % N

    @staticmethod
    def _align(have, tkeys, x, y, sx, sy):
        """How well the tiles on screen match the capture with the camera at
        (x, y): the share of the captured screen tiles that are the same tile."""
        _, x0, y0, hs = have[:4]
        wcs = np.arange((x + 7) // 8, (x + 152) // 8)
        wrs = np.arange((y + 7) // 8, (y + 120) // 8)
        ac, ar = wcs - x0 // 8, wrs - y0 // 8
        if _wrap(have):
            ac %= _wrap(have) // 8
        okc = (ac >= 0) & (ac < hs.shape[1])
        okr = (ar >= 0) & (ar < hs.shape[0])
        if not okc.any() or not okr.any():
            return 0.0
        want = hs[np.ix_(ar[okr], ac[okc])]
        mc = (wcs[okc] - (x - sx) // 8) % 32
        mr = (wrs[okr] - (y - sy) // 8) % 32
        got = tkeys[np.ix_(mr, mc)]
        known = want >= 0
        return float(((want == got) & known).sum()) / max(int(known.sum()), 1) * known.mean()

    def _solved_area(self, f):
        """The current area solved whole, or None while it is being captured (a
        worker process runs ugb.lineart.solve_area on a copy of the state). If the
        player later reaches parts the capture didn't (an area that starts on a
        locked screen), it is captured again from there and merged."""
        if not (hasattr(self.p, 'SWEEP') and hasattr(self.p, 'atlas_key')) or not hasattr(f, 'pb'):
            return None
        import concurrent.futures
        import concurrent.futures.process
        from ugb import lineart
        if self._pool is None:
            # start the worker now (title screen, stage intro) so its imports are
            # done when the first area needs it
            self._pool = concurrent.futures.ProcessPoolExecutor(max_workers=1)
            self._pool.submit(lineart.warm, self.p.__name__)
        job = self._area_job
        if job is not None and job[1].done():
            if isinstance(job[1].exception(), concurrent.futures.process.BrokenProcessPool):
                self._pool = None                     # the worker died: start a new pool
            self._area_job = None
            try:
                res = job[1].result()
                if job[0] == 'title':                 # an area captured ahead of the player
                    if res is not None and res[0] not in self._areas:
                        self._areas[res[0]] = self._queue_doors(res[0], res[1])
                        self._area_save(res[0], self._areas[res[0]])
                else:
                    res = self._queue_doors(job[0], res)
                    self._areas[job[0]] = res
                    self._area_save(job[0], res)
            except Exception as e:
                if type(e).__name__ != 'LeftArea':     # (caught mid-transition: try again)
                    print('area capture failed:', e)      # (keep playing with the per-frame code)
                    if job[0] != 'title':
                        self._areas.setdefault(job[0], None)
            job = None
        key = self.p.atlas_key(f)
        if key is None:
            # on the title screen: start the game in a copy and capture the first
            # area, so it is ready the moment the player starts
            sw = self.p.SWEEP
            if (job is None and not self._title_done and 'start_game' in sw
                    and sw.get('on_title', lambda m: False)(f.ram)):
                self._title_done = True
                import io
                buf = io.BytesIO()
                f.pb.save_state(buf)
                self._area_job = ('title', self._pool.submit(lineart.precapture, f.pb.gamerom,
                                                             buf.getvalue(), self.p.__name__))
            return None
        have = self._areas.get(key, False)
        self._doors_ahead(f, key, have)
        if have is False:                             # (kept from an earlier session?)
            have = self._area_load(key)
            if have is not False:
                self._areas[key] = have
        if have is False:
            if job is None:
                self._area_submit(f, key, None)
            return None
        if have is not None and job is None:
            self._area_refresh(f, key, have)
        return have

    def _doors_ahead(self, f, key, have):
        """The door worker: collect a finished door, then start the next one
        (once the player's area is known): the nearest door in this area first,
        the one the player is likeliest to take."""
        import concurrent.futures
        import concurrent.futures.process
        from ugb import lineart
        job = self._door_job
        if job is not None and job.done():
            self._door_job = None
            if isinstance(job.exception(), concurrent.futures.process.BrokenProcessPool):
                self._door_pool = None
            try:
                res = job.result()
                if res is not None and res[0] not in self._areas:
                    self._areas[res[0]] = self._queue_doors(res[0], res[1])
                    self._area_save(res[0], self._areas[res[0]])
            except Exception as e:
                if type(e).__name__ != 'LeftArea':
                    print('door capture failed:', e)
        if self._door_job is not None or have is False or not self._door_queue:
            return
        cx = self._track.get('x', 0) if self._track.get('key') == key else 0
        here = [i for i, (k, d) in enumerate(self._door_queue) if k == key]
        i = min(here, key=lambda i: abs(self._door_queue[i][1][2] * 8 - cx - 80)) if here else 0
        _, d = self._door_queue.pop(i)
        known = tuple(k for k, v in self._areas.items() if v is not None) + self._disk_keys()
        if self._door_pool is None:
            self._door_pool = concurrent.futures.ProcessPoolExecutor(max_workers=1)
        self._door_job = self._door_pool.submit(lineart.through_door, f.pb.gamerom, d, self.p.__name__, known)

    def _disk_keys(self):
        """Areas kept from earlier sessions by the current code (no need to go
        through a door to capture them again)."""
        import glob
        pat = self._area_file(('*',))
        out = []
        for path in glob.glob(pat):
            mid = os.path.basename(path)[len(self.p.TITLE.replace(' ', '')) + 1:-len(self._area_ver) - 5]
            try:
                out.append(tuple(int(v) for v in mid.split('-')))
            except ValueError:
                pass
        return tuple(out)

    def _area_file(self, key):
        """Where a solved area is kept between sessions: cache/areas, named by
        the game, the area and a hash of the code that solved it (so a change to
        the solver or the preset never reuses old results)."""
        if self._area_ver is None:
            import hashlib
            import importlib
            import inspect
            from ugb import atlas, lineart
            h = hashlib.blake2b(digest_size=6)
            for mod in (atlas, lineart, importlib.import_module(self.p.__name__)):
                try:
                    h.update(open(inspect.getsourcefile(mod), 'rb').read())
                except (TypeError, OSError):     # (the packaged app has no sources: its code, then)
                    import marshal
                    h.update(marshal.dumps(mod.__spec__.loader.get_code(mod.__name__)))
            self._area_ver = h.hexdigest()
        name = '%s_%s_%s.npz' % (self.p.TITLE.replace(' ', ''), '-'.join(map(str, key)), self._area_ver)
        from ugb.paths import data_path
        return data_path('cache', 'areas', name)

    def _area_save(self, key, res):
        if res is None or len(res) < 5:
            return
        try:
            path = self._area_file(key)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            np.savez_compressed(path, kind=res[0], x0=res[1], y0=res[2], hashes=res[3], shade=res[4],
                                wrap=_wrap(res))
        except OSError as e:
            print('could not keep the area:', e)

    def _area_load(self, key):
        """A solved area kept from an earlier session, or False."""
        try:
            path = self._area_file(key)
            if not os.path.exists(path):
                return False
            d = np.load(path)
            return (d['kind'], int(d['x0']), int(d['y0']), d['hashes'], d['shade'], [],
                    int(d['wrap']) if 'wrap' in d else 0)
        except Exception:
            return False

    def _queue_doors(self, key, res):
        """Queue an area's doors (the areas behind them are captured next, by
        ugb.lineart.through_door, while the player plays here); returns the
        result without them."""
        if res is None or len(res) <= 5:
            return res
        for d in res[5]:
            dk = (key, d[1], d[2])
            if dk not in self._doors_tried:
                self._doors_tried.add(dk)
                self._door_queue.append((key, d))
        return (*res[:5], [], _wrap(res))

    def _area_submit(self, f, key, prev):
        import concurrent.futures
        import io
        from ugb import lineart
        if self._pool is None:
            self._pool = concurrent.futures.ProcessPoolExecutor(max_workers=1)
        buf = io.BytesIO()
        f.pb.save_state(buf)
        fut = self._pool.submit(lineart.solve_area, f.pb.gamerom, buf.getvalue(), self.p.__name__, prev)
        self._area_job = (key, fut)

    def _area_refresh(self, f, key, have):
        """Capture again from here when the screen, or the screen ahead or behind,
        shows tiles the area's capture doesn't have, or the screen matches the
        capture nowhere (a part it didn't reach). At most 8 times an area, and
        only once the camera has moved on since the last try."""
        if len(have) < 5:
            return
        _, x0, y0, hs = have[:4]
        t = self._track
        tracked = t.get('key') == key and t.get('id') == id(hs)
        cx, cy = (t['x'], t['y']) if tracked else self._camera(f)[:2]
        lost = tracked and t.get('score', 1.0) < 0.5
        if not lost:
            cols = np.arange((cx - 160) // 8, (cx + 320) // 8) - x0 // 8
            if _wrap(have):
                cols %= _wrap(have) // 8
            rows = np.arange(cy // 8, (cy + 128) // 8) - y0 // 8
            okc = (cols >= 0) & (cols < hs.shape[1])
            okr = (rows >= 0) & (rows < hs.shape[0])
            seen = np.zeros((len(rows), len(cols)), bool)
            seen[np.ix_(okr, okc)] = hs[np.ix_(rows[okr], cols[okc])] >= 0
            # the screen counts wherever it is; the screens either side only
            # within what was captured (past that may simply be the area's end)
            onscr = (np.arange(len(cols)) >= 20) & (np.arange(len(cols)) < 40)
            if seen[:, onscr | okc].mean() > 0.95:
                return
        r = self._refresh.setdefault(key, {'n': 0, 'pos': None})
        if r['n'] >= 8 or (r['pos'] is not None and abs(cx - r['pos'][0]) + abs(cy - r['pos'][1]) < 48):
            return
        r['n'] += 1
        r['pos'] = (cx, cy)
        self._area_submit(f, key, have)

    @staticmethod
    def _bands(need):
        """Split the tiles to redraw into bands: groups of rows, and within each,
        groups of columns. Groups closer than 2*MARGIN are merged (they'd share
        their margins anyway), so far-apart changes don't redraw everything between."""
        def groups(mask):
            if mask.all():
                return [(0, 32)]
            start = int(np.argmin(mask))          # a cell that is not needed
            out, cur, gap = [], None, 0
            for i in (np.arange(32) + start) % 32:
                if mask[i]:
                    if cur is not None and gap <= 2 * MARGIN:
                        cur[1] = i
                    else:
                        if cur:
                            out.append(cur)
                        cur = [i, i]
                    gap = 0
                else:
                    gap += 1
            if cur:
                out.append(cur)
            return [(a, (b - a) % 32 + 1) for a, b in out]

        bands = []
        for a, n in groups(need.any(1)):
            rr = (np.arange(a, a + n)) % 32
            r0, rl = a - MARGIN, n + 2 * MARGIN
            if rl >= 32:
                r0, rl = 0, 32
            for c, cn in groups(need[rr].any(0)):
                c0, cl = c - MARGIN, cn + 2 * MARGIN
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
        R = _Ramps(self.p.RAMPS, **getattr(self.p, 'RAMP_BY_BACKDROP', {}).get(self._bd_key, {}))
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
        w4 = (a == 4) | (a == 9)     # (9: sky inside a swaying tile; the sway moves it below)
        if w4.any() and self._bd_screen is not None:   # parallax backdrop behind open sky
            rgb[w4] = self._bd_screen[w4]
        ec = getattr(self.p, 'EYE_CANDY', {}) if self.eye_candy else {}
        if ec and (a >= 5).any():
            self._eye_candy(rgb, st, a, ys, xs, oy, ox, ec)
        fl = a == 2
        if fl.any():
            yy, xx = ys[fl], xs[fl]
            i = idx_s[fl]
            bed = fx.pick(R['lawn'], st.extra[yy, xx], bay[fl], 0.8)
            bloom = fx.pick(R['petal'], PETAL_T[i])
            rgb[fl] = np.where((i != 0)[:, None], bloom, bed) * st.mul[yy, xx]

    def _eye_candy(self, rgb, st, a, ys, xs, oy, ox, ec):
        """Effects on pixels the preset marked (anim 5-9), strengths from its
        EYE_CANDY dict (0 or missing: off). All work on screen pixels only."""
        fn = self.frame_no

        def hsh(*v):          # a repeatable 0..1 value per position (and time slot)
            h = np.zeros_like(v[0], dtype=np.int64)
            for k, x in zip((73856093, 19349663, 83492791), v):
                h ^= np.asarray(x, np.int64) * k
            return ((h * 2654435761) >> 7 & 0xffff) / 65535.0

        bd = self._bd_screen
        s = ec.get('twinkle', 0)
        m = a == 5
        if s and m.any():     # stars pulse, each tile on its own phase
            wy, wx = (ys[m] + oy) % N, (xs[m] + ox) % N
            ph = fn * 0.09 + hsh(wy // 8, wx // 8) * 6.283
            k = 1 + s * (0.3 * np.sin(ph) - 0.05)
            rgb[m] = np.clip(rgb[m] * k[:, None], 0, 255)
        s = ec.get('glint', 0)
        m = (a == 6) | np.isin(a, ec.get('glint_on', ())) if s else None
        if s and m.any():     # a few water pixels flash white for a moment
            wy, wx = (ys[m] + oy) % N, (xs[m] + ox) % N
            lit = hsh(wy, wx, fn // 5) < 0.02 * s
            if lit.any():
                v = rgb[m]
                v[lit] = v[lit] * 0.25 + np.array([255, 255, 250], np.float32) * 0.75
                rgb[m] = v
        m = a == 7
        sw, sc = ec.get('wobble', 0), ec.get('caustics', 0)
        if (sw or sc) and m.any():   # under water: lines sway sideways, light ripples
            yy, xx = ys[m], xs[m]
            wy, wx = (yy + oy) % N, (xx + ox) % N
            v = rgb[m]
            if sw:
                dx = np.rint(sw * np.sin(wy * 0.42 + fn * 0.09)).astype(int)
                src = (xx + dx) % N
                ok = st.anim[yy, src] == 7
                v = np.where(ok[:, None], st.out[yy, src], v)
            if sc:
                c = (np.sin(0.33 * wx + 0.17 * wy - fn * 0.06)
                     + np.sin(-0.21 * wx + 0.31 * wy + fn * 0.045))
                light = np.clip(c - 1.15, 0, 1) * sc
                v = np.clip(v + light[:, None] * np.array([70, 90, 80], np.float32), 0, 255)
            rgb[m] = v
        s = ec.get('sway', 0)
        m = (a == 8) | (a == 9)
        if s and m.any():     # tips of grass and fronds sway, the tile's foot stays put
            yy, xx = ys[m], xs[m]
            wy, wx = (yy + oy) % N, (xx + ox) % N
            dx = np.rint(s * np.sin(0.5 * (wx // 8) + fn * 0.05) * (1 - (wy % 8) / 7.0)).astype(int)
            src = (xx - dx) % N
            sa = st.anim[yy, src]
            v = st.out[yy, src].astype(np.float32)
            if bd is not None:
                sky = (sa == 4) | (sa == 9)
                v = np.where(sky[:, None], bd[m], v)
            rgb[m] = v

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
        # keep the margin out unless the patch already spans the whole ring
        my = 0 if rl == 32 else MARGIN * 8
        mx = 0 if cl == 32 else MARGIN * 8
        self._patch_core = (my // 8, mx // 8)     # (tiles of margin: context only, not kept)
        res = self._render_patch(f, idx_full[np.ix_(ys, xs)], pal_full[np.ix_(ys, xs)],
                                 keys_full[T], tmat_full[T], table, ys, xs)
        self._patch_core = (0, 0)
        iy = slice(my, len(ys) - my)
        ix = slice(mx, len(xs) - mx)
        gy, gx = np.ix_(ys[iy], xs[ix])
        for name in ('out', 'anim', 'extra', 'over', 'mul'):
            getattr(st, name)[gy, gx] = res[name][iy, ix]

    def _render_patch(self, f, idx, pal, keys, tmat, table, ys, xs):
        p = self.p
        R = _Ramps(p.RAMPS, **getattr(p, 'RAMP_OVERRIDES', {}).get(self._tileset, {}),
                   **getattr(p, 'RAMP_BY_BACKDROP', {}).get(self._bd_key, {}))
        H, W = idx.shape
        YY = ys[:, None] + 0 * xs[None, :]
        XX = xs[None, :] + 0 * ys[:, None]
        off_y, off_x = self._off
        sel = np.ix_((ys + off_y) % N, (xs + off_x) % N)
        nb, nm, ng, npx, bay = (self.n_big[sel], self.n_mid[sel], self.n_grain[sel],
                                self.n_px[sel], self.bay[sel])
        th, tw = tmat.shape
        if (tmat == M['A']).any():
            # A fill tile (one plain shade) can be the inside of a platform or a
            # band of sky. It is lawn when connected to ground tiles, else sky.
            amb = tmat == M['A']
            grounded = IS_GROUND[tmat] | (tmat == M['L']) | (tmat == M['E'])
            lab, _ = ndi.label(amb | grounded)       # 4-connected
            reach = amb & np.isin(lab, np.unique(lab[grounded]))
            tmat = tmat.copy()
            tmat[amb] = np.where(reach[amb], M['l'], M['Y'])
        for a, b in getattr(p, 'TILE_FOLLOWS', {}).items():
            # a plain tile shared by two materials (Kirby's blank white: plaster,
            # and the middle of a marble diamond) takes the other one where
            # that one surrounds it (three sides or more)
            ta, tb = tmat == M[a], tmat == M[b]
            if ta.any() and tb.any():
                n = (fx.shift(tb, 1, 0, False, False).astype(np.int8) + fx.shift(tb, -1, 0, False, False)
                     + fx.shift(tb, 0, 1, False, False) + fx.shift(tb, 0, -1, False, False))
                tmat = np.where(ta & (n >= 3), M[b], tmat).astype(np.uint8)
        idx_raw = idx                 # colour numbers, for the game's own palette
        if f.dmg:
            # plain Game Boy: ramps go by shade (0 white .. 3 black), not raw colour
            idx = np.array([(f.bgp >> (2 * i)) & 3 for i in range(4)])[idx]
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
        if getattr(p, 'NO_EAVES', ''):      # (materials whose white is their own: a wall's plaster)
            bld &= ~np.isin(mat, [M[c] for c in p.NO_EAVES])
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
            reach = _grow4(fx.dilate(IS_GROUND[mat], wrap) & free, free, 8, wrap)
            gcodes = mat[IS_GROUND[mat]]
            fill = np.bincount(gcodes, minlength=256).argmax() if gcodes.size else M['g']
            mat[reach] = fill

        # Open sky: white pixels in other tiles (around clouds, trees, letters, the
        # space above a grassy edge) that connect to the sky without crossing an
        # outline are sky too. Kept local, like the building fill.
        sky0 = mat == M['Y']
        if sky0.any():
            # (text boxes stay as they are; ground and rock keep their own white)
            free = ~sky0 & (idx == 0) & ~obj & ~np.isin(mat, [M['U'], M['L'], M['E'], M['K'], M['B'],
                                                             M['V'], M['Q'], M['F'], M['O'], M['H'], M['M'], M['D']])   # (canopy white reachable from the sky is sky; not a wall's mortar or marble)
            reach = _grow4(fx.dilate(sky0, wrap) & free, free, 24, wrap)
            mat[reach] = M['Y']

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
        if m.any() and getattr(p, 'CLEAN_GRASS', False):
            # clean foliage: white shapes are leaves (lit along their top), lone
            # white dots and the colour behind them are one smooth backdrop, ink
            # is a dark outline; no texture noise
            white = idx == 0
            near = (fx.shift(white, 1, 0, False, wrap) | fx.shift(white, -1, 0, False, wrap)
                    | fx.shift(white, 0, 1, False, wrap) | fx.shift(white, 0, -1, False, wrap))
            leaf = white & near
            stroke = idx >= 2
            # behind the leaves: exactly the ground body ('E'), so the band joins it
            back = m & ~leaf & ~stroke
            if self._kind is not None:   # white that is open sky (above the ground)
                skyp = self._kind[np.ix_(ys, xs)] == 1
                leaf &= ~skyp
                back &= ~skyp
            out[back] = fx.pick(R['earth'], ch([0.8, 0.6, 0.42, 0.12]) + 0.14 * (ng - 0.5))[back]
            top = leaf & ~fx.shift(leaf, 1, 0, False, wrap)
            bottom = leaf & ~fx.shift(leaf, -1, 0, False, wrap)
            t = np.where(top, 0.98, np.where(bottom, 0.68, 0.84))
            t = np.where(leaf, t, np.where(idx == 3, 0.02, 0.18))
            fg = m & (leaf | stroke)
            out[fg] = fx.pick(R['tallgrass'], t)[fg]
            if 'berry' in p.RAMPS:
                # round white blobs among the leaves are berries: glossy, lit top-left
                lb_, nb_ = ndi.label(leaf)
                if nb_:
                    idxs = np.arange(1, nb_ + 1)
                    area = ndi.sum(leaf, lb_, idxs)
                    sl = ndi.find_objects(lb_)
                    # berries: round blobs as tall as wide, filling most of their box,
                    # and big enough (Kirby's are 6x6 discs of 24 px; the leaf
                    # shapes below them are 5x5 or smaller)
                    roundish = np.array([a >= 20 and (q[0].stop - q[0].start) == (q[1].stop - q[1].start)
                                         and a >= 0.6 * (q[0].stop - q[0].start) * (q[1].stop - q[1].start)
                                         for a, q in zip(area, sl)])
                    bm = np.concatenate([[False], roundish])[lb_] & leaf
                    if bm.any():
                        hi = bm & ~fx.shift(bm, 1, 1, False, wrap)
                        lo = bm & ~fx.shift(bm, -1, -1, False, wrap)
                        tb = np.where(hi, 0.95, np.where(lo, 0.45, 0.68))
                        out[bm] = fx.pick(R['berry'], tb)[bm]
        elif m.any():
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
                                        ('P', 'post', [0.9, 0.62, 0.4, 0.0], 0.0),
                                        ('V', 'pipe', [0.9, 0.62, 0.4, 0.05], 0.0),
                                        ('Q', 'gold', [0.92, 0.66, 0.42, 0.12], 0.0)):
            m = mat == M[code]
            if code in 'TPVQ':
                m = m & ~obj      # stamped objects are lit below
            if m.any():
                t = ch(vals) + noise * (ng - 0.5)
                if code == 'N':   # a diagonal glint across windows
                    t = np.where(((XX + off_x + YY + off_y) % 7 < 2) & (idx != 3), t + 0.25, t)
                out[m] = fx.pick(R[ramp], t)[m]
        # a cliff's dithered side (the same tile as a tall hill's edge, where it
        # is ground): the shaded side of the ground, one smooth darker tone
        if getattr(p, 'LINE_EDGE_TILES', None):
            et2 = np.repeat(np.repeat(np.isin(keys, p.LINE_EDGE_TILES), 8, 0), 8, 1) & (mat == M['E'])
            if et2.any():
                out[et2] = fx.pick(R['earth'], np.where(idx >= 2, 0.1, 0.42) + 0.05 * (ng - 0.5))[et2]

        # ledges drawn from their ground line: above it, a ledge tile belongs to
        # what stands on the ground (a dome's foot): draw it as a hill outline
        ledge_up = None
        if getattr(p, 'LEDGE_FROM_LINE', False) and (mat == M['L']).any():
            from ugb import lineart
            lm = mat == M['L']
            ledge_up = lm & ~lineart.below_ledge_line(idx, lm, (np.arange(H) // 8) * 8)
            mat[ledge_up] = M['h']
        # tiles the game uses both as a cliff's side and as a tall hill's edge:
        # with line art on both sides (not ground on one), draw them as the hill's
        if self._kind is not None and getattr(p, 'LINE_EDGE_TILES', None):
            et = np.repeat(np.repeat(np.isin(keys, p.LINE_EDGE_TILES), 8, 0), 8, 1)
            if et.any():
                art_ = self._kind[np.ix_(ys, xs)] > 0
                lft = np.zeros((H, W), bool)
                rgt = np.zeros((H, W), bool)
                for k in range(1, 9):
                    lft |= fx.shift(art_, 0, k, False, False)
                    rgt |= fx.shift(art_, 0, -k, False, False)
                mat[et & lft & rgt] = M['h']
        # status-bar text ('X'): the paper around the letters is sky; the letters
        # themselves are painted solid with a drop shadow once the sky is down
        txt = mat == M['X']
        txt_ink = txt & (idx >= 2)
        if txt.any():
            mat[txt & ~txt_ink] = M['Y']
        # sky: a stepped vertical gradient, deeper at the top
        sky = mat == M['Y']
        hill_line = (mat == M['h']) & (idx >= 2)
        if sky.any() or hill_line.any():
            # outline hills: anything below a hill's outline in its column is inside it
            under = np.maximum.accumulate(hill_line, axis=0) & ~hill_line
            inside = under & (sky | (mat == M['h']))
            if self._kind is not None:
                inside[:] = False       # line art: regions decide (below)
            t = 1.0 - np.clip((YY - 8) / 136.0, 0, 1) * 0.85 + 0.04 * (nb - 0.5)
            m = sky & ~inside
            out[m] = fx.pick(R['sky'], 1 - t, bay, 0.9)[m]
            if hasattr(p, 'make_backdrop'):
                anim[m] = 4          # open sky shows the parallax backdrop
            if inside.any():
                th_ = 0.75 - 0.35 * np.clip((YY % 144) / 144.0, 0, 1) + 0.1 * (nb - 0.5)
                out[inside] = fx.pick(R['hill'], th_, bay, 0.6)[inside]
            out[hill_line] = fx.pick(R['hill'], np.full((H, W), 0.12, np.float32))[hill_line]
            rest = (mat == M['h']) & ~hill_line & ~inside
            out[rest] = fx.pick(R['sky'], 1 - t, bay, 0.9)[rest]
            if hasattr(p, 'make_backdrop'):
                anim[rest] = 4
        m = mat == M['Z']
        if m.any():   # clouds: soft white to blue by shade
            out[m] = fx.pick(R['cloud'], ch([0.98, 0.72, 0.45, 0.18]))[m]
        if self._kind is not None:
            kd = self._kind[np.ix_(ys, xs)]
            t_sky = 1.0 - np.clip((YY - 8) / 136.0, 0, 1) * 0.85 + 0.04 * (nb - 0.5)
            m = kd == 1
            if m.any():   # open sky (behind the backdrop, if any)
                out[m] = fx.pick(R['sky'], 1 - t_sky, bay, 0.9)[m]
                if hasattr(p, 'make_backdrop'):
                    anim[m] = 4
            m = kd == 2
            if m.any():   # cloud bodies: white, a little cooler toward the bottom of each tile row
                out[m] = fx.pick(R['cloud'], 0.97 - 0.05 * ((YY % 16) > 11) + 0.03 * (nb - 0.5))[m]
                anim[m] = 0
            # hills: flat steps of the ramp, no noise or dither (pixel-art clean):
            # the body, its shaded rim one step darker, a lit edge under the top
            # outline one step lighter, and the outline dark
            body_t, rim_t, lit_t = 0.62, 0.42, 0.82
            line = (mat == M['h']) & (idx >= 2)
            m = (mat == M['h']) & (idx >= 1)
            if m.any():   # hills and hoops: the inner band is the body, the line dark
                t = np.where(idx == 1, body_t, np.where(idx == 2, 0.12, 0.04))
                out[m] = fx.pick(R['hill'], t)[m]
                anim[m] = 0
            m = kd == 3
            if m.any():
                lit = m & (fx.shift(line, 1, 0, False, wrap) | fx.shift(line, 2, 0, False, wrap))
                out[m] = fx.pick(R['hill'], np.where(lit, lit_t, body_t))[m]
                anim[m] = 0
            # outlines in tiles shared with clouds (hoop tops, dome shoulders)
            # belong to the hill they touch when no cloud is beside them
            zl = (mat == M['Z']) & (kd == 0) & (idx >= 1)
            if zl.any():
                hillish = (kd == 3) | (kd == 5)
                near_h = fx.dilate(fx.dilate(hillish, wrap), wrap)
                near_c = fx.dilate(fx.dilate(kd == 2, wrap), wrap)
                m = zl & near_h & ~near_c
                if m.any():
                    t = np.where(idx == 1, body_t, np.where(idx == 2, 0.12, 0.04))
                    out[m] = fx.pick(R['hill'], t)[m]
                    anim[m] = 0
            m = kd == 6
            if m.any():   # tree trunks: bark, lighter toward the lit left
                lit_l = ~fx.shift(kd == 6, 0, 2, False, wrap)
                out[m] = fx.pick(R['bark'], np.where(lit_l, 0.78, 0.58) + 0.12 * (ng - 0.5), bay, 0.4)[m]
                anim[m] = 0
            m = kd == 7
            if m.any():   # a cloud's own outline (its arcs share tiles with hills)
                out[m] = fx.pick(R['cloud'], ch([0.98, 0.72, 0.45, 0.18]))[m]
                anim[m] = 0
            m = kd == 5
            if m.any():   # a hill's shaded rim (its band and the dither in it): a soft shade
                out[m] = fx.pick(R['hill'], np.full((H, W), rim_t, np.float32))[m]
                anim[m] = 0
            jm = mat == M['J']
            if jm.any() or (kd == 4).any():
                # logo: letters lit from the top (white rim, then a glossy gradient
                # by depth), the game's inner shading as a deeper tone, dark outline;
                # rows below LOGO_SPLIT use the second logo ramp
                body = kd == 4
                depth = np.zeros((H, W), np.float32)
                run = body.copy()
                for i in range(1, 22):
                    run &= fx.shift(body, i, 0, False, wrap)
                    depth += run
                rim = body & ~fx.shift(body, 1, 0, False, wrap)
                t = np.where(rim, 0.95, 0.8 - 0.018 * depth)
                t = np.where(body, t, np.where(idx == 3, 0.02, np.where(idx >= 1, 0.3, t)))
                # each letter takes its ramp from where its middle is
                lab4, n4 = ndi.label(body)
                lower = np.zeros((H, W), bool)
                if n4:
                    mid = ndi.mean(YY, lab4, np.arange(1, n4 + 1))
                    low = np.concatenate([[False], mid >= getattr(p, 'LOGO_SPLIT', 999)])
                    lower = low[lab4]
                    # the outline and inner shade go with the nearest letter
                    near = ndi.distance_transform_edt(lab4 == 0, return_distances=False,
                                                      return_indices=True)
                    lower = np.where(body, lower, low[lab4[near[0], near[1]]])
                m = (body | (jm & (idx >= 1)))
                out[m & ~lower] = fx.pick(R['logo'], t)[m & ~lower]
                out[m & lower] = fx.pick(R['logo2'], t)[m & lower]
                anim[m] = 0
        if txt_ink.any():   # bold letters, lit from the top, with a drop shadow
            shadow = (fx.shift(txt_ink, 1, 1, False, wrap) | fx.shift(txt_ink, 0, 1, False, wrap)) & ~txt_ink
            sc = fx.hx(getattr(p, 'TEXT_SHADOW_BY_BACKDROP', {}).get(
                self._bd_key, getattr(p, 'TEXT_SHADOW', '#0a0e28')))[0]
            out[shadow] = out[shadow] * 0.25 + sc * 0.75
            anim[shadow] = 0
            top = txt_ink & ~fx.shift(txt_ink, 1, 0, False, wrap)
            tone = np.where(top, 1.0, 0.82 - 0.25 * ((YY % 8) / 8.0))
            out[txt_ink] = fx.pick(R['text'], tone)[txt_ink]

        # ledges: a lit grassy lip, a short dirt face, a shadow below (cast later)
        m = mat == M['L']
        if m.any() and getattr(p, 'LEDGE_FROM_LINE', False):
            # the ledge starts at its ground line in each column (above it, the
            # line art carries on: sky, or a dome's foot)
            from ugb import lineart
            gnd = lineart.below_ledge_line(idx, m, (np.arange(H) // 8) * 8)
            rows_ = np.arange(H)[:, None]
            top = np.maximum.accumulate(np.where(m & (idx >= 2) & ~fx.shift(m & (idx >= 2), 1, 0, False, False),
                                                 rows_, -1), axis=0)
            depth = np.where(gnd, rows_ - top, 99).astype(np.float32)
            lip = gnd & (depth < 3)
            tg = ch([0.98, 0.8, 0.6, 0.3]) + 0.06 * (ng - 0.5)
            td = ch([0.7, 0.55, 0.4, 0.12]) - 0.05 * np.clip(depth - 3, 0, 5) + 0.05 * (ng - 0.5)
            tg = np.where(depth == 2, tg + 0.1, tg)
            out[lip] = fx.pick(R['ground'], tg)[lip]
            dm = gnd & ~lip
            out[dm] = fx.pick(R['dirt'], td)[dm]
            anim[gnd] = 0
        elif m.any():
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
        m = obj & (mat == M['Q'])
        if m.any():   # blocks: a flat face with a lit top-left bevel and a dark bottom-right
            far = edge & ~lit_edge
            t = ch([0.95, 0.72, 0.5, 0.15]) + 0.18 * (-nx - ny) * 0.5
            t = np.where(lit_edge, t + 0.2, np.where(far, t - 0.25, t))
            out[m] = fx.pick(R['gold'], t)[m]
        m = obj & (mat == M['V'])
        if m.any():   # pipes: green cylinders
            nz = np.sqrt(np.clip(1 - nx ** 2, 0, 1))
            lam = np.clip((nx * L[0] + nz * L[2] + 0.6) / 1.2, 0, 1)
            t = ch([0.95, 0.7, 0.45, 0.05]) * 0.4 + 0.7 * lam - 0.05
            t = np.where(edge & (idx == 3), np.where(lit_edge, 0.12, 0.0), t)
            out[m] = fx.pick(R['pipe'], t)[m]
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
            raw_rgb = f.bgpal[pal, idx_raw].astype(np.float32)
            flat = (raw_rgb[m] == raw_rgb[m][0]).all()
            if flat:
                # e.g. the black outside a room: nothing for the generic pass to do
                out[m] = raw_rgb[m]
            else:
                # run the generic pass only on the unlabelled area, plus a margin of
                # context, in tile-aligned steps (the water test works on tiles).
                # Rows of unlabelled tiles far apart (a status bar and a lone object
                # lower down) are done separately, not as one box spanning both.
                tm = m.reshape(H // 8, 8, W // 8, 8).any(axis=(1, 3))
                # (unlabelled tiles only in the margin are context, not kept: skip them)
                cy, cx = getattr(self, '_patch_core', (0, 0))
                if cy:
                    tm[:cy] = False
                    tm[tm.shape[0] - cy:] = False
                if cx:
                    tm[:, :cx] = False
                    tm[:, tm.shape[1] - cx:] = False
                trs = np.nonzero(tm.any(1))[0]
                cuts = np.nonzero(np.diff(trs) > 5)[0] + 1
                for grp in (np.split(trs, cuts) if len(trs) else []):
                    tx = np.nonzero(tm[grp].any(0))[0]
                    r0, r1 = max(grp.min() - 2, 0) * 8, min(grp.max() + 3, H // 8) * 8
                    c0, c1 = max(tx.min() - 2, 0) * 8, min(tx.max() + 3, W // 8) * 8
                    whole = (r0, r1, c0, c1) == (0, H, 0, W)
                    Y, X = slice(r0, r1), slice(c0, c1)
                    tex = 0.6 * nb[Y, X] + 0.4 * ng[Y, X]
                    shade = idx[Y, X] if f.dmg else None   # already shades for plain Game Boy
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

        if hasattr(p, 'paint_tiles'):   # the preset's own touches (Kirby)
            kdp = self._kind[np.ix_(ys, xs)] if self._kind is not None else None
            p.paint_tiles(out, anim, kdp, idx, np.repeat(np.repeat(keys, 8, 0), 8, 1), XX, YY, R, f)

        # shadows and contact darkening -----------------------------------------
        solid = obj | IS_BUILDING[mat]
        if getattr(p, 'LEDGE_FROM_LINE', False):
            solid &= mat != M['L']      # (a ledge is the ground's own edge: no drop shadow)
        ground_like = IS_GROUND[mat] & ~solid
        cast = (fx.shift(solid, 2, 2, wrap=wrap) | fx.shift(solid, 1, 2, wrap=wrap)
                | fx.shift(solid, 2, 1, wrap=wrap) | fringe) & ground_like
        contact = fx.dilate(solid, wrap) & ground_like & ~cast
        mul = np.ones((H, W, 3), np.float32)
        mul[cast] = (0.62, 0.66, 0.86)
        mul[contact] = 0.86
        out *= mul

        m = mat == M['U']   # text boxes are styled in screen space
        out[m] = f.bgpal[pal, idx_raw][m]
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
        overlay = self.p.patch_frame(f) if hasattr(self.p, 'patch_frame') else []
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
        if hasattr(self.p, 'make_backdrop'):
            self._backdrop(f)
        # tiles on screen plus one tile of slack, so scrolling never shows a stale tile
        # by depends only on the line and bx only on the line's SCX, so small sets do
        # (only lines where this map shows: not under a full-width window such as
        # a status bar, nor drawn from the other map; the rows below a level's
        # playfield are often leftover tiles that would be redrawn for nothing)
        shown = ~f.window_mask().all(1) & (f.line_maps() == f.bg_map())
        rows = np.unique(by[shown if shown.any() else slice(None), 0] // 8)
        cols = np.unique(np.concatenate([((np.arange(160) + sx) & 255) // 8
                                         for sx in np.unique(f.scx).tolist()]))
        vis = np.zeros((32, 32), bool)
        vis[np.ix_(np.unique(np.concatenate([rows - 1, rows, rows + 1])) % 32,
                   np.unique(np.concatenate([cols - 1, cols, cols + 1])) % 32)] = True
        core = np.zeros((32, 32), bool)
        core[np.ix_(rows % 32, cols % 32)] = True
        self._vis_core = {f.bg_map(): core}      # (layer() leaves the slack to idle())
        if hasattr(self.p, 'has_status_bar') and not self.p.has_status_bar(f):
            bbar = wbar = None      # (the preset knows there's none: an ending, a cutscene)
        else:
            bbar, wbar = self._status_bar(f, by, bx)
        bst, bidx, bprio, braw = self.layer(f, f.bg_map(), table, vis, bar=bbar)
        win = f.window_mask()
        rgb = bst.out[by, bx]
        sidx = bidx[by, bx]
        self._animate(rgb, bst, sidx, by, bx)
        sprio = bprio[by, bx]
        stid = braw[by // 8, bx // 8]
        ui = self._ui_tiles(braw, by[0, 0] // 8, bx[0, 0] // 8)[by // 8, bx // 8]
        if bst.bar.any():
            hud = bst.hud[by // 8, bx // 8]
            hbar = bst.bar[by // 8, bx // 8]
            hico = bst.icon[by // 8, bx // 8]
        else:
            hud = hbar = hico = np.zeros((144, 160), bool)
        # lines drawn from the other tile map (a mid-frame LCDC switch: gb.Frame.line_maps)
        lm = f.line_maps()
        other = 1 - f.bg_map()
        olines = lm == other
        if olines.any():
            ovis = np.zeros((32, 32), bool)
            orows = np.unique(by[olines, 0] // 8)
            ovis[np.ix_(np.unique(np.concatenate([orows - 1, orows, orows + 1])) % 32,
                        np.unique(np.concatenate([cols - 1, cols, cols + 1])) % 32)] = True
            ost, oidx, oprio, oraw = self.layer(f, other, table, ovis)
            orgb = ost.out[by, bx]
            osidx = oidx[by, bx]
            self._animate(orgb, ost, osidx, by, bx)
            L = olines[:, None]
            rgb = np.where(L[..., None], orgb, rgb)
            sidx = np.where(L, osidx, sidx)
            sprio = np.where(L, oprio[by, bx], sprio)
            stid = np.where(L, oraw[by // 8, bx // 8], stid)
            ui = np.where(L, self._ui_tiles(oraw, by[0, 0] // 8, bx[0, 0] // 8)[by // 8, bx // 8], ui)
            hud = hud & ~L
            hbar = hbar & ~L
            hico = hico & ~L
        if win.any():
            wvis = np.zeros((32, 32), bool)
            wvis[np.ix_(np.unique(wy // 8), np.unique(wx // 8))] = True
            # world position of the window's top-left pixel (screen position + scroll)
            on, _ = f._window_lines()
            y0 = int(np.argmax(on))
            woff = (int(y0 + f.scy[y0]) % N, int(f.wx[y0] - 7 + f.scx[y0]) % N)
            if wbar is not None:
                woff = (0, 0)     # a status bar doesn't sit over the map: keep it still
            wst, widx, wprio, wraw = self.layer(f, f.win_map(), table, wvis, woff, bar=wbar)
            wrgb = wst.out[wy, wx]
            wsidx = widx[wy, wx]
            self._animate(wrgb, wst, wsidx, wy, wx)
            rgb = np.where(win[..., None], wrgb, rgb)
            sidx = np.where(win, wsidx, sidx)
            sprio = np.where(win, wprio[wy, wx], sprio)
            stid = np.where(win, wraw[wy // 8, wx // 8], stid)
            ui = np.where(win, self._ui_tiles(wraw, 0, 0)[wy // 8, wx // 8], ui)
            if wst.bar.any():
                hud = np.where(win, wst.hud[wy // 8, wx // 8], hud)
                hbar = np.where(win, wst.bar[wy // 8, wx // 8], hbar)
                hico = np.where(win, wst.icon[wy // 8, wx // 8], hico)
        shade = np.array([(f.bgp >> (2 * i)) & 3 for i in range(4)])[sidx] if f.dmg else sidx
        self._hud_text(rgb, hud, hbar, hico, shade, stid)
        if overlay:
            self._text_overlay(f, rgb, overlay)
        if self.eye_candy:
            ec = getattr(self.p, 'EYE_CANDY', {})
            mspec = getattr(self.p, 'MOTES', {}).get(self._bd_key)
            if mspec and ec.get('motes', 0):
                sky = np.isin(bst.anim[by, bx], (4, 9)) & ~win & (lm == f.bg_map())[:, None]
                self._motes(rgb, sky, mspec, ec['motes'])
            if getattr(self.p, 'TRAIL_SPRITES', None) and ec.get('trail', 0):
                self._trail(f, rgb, ec['trail'])
        self._sprites(f, rgb, sidx, sprio, ui, overworld=table is not None)
        self._textbox(rgb, sidx, stid, ui)
        return fx.snes15(rgb)

    def _motes(self, rgb, sky, spec, strength):
        """A few drifting specks over open sky (presets' MOTES, per backdrop):
        falling leaves, rising spray, floating specks of light. No state: each
        mote's path is a function of its number and the frame, scrolled with
        the world at `par` (a fraction of the camera)."""
        fn = self.frame_no
        n = int(spec.get('n', 6) * strength)
        if n <= 0:
            return
        cam = getattr(self, '_bd_cam', np.zeros(2))
        par = spec.get('par', 0.8)
        cols = np.array([fx.hx(c)[0] for c in spec['colours']], np.float32)
        W, H = 192, 176
        for i in range(n):
            r = [((i * 2654435761 + k * 40503) >> 3 & 0xffff) / 65535.0 for k in range(5)]
            x = (r[0] * W + fn * spec.get('vx', 0) * (0.6 + 0.8 * r[2]) - cam[0] * par
                 + spec.get('amp', 0) * np.sin(fn * spec.get('freq', 0.03) + r[3] * 6.283)) % W - 16
            y = (r[1] * H + fn * spec.get('vy', 0) * (0.6 + 0.8 * r[2]) - cam[1] * par) % H - 16
            xi, yi = int(x), int(y)
            shape = spec.get('shape', 'dot')
            if shape == 'leaf':       # 2x2, its lit half flips as it tumbles
                flip = (fn // 8 + i) % 2
                pts = [(0, 0, 0 if flip else 1), (0, 1, 1), (1, 0, 1), (1, 1, 1 if flip else 0)]
            elif shape == 'speck':    # a dot that flares into a small cross now and then
                if (fn // 6 + i) % 3 == 0:
                    pts = [(0, 0, 1), (-1, 0, 0), (1, 0, 0), (0, -1, 0), (0, 1, 0)]
                else:
                    pts = [(0, 0, 0)]
            else:
                pts = [(0, 0, 0)]
            for dy, dx, c in pts:
                yy, xx = yi + dy, xi + dx
                if 0 <= yy < 144 and 0 <= xx < 160 and sky[yy, xx]:
                    a = spec.get('alpha', 0.85)
                    rgb[yy, xx] = rgb[yy, xx] * (1 - a) + cols[min(c, len(cols) - 1)] * a

    def _trail(self, f, rgb, strength):
        """Sparkles trailing the preset's TRAIL_SPRITES (Kirby's warp star),
        and a soft glow around it."""
        hs = getattr(self, '_trail_set', None)
        if hs is None:
            hs = self._trail_set = set(self.p.TRAIL_SPRITES)
        pts = []
        for sp in f.sprites():
            h = int(hashlib.blake2b(sp['px'].tobytes(), digest_size=3).hexdigest(), 16)
            if h in hs:
                pts.append((sp['y'] + sp['px'].shape[0] / 2, sp['x'] + 4))
        hist = getattr(self, '_trail_hist', [])
        if pts:
            hist.append((self.frame_no, float(np.mean([p[0] for p in pts])), float(np.mean([p[1] for p in pts]))))
        hist = [h for h in hist if self.frame_no - h[0] < 24]
        self._trail_hist = hist
        if not hist:
            return
        warm = np.array([255, 236, 150], np.float32)
        white = np.array([255, 255, 240], np.float32)
        if pts:          # glow around the star
            cy, cx = hist[-1][1], hist[-1][2]
            y0, y1 = int(max(cy - 14, 0)), int(min(cy + 15, 144))
            x0, x1 = int(max(cx - 14, 0)), int(min(cx + 15, 160))
            if y1 > y0 and x1 > x0:
                yy, xx = np.mgrid[y0:y1, x0:x1]
                g = np.clip(1 - np.hypot(yy - cy, xx - cx) / 14.0, 0, 1) ** 2 * 0.45 * strength
                rgb[y0:y1, x0:x1] = rgb[y0:y1, x0:x1] * (1 - g[..., None]) + warm * g[..., None]
        for k, (fr, cy, cx) in enumerate(hist[:-1]):
            age = (self.frame_no - fr) / 24.0
            if (fr + k) % 2:
                continue
            j = ((fr * 7919) % 7) - 3          # a little scatter
            y, x = int(cy + j * 0.7), int(cx - j * 0.5)
            a = (1 - age) * 0.9 * strength
            arm = 1 if age > 0.5 else 2
            for dy, dx in [(0, 0)] + [(d, 0) for d in range(-arm, arm + 1) if d] + [(0, d) for d in range(-arm, arm + 1) if d]:
                yy, xx = y + dy, x + dx
                if 0 <= yy < 144 and 0 <= xx < 160:
                    c = white if (dy, dx) == (0, 0) else warm
                    aa = a if (dy, dx) == (0, 0) else a * 0.6
                    rgb[yy, xx] = rgb[yy, xx] * (1 - aa) + c * aa

    def _text_overlay(self, f, rgb, overlay):
        """Draw text tiles a preset lifted off the map (see patch_frame) on top of
        the picture: their ink in the text ramp, with the text shadow."""
        p = self.p
        R = _Ramps(p.RAMPS, **getattr(p, 'RAMP_BY_BACKDROP', {}).get(self._bd_key, {}))
        sc = fx.hx(getattr(p, 'TEXT_SHADOW_BY_BACKDROP', {}).get(
            self._bd_key, getattr(p, 'TEXT_SHADOW', '#0a0e28')))[0]
        shade_of = np.array([(f.bgp >> (2 * i)) & 3 for i in range(4)])
        ink = np.zeros((144, 160), bool)
        for r, c, t in overlay:
            px = f.tiles[0, int(f.tile_index(np.array(t)))]
            sh = shade_of[px] if f.dmg else px
            y0 = (r * 8 - int(f.scy[0])) % N
            x0 = (c * 8 - int(f.scx[0])) % N
            if y0 <= 136 and x0 <= 152:
                ink[y0:y0 + 8, x0:x0 + 8] |= sh >= 2
        shadow = (fx.shift(ink, 1, 1) | fx.shift(ink, 0, 1)) & ~ink
        rgb[shadow] = rgb[shadow] * 0.25 + sc * 0.75
        top = ink & ~fx.shift(ink, 1, 0)
        rgb[ink] = fx.pick(R['text'], np.where(top, 1.0, 0.75))[ink]

    def _backdrop(self, f):
        """Compose this frame's parallax backdrop (screen-sized) from the preset's layers.

        The preset builds its layers once per key (stage): a list of (image, kx, ky),
        each an (h, w, 4) float array with alpha, scrolled at kx, ky times the camera.
        The camera follows the playfield's scroll, unwrapped across the 256-pixel map."""
        key = self.p.backdrop_key(f)
        if key != self._bd_key:
            self._bd_key = key
            self._bd_layers = self.p.make_backdrop(key) if key is not None else None
            self._bd_cam[:] = 0
            self._bd_scroll = None
            self._bd_offs = None
        if self._bd_layers is None:
            self._bd_screen = None
            return
        sx = int(np.bincount(f.scx).argmax())
        sy = int(np.bincount(f.scy).argmax())
        if self._bd_scroll is not None:
            dx = (sx - self._bd_scroll[0] + 128) % 256 - 128
            dy = (sy - self._bd_scroll[1] + 128) % 256 - 128
            self._bd_cam += (dx, dy)
        self._bd_scroll = (sx, sy)
        yo = self.p.backdrop_y(f) if hasattr(self.p, 'backdrop_y') else None   # (a row the preset pins)
        offs = tuple((int(round(self._bd_cam[0] * kx)), int(round(self._bd_cam[1] * ky)) if yo is None else yo)
                     for _, kx, ky in self._bd_layers)
        if offs == getattr(self, '_bd_offs', None):
            return                       # no layer moved by a whole pixel: reuse
        self._bd_offs = offs
        out = None
        for (img, kx, ky), (ox, oy) in zip(self._bd_layers, offs):
            h, w = img.shape[:2]
            y0 = int(np.clip(oy, 0, h - 144))
            x0 = ox % w
            rows = img[y0:y0 + 144]
            if x0 + 160 <= w:
                px = rows[:, x0:x0 + 160]
            else:
                px = np.concatenate([rows[:, x0:], rows[:, :x0 + 160 - w]], 1)
            if out is None:
                out = px[..., :3].copy()
            else:
                a = px[..., 3:4]
                out = out * (1 - a) + px[..., :3] * a
        self._bd_screen = out

    @staticmethod
    def _status_bar(f, by, bx):
        """32x32 masks of status-bar tiles in the BG map and the window map.

        A status bar is a band of at most 40 lines along the top or bottom of the
        screen that doesn't scroll with the rest: either a full-width window, or
        BG lines whose scroll differs from the playfield's."""
        bbar = wbar = None
        on, row = f._window_lines()
        lines = np.nonzero(on)[0]
        if 0 < len(lines) <= 40 and lines[-1] == 143 and len(lines) == lines[-1] - lines[0] + 1                 and (f.wx[lines] <= 7).all():
            wbar = np.zeros((32, 32), bool)
            wbar[np.unique(row[lines] // 8)] = True
        off = f.scx.astype(np.int32) * 256 + f.scy.astype(np.int32)
        main = np.bincount(off).argmax()
        other = off != main
        first = int(np.argmin(other)) if other[0] else 0          # lines before the playfield
        last = 143 - int(np.argmin(other[::-1])) if other[-1] else 143
        band = np.zeros(144, bool)
        if 0 < first <= 40:
            band[:first] = True
        if 0 < 143 - last <= 40:
            band[last + 1:] = True
        band &= ~on
        band &= f.line_maps() == f.bg_map()     # (lines from the other map aren't this map's bar)
        if band.any():
            bbar = np.zeros((32, 32), bool)
            bbar[by[band] // 8, bx[band] // 8] = True
        return bbar, wbar

    def _hud_text(self, rgb, hud, bar, icon, shade, stid):
        """SNES-style status bar: a dark gradient panel, cream text with a shadow.

        `hud` marks blank and two-colour tiles in the bar (text); their darker
        colour is the lettering. The panel also fills the paper of other bar tiles
        (icons, gauges) where it connects to the text area, but not their insides."""
        rows = np.nonzero(bar.any(1))[0]
        if not len(rows):
            return
        r0, r1 = rows[0], rows[-1] + 1        # work on the bar's lines only
        full, rgb, hud, bar = rgb, rgb[r0:r1], hud[r0:r1], bar[r0:r1]
        icon, shade, stid = icon[r0:r1], shade[r0:r1], stid[r0:r1]
        if not hud.any():
            return
        ck = (r0, rgb.tobytes(), np.packbits(hud).tobytes(), np.packbits(bar).tobytes(),
              np.packbits(icon).tobytes())
        hit = self._hud_cache
        if hit is not None and hit[0] == ck:      # the bar hasn't changed: reuse it
            full[r0:r1] = hit[1]
            return
        lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
        lo, hi = lum[hud].min(), lum[hud].max()
        if hi - lo < 24:
            return                      # nothing but blank tiles
        ink = hud & (lum < (lo + hi) / 2)
        paper = bar & (lum >= hi - 24) & ~ink
        style = getattr(self.p, 'HUD_STYLE', {})
        paper |= icon & (shade == 0)
        # the panel: paper reachable from the text tiles without crossing a line
        panel = _grow4(paper & hud, paper, 64, False)
        steps = fx.hx(*style.get('panel', ('#3a56c8', '#3048b8', '#283ca4', '#203090', '#1a267c', '#141e68')))
        k = np.clip((SY[r0:r1] - r0) * len(steps) // max(r1 - r0, 1), 0, len(steps) - 1)
        rgb[panel] = steps[k][panel]
        if 'edge' in style:      # a line along the panel's top edge
            top_row = panel & (SY[r0:r1] == r0)
            rgb[top_row] = fx.hx(style['edge'])[0]
        shadow = (fx.shift(ink, 1, 1) | fx.shift(ink, 0, 1)) & panel
        rgb[shadow] = fx.hx(style.get('shadow', '#060c38'))[0]
        for tile, ramp in style.get('icons', {}).items():   # icons: their own ramps by shade
            m = icon & (stid == tile) & ((shade > 0) | ~panel)      # incl. their enclosed white
            if m.any():
                t = np.choose(shade, [0.64, 0.72, 0.42, 0.06])   # white inside an icon: its body colour
                top_px = m & ~fx.shift(m, 1, 0)
                t = np.where(top_px & (shade < 3), t + 0.12, t)
                rgb[m] = fx.pick(self.p.RAMPS[ramp], t)[m]
        text = fx.hx(*style.get('text', ('#fff4d0', '#f4e0a8', '#d8b878')))
        top = ink & ~fx.shift(ink, 1, 0)
        tone = np.where(top, 0, np.where(fx.shift(ink, -1, 0), 1, 2))
        rgb[ink] = text[tone][ink]
        full[r0:r1] = rgb
        self._hud_cache = (ck, rgb.copy())

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
        # Games reuse OAM groups for unrelated objects far apart; shading one box
        # around them all is slow and never cached. Split groups into pieces whose
        # sprites touch (a group that is one object, as in Pokemon, stays whole).
        split = {}
        for g, ss in groups.items():
            parts = []
            for s in ss:
                hs = s['px'].shape[0]
                hit = [q for q in parts if any(s['x'] <= t['x'] + 8 and t['x'] <= s['x'] + 8
                                               and s['y'] <= t['y'] + t['px'].shape[0]
                                               and t['y'] <= s['y'] + hs for t in q)]
                merged = [s] + [t for q in hit for t in q]
                parts = [q for q in parts if not any(q is h for h in hit)] + [merged]
            for k, q in enumerate(parts):
                split[g + k / 8] = q
        groups = split
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

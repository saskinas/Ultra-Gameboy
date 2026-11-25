"""Ultra Game Boy preset: Kirby's Dream Land. The special one.

Kirby is the one game where game-specific code is welcome (docs/KIRBY_PLAN.md):
vibrant colours, a hand-tuned look per stage, and parallax backdrops drawn by code
behind the open sky. All art is procedural and original; nothing is taken from
later Kirby games.

Tiles are recognised by a hash of their pixels (tools/hash_sheet.py).
States for labelling come from tools/kirby_run.py.
"""
import numpy as np

from ugb.fx import hx

TITLE = 'KIRBY DREAM LAN'
RAM = {}
TILESETS = {}
UI_FIRST_TILE = 256
GAME_COLOURS = False
LINE_ART = True     # white shapes outlined on a white sky: classify regions map-wide
SPRITE_SLOT = {}
SPRITE_PIC = {}
NPC_CYCLE = []

RAMPS = {
    # Green Greens: a bright spring morning
    'sky': hx('#3a78e0', '#4a8cf0', '#64a6f6', '#86c4fa', '#acdcfc', '#d6f2ff', '#f2fbff'),
    'hill': hx('#2a7a5a', '#38966a', '#4cb07a', '#6ac88c', '#90dca4', '#bcecc4'),
    'ground': hx('#1e7a2c', '#2c9a34', '#46b83e', '#6cd04c', '#9ae268', '#ccf49c'),
    'dirt': hx('#2a8a34', '#3aa23c', '#52b846', '#70cc54', '#96dc6c'),
    'earth': hx('#227a30', '#329438', '#48ac40', '#64c04c', '#86d462', '#b0e888'),
    'tallgrass': hx('#0c4a22', '#14682c', '#1e8636', '#30a444', '#52c05a', '#84d874', '#b8ec9c'),
    'rock': hx('#3a3478', '#544ea0', '#7270c0', '#9898dc', '#c2c2f0', '#eaeaff'),
    'cloud': hx('#8aa0e8', '#aebef4', '#d2dcfa', '#ecf2ff', '#ffffff'),
    'specks': hx('#46b83e', '#9ae268'),
    'neutral': hx('#2a2440', '#5a5480', '#9890b8', '#d0cce4', '#fbf8ff'),
    # status bar icons
    'health': hx('#8a4a00', '#d08a10', '#f6c020', '#ffe050', '#fff4a0', '#fffde0'),
    'health_empty': hx('#b07090', '#d8a0bc', '#ecc4d6', '#f8e0ea', '#fff4f8'),
    'kirby': hx('#6a0c3a', '#c0306e', '#ec78a8', '#ffaed0', '#ffd8e8', '#fff4f8'),
}

# Status bar: light pink panel, berry lettering with a soft pink shadow, yellow
# health pips, a pink Kirby lives icon. Icons are window tile numbers.
HUD_STYLE = {
    'panel': ('#fff2f8', '#ffe8f2', '#ffdeec', '#ffd4e6', '#ffcae0', '#ffc0da'),
    'edge': '#f4a6c8',
    'text': ('#c43c7c', '#9c1e5c', '#7c1048'),
    'shadow': '#f2b0cc',
    'icons': {0x68: 'health', 0x6e: 'health_empty', 0x67: 'kirby'},
}
CLEAN_GRASS = True   # the foreground foliage band, drawn clean


def _k(code, *hexes):
    for h in hexes:
        TILE_KEYS[int(h, 16)] = code


TILE_KEYS = {}
# ---- Green Greens (first area) ----
_k('Y', 'b77a35')                                          # open sky
_k('E', '2943e3', '0c913b', '182a35', '2ae841', 'd76da9')  # dotted ground body, its cliff sides
_k('L', '6df7e2', '96415c', '9fd36c', '5fa707', '6a2523')    # grassy top edges and corners
_k('G', '42f6ee', 'f62142', '77323a', 'c7d3c7', '69efb2',  # grass tufts and round flowers,
   '7316ab', 'fab5f0', '35dc1f', '3d6082', '473e45', '7a0b52')   # also standing on the ground
_k('K', '73fca6', '268420', '506a64', '735685',            # cobbled cliff face
   '6d2bd7', 'b8e15a', '6eb939')
_k('Z', '91e532', 'c2cc69', 'dc80d2', '279c1b', '5435d0',  # clouds
   '82a6f8', 'c20b4a', 'f9844b', 'f72f32', '29e336', 'da535f', '9e43af')
_k('h', 'b4c507', '7f0ec8', '5d8d11', 'a271b5', 'e35cb5',  # outline hills and arches
   '3da09a', '3a38bc', 'd6f0fc', '7adab7', 'd7d382', '03109f', 'd50847',
   'a315bd', '1d2856', 'a44b6b', '539833', '198899', '05f81e')

STAMPS = []


# ---- parallax backdrops -------------------------------------------------------
def backdrop_key(f):
    """Which stage's backdrop to show. Only Green Greens so far."""
    return 'green_greens'


def _bands(top, bottom, ys, steps):
    """A vertical gradient quantised into flat bands (the 16-bit look)."""
    t = np.clip((ys - top) / max(bottom - top, 1), 0, 1)
    return np.floor(t * steps) / steps


def _profile(w, base, amp, waves, seed):
    """A wrapping skyline: the sum of a few whole-number sine waves."""
    rng = np.random.default_rng(seed)
    x = np.arange(w) / w * 2 * np.pi
    y = np.full(w, float(base))
    for n, a in waves:
        y += amp * a * np.sin(n * x + rng.uniform(0, 2 * np.pi))
    return y


def _silhouette(w, h, line, top_col, body_col, rim_col, shade_col=None):
    """RGBA layer: solid below `line` (per column), lit rim on top, darker toward
    the bottom in bands."""
    ys = np.arange(h)[:, None].astype(np.float32)
    inside = ys >= line[None, :]
    depth = ys - line[None, :]
    img = np.zeros((h, w, 4), np.float32)
    t = np.clip(depth / 40.0, 0, 1)
    t = np.floor(t * 4) / 4
    col = top_col[None, None] * (1 - t[..., None]) + body_col[None, None] * t[..., None]
    if shade_col is not None:     # the slope facing away from the light is darker
        slope = np.gradient(line)[None, :, None]
        col = np.where(slope < -0.15, col * 0.75 + shade_col * 0.25, col)
    rim = inside & (depth < 1.5)
    col = np.where(rim[..., None], rim_col[None, None], col)
    img[..., :3] = col
    img[..., 3] = inside
    return img


def _clouds(w, h, seed, n, y0, y1, col, shade, alpha):
    """RGBA layer of soft round cumulus: unions of circles, shaded underneath."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    mask = np.zeros((h, w), bool)
    low = np.zeros((h, w), bool)
    for _ in range(n):
        cx, cy = rng.uniform(0, w), rng.uniform(y0, y1)
        size = rng.uniform(10, 20)
        for _ in range(5):
            bx = cx + rng.uniform(-1.6, 1.6) * size
            by = cy + rng.uniform(-0.5, 0.2) * size
            r = size * rng.uniform(0.55, 0.95)
            dx = (xx - bx + w / 2) % w - w / 2        # wraps around
            d = dx ** 2 + (yy - by) ** 2
            mask |= d < r * r
        low |= mask & (yy > cy + size * 0.15)
    img = np.zeros((h, w, 4), np.float32)
    img[..., :3] = np.where(low[..., None], shade, col)
    img[..., 3] = mask * alpha
    return img


def make_backdrop(key):
    """Layers for a stage, far to near: (rgba image, kx, ky)."""
    h = 160
    ys = np.arange(h, dtype=np.float32)
    # sky: deep blue at the top to pale near the horizon, in flat bands
    sky = hx('#3a78e0', '#4a8cf0', '#64a6f6', '#86c4fa', '#acdcfc', '#d6f2ff')
    k = (_bands(0, 112, ys, len(sky) - 1) * (len(sky) - 1)).astype(int)
    grad = np.zeros((h, 160, 4), np.float32)
    grad[..., :3] = sky[k][:, None]
    grad[..., 3] = 1
    # a soft morning sun glow, fixed on screen (far away), top right
    yy, xx = np.mgrid[0:h, 0:160]
    d = np.hypot(xx - 128, yy - 18)
    glow = (d < 14) * 0.45 + (d < 20) * 0.2
    grad[..., :3] = grad[..., :3] * (1 - glow[..., None]) + hx('#fff6d0')[0] * glow[..., None]
    sun = d < 9
    grad[sun, :3] = hx('#fffbe8')[0]
    layers = [(grad, 0.0, 0.0)]
    # far mountains, hazy blue
    w = 640
    line = _profile(w, 92, 14, ((2, 1.0), (5, 0.5), (11, 0.25)), 1)
    layers.append((_silhouette(w, h, line, hx('#b4dcef')[0], hx('#cdeaf4')[0], hx('#e6f6fb')[0],
                               hx('#90bcd8')[0]), 0.1, 0.0))
    # high soft clouds
    layers.append((_clouds(768, h, 2, 9, 14, 60, hx('#ffffff')[0], hx('#dce6fb')[0], 0.9), 0.22, 0.0))
    # nearer rolling hills, fresh green
    w = 768
    line = _profile(w, 112, 9, ((3, 1.0), (7, 0.45), (13, 0.2)), 3)
    layers.append((_silhouette(w, h, line, hx('#8edca0')[0], hx('#6cc88c')[0], hx('#c6f2c8')[0],
                               hx('#4ca878')[0]), 0.35, 0.0))
    return layers

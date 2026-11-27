"""Shared image helpers: colour ramps, tileable noise, small morphology. Numpy only."""
import numpy as np


def hx(*cols):
    return np.array([[int(c[i:i + 2], 16) for i in (1, 3, 5)] for c in cols], np.float32)


BAYER4 = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], np.float32) / 16.0


def bayer(h, w):
    return np.tile(BAYER4, (h // 4 + 1, w // 4 + 1))[:h, :w]


def pick(ramp, t, bay=None, dither=0.0):
    """Stepped ramp lookup. Pixel art keeps hard steps; optional ordered dither between them."""
    n = len(ramp)
    v = np.asarray(t, np.float32) * (n - 1) + 0.5
    if bay is not None and dither:
        v = v + (bay - 0.5) * dither
    return ramp[np.clip(np.floor(v), 0, n - 1).astype(np.int32)]


def tile_noise(size, cells, seed):
    """Smooth value noise on a size x size torus, so it wraps like the Game Boy's BG map."""
    rng = np.random.default_rng(seed)
    g = rng.random((cells, cells)).astype(np.float32)
    s = np.arange(size, dtype=np.float32) * cells / size
    i0 = s.astype(np.int32)
    i1 = (i0 + 1) % cells
    f = s - i0
    f = f * f * (3 - 2 * f)
    fy, fx = f[:, None], f[None, :]
    a = g[i0][:, i0]
    b = g[i0][:, i1]
    c = g[i1][:, i0]
    d = g[i1][:, i1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


# ---- morphology: wrap=True for the toroidal BG layer, False for local patches ----
def shift(m, dy, dx, fill=False, wrap=False):
    """m moved by (dy, dx): wrapped round (the BG layer), or with `fill` coming in."""
    if wrap:
        return np.roll(m, (dy, dx), (0, 1))
    h, w = m.shape[:2]
    if abs(dy) >= h or abs(dx) >= w:
        return np.full_like(m, fill)
    r = np.empty_like(m)
    r[max(dy, 0):h + min(dy, 0), max(dx, 0):w + min(dx, 0)] = m[max(-dy, 0):h + min(-dy, 0), max(-dx, 0):w + min(-dx, 0)]
    if dy > 0:
        r[:dy] = fill
    elif dy < 0:
        r[dy:] = fill
    if dx > 0:
        r[:, :dx] = fill
    elif dx < 0:
        r[:, dx:] = fill
    return r


def dilate(m, wrap=False):
    """3x3 grow, done as a row pass then a column pass (the same, with half the shifts)."""
    a = m | shift(m, 0, 1, False, wrap) | shift(m, 0, -1, False, wrap)
    return a | shift(a, 1, 0, False, wrap) | shift(a, -1, 0, False, wrap)


def erode(m, wrap=False):
    """3x3 shrink, done as a row pass then a column pass."""
    a = m & shift(m, 0, 1, True, wrap) & shift(m, 0, -1, True, wrap)
    return a & shift(a, 1, 0, True, wrap) & shift(a, -1, 0, True, wrap)


def fill_holes(m):
    """Set pixels that can't reach the patch border through unset pixels."""
    free = ~m
    reach = np.zeros_like(m)
    reach[0], reach[-1] = free[0], free[-1]
    reach[:, 0] |= free[:, 0]
    reach[:, -1] |= free[:, -1]
    while True:
        n = reach.copy()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n |= shift(reach, dy, dx)
        n &= free
        if (n == reach).all():
            return m | ~reach
        reach = n


def solid_from_outline(outline):
    """Close small gaps in a dark outline, fill it, keep the outline itself."""
    return erode(fill_holes(dilate(outline))) | outline


def box_blur(a, r=1, wrap=False):
    """Mean over a (2r+1) square (zeros beyond the edge unless wrapped): a row
    pass then a column pass."""
    a = a.astype(np.float32)
    acc = a.copy()
    for d in range(1, r + 1):
        acc += shift(a, 0, d, 0.0, wrap) + shift(a, 0, -d, 0.0, wrap)
    out = acc.copy()
    for d in range(1, r + 1):
        out += shift(acc, d, 0, 0.0, wrap) + shift(acc, -d, 0, 0.0, wrap)
    return out / float((2 * r + 1) ** 2)


def snes15(rgb):
    """Round to the SNES's 15-bit colour (5 bits per channel)."""
    return (np.clip(rgb, 0, 255).astype(np.uint8) // 8 * 8) | 0


# ---- hue-shifted ramps: how 16-bit artists step colours lighter or darker ----
def rgb_to_hsv(rgb):
    c = np.asarray(rgb, np.float32) / 255.0
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    mx = c.max(-1)
    mn = c.min(-1)
    d = mx - mn
    safe = np.where(d == 0, 1, d)
    h = np.where(mx == r, ((g - b) / safe) % 6, np.where(mx == g, (b - r) / safe + 2, (r - g) / safe + 4))
    h = np.where(d == 0, 0, h) * 60.0
    s = np.where(mx == 0, 0, d / np.where(mx == 0, 1, mx))
    return h, s, mx


def hsv_to_rgb(h, s, v):
    h = (h % 360) / 60.0
    i = np.floor(h).astype(np.int32) % 6
    f = h - np.floor(h)
    p = v * (1 - s)
    q = v * (1 - s * f)
    t = v * (1 - s * (1 - f))
    r = np.choose(i, [v, q, p, p, t, v])
    g = np.choose(i, [t, v, v, q, p, p])
    b = np.choose(i, [p, p, t, v, v, q])
    return np.stack([r, g, b], -1) * 255.0


def ramp_step(rgb, k):
    """Move a colour k steps along a hue-shifted ramp (k<0 darker, k>0 lighter).

    Darker steps lose value, gain saturation and turn toward blue-violet;
    lighter steps gain value, lose saturation and turn toward warm yellow.
    One step is roughly what a 16-bit artist would use between two shades.
    """
    k = np.asarray(k, np.float32)
    h, s, v = rgb_to_hsv(rgb)
    dark = k < 0
    a = np.abs(k)
    v2 = np.where(dark, v * (1 - 0.14 * a), v + (1 - v) * 0.22 * a)
    s2 = np.where(dark, np.maximum(s, 0.08 * a) * (1 + 0.06 * a), s * (1 - 0.12 * a))
    target = np.where(dark, 245.0, 50.0)
    h = np.where(s < 0.08, target, h)          # greys have no hue: take the ramp's
    diff = (target - h + 540) % 360 - 180
    h2 = h + np.sign(diff) * np.minimum(np.abs(diff), 9.0 * a)
    return hsv_to_rgb(h2, np.clip(s2, 0, 1), np.clip(v2, 0, 1))

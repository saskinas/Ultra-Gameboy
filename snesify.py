"""Rule-based "SNESify" demo: reshade a Game Boy screenshot into a 16-bit look.

No generative art. Every output pixel comes from the original pixel's shade,
which material its tile is, and simple lighting:

  1. Map the 4 Game Boy shades to indices 0 (white) .. 3 (black).
  2. Label each 8x8 tile with a material (a hand-written profile here; the real
     enhancer would read tile numbers and collision data from the game).
  3. Separate sprites from the background tile they stand on.
  4. Fill object outlines (posts, trees) to get solid shapes.
  5. Replace dither patterns with smooth tones plus texture noise.
  6. Shade objects as cylinders, spheres or bevels, lit from the top left.
  7. Add drop shadows, contact darkening, shore foam and an SNES-style text box.
  8. Snap to the SNES's 15-bit colour.

Usage: python -I snesify.py   (reads input/*.png, writes out/*.png)
"""
import os
import numpy as np
from PIL import Image, ImageDraw

H, W = 144, 160
HERE = os.path.dirname(os.path.abspath(__file__))
L = np.array([-1.0, -1.0, 1.0]) / np.sqrt(3)  # light from the top left


def hx(*cols):
    return np.array([[int(c[i:i + 2], 16) for i in (1, 3, 5)] for c in cols], float)


RAMPS = {
    # Shadows lean cool, highlights lean warm, as SNES artists shaded.
    'ground': hx('#1e4a3c', '#2c6a44', '#3f8a48', '#5aa64c', '#7cc05a', '#a8d870'),
    'tallgrass': hx('#0e2c2a', '#16452e', '#1f6234', '#30823a', '#4ea23e', '#86c84c', '#bfe470'),
    'post': hx('#2a2030', '#4a3a40', '#6e5a54', '#957d6a', '#b9a284', '#d8c6a2', '#f2e8c8'),
    'tree': hx('#0a1c1e', '#123326', '#1c4d2c', '#286a30', '#3a8a34', '#5aaa3c', '#8ccc54'),
    'water': hx('#14205a', '#1c3488', '#2450b0', '#2e70d0', '#4c96e8', '#7cc0f4', '#c8ecff'),
    'wood': hx('#2e1810', '#4c2a18', '#6e4222', '#925c2e', '#b47c3e', '#d4a058', '#eec680'),
    'dirt': hx('#2a1810', '#4a2e1a', '#6c4626', '#8e6234', '#ae8048'),
    'red': hx('#3a0818', '#6a1022', '#a01c2c', '#d0363a', '#ee6a52', '#fca080'),
    'skin': hx('#7a4030', '#b06a50', '#dc9a74', '#f4c49c', '#fde6c8'),
    'yellow': hx('#5a3a08', '#946412', '#cc9a1c', '#ecc432', '#f8e066', '#fff4b0'),
    'orange': hx('#3a1808', '#6a3010', '#9a4c18', '#c86c24'),
    'purple': hx('#1c1040', '#34226a', '#4e3a98', '#6c58c0', '#9a88e0'),
}

BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0
BAY = np.tile(BAYER, (H // 4 + 1, W // 4 + 1))[:H, :W]
YY, XX = np.mgrid[0:H, 0:W]


def pick(ramp, t, dither=0.0):
    """Stepped ramp lookup (pixel art keeps hard steps); optional ordered dither."""
    n = len(ramp)
    v = np.asarray(t) * (n - 1) + 0.5 + (BAY[:np.shape(t)[0], :np.shape(t)[1]] - 0.5) * dither \
        if np.ndim(t) == 2 else np.asarray(t) * (n - 1) + 0.5
    return ramp[np.clip(np.floor(v), 0, n - 1).astype(int)]


def value_noise(scale, seed, sx=1.0):
    rng = np.random.default_rng(seed)
    g = rng.random((int(H / scale) + 3, int(W / (scale * sx)) + 3))
    ys = np.arange(H) / scale
    xs = np.arange(W) / (scale * sx)
    y0 = ys.astype(int)
    x0 = xs.astype(int)
    fy = (ys - y0)[:, None]
    fx = (xs - x0)[None, :]
    fy = fy * fy * (3 - 2 * fy)
    fx = fx * fx * (3 - 2 * fx)
    a = g[y0][:, x0]
    b = g[y0][:, x0 + 1]
    c = g[y0 + 1][:, x0]
    d = g[y0 + 1][:, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


# ---------- small morphology helpers (numpy only) ----------
def shift(m, dy, dx, fill=False):
    r = np.roll(m, (dy, dx), (0, 1))
    if dy > 0:
        r[:dy] = fill
    elif dy < 0:
        r[dy:] = fill
    if dx > 0:
        r[:, :dx] = fill
    elif dx < 0:
        r[:, dx:] = fill
    return r


def dilate(m):
    out = m.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            out |= shift(m, dy, dx)
    return out


def erode(m):
    out = m.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            out &= shift(m, dy, dx, True)
    return out


def fill_holes(m):
    """True where m is set or where the pixel can't reach the border through ~m."""
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
    """Close small gaps in a black outline, fill it, and keep the outline itself."""
    return erode(fill_holes(dilate(outline))) | outline


def box_blur(a, r=1):
    acc = np.zeros_like(a, float)
    k = 0
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            acc += shift(a.astype(float), dy, dx, 0.0)
            k += 1
    return acc / k


# ---------- profiles: what the real enhancer would read from the game ----------
PROFILES = {
    'tall_grass': {
        'colors': {(248, 248, 248): 0, (88, 184, 248): 1, (184, 136, 248): 2, (24, 24, 24): 3},
        'tiles': {0: 'P', 1: 'P', 3: 'P', 4: 'P', 2: 'G', 5: 'g',
                  **{i: 'S' for i in range(6, 16)}, **{i: 'U' for i in range(16, 42)}},
        'sprite_under': ('G', 2),
        # (top y, bottom y, main ramp, light ramp)
        'sprites': [(56, 76, 'red', 'skin'), (76, 96, 'orange', 'yellow')],
    },
    'route24': {
        'colors': {(248, 248, 248): 0, (88, 184, 248): 1, (40, 64, 248): 2, (24, 24, 24): 3},
        'tiles': {0: 'W', 1: 'P', 2: 'P', 5: 'P', 6: 'P', 3: 'B', 4: 'g', 7: 'L',
                  14: 'T', 15: 'T', 18: 'T', 19: 'T',
                  **{i: 'S' for i in (8, 9, 10, 11, 12, 13, 16, 17, 20, 21, 22, 23, 24, 25)},
                  **{i: 'U' for i in range(26, 33)}},
        'sprite_under': ('g', 4),
        'sprites': [(40, 60, 'purple', 'skin'), (60, 76, 'red', 'skin'), (76, 96, 'orange', 'yellow')],
    },
}


def snesify(name):
    prof = PROFILES[name]
    rgb = np.array(Image.open(os.path.join(HERE, 'input', name + '.png')).convert('RGB'))
    idx = np.zeros((H, W), int)
    for col, i in prof['colors'].items():
        idx[(rgb == col).all(-1)] = i

    # 1-2. tiles -> materials
    seen, tile_pat = {}, {}
    mat = np.full((H, W), 'g', '<U1')
    for ty in range(18):
        for tx in range(20):
            sl = (slice(ty * 8, ty * 8 + 8), slice(tx * 8, tx * 8 + 8))
            key = rgb[sl].tobytes()
            if key not in seen:
                seen[key] = len(seen)
                tile_pat[seen[key]] = idx[sl].copy()
            mat[sl] = prof['tiles'].get(seen[key], 'g')
    tile_mat = mat.copy()

    # 3. sprites: anything that differs from the tile underneath, plus enclosed pixels
    under_mat, under_tile = prof['sprite_under']
    bg_idx = np.tile(tile_pat[under_tile], (18, 20))
    S = mat == 'S'
    ys, xs = np.where(S)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    diff = S & (idx != bg_idx)
    sub = diff[y0:y1, x0:x1]
    spr = np.zeros((H, W), bool)
    spr[y0:y1, x0:x1] = erode(fill_holes(dilate(sub))) | sub
    spr &= S
    sprite_idx = idx.copy()
    idx = np.where(S & ~spr, bg_idx, idx)          # background continues under the sprite
    mat[S] = under_mat

    # 4. solid objects from outlines, per 16x16 block
    obj = np.zeros((H, W), bool)
    fringe = np.zeros((H, W), bool)                 # artist-drawn shadow pixels outside outlines
    centers = np.zeros((H, W, 4))                   # cx, cy, rx, ry per object pixel
    for my in range(9):
        for mx in range(10):
            sl = (slice(my * 16, my * 16 + 16), slice(mx * 16, mx * 16 + 16))
            m = mat[sl]
            kind = m[0, 0]
            if kind in 'PT' and (m == kind).all():
                f = solid_from_outline(idx[sl] == 3)
                oy, ox = np.where(f)
                cx, cy = ox.mean() + mx * 16, oy.mean() + my * 16
                rx, ry = (ox.max() - ox.min() + 1) / 2, (oy.max() - oy.min() + 1) / 2
                centers[sl] = (cx, cy, rx, ry)
                obj[sl] = f
                fringe[sl] = ~f & (idx[sl] != 0)
                m[~f] = 'g'

    solid = obj | spr
    out = np.zeros((H, W, 3))
    n_big = value_noise(14, 1)
    n_mid = value_noise(5, 2)
    n_small = np.random.default_rng(3).random((H, W))

    # 5. flat materials
    g = mat == 'g'
    t = 0.55 + 0.30 * (n_big - 0.5) + 0.14 * (n_mid - 0.5)
    # The GB ground tile repeats the same specks every 8 px; keep only some so
    # they read as scattered flowers and pebbles instead of a grid.
    speck = g & (tile_mat == 'g') & (idx == 1) & (n_small > 0.45) & (n_mid > 0.35)
    t = np.where(speck, t + 0.3, t)
    out[g] = pick(RAMPS['ground'], t, 0.7)[g]
    petals = speck & (n_small > 0.88)
    out[petals] = hx('#f8f0b8')[0]

    G = mat == 'G'
    base = np.choose(idx, [0.06, 0.82, 0.52, 0.0])
    row = YY % 8
    t = base - 0.07 * (row - 3.5) / 3.5 + 0.10 * (n_mid - 0.5)
    out[G] = pick(RAMPS['tallgrass'], t)[G]

    Wm = mat == 'W'
    land = ~Wm
    near1 = dilate(land) & Wm
    near2 = dilate(dilate(land)) & Wm & ~near1
    near3 = dilate(dilate(dilate(land))) & Wm & ~near1 & ~near2
    base = np.choose(idx, [0.80, 0.42, 0.30, 0.10])
    t = base + 0.18 * (n_big - 0.5)
    t = np.where(near3 | near2, t + 0.14, t)
    t = np.where(near1, 0.98, t)
    out[Wm] = pick(RAMPS['water'], t, 0.5)[Wm]
    bank = dilate(Wm) & g
    out[bank] = pick(RAMPS['ground'], np.full((H, W), 0.12))[bank]

    B = mat == 'B'
    grain = value_noise(2, 5, sx=4)
    base = np.choose(idx, [0.36, 0.82, 0.52, 0.02])
    t = base + 0.16 * (grain - 0.5)
    out[B] = pick(RAMPS['wood'], t)[B]

    Lm = mat == 'L'
    top = (YY % 8) < 4
    tg = np.choose(idx, [0.9, 0.75, 0.55, 0.15])
    td = np.choose(idx, [0.85, 0.65, 0.45, 0.02])
    lg = Lm & top & (idx != 3)
    ld = Lm & ~lg
    out[lg] = pick(RAMPS['ground'], tg)[lg]
    out[ld] = pick(RAMPS['dirt'], td)[ld]

    # 6. lit objects
    cx, cy, rx, ry = (centers[..., i] for i in range(4))
    edge = solid & ~erode(solid)
    lit_edge = edge & ~shift(solid, 1, 1)           # outline pixels facing the light

    P = obj & (mat == 'P')
    nx = np.clip((XX - cx) / np.maximum(rx, 1), -1, 1)
    nz = np.sqrt(1 - nx ** 2)
    lam = np.clip((nx * L[0] + nz * L[2] + 0.6) / 1.2, 0, 1)  # cylinder
    cap = (idx == 0) & (YY < cy)                    # white in the top half is the post's top
    t_side = np.choose(idx, [0.72, 0.6, 0.34, 0.0]) + 0.6 * (lam - 0.5)
    t_side -= 0.12 * ((YY - (cy - ry)) > 1.55 * ry)
    t_cap = 0.92 + 0.1 * (-nx)
    t = np.where(cap, t_cap, t_side)
    t = np.where(idx == 3, np.where(lit_edge, 0.18, 0.0), t)
    out[P] = pick(RAMPS['post'], t)[P]

    T = obj & (mat == 'T')
    ny = np.clip((YY - cy) / np.maximum(ry, 1), -1, 1)
    nz = np.sqrt(np.clip(1 - nx ** 2 - ny ** 2, 0, 1))
    lam = np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0, 1)
    base = np.choose(idx, [0.95, 0.72, 0.5, 0.15])
    t = 0.5 * base + 0.62 * lam - 0.08
    t = np.where(edge & (idx == 3), np.where(lit_edge, 0.12, 0.0), t)
    out[T] = pick(RAMPS['tree'], t)[T]

    # sprites: bevel lighting from distance to the edge
    d = np.zeros((H, W))
    m = spr.copy()
    for _ in range(3):
        m = erode(m)
        d += m
    h = box_blur(d, 1)
    gy, gx = np.gradient(h)
    nrm = np.stack([-gx, -gy, np.ones_like(h)], -1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    lam = nrm @ L
    shade = 0.55 * (lam - L[2])
    for top_y, bot_y, main, light in prof['sprites']:
        band = spr & (YY >= top_y) & (YY < bot_y)
        si = sprite_idx
        tm = np.choose(si, [0.0, 0.72, 0.5, 0.0]) + shade
        tm = np.where(si == 3, np.where(lit_edge, 0.2, 0.0), tm)
        tl = 0.7 + shade
        mm = band & (si != 0)
        ll = band & (si == 0)
        out[mm] = pick(RAMPS[main], tm)[mm]
        out[ll] = pick(RAMPS[light], tl)[ll]

    # 7. shadows and contact darkening on the ground
    ground_like = np.isin(mat, ['g', 'G', 'L']) & ~solid
    cast = (shift(solid, 2, 2) | shift(solid, 1, 2) | shift(solid, 2, 1) | fringe) & ground_like
    contact = dilate(solid) & ground_like & ~cast
    out[cast] *= np.array([0.62, 0.66, 0.86])
    out[contact] *= 0.86

    # text box, SNES style: stepped blue gradient, white text with a drop shadow
    U = tile_mat == 'U'
    if U.any():
        uy, ux = np.where(U)
        sl = (slice(uy.min(), uy.max() + 1), slice(ux.min(), ux.max() + 1))
        border = np.zeros((H, W), bool)
        border[uy.min():uy.min() + 8] = True
        border[uy.max() - 7:uy.max() + 1] = True
        border[:, :8] = True
        border[:, -8:] = True
        frame = U & border & (idx == 3)
        inside = np.zeros((H, W), bool)
        inside[sl] = fill_holes(dilate(frame[sl])) & ~dilate(frame[sl])
        text = inside & (idx == 3)
        steps = hx('#3a56c8', '#3048b8', '#283ca4', '#203090', '#1a267c', '#141e68')
        k = np.clip(((YY - uy.min()) / (uy.max() - uy.min() + 1) * len(steps)).astype(int), 0, len(steps) - 1)
        out[U] = hx('#0c0c28')[0]
        out[inside] = steps[k][inside]
        bevel = dilate(frame) & inside & ~text
        out[bevel] = hx('#7880c8')[0]
        out[frame] = hx('#e8ecf8')[0]
        sh = shift(text, 1, 1) & inside & ~text
        out[sh] = hx('#060c38')[0]
        out[text] = hx('#f8f8f8')[0]

    # 8. 15-bit colour, like the SNES
    out = (np.clip(out, 0, 255) // 8 * 8).astype(np.uint8)
    return rgb, out


def main():
    os.makedirs(os.path.join(HERE, 'out'), exist_ok=True)
    S, gap = 4, 12
    rows = []
    for name in PROFILES:
        orig, new = snesify(name)
        Image.fromarray(new).save(os.path.join(HERE, 'out', name + '_snes.png'))
        rows.append((Image.fromarray(orig).resize((W * S, H * S), Image.NEAREST),
                     Image.fromarray(new).resize((W * S, H * S), Image.NEAREST)))
    head = 28
    sheet = Image.new('RGB', (W * S * 2 + gap * 3, head + (H * S + gap) * len(rows) + gap), (20, 20, 28))
    d = ImageDraw.Draw(sheet)
    d.text((gap, 8), 'Game Boy original (Super Game Boy palette)', fill=(220, 220, 230))
    d.text((gap * 2 + W * S, 8), 'Rule-based reshade (no generative art)', fill=(220, 220, 230))
    for i, (a, b) in enumerate(rows):
        y = head + i * (H * S + gap)
        sheet.paste(a, (gap, y))
        sheet.paste(b, (gap * 2 + W * S, y))
    sheet.save(os.path.join(HERE, 'out', 'comparison.png'))
    print('wrote out/comparison.png')


if __name__ == '__main__':
    main()

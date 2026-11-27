"""Solve line-art backgrounds on a whole area (see ugb/atlas.py).

Some games draw their backgrounds as white shapes outlined on a white sky:
clouds, hills, domes, hoops and towers, many of them open (a dome stops above
the grass, a tower runs past the top of the level). On a slice of the map that
is guesswork; on the whole area it can be solved once, per pixel:

1. Clouds: white enclosed by outlines, made at least a quarter of cloud-bottom
   tiles ('Z'), is a cloud body.
2. Close the hills: every long vertical outline (a dome's leg) carries on
   straight down to the land, so a dome's inside is cut off from the sky.
3. Sort the white regions: hills are drawn with a dark outer line and a light
   inner band. A region whose border meets more band-with-the-line-behind-it
   than bare line is inside a hill; otherwise it is sky.
4. Tubes: thin white between two outlines (hoops, arches) is a tube's body.
5. Rims: a hill's band, and the white dithered into it, is its shaded rim.

6. Trunks: white walled in mostly by trunk-side tiles ('V') is a tree's trunk.
7. A cloud's own outline is cloud edge (its arcs share tiles with hills).

Output codes: 0 not line art, 1 sky, 2 cloud, 3 hill, 5 rim, 6 trunk, 7 cloud edge.
"""
import numpy as np
from scipy import ndimage as ndi

SKY, CLOUD, HILL, RIM, TRUNK, CLOUD_EDGE = 1, 2, 3, 5, 6, 7


def below_ledge_line(shade, ledge, tile_top):
    """Pixels of ledge tiles at or below the first dark pixel in their tile column
    (the ground's top line): the ground. Above it, a ledge tile is still sky or
    whatever stands on the ground. tile_top: per row, the first row of its tile."""
    H = shade.shape[0]
    rows = np.arange(H)[:, None]
    dark = ledge & (shade >= 2)
    last = np.maximum.accumulate(np.where(dark, rows, -1), axis=0)
    return ledge & (last >= tile_top[:, None])


def _nb4(x):
    return np.roll(x, 1, 0) | np.roll(x, -1, 0) | np.roll(x, 1, 1) | np.roll(x, -1, 1)


def solve(shade, mat, seen, codes, edge=None, front=None):
    """shade: (H, W) 0 white .. 3 black; mat: (H, W) material code per pixel;
    seen: (H, W) bool, pixels whose tile was captured; codes: material letters
    to code values (the renderer's M); edge: (H, W) bool, pixels of tiles that
    are hill outlines even though labelled as land (a tile the game uses for
    both a cliff and a tower's side); front: (H, W) bool, pixels of tiles drawn
    in front of the shapes behind (hoop legs, a room's pillars), whose lines
    don't vote on what a region is. Returns the (H, W) kind map."""
    H, W = shade.shape
    Z, h, J = codes['Z'], codes['h'], codes['J']
    # land: ground tiles, ledges included (their part above the ground line is
    # settled at the end, from what is above it)
    tile_top = (np.arange(H) // 8) * 8
    ledge_ground = below_ledge_line(shade, mat == codes['L'], tile_top)
    land = np.isin(mat, [codes[c] for c in 'ELGKBUTSVQFOHMD']) | ~seen     # (solid materials)
    if edge is not None:
        land &= ~edge
    white = (shade == 0) & ~land
    # line-art white: connected areas of 12 px or more (not texture dots)
    lab, n = ndi.label(white)
    big = np.bincount(lab.ravel(), minlength=n + 1) >= 12
    big[0] = False
    art = big[lab]
    out = np.where(art, SKY, 0).astype(np.uint8)
    hm = (mat == h) if edge is None else (mat == h) | edge
    line = (shade >= 2) & ~land
    band = (shade == 1) & (hm | (mat == Z))

    # 1. clouds: enclosed regions (the area's own edge counts as open)
    lab, n = ndi.label(art)
    if n:
        # (cut off by the left or right end of the area: maybe open sky beyond.
        # The top and bottom are the level's own; a cloud cut by them is a cloud.)
        edge = np.zeros(n + 1, bool)
        edge[np.concatenate([lab[:, 0], lab[:, -1]])] = True
        zc = np.bincount(lab[art & (mat == Z)], minlength=n + 1)
        allc = np.bincount(lab[art & np.isin(mat, [Z, h])], minlength=n + 1)
        size = np.bincount(lab.ravel(), minlength=n + 1)
        thick = np.asarray(ndi.maximum(ndi.distance_transform_edt(art), lab, np.arange(n + 1)))
        cloud = ((zc >= 0.25 * np.maximum(allc, 1)) & (zc >= 0.2 * size) & (zc > 0) & (size < 6000)
                 & (thick > 1.5))         # (a cloud's inside lies largely in cloud tiles)
        # cut by the edge: only if mostly cloud tiles (of its pixels, or of those
        # in outline tiles)
        cloud &= ~edge | (zc > 0.5 * size) | ((zc >= 0.75 * allc) & (zc >= 0.25 * size))
        # or by shape: a closed shape that floats (touches no ground) with its
        # shading along the bottom of its inside (big clouds are mostly drawn
        # with the arc tiles hills use)
        touch_land = np.zeros(n + 1, bool)
        touch_land[lab[art & _nb4(land)]] = True
        sh_px = art & _nb4((shade == 1) & np.isin(mat, [Z, h]))
        ys_ = np.broadcast_to(np.arange(H)[:, None], (H, W))
        nsh = np.bincount(lab[sh_px], minlength=n + 1)
        ysh = np.bincount(lab[sh_px], weights=ys_[sh_px], minlength=n + 1) / np.maximum(nsh, 1)
        ymid = np.bincount(lab[art], weights=ys_[art], minlength=n + 1) / np.maximum(size, 1)
        # (cut by the area's end: only with its shading clearly low, as a cloud's is)
        floating = (~touch_land & (~edge | (ysh > ymid + 4)) & (size < 6000) & (thick > 1.5)
                    & (nsh >= 4) & (ysh > ymid))
        floating[0] = False
        # a hoop's inside is a narrow upright slot; clouds are wider than tall
        hoop = np.zeros(n + 1, bool)
        for r in np.nonzero(floating)[0]:
            sl = ndi.find_objects((lab == r).astype(np.int32))[0]
            hh, ww = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
            hoop[r] = ww <= 12 and hh >= 1.3 * ww
        if solve.debug_top:
            for r in np.nonzero(floating)[0]:
                ys0, xs0 = np.nonzero(lab == r)
                print('floating at x %d y %d size %d %s' % (xs0.mean(), ys0.mean(), size[r], 'HOOP' if hoop[r] else ''))
        floating &= ~hoop
        if solve.probe is not None:
            r = lab[solve.probe]
            print('cloud probe', r, 'size', size[r], 'zc', zc[r], 'allc', allc[r], 'thick', thick[r], 'edge', edge[r],
                  'land', touch_land[r], 'nsh', nsh[r], 'ysh', ysh[r], 'ymid', ymid[r], 'cloud', cloud[r])
        cloud |= floating
        cloud[0] = False
        out[cloud[lab]] = CLOUD
    cloud_px = out == CLOUD
    # the cloud's outline goes with it (so the shapes behind see through it)
    cloud_shape = ndi.binary_dilation(cloud_px, iterations=3) & ~white | cloud_px

    # a hill's band and the white dithered into it make one zone
    hband0 = band & hm & ~cloud_shape
    bz = (ndi.binary_closing(hband0, np.ones((3, 3), bool)) | hband0) & ~line

    # 2. complete the implied contours. Where an outline simply stops (a dome's
    # leg above the grass, a side that slants down and stops), the eye carries
    # it on the way it was heading until it meets something; so do we, as a
    # wall for sorting the regions. In this art the implied contours fall:
    # down, or down at a slant (shapes cut off at the top or sides are closed
    # by the area's own edges). An end is where an outline
    # has run straight for 8 px and the next pixel is open white; an arc that
    # merely curves away is not an end, because more of it lies just ahead.
    # (Clouds in front stop a contour: it carries on behind them, unseen.)
    hs = (line | bz) & ~cloud_shape
    hs_thick = ndi.binary_dilation(hs)            # (staircase diagonals)
    open_ = white & ~bz
    rows = np.arange(H)[:, None]
    cols = np.arange(W)[None, :]
    curtain = np.zeros((H, W), bool)
    for dy, dx in ((1, 0), (1, 1), (1, -1)):
        end = hs & np.roll(open_, (-dy, -dx), (0, 1))
        end &= np.roll(hs, (dy, dx), (0, 1))
        for k in range(2, 8):
            end &= np.roll(hs_thick, (k * dy, k * dx), (0, 1))
        if not end.any():
            continue
        # nothing of the outline just ahead (2-12 px on, 5 px either side)
        ahead = np.zeros((H, W), bool)
        for t in range(2, 13):
            ahead |= np.roll(hs, (-t * dy, -t * dx), (0, 1))
        py, px = dx, -dy                            # sideways
        wide = ahead.copy()
        for s_ in range(1, 6):
            wide |= np.roll(ahead, (s_ * py, s_ * px), (0, 1)) | np.roll(ahead, (-s_ * py, -s_ * px), (0, 1))
        end &= ~wide
        # carry it on until it meets anything (at most 80 px)
        cur = end
        for _ in range(80):
            cur = np.roll(cur, (dy, dx), (0, 1)) & open_
            if not cur.any():
                break
            curtain |= cur

    # a leg that runs straight down into a cloud in front of it carries on
    # behind the cloud, and from the cloud's underside on down to what it meets
    occ = hs & np.roll(cloud_shape, -1, 0) & ~cloud_shape
    for k in range(1, 8):
        occ &= np.roll(hs_thick, k, 0)
    cur = occ
    if solve.debug_top:
        print("occluded leg starts", list(zip(*np.nonzero(occ)))[:20])
    for _ in range(96):
        nxt = np.roll(cur, 1, 0)
        behind = nxt & (cloud_shape | bz)        # (and the dithered foot under it)
        out_ = nxt & open_ & ~cloud_shape
        curtain |= out_
        cur = behind | out_
        if not cur.any():
            break

    # 3. sort the white regions by what their border meets
    free = art & ~cloud_px & ~curtain & ~bz
    lab, n = ndi.label(free)
    if n:
        # a contact is 'inner' when the white touches a band that has the dark
        # line on its far side (1-4 px further on), 'outer' when it touches a
        # line directly
        # (only hill outlines vote: clouds are settled, and their top edge has a
        # light rim on the outside that would read as an inner band)
        hband = bz
        hline = line & ~cloud_shape
        inner = np.zeros((H, W), bool)
        outer = np.zeros((H, W), bool)
        outer_all = np.zeros((H, W), bool)       # (front lines included: for tubes)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nb_band = np.roll(hband, (-dy, -dx), (0, 1))         # band next to us this way
            far = np.zeros((H, W), bool)
            for k in range(2, 6):
                far |= np.roll(hline, (-k * dy, -k * dx), (0, 1))
            inner |= free & nb_band & far
            own = hline & hm if front is None else hline & hm & ~front
            outer |= free & np.roll(own, (-dy, -dx), (0, 1)) & ~_nb4(bz)
            outer_all |= free & np.roll(hline & hm, (-dy, -dx), (0, 1)) & ~_nb4(bz)
        solve.debug = (inner, outer, lab, curtain)
        vin = np.bincount(lab[inner], minlength=n + 1)
        vout = np.bincount(lab[outer], minlength=n + 1)
        size = np.bincount(lab.ravel(), minlength=n + 1)
        hill = (vin > vout) & (vin >= 6)
        hill[0] = False
        out[hill[lab]] = HILL
        # 4. tubes: thin regions between outlines
        dist = ndi.distance_transform_edt(free)
        thick = ndi.maximum(dist, lab, np.arange(n + 1))
        vall = np.bincount(lab[outer_all], minlength=n + 1)
        tube = (np.asarray(thick) <= 2.5) & (vin + vall >= 4) & (size < 400)
        tube[0] = False
        out[tube[lab]] = HILL
        # the inside of an arch meets mostly bare line: it shows what is behind the
        # arch. Small enclosed regions like that take the majority of the
        # hill-or-sky around them (a few px out, past the arch's own lines).
        edge = np.zeros(n + 1, bool)
        edge[np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])] = True
        cand = np.nonzero((size < 2000) & ~edge & ~hill & ~tube)[0]
        if solve.probe is not None:
            r = lab[solve.probe]
            print('probe region', r, 'size', size[r], 'vin', vin[r], 'vout', vout[r], 'edge', edge[r],
                  'hill', hill[r], 'tube', tube[r])
        for r in cand:
            if r == 0:
                continue
            reg = lab == r
            ys, xs = np.nonzero(reg)
            y0, y1 = max(ys.min() - 10, 0), min(ys.max() + 11, H)
            x0, x1 = max(xs.min() - 10, 0), min(xs.max() + 11, W)
            sub = reg[y0:y1, x0:x1]
            ring = ndi.binary_dilation(sub, iterations=8) & ~ndi.binary_dilation(sub, iterations=3)
            o = out[y0:y1, x0:x1][ring]
            nh, ns = int((o == HILL).sum()), int((o == SKY).sum())
            if nh > ns:
                out[reg] = HILL
    # curtains take the kind beside them
    # (a hill around it, any of 8 neighbours, 2 px out: it is the hill's edge; else sky)
    near_h = ndi.binary_dilation((out == HILL) & ~curtain, np.ones((3, 3), bool), iterations=2)
    near_s = ndi.binary_dilation((out == SKY) & ~curtain, np.ones((3, 3), bool), iterations=2)
    out[curtain & near_h] = HILL
    out[curtain & ~near_h & near_s] = SKY

    # 5. rims: a hill's band zone, wherever it touches the hill, is its shaded
    # rim (white dithered into it included); a band zone touching no hill isn't
    # line art (a cliff's dithered side keeps its tile's own drawing)
    lb, nbz = ndi.label(bz | (band & hm & ~cloud_shape))
    if nbz:
        touch = np.zeros(nbz + 1, bool)
        touch[lb[ndi.binary_dilation(out == HILL) & (lb > 0)]] = True
        touch[0] = False
        zone = lb > 0
        out[zone & touch[lb] & (shade <= 1)] = RIM
        out[zone & ~touch[lb] & (out == SKY)] = 0
    # slivers of sky under 4 px across with hill on both sides (where a dome's
    # outline meets the one behind it): part of the hill
    sky = out == SKY
    thin = sky & ~ndi.maximum_filter(ndi.minimum_filter(sky, (1, 4)), (1, 4))
    hl = np.isin(out, [HILL, RIM]) | (line & hm)
    lf = np.zeros((H, W), bool)
    rt = np.zeros((H, W), bool)
    for k in range(1, 5):
        lf |= np.roll(hl, k, 1)
        rt |= np.roll(hl, -k, 1)
    out[thin & lf & rt] = HILL
    # trunks: free regions walled in mostly by trunk-side tiles
    V = codes['V']
    if (mat == V).any():
        lt, nt = ndi.label(out == SKY)
        if nt:
            # (trunk sides, and ground edges: the tall tree with the door uses them)
            nv = np.bincount(lt[_nb4(np.isin(mat, [V, codes['E']])) & (lt > 0)], minlength=nt + 1)
            nw = np.bincount(lt[_nb4(~white) & (lt > 0)], minlength=nt + 1)
            sz = np.bincount(lt.ravel(), minlength=nt + 1)
            # (and tall: trunks and the tall tree stand upright)
            tall = np.zeros(nt + 1, bool)
            for i_, q in enumerate(ndi.find_objects(lt), 1):
                if q is not None:
                    tall[i_] = (q[0].stop - q[0].start) >= 1.5 * (q[1].stop - q[1].start)
            # (walled on both sides, not just standing on the ground)
            vt = np.isin(mat, [V, codes['E']])
            nl = np.bincount(lt[np.roll(vt, 1, 1) & (lt > 0)], minlength=nt + 1)
            nr = np.bincount(lt[np.roll(vt, -1, 1) & (lt > 0)], minlength=nt + 1)
            trunk = (nv > 0.35 * nw) & (nv >= 12) & (sz < 12000) & tall & (nl >= 6) & (nr >= 6)
            # (or cut off by the area's left or right end, with a clear trunk wall
            # on its other side: the tree with the door at the treetop's corner)
            at_l = np.zeros(nt + 1, bool)
            at_r = np.zeros(nt + 1, bool)
            at_l[lt[:, 0]] = True
            at_r[lt[:, -1]] = True
            # (trunk-side tiles proper, not ground, met on their shaded side: the
            # first mark from the region toward the wall is the light shading
            # inside a trunk, not its dark outline, which faces the outside)
            vo = mat == V

            def soft(d):
                first = np.zeros((H, W), np.uint8)
                for k_ in range(4, 0, -1):
                    s_ = np.roll(shade, -d * k_, 1)
                    first = np.where(s_ > 0, s_, first)
                return np.roll(vo, -d, 1) & (first == 1) & (lt > 0)
            nlv = np.bincount(lt[soft(-1)], minlength=nt + 1)
            nrv = np.bincount(lt[soft(1)], minlength=nt + 1)
            trunk |= (sz < 12000) & ((at_l & (nrv >= 24)) | (at_r & (nlv >= 24)))
            trunk[0] = False
            trunk[0] = False
            if solve.debug_top:
                for r in np.nonzero(at_l | at_r)[0]:
                    if r:
                        print('edge region', r, 'size', sz[r], 'nv', nv[r], 'nw', nw[r], 'nl', nl[r], 'nr', nr[r],
                              'V l/r', nlv[r], nrv[r], 'trunk', trunk[r])
            out[trunk[lt]] = TRUNK
            # branches (Whispy Woods' nose): small wide shapes against a trunk
            # (solved as sky or, closed and shaded below, as a cloud)
            near_t = ndi.binary_dilation(out == TRUNK, iterations=3)
            lb, nb_ = ndi.label(np.isin(out, [SKY, CLOUD]))
            nt_ = np.bincount(lb[near_t & (lb > 0)], minlength=nb_ + 1)
            szb = np.bincount(lb.ravel(), minlength=nb_ + 1)
            for i_, q in enumerate(ndi.find_objects(lb), 1):
                if q is not None and nt_[i_] and szb[i_] < 400:
                    if (q[1].stop - q[1].start) >= 2.5 * (q[0].stop - q[0].start):
                        out[lb == i_] = TRUNK
    # a cloud's own outline: cloud edge
    out[cloud_shape & ~white & (out == 0) & ~land] = CLOUD_EDGE
    # completed contours next to a rim: part of that hill
    near_r = ndi.binary_dilation(np.isin(out, [HILL, RIM]) & ~curtain, np.ones((3, 3), bool), iterations=2)
    out[curtain & (out == SKY) & near_r] = HILL

    # a completed contour left as sky with hill on both sides of it (a dome's
    # leg carried down through the dome in front): part of that hill
    hillish = (out == HILL) | (out == RIM)
    for d in (1, 2):
        lr = np.roll(hillish, d, 1) & np.roll(hillish, -d, 1)
        ud = np.roll(hillish, d, 0) & np.roll(hillish, -d, 0)
        out[curtain & (out == SKY) & (lr | ud)] = HILL

    # 6. grass standing on the ground: the white around its blades takes the kind
    # of the white just above it; a hill reaches down through the grass to the
    # land, and only right above the land fades into the sky with a dither
    G = codes['G']
    # (and the white of a ledge tile above its ground line, the same way)
    wg = (shade == 0) & ((mat == G) | ((mat == codes['L']) & ~ledge_ground)) & seen
    if wg.any():
        # (past the blades and a ledge's top, never through a ledge's ground)
        src = np.maximum.accumulate(np.where(~((mat == G) | ((mat == codes['L']) & ~ledge_ground)), rows, -1),
                                    axis=0)
        above = np.where(src >= 0, out[np.maximum(src, 0), cols], 0)
        above = np.where(above == RIM, HILL, above)
        out[wg] = above[wg]          # (solid above, as in the band below the ground: none)
        landpx = np.isin(mat, [codes['E'], codes['L']]) & (shade > 0)
        down = np.minimum.accumulate(np.where(landpx, rows, H + 64)[::-1], axis=0)[::-1] - rows
        alpha = np.clip((down - 1) / 6.0, 0, 1)
        bay = np.tile(np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0,
                      (H // 4 + 1, W // 4 + 1))[:H, :W]
        out[wg & (out == HILL) & (alpha <= bay)] = SKY
    return out


solve.probe = None
solve.debug_top = False


INTERIOR, PILLAR, DOORWAY, TRIM = 8, 9, 10, 11


def interiors(kind, shade, room, land):
    """Rooms behind doors: a big black region in `room` tiles (the preset's
    interior tiles) is the room's back wall; hill shapes touching it are its
    pillars; a white region walled mostly by it is a doorway (light from outside).
    Outdoors the same black tile is only a small doorway, too small to count."""
    black = room & (shade == 3)
    lab, n = ndi.label(black)
    if not n:
        return kind
    size = np.bincount(lab.ravel())
    big = np.nonzero(size >= 12 * 64)[0]
    big = big[big > 0]
    if not len(big):
        return kind
    wall = black          # (an area with a room is a room: all its black is wall)
    kind = kind.copy()
    kind[wall] = INTERIOR
    # doorways: white regions whose border is mostly the wall
    white = (shade == 0) & ~land & ~wall
    wl, wn = ndi.label(white)
    if wn:
        ring = ndi.binary_dilation(white) & ~white
        # each ring pixel votes for its white neighbour region(s)
        nbr = np.maximum.reduce([np.roll(wl, d, a) for a in (0, 1) for d in (1, -1)])
        tot = np.bincount(nbr[ring], minlength=wn + 1)
        onwall = np.bincount(nbr[ring & ndi.binary_dilation(wall, iterations=2)], minlength=wn + 1)
        wsize = np.bincount(wl.ravel(), minlength=wn + 1)
        door = np.nonzero((onwall >= 0.6 * np.maximum(tot, 1)) & (wsize < 60 * 64))[0]
        door = door[door > 0]
        kind[np.isin(wl, door)] = DOORWAY
        # thin white strips along the wall (above a floor beam): a lit trim
        thick = np.asarray(ndi.maximum(ndi.distance_transform_edt(white), wl, np.arange(wn + 1)))
        flat = np.zeros(wn + 1, bool)
        for r, q in enumerate(ndi.find_objects(wl), 1):
            if q is not None:
                flat[r] = (q[1].stop - q[1].start) >= 3 * (q[0].stop - q[0].start)
        trim = np.nonzero((onwall > 0) & (thick <= 1.5) & flat)[0]
        trim = trim[(trim > 0) & ~np.isin(trim, door)]
        kind[np.isin(wl, trim)] = TRIM
        # pillars: tall narrow white strips beside the wall (columns drawn with
        # double lines), and hill shapes touching it
        near5 = ndi.binary_dilation(wall, iterations=8)
        tn = np.bincount(wl[near5 & white], minlength=wn + 1)
        pill = np.zeros(wn + 1, bool)
        for r, q in enumerate(ndi.find_objects(wl), 1):
            if q is not None and tn[r] and r not in door and r not in trim:
                pill[r] = (q[0].stop - q[0].start) >= 2.5 * (q[1].stop - q[1].start)
        kind[pill[wl] & (wl > 0)] = PILLAR
    near = ndi.binary_dilation(wall, iterations=3)
    hillish = (kind == 3) | (kind == 5)
    hl, hn = ndi.label(hillish)
    if hn:
        touch = np.unique(hl[near & hillish])
        kind[np.isin(hl, touch[touch > 0])] = PILLAR
        # pillars: tall narrow white strips beside the wall (columns drawn with
        # double lines), and hill shapes touching it
        near5 = ndi.binary_dilation(wall, iterations=8)
        tn = np.bincount(wl[near5 & white], minlength=wn + 1)
        pill = np.zeros(wn + 1, bool)
        for r, q in enumerate(ndi.find_objects(wl), 1):
            if q is not None and tn[r] and r not in door and r not in trim:
                pill[r] = (q[0].stop - q[0].start) >= 2.5 * (q[1].stop - q[1].start)
        kind[pill[wl] & (wl > 0)] = PILLAR
    near = ndi.binary_dilation(wall, iterations=3)
    hillish = (kind == 3) | (kind == 5)
    hl, hn = ndi.label(hillish)
    if hn:
        touch = np.unique(hl[near & hillish])
        kind[np.isin(hl, touch[touch > 0])] = PILLAR
        if solve.debug_top:
            for r in range(1, wn + 1):
                if onwall[r] or tn[r]:
                    q = ndi.find_objects((wl == r).astype(np.int32))[0]
                    print('white region', r, 'size', wsize[r], 'thick', thick[r], 'bbox y', q[0].start, q[0].stop,
                          'x', q[1].start, q[1].stop, 'wall', onwall[r], '/', tot[r], 'kinds',
                          np.bincount(kind[wl == r], minlength=12)[[0, 1, 2, 3, 5, 9, 10, 11]])
    return kind


def warm(preset_name):
    """Import what solve_area needs (run once in the worker ahead of time)."""
    import importlib
    import pyboy   # noqa: F401
    from ugb import atlas, render   # noqa: F401
    importlib.import_module(preset_name)


def precapture(rom, state, preset_name):
    """On the title screen: start the game in a copy (the preset's SWEEP
    'start_game') and capture the first area. Returns (area key, result) or None."""
    import importlib
    import io
    from pyboy import PyBoy
    p = importlib.import_module(preset_name)
    pb = PyBoy(rom, window='null', cgb=True, sound_emulated=False)
    pb.load_state(io.BytesIO(state))
    ok = p.SWEEP['start_game'](pb)
    key = p.SWEEP['key'](pb.memory)
    buf = io.BytesIO()
    pb.save_state(buf)
    pb.stop(save=False)
    if not ok or key is None:
        return None
    return key, solve_area(rom, buf.getvalue(), preset_name)


def through_door(rom, door, preset_name, known=(), film=None):
    """From a snapshot with the player by a door (Atlas.doors: snapshot, the
    door's top tile row and left column): go through it and capture the area
    behind, before the player gets there. Returns (area key, result), or None if
    no new area came of it."""
    import importlib
    import io
    from pyboy import PyBoy
    p = importlib.import_module(preset_name)
    state, wr, wc = door
    pb = PyBoy(rom, window='null', cgb=True, sound_emulated=False)
    pb.load_state(io.BytesIO(state))
    m = pb.memory
    sw = p.SWEEP
    key0 = sw['key'](m)
    for b in ('up', 'down', 'left', 'right', 'a', 'b', 'start', 'select'):
        pb.button_release(b)

    def tick(n):
        for _ in range(n):
            pb.tick(1, film is not None)
            if film is not None and len(film) < 600:
                film.append(pb.screen.ndarray[:, :, :3].copy())

    def press(b, n=6):
        pb.button_press(b)
        tick(n)
        pb.button_release(b)

    def entered():
        for _ in range(150):
            tick(1)
            k = sw['key'](m)
            if k is not None and k != key0:
                return k
        return None

    key = None
    for attempt in range(4):
        # hover just above the door for a moment (where the capture pinned him
        # may not be a real place: let go there, he may fall out of the
        # world), then let go so he lands in front of it. Again if an enemy
        # knocks him away.
        cx, cy = sw['camera'](m)
        cx = m[0xFF43] + int(round((cx - m[0xFF43]) / 16.0)) * 16
        cy = m[0xFF42] + int(round((cy - m[0xFF42]) / 16.0)) * 16
        sx_, sy_ = wc * 8 + 8 - cx, wr * 8 - cy - 12
        if 8 <= sx_ < 152 and 8 <= sy_ < 120:
            for i in range(40):
                m[sw['pin_x']], m[sw['pin_y']] = sx_, sy_
                if 'each_frame' in sw:
                    sw['each_frame'](m)
                if i % 8 == 0:
                    pb.button_press('a')
                if i % 8 == 4:
                    pb.button_release('a')
                tick(1)
            pb.button_release('a')
        press('b', 4)              # (let the air out)
        last, still = None, 0
        for _ in range(300):       # land: wait until he stands still on screen
            tick(1)
            y = m[sw['pin_y']]
            still = still + 1 if y == last and y < 0xA0 else 0
            last = y
            if still > 20:
                break
        press('down')              # (swallow anything in his mouth)
        tick(30)
        press('up')                # enter
        key = entered()
        if key is not None:
            break
    if key is None or key in known:
        pb.stop(save=False)
        return None
    buf = io.BytesIO()
    pb.save_state(buf)
    pb.stop(save=False)
    res = solve_area(rom, buf.getvalue(), preset_name)
    through_door.entry = buf.getvalue()        # (for tools: the state on arrival)
    return key, res


def solve_area(rom, state, preset_name, prev=None):
    """Capture an area whole (ugb.atlas) and solve it: the job a preset with SWEEP
    and LINE_ART runs in a worker process when a new area starts. Returns
    (kind map, world x of its left edge, world y of its top, tile hashes, shades).

    prev: an earlier result for the same area, to add to. An area may not have
    been reachable whole the first time (Kirby's forest starts with a fight on a
    locked screen); then it is captured again later from where the player is
    (without restarting it), merged with what was seen before, and solved again."""
    import importlib
    from ugb import atlas
    p = importlib.import_module(preset_name)
    sweep = dict(p.SWEEP)
    if prev is not None:
        sweep.pop('restart', None)
    at = atlas.capture(rom, state, sweep)
    if prev is not None:
        at = _merge(prev, at)
    return solve_atlas(at, p)


def _merge(prev, at):
    """Union of an earlier result's capture and a new one (the new one wins)."""
    from ugb import atlas
    _, px0, py0, ph, ps = prev[:5]
    w = prev[6] if len(prev) > 6 else 0
    if w or at.wrap:
        # a loop: both are one lap from the loop's start (x0 0); the new one wins
        w = w or at.wrap
        y0 = min(py0, at.y0)
        y1 = max(py0 + ph.shape[0] * 8, at.y0 + at.height)
        out = atlas.Atlas((y1 - y0) // 8, w // 8)
        out.y0, out.wrap = y0, w
        for hs, sh, ax, ay in ((ph, ps, px0, py0), (at.hashes, at.shade, at.x0, at.y0)):
            if hs.shape[1] * 8 != w:
                continue
            r = (ay - y0) // 8
            seen = hs >= 0
            out.hashes[r:r + hs.shape[0]][seen] = hs[seen]
            px = np.repeat(np.repeat(seen, 8, 0), 8, 1)
            out.shade[r * 8:(r + hs.shape[0]) * 8][px] = sh[px]
        out.doors, out.tile_keys = at.doors, getattr(at, 'tile_keys', None)
        return out
    # the game's counters wrap (Kirby's tall tree: every 256 px), so the new
    # capture may be placed a multiple of 256 px off: put it where its tiles
    # agree with the earlier one's
    best = (0, 0, 0)
    for dy in (-512, -256, 0, 256, 512):
        for dx in (-256, 0, 256):
            r, c = (at.y0 + dy - py0) // 8, (at.x0 + dx - px0) // 8
            r0, c0 = max(r, 0), max(c, 0)
            r1, c1 = min(r + at.hashes.shape[0], ph.shape[0]), min(c + at.hashes.shape[1], ph.shape[1])
            if r1 <= r0 or c1 <= c0:
                continue
            a = ph[r0:r1, c0:c1]
            b = at.hashes[r0 - r:r1 - r, c0 - c:c1 - c]
            both = (a >= 0) & (b >= 0)
            agree = int(((a == b) & both).sum())
            if both.sum() >= 20 and agree >= 0.8 * both.sum() and agree > best[0]:
                best = (agree, dx, dy)
    at.x0 += best[1]
    at.y0 += best[2]
    x0, y0 = min(px0, at.x0), min(py0, at.y0)
    x1 = max(px0 + ph.shape[1] * 8, at.x0 + at.width)
    y1 = max(py0 + ph.shape[0] * 8, at.y0 + at.height)
    out = atlas.Atlas((y1 - y0) // 8, (x1 - x0) // 8)
    out.x0, out.y0 = x0, y0
    for hs, sh, ax, ay in ((ph, ps, px0, py0), (at.hashes, at.shade, at.x0, at.y0)):
        r, c = (ay - y0) // 8, (ax - x0) // 8
        seen = hs >= 0
        sub = out.hashes[r:r + hs.shape[0], c:c + hs.shape[1]]
        sub[seen] = hs[seen]
        px = np.repeat(np.repeat(seen, 8, 0), 8, 1)
        ssub = out.shade[r * 8:(r + hs.shape[0]) * 8, c * 8:(c + hs.shape[1]) * 8]
        ssub[px] = sh[px]
    out.tile_keys = getattr(at, 'tile_keys', None)     # (the area's own labels: the merge keeps them)
    return out


def solve_atlas(at, p):
    """Solve a captured area (see solve_area). An area that loops sideways is
    solved as three laps side by side and the middle one kept, so shapes that
    cross the loop's seam are seen whole."""
    if getattr(at, 'wrap', 0):
        from ugb import atlas
        n = at.hashes.shape[1]
        big = atlas.Atlas(at.hashes.shape[0], n * 3)
        big.x0, big.y0, big.wrap = at.x0 - at.width, at.y0, 0
        big.hashes[:] = np.tile(at.hashes, (1, 3))
        big.shade[:] = np.tile(at.shade, (1, 3))
        big.tile_keys, big.doors = getattr(at, 'tile_keys', None), getattr(at, 'doors', [])
        kind, _, _, _, _, doors = solve_atlas(big, p)[:6]
        return kind[:, at.width:2 * at.width].copy(), at.x0, at.y0, at.hashes, at.shade, doors, at.wrap
    from ugb.render import M
    mt = np.full(at.hashes.shape, M['?'], np.uint8)
    for k, v in (getattr(at, 'tile_keys', None) or p.TILE_KEYS).items():
        mt[at.hashes == k] = M[v]
    mat = np.repeat(np.repeat(mt, 8, 0), 8, 1)
    seen = np.repeat(np.repeat(at.hashes >= 0, 8, 0), 8, 1)
    edge = np.repeat(np.repeat(np.isin(at.hashes, getattr(p, 'LINE_EDGE_TILES', [])), 8, 0), 8, 1)
    # (in a room's area only: there the pillars stand in front of the outside's
    # shapes; outdoors the hoop legs' lines help hold the open sky)
    front = None
    if np.isin(at.hashes, getattr(p, 'ROOM_TILES', [])).sum() >= 12:
        front = np.repeat(np.repeat(np.isin(at.hashes, getattr(p, 'FRONT_TILES', [])), 8, 0), 8, 1)
    kind = solve(at.shade, mat, seen, M, edge, front)
    rt = getattr(p, 'ROOM_TILES', None)
    if rt:
        room = np.repeat(np.repeat(np.isin(at.hashes, rt), 8, 0), 8, 1)
        land = np.isin(mat, [M[c] for c in 'ELGKBUTSVQFOHMD']) & seen
        kind = interiors(kind, at.shade, room, land)
    if hasattr(p, 'post_solve'):        # (a preset's own last word on the shapes)
        kind = p.post_solve(kind, at, mat, M)
    return kind, at.x0, at.y0, at.hashes, at.shade, getattr(at, 'doors', []), 0

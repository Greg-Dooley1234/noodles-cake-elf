"""Find the individual poses on a keyed sheet.

Do NOT slice sheets on an even grid. The generators lay poses out irregularly:
the elf's base sheet has SEVEN poses in its bottom row while the others have
six, and figures drift well outside their nominal cell. Even-grid slicing
decapitates poses and mixes neighbours together.

Instead: label connected components, attach small parts (a detached fist, a
thrown prop) to the nearest big figure, then order by position.
"""
import numpy as np
from scipy import ndimage

from .chroma import (key_sheet, load_rgb, fill_holes, despill_edges,
                     despill_global, feather, alpha_bbox)

LARGE = 8000          # px area that counts as "a whole figure"
CRUMB = 200           # below this is keying noise


def detect_figures(fg, min_area=1500, merge_gap=30):
    lbl, n = ndimage.label(fg)
    comps = []
    for i in range(1, n + 1):
        m = lbl == i
        a = int(m.sum())
        if a < CRUMB:
            continue
        ys, xs = np.where(m)
        comps.append(dict(mask=m, area=a,
                          box=[xs.min(), ys.min(), xs.max(), ys.max()]))

    parent = list(range(len(comps)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def gap(b1, b2):
        dx = max(0, max(b1[0] - b2[2], b2[0] - b1[2]))
        dy = max(0, max(b1[1] - b2[3], b2[1] - b1[3]))
        return max(dx, dy)

    # Figure-sized blobs never merge with each other: a thin projectile or beam
    # bridging two poses would otherwise fuse them into one.
    larges = [i for i in range(len(comps)) if comps[i]['area'] >= LARGE]
    for i in range(len(comps)):
        if comps[i]['area'] >= LARGE:
            continue
        best, bestg = None, merge_gap + 1
        for j in larges:
            g = gap(comps[i]['box'], comps[j]['box'])
            if g < bestg:
                bestg, best = g, j
        if best is not None:
            parent[find(i)] = find(best)

    groups = {}
    for i in range(len(comps)):
        groups.setdefault(find(i), []).append(i)

    figs = []
    for g in groups.values():
        m = np.zeros_like(fg)
        for i in g:
            m |= comps[i]['mask']
        if int(m.sum()) < min_area:
            continue
        ys, xs = np.where(m)
        figs.append(dict(mask=m, area=int(m.sum()),
                         box=[xs.min(), ys.min(), xs.max(), ys.max()],
                         cx=float(xs.mean()), cy=float(ys.mean())))
    return figs


def order_grid(figs, rows=3):
    """Group into `rows` bands by y, then left-to-right. Rows may differ in length."""
    figs = sorted(figs, key=lambda f: f['cy'])
    n = len(figs)
    if n <= rows:
        bands = [[f] for f in figs]
    else:
        cys = [f['cy'] for f in figs]
        cuts = sorted(sorted(range(1, n), key=lambda i: cys[i] - cys[i - 1],
                             reverse=True)[:rows - 1])
        bands, prev = [], 0
        for c in cuts + [n]:
            bands.append(figs[prev:c])
            prev = c
    out = {}
    for r, band in enumerate(bands):
        for c, f in enumerate(sorted(band, key=lambda f: f['cx'])):
            out[(r, c)] = f
    return out, bands


def drop_strays(rgba, gap=52):
    """Drop blobs far from the main figure (a neighbour's prop caught in the crop)."""
    a = rgba[:, :, 3] > 40
    lbl, n = ndimage.label(a)
    if n <= 1:
        return rgba
    sizes = ndimage.sum(np.ones_like(lbl), lbl, index=range(1, n + 1))
    main = int(np.argmax(sizes)) + 1
    ys, xs = np.where(lbl == main)
    bx0, bx1, by0, by1 = xs.min(), xs.max(), ys.min(), ys.max()
    keep = np.zeros_like(a)
    for i in range(1, n + 1):
        m = lbl == i
        if i == main:
            keep |= m
            continue
        cy, cx = np.where(m)
        dx = max(0, max(cx.min() - bx1, bx0 - cx.max()))
        dy = max(0, max(cy.min() - by1, by0 - cy.max()))
        if max(dx, dy) <= gap:
            keep |= m
    out = rgba.copy()
    out[:, :, 3] = np.where(keep, rgba[:, :, 3], 0)
    return out


def cut_sheet(path, rows=3, green_costume=False, fill_max=1500):
    """Return {(row, col): RGBA crop} for one sheet."""
    rgb = load_rgb(path)
    fg = key_sheet(rgb)
    grid, bands = order_grid(detect_figures(fg), rows)
    full = np.dstack([rgb.astype(np.uint8), np.where(fg, 255, 0).astype(np.uint8)])
    out = {}
    for (r, c), f in grid.items():
        img = full.copy()
        img[:, :, 3] = np.where(f['mask'], full[:, :, 3], 0)
        x0, y0, x1, y1 = f['box']
        crop = img[y0:y1 + 1, x0:x1 + 1].copy()
        crop = fill_holes(crop, fill_max)
        if not green_costume:
            crop = despill_global(crop)
        crop = despill_edges(crop)
        crop = feather(crop)
        out[(r, c)] = crop
    return out, bands


def head_width(rgba):
    """Pose-invariant scale ruler: median run-width across the top of the figure.

    Use this — NOT bbox height — to compare scale between sheets. Bbox height
    varies with stance by 15%+ (a fighting crouch vs a straight stand) and will
    make you "correct" a scale difference that does not exist.
    """
    a = rgba[:, :, 3] > 40
    ys, xs = np.where(a)
    t, b = ys.min(), ys.max()
    band = a[t:t + max(6, int((b - t) * 0.12))]
    ws = [int(np.where(row)[0].max() - np.where(row)[0].min() + 1)
          for row in band if row.any()]
    return int(np.median(ws)) if ws else 0

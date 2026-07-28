"""Turn chosen cells into engine sprites + metadata.

SPRMETA format: [w, h, anchorX, anchorY, k]
  w,h       stored pixel size
  anchorX   the fighter's standing axis WITHIN the crop
  anchorY   the feet (alpha bottom)
  k         this cell's downscale factor, times any cross-sheet scale fix

The engine draws at spriteScale/k with (anchorX, anchorY) landing on the
fighter's world position, so anchorX must track the BODY.

ANCHORING — the bug that cost the most time. Using the alpha centroid makes
specials shudder: a film reel, boom mic or beam entering frame swings the
centroid 100px+ between consecutive frames and the character appears to lurch
sideways. Anchor on the body instead. `anchor_mode` in the config picks how:

  "dark"   median x of dark clothing  (default; works when the costume is
           darker than the effects — black/navy/grey outfits)
  "feet"   median x of the body's bottom band (good for bright costumes with
           grounded poses)
  "centre" bbox centre (only for prop-free sheets)

Whichever you choose, VERIFY with `add_fighter.py verify --preview`: it renders
each special in engine space with the anchor marked. The body must sit on the
mark in every frame.
"""
import base64
import io
import numpy as np
from PIL import Image
from scipy import ndimage

from .chroma import alpha_bbox

CAP = 285          # max stored dimension; keeps the HTML payload sane


def anchor_dark(crop):
    a = crop[:, :, 3] > 40
    v = crop[:, :, :3].max(axis=2)
    dark = a & (v < 110)
    if dark.sum() < 300:
        dark = a & (v < 150)
    if dark.sum() < 300:
        dark = a
    lbl, n = ndimage.label(dark)
    if n > 1:
        sizes = ndimage.sum(np.ones_like(lbl), lbl, index=range(1, n + 1))
        big = lbl == int(np.argmax(sizes)) + 1
        if big.sum() > 300:
            dark = big
    return int(np.median(np.where(dark)[1]))


def anchor_feet(crop):
    a = crop[:, :, 3] > 40
    lbl, n = ndimage.label(a)
    if n > 1:
        sizes = ndimage.sum(np.ones_like(lbl), lbl, index=range(1, n + 1))
        a = lbl == int(np.argmax(sizes)) + 1
    ys, xs = np.where(a)
    top, bot = ys.min(), ys.max()
    sel = ys >= bot - max(6, int((bot - top) * 0.18))
    return int(np.median(xs[sel])) if sel.any() else int(np.median(xs))


def anchor_centre(crop):
    bb = alpha_bbox(crop)
    return (bb[2] - bb[0]) // 2


ANCHORS = {"dark": anchor_dark, "feet": anchor_feet, "centre": anchor_centre}


def face_dir(crop):
    """+1 faces right, -1 faces left, 0 unsure — via skin position in the head band.

    Unreliable on frontal poses. Treat as a hint: confirm visually, and use the
    per-pose `"flip": true` config override for any it gets wrong.
    """
    bb = alpha_bbox(crop)
    if bb is None:
        return 0
    l, t, r, b = bb
    band = crop[t:t + int((b - t) * 0.34), l:r]
    R = band[:, :, 0].astype(int)
    G = band[:, :, 1].astype(int)
    B = band[:, :, 2].astype(int)
    A = band[:, :, 3] > 60
    skin = A & (R > 135) & (R >= G + 8) & (G >= B) & ((R - B) > 28)
    ys, xs = np.where(skin)
    ay, ax = np.where(A)
    if len(xs) < 20 or len(ax) == 0:
        return 0
    off = xs.mean() - ax.mean()
    return 0 if abs(off) < (r - l) * 0.03 else (1 if off > 0 else -1)


def make_sprite(crop, scale_norm=1.0, anchor_mode="dark", flip=False, quality=88,
                cell_scale=1.0):
    """One cell -> (data-uri, meta).

    scale_norm  corrects a whole sheet drawn at a different size.
    cell_scale  corrects ONE cell where the generator shrank the character to
                fit a building/explosion into the square frame — the usual cause
                of a fighter appearing to shrink and grow mid-move. >1 enlarges.
                Found by eye with `add_fighter.py scale <cfg>`; no automatic
                measure was reliable enough to apply unattended (a tucked
                mid-air pose looks "small" by every metric but is correct).
    """
    if flip:
        crop = crop[:, ::-1]
    bb = alpha_bbox(crop)
    crop = crop[bb[1]:bb[3], bb[0]:bb[2]]
    rh, rw = crop.shape[0], crop.shape[1]
    d = min(1.0, CAP / max(rw, rh))
    if d < 1.0:
        crop = np.asarray(Image.fromarray(crop).resize(
            (max(1, round(rw * d)), max(1, round(rh * d))), Image.LANCZOS))
    h, w = crop.shape[0], crop.shape[1]
    ax = ANCHORS[anchor_mode](crop)
    ay = int(np.where(crop[:, :, 3] > 40)[0].max())
    buf = io.BytesIO()
    Image.fromarray(crop).save(buf, "WEBP", quality=quality, method=6)
    uri = "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()
    # the engine draws at spriteScale/k, so dividing k by cell_scale enlarges
    # this one cell without touching any other
    k = d * scale_norm / max(0.05, float(cell_scale))
    return uri, [w, h, ax, ay, round(k, 4)]


def scale_norms(cells_by_sheet, refs=None, tolerance=0.06, sane=(0.75, 1.34)):
    """Work out whether sheets really are drawn at different scales.

    Measures head width, which is pose-invariant — NEVER derive this from bbox
    height, which swings 15%+ with stance and will have you "fixing" a size
    difference that does not exist.

    By default it takes the MEDIAN over every cell on a sheet. Individual cells
    lie: a hovering drone or raised boom mic sits above the head and inflates
    that cell's reading 3-5x. The median shrugs those off, so no hand-picked
    reference cells are needed. `refs` can still pin specific cells if you want.

    Ratios outside `sane` are refused (treated as 1.0 and reported) — a genuine
    cross-sheet difference is mild, so anything wilder means the measurement was
    fooled, and silently applying it would wreck the fighter's size.
    """
    from .sheets import head_width
    widths, suspect = {}, []
    for tag, cells in cells_by_sheet.items():
        if refs and tag in refs:
            vals = [head_width(cells[tuple(rc)]) for rc in refs[tag] if tuple(rc) in cells]
        else:
            vals = [head_width(c) for c in cells.values()]
        vals = [v for v in vals if v > 0]
        if vals:
            widths[tag] = float(np.median(vals))
    if not widths:
        return {t: 1.0 for t in cells_by_sheet}, {}
    base = float(np.median(list(widths.values())))
    out = {}
    for tag in cells_by_sheet:
        w = widths.get(tag)
        if not w or base <= 0:
            out[tag] = 1.0
            continue
        ratio = w / base
        if abs(ratio - 1.0) <= tolerance:
            out[tag] = 1.0
        elif sane[0] <= ratio <= sane[1]:
            out[tag] = round(ratio, 4)
        else:
            out[tag] = 1.0
            suspect.append((tag, round(ratio, 2)))
    if suspect:
        print("  note: ignoring implausible scale ratio(s) %s — measurement was "
              "probably fooled by a prop; using 1.0" % suspect)
    return out, widths

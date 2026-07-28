"""Green-screen keying for AI-generated sprite sheets.

The rules here are the ones that survived contact with the real sheets — see
tools/README.md for why each exists. Do not "simplify" them away:

  * A single global threshold leaves MOTH HOLES in any character wearing green
    (the elf's leaf armour). We remove pure screen-green anywhere, but weaker
    green only where it connects to the border or to a pure-green pocket.
  * Screen green gets trapped in enclosed pockets (between an arm and the
    torso). Those must go, or you get green slivers mid-sprite.
  * Anything still enclosed after keying is a hole in the character and is
    filled from its neighbours.
"""
import numpy as np
from scipy import ndimage
from PIL import Image


def load_rgb(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.int32)


def key_sheet(rgb, gdom=55, gmin=105):
    """Return a boolean foreground mask for a whole sheet."""
    R, G, B = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    # pure screen green: never appears on a character, so it is safe to kill
    # anywhere — this is what clears slivers trapped between limbs.
    pure = (R < 70) & (B < 80) & (G > 150) & ((G - R) > 90) & ((G - B) > 85)
    gd = G - np.maximum(R, B)
    weak = (gd > gdom) & (G > gmin)      # could be screen, could be costume
    seed = pure.copy()
    seed[0, :] = seed[-1, :] = seed[:, 0] = seed[:, -1] = True
    lbl, _ = ndimage.label(weak | pure)
    keep = set(np.unique(lbl[seed & (weak | pure)]))
    keep.discard(0)
    bg = np.isin(lbl, list(keep)) | pure
    return ~bg


def fill_holes(rgba, max_area=1500):
    """Fill enclosed transparent regions (moth holes) from nearest opaque pixel."""
    a = rgba[:, :, 3] > 40
    holes = ndimage.binary_fill_holes(a) & ~a
    if not holes.any():
        return rgba
    hl, hn = ndimage.label(holes)
    tofill = np.zeros_like(holes)
    for i in range(1, hn + 1):
        m = hl == i
        if m.sum() <= max_area:
            tofill |= m
    if not tofill.any():
        return rgba
    idx = ndimage.distance_transform_edt(~a, return_distances=False, return_indices=True)
    out = rgba.copy()
    ys, xs = np.where(tofill)
    for ch in range(3):
        out[ys, xs, ch] = rgba[idx[0][ys, xs], idx[1][ys, xs], ch]
    out[ys, xs, 3] = 255
    return out


def despill_edges(rgba, iters=2):
    """Pull green fringe off the silhouette edge."""
    a = rgba[:, :, 3] > 40
    near = ndimage.binary_dilation(~a, iterations=iters) & a
    R = rgba[:, :, 0].astype(np.int32)
    G = rgba[:, :, 1].astype(np.int32)
    B = rgba[:, :, 2].astype(np.int32)
    cap = (R + B) // 2 + 18
    out = rgba.copy()
    out[:, :, 1] = np.where(near & (G > cap), np.minimum(G, cap), G).astype(np.uint8)
    return out


def despill_global(rgba):
    """Kill green bounce across the whole sprite.

    ONLY for characters wearing no green. Set `"green_costume": true` in the
    fighter config to skip this — it would grey out an elf's armour.
    """
    out = rgba.copy()
    R = out[:, :, 0].astype(np.int32)
    G = out[:, :, 1].astype(np.int32)
    B = out[:, :, 2].astype(np.int32)
    mx = np.maximum(R, B)
    m = (out[:, :, 3] > 40) & (G > mx + 18)
    out[:, :, 1] = np.where(m, mx + 10, G).astype(np.uint8)
    return out


def feather(rgba):
    """One-pixel alpha softening so sprites don't read as cut-outs."""
    a = rgba[:, :, 3].astype(np.float32)
    blur = ndimage.uniform_filter(a, size=3)
    edge = (rgba[:, :, 3] == 255) & ndimage.binary_dilation(rgba[:, :, 3] < 40)
    out = rgba.copy()
    out[:, :, 3] = np.where(edge, 0.5 * a + 0.5 * blur, a).astype(np.uint8)
    return out


def alpha_bbox(rgba, thr=40):
    a = rgba[:, :, 3] > thr
    ys, xs = np.where(a)
    if len(ys) == 0:
        return None
    return (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)

#!/usr/bin/env python3
"""Add a fighter to Noodles, Cake & Elf.

    python3 tools/add_fighter.py probe  tools/fighters/max.json   # look at the art
    python3 tools/add_fighter.py build  tools/fighters/max.json   # cut + embed
    python3 tools/add_fighter.py verify max                       # static checks
    python3 tools/add_fighter.py voices tools/fighters/max.json   # transcribe takes

Run `probe` first and OPEN the montages it writes: you cannot map poses you have
not looked at. Then fill in the config, `build`, `verify`, and play-test.

Read tools/README.md before your first fighter.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ncebuild import chroma, sheets, sprites as spr, media, embed, verify  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, "index.html")


def load_cfg(path):
    cfg = json.load(open(path))
    cfg["_dir"] = os.path.dirname(os.path.abspath(path))
    return cfg


def sheet_paths(cfg):
    out = {}
    for tag, rel in cfg["sheets"].items():
        p = rel if os.path.isabs(rel) else os.path.join(ROOT, rel)
        if not os.path.exists(p):
            raise SystemExit("sheet %s not found: %s" % (tag, p))
        out[tag] = p
    return out


def cut_all(cfg):
    green = cfg.get("green_costume", False)
    rows = cfg.get("sheet_rows", 3)
    cells = {}
    for tag, path in sheet_paths(cfg).items():
        c, bands = sheets.cut_sheet(path, rows=rows, green_costume=green)
        cells[tag] = c
        print("  %-3s %s  rows=%s" % (tag, os.path.basename(path),
                                      [len(b) for b in bands]))
    return cells


# ------------------------------------------------------------------ probe --

def cmd_probe(cfg):
    out = os.path.join(cfg["_dir"], "_probe_" + cfg["id"])
    os.makedirs(out, exist_ok=True)
    print("cutting sheets…")
    cells = cut_all(cfg)
    for tag, cs in cells.items():
        cell, pad = 250, 5
        rows = max(r for r, _ in cs) + 1
        cols = max(c for _, c in cs) + 1
        cv = Image.new("RGBA", (cols * (cell + pad) + pad, rows * (cell + pad) + pad),
                       (38, 38, 44, 255))
        dr = ImageDraw.Draw(cv)
        for (r, c), rgba in cs.items():
            bb = chroma.alpha_bbox(rgba)
            crop = Image.fromarray(rgba[bb[1]:bb[3], bb[0]:bb[2]])
            s = min((cell - 12) / crop.width, (cell - 12) / crop.height, 1.4)
            crop = crop.resize((max(1, int(crop.width * s)), max(1, int(crop.height * s))))
            cb = (((np.arange(cell)[:, None] // 14) + (np.arange(cell)[None, :] // 14)) % 2)
            tile = Image.fromarray(np.dstack([np.where(cb == 0, 112, 82)] * 3 +
                                             [np.full((cell, cell), 255)]).astype(np.uint8))
            tile.alpha_composite(crop, ((cell - crop.width) // 2, (cell - crop.height) // 2))
            px, py = c * (cell + pad) + pad, r * (cell + pad) + pad
            cv.alpha_composite(tile, (px, py))
            dr.text((px + 4, py + 4), "%s r%d c%d" % (tag, r, c), fill=(255, 255, 0, 255))
        p = os.path.join(out, "sheet_%s.png" % tag)
        cv.convert("RGB").save(p)
        print("  wrote", p)
    norms, widths = spr.scale_norms(cells, cfg.get("scale_refs", {t: [[0, 0]] for t in cells}))
    print("\nhead widths per sheet:", {k: round(v) for k, v in widths.items()})
    print("scale norms (1.0 = same scale):", norms)
    print("\nNow open those montages and fill in \"poses\" in the config, e.g.")
    print('   "idle0": ["A", 0, 0],   "walk0": ["A", 1, 0], …')
    return 0


# ----------------------------------------------------------------- voices --

def cmd_voices(cfg):
    folder = cfg.get("voice_dir")
    if not folder:
        raise SystemExit('config has no "voice_dir"')
    folder = folder if os.path.isabs(folder) else os.path.join(ROOT, folder)
    print("transcribing", folder)
    for name, segs in media.transcribe_dir(folder).items():
        print("\n== %s" % name)
        for s in segs:
            print("   [%6.2f-%6.2f] %s" % (s["start"], s["end"], s["text"]))
    print("\nAdd the good takes to \"voice_clips\" as {key: [file, t0, t1, expected_text]}.")
    return 0


# ------------------------------------------------------------------ scale --

def cmd_scale(cfg):
    """Render every pose at engine scale so wrong-sized cells are obvious.

    The generators shrink the character when a building or explosion has to
    share the square frame, which makes a fighter appear to grow and shrink
    mid-move. No automatic measure was trustworthy enough to apply unattended
    (head-width is thrown by raised arms and beards; body-area calls a tucked
    mid-air pose "small" when it is correct), so this makes the error visible
    and the fix a single number.

    Read off the ratio against the guide bars and put it in "cell_scale":
    a frame drawn at two-thirds size needs about 1.5.
    """
    from ncebuild.chroma import alpha_bbox
    cells = cut_all(cfg)
    norms, _ = spr.scale_norms(cells, cfg.get("scale_refs"))
    cscale = cfg.get("cell_scale") or {}
    anchor_mode = cfg.get("anchor_mode", "dark")

    rendered = []
    for pose, ref in cfg["poses"].items():
        tag, r, c = ref[0], int(ref[1]), int(ref[2])
        flip = bool(ref[3]) if len(ref) > 3 else False
        crop = sheets.drop_strays(cells[tag][(r, c)])
        _, m = spr.make_sprite(crop, norms.get(tag, 1.0), anchor_mode, flip,
                               cell_scale=float(cscale.get(pose, 1.0)))
        bb = alpha_bbox(crop if not flip else crop[:, ::-1])
        img = Image.fromarray((crop if not flip else crop[:, ::-1])[bb[1]:bb[3], bb[0]:bb[2]])
        rendered.append((pose, img, m))

    # engine maths: everything is drawn at spriteScale/k
    idle = dict((p, m) for p, _, m in rendered).get("idle0") or rendered[0][2]
    ss = 252.0 / (idle[1] / (idle[4] or 1))

    CW, per_row = 260, 8
    rows = (len(rendered) + per_row - 1) // per_row
    tiles = []
    for pose, img, m in rendered:
        s = ss / (m[4] or 1)
        tiles.append((pose, img.resize((max(1, int(m[0] * s)), max(1, int(m[1] * s))),
                                       Image.LANCZOS), m[2] * s, m[3] * s))
    above = int(max(t[3] for t in tiles)) + 26
    RH = above + 60
    cv = Image.new("RGBA", (CW * per_row, RH * rows), (44, 46, 52, 255))
    dr = ImageDraw.Draw(cv)
    for i, (pose, im, ax, ay) in enumerate(tiles):
        rw, cl = divmod(i, per_row)
        ox, oy = cl * CW, rw * RH
        gy = oy + above
        dr.line([(ox, gy), (ox + CW, gy)], fill=(90, 170, 90, 255))
        # guide bars at the reference standing height (252px) and +/-12%
        for frac, col in ((1.0, (250, 220, 90, 170)), (0.88, (250, 120, 120, 110)),
                          (1.12, (250, 120, 120, 110))):
            yy = gy - 252 * frac
            dr.line([(ox + 6, yy), (ox + CW - 6, yy)], fill=col)
        cv.alpha_composite(im, (int(ox + CW / 2 - ax), int(gy - ay)))
        dr.text((ox + 5, oy + 4), pose, fill=(255, 255, 0, 255))
    out = os.path.join(cfg["_dir"], "_probe_" + cfg["id"], "scale_check.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    cv.convert("RGB").save(out)
    print("wrote", out)
    print("\nYellow line = a standing fighter's height. Any pose whose body is well")
    print("short of it (and is not crouching/airborne on purpose) needs a")
    print('"cell_scale" entry, e.g.  "cell_scale": {"superf1": 1.5}')
    return 0


# ------------------------------------------------------------------ build --

def cmd_build(cfg):
    fid = cfg["id"]
    print("cutting sheets…")
    cells = cut_all(cfg)

    refs = cfg.get("scale_refs") or {t: [[0, 0]] for t in cells}
    norms, widths = spr.scale_norms(cells, refs)
    print("head widths:", {k: round(v) for k, v in widths.items()}, "-> norms:", norms)

    anchor_mode = cfg.get("anchor_mode", "dark")
    poses, meta, sprite_uris, seen = {}, {}, {}, {}
    for pose, ref in cfg["poses"].items():
        tag, r, c = ref[0], int(ref[1]), int(ref[2])
        flip = bool(ref[3]) if len(ref) > 3 else False
        if (tag, r, c) not in cells:
            pass
        if tag not in cells or (r, c) not in cells[tag]:
            raise SystemExit("pose %s -> %s r%d c%d does not exist on that sheet"
                             % (pose, tag, r, c))
        cscale = float((cfg.get("cell_scale") or {}).get(pose, 1.0))
        sig = (tag, r, c, flip, cscale)
        if sig in seen:
            poses[pose] = seen[sig]
            continue
        key = "%s_%s" % (fid, pose)
        crop = sheets.drop_strays(cells[tag][(r, c)])
        uri, m = spr.make_sprite(crop, norms.get(tag, 1.0), anchor_mode, flip,
                                 cell_scale=cscale)
        sprite_uris[key] = uri
        meta[key] = m
        poses[pose] = key
        seen[sig] = key
    poses.setdefault("idle", poses.get("idle0"))
    poses.setdefault("jump", poses.get("jumpUp"))
    print("  %d sprites, %d poses" % (len(sprite_uris), len(poses)))

    # voice clips
    clips, clipdir = {}, os.path.join(cfg["_dir"], "_clips_" + fid)
    if cfg.get("voice_clips"):
        os.makedirs(clipdir, exist_ok=True)
        vd = cfg["voice_dir"]
        vd = vd if os.path.isabs(vd) else os.path.join(ROOT, vd)
        ref_rms = media._ref_loudness(HTML)
        for key, spec in cfg["voice_clips"].items():
            src = os.path.join(vd, spec[0])
            outp = os.path.join(clipdir, "%s.mp3" % key)
            n = media.cut_clip(src, float(spec[1]), float(spec[2]), ref_rms, outp)
            clips["%s_%s" % (fid, key)] = media.mp3_data_uri(outp)
            print("  voice %s_%s (%d bytes)" % (fid, key, n))

    # art
    art = {}
    for kind, conv in (("card", media.convert_card), ("stage", media.convert_stage)):
        rel = cfg.get(kind)
        if rel:
            p = rel if os.path.isabs(rel) else os.path.join(ROOT, rel)
            art[kind] = conv(p)[0]
            print("  %s art ok" % kind)
    fin_anch = None
    if cfg.get("finish"):
        p = cfg["finish"]
        p = p if os.path.isabs(p) else os.path.join(ROOT, p)
        art["finish"], fin_anch, _ = media.convert_finish(p)
        print("  finish sheet ok")

    # ---- inject ----
    src = open(HTML, encoding="utf-8").read()
    n0 = len(src)
    src = embed.merge_sprites(src, sprite_uris)
    m = __import__("re").search(r'const SPRMETA=(\{.*?\});', src)
    md = json.loads(m.group(1)); md.update(meta)
    src = src[:m.start()] + "const SPRMETA=" + json.dumps(md) + ";" + src[m.end():]
    src = embed.set_json_key(src, "POSEMAP", fid, poses, r'const POSEMAP=(\{.*?\});\n')
    src = embed.set_json_key(src, "POSEANIMN", fid, cfg["anim"])
    src = embed.set_object_entry(src, "SP_PHASE", fid, "spphase",
                                 "  %s:%s," % (fid, json.dumps(cfg["sp_phase"])))
    src = embed.add_to_charlist(src, fid)

    if "card" in art:
        src = embed.set_js_key(src, "CARD_SRC", fid, art["card"])
    if "stage" in art:
        src = embed.set_js_key(src, "SCENE_SRC", fid, art["stage"])
    if "finish" in art:
        src = embed.set_js_key(src, "FINISH_SRC", fid, art["finish"])
        src = embed.set_json_key(src, "FIN_ANCH", fid, fin_anch, r'FIN_ANCH=(\{.*?\});', "FIN_ANCH=")
    if clips:
        src = embed.merge_vclip(src, clips)
    if cfg.get("clipfor"):
        src = embed.set_object_entry(src, "CLIPFOR", fid, "clipfor",
                                     "  %s:%s," % (fid, json.dumps(cfg["clipfor"])))

    chars_body = "  " + cfg["chars"].strip()
    if chars_body.startswith("  %s:" % fid):
        chars_body = chars_body[len("  %s:" % fid):].rstrip().rstrip(",")
    src = embed.set_object_entry(src, "CHARS", fid, "chars", "  %s:%s," % (fid, chars_body))
    src = embed.put_block(src, fid, "moves",
                          "  if(id==='%s')return{\n%s\n  };" % (fid, cfg["moves"].rstrip()),
                          "  return{\n    light:{name:'Palm Strike'")
    if cfg.get("callouts"):
        src = embed.set_object_entry(src, "CALLOUTS", fid, "callouts",
                                     "  %s:%s," % (fid, cfg["callouts"]))
    if cfg.get("theme"):
        src = embed.set_object_entry(src, "THEMES", fid, "theme",
                                     "  %s:%s," % (fid, cfg["theme"]))
    if cfg.get("extra_js"):
        src = embed.put_block(src, fid, "extra", cfg["extra_js"], "// ---------- HUD ----------")

    open(HTML, "w", encoding="utf-8").write(src)
    print("embedded into index.html: %d -> %d bytes (%+dKB)"
          % (n0, len(src), (len(src) - n0) // 1024))
    return cmd_verify(fid)


# ----------------------------------------------------------------- verify --

def cmd_verify(fid):
    errs, warns, notes = verify.check(HTML, fid)
    for n in notes:
        print("  note:", n)
    for w in warns:
        print("  WARN:", w)
    for e in errs:
        print("  FAIL:", e)
    print(("verify: %d error(s), %d warning(s)" % (len(errs), len(warns)))
          if (errs or warns) else "verify: all checks passed")
    return 1 if errs else 0


def main():
    ap = argparse.ArgumentParser(description="Add a fighter to Noodles, Cake & Elf")
    ap.add_argument("cmd", choices=["probe", "build", "verify", "voices", "scale"])
    ap.add_argument("target", help="config path (probe/build/voices) or fighter id (verify)")
    a = ap.parse_args()
    if a.cmd == "verify":
        return cmd_verify(a.target)
    cfg = load_cfg(a.target)
    if a.cmd == "probe":
        return cmd_probe(cfg)
    if a.cmd == "voices":
        return cmd_voices(cfg)
    if a.cmd == "scale":
        return cmd_scale(cfg)
    return cmd_build(cfg)


if __name__ == "__main__":
    sys.exit(main())

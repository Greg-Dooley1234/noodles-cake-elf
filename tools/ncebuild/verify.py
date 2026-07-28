"""Static checks against index.html.

Every check here exists because the bug it catches actually shipped once. Run
`add_fighter.py verify <id>` after every build; it is far cheaper than finding
these by playing.
"""
import json
import re

REQUIRED_POSES = ["idle", "walk0", "crouch", "block", "atkL", "atkH", "clow",
                  "atkA", "jumpUp", "jumpDn", "hit", "launch", "down", "ko",
                  "win", "spWind", "spActive", "super"]

# Every fighter carries four specials plus a super; a missing sp4 leaves the
# character without the anti-air everyone else has.
REQUIRED_MOVES = ["light", "heavy", "clight", "air", "sp1", "sp2", "sp3", "sp4", "super"]

THEME_KEYS = ["bpm", "drums", "pad", "lead", "roots", "chords", "melA", "melB"]
DRUMS = {"four", "boombap", "soft", "bounce"}
PADS = {"warm", "airy", "saw", "square", "sawtooth"}
LEADS = {"pluck", "harp", "saw", "square"}


def _json_obj(src, name, pattern=None, decl=None):
    """Brace-match the object rather than regex it — these literals are huge,
    single-line and full of braces inside base64."""
    head = decl or ("const %s=" % name)
    if head not in src:
        return None
    i = src.index(head)
    j = src.index("{", i)
    depth, instr, esc = 0, False, False
    for k in range(j, len(src)):
        ch = src[k]
        if instr:
            if esc: esc = False
            elif ch == "\\": esc = True
            elif ch == '"': instr = False
            continue
        if ch == '"': instr = True
        elif ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(src[j:k + 1])
                except Exception:
                    return None
    return None


def check(html_path, fid):
    src = open(html_path, encoding="utf-8").read()
    errs, warns, notes = [], [], []

    sprites = set(re.findall(r'"([A-Za-z0-9_]+)":"data:image/webp', src))
    # a fighter may instead load sprites from files (SPRITES.<key>='assets/…')
    sprites |= set(re.findall(r"SPRITES\.([A-Za-z0-9_]+)\s*=", src))
    sprites |= set(re.findall(r"['\"]([A-Za-z0-9_]+)['\"]\s*:\s*['\"]assets/[^'\"]+\.webp", src))
    external = bool(re.search(r"SPRITES\[[^\]]+\]\s*=\s*['\"]?assets/", src)) or \
               ("generated-sprites" in src)
    meta = _json_obj(src, "SPRMETA") or {}
    posemap = _json_obj(src, "POSEMAP", r'const POSEMAP=(\{.*?\});\n') or {}
    animn = _json_obj(src, "POSEANIMN") or {}

    pm = posemap.get(fid)
    if pm is None:
        # some fighters are attached after the literal: POSEMAP.<id>={...}
        m = re.search(r"POSEMAP\.%s\s*=\s*\{" % re.escape(fid), src)
        if m:
            i = src.index("{", m.start())
            depth = 0
            for j in range(i, len(src)):
                if src[j] == "{":
                    depth += 1
                elif src[j] == "}":
                    depth -= 1
                    if depth == 0:
                        pm = dict(re.findall(r"['\"]?([A-Za-z0-9_]+)['\"]?\s*:\s*'([^']+)'",
                                             src[i:j + 1]))
                        break
    if not pm:
        errs.append("POSEMAP has no entry for '%s'" % fid)
        return errs, warns, notes

    # 1. every referenced sprite exists in both tables. Fighters whose art is
    #    loaded from files rather than embedded are reported as notes: this
    #    checker can only see what is inside index.html.
    miss_spr = [(p_, k) for p_, k in pm.items() if k not in sprites]
    if miss_spr and external and len(miss_spr) == len(pm):
        notes.append("'%s' loads its %d sprites from files — check those exist on disk"
                     % (fid, len(pm)))
    else:
        for p_, k in miss_spr:
            errs.append("pose %s -> %s missing from SPRITES" % (p_, k))
    for p_, k in pm.items():
        if k not in meta:
            (notes if (external and len(miss_spr) == len(pm)) else errs).append(
                "pose %s -> %s missing from SPRMETA" % (p_, k))

    # 2. the poses the engine assumes are present
    for p in REQUIRED_POSES:
        if p in pm:
            continue
        # a fighter may animate the super as superf0..N instead of one 'super'
        if p == "super" and "superf0" in pm:
            continue
        if p == "block" and "blockLow" in pm:
            warns.append("no 'block' pose (only blockLow)")
            continue
        errs.append("missing required pose '%s'" % p)

    # 3. animation frame counts line up with the frames that exist
    an = animn.get(fid, {})
    for i in range(an.get("walk", 0)):
        if "walk%d" % i not in pm:
            errs.append("POSEANIMN walk=%d but walk%d is missing" % (an["walk"], i))
    for i in range(an.get("idle", 0)):
        if "idle%d" % i not in pm:
            errs.append("POSEANIMN idle=%d but idle%d is missing" % (an["idle"], i))
    for slot, n in (an.get("sp") or {}).items():
        for i in range(n):
            if "%sf%d" % (slot, i) not in pm:
                errs.append("POSEANIMN %s=%d but %sf%d is missing" % (slot, n, slot, i))

    # 4. SP_PHASE splits must sum to the frame count, or playback skips frames.
    #    Scope to THIS fighter's braces — SP_PHASE holds every fighter, and a
    #    loose scan happily reports the neighbours' numbers as your errors.
    mp = re.search(r"\b%s:\{" % re.escape(fid), src)
    sp_block = None
    if mp:
        i = src.index("{", mp.start())
        depth = 0
        for j in range(i, min(len(src), i + 2000)):
            if src[j] == "{":
                depth += 1
            elif src[j] == "}":
                depth -= 1
                if depth == 0:
                    sp_block = src[i:j + 1]
                    break
    if sp_block and "sp1:[" in sp_block:
        for slot, w, a, r in re.findall(r"(\w+):\[(\d+),(\d+),(\d+)\]", sp_block):
            n = (an.get("sp") or {}).get(slot)
            if n and int(w) + int(a) + int(r) != n:
                errs.append("SP_PHASE %s.%s sums to %d but POSEANIMN says %d frames"
                            % (fid, slot, int(w) + int(a) + int(r), n))

    # 5. moves
    mm = re.search(r"if\(id==='%s'\)return\{(.*?)\n  \};" % fid, src, re.S)
    if not mm:
        # not fatal: one fighter legitimately uses mkMoves' shared fallback set
        warns.append("mkMoves has no branch for '%s' (using the shared default move set)" % fid)
    else:
        body = mm.group(1)
        for mv in REQUIRED_MOVES:
            if not re.search(r"\b%s:\{" % mv, body):
                errs.append("move '%s' not defined" % mv)

    # 6. roster + art
    if not re.search(r"const CHARLIST=\[[^\]]*'%s'" % fid, src):
        errs.append("'%s' is not in CHARLIST" % fid)
    if not re.search(r"\bid:'%s'" % fid, src):
        errs.append("CHARS has no entry for '%s'" % fid)
    for tbl in ("CARD_SRC", "SCENE_SRC", "FINISH_SRC"):
        if not re.search(r"const %s=\{[^}]*?\b%s:" % (tbl, fid), src, re.S):
            warns.append("%s has no art for '%s'" % (tbl, fid))

    # 7. theme must match the music engine's schema or it plays silently
    mt = re.search(r'const THEMES=\{(.*?)\n\};', src, re.S)
    if mt:
        tb = mt.group(1)
        i = tb.find("\n  %s:{" % fid)
        if i < 0:
            warns.append("THEMES has no '%s' entry — the stage will reuse another cue" % fid)
        else:
            entry = tb[i:i + 900]
            for k in THEME_KEYS:
                if (k + ":") not in entry:
                    errs.append("THEMES.%s is missing '%s' (silent theme)" % (fid, k))
            for label, allowed in (("drums", DRUMS), ("pad", PADS), ("lead", LEADS)):
                mv = re.search(r"%s:'(\w+)'" % label, entry)
                if mv and mv.group(1) not in allowed:
                    errs.append("THEMES.%s %s='%s' is not one of %s"
                                % (fid, label, mv.group(1), sorted(allowed)))

    # 8. scene overlays must not run on the hitstop-scaled clock (freezes forever)
    for m in re.finditer(r"function update%s\w*\(dt\)\{(.{0,200})" % fid.capitalize(), src, re.S):
        if "S.t+=dt" in m.group(1):
            notes.append("scene timer for '%s' found — make sure it is ticked with the "
                         "REAL dt, not sdt (sdt is 0 during super-freeze)" % fid)

    # 9. anchor sanity: a pose whose anchor sits outside its own width is broken
    for pose, key in pm.items():
        mt2 = meta.get(key)
        if mt2 and not (0 <= mt2[2] <= mt2[0]):
            errs.append("%s anchorX %d outside width %d" % (key, mt2[2], mt2[0]))

    notes.append("%d sprites, %d poses" % (len([k for k in sprites if k.startswith(fid)]), len(pm)))
    return errs, warns, notes

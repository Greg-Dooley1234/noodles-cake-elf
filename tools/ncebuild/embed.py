"""Inject a fighter into index.html — idempotently.

Re-running `build` for the same fighter must never double-insert. Two tactics:

  * Data tables (SPRITES, SPRMETA, POSEMAP, POSEANIMN, CARD_SRC, SCENE_SRC,
    FINISH_SRC, FIN_ANCH, VCLIP, CLIPFOR) are parsed, keyed by fighter id and
    re-serialised, so writing the same key twice is a no-op.
  * Code blocks (moves, callouts, theme, stage FX) are wrapped in
    /*<<NCE:id:slot>>*/ ... /*<</NCE:id:slot>>*/ markers and replaced wholesale.

Always keep index.html in git so a bad run is one `git checkout` away.
"""
import json
import re

MARK_OPEN = "/*<<NCE:%s:%s>>*/"
MARK_CLOSE = "/*<</NCE:%s:%s>>*/"


def _block(fid, slot, body):
    return "%s\n%s\n%s" % (MARK_OPEN % (fid, slot), body, MARK_CLOSE % (fid, slot))


def put_block(src, fid, slot, body, anchor):
    """Insert or replace a marked code block. `anchor` is literal text to sit before."""
    o, c = MARK_OPEN % (fid, slot), MARK_CLOSE % (fid, slot)
    if o in src and c in src:
        i, j = src.index(o), src.index(c) + len(c)
        return src[:i] + _block(fid, slot, body) + src[j:]
    if anchor not in src:
        raise KeyError("anchor not found for %s/%s: %r" % (fid, slot, anchor[:60]))
    return src.replace(anchor, _block(fid, slot, body) + "\n" + anchor, 1)


def _find_obj(src, decl):
    """Locate `decl` (e.g. "const POSEMAP=") and brace-match its object.

    Regex cannot reliably delimit these objects: they are megabytes long, live
    on one line and contain braces inside base64 and nested arrays. Returns
    (start_of_decl, start_of_brace, end_after_brace).
    """
    i = src.index(decl)
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
                return i, j, k + 1
    raise KeyError("unbalanced braces after %r" % decl)


def set_json_key(src, name, key, value, pattern=None, decl=None):
    """Merge one key into a JSON-shaped table and re-serialise."""
    head = decl or ("const %s=" % name)
    i, j, end = _find_obj(src, head)
    obj = json.loads(src[j:end])
    obj[key] = value
    tail = src[end:]
    if tail.startswith(";"):
        tail = tail[1:]
    return src[:i] + head + json.dumps(obj) + ";" + tail


def set_js_key(src, name, key, value):
    """Set one entry in a JS object literal with UNQUOTED keys.

    CARD_SRC / SCENE_SRC / FINISH_SRC are written `max:"data:…"`, which is not
    JSON, so they cannot go through set_json_key.
    """
    decl = "const %s={" % name
    if decl not in src:
        raise KeyError("could not find object %s" % name)
    pat = re.compile(r'(\n\s*%s\s*:\s*)"[^"]*"' % re.escape(key))
    start = src.index(decl)
    end = src.index("};", start)
    seg = src[start:end]
    if pat.search(seg):
        seg2 = pat.sub(lambda m: m.group(1) + '"%s"' % value, seg, count=1)
        return src[:start] + seg2 + src[end:]
    return src.replace(decl, decl + '\n  %s:"%s",' % (key, value), 1)


def set_object_entry(src, name, fid, slot, body):
    """Put `fid: <body>` INSIDE the object literal `const name={ … }`.

    Two traps this avoids:
      * anchoring on text that follows the object drops the entry at statement
        level, which is a syntax error (`Unexpected token ':'`);
      * a hand-written entry for the same fighter later in the object would
        override ours, so any existing top-level entry is removed first.
    """
    decl = "const %s={" % name
    if decl not in src:
        raise KeyError("could not find object %s" % name)
    start = src.index(decl)
    open_brace = src.index("{", start)
    # brace-match the whole object so we only edit within it
    depth, end = 0, None
    for k in range(open_brace, len(src)):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                end = k
                break
    seg = src[open_brace + 1:end]

    o, c = MARK_OPEN % (fid, slot), MARK_CLOSE % (fid, slot)
    if o in seg and c in seg:                      # replace our own block
        i, j = seg.index(o), seg.index(c) + len(c)
        seg = seg[:i] + _block(fid, slot, body) + seg[j:]
    else:
        # drop a pre-existing unmarked entry for this fighter, then prepend ours
        m = re.search(r"\n\s*%s\s*:\s*[\{\[]" % re.escape(fid), seg)
        if m:
            k = seg.index("{" if seg[m.end() - 1] == "{" else "[", m.start())
            d, stop = 0, None
            openc, closec = seg[k], ("}" if seg[k] == "{" else "]")
            for x in range(k, len(seg)):
                if seg[x] == openc:
                    d += 1
                elif seg[x] == closec:
                    d -= 1
                    if d == 0:
                        stop = x + 1
                        break
            if stop:
                while stop < len(seg) and seg[stop] in ", ":
                    stop += 1
                seg = seg[:m.start()] + seg[stop:]
        seg = "\n" + _block(fid, slot, body) + seg
    return src[:open_brace + 1] + seg + src[end:]


def merge_sprites(src, sprites):
    """SPRITES is a big literal; add missing keys, replace existing ones."""
    for k, uri in sorted(sprites.items()):
        line = '"%s":"%s",\n' % (k, uri)
        existing = re.search(r'"%s":"data:image/webp;base64,[A-Za-z0-9+/=]*",\n' % re.escape(k), src)
        if existing:
            src = src[:existing.start()] + line + src[existing.end():]
        else:
            src = src.replace("const SPRITES={\n", "const SPRITES={\n" + line, 1)
    return src


def merge_vclip(src, clips):
    for k, uri in sorted(clips.items()):
        line = '  %s:"%s",\n' % (k, uri)
        existing = re.search(r'\n\s*%s:"data:audio/mpeg;base64,[A-Za-z0-9+/=]*",\n' % re.escape(k), src)
        if existing:
            src = src[:existing.start()] + "\n" + line + src[existing.end():]
        else:
            src = src.replace("const VCLIP={\n", "const VCLIP={\n" + line, 1)
    return src


def add_to_charlist(src, fid):
    m = re.search(r"const CHARLIST=\[([^\]]*)\];", src)
    if not m:
        raise KeyError("CHARLIST not found")
    ids = [s.strip().strip("'\"") for s in m.group(1).split(",") if s.strip()]
    if fid in ids:
        return src
    ids.append(fid)
    return (src[:m.start()] + "const CHARLIST=[" +
            ",".join("'%s'" % i for i in ids) + "];" + src[m.end():])


def set_clipfor(src, fid, mapping):
    """CLIPFOR holds JS values (arrays/strings) — emit as a marked line."""
    body = "  %s:%s," % (fid, json.dumps(mapping))
    o, c = MARK_OPEN % (fid, "clipfor"), MARK_CLOSE % (fid, "clipfor")
    if o in src:
        i, j = src.index(o), src.index(c) + len(c)
        return src[:i] + _block(fid, "clipfor", body) + src[j:]
    return src.replace("const CLIPFOR={\n", "const CLIPFOR={\n" +
                       _block(fid, "clipfor", body) + "\n", 1)


def set_sp_phase(src, fid, phases):
    body = "  %s:%s," % (fid, json.dumps(phases))
    o = MARK_OPEN % (fid, "spphase")
    c = MARK_CLOSE % (fid, "spphase")
    if o in src:
        i, j = src.index(o), src.index(c) + len(c)
        return src[:i] + _block(fid, "spphase", body) + src[j:]
    return src.replace("const SP_PHASE={", "const SP_PHASE={\n" +
                       _block(fid, "spphase", body) + "\n", 1)

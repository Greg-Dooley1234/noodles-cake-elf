"""Voice clips, card art, stage backdrop and the finish-move sheet."""
import base64
import glob
import io
import os
import re

import numpy as np
from PIL import Image

from .chroma import (load_rgb, key_sheet, fill_holes, despill_edges, feather)

# ---------------------------------------------------------------- voice ----

def _ref_loudness(html_path, ref_key="bal_1"):
    """Match new clips to a clip already shipping in the game."""
    try:
        import av
        src = open(html_path, encoding="utf-8").read()
        m = re.search(r'[^A-Za-z_"]%s:"data:audio/mpeg;base64,([A-Za-z0-9+/=]+)"' % ref_key, src)
        if not m:
            return 0.12
        c = av.open(io.BytesIO(base64.b64decode(m.group(1))))
        fr = [f.to_ndarray().astype(np.float32) for f in c.decode(audio=0)]
        a = np.concatenate(fr, axis=1).mean(axis=0)
        if np.abs(a).max() > 1.5:
            a /= 32768.0
        return float(np.sqrt((a[np.abs(a) > 0.02] ** 2).mean()))
    except Exception:
        return 0.12


def transcribe_dir(folder, model_size="base.en"):
    """List every take with word timings so you can pick clean in/out points."""
    from faster_whisper import WhisperModel
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    out = {}
    for f in sorted(glob.glob(os.path.join(folder, "*.ogg")) +
                    glob.glob(os.path.join(folder, "*.m4a")) +
                    glob.glob(os.path.join(folder, "*.mp3"))):
        segs, _ = model.transcribe(f, word_timestamps=True, vad_filter=True)
        items = []
        for s in segs:
            items.append({"text": s.text.strip(), "start": round(s.start, 2),
                          "end": round(s.end, 2)})
        out[os.path.basename(f)] = items
    return out


def cut_clip(src_path, t0, t1, ref_rms, out_path, bitrate=64):
    import soundfile as sf
    import lameenc
    d, sr = sf.read(src_path)
    if d.ndim > 1:
        d = d.mean(axis=1)
    seg = d[int(t0 * sr):int(t1 * sr)].astype(np.float32)
    if len(seg) < 32:
        raise ValueError("clip window is empty: %s %.2f-%.2f" % (src_path, t0, t1))
    f = int(0.008 * sr)
    seg[:f] *= np.linspace(0, 1, f)
    seg[-f:] *= np.linspace(1, 0, f)
    act = seg[np.abs(seg) > 0.02]
    if len(act):
        seg = seg * min(ref_rms / np.sqrt((act ** 2).mean()),
                        0.95 / max(1e-6, np.abs(seg).max()))
    pcm = (np.clip(seg, -1, 1) * 32767).astype(np.int16)
    enc = lameenc.Encoder()
    enc.set_bit_rate(bitrate); enc.set_in_sample_rate(sr)
    enc.set_channels(1); enc.set_quality(2)
    mp3 = enc.encode(pcm.tobytes()) + enc.flush()
    open(out_path, "wb").write(mp3)
    return len(mp3)


def verify_clip(path, model_size="base.en"):
    """Re-transcribe the encoded mp3 — catches a window that caught the wrong words."""
    from faster_whisper import WhisperModel
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segs, _ = model.transcribe(path, vad_filter=False)
    return " ".join(s.text.strip() for s in segs)


def mp3_data_uri(path):
    return "data:audio/mpeg;base64," + base64.b64encode(open(path, "rb").read()).decode()


# ------------------------------------------------------------------ art ----

def convert_card(path, max_size=(520, 780), quality=82):
    im = Image.open(path).convert("RGB")
    im.thumbnail(max_size, Image.LANCZOS)
    b = io.BytesIO(); im.save(b, "WEBP", quality=quality, method=6)
    return "data:image/webp;base64," + base64.b64encode(b.getvalue()).decode(), im.size


def convert_stage(path, size=(1440, 810), quality=80):
    im = Image.open(path).convert("RGB").resize(size, Image.LANCZOS)
    b = io.BytesIO(); im.save(b, "WEBP", quality=quality, method=6)
    return "data:image/webp;base64," + base64.b64encode(b.getvalue()).decode(), im.size


def convert_finish(path, cols=6, rows=3, half=True, quality=86):
    """Key the finish sheet but KEEP its grid — the engine slices it into 18 frames."""
    rgb = load_rgb(path)
    fg = key_sheet(rgb)
    rgba = np.dstack([rgb.astype(np.uint8), np.where(fg, 255, 0).astype(np.uint8)])
    rgba = fill_holes(rgba, 3000)
    rgba = despill_edges(rgba)
    rgba = feather(rgba)
    im = Image.fromarray(rgba)
    if half:
        im = im.resize((im.width // 2, im.height // 2), Image.LANCZOS)
    b = io.BytesIO(); im.save(b, "WEBP", quality=quality, method=6)
    uri = "data:image/webp;base64," + base64.b64encode(b.getvalue()).decode()
    arr = np.asarray(im)
    cw, ch = im.width // cols, im.height // rows
    anch = []
    for r in range(rows):
        for c in range(cols):
            cell = arr[r * ch:(r + 1) * ch, c * cw:(c + 1) * cw]
            a = cell[:, :, 3] > 40
            ys, xs = np.where(a)
            if len(ys) == 0:
                anch.append([0.5, 0.95])
            else:
                anch.append([round(float(xs.mean()) / cw, 4),
                             round(float(ys.max()) / ch, 4)])
    return uri, anch, im.size

"""Local server for the interactive 3D viewer (cad-preview mod).

Static files:  /  /app.js  /geom.js  /analysis.js
API:
  GET  /api/ping
  GET  /api/latest                  current model (+ STEP, script, parameters if available)
  GET  /api/file?path=              raw bytes of .stl/.step/.stp
  GET  /api/params                  parameters from the script header
  GET  /api/motion                  joints and animations from <model>.motion.json
  GET  /api/explode                 disassembly steps from <model>.explode.json
  POST /api/params {values}         writes values, runs the script, returns its output
  GET  /api/history                 versions of the current model
  GET  /api/history/file?id=&kind=  stl|step of a version
  POST /api/history/restore {id}    restores a version (model + script)
  GET  /api/annotations             notes for the current model with their status
  POST /api/annotations/status      {id, status: open|done|hidden, note?}
  POST /api/annotate                stores a note (JSON + PNG) in <data>/inbox
  POST /api/annotate-batch          {model, name, step, markers:[{label, type, points, faceNormal, part, note}], camera, parts}
                                    all viewer markers as one inbox note (kind batch)
  POST /api/screenshot {image}      saves a PNG screenshot to <data>/shots
  POST /api/data {data}             switches the data folder
  POST /api/open {path}             shows an existing .stl/.step in the viewer
  GET  /api/variants                design variants <base>@<label>.step next to the model
  POST /api/variants/choose {path}  marks the chosen variant, adds a message for Claude
  GET  /api/export/formats          formats the Export menu offers
  POST /api/export {format, quality} converts the model, asks where to save (native dialog)
  GET  /canvas                      AI construction canvas (canvas.html, canvas.js, geo.js); API /api/canvas* is in canvas.py
  GET  /sketch                      infinite-canvas sketch pad (sketch.html, sketch.js, ink.js)
  GET  /api/sketch?since=&wait=     items and snaps changed since rev since (wait: long-poll up to 25 s)
  POST /api/sketch/ops {put, del, snaps, by}  one atomic batch of item changes, returns the new rev
  POST /api/sketch/image {image}    stores a pasted image in <data>/sketch-images, returns its src
  GET  /api/sketch/image?f=         serves it
  POST /api/sketch/snap {rect, text, ids, image, scale, outside, direct?}  region redraw request for Claude (inbox)
  POST /api/sketch/proposal {snap, items, space?, note?}  Claude's redraw of that region, shown in the pad for Accept / Reject
  POST /api/sketch/send {image, text}  the whole canvas as a brief for Claude via <data>/inbox

Run:  python server.py --port 8766 --data <folder> [--detach]
Listens on 127.0.0.1 only (set CAD_PREVIEW_LAN=1 or create ~/.cad-preview-lan to listen on the network; other machines then
need the token in <data>/lan-token, GET /api/lan gives the full addresses for a tablet).
"""
import argparse
import ast
import base64
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import tokenize
import urllib.request
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import canvas as CV

HERE = os.path.dirname(os.path.abspath(__file__))
IDLE_LIMIT = 8 * 3600
STATIC = {"/": "viewer.html", "/index.html": "viewer.html", "/app.js": "app.js", "/geom.js": "geom.js", "/analysis.js": "analysis.js",
          "/sketch": "sketch.html", "/sketch.js": "sketch.js", "/ink.js": "ink.js",
          "/canvas": "canvas.html", "/canvas.js": "canvas.js", "/geo.js": "geo.js", "/lib.js": "lib.js"}
MODEL_EXT = (".stl", ".step", ".stp")
STATE = {"data": None, "last": time.time(), "pending_label": None}
LOCK = threading.RLock()
RUN_LOCK = threading.Lock()
EXPORT_LOCK = threading.Lock()


# ------------------------------------------------------------------ helpers

def data_dir():
    return STATE["data"] or ""


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return default


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def stamp():
    return time.strftime("%Y%m%d-%H%M%S") + "-%03d" % (int(time.time() * 1000) % 1000)


def sibling_step(stl):
    base = os.path.splitext(stl)[0]
    for ext in (".step", ".stp", ".STEP", ".STP"):
        if os.path.isfile(base + ext):
            return base + ext
    return None


def find_script(stl):
    """Script that exports the model: a .py in the same folder that mentions the file name."""
    folder = os.path.dirname(stl)
    stem = os.path.splitext(os.path.basename(stl))[0]
    best = None
    try:
        names = os.listdir(folder)
    except OSError:
        return None
    for n in names:
        if not n.endswith(".py"):
            continue
        p = os.path.join(folder, n)
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                src = f.read()
        except OSError:
            continue
        if stem + ".stl" in src or stem + ".step" in src or f'"{stem}' in src or f"'{stem}" in src:
            m = os.path.getmtime(p)
            if best is None or m > best[0]:
                best = (m, p)
    return best[1] if best else None


def open_model(path):
    st = os.stat(path)
    write_json(os.path.join(STATE["data"], "latest.json"),
               {"path": path, "name": os.path.basename(path), "mtimeMs": st.st_mtime * 1000, "size": st.st_size})


def library():
    """Models (.step/.stp/.stl, variants grouped) and canvas files (.platno.json) next to the data dir: newest first."""
    root = os.path.abspath(STATE["data"] or ".")
    while os.path.dirname(root) != root and not os.path.basename(root).startswith(".cad-preview"):
        root = os.path.dirname(root)  # data dir is <project>/.cad-preview[/<session>]
    root = os.path.dirname(root) if os.path.basename(root).startswith(".cad-preview") else os.path.dirname(os.path.abspath(STATE["data"] or "."))
    skip = {"node_modules", "__pycache__", "venv", "graphify-out"}
    models, canvases = {}, []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if not d.startswith(".") and d not in skip and dp[len(root):].count(os.sep) < 3]
        for fn in fns:
            full = os.path.join(dp, fn)
            low = fn.lower()
            try:
                st = os.stat(full)
            except OSError:
                continue
            if low.endswith(".platno.json"):
                canvases.append({"name": fn[:-12], "path": full, "mtime": st.st_mtime})
            elif low.endswith(MODEL_EXT) and ".ref." not in low:
                stem = os.path.splitext(fn)[0]
                base, _, label = stem.partition("@")
                m = models.setdefault(os.path.join(dp, base), {"name": base, "path": full, "mtime": st.st_mtime, "size": st.st_size, "variants": []})
                if label:
                    m["variants"].append(label)
                if st.st_mtime >= m["mtime"]:
                    m.update(path=full, mtime=st.st_mtime, size=st.st_size)
    by_time = lambda x: -x["mtime"]  # noqa: E731
    cur = current()
    return {"root": root, "current": cur and cur.get("path"), "models": sorted(models.values(), key=by_time)[:80], "canvases": sorted(canvases, key=by_time)[:40]}


def current():
    """Current model from latest.json, completed with the actual file state."""
    info = read_json(os.path.join(data_dir(), "latest.json"), {})
    path = info.get("path")
    if not path or not os.path.isfile(path):
        return {}
    st = os.stat(path)
    out = {"path": path, "name": os.path.basename(path), "mtimeMs": st.st_mtime * 1000, "size": st.st_size}
    step = sibling_step(path)
    if step:
        out["step"] = step
        out["stepMtimeMs"] = os.path.getmtime(step) * 1000
    script = find_script(path)
    if script:
        out["script"] = script
    motion = os.path.splitext(path)[0] + ".motion.json"
    if os.path.isfile(motion):
        out["motion"] = motion
        out["motionMtimeMs"] = os.path.getmtime(motion) * 1000
    explode = os.path.splitext(path)[0] + ".explode.json"
    if os.path.isfile(explode):
        out["explode"] = explode
        out["explodeMtimeMs"] = os.path.getmtime(explode) * 1000
    return out


def history_dir(model_path):
    key = hashlib.sha1(os.path.normcase(os.path.abspath(model_path)).encode()).hexdigest()[:12]
    return os.path.join(data_dir(), "history", key)


def snapshot_if_changed(cur):
    """Every new state of the model is stored as a version."""
    if not cur:
        return None
    with LOCK:
        hdir = history_dir(cur["path"])
        os.makedirs(hdir, exist_ok=True)
        entries = sorted(e for e in os.listdir(hdir) if os.path.isdir(os.path.join(hdir, e)))
        if entries:
            last = read_json(os.path.join(hdir, entries[-1], "meta.json"), {})
            if abs(last.get("mtimeMs", 0) - cur["mtimeMs"]) < 1 and last.get("size") == cur["size"]:
                return entries[-1]
        vid = stamp()
        vdir = os.path.join(hdir, vid)
        os.makedirs(vdir)
        is_stl = cur["path"].lower().endswith(".stl")
        if is_stl:  # a STEP-only model is stored once, as model.step
            shutil.copy2(cur["path"], os.path.join(vdir, "model.stl"))
        if cur.get("step"):
            shutil.copy2(cur["step"], os.path.join(vdir, "model.step"))
        params = []
        if cur.get("script"):
            shutil.copy2(cur["script"], os.path.join(vdir, "script.py"))
            try:
                params = [{"name": p["name"], "value": p["value"]} for p in parse_params(cur["script"])]
            except Exception:  # noqa: BLE001
                params = []
        label = STATE.pop("pending_label", None) if STATE.get("pending_label") else None
        STATE["pending_label"] = None
        write_json(os.path.join(vdir, "meta.json"), {
            "id": vid, "time": time.time(), "label": label or "export",
            "mtimeMs": cur["mtimeMs"], "size": cur["size"], "params": params,
            "model": cur["path"], "hasStep": bool(cur.get("step")), "hasStl": is_stl, "hasScript": bool(cur.get("script")),
        })
        return vid


# -------------------------------------------------------------- variants

def variants_of(path):
    """Design variants: <base>@<label>.step|.stl in the model's folder, plus <base>.step itself."""
    folder = os.path.dirname(path)
    base = os.path.splitext(os.path.basename(path))[0].split("@", 1)[0]
    found = {}
    try:
        names = os.listdir(folder)
    except OSError:
        names = []
    for n in names:
        stem, ext = os.path.splitext(n)
        if ext.lower() not in MODEL_EXT or stem.endswith(".ref") or (stem != base and not stem.startswith(base + "@")):
            continue
        prev = found.get(stem)
        if prev is None or (ext.lower() != ".stl" and prev.lower().endswith(".stl")):  # STEP wins over STL
            found[stem] = os.path.join(folder, n)
    items = []
    for stem, p in sorted(found.items(), key=lambda kv: (kv[0] != base, kv[0].lower())):
        items.append({"path": p, "name": os.path.basename(p), "label": stem.split("@", 1)[1] if "@" in stem else "base",
                      "mtimeMs": os.path.getmtime(p) * 1000})
    choice = read_json(os.path.join(folder, base + ".variants.json"), {})
    return {"base": base, "chosen": choice.get("path"), "items": items if len(items) > 1 else []}


# ---------------------------------------------------------------- params

PARAM_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _literal(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, bool)):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)) and \
            isinstance(node.operand, ast.Constant) and isinstance(node.operand.value, (int, float)) and \
            not isinstance(node.operand.value, bool):
        return -node.operand.value if isinstance(node.op, ast.USub) else node.operand.value
    raise ValueError


def parse_params(script):
    with open(script, encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src)
    comments = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                comments[tok.start[0]] = tok.string.lstrip("#").strip()
    except tokenize.TokenError:
        pass
    out = []
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        t = node.targets[0]
        if not isinstance(t, ast.Name) or not PARAM_NAME.match(t.id):
            continue
        try:
            val = _literal(node.value)
        except ValueError:
            continue
        if node.value.lineno != node.value.end_lineno:
            continue
        comment = comments.get(node.lineno, "")
        unit = ""
        m = re.search(r"\[([^\]]+)\]", comment)
        if m:
            unit = m.group(1)
        kind = "bool" if isinstance(val, bool) else ("int" if isinstance(val, int) else "float")
        out.append({
            "name": t.id, "value": val, "type": kind, "comment": comment, "unit": unit,
            "line": node.value.lineno, "col": node.value.col_offset, "endCol": node.value.end_col_offset,
        })
    return out


def fmt_value(val, kind):
    if kind == "bool":
        return "True" if val else "False"
    if kind == "int":
        return str(int(round(float(val))))
    v = float(val)
    s = f"{v:.6f}".rstrip("0")
    return s + "0" if s.endswith(".") else s


def write_params(script, values):
    params = {p["name"]: p for p in parse_params(script)}
    with open(script, encoding="utf-8") as f:
        lines = f.read().split("\n")
    changes = []
    # back to front by position so offsets do not shift
    for name, val in sorted(values.items(), key=lambda kv: (-params[kv[0]]["line"], -params[kv[0]]["col"])
                            if kv[0] in params else (0, 0)):
        p = params.get(name)
        if not p:
            continue
        i = p["line"] - 1
        line = lines[i]
        # col_offset is in UTF-8 bytes
        b = line.encode("utf-8")
        new = fmt_value(val, p["type"])
        old = b[p["col"]:p["endCol"]].decode("utf-8")
        if old == new:
            continue
        lines[i] = (b[:p["col"]] + new.encode("utf-8") + b[p["endCol"]:]).decode("utf-8")
        changes.append(f"{name} {old}→{new}")
    with open(script, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines))
    return changes


def run_script(script):
    t0 = time.time()
    r = subprocess.run([sys.executable, os.path.basename(script)], cwd=os.path.dirname(script),
                       capture_output=True, text=True, timeout=600,
                       creationflags=0x08000000 if os.name == "nt" else 0)
    return {"ok": r.returncode == 0, "code": r.returncode, "stdout": r.stdout[-4000:],
            "stderr": r.stderr[-4000:], "ms": int((time.time() - t0) * 1000)}


# ---------------------------------------------------------------- notes

def annotations_for(model):
    inbox = os.path.join(data_dir(), "inbox")
    status = read_json(os.path.join(data_dir(), "status.json"), {})
    out = []
    try:
        names = sorted(n for n in os.listdir(inbox) if n.endswith(".json"))
    except OSError:
        return out
    norm = os.path.normcase(os.path.abspath(model)) if model else None
    for n in names:
        a = read_json(os.path.join(inbox, n), None)
        if not a:
            continue
        a["id"] = a.get("id") or n[:-5]
        if norm and os.path.normcase(os.path.abspath(a.get("model") or "")) != norm:
            continue
        s = status.get(a["id"], {})
        a["status"] = s.get("status", "open")
        a["statusNote"] = s.get("note", "")
        out.append(a)
    for i, a in enumerate(out, 1):
        a["number"] = i
    return out


MARK_POINTS = {"point": (1, 1), "line": (2, 2), "area": (3, 200)}


def _vec3(v):
    v = [float(c) for c in v]
    if len(v) != 3 or not all(math.isfinite(c) for c in v):
        raise ValueError("a point needs 3 finite coordinates")
    return v


def annotate_batch(body):
    """All viewer markers (point / line / area, a note each) as one inbox note with kind batch. A bad marker rejects all."""
    markers = body.get("markers")
    if not isinstance(markers, list) or not 0 < len(markers) <= 200:
        raise ValueError("markers: 1 to 200 expected")
    out = []
    for m in markers:
        typ = m.get("type") if isinstance(m, dict) else None
        if typ not in MARK_POINTS:
            raise ValueError("marker type must be point, line or area")
        pts = [_vec3(p) for p in m.get("points") or []]
        lo, hi = MARK_POINTS[typ]
        if not lo <= len(pts) <= hi:
            raise ValueError(f"a {typ} marker needs {lo}{'' if lo == hi else f' to {hi}'} points")
        out.append({"label": str(m.get("label") or "")[:8], "type": typ, "points": pts,
                    "faceNormal": _vec3(m.get("faceNormal") or [0, 0, 0]),
                    "part": None if m.get("part") is None else str(m["part"])[:200], "note": str(m.get("note") or "")[:4000]})
    sid = stamp()
    write_json(os.path.join(data_dir(), "inbox", f"{sid}.json"), {
        "id": sid, "kind": "batch", "model": str(body.get("model") or ""), "name": str(body.get("name") or ""),
        "step": body.get("step") or None,
        "comment": ("; ".join(f"{m['label']}: {m['note'] or '(no note)'}" for m in out))[:4000],
        "markers": out, "camera": body.get("camera") if isinstance(body.get("camera"), dict) else None,
        "parts": [str(p) for p in body.get("parts") or []][:500],
        "anchor": out[0]["points"][0], "anchorPart": out[0]["part"], "created": time.time()})
    return sid


# ---------------------------------------------------------------- sketch (infinite canvas)
# <data>/sketch.json = {"v": 2, "rev": n, "items": {id: item}, "snaps": {id: snap}}. Every change bumps rev and stamps the
# changed items / snaps with it, so a tab asks only for what changed since its last rev; deletions stay as tombstones.

SKETCH_V = 2
SNAP_MODEL = "claude-opus-5-5"
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
COLOR_RE = re.compile(r"^(ink|#[0-9a-fA-F]{6})$")
IMG_RE = re.compile(r"^[0-9a-f]{40}\.(png|jpg|webp)$")
IMG_TYPES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}
SNAP_STATUS = ("pending", "proposed", "accepted", "rejected", "error")
SKETCH_COND = threading.Condition(LOCK)


def sketch_path():
    return os.path.join(data_dir(), "sketch.json")


def load_sketch():
    p = sketch_path()
    c = STATE.get("sk")
    if c and c[0] == p:
        return c[1]
    sk = read_json(p, None)
    if not isinstance(sk, dict) or sk.get("v") != SKETCH_V:
        if os.path.isfile(p):  # a sketch from the old pad: keep it aside instead of overwriting it
            os.replace(p, os.path.join(data_dir(), "sketch.v1.json"))
        sk = {"v": SKETCH_V, "rev": 0, "items": {}, "snaps": {}}
    STATE["sk"] = (p, sk)
    return sk


def _num(v, lim=1e7):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or abs(v) > lim:
        raise ValueError(f"bad number {v!r}")
    return round(float(v), 2)


def _color(v):
    v = v or "ink"
    if not isinstance(v, str) or not COLOR_RE.match(v):
        raise ValueError(f"bad color {v!r}")
    return v


def clean_item(it):
    """One canvas item as the pad stores it; raises ValueError on anything malformed."""
    if not isinstance(it, dict) or not ID_RE.match(str(it.get("id", ""))):
        raise ValueError("bad item id")
    t = it.get("t")
    out = {"id": it["id"], "t": t, "z": _num(it.get("z", 0), 1e15)}
    if t == "stroke":
        pts = it.get("pts")
        if not isinstance(pts, list) or not 1 <= len(pts) <= 20000 or not all(isinstance(p, list) and len(p) >= 2 for p in pts):
            raise ValueError("bad stroke points")
        out["pts"] = [[_num(p[0]), _num(p[1]), min(1.0, max(0.0, _num(p[2] if len(p) > 2 else 0.5)))] for p in pts]
        out["w"] = min(400.0, max(0.1, _num(it.get("w", 2))))
        out["tool"] = "hl" if it.get("tool") == "hl" else "pen"
        out["color"] = _color(it.get("color"))
    elif t == "text":
        if not isinstance(it.get("s"), str):
            raise ValueError("text needs s")
        out.update(x=_num(it.get("x")), y=_num(it.get("y")), s=it["s"][:5000], size=min(2000.0, max(2.0, _num(it.get("size", 18)))),
                   color=_color(it.get("color")))
    elif t == "image":
        src = str(it.get("src", ""))
        if not src.startswith("/api/sketch/image?f=") or not IMG_RE.match(src[20:]):
            raise ValueError("bad image src")
        out.update(src=src, x=_num(it.get("x")), y=_num(it.get("y")), w=max(1.0, _num(it.get("w"))), h=max(1.0, _num(it.get("h"))))
    else:
        raise ValueError(f"bad item type {t!r}")
    return out


def save_sketch_doc(sk):
    write_json(sketch_path(), sk)
    SKETCH_COND.notify_all()


def sketch_ops(put=(), dels=(), snaps=(), by=""):
    """Apply one batch atomically (all validated first): deletions, then puts, then snap status changes."""
    items = [clean_item(i) for i in put or []]
    ids = [str(i) for i in dels or []]
    if not all(ID_RE.match(i) for i in ids):
        raise ValueError("bad id to delete")
    sn = [s for s in snaps or [] if isinstance(s, dict) and s.get("status") in SNAP_STATUS]
    by = str(by)[:40]
    with SKETCH_COND:
        sk = load_sketch()
        sk["rev"] += 1
        r = sk["rev"]
        for i in ids:
            sk["items"][i] = {"id": i, "deleted": True, "rev": r, "by": by}
        for it in items:
            sk["items"][it["id"]] = {**it, "rev": r, "by": by}
        for s in sn:
            if s.get("id") in sk["snaps"]:
                sk["snaps"][s["id"]].update(status=s["status"], rev=r)
        save_sketch_doc(sk)
        return r


def sketch_changes(since, wait=0):
    with SKETCH_COND:
        if wait and load_sketch()["rev"] <= since:
            SKETCH_COND.wait_for(lambda: load_sketch()["rev"] != since, timeout=min(wait, 25))
        sk = load_sketch()
        items = [i for i in sk["items"].values() if i["rev"] > since and not (since == 0 and i.get("deleted"))]
        return {"v": SKETCH_V, "rev": sk["rev"], "items": items, "snaps": [s for s in sk["snaps"].values() if s["rev"] > since],
                "api": api_available()}


def api_available():
    import importlib.util  # noqa: PLC0415
    return bool(os.environ.get("ANTHROPIC_API_KEY")) and importlib.util.find_spec("anthropic") is not None


def save_data_url(url, folder, name=None):
    """data:image/...;base64 -> file in <data>/<folder>; returns the file name (content hash) or raises ValueError."""
    m = re.match(r"^data:image/(png|jpeg|webp);base64,", url or "")
    if not m:
        raise ValueError("image must be a PNG, JPEG or WebP data URL")
    raw = base64.b64decode(url[m.end():])
    if len(raw) > 20 * 1024 * 1024:
        raise ValueError("image too large")
    ext = "jpg" if m.group(1) == "jpeg" else m.group(1)
    name = (name or hashlib.sha1(raw).hexdigest()) + "." + ext
    os.makedirs(os.path.join(data_dir(), folder), exist_ok=True)
    with open(os.path.join(data_dir(), folder, name), "wb") as f:
        f.write(raw)
    return name


def _shape_pts(raw):
    """Proposal shorthands (line / rect / ellipse) become stroke points."""
    t = raw.get("t")
    if t == "line":
        return [raw["a"], raw["b"]]
    x, y, w, h = (raw[k] for k in ("x", "y", "w", "h"))
    if t == "rect":
        return [[x, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y]]
    if t == "ellipse":
        return [[x + w / 2 + w / 2 * math.cos(k * math.pi / 32), y + h / 2 + h / 2 * math.sin(k * math.pi / 32)] for k in range(65)]
    raise ValueError(f"bad proposal item type {t!r}")


def clean_proposal(raws, snap, space="world"):
    """Proposal items -> pad items in world units. Items with nothing inside the region are dropped; the pad clips the rest
    exactly to the region when it shows and accepts them."""
    rx, ry, rw, rh = snap["rect"]
    sc = snap.get("scale") or 1
    if space not in ("world", "rect", "image"):
        raise ValueError("space must be world, rect or image")
    k = 1 / sc if space == "image" else 1
    ox, oy = (0, 0) if space == "world" else (rx, ry)
    to_w = lambda p: [ox + _num(p[0]) * k, oy + _num(p[1]) * k] + ([_num(p[2])] if len(p) > 2 else [])  # noqa: E731
    inside = lambda p: rx - 1 <= p[0] <= rx + rw + 1 and ry - 1 <= p[1] <= ry + rh + 1  # noqa: E731
    out = []
    for n, raw in enumerate(raws if isinstance(raws, list) else []):
        if not isinstance(raw, dict):
            raise ValueError("proposal items must be objects")
        it = {"id": f"{snap['id']}-{snap.get('round', 1)}-{n}", "z": time.time() + n * 1e-4, "color": raw.get("color", "ink")}
        if raw.get("t") == "text":
            x, y = to_w([raw.get("x"), raw.get("y")])
            it.update(t="text", x=x, y=y, s=raw.get("s"), size=_num(raw.get("size", 18)) * k)
            if not inside([x, y]):
                continue
        else:
            try:
                pts = [to_w(p) for p in (raw["pts"] if raw.get("t", "stroke") == "stroke" else _shape_pts(raw))]
            except (KeyError, TypeError, IndexError) as e:
                raise ValueError(f"proposal item {n}: missing or malformed {e}") from None
            if not any(inside(p) for p in pts):
                continue
            lw = raw.get("lw", 2) if raw.get("t") in ("rect", "ellipse") else raw.get("lw", raw.get("w", 2))  # rect / ellipse use w for the box
            it.update(t="stroke", pts=pts, w=_num(lw) * k, tool="hl" if raw.get("tool") == "hl" else "pen")
        out.append(clean_item(it))
    return out


def sketch_snap(body):
    """A snap request: the region image, the instruction and the region's items go to Claude; returns the snap id."""
    rect = [_num(v) for v in body.get("rect") or []]
    text = str(body.get("text", "")).strip()[:4000]
    if len(rect) != 4 or rect[2] <= 0 or rect[3] <= 0 or not text:
        raise ValueError("snap needs rect [x, y, w, h] and text")
    sid = "snap-" + stamp()
    png = os.path.join(data_dir(), "shots", save_data_url(body.get("image"), "shots", sid))
    with SKETCH_COND:
        sk = load_sketch()
        ids = [i for i in body.get("ids") or [] if i in sk["items"] and not sk["items"][i].get("deleted")]
        region = [sk["items"][i] for i in ids]
        sk["rev"] += 1
        snap = {"id": sid, "rect": rect, "text": text, "ids": ids, "scale": _num(body.get("scale", 1)), "status": "pending",
                "round": 1, "rev": sk["rev"], "created": time.time()}
        sk["snaps"][sid] = snap
        outside = [i for i in sk["items"].values() if not i.get("deleted") and i["id"] not in ids]
        save_sketch_doc(sk)
    req = {"id": sid, "instruction": text, "rect": rect, "scale": snap["scale"], "image": png,
           "items": [{k: v for k, v in i.items() if k not in ("rev", "by")} for i in region],
           "outsideBounds": [b for b in body.get("outside") or []][:500], "outsideCount": len(outside),
           "answer": f"POST /api/sketch/proposal {{\"snap\": \"{sid}\", \"space\": \"world|rect|image\", \"items\": [...]}}"}
    req_file = os.path.join(data_dir(), "snaps", f"{sid}.json")
    write_json(req_file, req)
    if body.get("direct") and api_available():
        threading.Thread(target=snap_direct, args=(sid, req), daemon=True).start()
    else:
        write_json(os.path.join(data_dir(), "inbox", f"{sid}.json"), {
            "id": sid, "kind": "snap", "model": current().get("path", ""), "name": current().get("name", ""), "comment": text,
            "rect": rect, "scale": snap["scale"], "screenshot": png, "sketch": req_file, "created": time.time()})
    return sid


def sketch_proposal(sid, raws, space="world", note=""):
    with SKETCH_COND:
        sk = load_sketch()
        snap = sk["snaps"].get(sid)
        if not snap:
            raise KeyError("no such snap")
        if snap["status"] not in ("pending", "proposed", "error"):
            raise ValueError(f"snap is already {snap['status']}")
        items = clean_proposal(raws, snap, space)
        sk["rev"] += 1
        snap.update(status="proposed", proposal=items, note=str(note)[:1000], rev=sk["rev"])
        save_sketch_doc(sk)
        return len(items)


SNAP_SYSTEM = """You redraw one rectangular region of an engineer's hand-drawn sketch on an infinite canvas.
You get the region as an image, the instruction, and the region's items. Return the complete new content of the
region (it replaces everything drawn there): pen strokes as point lists in IMAGE PIXELS of the given image (0,0 = top-left),
straight parts as few points, curves as enough points to look smooth; text as {t: text, x, y, s, size}.
Keep what the instruction does not ask to change, stay inside the image, use color "ink" unless asked otherwise."""

SNAP_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["items", "note"],
    "properties": {
        "note": {"type": "string"},
        "items": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["t"],
            "properties": {
                "t": {"type": "string", "enum": ["stroke", "text"]},
                "pts": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
                "w": {"type": "number"}, "color": {"type": "string"},
                "x": {"type": "number"}, "y": {"type": "number"}, "s": {"type": "string"}, "size": {"type": "number"},
            }}},
    },
}


def snap_direct(sid, req):
    """ANTHROPIC_API_KEY set: ask the model directly; the proposal (or the error) lands on the snap like one from the chat."""
    try:
        import anthropic  # noqa: PLC0415
        with open(req["image"], "rb") as f:
            img = base64.b64encode(f.read()).decode()
        items = json.dumps(req["items"], separators=(",", ":"))[:60000]
        content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img}},
                   {"type": "text", "text": f"Instruction: {req['instruction']}\nImage scale: {req['scale']} px per world unit, "
                                            f"region {req['rect']} (world x, y, w, h).\nRegion items (world units): {items}"}]
        client = anthropic.Anthropic(max_retries=1, timeout=180)
        r = client.beta.messages.create(
            model=SNAP_MODEL, max_tokens=16000, system=SNAP_SYSTEM, messages=[{"role": "user", "content": content}],
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SNAP_SCHEMA}},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        if r.stop_reason in ("refusal", "max_tokens"):
            raise RuntimeError(f"no usable reply ({r.stop_reason})")
        data = json.loads(next(b.text for b in r.content if b.type == "text"))
        sketch_proposal(sid, data.get("items", []), "image", data.get("note", ""))
    except Exception as e:  # noqa: BLE001  (shown on the snap in the pad)
        with SKETCH_COND:
            sk = load_sketch()
            snap = sk["snaps"].get(sid)
            if snap and snap["status"] == "pending":
                sk["rev"] += 1
                snap.update(status="error", note=f"AI call failed: {str(e)[:300]}", rev=sk["rev"])
                save_sketch_doc(sk)


def sketch_send(body):
    """The whole canvas as a brief for Claude: a PNG plus a text list of what is on it."""
    sid = stamp()
    png = os.path.join(data_dir(), "shots", save_data_url(body.get("image"), "shots", "sketch-" + sid))
    with SKETCH_COND:
        live = [i for i in load_sketch()["items"].values() if not i.get("deleted")]
    count = {t: sum(1 for i in live if i["t"] == t) for t in ("stroke", "text", "image")}
    lines = [f"{count['stroke']} strokes, {count['text']} texts, {count['image']} images"]
    lines += [f'text at ({i["x"]:.0f}, {i["y"]:.0f}): {i["s"][:300]}' for i in sorted(live, key=lambda i: i.get("z", 0)) if i["t"] == "text"][:80]
    write_json(os.path.join(data_dir(), "inbox", f"{sid}.json"), {
        "id": sid, "kind": "sketch", "model": current().get("path", ""), "name": current().get("name", ""),
        "comment": str(body.get("text", ""))[:4000], "summary": "\n".join(lines), "screenshot": png, "sketch": sketch_path(),
        "created": time.time()})
    return sid


# ---------------------------------------------------------------- server

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False)
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if lan_on():
            self.send_header("Set-Cookie", f"cadlan={lan_token()}; Path=/; HttpOnly; SameSite=Strict")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, ctype="application/octet-stream"):
        with open(path, "rb") as f:
            return self._send(200, f.read(), ctype)

    def _json_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 60 * 1024 * 1024:
            raise ValueError("too large")
        return json.loads(self.rfile.read(n).decode("utf-8") or "{}")

    def _lan_denied(self, url):
        """Other machines (CAD_PREVIEW_LAN=1) need the token from <data>/lan-token, sent once as ?t= and kept in a cookie."""
        if self.client_address[0] in ("127.0.0.1", "::1"):
            return False
        tok = lan_token()
        if parse_qs(url.query).get("t", [""])[0] == tok:
            return False
        if f"cadlan={tok}" in (self.headers.get("Cookie") or ""):
            return False
        self._send(403, {"error": "token required"})
        return True

    def do_GET(self):  # noqa: C901
        STATE["last"] = time.time()
        url = urlparse(self.path)
        if self._lan_denied(url):
            return
        q = parse_qs(url.query)
        try:
            if url.path in STATIC:
                name = STATIC[url.path]
                ctype = "text/html; charset=utf-8" if name.endswith(".html") else "text/javascript; charset=utf-8"
                return self._file(os.path.join(HERE, name), ctype)
            if url.path.startswith("/api/canvas"):
                res = CV.route("GET", url.path, q, None, STATE["data"])
                if res:
                    return self._send(*res)
            if url.path == "/api/lan" and self.client_address[0] in ("127.0.0.1", "::1"):  # the token only to this PC
                return self._send(200, lan_info(self.server.server_address[1]))
            if url.path == "/api/library":
                return self._send(200, library())
            if url.path == "/api/ping":
                return self._send(200, {"ok": True, "data": STATE["data"]})
            if url.path == "/api/latest":
                cur = current()
                if cur:
                    cur["version"] = snapshot_if_changed(cur)
                return self._send(200, cur)
            if url.path == "/api/file":
                path = (q.get("path") or [""])[0]
                if not path.lower().endswith(MODEL_EXT) or not os.path.isfile(path):
                    return self._send(404, {"error": "not found"})
                return self._file(path)
            if url.path in ("/api/motion", "/api/explode"):
                key = url.path.rsplit("/", 1)[1]
                cur = current()
                if not cur.get(key):
                    return self._send(404, {"error": f"no {key} file"})
                try:
                    with open(cur[key], encoding="utf-8") as f:
                        data = json.load(f)
                except ValueError as e:
                    return self._send(400, {"error": f"invalid {os.path.basename(cur[key])}: {e}"})
                return self._send(200, data)
            if url.path == "/api/params":
                cur = current()
                if not cur.get("script"):
                    return self._send(200, {"script": None, "params": []})
                try:
                    return self._send(200, {"script": cur["script"], "params": parse_params(cur["script"])})
                except SyntaxError as exc:
                    return self._send(200, {"script": cur["script"], "params": [], "error": str(exc)})
            if url.path == "/api/history":
                cur = current()
                if not cur:
                    return self._send(200, [])
                hdir = history_dir(cur["path"])
                items = []
                if os.path.isdir(hdir):
                    for e in sorted(os.listdir(hdir)):
                        meta = read_json(os.path.join(hdir, e, "meta.json"), None)
                        if meta:
                            items.append(meta)
                return self._send(200, items)
            if url.path == "/api/history/file":
                cur = current()
                vid = (q.get("id") or [""])[0]
                kind = (q.get("kind") or ["stl"])[0]
                if not cur or not re.match(r"^[0-9-]+$", vid) or kind not in ("stl", "step"):
                    return self._send(404, {"error": "not found"})
                p = os.path.join(history_dir(cur["path"]), vid, f"model.{kind}")
                if not os.path.isfile(p):
                    return self._send(404, {"error": "not found"})
                return self._file(p)
            if url.path == "/api/variants":
                cur = current()
                return self._send(200, variants_of(cur["path"]) if cur else {"items": []})
            if url.path == "/api/export/formats":
                sys.path.insert(0, HERE)
                import export  # noqa: PLC0415
                cq = export.have_cadquery()
                return self._send(200, [{"id": k, "ext": v[0], "label": v[1], "available": cq or not v[2]}
                                        for k, v in export.FORMATS.items()])
            if url.path == "/api/sketch":
                since = int(float((q.get("since") or ["0"])[0]))
                return self._send(200, sketch_changes(since, float((q.get("wait") or ["0"])[0])))
            if url.path == "/api/sketch/image":
                name = (q.get("f") or [""])[0]
                p = os.path.join(data_dir(), "sketch-images", name)
                if not IMG_RE.match(name) or not os.path.isfile(p):
                    return self._send(404, {"error": "not found"})
                return self._file(p, IMG_TYPES[name.rsplit(".", 1)[1]])
            if url.path == "/api/annotations":
                cur = current()
                notes = annotations_for(cur.get("path"))
                for a in notes:
                    a.pop("image", None)
                return self._send(200, notes)
        except Exception as exc:  # noqa: BLE001
            return self._send(500, {"error": str(exc)})
        return self._send(404, {"error": "not found"})

    def do_POST(self):  # noqa: C901
        STATE["last"] = time.time()
        url = urlparse(self.path)
        if self._lan_denied(url):
            return
        try:
            body = self._json_body()
        except Exception as exc:  # noqa: BLE001
            return self._send(400, {"error": str(exc)})
        try:
            if url.path == "/api/open":
                path = os.path.abspath(body.get("path") or "")
                if not path.lower().endswith(MODEL_EXT) or not os.path.isfile(path):
                    return self._send(404, {"error": "not a model file"})
                if not STATE["data"]:
                    return self._send(500, {"error": "no data dir"})
                open_model(path)
                return self._send(200, {"ok": True})

            if url.path == "/api/new/model":  # the "New model" button: a brief for Claude via the chat inbox
                if not STATE["data"]:
                    return self._send(500, {"error": "no data dir"})
                name = re.sub(r"[^\w.-]+", "_", str(body.get("name") or "novy_model").strip())[:60] or "novy_model"
                inbox = os.path.join(data_dir(), "inbox")
                os.makedirs(inbox, exist_ok=True)
                sid = stamp()
                write_json(os.path.join(inbox, f"{sid}.json"), {"id": sid, "kind": "newmodel", "model": name, "name": name,
                                                                 "comment": str(body.get("text") or "")[:4000], "created": time.time()})
                return self._send(200, {"ok": True, "name": name})

            if url.path == "/api/variants/choose":
                cur = current()
                path = os.path.abspath(body.get("path") or "")
                v = variants_of(cur["path"]) if cur else {"items": []}
                item = next((i for i in v["items"] if os.path.normcase(i["path"]) == os.path.normcase(path)), None)
                if not item:
                    return self._send(400, {"error": "not a variant of the current model"})
                folder = os.path.dirname(path)
                write_json(os.path.join(folder, v["base"] + ".variants.json"),
                           {"chosen": item["label"], "path": path, "time": time.time()})
                inbox = os.path.join(data_dir(), "inbox")
                os.makedirs(inbox, exist_ok=True)
                sid = stamp()
                write_json(os.path.join(inbox, f"{sid}.json"), {
                    "id": sid, "kind": "variant", "model": path, "name": item["name"], "comment": item["label"],
                    "variants": [i["label"] for i in v["items"]], "created": time.time()})
                return self._send(200, {"ok": True})

            if url.path == "/api/export":
                cur = current()
                fmt = str(body.get("format", ""))
                quality = str(body.get("quality", "normal"))
                if not cur:
                    return self._send(400, {"error": "no model"})
                if not re.match(r"^[a-z0-9]+$", fmt) or quality not in ("coarse", "normal", "fine"):
                    return self._send(400, {"error": "bad format"})
                if not EXPORT_LOCK.acquire(blocking=False):
                    return self._send(409, {"error": "an export is already running (is a Save dialog open?)"})
                try:
                    r = subprocess.run([sys.executable, os.path.join(HERE, "export.py"), cur.get("step") or cur["path"],
                                        fmt, "--quality", quality], capture_output=True, text=True, timeout=900,
                                       creationflags=0x08000000 if os.name == "nt" else 0)
                finally:
                    EXPORT_LOCK.release()
                try:
                    res = json.loads(r.stdout.strip().splitlines()[-1])
                except (ValueError, IndexError):
                    res = {"ok": False, "error": (r.stderr or r.stdout or "export failed")[-500:]}
                return self._send(200 if res.get("ok") or res.get("cancelled") else 500, res)

            if url.path == "/api/data":
                STATE["data"] = body.get("data") or STATE["data"]
                return self._send(200, {"ok": True})

            if url.path == "/api/annotate":
                if not STATE["data"]:
                    return self._send(500, {"error": "no data dir"})
                inbox = os.path.join(STATE["data"], "inbox")
                shots = os.path.join(STATE["data"], "shots")
                os.makedirs(inbox, exist_ok=True)
                os.makedirs(shots, exist_ok=True)
                sid = stamp()
                image = body.pop("image", "") or ""
                if image.startswith("data:image/png;base64,"):
                    png = os.path.join(shots, f"annotation-{sid}.png")
                    with open(png, "wb") as f:
                        f.write(base64.b64decode(image.split(",", 1)[1]))
                    body["screenshot"] = png
                body["id"] = sid
                body["created"] = time.time()
                tmp = os.path.join(inbox, f"{sid}.tmp")
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(body, f, ensure_ascii=False)
                os.replace(tmp, os.path.join(inbox, f"{sid}.json"))
                return self._send(200, {"ok": True, "id": sid})

            if url.path == "/api/annotations/clear":
                # move (not delete) the model's note files into inbox/_trash, so they can be restored by hand
                inbox = os.path.join(data_dir(), "inbox")
                trash = os.path.join(inbox, "_trash")
                os.makedirs(trash, exist_ok=True)
                norm = os.path.normcase(os.path.abspath(body.get("model") or "")) if body.get("model") else None
                moved = 0
                for n in os.listdir(inbox):
                    p = os.path.join(inbox, n)
                    if not n.endswith(".json") or not os.path.isfile(p):
                        continue
                    a = read_json(p, None)
                    if a and norm and os.path.normcase(os.path.abspath(a.get("model") or "")) == norm:
                        os.replace(p, os.path.join(trash, n))
                        moved += 1
                return self._send(200, {"ok": True, "moved": moved})

            if url.path == "/api/annotate-batch":
                if not STATE["data"]:
                    return self._send(500, {"error": "no data dir"})
                try:
                    return self._send(200, {"ok": True, "id": annotate_batch(body)})
                except (ValueError, TypeError, AttributeError) as exc:
                    return self._send(400, {"error": str(exc)})

            if url.path.startswith("/api/canvas"):
                res = CV.route("POST", url.path, {}, body, STATE["data"])
                if res:
                    return self._send(*res)

            if url.path.startswith("/api/sketch"):
                if not STATE["data"]:
                    return self._send(500, {"error": "no data dir"})
                try:
                    if url.path == "/api/sketch/ops":
                        return self._send(200, {"ok": True, "rev": sketch_ops(body.get("put"), body.get("del"), body.get("snaps"), body.get("by", ""))})
                    if url.path == "/api/sketch/image":
                        return self._send(200, {"ok": True, "src": "/api/sketch/image?f=" + save_data_url(body.get("image"), "sketch-images")})
                    if url.path == "/api/sketch/snap":
                        return self._send(200, {"ok": True, "id": sketch_snap(body)})
                    if url.path == "/api/sketch/proposal":
                        n = sketch_proposal(str(body.get("snap", "")), body.get("items"), body.get("space", "world"), body.get("note", ""))
                        return self._send(200, {"ok": True, "items": n})
                    if url.path == "/api/sketch/send":
                        return self._send(200, {"ok": True, "id": sketch_send(body)})
                except KeyError as exc:
                    return self._send(404, {"error": str(exc.args[0] if exc.args else exc)})
                except (ValueError, TypeError, IndexError) as exc:
                    return self._send(400, {"error": str(exc)})

            if url.path == "/api/screenshot":
                image = body.get("image", "") or ""
                if not image.startswith("data:image/png;base64,"):
                    return self._send(400, {"error": "missing PNG"})
                shots = os.path.join(data_dir(), "shots")
                os.makedirs(shots, exist_ok=True)
                png = os.path.join(shots, f"screenshot-{stamp()}.png")
                with open(png, "wb") as f:
                    f.write(base64.b64decode(image.split(",", 1)[1]))
                return self._send(200, {"ok": True, "path": png})

            if url.path == "/api/annotations/status":
                sid = str(body.get("id", ""))
                st = body.get("status", "open")
                if not re.match(r"^[0-9-]+$", sid) or st not in ("open", "done", "hidden"):
                    return self._send(400, {"error": "bad id or status"})
                with LOCK:
                    path = os.path.join(data_dir(), "status.json")
                    status = read_json(path, {})
                    status[sid] = {"status": st, "note": str(body.get("note", ""))[:500], "time": time.time()}
                    write_json(path, status)
                return self._send(200, {"ok": True})

            if url.path == "/api/params":
                cur = current()
                script = cur.get("script")
                if not script:
                    return self._send(400, {"error": "no script found for the model"})
                values = body.get("values") or {}
                if not RUN_LOCK.acquire(blocking=False):
                    return self._send(409, {"error": "script is already running"})
                try:
                    snapshot_if_changed(cur)  # keep the original state as a version
                    changes = write_params(script, values)
                    if not changes:
                        return self._send(200, {"ok": True, "changes": [], "skipped": True})
                    STATE["pending_label"] = "parameters: " + ", ".join(changes)
                    res = run_script(script)
                    res["changes"] = changes
                    if res["ok"]:
                        snapshot_if_changed(current())
                    else:
                        STATE["pending_label"] = None
                    return self._send(200, res)
                finally:
                    RUN_LOCK.release()

            if url.path == "/api/history/restore":
                cur = current()
                vid = str(body.get("id", ""))
                if not cur or not re.match(r"^[0-9-]+$", vid):
                    return self._send(400, {"error": "bad id"})
                vdir = os.path.join(history_dir(cur["path"]), vid)
                if not os.path.isdir(vdir):
                    return self._send(404, {"error": "version does not exist"})
                snapshot_if_changed(cur)
                meta = read_json(os.path.join(vdir, "meta.json"), {})
                if os.path.isfile(os.path.join(vdir, "model.stl")) and cur["path"].lower().endswith(".stl"):
                    shutil.copy2(os.path.join(vdir, "model.stl"), cur["path"])
                if os.path.isfile(os.path.join(vdir, "model.step")) and cur.get("step"):
                    shutil.copy2(os.path.join(vdir, "model.step"), cur["step"])
                if os.path.isfile(os.path.join(vdir, "script.py")) and cur.get("script"):
                    shutil.copy2(os.path.join(vdir, "script.py"), cur["script"])
                now = time.time()
                os.utime(cur["path"], (now, now))
                if cur.get("step"):
                    os.utime(cur["step"], (now, now))
                STATE["pending_label"] = "restored from version " + time.strftime(
                    "%H:%M:%S", time.localtime(meta.get("time", now)))
                snapshot_if_changed(current())
                return self._send(200, {"ok": True})
        except Exception as exc:  # noqa: BLE001
            return self._send(500, {"error": str(exc)})
        return self._send(404, {"error": "not found"})


LAN_FLAG = os.path.join(os.path.expanduser("~"), ".cad-preview-lan")


def lan_on():
    """Network mode: the env var, or the flag file so servers the plugin starts (no env) get it too."""
    return bool(os.environ.get("CAD_PREVIEW_LAN")) or os.path.isfile(LAN_FLAG)


def lan_ips():
    """This PC's IPv4 addresses on the local network (the default route's first)."""
    import socket  # noqa: PLC0415
    ips = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as so:
            so.connect(("192.0.2.1", 9))  # no packet is sent; only picks the outgoing interface
            ips.append(so.getsockname()[0])
    except OSError:
        pass
    try:
        ips += socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        pass
    return [ip for i, ip in enumerate(ips) if ip not in ips[:i] and not ip.startswith(("127.", "169.254."))]


def lan_info(port):
    """Full addresses another device on the same network can open (token included); lan false when not in network mode."""
    if not lan_on() or not STATE["data"]:
        return {"lan": False, "hint": f"create {LAN_FLAG} (or set CAD_PREVIEW_LAN=1) and restart the server"}
    t = lan_token()
    return {"lan": True, "token": t, "urls": [{"ip": ip, "viewer": f"http://{ip}:{port}/?t={t}", "canvas": f"http://{ip}:{port}/canvas?t={t}",
                                               "sketch": f"http://{ip}:{port}/sketch?t={t}"} for ip in lan_ips()]}


def lan_token():
    p = os.path.join(STATE["data"], "lan-token")
    if not os.path.isfile(p):
        with open(p, "w") as f:
            f.write(secrets.token_urlsafe(16))
    return open(p).read().strip()


def hand_over(port, data):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/data",
        data=json.dumps({"data": data}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=3).read()
        return True
    except Exception:  # noqa: BLE001
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--data", required=True)
    ap.add_argument("--detach", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.data, exist_ok=True)

    if a.detach:
        if hand_over(a.port, a.data):
            print("handed-over")
            return
        flags = 0
        if os.name == "nt":
            flags = 0x00000008 | 0x00000200 | 0x08000000
        subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "--port", str(a.port), "--data", a.data],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=flags, close_fds=True,
            start_new_session=(os.name != "nt"),
        )
        print("started")
        return

    STATE["data"] = a.data
    try:
        srv = ThreadingHTTPServer(("0.0.0.0" if lan_on() else "127.0.0.1", a.port), Handler)
    except OSError:
        hand_over(a.port, a.data)
        return
    srv.timeout = 30
    while time.time() - STATE["last"] < IDLE_LIMIT:
        srv.handle_request()


if __name__ == "__main__":
    main()

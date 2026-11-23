"""Backend of the construction canvas (/canvas): the object store with revisions, layers, snapshots, AI requests,
briefing questions pinned to geometry and AI change proposals. server.py hands every /api/canvas* call to route().

<data>/canvas.json = {"v": 1, "rev": n, "objs": {id: obj}, "layers": [...], "regions": {...}, "briefs": {...}, "reqs": {...},
"snaps": [...]}. Every change bumps rev and stamps the changed records with it, so a tab asks only for what changed since its
last rev; deleted objects stay as tombstones. Requests for Claude go to <data>/inbox (the plugin hook puts them in the chat
draft, never sends them); Claude answers through skills/cad-canvas/scripts/canvas.py (briefing, preview, status).
"""
import base64
import json
import os
import re
import threading
import time

V = 1
ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,60}$")
COLOR_RE = re.compile(r"^(ink|#[0-9a-fA-F]{6})$")
LAYER_NAMES = ["Ruční náčrty", "AI geometrie", "Poznámky", "Kóty a značení", "Konstrukční prvky", "Mechanismy", "Trajektorie", "AI briefing", "Importy"]
AUTONOMY = ("consult", "propose", "direct")
CONTEXT = ("selection", "around", "page")
REQ_STATUS = ("pending", "asking", "drafting", "proposed", "applied", "rejected", "closed")  # closed: done without a change, or dropped
LOCK = threading.RLock()
COND = threading.Condition(LOCK)
CACHE = {}


class Conflict(Exception):
    """Objects changed since the request was made: .ids lists them."""

    def __init__(self, ids):
        super().__init__("objects changed since the request: " + ", ".join(ids))
        self.ids = ids


# ---------------------------------------------------------------- storage
def _path(data):
    return os.path.join(data, "canvas.json")


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def load(data):
    c = CACHE.get(data)
    if c:
        return c
    try:
        with open(_path(data), encoding="utf-8") as f:
            doc = json.load(f)
        if doc.get("v") != V:
            raise ValueError
    except Exception:  # noqa: BLE001
        doc = {"v": V, "rev": 0, "objs": {}, "regions": {}, "briefs": {}, "reqs": {}, "snaps": [],
               "layers": [{"n": i + 1, "name": n, "vis": True, "lock": False, "op": 1.0} for i, n in enumerate(LAYER_NAMES)]}
    CACHE[data] = doc
    return doc


def save(data, doc):
    _write(_path(data), doc)
    COND.notify_all()


def stamp():
    return time.strftime("%Y%m%d-%H%M%S") + "-%03d" % (int(time.time() * 1000) % 1000)


# ---------------------------------------------------------------- validation
def num(v, lim=1e7):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or abs(v) > lim:
        raise ValueError(f"bad number {v!r}")
    return round(float(v), 3)


def pt(v):
    if not isinstance(v, (list, tuple)) or len(v) < 2:
        raise ValueError(f"bad point {v!r}")
    return [num(v[0]), num(v[1])]


DEFAULT_LAYER = {"text": 3, "dim": 4, "mech": 6}


def clean_obj(o):
    """One canvas object as stored; raises ValueError on anything malformed."""
    if not isinstance(o, dict) or not ID_RE.match(str(o.get("id", ""))):
        raise ValueError("bad object id")
    t = o.get("t")
    layer = int(num(o.get("layer", 5 if o.get("cons") else DEFAULT_LAYER.get(t, 1))))
    if not 1 <= layer <= 9:
        raise ValueError("layer must be 1..9")
    color = o.get("color") or "ink"
    if not isinstance(color, str) or not COLOR_RE.match(color):
        raise ValueError(f"bad color {color!r}")
    out = {"id": o["id"], "t": t, "layer": layer, "z": num(o.get("z", 0), 1e15), "color": color,
           "w": min(50.0, max(0.1, num(o.get("w", 1.5))))}
    if o.get("g"):
        if not ID_RE.match(str(o["g"])):
            raise ValueError("bad group id")
        out["g"] = o["g"]
    if o.get("cons"):
        out["cons"] = True
    if t == "stroke":
        pts = o.get("pts")
        if not isinstance(pts, list) or not 1 <= len(pts) <= 20000:
            raise ValueError("bad stroke points")
        out["pts"] = [[*pt(p), min(1.0, max(0.0, num(p[2] if len(p) > 2 else 0.5)))] for p in pts]
        out["tool"] = "hl" if o.get("tool") == "hl" else "pen"
        out["alpha"] = min(1.0, max(0.05, num(o.get("alpha", 1))))
    elif t == "line":
        out.update(a=pt(o.get("a")), b=pt(o.get("b")))
        if o.get("arrow"):
            out["arrow"] = True
    elif t == "circle":
        out.update(c=pt(o.get("c")), r=max(0.01, num(o.get("r"))))
    elif t == "arc":
        out.update(c=pt(o.get("c")), r=max(0.01, num(o.get("r"))), a0=num(o.get("a0"), 100), a1=num(o.get("a1"), 100))
    elif t == "rect":
        out.update(p=pt(o.get("p")), q=pt(o.get("q")))
    elif t == "ellipse":
        out.update(c=pt(o.get("c")), rx=max(0.01, num(o.get("rx"))), ry=max(0.01, num(o.get("ry"))))
    elif t == "dim":
        kind = o.get("kind", "lin")
        if kind not in ("lin", "dia", "rad"):
            raise ValueError("dim kind must be lin, dia or rad")
        out["kind"] = kind
        if o.get("ref"):
            if not ID_RE.match(str(o["ref"])):
                raise ValueError("bad dim ref")
            out["ref"] = o["ref"]
        if not out.get("ref") or kind == "lin" and o.get("a"):
            out.update(a=pt(o.get("a")), b=pt(o.get("b")))
        if kind == "lin":
            out["off"] = num(o.get("off", 20))
        if "ang" in o:
            out["ang"] = num(o["ang"], 100)
        if o.get("txt"):
            out["txt"] = str(o["txt"])[:40]
        if o.get("edge") is not None:
            out["edge"] = int(num(o["edge"])) % 4
        if o.get("size") is not None:
            out["size"] = min(500.0, max(0.5, num(o["size"])))
    elif t == "text":
        if not isinstance(o.get("s"), str):
            raise ValueError("text needs s")
        out.update(x=num(o.get("x")), y=num(o.get("y")), s=o["s"][:5000], size=min(2000.0, max(2.0, num(o.get("size", 14)))))
    elif t == "mech":
        out.update(clean_mech(o))
    else:
        raise ValueError(f"bad object type {t!r}")
    return out


JOINT_RE = re.compile(r"^[A-Za-z0-9_]{1,12}$")


def clean_mech(o):
    """A kinematic model: joints (some fixed), links between them, sliders (joint on a line), one driving crank."""
    js = o.get("joints")
    if not isinstance(js, list) or not 2 <= len(js) <= 30:
        raise ValueError("mech needs 2..30 joints")
    joints = []
    for j in js:
        if not isinstance(j, dict) or not JOINT_RE.match(str(j.get("id", ""))):
            raise ValueError("bad joint id")
        joints.append({"id": j["id"], "p": pt(j.get("p")), **({"fixed": True} if j.get("fixed") else {})})
    ids = {j["id"] for j in joints}
    if len(ids) != len(joints):
        raise ValueError("joint ids must be unique")
    links = o.get("links")
    if not isinstance(links, list) or not 1 <= len(links) <= 60 or not all(isinstance(l, list) and len(l) == 2 and l[0] in ids and l[1] in ids and l[0] != l[1] for l in links):
        raise ValueError("links must be [[joint, joint], ...] between known joints")
    sliders = []
    for s in o.get("sliders") or []:
        if not isinstance(s, dict) or s.get("j") not in ids:
            raise ValueError("slider needs j (a joint) and a, b (its line)")
        sliders.append({"j": s["j"], "a": pt(s.get("a")), "b": pt(s.get("b"))})
    d = o.get("driver") or {}
    fixed = {j["id"] for j in joints if j.get("fixed")}
    if d.get("c") not in fixed or d.get("j") not in ids or [d["j"], d["c"]] not in links and [d["c"], d["j"]] not in links:
        raise ValueError("driver {j, c}: joint j turns about the fixed joint c, and a link must join them")
    out = {"joints": joints, "links": [list(l) for l in links], "sliders": sliders, "driver": {"j": d["j"], "c": d["c"]},
           "name": str(o.get("name", ""))[:60]}
    if o.get("len") is not None:
        ln = o["len"]
        if not isinstance(ln, list) or len(ln) != len(links):
            raise ValueError("len must give one length per link")
        out["len"] = [max(0.01, num(v)) for v in ln]
    return out


def _public(o):
    return {k: v for k, v in o.items() if k not in ("rev", "by")}


# ---------------------------------------------------------------- objects, layers, snapshots
def ops(data, put=(), dels=(), layers=(), regions=None, by="", base=None, force=False):
    """One atomic batch: validate everything first, check base revs (Conflict), then apply. Returns the new rev."""
    items = [clean_obj(i) for i in put or []]
    ids = [str(i) for i in dels or []]
    if not all(ID_RE.match(i) for i in ids):
        raise ValueError("bad id to delete")
    by = str(by)[:40]
    with COND:
        doc = load(data)
        if base and not force:
            bad = [i for i in {*(it["id"] for it in items), *ids} if i in base and i in doc["objs"] and doc["objs"][i]["rev"] > base[i]]
            if bad:
                raise Conflict(bad)
        doc["rev"] += 1
        r = doc["rev"]
        for i in ids:
            if i in doc["objs"]:
                doc["objs"][i] = {"id": i, "deleted": True, "rev": r, "by": by}
        for it in items:
            doc["objs"][it["id"]] = {**it, "rev": r, "by": by}
        for ly in layers or []:
            for cur in doc["layers"]:
                if isinstance(ly, dict) and cur["n"] == ly.get("n"):
                    cur.update({k: ly[k] for k in ("name", "vis", "lock", "op") if k in ly})
                    cur["op"] = min(1.0, max(0.05, num(cur["op"])))
        if isinstance(regions, dict):
            for k, v in regions.items():
                if not ID_RE.match(k):
                    raise ValueError("bad region id")
                if v is None:
                    doc["regions"].pop(k, None)
                else:
                    doc["regions"][k] = {"id": k, "name": str(v.get("name", ""))[:60], "rect": [num(x) for x in v["rect"]][:4], "rev": r}
        save(data, doc)
        return r


def live(doc):
    return [o for o in doc["objs"].values() if not o.get("deleted")]


def snapshot(data, name, auto=False):
    """Restore point of all objects + layers; keeps the 40 newest automatic ones."""
    with COND:
        doc = load(data)
        sid = stamp()
        _write(os.path.join(data, "canvas-snap", sid + ".json"), {"objs": [_public(o) for o in live(doc)], "layers": doc["layers"]})
        doc["snaps"].append({"id": sid, "name": str(name)[:80], "auto": bool(auto), "created": time.time()})
        autos = [s for s in doc["snaps"] if s["auto"]]
        for s in autos[:-40]:
            doc["snaps"].remove(s)
            try:
                os.remove(os.path.join(data, "canvas-snap", s["id"] + ".json"))
            except OSError:
                pass
        doc["rev"] += 1
        save(data, doc)
        return sid


def restore(data, sid):
    """Bring a snapshot back as a new revision (older history stays; the state before is snapshotted first)."""
    if not ID_RE.match(sid):
        raise ValueError("bad snapshot id")
    try:
        with open(os.path.join(data, "canvas-snap", sid + ".json"), encoding="utf-8") as f:
            snap = json.load(f)
    except OSError:
        raise KeyError("no such snapshot") from None
    snapshot(data, f"before restoring {sid}", auto=True)
    with COND:
        doc = load(data)
        keep = {o["id"] for o in snap["objs"]}
        gone = [i for i in doc["objs"] if i not in keep and not doc["objs"][i].get("deleted")]
    return ops(data, snap["objs"], gone, snap.get("layers", []), by="restore", force=True)


# ---------------------------------------------------------------- AI requests
def _save_png(data, url, name):
    m = re.match(r"^data:image/png;base64,", url or "")
    if not m:
        raise ValueError("image must be a PNG data URL")
    raw = base64.b64decode(url[m.end():])
    if len(raw) > 20 * 1024 * 1024:
        raise ValueError("image too large")
    p = os.path.join(data, "shots", name + ".png")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(raw)
    return p


def _inbox(data, rec):
    rec["created"] = time.time()
    _write(os.path.join(data, "inbox", rec["id"] + ".json"), rec)


def _bounds(o):
    """Cheap bounding box [x, y, w, h] for the context cut (the client has the exact one)."""
    pts = (o.get("pts") or [j["p"] for j in o.get("joints") or []] or [o.get("a"), o.get("b"), o.get("p"), o.get("q")])
    pts = [p for p in pts if p]
    if o["t"] in ("circle", "arc", "ellipse") or (not pts and o.get("c")):
        rx, ry = o.get("rx", o.get("r", 0)), o.get("ry", o.get("r", 0))
        return [o["c"][0] - rx, o["c"][1] - ry, 2 * rx, 2 * ry]
    if o["t"] in ("text",):
        return [o["x"], o["y"], len(o["s"]) * o["size"] * 0.6, o["size"] * 1.25]
    if not pts:
        return [0, 0, 0, 0]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]


def _overlap(a, b):
    return a[0] <= b[0] + b[2] and b[0] <= a[0] + a[2] and a[1] <= b[1] + b[3] and b[1] <= a[1] + a[3]


def send(data, body):
    """'Send to AI': the selection (image, objects, context by scope) as a request for Claude; returns the request id."""
    rect = [num(v) for v in body.get("rect") or []]
    text = str(body.get("text", "")).strip()[:4000]
    autonomy, context = body.get("autonomy", "propose"), body.get("context", "selection")
    if len(rect) != 4 or rect[2] <= 0 or rect[3] <= 0:
        raise ValueError("request needs rect [x, y, w, h]")
    if autonomy not in AUTONOMY or context not in CONTEXT:
        raise ValueError("bad autonomy or context")
    marks = body.get("marks") or []
    if not isinstance(marks, list) or len(marks) > 300 or not all(isinstance(m, list) and m for m in marks):
        raise ValueError("marks must be a list of point lists")
    marks = [[pt(p) for p in m[:3000]] for m in marks]
    rid = "req-" + stamp()
    png = _save_png(data, body.get("image"), rid)
    with COND:
        doc = load(data)
        objs = live(doc)
        ids = [i for i in body.get("ids") or [] if i in doc["objs"] and not doc["objs"][i].get("deleted")]
        sel = [doc["objs"][i] for i in ids]
        wide = [rect[0] - rect[2] / 2, rect[1] - rect[3] / 2, rect[2] * 2, rect[3] * 2]
        around = [o for o in objs if o["id"] not in ids and _overlap(_bounds(o), wide)][:300] if context == "around" else []
        req = {"id": rid, "instruction": text, "rect": rect, "autonomy": autonomy, "context": context, "scale": num(body.get("scale", 1)),
               "image": png, "ids": ids, "rev0": doc["rev"], "base": {o["id"]: o["rev"] for o in sel},
               "marks": marks, "objects": [_public(o) for o in sel], "neighbours": [_public(o) for o in around], "layers": doc["layers"],
               "canvasFile": _path(data), "status": "pending", "note": "", "created": time.time(), "rev": doc["rev"] + 1}
        if context == "page":
            req["page"] = {"counts": {str(n): sum(1 for o in objs if o["layer"] == n) for n in range(1, 10)},
                           "texts": [{"id": o["id"], "at": [o["x"], o["y"]], "s": o["s"][:300]} for o in objs if o["t"] == "text"][:200],
                           "outline": [{"id": o["id"], "t": o["t"], "layer": o["layer"], "bounds": _bounds(o)} for o in objs][:1500]}
        doc["rev"] += 1
        doc["reqs"][rid] = req
        save(data, doc)
    full = {**req, "briefs": []}
    _write(os.path.join(data, "canvas-req", rid + ".json"), full)
    lines = [f"{len(sel)} selected objects" + (f" ({', '.join(sorted({o['t'] for o in sel}))})" if sel else ""),
             f"autonomy: {autonomy}", f"context: {context}"] + ([f"{len(marks)} pen marks drawn on the image (in the request as marks)"] if marks else [])
    _inbox(data, {"id": rid, "kind": "canvas", "comment": text, "rect": rect, "scale": req["scale"], "screenshot": png,
                  "sketch": os.path.join(data, "canvas-req", rid + ".json"), "summary": "; ".join(lines)})
    return rid


def _req(doc, rid):
    r = doc["reqs"].get(rid)
    if not r:
        raise KeyError("no such request")
    return r


def set_status(data, rid, status, note=""):
    if status not in REQ_STATUS:
        raise ValueError("status must be one of " + ", ".join(REQ_STATUS))
    with COND:
        doc = load(data)
        r = _req(doc, rid)
        doc["rev"] += 1
        r.update(status=status, rev=doc["rev"])
        if note:
            r["note"] = str(note)[:1000]
        save(data, doc)


def briefing(data, body):
    """show_briefing: questions / warnings pinned to an object or a point. Returns the item ids."""
    rid, items = str(body.get("req", "")), body.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("items must be a non-empty list")
    with COND:
        doc = load(data)
        r = _req(doc, rid)
        new = []
        for n, it in enumerate(items):
            if not isinstance(it, dict) or not str(it.get("q", "")).strip():
                raise ValueError("each item needs q")
            a = it.get("anchor") or {}
            if a.get("obj"):
                if a["obj"] not in doc["objs"] or doc["objs"][a["obj"]].get("deleted"):
                    raise ValueError(f"anchor object {a['obj']!r} does not exist (anchor to geometry or give pt)")
                anchor = {"obj": a["obj"]}
            else:
                anchor = {"pt": pt(a.get("pt"))}
            bid = str(it.get("id") or f"{rid}-b{len(doc['briefs']) + n + 1}")
            if not ID_RE.match(bid):
                raise ValueError("bad item id")
            opts = [str(x)[:60] for x in it.get("options") or []][:6]
            new.append({"id": bid, "req": rid, "anchor": anchor, "kind": "warning" if it.get("kind") == "warning" else "question",
                        "q": str(it["q"])[:300], "options": opts, "assumption": str(it.get("assumption", ""))[:200],
                        "state": "open", "answer": "", "n": len([b for b in doc["briefs"].values() if b["req"] == rid]) + 1 + n})
        doc["rev"] += 1
        for b in new:
            doc["briefs"][b["id"]] = {**b, "rev": doc["rev"]}
        r.update(status="asking", rev=doc["rev"], summary=str(body.get("summary", ""))[:1500] or r.get("summary", ""))
        save(data, doc)
        return [b["id"] for b in new]


def answer(data, bid, text, state):
    if state not in ("open", "answered", "assumed"):
        raise ValueError("state must be open, answered or assumed")
    with COND:
        doc = load(data)
        b = doc["briefs"].get(bid)
        if not b:
            raise KeyError("no such briefing item")
        doc["rev"] += 1
        b.update(answer=str(text)[:1000], state=state, rev=doc["rev"])
        save(data, doc)


def answers_send(data, rid, extra=""):
    """The user's answers as a chat message for Claude (inbox); the request goes back to 'pending'."""
    with COND:
        doc = load(data)
        r = _req(doc, rid)
        bs = sorted((b for b in doc["briefs"].values() if b["req"] == rid), key=lambda b: b["n"])
    lines = []
    for b in bs:
        where = f"object {b['anchor']['obj']}" if "obj" in b["anchor"] else f"point {b['anchor']['pt']}"
        a = (b["answer"] + (" (accepted your assumption)" if b["state"] == "assumed" else "")) if b["state"] != "open" else \
            ("warning seen, nothing to answer" if b["kind"] == "warning" else
             f"no answer, use your assumption: {b['assumption']}" if b["assumption"] else "no answer, decide sensibly and say what you assumed")
        lines.append(f"{b['n']}) [{b['id']}] at {where}: {b['q']} -> {a}")
    sid = "ans-" + stamp()
    _inbox(data, {"id": sid, "kind": "canvas-answers", "comment": str(extra)[:2000], "summary": "\n".join(lines), "req": rid,
                  "sketch": os.path.join(data, "canvas-req", rid + ".json")})
    set_status(data, rid, "pending")
    return sid


def preview(data, body):
    """preview_changes: Claude's proposal for a request. consult -> refused; propose -> shown as a ghost for Accept / Reject;
    direct -> applied at once (snapshot first) but only inside the request's region."""
    rid = str(body.get("req", ""))
    with COND:
        doc = load(data)
        r = _req(doc, rid)
        if r["autonomy"] == "consult":
            raise ValueError("this request is consult-only: answer in the chat or ask with a briefing, do not change the canvas")
        if r["status"] in ("applied", "rejected", "closed"):
            raise ValueError(f"request is already {r['status']}")
        put = []
        for n, raw in enumerate(body.get("put") or []):
            if not isinstance(raw, dict):
                raise ValueError("put items must be objects")
            put.append(clean_obj({"id": f"ai-{rid[4:]}-{n}", "layer": 2, **raw}))
        dels = [str(i) for i in body.get("del") or []]
        for i in dels:
            if i not in doc["objs"] or doc["objs"][i].get("deleted"):
                raise ValueError(f"cannot delete unknown object {i!r}")
        if r["autonomy"] == "direct":
            x, y, w, h = r["rect"]
            inside = lambda o: x <= (_bounds(o)[0] + _bounds(o)[2] / 2) <= x + w and y <= (_bounds(o)[1] + _bounds(o)[3] / 2) <= y + h  # noqa: E731
            outside = [o["id"] for o in put if not inside(o)] + [i for i in dels if i not in r["ids"] and not inside(doc["objs"][i])]
            outside += [o["id"] for o in put if o["id"] in doc["objs"] and o["id"] not in r["ids"] and not doc["objs"][o["id"]].get("deleted") and not inside(doc["objs"][o["id"]])]
            if outside:
                raise ValueError("direct edit may only touch the selected region; outside it: " + ", ".join(outside[:8]))
        doc["rev"] += 1
        r.update(proposal={"put": put, "del": dels}, note=str(body.get("note", ""))[:1000], status="proposed", rev=doc["rev"])
        save(data, doc)
        direct = r["autonomy"] == "direct"
    if direct:
        decide(data, rid, True)
    return len(put), len(dels)


def decide(data, rid, accept, force=False, by="user"):
    """Accept (snapshot, version check, apply) or reject a proposal."""
    with COND:
        doc = load(data)
        r = _req(doc, rid)
        prop = r.get("proposal")
        if r["status"] != "proposed" or not prop:
            raise ValueError("nothing to decide: request is " + r["status"])
        if not accept:
            doc["rev"] += 1
            r.update(status="rejected", rev=doc["rev"])
            save(data, doc)
            return None
        touched = {o["id"] for o in prop["put"]} | set(prop["del"])
        bad = [i for i in touched if i in doc["objs"] and doc["objs"][i]["rev"] > r["base"].get(i, r["rev0"])]
        if bad and not force:
            raise Conflict(bad)
    sid = snapshot(data, f"before AI change {rid}", auto=True)
    ops(data, prop["put"], [i for i in prop["del"]], by="claude" if by == "user" else by, force=True)
    with COND:
        doc = load(data)
        doc["rev"] += 1
        r.update(status="applied", snap=sid, rev=doc["rev"])
        save(data, doc)
    return sid


# ---------------------------------------------------------------- reads
def changes(data, since, wait=0):
    with COND:
        if wait and load(data)["rev"] <= since:
            COND.wait_for(lambda: load(data)["rev"] != since, timeout=min(wait, 25))
        d = load(data)
        return {"v": V, "rev": d["rev"], "objs": [o for o in d["objs"].values() if o["rev"] > since and not (since == 0 and o.get("deleted"))],
                "layers": d["layers"], "regions": list(d["regions"].values()), "snaps": d["snaps"][-60:],
                "briefs": [b for b in d["briefs"].values() if b["rev"] > since],
                "reqs": [{k: v for k, v in r.items() if k not in ("layers", "objects", "neighbours", "page")} for r in d["reqs"].values() if r["rev"] > since]}


def get_object(data, oid):
    """get_object: the object plus what depends on it (dimensions that reference it, its group)."""
    with COND:
        d = load(data)
        o = d["objs"].get(oid)
        if not o or o.get("deleted"):
            raise KeyError("no such object")
        dep = [_public(x) for x in live(d) if x["id"] != oid and (x.get("ref") == oid or (o.get("g") and x.get("g") == o["g"]))]
        return {"object": _public(o), "dependents": dep}


# ---------------------------------------------------------------- canvas files (share a canvas with someone else)
FILE_FORMAT = "cad-preview-canvas"


def _dialog(save, title, initial=""):
    """Native file dialog in its own process (tkinter does not like the server's threads); '' when cancelled."""
    import subprocess
    import sys
    code = ("import sys,os,tkinter;from tkinter import filedialog as f;r=tkinter.Tk();r.withdraw();r.attributes('-topmost',True);"
            "kw=dict(parent=r,title=sys.argv[2],initialdir=os.path.expanduser('~'),filetypes=[('Plátno','*.platno.json'),('JSON','*.json'),('Vše','*.*')]);"
            "p=f.asksaveasfilename(initialfile=sys.argv[3],defaultextension='.platno.json',**kw) if sys.argv[1]=='save' else f.askopenfilename(**kw);"
            "print(p or '')")
    out = subprocess.run([sys.executable, "-c", code, "save" if save else "open", title, initial], capture_output=True, text=True,
                         encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=900)
    return out.stdout.strip()


def file_save(data, body):
    """The live canvas (objects, layers, named areas) as one .platno.json file. Returns the path, or '' when cancelled."""
    path = body.get("path") or _dialog(True, "Uložit plátno", (str(body.get("name") or "platno")) + ".platno.json")
    if not path:
        return ""
    if not path.lower().endswith(".json"):
        raise ValueError("canvas files end with .platno.json")
    with COND:
        d = load(data)
        doc = {"format": FILE_FORMAT, "v": V, "saved": time.strftime("%Y-%m-%d %H:%M:%S"), "objs": [_public(o) for o in live(d)],
               "layers": d["layers"], "regions": [{k: r[k] for k in ("id", "name", "rect")} for r in d["regions"].values()]}
    _write(os.path.abspath(path), doc)
    return os.path.abspath(path)


def file_open(data, body):
    """Open a .platno.json: replace the canvas (a restore point is made first) or add its objects next to the current ones."""
    path = body.get("path") or _dialog(False, "Otevřít plátno")
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as e:
        raise ValueError(f"cannot read {os.path.basename(path)}: {e}") from None
    if not isinstance(doc, dict) or doc.get("format") != FILE_FORMAT or not isinstance(doc.get("objs"), list):
        raise ValueError(f"{os.path.basename(path)} is not a cad-preview canvas file")
    objs = [o for o in doc["objs"] if isinstance(o, dict)]
    name = os.path.basename(path)
    snapshot(data, f"před otevřením {name}", auto=True)
    if body.get("mode") == "add":  # fresh ids so nothing collides; references and groups follow
        pre = "f" + stamp()[-9:].replace("-", "") + "-"
        nid = lambda i: (pre + str(i))[:60] if i else i  # noqa: E731
        objs = [{**o, "id": nid(o.get("id")), **({"ref": nid(o["ref"])} if o.get("ref") else {}), **({"g": nid(o["g"])} if o.get("g") else {})} for o in objs]
        return {"path": path, "objs": len(objs), "rev": ops(data, objs, by="file")}
    with COND:
        gone = [o["id"] for o in live(load(data))]
    regions = {i: None for i in load(data)["regions"]}
    regions.update({r["id"]: r for r in doc.get("regions") or [] if isinstance(r, dict) and ID_RE.match(str(r.get("id", ""))) and r.get("rect")})
    return {"path": path, "objs": len(objs), "rev": ops(data, objs, gone, doc.get("layers") or [], regions, by="file", force=True)}


def route(method, path, q, body, data):
    """-> (status, json) for /api/canvas*, or None when the path is not ours."""
    if not path.startswith("/api/canvas"):
        return None
    if not data:
        return 500, {"error": "no data dir"}
    try:
        if method == "GET":
            if path == "/api/canvas":
                return 200, changes(data, int((q.get("since") or ["0"])[0]), float((q.get("wait") or ["0"])[0]))
            if path == "/api/canvas/object":
                return 200, get_object(data, (q.get("id") or [""])[0])
            if path == "/api/canvas/req":
                with COND:
                    r = dict(_req(load(data), (q.get("id") or [""])[0]))
                    r["briefs"] = [b for b in load(data)["briefs"].values() if b["req"] == r["id"]]
                return 200, r
            return None
        if path == "/api/canvas/ops":
            return 200, {"ok": True, "rev": ops(data, body.get("put"), body.get("del"), body.get("layers"), body.get("regions"), body.get("by", ""),
                                                body.get("base"), bool(body.get("force")))}
        if path == "/api/canvas/send":
            return 200, {"ok": True, "id": send(data, body)}
        if path == "/api/canvas/briefing":
            return 200, {"ok": True, "items": briefing(data, body)}
        if path == "/api/canvas/answer":
            answer(data, str(body.get("item", "")), body.get("answer", ""), body.get("state", "answered"))
            return 200, {"ok": True}
        if path == "/api/canvas/answers/send":
            return 200, {"ok": True, "id": answers_send(data, str(body.get("req", "")), body.get("text", ""))}
        if path == "/api/canvas/preview":
            p, d = preview(data, body)
            return 200, {"ok": True, "put": p, "del": d}
        if path == "/api/canvas/decide":
            return 200, {"ok": True, "snap": decide(data, str(body.get("req", "")), bool(body.get("accept")), bool(body.get("force")))}
        if path == "/api/canvas/status":
            set_status(data, str(body.get("req", "")), body.get("status"), body.get("note", ""))
            return 200, {"ok": True}
        if path == "/api/canvas/file/save":
            return 200, {"ok": True, "path": file_save(data, body)}
        if path == "/api/canvas/file/open":
            r = file_open(data, body)
            return 200, {"ok": True, **(r or {"cancelled": True})}
        if path == "/api/canvas/snapshot":
            return 200, {"ok": True, "id": snapshot(data, body.get("name") or "manual")}
        if path == "/api/canvas/restore":
            return 200, {"ok": True, "rev": restore(data, str(body.get("id", "")))}
    except KeyError as e:
        return 404, {"error": str(e.args[0] if e.args else e)}
    except Conflict as e:
        return 409, {"error": str(e), "ids": e.ids}
    except (ValueError, TypeError, IndexError) as e:
        return 400, {"error": str(e)}
    return None


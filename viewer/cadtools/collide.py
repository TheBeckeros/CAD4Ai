"""All-pairs collision and clearance check of an assembly, on all CPU cores.

Pairs are pre-filtered by bounding boxes (grown by the clearance limit), then BRepExtrema gives the exact
minimum distance; touching / overlapping pairs get a boolean common to measure the interference volume.
Fastener-type parts (parts.json) in holes are reported separately as "expected" (threads modelled as the
nominal diameter always overlap).
"""
import os

from . import core


def _overlap(a, b, m):
    return not (a[3] + m < b[0] or b[3] + m < a[0] or a[4] + m < b[1] or b[4] + m < a[1] or
                a[5] + m < b[2] or b[5] + m < a[2])


def _pair(a, b, limit):
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    d = BRepExtrema_DistShapeShape(a.shape, b.shape)
    if not d.IsDone():
        return None
    dist = d.Value()
    if dist > limit:
        return None
    p1, p2 = d.PointOnShape1(1), d.PointOnShape2(1)
    res = {"a": a.name, "b": b.name, "dist": core.r(dist, 3), "at": core.r([(p1.X() + p2.X()) / 2,
                                                                         (p1.Y() + p2.Y()) / 2,
                                                                         (p1.Z() + p2.Z()) / 2])}
    if dist < 1e-6:
        com = BRepAlgoAPI_Common(a.shape, b.shape)
        vol = 0.0
        if com.IsDone():
            v, _, c = core.props(com.Shape())
            vol = v
            if v > 1e-6:
                res["at"] = core.r(c)
                bb = core.bbox(com.Shape())
                if bb:
                    res["depth"] = core.r(min(bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]), 3)
        res["overlap_mm3"] = core.r(vol, 3)
        res["kind"] = "COLLISION" if vol > 1e-3 else "touch"
    else:
        res["kind"] = "clearance"
    return res


_W = {}


def _init(step):
    _W["m"] = {i.name: i for i in core.load(step)}


def _job(args):
    pairs, limit = args
    m = _W["m"]
    out = []
    for a, b in pairs:
        r = _pair(m[a], m[b], limit)
        if r:
            out.append(r)
    return out


def check(step, limit=0.5, names=None):
    """limit: report clearances below this [mm]; names: only pairs involving these parts."""
    def go():
        model = core.load(step)
        sel = set(i.name for i in core.find(model, names)) if names else None
        bbs = {i.name: core.bbox(i.shape, False) for i in model}
        pairs = []
        for x in range(len(model)):
            for y in range(x + 1, len(model)):
                a, b = model[x], model[y]
                if sel and a.name not in sel and b.name not in sel:
                    continue
                if _overlap(bbs[a.name], bbs[b.name], limit):
                    pairs.append((a.name, b.name))
        found = []
        if len(pairs) > 8:
            n = max(1, min(len(pairs) // 4, (os.cpu_count() or 2) - 1))
            chunks = [pairs[i::n] for i in range(n)]
            from concurrent.futures import ProcessPoolExecutor
            with ProcessPoolExecutor(max_workers=n, initializer=_init, initargs=(step,)) as ex:
                for res in ex.map(_job, [(c, limit) for c in chunks]):
                    found += res
        else:
            m = {i.name: i for i in model}
            for a, b in pairs:
                r = _pair(m[a], m[b], limit)
                if r:
                    found.append(r)
        info = {i.name: i.type for i in model}
        coll, expected, touch, clear = [], [], [], []
        for f in sorted(found, key=lambda f: (-f.get("overlap_mm3", 0), f["dist"])):
            if f["kind"] == "COLLISION":
                (expected if "fastener" in (info[f["a"]], info[f["b"]]) else coll).append(f)
            elif f["kind"] == "touch":
                touch.append(f"{f['a']} | {f['b']}")
            else:
                clear.append(f)
        return {"ok": True, "pairs_checked": len(pairs), "parts": len(model), "collisions": coll,
                "expected_fastener_overlaps": len(expected), "fastener_overlaps": expected[:20],
                "touching_n": len(touch), "touching": touch[:30], "clearance_below_limit": clear[:30], "clearance_n": len(clear), "limit": limit}
    return core.cached(step, "collide", f"{limit}|{names}", go)

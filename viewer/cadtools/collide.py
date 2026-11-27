"""All-pairs collision and clearance check of an assembly, on all CPU cores, incremental between versions.

Pairs are pre-filtered by bounding boxes (grown by the clearance limit), then BRepExtrema gives the exact
minimum distance; touching / overlapping pairs get a boolean common to measure the interference volume.

What is NOT reported as a collision (listed apart, so nothing is hidden):
- self_overlaps: solids of one STEP part overlapping each other (a cable built from overlapping segments);
  a modelling note, not two parts fighting;
- expected contacts: cables, wires, straps, hoses (modelled crossing / clamped);
- thread engagements by the CAD4Ai convention (screw = nominal diameter, tapped hole / nut = tap drill):
  the overlap is at most the ring between the two diameters over the engaged length. A screw through
  material with no hole, or in a hole smaller than the tap drill, is a real COLLISION.
Incremental: every part gets a fingerprint (volume, area, bounding box, centre of mass). Pairs whose two
fingerprints are unchanged since the previous check of this model reuse the previous result, so after a
local edit only the pairs of the changed parts are computed.
"""
import json
import math
import os
import re

from . import core

M_SIZE = re.compile(r"(?:^|[^A-Za-z])M(\d+(?:\.\d+)?)", re.I)


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
        return False  # computed, nothing to report (cached as such)
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
                    dims = sorted([bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]])
                    res["depth"] = core.r(dims[0], 3)
                    res["len"] = core.r(dims[2], 3)
                    res["dims"] = core.r(dims, 3)
        res["overlap_mm3"] = core.r(vol, 3)
        res["kind"] = "COLLISION" if vol > 1e-3 else "touch"
    else:
        res["kind"] = "clearance"
    return res


def _thread_like(f, name):
    """Is the overlap a thread engagement by the CAD4Ai convention (external thread = nominal diameter,
    internal thread = tap-drill hole)? Then it is at most the ring between the two diameters over the
    engaged length. The length is the overlap's box dimension that is not the screw diameter."""
    from .std import THREAD
    m = M_SIZE.search(name)
    size = f"M{float(m.group(1)):g}" if m else None
    if not size or size not in THREAD or not f.get("dims"):
        return True  # size unknown: cannot judge, kept among fastener overlaps (listed, not hidden)
    d, tap = float(size[1:]), THREAD[size][1]
    dims = f["dims"]
    L = max(dims, key=lambda x: abs(x - d))  # the axial extent of the ring
    if abs(L - d) < 0.05 * d:
        L = d  # engagement about one diameter long: all box sides are ~d
    ring = math.pi / 4 * (d * d - tap * tap) * L
    f["thread"] = {"size": size, "engaged_mm": core.r(L, 2), "ring_mm3": core.r(ring, 2)}
    return f["overlap_mm3"] <= 1.15 * ring + 0.05


_W = {}


def _init(step):
    _W["m"] = {i.name: i for i in core.load(step)}


def _job(args):
    pairs, limit = args
    m = _W["m"]
    return [(a, b, _pair(m[a], m[b], limit)) for a, b in pairs]


def fingerprint(inst):
    vol, area, com = core.props(inst.shape)
    bb = core.bbox(inst.shape, False) or [0] * 6
    return "|".join(f"{x:.4f}" for x in [vol, area] + list(com) + list(bb))


def _pairs_file(step):
    return os.path.join(core.CACHE, "collide_pairs", core.model_key(step.split("@", 1)[0]) + ".json")


def check(step, limit=0.5, names=None, parallel=True):
    """limit: report clearances below this [mm]; names: only pairs involving these parts."""
    def go():
        model = core.load(step)
        sel = set(i.name for i in core.find(model, names)) if names else None
        bbs = {i.name: core.bbox(i.shape, False) for i in model}
        fps = {i.name: fingerprint(i) for i in model}
        pairs = []
        for x in range(len(model)):
            for y in range(x + 1, len(model)):
                a, b = model[x], model[y]
                if sel and a.name not in sel and b.name not in sel:
                    continue
                if _overlap(bbs[a.name], bbs[b.name], limit):
                    pairs.append((a.name, b.name))
        # previous results by fingerprint pair
        pf = _pairs_file(step)
        try:
            with open(pf, encoding="utf-8") as fh:
                prev = json.load(fh)
            prev = prev["pairs"] if prev.get("limit") == limit and prev.get("v") == core.TOOLS_VERSION else {}
        except (OSError, ValueError, KeyError):
            prev = {}
        pk = lambda a, b: "§".join(sorted((fps[a], fps[b])))  # noqa: E731
        found, todo, reused = [], [], 0
        for a, b in pairs:
            k = pk(a, b)
            if k in prev:
                reused += 1
                r = prev[k]
                if r:
                    r = dict(r)
                    # names may differ (renamed / reordered) - map by fingerprint
                    if fps[a] == r.get("fa"):
                        r["a"], r["b"] = a, b
                    else:
                        r["a"], r["b"] = b, a
                    found.append(r)
            else:
                todo.append((a, b))
        results = []
        if parallel and len(todo) > 8:
            n = max(1, min(len(todo) // 4, (os.cpu_count() or 2) - 1))
            chunks = [todo[i::n] for i in range(n)]
            from concurrent.futures import ProcessPoolExecutor
            with ProcessPoolExecutor(max_workers=n, initializer=_init, initargs=(step,)) as ex:
                for res in ex.map(_job, [(c, limit) for c in chunks]):
                    results += res
        else:
            m = {i.name: i for i in model}
            results = [(a, b, _pair(m[a], m[b], limit)) for a, b in todo]
        store = {}
        for a, b, r in results:
            if r is None:
                continue
            if r:
                r["fa"] = fps[a]
                found.append(r)
            store[pk(a, b)] = r or None
        for a, b in pairs:  # keep reused entries of this version too
            k = pk(a, b)
            if k in prev and k not in store:
                store[k] = prev[k]
        if not names:
            os.makedirs(os.path.dirname(pf), exist_ok=True)
            with open(pf, "w", encoding="utf-8") as fh:
                json.dump({"limit": limit, "v": core.TOOLS_VERSION, "pairs": store}, fh)
        byname = {i.name: i for i in model}
        coll, fast, flex, selfov, touch, clear = [], [], [], {}, [], []
        for f in sorted(found, key=lambda f: (-f.get("overlap_mm3", 0), f["dist"])):
            f.pop("fa", None)
            A, B = byname[f["a"]], byname[f["b"]]
            if f["kind"] == "COLLISION":
                if A.owner == B.owner:
                    selfov[A.owner] = selfov.get(A.owner, 0) + 1
                elif A.flexible or B.flexible:
                    flex.append(f)
                elif "fastener" in (A.type, B.type):
                    fn = A.name if A.type == "fastener" else B.name
                    other = B.name if fn == A.name else A.name
                    size_from = fn if M_SIZE.search(fn) else other
                    if _thread_like(f, size_from):
                        fast.append(f)
                    else:
                        t = f.get("thread") or {}
                        f["note"] = (f"more than a thread ring ({f['overlap_mm3']} > {t.get('ring_mm3')} mm3 for "
                                     f"{t.get('size')}): hole missing or smaller than the tap drill?")
                        coll.append(f)
                else:
                    coll.append(f)
            elif f["kind"] == "touch":
                touch.append(f"{f['a']} | {f['b']}")
            else:
                clear.append(f)
        return {"ok": True, "pairs_checked": len(pairs), "pairs_reused": reused, "parts": len(model),
                "collisions": coll,
                "expected_fastener_overlaps": len(fast), "fastener_overlaps": fast[:20],
                "expected_flexible_contacts": len(flex), "flexible_contacts": flex[:10],
                "self_overlaps": selfov,
                "touching_n": len(touch), "touching": touch[:30], "clearance_below_limit": clear[:30],
                "clearance_n": len(clear), "limit": limit}
    return core.cached(step, "collide", f"{limit}|{names}", go)

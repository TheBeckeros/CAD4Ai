"""Model digest: a compact text-like description of every part, and the diff to the previous version.

Per part: bounding box, volume, mass, centre of mass, face types, holes (diameter, axis, depth, through,
grouped into patterns: bolt circle / grid / row), shafts (outer cylinders) and the biggest planar faces.
The digest of the last version of each model is kept, so `diff` says what a rebuild changed in a few lines
instead of a screenshot.
"""
import json
import math
import os

from . import core

ANG_TOL = 1e-3


def _cyl_features(shape):
    """Cylindrical faces merged by (axis line, radius): holes (concave) and shafts (convex)."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder
    from OCP.BRepLProp import BRepLProp_SLProps
    from OCP.TopAbs import TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_VERTEX
    from OCP.BRep import BRep_Tool
    from OCP.TopoDS import TopoDS
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    feats = []
    for f in core.faces(shape):
        s = BRepAdaptor_Surface(f)
        if s.GetType() != GeomAbs_Cylinder:
            continue
        cyl = s.Cylinder()
        ax = cyl.Axis()
        d = ax.Direction()
        o = ax.Location()
        R = cyl.Radius()
        u = (s.FirstUParameter() + s.LastUParameter()) / 2
        v = (s.FirstVParameter() + s.LastVParameter()) / 2
        pr = BRepLProp_SLProps(s, u, v, 1, 1e-6)
        if not pr.IsNormalDefined():
            continue
        n = pr.Normal()
        if f.Orientation() == TopAbs_REVERSED:
            n.Reverse()
        p = pr.Value()
        # radial direction from axis to the point
        dv = (d.X(), d.Y(), d.Z())
        w = (p.X() - o.X(), p.Y() - o.Y(), p.Z() - o.Z())
        t = sum(a * b for a, b in zip(w, dv))
        rad = tuple(w[i] - t * dv[i] for i in range(3))
        concave = sum(rad[i] * (n.X(), n.Y(), n.Z())[i] for i in range(3)) < 0
        # axial extent from vertices
        ts = []
        exp = TopExp_Explorer(f, TopAbs_VERTEX)
        while exp.More():
            q = BRep_Tool.Pnt_s(TopoDS.Vertex_s(exp.Current()))
            ts.append((q.X() - o.X()) * dv[0] + (q.Y() - o.Y()) * dv[1] + (q.Z() - o.Z()) * dv[2])
            exp.Next()
        g = GProp_GProps()
        BRepGProp.SurfaceProperties_s(f, g)
        span = abs(s.LastUParameter() - s.FirstUParameter())
        if not ts:
            ts = [s.FirstVParameter(), s.LastVParameter()]
        # canonical axis: direction with positive first non-zero component, origin = foot from world origin
        c = _canon(dv)
        if c != dv:
            ts = [-x for x in ts]
            dv = c
        ox, oy, oz = o.X(), o.Y(), o.Z()
        k = ox * dv[0] + oy * dv[1] + oz * dv[2]
        foot = (ox - k * dv[0], oy - k * dv[1], oz - k * dv[2])
        ts = [x + k for x in ts]
        feats.append({"r": R, "dir": dv, "foot": foot, "t0": min(ts), "t1": max(ts), "concave": concave,
                      "ang": span, "area": g.Mass()})
    merged = []
    for fe in feats:
        for m in merged:
            if m["concave"] == fe["concave"] and abs(m["r"] - fe["r"]) < 1e-3 and \
                    sum(abs(a - b) for a, b in zip(m["dir"], fe["dir"])) < ANG_TOL * 3 and \
                    math.dist(m["foot"], fe["foot"]) < 1e-3 and fe["t0"] <= m["t1"] + 1e-3 and fe["t1"] >= m["t0"] - 1e-3:
                m["t0"], m["t1"] = min(m["t0"], fe["t0"]), max(m["t1"], fe["t1"])
                m["ang"] += fe["ang"]
                m["area"] += fe["area"]
                break
        else:
            merged.append(dict(fe))
    return merged


def _canon(d):
    for c in d:
        if abs(c) > ANG_TOL:
            return d if c > 0 else tuple(-x for x in d)
    return d


def _dir_name(d):
    names = {(1, 0, 0): "X", (0, 1, 0): "Y", (0, 0, 1): "Z", (-1, 0, 0): "-X", (0, -1, 0): "-Y", (0, 0, -1): "-Z"}
    for k, v in names.items():
        if sum(abs(a - b) for a, b in zip(d, k)) < 1e-4:
            return v
    return core.r(list(d), 3)


def _point(fe, t):
    return [fe["foot"][i] + t * fe["dir"][i] for i in range(3)]


def holes_and_shafts(shape, bb):
    feats = _cyl_features(shape)
    holes, shafts, fillets = [], [], 0
    for fe in feats:
        full = fe["ang"] > 1.9 * math.pi
        if not full:
            fillets += 1
            continue
        L = fe["t1"] - fe["t0"]
        item = {"d": core.r(2 * fe["r"], 3), "axis": _dir_name(fe["dir"]),
                "at": core.r(_point(fe, fe["t0"])), "len": core.r(L)}
        if fe["concave"]:
            # through if the hole reaches the bounding box on both sides along its axis
            item["through"] = _open_end(shape, fe, fe["t0"], -1) and _open_end(shape, fe, fe["t1"], 1)
            holes.append(item)
        else:
            shafts.append(item)
    return holes, shafts, fillets


def _open_end(shape, fe, t, sign):
    """Is the solid absent just beyond this end of the hole (on its axis)?"""
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_OUT
    # a few steps beyond the end (a chamfer or counterbore there still counts as open)
    for k in (0.05, 0.5 * fe["r"], fe["r"], 2 * fe["r"], 4 * fe["r"]):
        p = _point(fe, t + sign * k)
        if BRepClass3d_SolidClassifier(shape, gp_Pnt(*p), 1e-6).State() == TopAbs_OUT:
            return True
    return False


def _extent(bb, d):
    xs = [bb[0], bb[3]]
    ys = [bb[1], bb[4]]
    zs = [bb[2], bb[5]]
    ts = [x * d[0] + y * d[1] + z * d[2] for x in xs for y in ys for z in zs]
    return min(ts), max(ts)


def patterns(holes):
    """Group holes of one diameter and axis; describe as bolt circle, grid or row."""
    groups = {}
    for h in holes:
        groups.setdefault((h["d"], str(h["axis"])), []).append(h)
    out = []
    for (d, ax), hs in groups.items():
        pts = [h["at"] for h in hs]
        g = {"d": d, "axis": hs[0]["axis"], "n": len(hs)}
        if len(hs) >= 3:
            c = [sum(p[i] for p in pts) / len(pts) for i in range(3)]
            rads = [math.dist(p, c) for p in pts]
            if max(rads) - min(rads) < 0.02 and min(rads) > 0.1:
                g.update(kind="circle", center=core.r(c), pcd=core.r(2 * rads[0], 3))
        if len(hs) >= 2:
            ax_i = {"X": 0, "Y": 1, "Z": 2}.get(ax)
            if ax_i is not None:
                others = [i for i in range(3) if i != ax_i]
                us = sorted({round(p[others[0]], 2) for p in pts})
                vs = sorted({round(p[others[1]], 2) for p in pts})
                if len(us) * len(vs) == len(hs):
                    axn = "XYZ"
                    g.setdefault("kind", "grid" if len(us) > 1 and len(vs) > 1 else "row")
                    g["pitch"] = {axn[others[0]]: _pitch(us), axn[others[1]]: _pitch(vs)}
        if len(hs) <= 6 or "kind" not in g:
            g["at"] = [h["at"] for h in hs][:12]
        g["through"] = all(h.get("through") for h in hs)
        g["len"] = hs[0]["len"]
        out.append(g)
    return sorted(out, key=lambda g: (-g["n"], -g["d"]))


def _pitch(vals):
    if len(vals) < 2:
        return None
    steps = [round(b - a, 2) for a, b in zip(vals, vals[1:])]
    return steps[0] if len(set(steps)) == 1 else steps


def big_planes(shape, n=4):
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    from OCP.TopAbs import TopAbs_REVERSED
    out = []
    for f in core.faces(shape):
        s = BRepAdaptor_Surface(f)
        if s.GetType() != GeomAbs_Plane:
            continue
        pl = s.Plane()
        nrm = pl.Axis().Direction()
        nv = [nrm.X(), nrm.Y(), nrm.Z()]
        if f.Orientation() == TopAbs_REVERSED:
            nv = [-x for x in nv]
        g = GProp_GProps()
        BRepGProp.SurfaceProperties_s(f, g)
        c = g.CentreOfMass()
        out.append({"normal": _dir_name(tuple(round(x, 6) + 0.0 for x in nv)),
                    "area": core.r(g.Mass(), 1), "at": core.r([c.X(), c.Y(), c.Z()])})
    out.sort(key=lambda x: -x["area"])
    return out[:n]


def face_types(shape):
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    names = {0: "plane", 1: "cyl", 2: "cone", 3: "sphere", 4: "torus", 5: "bezier", 6: "bspline", 7: "revol",
             8: "extrus", 9: "offset", 10: "other"}
    cnt = {}
    for f in core.faces(shape):
        t = names.get(int(BRepAdaptor_Surface(f).GetType()), "other")
        cnt[t] = cnt.get(t, 0) + 1
    return cnt


def part_digest(inst, detail=True):
    from OCP.BRepCheck import BRepCheck_Analyzer
    bb = core.bbox(inst.shape)
    vol, area, com = core.props(inst.shape)
    dens = core.density_of(inst.material)
    d = {"name": inst.name, "size": core.r([bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]]),
         "min": core.r(bb[:3]), "max": core.r(bb[3:]), "vol": core.r(vol, 1), "area": core.r(area, 1),
         "mass_g": core.r(vol * dens / 1000, 1), "com": core.r(com)}
    if inst.type:
        d["type"] = inst.type
    if inst.material:
        d["material"] = inst.material
    if not BRepCheck_Analyzer(inst.shape).IsValid():
        d["INVALID"] = True
    if detail:
        holes, shafts, fil = holes_and_shafts(inst.shape, bb)
        d["faces"] = face_types(inst.shape)
        if holes:
            d["holes"] = patterns(holes)
        if shafts:
            d["shafts"] = sorted(shafts, key=lambda s: -s["d"])[:8]
        if fil:
            d["partial_cyl"] = fil
        d["planes"] = big_planes(inst.shape)
    return d


def _digest_worker(args):
    step, names, detail = args
    model = core.load(step)
    sel = [i for i in model if i.name in set(names)]
    return [part_digest(i, detail) for i in sel]


def _incremental(step, model, detail):
    """Per-part digests; a part whose fingerprint (volume, area, centre, box) is unchanged since the
    previous version of this model is copied from there instead of measured again."""
    from . import collide
    pf = os.path.join(core.CACHE, "digest_parts", core.model_key(step.split("@", 1)[0]) + f"_{int(detail)}.json")
    try:
        with open(pf, encoding="utf-8") as f:
            old = json.load(f)
        old = old["parts"] if old.get("v") == core.TOOLS_VERSION else {}
    except (OSError, ValueError, KeyError):
        old = {}
    new, parts = {}, []
    for i in model:
        fp = collide.fingerprint(i) + "|" + i.name + "|" + str(i.info)
        p = old.get(fp) or part_digest(i, detail)
        new[fp] = p
        parts.append(p)
    os.makedirs(os.path.dirname(pf), exist_ok=True)
    with open(pf, "w", encoding="utf-8") as f:
        json.dump({"v": core.TOOLS_VERSION, "parts": new}, f, ensure_ascii=False)
    return parts


def digest(step, detail=True, parallel=False):
    def go():
        model = core.load(step)
        names = [i.name for i in model]
        # identical parts (same shape key) computed once, moved copies only re-placed
        if parallel and len(model) > 6:
            chunks = [names[i::max(1, min(len(names), (os.cpu_count() or 2) - 1))]
                      for i in range(max(1, min(len(names), (os.cpu_count() or 2) - 1)))]
            with core.pool(len(chunks)) as ex:
                parts = [p for res in ex.map(_digest_worker, [(step, c, detail) for c in chunks]) for p in res]
            order = {n: i for i, n in enumerate(names)}
            parts.sort(key=lambda p: order[p["name"]])
        else:
            parts = _incremental(step, model, detail)
        allbb = [min(p["min"][0] for p in parts), min(p["min"][1] for p in parts), min(p["min"][2] for p in parts),
                 max(p["max"][0] for p in parts), max(p["max"][1] for p in parts), max(p["max"][2] for p in parts)]
        return {"ok": True, "model": os.path.basename(step), "parts_n": len(parts),
                "size": core.r([allbb[3] - allbb[0], allbb[4] - allbb[1], allbb[5] - allbb[2]]),
                "mass_g": core.r(sum(p["mass_g"] for p in parts), 1),
                "invalid": [p["name"] for p in parts if p.get("INVALID")], "parts": parts}
    return core.cached(step, "digest", str(detail), go)


# ---------------------------------------------------------------- diff

def _last_file(step):
    return os.path.join(core.CACHE, "last", core.model_key(step.split("@", 1)[0]) + ".json")


def remember(step, dg):
    """Keep the digest of this version; the one it replaces becomes "prev" (what diff compares to)."""
    p = _last_file(step)
    key, prev = core.file_key(step), None
    try:
        with open(p, encoding="utf-8") as f:
            old = json.load(f)
        prev = old.get("prev") if old.get("key") == key else old.get("digest")
    except (OSError, ValueError):
        pass
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"key": key, "digest": dg, "prev": prev}, f, ensure_ascii=False)


def previous(step):
    try:
        with open(_last_file(step), encoding="utf-8") as f:
            d = json.load(f)
        return d.get("prev") if d.get("key") == core.file_key(step) else d.get("digest")
    except (OSError, ValueError, KeyError):
        return None


def diff(old, new, tol=0.01):
    """Human-readable lines: added/removed parts, changed size/mass/holes/position."""
    if not old:
        return ["(no previous version to compare)"]
    lines = []
    o = {p["name"]: p for p in old["parts"]}
    n = {p["name"]: p for p in new["parts"]}
    for k in n.keys() - o.keys():
        p = n[k]
        lines.append(f"+ {k}: new part {p['size']} mm, {p['mass_g']} g")
    for k in o.keys() - n.keys():
        lines.append(f"- {k}: removed")
    for k in n.keys() & o.keys():
        a, b = o[k], n[k]
        ch = []
        if any(abs(x - y) > tol for x, y in zip(a["size"], b["size"])):
            ch.append(f"size {a['size']}→{b['size']}")
        mv = [round(y - x, 2) for x, y in zip(a["min"], b["min"])]
        if any(abs(x) > tol for x in mv) and not ch:
            ch.append(f"moved {mv}")
        elif any(abs(x) > tol for x in mv):
            ch.append(f"min corner {a['min']}→{b['min']}")
        if abs(a["vol"] - b["vol"]) > max(0.5, 1e-4 * a["vol"]):
            ch.append(f"mass {a['mass_g']}→{b['mass_g']} g")
        ha, hb = _hole_sig(a), _hole_sig(b)
        for s in hb - ha:
            ch.append(f"holes + {s}")
        for s in ha - hb:
            ch.append(f"holes - {s}")
        if b.get("INVALID") and not a.get("INVALID"):
            ch.append("NOW INVALID B-rep")
        if ch:
            lines.append(f"~ {k}: " + "; ".join(ch))
    if not lines:
        lines.append("no geometric change")
    return lines


def _hole_sig(p):
    out = set()
    for g in p.get("holes", []):
        s = f"{g['n']}x Ø{g['d']} {g['axis']}"
        if g.get("kind") == "circle":
            s += f" PCD{g['pcd']} @{g['center']}"
        elif g.get("pitch"):
            s += f" pitch {g['pitch']}"
        if g.get("at") and g["n"] <= 4:
            s += f" @{g['at']}"
        out.add(s)
    return out


def summary_text(dg, max_parts=40):
    """Very short text version of a digest."""
    L = [f"{dg['model']}: {dg['parts_n']} parts, {dg['size']} mm, {dg['mass_g']} g"]
    if dg["invalid"]:
        L.append("INVALID B-rep: " + ", ".join(dg["invalid"]))
    for p in dg["parts"][:max_parts]:
        h = "; ".join(sorted(_hole_sig(p)))
        L.append(f"- {p['name']}: {p['size']} @{p['min']} {p['mass_g']}g" + (f" | holes {h}" if h else ""))
    if dg["parts_n"] > max_parts:
        L.append(f"... {dg['parts_n'] - max_parts} more parts")
    return L

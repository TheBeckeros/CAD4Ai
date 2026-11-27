"""Manufacturability checks of one part: wall thickness map, 3D-print overhangs, draft, small radii and holes.

Wall thickness: from many surface samples a ray is cast inwards (opposite the outward normal) and the
first hit on the other side is the local thickness (numpy ray/triangle test against all triangles in
blocks; heavy but exact enough). Thin spots are clustered and reported with their location.
"""
import math

import numpy as np

from . import core


def surface_samples(shape, samples):
    """Exact points and outward normals on the B-rep faces, area-weighted (random UV, kept if on the face)."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepLProp import BRepLProp_SLProps
    from OCP.BRepTopAdaptor import BRepTopAdaptor_FClass2d
    from OCP.BRepTools import BRepTools
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    from OCP.TopAbs import TopAbs_REVERSED, TopAbs_IN
    from OCP.gp import gp_Pnt2d
    fs = list(core.faces(shape))
    areas = []
    for f in fs:
        g = GProp_GProps()
        BRepGProp.SurfaceProperties_s(f, g)
        areas.append(max(g.Mass(), 0))
    areas = np.array(areas)
    rng = np.random.default_rng(0)
    counts = rng.multinomial(samples, areas / areas.sum())
    P, N = [], []
    for f, k in zip(fs, counts):
        if not k:
            continue
        s = BRepAdaptor_Surface(f)
        u0, u1, v0, v1 = BRepTools.UVBounds_s(f)
        cls = BRepTopAdaptor_FClass2d(f, 1e-7)
        rev = f.Orientation() == TopAbs_REVERSED
        got, tries = 0, 0
        while got < k and tries < 20 * k + 50:
            tries += 1
            u, v = u0 + (u1 - u0) * rng.random(), v0 + (v1 - v0) * rng.random()
            if cls.Perform(gp_Pnt2d(u, v)) != TopAbs_IN:
                continue
            pr = BRepLProp_SLProps(s, u, v, 1, 1e-7)
            if not pr.IsNormalDefined():
                continue
            q, n = pr.Value(), pr.Normal()
            sg = -1 if rev else 1
            P.append((q.X(), q.Y(), q.Z()))
            N.append((sg * n.X(), sg * n.Y(), sg * n.Z()))
            got += 1
    return np.array(P), np.array(N)


def thickness(shape, samples=6000):
    """Exact B-rep ray from each surface sample inwards (OpenCascade IntCurvesFace_ShapeIntersector)."""
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
    from OCP.gp import gp_Lin, gp_Pnt, gp_Dir
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepLProp import BRepLProp_SLProps
    P, N = surface_samples(shape, samples)
    isec = IntCurvesFace_ShapeIntersector()
    isec.Load(shape, 1e-7)
    t = np.full(len(P), np.inf)
    eps = 1e-4
    for i in range(len(P)):
        isec.Perform(gp_Lin(gp_Pnt(*P[i]), gp_Dir(*(-N[i]))), eps, 1e9)
        if isec.IsDone() and isec.NbPnt():
            hits = sorted((isec.WParameter(k), k) for k in range(1, isec.NbPnt() + 1))
            for w, k in hits:
                if w <= 2e-3:
                    continue
                # a grazing hit (wall nearly parallel to the ray) is an edge artefact, not a wall
                s = BRepAdaptor_Surface(isec.Face(k))
                pr = BRepLProp_SLProps(s, isec.UParameter(k), isec.VParameter(k), 1, 1e-7)
                if pr.IsNormalDefined():
                    nn = pr.Normal()
                    if abs(nn.X() * N[i][0] + nn.Y() * N[i][1] + nn.Z() * N[i][2]) < 0.35:
                        continue
                t[i] = w
                break
    good = np.isfinite(t)
    return P[good], t[good], N[good]


def _clusters(P, t, limit, rad):
    idx = np.nonzero(t < limit)[0]
    idx = idx[np.argsort(t[idx])]
    out, used = [], np.zeros(len(P), bool)
    for i in idx:
        if used[i]:
            continue
        near = np.linalg.norm(P - P[i], axis=1) < rad
        sel = near & (t < limit)
        used |= sel
        if sel.sum() < 2:  # a lone sample is noise
            continue
        out.append({"t_min": core.r(float(t[i]), 2), "at": core.r(P[i].tolist()), "samples": int(sel.sum())})
        if len(out) >= 12:
            break
    return out


def overhangs(shape, up=(0, 0, 1), angle=45):
    """Downward faces steeper than `angle` from vertical (need support), area and where."""
    V, T = core.mesh(shape)
    tri = V[T]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    a2 = np.linalg.norm(n, axis=1)
    ok = a2 > 1e-12
    tri, n, area = tri[ok], n[ok] / a2[ok, None], a2[ok] / 2
    up = np.asarray(up, float) / np.linalg.norm(up)
    c = tri.mean(axis=1)
    zmin = (V @ up).min()
    down = -(n @ up)
    need = (down > math.cos(math.radians(angle))) & ((c @ up) > zmin + 0.2)
    bed = (down > 0.999) & ((c @ up) <= zmin + 0.2)
    regions = []
    if need.any():
        cc = c[need]
        for k in np.argsort(-area[need])[:5]:
            regions.append(core.r(cc[k].tolist()))
    return {"up": up.tolist(), "support_area_mm2": core.r(float(area[need].sum()), 1),
            "bed_contact_mm2": core.r(float(area[bed].sum()), 1), "worst_at": regions}


def draft(shape, pull=(0, 0, 1), min_deg=1.0):
    """Faces nearly parallel to the pull direction (no draft) - for moulding/casting."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepLProp import BRepLProp_SLProps
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    pull = np.asarray(pull, float) / np.linalg.norm(pull)
    zero, area = [], 0.0
    for f in core.faces(shape):
        s = BRepAdaptor_Surface(f)
        u = (s.FirstUParameter() + s.LastUParameter()) / 2
        v = (s.FirstVParameter() + s.LastVParameter()) / 2
        pr = BRepLProp_SLProps(s, u, v, 1, 1e-6)
        if not pr.IsNormalDefined():
            continue
        nn = pr.Normal()
        ang = math.degrees(math.asin(min(1, abs(nn.X() * pull[0] + nn.Y() * pull[1] + nn.Z() * pull[2]))))
        if ang < min_deg:
            g = GProp_GProps()
            BRepGProp.SurfaceProperties_s(f, g)
            c = g.CentreOfMass()
            area += g.Mass()
            zero.append({"deg": core.r(ang, 2), "area": core.r(g.Mass(), 1), "at": core.r([c.X(), c.Y(), c.Z()])})
    zero.sort(key=lambda x: -x["area"])
    return {"pull": pull.tolist(), "no_draft_area_mm2": core.r(area, 1), "faces": zero[:10], "faces_n": len(zero)}


def radii(shape):
    """Smallest concave (inner) radii - end-mill size - and smallest holes."""
    from . import digest
    feats = digest._cyl_features(shape)
    inner = sorted({round(f["r"], 3) for f in feats if f["concave"] and f["ang"] < 1.9 * math.pi})
    holes = sorted({round(2 * f["r"], 3) for f in feats if f["concave"] and f["ang"] >= 1.9 * math.pi})
    deep = [{"d": core.r(2 * f["r"], 3), "depth": core.r(f["t1"] - f["t0"], 2), "ratio": core.r((f["t1"] - f["t0"]) / (2 * f["r"]), 1)}
            for f in feats if f["concave"] and f["ang"] >= 1.9 * math.pi and (f["t1"] - f["t0"]) > 6 * 2 * f["r"]]
    return {"inner_radii": inner[:8], "min_inner_radius": inner[0] if inner else None,
            "hole_diameters": holes[:12], "deep_holes_over_6xD": deep[:8]}


def analyse(step, part, process="print", min_wall=None, up=(0, 0, 1), samples=6000):
    """process: print | mill | mould. min_wall default: print 1.2, mill 0.8, mould 1.0 mm."""
    def go():
        inst = core.find(core.load(step), [part])[0]
        lim = min_wall or {"print": 1.2, "mill": 0.8, "mould": 1.0}.get(process, 1.0)
        P, t, _ = thickness(inst.shape, samples)
        bb = core.bbox(inst.shape)
        res = {"ok": True, "part": inst.name, "process": process, "min_wall_limit": lim,
               "wall": {"min": core.r(float(t.min()), 2) if len(t) else None,
                        "p5": core.r(float(np.percentile(t, 5)), 2) if len(t) else None,
                        "median": core.r(float(np.median(t)), 2) if len(t) else None, "samples": int(len(t)),
                        "thin_spots": _clusters(P, t, lim, 0.05 * max(bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]))},
               "radii": radii(inst.shape)}
        if process == "print":
            res["overhang"] = overhangs(inst.shape, up)
        if process == "mould":
            res["draft"] = draft(inst.shape, up)
        if process == "mill":
            mr = res["radii"]["min_inner_radius"]
            res["mill_note"] = (f"smallest inner radius {mr} mm -> end mill Ø{core.r(2 * mr, 2)} or smaller" if mr
                                else "no inner fillets: sharp inner corners cannot be milled (add radius ≥ tool/2)")
        return res
    return core.cached(step, "dfm", f"{part}|{process}|{min_wall}|{up}|{samples}", go)

"""Measurements Claude would otherwise script by hand: distance between parts, cross-section, mass table."""
import math
import os

from . import core


def distance(step, a, b):
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    m = core.load(step)
    A, B = core.find(m, [a])[0], core.find(m, [b])[0]
    d = BRepExtrema_DistShapeShape(A.shape, B.shape)
    p1, p2 = d.PointOnShape1(1), d.PointOnShape2(1)
    ca, cb = core.props(A.shape)[2], core.props(B.shape)[2]
    return {"ok": True, "a": A.name, "b": B.name, "min_dist": core.r(d.Value(), 4),
            "pa": core.r([p1.X(), p1.Y(), p1.Z()], 3), "pb": core.r([p2.X(), p2.Y(), p2.Z()], 3),
            "com_dist": core.r(math.dist(ca, cb), 3), "com_delta": core.r([y - x for x, y in zip(ca, cb)], 3)}


def _plane(spec):
    """'Z=20' | 'X=0' | 'p=x,y,z n=nx,ny,nz'."""
    from OCP.gp import gp_Pln, gp_Pnt, gp_Dir
    s = spec.replace(" ", "")
    if s[:1].upper() in "XYZ" and "=" in s and not s.startswith("p="):
        ax, v = s[0].upper(), float(s.split("=")[1])
        n = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}[ax]
        p = tuple(v * c for c in n)
    else:
        kv = dict(x.split("=") for x in spec.split())
        p = tuple(map(float, kv["p"].split(",")))
        n = tuple(map(float, kv["n"].split(",")))
    return gp_Pln(gp_Pnt(*p), gp_Dir(*n)), p, n


def section(step, spec, names=None, svg=True):
    """Cut parts by a plane: per part the section area, its bounds and loop count; optional SVG drawing."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_QuasiUniformDeflection
    from OCP.TopoDS import TopoDS
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    import numpy as np

    m = core.load(step)
    pln, p0, n = _plane(spec)
    n = np.array(n, float) / np.linalg.norm(n)
    # 2D frame on the plane
    u = np.cross(n, [0, 0, 1] if abs(n[2]) < 0.9 else [1, 0, 0])
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    big = BRepBuilderAPI_MakeFace(pln, -1e5, 1e5, -1e5, 1e5).Face()
    out, polys = [], []
    for inst in core.find(m, names):
        sec = BRepAlgoAPI_Section(inst.shape, big)
        sec.Build()
        if not sec.IsDone():
            continue
        shp = sec.Shape()
        segs = []
        exp = TopExp_Explorer(shp, TopAbs_EDGE)
        while exp.More():
            c = BRepAdaptor_Curve(TopoDS.Edge_s(exp.Current()))
            disc = GCPnts_QuasiUniformDeflection(c, 0.02)
            pts = []
            if disc.IsDone():
                for k in range(1, disc.NbPoints() + 1):
                    q = disc.Value(k)
                    w = np.array([q.X(), q.Y(), q.Z()]) - p0
                    pts.append((float(w @ u), float(w @ v)))
            segs.append(pts)
            exp.Next()
        if not segs:
            continue
        # area: the part of the (huge) plane face that lies inside the solid
        from OCP.GProp import GProp_GProps
        from OCP.BRepGProp import BRepGProp
        g = GProp_GProps()
        BRepGProp.SurfaceProperties_s(BRepAlgoAPI_Common(inst.shape, big).Shape(), g)
        area = g.Mass()
        allp = [q for s in segs for q in s]
        us, vs = [q[0] for q in allp], [q[1] for q in allp]
        out.append({"part": inst.name, "area": core.r(area, 1), "edges": len(segs),
                    "u": core.r([min(us), max(us)]), "v": core.r([min(vs), max(vs)])})
        polys.append((inst.name, segs))
    res = {"ok": True, "plane": spec, "u_dir": core.r(list(u), 3), "v_dir": core.r(list(v), 3), "parts": out}
    if svg and polys:
        res["svg"] = _svg(step, spec, polys)
    return res


def _svg(step, spec, polys):
    allp = [q for _, segs in polys for s in segs for q in s]
    x0, x1 = min(q[0] for q in allp), max(q[0] for q in allp)
    y0, y1 = min(q[1] for q in allp), max(q[1] for q in allp)
    w, h = max(x1 - x0, 1e-3), max(y1 - y0, 1e-3)
    sc = 800 / max(w, h)
    pal = ["#c0392b", "#2471a3", "#239b56", "#b9770e", "#7d3c98", "#17a589", "#566573"]
    L = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-20 -20 {w * sc + 40:.0f} {h * sc + 60:.0f}" '
         f'style="background:#fff"><text x="0" y="-5" font-size="14">{spec}  ({w:.1f} x {h:.1f} mm)</text>']
    for k, (nm, segs) in enumerate(polys):
        c = pal[k % len(pal)]
        for s in segs:
            d = " ".join(f"{(q[0] - x0) * sc:.1f},{(y1 - q[1]) * sc:.1f}" for q in s)
            L.append(f'<polyline points="{d}" fill="none" stroke="{c}" stroke-width="1.5"/>')
        q = segs[0][0] if segs and segs[0] else (x0, y0)
        L.append(f'<text x="{(q[0] - x0) * sc:.0f}" y="{(y1 - q[1]) * sc:.0f}" font-size="11" fill="{c}">{nm}</text>')
    L.append("</svg>")
    p = os.path.join(core.out_dir(step, "section"), spec.replace("=", "_").replace(" ", "_").replace(",", "_") + ".svg")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return p


def mass_table(step):
    m = core.load(step)
    rows, tot = [], 0.0
    for i in m:
        vol, _, com = core.props(i.shape)
        dens = core.density_of(i.material)
        g = vol * dens / 1000
        tot += g
        rows.append({"part": i.name, "mass_g": core.r(g, 1), "density": dens, "material": i.material or "(steel default)"})
    rows.sort(key=lambda x: -x["mass_g"])
    return {"ok": True, "total_g": core.r(tot, 1), "parts": rows}

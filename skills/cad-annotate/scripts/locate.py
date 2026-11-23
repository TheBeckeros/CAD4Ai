"""Determine which B-rep features (faces, edges, vertices) a cad-preview note points at.

Usage:
    python locate.py --step model.step --annotation <path to annotation JSON>
    python locate.py --step model.step --points "x,y,z;x,y,z;..."

The cad-preview viewer stores annotation JSON in <project>/.cad-preview/inbox/.
For every selected feature it prints the exact matching B-rep entity. For every
pen stroke it prints which faces the drawing crosses, which edges and vertices
are near it or inside its loop, and the most likely target.
"""
import argparse
import json
import math
import sys

import cadquery as cq


def fmt(v):
    return "[" + ", ".join(f"{c:.2f}".rstrip("0").rstrip(".") if abs(c) > 1e-9 else "0" for c in v) + "]"


def vec(v):
    return (v.x, v.y, v.z)


def face_info(i, f):
    kind = f.geomType()
    c = f.Center()
    text = f"face #{i} {kind}"
    if kind == "PLANE":
        n = f.normalAt(c)
        text += f", normal {fmt(vec(n))}, center {fmt(vec(c))}"
    elif kind in ("CYLINDER", "CONE"):
        text += f", center {fmt(vec(c))}"
        try:
            text += f", radius {f._geomAdaptor().Cylinder().Radius():.3f}"
        except Exception:  # noqa: BLE001
            pass
    else:
        text += f", center {fmt(vec(c))}"
    return text + f", area {f.Area():.1f} mm2"


def edge_info(i, e):
    a, b = e.startPoint(), e.endPoint()
    return f"edge #{i} {e.geomType()} {fmt(vec(a))} -> {fmt(vec(b))}, length {e.Length():.2f}"


def analyze(solid, strokes, view_dir=None):
    faces = solid.Faces()
    edges = solid.Edges()
    verts = solid.Vertices()
    bb = solid.BoundingBox()
    diag = math.dist((bb.xmin, bb.ymin, bb.zmin), (bb.xmax, bb.ymax, bb.zmax))
    on_tol = max(0.02, diag * 0.002)   # point lies on a face
    near_tol = max(0.5, diag * 0.06)   # edge/vertex is "near the drawing"

    out = []
    for si, pts in enumerate(strokes, 1):
        out.append(f"\nStroke {si}: {len(pts)} points")
        if not pts:
            continue
        pv = [cq.Vertex.makeVertex(*p) for p in pts]
        touched = {}
        for v in pv:
            best = min(range(len(faces)), key=lambda k: faces[k].distance(v))
            if faces[best].distance(v) <= on_tol * 5:
                touched[best] = touched.get(best, 0) + 1
        near_edges = {}
        for k, e in enumerate(edges):
            d = min(e.distance(v) for v in pv)
            if d <= near_tol:
                near_edges[k] = d
        near_verts = {}
        for k, vx in enumerate(verts):
            d = min(vx.distance(v) for v in pv)
            if d <= near_tol * 1.5:
                near_verts[k] = d

        centroid = tuple(sum(p[a] for p in pts) / len(pts) for a in range(3))
        span = max(math.dist(centroid, p) for p in pts)
        # loop: the end returns to the start or to one of the first points (overlapping stroke)
        head = pts[: max(2, len(pts) // 3)]
        path_len = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
        closed = len(pts) > 6 and (
            math.dist(pts[0], pts[-1]) < 0.2 * path_len
            or min(math.dist(pts[-1], p) for p in head) < max(0.35 * span, on_tol * 10)
        )
        out.append(f"  shape: {'closed loop' if closed else 'open line'}, centroid {fmt(centroid)}, extent radius {span:.2f} mm")

        out.append("  faces drawn on:")
        for k, n in sorted(touched.items(), key=lambda t: -t[1]):
            out.append(f"    - {face_info(k, faces[k])} ({n} points)")

        # vertices whose adjacent faces were all drawn on = a circled corner
        cand_v = []
        for k, vx in enumerate(verts):
            adj = [fi for fi, f in enumerate(faces) if f.distance(vx) < 1e-6]
            hit = [fi for fi in adj if fi in touched]
            if len(hit) >= 2 and len(hit) == len(adj) and math.dist(vec(vx.Center()), centroid) <= span * 1.3:
                cand_v.append((math.dist(vec(vx.Center()), centroid), k, len(adj)))
        cand_e = []
        for k, e in enumerate(edges):
            mid = cq.Vertex.makeVertex(*vec(e.positionAt(0.5)))
            adj = [fi for fi, f in enumerate(faces) if f.distance(mid) < 1e-6]
            if len(adj) == 2 and all(fi in touched for fi in adj) and k in near_edges:
                cand_e.append((near_edges[k], k))

        if near_verts:
            out.append("  vertices near the drawing:")
            for k, d in sorted(near_verts.items(), key=lambda t: t[1])[:3]:
                out.append(f"    - vertex #{k} {fmt(vec(verts[k].Center()))} (distance {d:.2f} mm)")
        if near_edges:
            out.append("  edges near the drawing:")
            for k, d in sorted(near_edges.items(), key=lambda t: t[1])[:3]:
                out.append(f"    - {edge_info(k, edges[k])} (distance {d:.2f} mm)")

        # what the loop encircles: projection onto the plane normal to the view direction
        inside_v = []
        if closed:
            d = view_dir or tuple(-c for c in centroid)
            dl = math.sqrt(sum(c * c for c in d)) or 1.0
            d = tuple(c / dl for c in d)
            ref = (1, 0, 0) if abs(d[0]) < 0.9 else (0, 1, 0)
            u = (d[1] * ref[2] - d[2] * ref[1], d[2] * ref[0] - d[0] * ref[2], d[0] * ref[1] - d[1] * ref[0])
            ul = math.sqrt(sum(c * c for c in u))
            u = tuple(c / ul for c in u)
            w = (d[1] * u[2] - d[2] * u[1], d[2] * u[0] - d[0] * u[2], d[0] * u[1] - d[1] * u[0])
            proj = lambda p: (sum(p[i] * u[i] for i in range(3)), sum(p[i] * w[i] for i in range(3)))  # noqa: E731
            poly = [proj(p) for p in pts]

            def inside(q):
                x, y = q
                hit = False
                for i in range(len(poly)):
                    (x1, y1), (x2, y2) = poly[i], poly[i - 1]
                    if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                        hit = not hit
                return hit

            for k, vx in enumerate(verts):
                p = vec(vx.Center())
                if math.dist(p, centroid) <= span * 1.5 and inside(proj(p)):
                    inside_v.append(k)

        if closed and inside_v:
            pos = [vec(verts[k].Center()) for k in inside_v]
            if len(inside_v) == 1:
                target = f"VERTEX #{inside_v[0]} {fmt(pos[0])} (encircled by the loop)"
            else:
                inner_e = [k for k, e in enumerate(edges)
                           if any(math.dist(vec(e.startPoint()), p) < 1e-6 for p in pos)
                           and any(math.dist(vec(e.endPoint()), p) < 1e-6 for p in pos)]
                c = tuple(sum(p[a] for p in pos) / len(pos) for a in range(3))
                target = (f"CORNER / REGION with {len(inside_v)} vertices around {fmt(c)} "
                          f"(vertices {', '.join(fmt(p) for p in pos)}; edges inside: "
                          f"{', '.join('#' + str(k) for k in inner_e) or 'none'})")
        elif closed and cand_v:
            _, k, n = min(cand_v)
            target = f"VERTEX #{k} {fmt(vec(verts[k].Center()))} (the loop wraps all {n} of its faces)"
        elif len(touched) == 1 and closed:
            k = next(iter(touched))
            target = f"FACE #{k} (loop inside a single face: a spot on the face around {fmt(centroid)})"
        elif cand_e:
            _, k = min(cand_e)
            target = f"EDGE #{k} ({edge_info(k, edges[k])}): the line crosses it or runs along it"
        elif cand_v:
            _, k, _ = min(cand_v)
            target = f"VERTEX #{k} {fmt(vec(verts[k].Center()))}"
        elif touched:
            k = max(touched, key=touched.get)
            target = f"FACE #{k} around {fmt(centroid)}"
        else:
            target = "nothing: the points are not on the model (did the model change since the drawing?)"
        out.append(f"  => most likely target: {target}")
    return "\n".join(out)


def match_feature(solids, f):
    """Feature selected in the viewer -> exact B-rep entity (matched by coordinates, not index)."""
    pts = []
    for key in ("points", "samples"):
        pts += [tuple(p) for p in f.get(key) or []]
    if f.get("point"):
        pts.append(tuple(f["point"]))
    if not pts and f.get("centroid"):  # the centroid of a curved face is not on the face; fallback only
        pts.append(tuple(f["centroid"]))
    if not pts:
        return "  (feature without coordinates)"
    pv = [cq.Vertex.makeVertex(*p) for p in pts]
    best = None
    for si, solid in enumerate(solids):
        if f["type"] == "vertex":
            pool = [("vertex", k, v) for k, v in enumerate(solid.Vertices())]
        elif f["type"] == "edge":
            pool = [("edge", k, e) for k, e in enumerate(solid.Edges())]
        elif f["type"] == "part":
            pool = [("solid", si, solid)]
        else:
            pool = [("face", k, fc) for k, fc in enumerate(solid.Faces())]
        for kind, k, shp in pool:
            d = sum(shp.distance(v) for v in pv) / len(pv)
            if best is None or d < best[0]:
                best = (d, si, kind, k, shp)
    d, si, kind, k, shp = best
    if kind == "face":
        desc = face_info(k, shp)
    elif kind == "edge":
        desc = edge_info(k, shp)
    elif kind == "vertex":
        desc = f"vertex #{k} {fmt(vec(shp.Center()))}"
    else:
        bb = shp.BoundingBox()
        desc = f"solid #{si}, {bb.xlen:.2f} x {bb.ylen:.2f} x {bb.zlen:.2f} mm, volume {shp.Volume():.1f} mm3"
    ok = "exact" if d < 0.15 else f"deviation {d:.3f} mm (did the model change?)"
    return f"  => solid #{si}: {desc} [{ok}]"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", required=True)
    ap.add_argument("--annotation")
    ap.add_argument("--points")
    a = ap.parse_args()

    shape = cq.importers.importStep(a.step)
    solids = sorted(shape.solids().vals(), key=lambda s: -s.Volume())

    features = []
    if a.annotation:
        with open(a.annotation, encoding="utf-8") as f:
            data = json.load(f)
        strokes = [[tuple(p) for p in s["points"]] for s in data.get("strokes", [])]
        features = data.get("features") or []
        view_dir = tuple((data.get("camera") or {}).get("viewDir") or ()) or None
        # comment, dimensions and section are already in the chat note, not repeated here
    elif a.points:
        view_dir = None
        strokes = [[tuple(float(c) for c in p.split(",")) for p in a.points.split(";") if p.strip()]]
    else:
        ap.error("pass --annotation or --points")

    if len(solids) > 1:
        print(f"{len(solids)} solids")
    for f in features:
        print(f"\nSelected feature {f.get('index')}: {f.get('title')} ({f.get('description')})")
        print(match_feature(solids, f))
    if not strokes and not features:
        print("The note has no drawing or selection: it applies to the whole model.")
        return
    for si, pts in enumerate(strokes, 1):
        # the solid the stroke lies on
        pv = [cq.Vertex.makeVertex(*p) for p in pts[:: max(1, len(pts) // 10)]]
        solid = min(solids, key=lambda s: sum(s.distance(v) for v in pv))
        text = analyze(solid, [pts], view_dir).replace("\nStroke 1:", f"\nStroke {si} (solid #{solids.index(solid)}):")
        print(text)


if __name__ == "__main__":
    main()

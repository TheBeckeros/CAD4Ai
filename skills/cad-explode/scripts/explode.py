"""Disassembly analysis for <model>.explode.json (CAD4Ai exploded view).

  explode.py info <model.step>
      parts (names as the viewer shows them) with bounding boxes, volumes and cylinder axes
  explode.py plan <model.step> [--out <model>.explode.json] [--base <part>] [--dirs x,y,z;...]
      finds a disassembly sequence: repeatedly removes a part that can slide out without
      hitting the parts still in place, along ±X/±Y/±Z or its own cylinder axes.
      Parts that cannot come out in any direction are reported as LOCKED.

Collision test: the part is moved in steps of 1/4 of its smallest size (so no wall is skipped)
and intersected with the remaining parts (B-rep boolean). Overlap that exists already in the
assembled state (press fit, modelled interference) is subtracted, so it does not block.
"""
import argparse
import json
import math
import sys

sys.dont_write_bytecode = True  # no __pycache__ inside the app folder


def load_parts(step):
    """[(name, cq.Shape)] in the STEP's assembly order, with locations applied (XCAF)."""
    import cadquery as cq
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDF import TDF_LabelSequence
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.XCAFDoc import XCAFDoc_DocumentTool

    doc = TDocStd_Document(TCollection_ExtendedString("doc"))
    rd = STEPCAFControl_Reader()
    rd.SetNameMode(True)
    if rd.ReadFile(step) != IFSelect_RetDone or not rd.Transfer(doc):
        raise RuntimeError("cannot read " + step)
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())

    def name_of(label):
        attr = TDataStd_Name()
        return attr.Get().ToExtString() if label.FindAttribute(TDataStd_Name.GetID_s(), attr) else ""

    out = []

    def walk(label, loc, inherited):
        nm = name_of(label) or inherited
        if st.IsReference_s(label):
            ref = label.__class__()
            st.GetReferredShape_s(label, ref)
            return walk(ref, loc.Multiplied(st.GetLocation_s(label)), nm)
        if st.IsAssembly_s(label):
            kids = TDF_LabelSequence()
            st.GetComponents_s(label, kids)
            for i in range(1, kids.Length() + 1):
                walk(kids.Value(i), loc, nm)
            return
        shape = st.GetShape_s(label).Moved(loc)
        ex = TopExp_Explorer(shape, TopAbs_SOLID)
        solids = []
        while ex.More():
            solids.append(cq.Solid(ex.Current()))
            ex.Next()
        for k, s in enumerate(solids):
            out.append((nm if len(solids) == 1 else f"{nm} {k + 1}", s))

    roots = TDF_LabelSequence()
    st.GetFreeShapes(roots)
    for i in range(1, roots.Length() + 1):
        walk(roots.Value(i), TopLoc_Location(), "")
    return [(n or f"Part {i + 1}", s) for i, (n, s) in enumerate(out)]


def cyl_axes(shape):
    axes = []
    for f in shape.Faces():
        if f.geomType() == "CYLINDER":
            d = f._geomAdaptor().Cylinder().Axis().Direction()
            v = (d.X(), d.Y(), d.Z())
            if not any(abs(abs(sum(a * b for a, b in zip(v, w))) - 1) < 1e-6 for w in axes):
                axes.append(v)
    return axes


def bb(s):
    b = s.BoundingBox()
    return b.xmin, b.ymin, b.zmin, b.xmax, b.ymax, b.zmax


def boxes_overlap(a, b, gap=1e-6):
    return all(a[i] < b[i + 3] - gap and b[i] < a[i + 3] - gap for i in range(3))


def overlap(a, b):
    try:
        return a.intersect(b).Volume()
    except Exception:  # noqa: BLE001  (boolean failed: treat as touching only)
        return 0.0


def info(step):
    for i, (n, s) in enumerate(load_parts(step)):
        b = bb(s)
        print(f"{i}: {n}  volume {s.Volume():.1f} mm3  bbox [{b[0]:.2f},{b[1]:.2f},{b[2]:.2f}] .. [{b[3]:.2f},{b[4]:.2f},{b[5]:.2f}]")
        for a in cyl_axes(s):
            print(f"     cylinder axis {tuple(round(x, 4) for x in a)}")


def removal(part, others, d, base_overlap):
    """Distance to slide `part` along unit d until it clears `others`, or None if it collides."""
    import cadquery as cq
    pb, ob = bb(part), [bb(o) for o in others]
    if not others:
        return 0.0
    size = [pb[i + 3] - pb[i] for i in range(3)]
    stepl = max(min(size) / 4, 0.05)
    # far enough: the part's box is past every remaining box along d
    proj = lambda box: [sum(d[i] * (box[i + 3] if d[i] > 0 else box[i]) for i in range(3)),
                        sum(d[i] * (box[i] if d[i] > 0 else box[i + 3]) for i in range(3))]
    pmin = proj(pb)[1]
    far = max(proj(b)[0] for b in ob) - pmin
    far = max(far, 0.0)
    n = max(1, math.ceil(far / stepl))
    for k in range(1, n + 1):
        t = far * k / n
        moved = part.moved(cq.Location(cq.Vector(*(c * t for c in d))))
        mb = bb(moved)
        for o, obox, base in zip(others, ob, base_overlap):
            if boxes_overlap(mb, obox) and overlap(moved, o) > base + max(1e-3, 1e-4 * part.Volume()):
                return None
    return far


def plan(step, out, base_name=None, extra_dirs=()):
    parts = load_parts(step)
    names = [n for n, _ in parts]
    vol = {n: s.Volume() for n, s in parts}
    base = base_name or max(names, key=lambda n: vol[n])
    if base not in names:
        sys.exit(f"unknown base part {base!r}; parts: {', '.join(names)}")
    shape = dict(parts)
    remaining = list(names)
    steps, notes = [], []
    pre = {}  # overlap already present in the assembled state
    for a in names:
        for b in names:
            if a < b and boxes_overlap(bb(shape[a]), bb(shape[b])):
                v = overlap(shape[a], shape[b])
                if v > 1e-3:
                    pre[(a, b)] = pre[(b, a)] = v
                    notes.append(f"{a} and {b} overlap by {v:.2f} mm3 when assembled (press fit or modelling error)")
    axes6 = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
    while len(remaining) > 1:
        found = []
        for n in remaining:
            if n == base:
                continue
            others = [m for m in remaining if m != n]
            dirs = list(axes6) + list(extra_dirs)
            for a in cyl_axes(shape[n]):
                dirs += [a, tuple(-x for x in a)]
            free = []
            for d in dirs:
                if any(abs(sum(x * y for x, y in zip(d, e)) - 1) < 1e-6 for e, _ in free):
                    continue  # same direction already tested
                dist = removal(shape[n], [shape[m] for m in others], d, [pre.get((n, m), 0.0) for m in others])
                if dist is not None:
                    free.append((d, dist))
            if free:
                found.append((n, free))
        if not found:
            break
        # take the smallest free part; prefer the direction with the shortest way out
        n, free = min(found, key=lambda f: vol[f[0]])
        d, dist = min(free, key=lambda f: f[1])
        b = bb(shape[n])
        size = max(b[i + 3] - b[i] for i in range(3))
        steps.append({"name": f"Remove {n}", "parts": [n], "direction": [round(x, 4) + 0.0 for x in d],
                      "distance": round(dist + max(0.3 * size, 5), 1),
                      "free": [[round(x, 4) + 0.0 for x in e] for e, _ in free]})
        remaining.remove(n)
    locked = [n for n in remaining if n != base]
    for n in locked:
        notes.append(f"LOCKED: {n} cannot slide out in any tested direction while "
                     f"{', '.join(m for m in remaining if m != n)} stay in place")
    data = {"base": base, "steps": steps, "locked": locked, "notes": notes}
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    print(json.dumps(data, ensure_ascii=False, indent=1))
    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("info")
    a.add_argument("step")
    p = sub.add_parser("plan")
    p.add_argument("step")
    p.add_argument("--out")
    p.add_argument("--base")
    p.add_argument("--dirs", default="", help="extra directions x,y,z;x,y,z")
    args = ap.parse_args()
    if args.cmd == "info":
        info(args.step)
    else:
        extra = []
        for s in filter(None, args.dirs.split(";")):
            v = [float(c) for c in s.split(",")]
            k = math.sqrt(sum(c * c for c in v))
            extra.append(tuple(c / k for c in v))
        plan(args.step, args.out, args.base, extra)


if __name__ == "__main__":
    main()

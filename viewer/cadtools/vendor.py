"""Interface of a purchased part from the vendor's STEP: envelope, mounting faces, hole patterns, shafts.

Claude then designs the mating part from ~20 lines of JSON instead of opening the vendor model.
"""
from . import core, digest


def _compound(model):
    from OCP.TopoDS import TopoDS_Compound
    from OCP.BRep import BRep_Builder
    b = BRep_Builder()
    c = TopoDS_Compound()
    b.MakeCompound(c)
    for i in model:
        b.Add(c, i.shape)
    return c


def interface(step):
    def go():
        model = core.load(step)
        comp = _compound(model)
        bb = core.bbox(comp)
        holes, shafts, _ = digest.holes_and_shafts(comp, bb)
        pats = digest.patterns(holes)
        # mounting faces: per direction the biggest planar face (then the outermost of similar size)
        planes = digest.big_planes(comp, 400)
        best = {}
        for p in planes:
            if not isinstance(p["normal"], str):
                continue
            cur = best.get(p["normal"])
            if cur is None or p["area"] > 1.2 * cur["area"]:
                best[p["normal"]] = p
        mount = sorted(best.values(), key=lambda p: -p["area"])
        # shafts that reach the envelope (output shafts, pins)
        out_shafts = []
        for s in shafts:
            ax = {"X": 0, "Y": 1, "Z": 2}.get(s["axis"]) if isinstance(s["axis"], str) else None
            if ax is None:
                continue
            end = s["at"][ax] + s["len"]
            if abs(end - bb[ax + 3]) < 0.5 or abs(s["at"][ax] - bb[ax]) < 0.5:
                out_shafts.append(s)
        vol = sum(core.props(i.shape)[0] for i in model)
        return {"ok": True, "model": step, "parts": len(model), "envelope": core.r([bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]]),
                "min": core.r(bb[:3]), "max": core.r(bb[3:]), "volume": core.r(vol, 0),
                "mass_steel_g": core.r(vol * 7.85 / 1000, 0), "mass_alu_g": core.r(vol * 2.7 / 1000, 0),
                "mounting_faces": mount, "hole_patterns": [p for p in pats if p["d"] < 0.5 * max(bb[3] - bb[0], bb[4] - bb[1])][:12],
                "shafts_out": sorted(out_shafts, key=lambda s: -s["d"])[:6],
                "note": "coordinates are in the vendor file's own frame"}
    return core.cached(step, "vendor", "", go)

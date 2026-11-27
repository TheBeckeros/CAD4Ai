"""Automatic motion: <model>.motion.json generated from one word per part in <model>.parts.json.

    "parts": {"BTN_":  {"motion": "press"},                 # buttons: stroke into the panel
              "KNOB":  {"motion": "rotate"},                # knobs, wheels: spin about their own axis
              "LID":   {"motion": "hinge"},                 # door / lid: swing until it hits something
              "DRAWER":{"motion": "slide"},                 # drawer, carriage: free travel along a rail
              "WHEEL": {"motion": {"type": "rotate", "range": [-90, 90], "on": "ARM"}}}

Kinds: press|button, rotate|knob|wheel|spin, hinge|door|lid|lever, slide|drawer|rail.
Optional dict keys (override what is detected): axis ("X", "-Z" or [x,y,z]), origin [x,y,z], range [min,max],
travel (mm, press), on (part that carries it), drive {"part": name, "ratio": r}, group (animation name).

Everything else is computed from the geometry on this PC: axis from the part's cylinders (or its thinnest
direction), press direction into the assembly, hinge/slide limits by stepping the part until it collides with
the rest (exact boolean, home overlaps such as a shaft fit are subtracted). The result is keyed to the STEP
version, so a rebuild (Claude's export or the user's Parameters tab) regenerates it without any AI step.
A hand-written motion.json (without "generated") is never overwritten.
"""
import json
import math
import os

import numpy as np

from . import core

KINDS = {"press": "press", "button": "press", "push": "press",
         "rotate": "rotate", "knob": "rotate", "wheel": "rotate", "spin": "rotate", "dial": "rotate",
         "hinge": "hinge", "door": "hinge", "lid": "hinge", "lever": "hinge", "flap": "hinge",
         "slide": "slide", "drawer": "slide", "rail": "slide", "slider": "slide"}
AX = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1), "-X": (-1, 0, 0), "-Y": (0, -1, 0), "-Z": (0, 0, -1)}
TOL = 0.5  # mm3 of new overlap that counts as a collision


def motion_file(step):
    return os.path.splitext(step)[0] + ".motion.json"


def specs(step):
    """{inst_name: spec dict} for parts that carry a "motion" key."""
    out = []
    for i in core.load(step):
        m = (i.info or {}).get("motion")
        if not m:
            continue
        if isinstance(m, str):
            m = {"type": m}
        kind = KINDS.get(str(m.get("type", "")).lower())
        if kind:
            out.append((i, dict(m, type=kind)))
    return out


def needed(step):
    """True when the motion file is missing or stale for this STEP and the parts ask for motion."""
    if not core.parts_info(step) or not any("motion" in (v or {}) for v in core.parts_info(step).values()):
        return False
    f = motion_file(step)
    try:
        with open(f, encoding="utf-8") as fh:
            cur = json.load(fh)
    except (OSError, ValueError):
        return True
    if not cur.get("generated"):
        return False  # hand-written: leave alone
    return cur.get("source_key") != _key(step)


def _key(step):
    pj = os.path.splitext(step)[0].split("@", 1)[0] + ".parts.json"
    k = core.file_key(step)
    try:
        k += f":{os.path.getmtime(pj):.0f}"
    except OSError:
        pass
    return k + ":" + core.TOOLS_VERSION


# ---------------------------------------------------------------- geometry helpers
def _vol(shape):
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, g)
    return abs(g.Mass())


def _common(a, b):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    try:
        c = BRepAlgoAPI_Common(a, b)
        return _vol(c.Shape()) if c.IsDone() else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


def _moved(shape, kind, origin, axis, v):
    from OCP.gp import gp_Trsf, gp_Ax1, gp_Pnt, gp_Dir, gp_Vec
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    t = gp_Trsf()
    if kind in ("hinge", "rotate"):
        t.SetRotation(gp_Ax1(gp_Pnt(*origin), gp_Dir(*axis)), math.radians(v))
    else:
        t.SetTranslation(gp_Vec(*(np.array(axis) * v)))
    return BRepBuilderAPI_Transform(shape, t, True).Shape()


def _overlap(a, b, pad=0.0):
    return all(a[k] - pad <= b[k + 3] and b[k] - pad <= a[k + 3] for k in range(3))


def _cyls(shape, min_ang=1.9 * math.pi, convex_only=False):
    from .digest import _cyl_features
    return [f for f in _cyl_features(shape) if f["ang"] > min_ang and not (convex_only and f["concave"])]


def _axis_of(inst, others, hinge=False):
    """Dominant rotation axis: the cylinder line with most area. Hinges: knuckles/pin bores need not be full."""
    feats = _cyls(inst.shape, 0.9 * math.pi) if hinge else _cyls(inst.shape)
    if feats:
        groups = []
        for f in feats:
            for g in groups:
                if abs(abs(np.dot(g["dir"], f["dir"])) - 1) < 1e-4 and \
                        np.linalg.norm(np.cross(np.array(f["foot"]) - g["foot"], g["dir"])) < 0.05:
                    g["area"] += f["area"]
                    g["t"] += [f["t0"], f["t1"]]
                    break
            else:
                groups.append({"dir": np.array(f["dir"], float), "foot": np.array(f["foot"], float),
                               "area": f["area"], "t": [f["t0"], f["t1"]]})
        g = max(groups, key=lambda g: g["area"])
        tm = (min(g["t"]) + max(g["t"])) / 2
        return g["dir"], g["foot"] + tm * g["dir"], "cylinder"
    bb = core.bbox(inst.shape)
    size = np.array(bb[3:]) - bb[:3]
    c = (np.array(bb[:3]) + bb[3:]) / 2
    d = np.zeros(3)
    if not hinge:
        d[int(np.argmin(size))] = 1
        return d, c, "thinnest direction"
    # hinge without a knuckle: the longest edge, on the side towards the assembly centre is tried by the caller
    k, th = int(np.argmax(size)), int(np.argmin(size))
    d[k] = 1
    return d, c, f"long edge {'XYZ'[k]}|thin {'XYZ'[th]}"


def _thin_axis(inst):
    bb = core.bbox(inst.shape)
    size = np.array(bb[3:]) - bb[:3]
    d = np.zeros(3)
    d[int(np.argmin(size))] = 1
    return d


def _parse_axis(a):
    if isinstance(a, str):
        return np.array(AX[a.upper()], float)
    v = np.array(a, float)
    return v / np.linalg.norm(v)


class _Scene:
    """Fixed parts near a moving part, with their home overlaps (so press fits are not collisions)."""

    def __init__(self, insts, mover, exclude, reach):
        bb = core.bbox(mover.shape)
        self.near = []
        for o in insts:
            if o is mover or o.name in exclude or o.owner == mover.owner:
                continue
            ob = core.bbox(o.shape)
            if ob and _overlap(bb, ob, reach):
                self.near.append((o, ob, _common(mover.shape, o.shape) if _overlap(bb, ob, 0.01) else 0.0))

    def hits(self, shape):
        b = core.bbox(shape)
        for o, ob, home in self.near:
            if _overlap(b, ob) and _common(shape, o.shape) > home + TOL:
                return o.name
        return None


def _free(inst, kind, origin, axis, scene, limit, step0):
    """Largest v in (0, limit] reachable from home without a collision (coarse steps + bisection)."""
    last, v = 0.0, step0
    while v <= limit + 1e-9:
        hit = scene.hits(_moved(inst.shape, kind, origin, axis, v))
        if hit:
            lo, hi = last, v
            for _ in range(6):
                mid = (lo + hi) / 2
                if scene.hits(_moved(inst.shape, kind, origin, axis, mid)):
                    hi = mid
                else:
                    lo = mid
            return lo, hit
        last, v = v, v + step0
    return limit, None


# ---------------------------------------------------------------- joints
def build(step):
    insts = core.load(step)
    byname = {i.name: i for i in insts}
    items = specs(step)
    moving = {i.name for i, _ in items}
    joints, notes = [], []
    for inst, sp in items:
        kind = sp["type"]
        others = [o for o in insts if o.name not in moving]
        carried = {j.name for j, s in items if s.get("on") == inst.name}
        bb = core.bbox(inst.shape)
        size = float(max(np.array(bb[3:]) - bb[:3]))
        center = (np.array(bb[:3]) + bb[3:]) / 2
        how = []
        j = {"name": inst.name, "parts": [inst.name]}
        if kind in ("rotate", "hinge"):
            j["type"] = "revolute"
            if "axis" in sp:
                axis, origin, src = _parse_axis(sp["axis"]), center, "given"
            else:
                axis, origin, src = _axis_of(inst, others, hinge=kind == "hinge")
            if kind == "hinge" and src.startswith("long edge") and "origin" not in sp:
                # no knuckle: try the 4 long edges of the box, keep the one that opens furthest
                th = "XYZ".index(src[-1])
                k = int(np.argmax(axis))
                o = [a for a in range(3) if a not in (k, th)][0]
                sc = _Scene(insts, inst, moving | carried, size)
                best = None
                for so in (0, 1):
                    for st_ in (0, 1):
                        org = center.copy()
                        org[o] = bb[o + 3 * so]
                        org[th] = bb[th + 3 * st_]
                        for sg in (1, -1):
                            v, h = _free(inst, "hinge", org, sg * axis, sc, 120, 10)
                            if best is None or v > best[0] + 1e-6:
                                best = (v, org, sg * axis)
                origin, axis = best[1], best[2]
                src = "long edge (no knuckle found)"
            if "origin" in sp:
                origin = np.array(sp["origin"], float)
            how.append(f"axis from {src}")
            if "range" in sp:
                lo, hi = sp["range"]
            elif kind == "rotate":
                lo, hi = -180, 180
            else:
                sc = _Scene(insts, inst, moving | carried, size)
                a, ha = _free(inst, "hinge", origin, axis, sc, 180, 5)
                b, hb = _free(inst, "hinge", origin, -axis, sc, 180, 5)
                if b > a:  # open the free way round as positive
                    axis, a, b, ha, hb = -axis, b, a, hb, ha
                lo, hi = 0, round(a, 1)
                how.append(f"opens {hi} deg" + (f" until it hits {ha}" if ha else " (free)"))
        else:
            j["type"] = "prismatic"
            if "axis" in sp:
                axis = _parse_axis(sp["axis"])
            elif kind == "press":
                cy = _cyls(inst.shape)
                axis = _axis_of(inst, others)[0] if cy else _thin_axis(inst)
            else:
                ext = np.array(bb[3:]) - bb[:3]
                axis = np.zeros(3)
                axis[int(np.argmax(ext))] = 1
            origin = center
            sc = _Scene(insts, inst, moving | carried, size * (0.6 if kind == "press" else 3))
            if kind == "press":
                if "axis" not in sp:
                    # press into the assembly: towards the centre of the parts around it
                    pts = [(np.array(ob[:3]) + ob[3:]) / 2 for _, ob, _ in sc.near] or \
                          [(np.array(core.bbox(o.shape)[:3]) + core.bbox(o.shape)[3:]) / 2 for o in others[:50]]
                    if pts and np.dot(np.mean(pts, axis=0) - center, axis) > 0:
                        pass
                    else:
                        axis = -axis
                if "travel" in sp:
                    t = float(sp["travel"])
                    how.append("travel given")
                else:
                    ext = float(np.dot(np.array(bb[3:]) - bb[:3], np.abs(axis)))
                    t, hit = _free(inst, "press", origin, axis, sc, max(0.5, min(5.0, 0.6 * ext)), 0.1)
                    if t < 0.2:
                        t = min(1.5, 0.3 * ext)
                        how.append(f"no free stroke found, {t:.1f} mm assumed")
                    else:
                        how.append(f"stroke {t:.2f} mm" + (f" to {hit}" if hit else ""))
                lo, hi = 0, round(t, 2)
            else:
                if "range" in sp:
                    lo, hi = sp["range"]
                else:
                    a, ha = _free(inst, "slide", origin, axis, sc, 3 * size, size / 40)
                    b, hb = _free(inst, "slide", origin, -axis, sc, 3 * size, size / 40)
                    lo, hi = -round(b, 2), round(a, 2)
                    how.append(f"travel {lo}..{hi} mm" + (f" (stops: {ha or '-'} / {hb or '-'})"))
        j.update(origin=[round(float(x), 3) + 0.0 for x in origin], axis=[round(float(x), 6) + 0.0 for x in axis],
                 min=lo, max=hi, home=0)
        if sp.get("on"):
            j["parent"] = sp["on"]
        if isinstance(sp.get("drive"), dict) and sp["drive"].get("part"):
            j["drive"] = {"joint": sp["drive"]["part"], "ratio": float(sp["drive"].get("ratio", 1))}
        j["note"] = f"auto ({kind}): " + ", ".join(how)
        j["_group"] = sp.get("group") or {"press": "Buttons", "rotate": "Knobs", "hinge": "Doors",
                                          "slide": "Slides"}[kind]
        joints.append(j)
        notes.append(f"{inst.name}: {j['type']} {lo}..{hi} ({', '.join(how)})")
    # parents must exist as joints
    names = {j["name"] for j in joints}
    for j in joints:
        if j.get("parent") and j["parent"] not in names:
            notes.append(f"{j['name']}: 'on' {j['parent']} is not a moving part, ignored")
            j.pop("parent")
        if j.get("drive") and j["drive"]["joint"] not in names:
            j.pop("drive")
    return joints, notes


def _animations(joints):
    anims, groups = [], {}
    for j in joints:
        if "drive" not in j:
            groups.setdefault(j["_group"], []).append(j)

    def full(j):
        return j["max"] if abs(j["max"]) >= abs(j["min"]) else j["min"]

    for g, js in groups.items():
        n = len(js)
        kf = [{"t": 0, "values": {j["name"]: 0 for j in js}}]
        if g == "Buttons" and n > 1:  # press one after another
            for k, j in enumerate(js):
                a, b = k / n, (k + 0.5) / n
                kf += [{"t": round(a, 4), "values": {j["name"]: 0}}, {"t": round((a + b) / 2, 4), "values": {j["name"]: full(j)}},
                       {"t": round(b, 4), "values": {j["name"]: 0}}]
        else:
            kf += [{"t": 0.5, "values": {j["name"]: full(j) for j in js}}]
        kf.append({"t": 1, "values": {j["name"]: 0 for j in js}})
        anims.append({"name": g, "duration": max(2, min(12, 0.8 * n)) if g == "Buttons" else 4, "keyframes": kf})
    return anims


def generate(step, force=False):
    f = motion_file(step)
    if not force:
        try:
            with open(f, encoding="utf-8") as fh:
                if not json.load(fh).get("generated"):
                    return {"ok": False, "skipped": "hand-written motion.json exists (use --force)"}
        except (OSError, ValueError):
            pass
    joints, notes = build(step)
    if not joints:
        return {"ok": False, "skipped": "no part has a 'motion' key in parts.json"}
    anims = _animations(joints)
    for j in joints:
        j.pop("_group", None)
    data = {"generated": "cad4ai motion (from parts.json motion keys; regenerated on every rebuild)",
            "source_key": _key(step), "joints": joints, "animations": anims}
    tmp = f + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    os.replace(tmp, f)
    return {"ok": True, "file": f, "joints": len(joints), "notes": notes}


def ensure(step):
    """Regenerate when stale; quiet no-op otherwise. Used by the hook and the viewer server."""
    try:
        if needed(step):
            return generate(step)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return None

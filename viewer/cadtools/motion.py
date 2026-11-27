"""Automatic motion: <model>.motion.json generated from one word per part in <model>.parts.json.

    "parts": {"BTN_CAP_": {"motion": "press"},              # buttons: the CAP strokes into the panel
              "KNOB":  {"motion": "rotate"},                # knobs, wheels: spin about their own axis
              "LID":   {"motion": "hinge"},                 # door / lid: swing until it hits something
              "DRAWER":{"motion": "slide"},                 # drawer, carriage: free travel along a rail
              "DOOR":  {"motion": {"type": "door", "home": 80, "with": ["DOOR_"]}},
              "WHEEL": {"motion": {"type": "rotate", "range": [-90, 90], "on": "ARM"}}}

Kinds: press|button, rotate|knob|wheel|spin, hinge|door|lid|lever, slide|drawer|rail.
Optional dict keys (override what is detected): axis ("X", "-Z" or [x,y,z]), origin [x,y,z], range [min,max]
(used as is, no collision search), max (furthest opening / travel to search), travel (mm, press),
home (joint value of the STEP pose, e.g. a door exported 80 deg open), with [names or name prefixes] (parts
carried along: hinge leaf, screws, lock, seal...), ignore [names or prefixes] (fixed parts left out of the
collision search), pin (name prefix of the fixed pin / axle that gives the axis), on (part that carries it),
drive {"part": name, "ratio": r}, group (animation name).

One joint per STEP instance: all its solids (name#1, name#2 ...) move together on the axis of the largest one.
Parts are also carried when their parts.json "subassembly" equals the moving part's (unless that subassembly
holds half the model or more, i.e. it is the whole machine). Flexible parts (cables, straps) never stop a motion.

Everything else is computed from the geometry on this PC:
- hinge axis: the line where a cylinder of the moving group (knuckle bore, pin) is coaxial with a cylinder of a
  fixed part nearby (pin, axle, frame-side knuckle); several pins on one line and pin-like names win, so a lock
  or screw hole does not. The part's own largest cylinder is only the fallback. Fixed parts on that axis that
  touch the group (pin, frame leaf) are hinge hardware and are left out of the collision search.
- press: the moving part should be the cap (the bit the finger pushes), not the whole switch. A fixed coaxial
  shank or plunger the cap sits on is left out of the collision search; the rest (bezel, housing) stops it.
- limits: the group is stepped from home in both directions until it collides with the rest (exact boolean,
  home overlaps such as a shaft fit are subtracted).
The result is keyed to the STEP version, so a rebuild (Claude's export or the user's Parameters tab)
regenerates it without any AI step. A hand-written motion.json (without "generated") is never overwritten.
"""
import json
import math
import os
import re

import numpy as np

from . import core

KINDS = {"press": "press", "button": "press", "push": "press",
         "rotate": "rotate", "knob": "rotate", "wheel": "rotate", "spin": "rotate", "dial": "rotate",
         "hinge": "hinge", "door": "hinge", "lid": "hinge", "lever": "hinge", "flap": "hinge",
         "slide": "slide", "drawer": "slide", "rail": "slide", "slider": "slide"}
AX = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1), "-X": (-1, 0, 0), "-Y": (0, -1, 0), "-Z": (0, 0, -1)}
TOL = 0.5  # mm3 of new overlap that counts as a collision
PIN_WORD = re.compile(r"pin|cep|čep|axle|shaft|hinge|pant|osa|osick|osičk|pivot|knuckle|bolzen|achse", re.I)


def motion_file(step):
    return os.path.splitext(step)[0] + ".motion.json"


def _base(name):
    return name.split("#", 1)[0]


def _hit(name, pats):
    """name (or its STEP instance base) equals one of pats or starts with it (parts.json key style)."""
    b = _base(name)
    return any(b == p or name == p or b.startswith(p) for p in pats)


def _key_for(info, name):
    """The parts.json key that applies to a STEP instance name (exact, else longest prefix)."""
    if name in info:
        return name
    best = None
    for k in info:
        if name.startswith(k) and (best is None or len(k) > len(best)):
            best = k
    return best


def specs(step):
    """[(solids of one STEP instance, spec dict, parts.json key)] for parts that carry a "motion" key."""
    info = core.parts_info(step)
    groups = {}
    for i in core.load(step):
        m = (i.info or {}).get("motion")
        if not m:
            continue
        if isinstance(m, str):
            m = {"type": m}
        kind = KINDS.get(str(m.get("type", "")).lower())
        if kind:
            g = groups.setdefault(i.owner, [[], dict(m, type=kind), _key_for(info, i.owner)])
            g[0].append(i)
    # a part another moving part carries ("with") moves with it, even when its name inherits the motion key
    # by prefix (key "DOOR" also matches "DOOR_LEAF")
    carried = set()
    for owner, (_, sp, _) in groups.items():
        pats = [sp["with"]] if isinstance(sp.get("with"), str) else list(sp.get("with") or [])
        carried |= {o for o in groups if o != owner and _hit(o, pats)}
    return [tuple(g) for o, g in groups.items() if o not in carried]


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


def _rot_pt(p, origin, axis, deg):
    a = math.radians(deg)
    v = np.asarray(p, float) - origin
    return origin + v * math.cos(a) + np.cross(axis, v) * math.sin(a) + axis * np.dot(axis, v) * (1 - math.cos(a))


def _overlap(a, b, pad=0.0):
    return all(a[k] - pad <= b[k + 3] and b[k] - pad <= a[k + 3] for k in range(3))


def _cyls(shape, min_ang=1.9 * math.pi, convex_only=False):
    from .digest import _cyl_features
    return [f for f in _cyl_features(shape) if f["ang"] > min_ang and not (convex_only and f["concave"])]


def _union_bb(bbs):
    a = np.array(bbs, float)
    return list(a[:, :3].min(0)) + list(a[:, 3:].max(0))


def _center(bb):
    return (np.array(bb[:3], float) + bb[3:]) / 2


def _line_dist(f, origin, axis):
    """Distance between a cylinder feature's axis line and the line (origin, axis); inf when not parallel."""
    d = np.array(f["dir"], float)
    if abs(abs(np.dot(d, axis)) - 1) > 1e-4:
        return math.inf
    return float(np.linalg.norm(np.cross(np.array(f["foot"], float) - origin, axis)))


class _Geo:
    """Per-build caches: tight bounding boxes and cylinder features of solids."""

    def __init__(self, insts):
        self.insts = insts
        self.by = {i.name: i for i in insts}
        self._bb, self._cy = {}, {}

    def bb(self, i):
        if i.name not in self._bb:
            self._bb[i.name] = core.bbox(i.shape)
        return self._bb[i.name]

    def cyl(self, i):
        if i.name not in self._cy:
            try:
                self._cy[i.name] = _cyls(i.shape, 0.9 * math.pi)
            except Exception:  # noqa: BLE001
                self._cy[i.name] = []
        return self._cy[i.name]

    def touching(self, movers, cands, pad=0.5):
        """Candidates whose box touches the box of any mover (cheap near-contact test)."""
        mbs = [self.bb(m) for m in movers]
        return [o for o in cands if self.bb(o) and any(_overlap(mb, self.bb(o), pad) for mb in mbs if mb)]


def _own_axis(main, hinge=False):
    """Dominant rotation axis of one solid: the cylinder line with most area. Hinges: knuckles need not be full."""
    feats = _cyls(main.shape, 0.9 * math.pi) if hinge else _cyls(main.shape)
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
        return g["dir"], g["foot"] + tm * g["dir"], "own largest cylinder"
    bb = core.bbox(main.shape)
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


def _pin_axis(geo, movers, fixed):
    """Hinge line from coaxial cylinder pairs between the moving group and fixed parts touching it (knuckle
    bore on a pin, pin in a frame bore, knuckle next to knuckle). Returns (dir, origin, source) or None."""
    lines = []
    for m in movers:
        fm = geo.cyl(m)
        if not fm:
            continue
        for o in geo.touching([m], fixed):
            for b in geo.cyl(o):
                bd, bf = np.array(b["dir"], float), np.array(b["foot"], float)
                for a in fm:
                    if _line_dist(a, bf, bd) > max(0.05, 0.02 * max(a["r"], b["r"])):
                        continue
                    if abs(a["r"] - b["r"]) > max(0.3, 0.1 * max(a["r"], b["r"])):
                        continue
                    if a["t0"] > b["t1"] + 1.0 or b["t0"] > a["t1"] + 1.0:
                        continue  # same line but apart along it
                    for ln in lines:
                        if _line_dist(b, ln["foot"], ln["dir"]) < 0.1:
                            break
                    else:
                        ln = {"dir": bd, "foot": bf, "w": 0.0, "fixed": set(), "t": []}
                        lines.append(ln)
                    ln["w"] += min(a["area"], b["area"])
                    ln["fixed"].add(o.name)
                    ln["t"] += [a["t0"], a["t1"], b["t0"], b["t1"]]
    if not lines:
        return None
    for ln in lines:
        named = any(PIN_WORD.search(_base(n)) for n in ln["fixed"])
        ln["score"] = ln["w"] * len(ln["fixed"]) * (3 if named else 1)
    ln = max(lines, key=lambda x: x["score"])
    tm = (min(ln["t"]) + max(ln["t"])) / 2
    d = ln["dir"] / np.linalg.norm(ln["dir"])
    pins = sorted({_base(n) for n in ln["fixed"]})
    return d, ln["foot"] + tm * d, "pin " + ", ".join(pins[:3])


def _given_pin(geo, prefix):
    """Axis from the largest cylinder of the named pin / axle parts."""
    best = None
    for i in geo.insts:
        if _hit(i.name, [prefix]):
            for f in geo.cyl(i):
                if best is None or f["area"] > best["area"]:
                    best = f
    if not best:
        return None
    d = np.array(best["dir"], float)
    d /= np.linalg.norm(d)
    return d, np.array(best["foot"], float) + (best["t0"] + best["t1"]) / 2 * d, f"pin {prefix} (given)"


def _on_axis(geo, movers, fixed, origin, axis, convex_only=False, pad=0.5):
    """Fixed parts touching the group that have a cylinder on the joint axis (hinge pin, frame leaf, shank)."""
    out = []
    for o in geo.touching(movers, fixed, pad):
        if any(_line_dist(f, origin, axis) < 0.2 and not (convex_only and f["concave"]) for f in geo.cyl(o)):
            out.append(o.name)
    return out


def _parse_axis(a):
    if isinstance(a, str):
        return np.array(AX[a.upper()], float)
    v = np.array(a, float)
    return v / np.linalg.norm(v)


class _Scene:
    """Fixed parts near a moving solid, with their home overlaps (so press fits are not collisions)."""

    def __init__(self, geo, mover, exclude, reach):
        if not isinstance(geo, _Geo):  # older scripts pass the instance list (panel_motion.py)
            geo = _Geo(geo)
        bb = geo.bb(mover)
        self.near = []
        for o in geo.insts:
            if o is mover or o.name in exclude or o.owner == mover.owner or o.flexible:
                continue
            ob = geo.bb(o)
            if ob and _overlap(bb, ob, reach):
                self.near.append((o, ob, _common(mover.shape, o.shape) if _overlap(bb, ob, 0.01) else 0.0))

    def hits(self, shape):
        b = core.bbox(shape)
        for o, ob, home in self.near:
            if _overlap(b, ob) and _common(shape, o.shape) > home + TOL:
                return o.name
        return None


class _Group:
    """The solids that move together (joint part + carried parts), each with its own scene."""

    def __init__(self, geo, movers, exclude, reach):
        self.sc = [(m, _Scene(geo, m, exclude, reach(m))) for m in movers]

    def hits(self, kind, origin, axis, v):
        for m, sc in self.sc:
            h = sc.hits(_moved(m.shape, kind, origin, axis, v))
            if h:
                return h
        return None


def _free(grp, kind, origin, axis, limit, step0):
    """Largest v in (0, limit] reachable from home without a collision (coarse steps + bisection)."""
    if limit <= 0:
        return 0.0, None
    last, v = 0.0, min(step0, limit)
    while True:
        hit = grp.hits(kind, origin, axis, v)
        if hit:
            lo, hi = last, v
            for _ in range(6):
                mid = (lo + hi) / 2
                if grp.hits(kind, origin, axis, mid):
                    hi = mid
                else:
                    lo = mid
            return lo, hit
        if v >= limit - 1e-9:
            return limit, None
        last, v = v, min(v + step0, limit)


def _closed_score(geo, main, fixed, exclude, origin, axis, home, size):
    """How well the main solid sits against the model when turned back by -home about axis: fixed solids
    within a few mm (a closed door lies on its frame, a wrongly turned one floats), then closeness to the
    median of the fixed parts as a tie-break."""
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    shp = _moved(main.shape, "hinge", origin, axis, -home)
    bb = core.bbox(shp)
    tol = max(3.0, 0.02 * size)
    n = 0
    for o in fixed:
        if o.name in exclude or not geo.bb(o) or not _overlap(bb, geo.bb(o), tol):
            continue
        try:
            d = BRepExtrema_DistShapeShape(shp, o.shape)
            if d.IsDone() and d.Value() <= tol:
                n += 1
        except Exception:  # noqa: BLE001
            pass
    cs = [_center(geo.bb(o)) for o in fixed if geo.bb(o)]
    rest = np.median(cs, axis=0) if cs else _center(bb)
    return n, -float(np.linalg.norm(_center(bb) - rest))


def _sweep_reach(geo, origin, axis):
    """Box padding that holds everything a solid sweeps rotating about the axis."""
    def reach(m):
        bb = geo.bb(m)
        corners = np.array([[bb[i], bb[j + 1], bb[k + 2]] for i in (0, 3) for j in (0, 3) for k in (0, 3)], float)
        r = max(np.linalg.norm(np.cross(c - origin, axis)) for c in corners)
        return 2 * r + 1
    return reach


# ---------------------------------------------------------------- joints
def build(step):
    insts = core.load(step)
    geo = _Geo(insts)
    items = specs(step)
    moving_owner = {g[0].owner for g, _, _ in items}
    n_all = len(insts)
    plan = []
    for solids, sp, key in items:
        main = max(solids, key=lambda s: _vol(s.shape))
        info = main.info or {}
        carried, why = [], []
        if sp.get("with"):
            pats = [sp["with"]] if isinstance(sp["with"], str) else list(sp["with"])
            carried += [i for i in insts if i.owner not in moving_owner and _hit(i.name, pats)]
            why.append("with " + ", ".join(pats))
        sub = info.get("subassembly")
        if sub:
            same = [i for i in insts if (i.info or {}).get("subassembly") == sub]
            if len(same) < 0.5 * n_all:
                extra = [i for i in same if i.owner not in moving_owner and i not in carried]
                if extra:
                    carried += extra
                    why.append(f"subassembly {sub}")
        plan.append((solids, sp, main, carried, why))
    all_moving = {i.name for s, _, _, c, _ in plan for i in s + c}

    joints, notes = [], []
    for solids, sp, main, carried, why in plan:
        kind = sp["type"]
        home = float(sp.get("home", 0) or 0)
        group = solids + carried
        movers = [i for i in group if not i.flexible]
        ignore = [sp["ignore"]] if isinstance(sp.get("ignore"), str) else list(sp.get("ignore") or [])
        fixed = [o for o in insts if o.name not in all_moving and not o.flexible and not _hit(o.name, ignore)]
        fixed_pins = [o for o in fixed if o.type != "fastener"]
        exclude = set(all_moving) | {o.name for o in insts if _hit(o.name, ignore)}
        gbb = _union_bb([geo.bb(i) for i in group])
        size = float(max(np.array(gbb[3:]) - gbb[:3]))
        center = _center(gbb)
        mbb = geo.bb(main)
        msize = float(max(np.array(mbb[3:]) - mbb[:3]))
        how = []
        if carried:
            how.append(f"carries {len(carried)} solid(s) ({'; '.join(why)})")
        j = {"name": main.owner, "parts": [i.name for i in group]}
        if kind in ("rotate", "hinge"):
            j["type"] = "revolute"
            src = None
            if "axis" in sp:
                axis, origin, src = _parse_axis(sp["axis"]), _center(mbb), "given"
            else:
                r = None
                if sp.get("pin"):
                    r = _given_pin(geo, sp["pin"])
                if r is None and kind == "hinge":
                    r = _pin_axis(geo, movers, fixed_pins)
                if r is None:
                    r = _own_axis(main, hinge=kind == "hinge")
                axis, origin, src = r
            axis = np.array(axis, float) / np.linalg.norm(axis)
            if kind == "hinge" and src.startswith("long edge") and "origin" not in sp:
                # no knuckle: try the 4 long edges of the box, keep the one that opens furthest
                th = "XYZ".index(src[-1])
                k = int(np.argmax(np.abs(axis)))
                o = [a for a in range(3) if a not in (k, th)][0]
                best = None
                for so in (0, 1):
                    for st_ in (0, 1):
                        org = _center(mbb)
                        org[o] = mbb[o + 3 * so]
                        org[th] = mbb[th + 3 * st_]
                        grp = _Group(geo, movers, exclude, _sweep_reach(geo, org, axis))
                        for sg in (1, -1):
                            v, h = _free(grp, "hinge", org, sg * axis, 120, 10)
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
                lo, hi = home - 180, home + 180
            else:
                hw = _on_axis(geo, movers, fixed, origin, axis)
                if hw:
                    exclude |= set(hw)
                    how.append("hinge hardware not checked: " + ", ".join(sorted({_base(n) for n in hw})[:4]))
                grp = _Group(geo, movers, exclude, _sweep_reach(geo, origin, axis))
                top = float(sp.get("max", 180))
                if abs(home) < 1e-9:
                    a, ha = _free(grp, "hinge", origin, axis, top, 5)
                    b, hb = _free(grp, "hinge", origin, -axis, top, 5)
                    if b > a:  # open the free way round as positive
                        axis, a, b, ha, hb = -axis, b, a, hb, ha
                    lo, hi = 0, round(a, 1)
                    how.append(f"opens {hi} deg" + (f" until it hits {ha}" if ha else " (free)"))
                else:
                    # exported open: closing (joint -> 0) lays the part back against the rest of the model
                    if _closed_score(geo, main, fixed, exclude, origin, axis, home, size) < \
                            _closed_score(geo, main, fixed, exclude, origin, -axis, home, size):
                        axis = -axis
                    up, hu = _free(grp, "hinge", origin, axis, max(0.0, top - home), 5)
                    dn, hd = _free(grp, "hinge", origin, -axis, max(0.0, home), 5)
                    lo, hi = round(home - dn, 1), round(home + up, 1)
                    how.append(f"home {home:g} deg, closes to {lo:g}" + (f" (hits {hd})" if hd else "")
                               + f", opens to {hi:g}" + (f" (hits {hu})" if hu else " (free)"))
        else:
            j["type"] = "prismatic"
            origin = center
            if "axis" in sp:
                axis = _parse_axis(sp["axis"])
                line_o = _center(mbb)
            elif kind == "press":
                if _cyls(main.shape):
                    axis, line_o, _ = _own_axis(main)
                else:
                    axis = np.zeros(3)
                    axis[int(np.argmin(np.array(mbb[3:]) - mbb[:3]))] = 1
                    line_o = _center(mbb)
            else:
                ext = np.array(mbb[3:]) - mbb[:3]
                axis = np.zeros(3)
                axis[int(np.argmax(ext))] = 1
                line_o = _center(mbb)
            axis = np.array(axis, float) / np.linalg.norm(axis)
            if kind == "press":
                # the cap's own cylinder on the axis: its radius and axial length
                own = [f for f in geo.cyl(main) if _line_dist(f, line_o, axis) < 0.2]
                r_cap = max((f["r"] for f in own if not f["concave"]), default=0.0)
                cap_len = max((f["t1"] - f["t0"] for f in own), default=0.0)
                # a fixed coaxial shank / plunger the cap sits on (not a housing: no wider than the cap)
                shank = [n for n in _on_axis(geo, movers, fixed, line_o, axis, convex_only=True, pad=0.05)
                         if r_cap and any(_line_dist(f, line_o, axis) < 0.2 and not f["concave"]
                                          and f["r"] <= 1.15 * r_cap for f in geo.cyl(geo.by[n]))]
                if shank:
                    exclude |= set(shank)
                    how.append("coaxial shank not checked: " + ", ".join(sorted({_base(n) for n in shank})[:3]))
            grp = _Group(geo, movers, exclude, lambda m: size * (0.6 if kind == "press" else 3))
            if kind == "press":
                if "axis" not in sp:
                    # press into the assembly: towards the centre of the parts around it
                    pts = [(np.array(ob[:3]) + ob[3:]) / 2 for _, sc in grp.sc for _, ob, _ in sc.near] or \
                          [_center(geo.bb(o)) for o in fixed[:50]]
                    if not (pts and np.dot(np.mean(pts, axis=0) - center, axis) > 0):
                        axis = -axis
                if "travel" in sp:
                    t = float(sp["travel"])
                    how.append("travel given")
                else:
                    ext = cap_len or float(np.dot(np.array(mbb[3:]) - mbb[:3], np.abs(axis)))
                    lim = float(sp.get("max", max(0.5, min(5.0, 0.6 * ext))))
                    t, hit = _free(grp, "press", origin, axis, lim, 0.1)
                    if t < 0.2:
                        t = min(1.5, 0.3 * ext)
                        how.append(f"no free stroke found, {t:.1f} mm assumed")
                    else:
                        how.append(f"stroke {t:.2f} mm" + (f" to {hit}" if hit else " (free, capped)"))
                lo, hi = home, round(home + t, 2)
            else:
                if "range" in sp:
                    lo, hi = sp["range"]
                else:
                    top = float(sp.get("max", 3 * msize))
                    a, ha = _free(grp, "slide", origin, axis, top, msize / 40)
                    b, hb = _free(grp, "slide", origin, -axis, top, msize / 40)
                    lo, hi = round(home - b, 2), round(home + a, 2)
                    how.append(f"travel {lo}..{hi} mm" + (f" (stops: {ha or '-'} / {hb or '-'})"))
        j.update(origin=[round(float(x), 3) + 0.0 for x in origin], axis=[round(float(x), 6) + 0.0 for x in axis],
                 min=lo, max=hi, home=home)
        if sp.get("on"):
            j["parent"] = sp["on"]
        if isinstance(sp.get("drive"), dict) and sp["drive"].get("part"):
            j["drive"] = {"joint": sp["drive"]["part"], "ratio": float(sp["drive"].get("ratio", 1))}
        j["note"] = f"auto ({kind}): " + ", ".join(how)
        j["_group"] = sp.get("group") or {"press": "Buttons", "rotate": "Knobs", "hinge": "Doors",
                                          "slide": "Slides"}[kind]
        joints.append(j)
        notes.append(f"{j['name']}: {j['type']} {lo}..{hi} ({', '.join(how)})")

    # parents / drives refer to a part name or prefix: map it to the joint that moves that part
    def joint_of(ref):
        for j in joints:
            if j["name"] == ref or ref in j["parts"]:
                return j["name"]
        for j in joints:
            if _hit(j["name"], [ref]):
                return j["name"]
        return None

    for j in joints:
        if j.get("parent"):
            p = joint_of(j["parent"])
            if p and p != j["name"]:
                j["parent"] = p
            else:
                notes.append(f"{j['name']}: 'on' {j['parent']} is not a moving part, ignored")
                j.pop("parent")
        if j.get("drive"):
            d = joint_of(j["drive"]["joint"])
            if d and d != j["name"]:
                j["drive"]["joint"] = d
            else:
                j.pop("drive")
    return joints, notes


def _animations(joints):
    anims, groups = [], {}
    for j in joints:
        if "drive" not in j:
            groups.setdefault(j["_group"], []).append(j)

    def h(j):
        return j.get("home", 0)

    def full(j):
        return j["max"] if abs(j["max"] - h(j)) >= abs(j["min"] - h(j)) else j["min"]

    for g, js in groups.items():
        n = len(js)
        if g == "Buttons" and n > 1:  # press one after another
            kf = [{"t": 0, "values": {j["name"]: h(j) for j in js}}]
            for k, j in enumerate(js):
                a, b = k / n, (k + 0.5) / n
                kf += [{"t": round(a, 4), "values": {j["name"]: h(j)}},
                       {"t": round((a + b) / 2, 4), "values": {j["name"]: full(j)}},
                       {"t": round(b, 4), "values": {j["name"]: h(j)}}]
            kf.append({"t": 1, "values": {j["name"]: h(j) for j in js}})
        else:
            # home -> max -> min -> home for a joint that can go both ways from home, else home -> end -> home
            two = [j for j in js if j["min"] < h(j) - 1e-6 and j["max"] > h(j) + 1e-6 and g != "Knobs"]
            one = [j for j in js if j not in two]
            kf = [{"t": 0, "values": {j["name"]: h(j) for j in js}}]
            if two:
                kf += [{"t": round(1 / 3, 4), "values": {j["name"]: j["max"] for j in two}},
                       {"t": round(2 / 3, 4), "values": {j["name"]: j["min"] for j in two}}]
            if one:
                kf.append({"t": 0.5, "values": {j["name"]: full(j) for j in one}})
            kf.append({"t": 1, "values": {j["name"]: h(j) for j in js}})
            kf.sort(key=lambda k: k["t"])
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

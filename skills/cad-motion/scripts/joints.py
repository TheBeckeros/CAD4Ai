"""Helpers for <model>.motion.json.

  joints.py info <model.step>
      solids with bounding boxes and cylinder axes (to find pins, shafts, bores)
  joints.py slider-crank <out.motion.json> --center --axis --pin --wrist --slide --crank P --slider P --rod P
      crank about center/axis, rod from crank pin to wrist pin, slider moves along slide
  joints.py four-bar <out.motion.json> --axis --a --b --c --d --crank P --coupler P --rocker P
      crank A-B, coupler B-C, rocker D-C, all pivots parallel to axis

Points and vectors are "x,y,z" in mm in the home pose. P is a comma separated list of part names.
"""
import argparse
import json
import math
import re
import sys

sys.dont_write_bytecode = True  # no __pycache__ inside the app folder


def v(s):
    return [float(c) for c in s.split(",")]


def sub(a, b): return [a[i] - b[i] for i in range(3)]
def add(a, b): return [a[i] + b[i] for i in range(3)]
def mul(a, k): return [x * k for x in a]
def dot(a, b): return sum(a[i] * b[i] for i in range(3))
def cross(a, b): return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
def norm(a): return mul(a, 1 / math.sqrt(dot(a, a)))
def r(x, n=3): return round(x, n) + 0.0


def rot(p, o, k, deg):
    """Rotate point p about axis (o, unit k) by deg, right-hand rule."""
    t = math.radians(deg)
    q = sub(p, o)
    q = add(add(mul(q, math.cos(t)), mul(cross(k, q), math.sin(t))), mul(k, dot(k, q) * (1 - math.cos(t))))
    return add(o, q)


def angle(a, b, k):
    """Signed angle from a to b about k, degrees."""
    return math.degrees(math.atan2(dot(k, cross(a, b)), dot(a, b)))


def unwrap(deg, prev):
    """deg shifted by 360s to be nearest prev, so keyframes never jump a full turn."""
    return deg if prev is None else deg - 360 * round((deg - prev) / 360)


def parts(s):
    return [p for p in s.split(",") if p]


def info(step):
    import cadquery as cq
    src = open(step, encoding="utf-8", errors="ignore").read()
    names = re.findall(r"PRODUCT\('([^']*)'", src)
    print("STEP product names (the assembly root is one of them):", ", ".join(dict.fromkeys(names)))
    for i, s in enumerate(cq.importers.importStep(step).solids().vals()):
        b = s.BoundingBox()
        print(f"solid #{i}: x {b.xmin:.1f}..{b.xmax:.1f}  y {b.ymin:.1f}..{b.ymax:.1f}  z {b.zmin:.1f}..{b.zmax:.1f}  volume {s.Volume():.0f}")
        seen = set()
        for f in s.Faces():
            if f.geomType() != "CYLINDER":
                continue
            c = f._geomAdaptor().Cylinder()
            d, l = c.Axis().Direction(), c.Axis().Location()
            d = [d.X(), d.Y(), d.Z()]
            if max(d, key=abs) < 0:
                d = mul(d, -1)
            p = [l.X(), l.Y(), l.Z()]
            p = sub(p, mul(d, dot(p, d)))  # point on the axis closest to the origin
            key = (round(c.Radius(), 2), *(round(x, 1) for x in p), *(round(x, 2) for x in d))
            if key not in seen:
                seen.add(key)
                print(f"   cylinder R{key[0]}  axis through ({key[1]}, {key[2]}, {key[3]}) dir ({key[4]}, {key[5]}, {key[6]})")


def write(path, joints, keys, name, steps):
    anim = {"name": name, "duration": 3, "keyframes": [{"t": r(i / steps, 4), "values": kv} for i, kv in enumerate(keys)]}
    json.dump({"joints": joints, "animations": [anim]}, open(path, "w", encoding="utf-8"), indent=1)
    for j in joints:
        vals = [k[j["name"]] for k in keys]
        print(f"{j['name']}: {min(vals):.2f} .. {max(vals):.2f}")
    print("written", path)


def span(vals, pad):
    return [r(math.floor(min(vals) - pad)), r(math.ceil(max(vals) + pad))]


def slider_crank(a):
    k, c, p0, w0, s = norm(v(a.axis)), v(a.center), v(a.pin), v(a.wrist), norm(v(a.slide))
    L = math.dist(p0, w0)
    keys, x = [], 0.0
    for i in range(a.steps + 1):
        th = 360 * i / a.steps
        p = rot(p0, c, k, th)
        # w = w0 + x*s with |w - p| = L, take the root nearest the previous x
        q = sub(w0, p)
        bq, cq_ = dot(q, s), dot(q, q) - L * L
        disc = bq * bq - cq_
        if disc < 0:
            sys.exit(f"rod too short at crank {th:.0f} deg")
        x = min((-bq + math.sqrt(disc), -bq - math.sqrt(disc)), key=lambda t: abs(t - x))
        w = add(w0, mul(s, x))
        rod = unwrap(angle(sub(p0, w0), sub(p, w), k), keys[-1]["rod"] if keys else None)
        keys.append({"crank": r(th, 2), "slider": r(x), "rod": r(rod)})
    xs, rs = [kv["slider"] for kv in keys], [kv["rod"] for kv in keys]
    joints = [
        {"name": "crank", "type": "revolute", "parts": parts(a.crank), "origin": c, "axis": k, "min": 0, "max": 360},
        {"name": "slider", "type": "prismatic", "parts": parts(a.slider), "origin": w0, "axis": s,
         "min": span(xs, 1)[0], "max": span(xs, 1)[1], "note": "follows the crank (closed loop, see animation)"},
        {"name": "rod", "type": "revolute", "parts": parts(a.rod), "parent": "slider", "origin": w0, "axis": k,
         "min": span(rs, 5)[0], "max": span(rs, 5)[1], "note": "swings about the wrist pin"},
    ]
    write(a.out, joints, keys, "Crank rotation", a.steps)


def four_bar(a):
    k, A, B0, C0, D = norm(v(a.axis)), v(a.a), v(a.b), v(a.c), v(a.d)
    lc, lr = math.dist(B0, C0), math.dist(D, C0)
    keys, C, start = [], C0, None
    for i in range(a.steps + 1):
        th = a.min + (a.max - a.min) * i / a.steps
        B = rot(B0, A, k, th)
        # C on the circle around D (radius lr) and around B (radius lc), both in the plane normal to k
        d = sub(B, D)
        d = sub(d, mul(k, dot(d, k)))
        dd = math.sqrt(dot(d, d))
        if dd > lc + lr or dd < abs(lc - lr):
            sys.exit(f"linkage cannot close at crank {th:.1f} deg, limit --min/--max")
        u = norm(d)
        along = (lr * lr - lc * lc + dd * dd) / (2 * dd)
        h = math.sqrt(max(0.0, lr * lr - along * along))
        base = add(D, mul(u, along))
        C = min((add(base, mul(cross(k, u), h)), add(base, mul(cross(k, u), -h))), key=lambda q: math.dist(q, C))
        prev = keys[-1] if keys else {"rocker": None, "coupler": None}
        rocker = unwrap(angle(sub(C0, D), sub(C, D), k), prev["rocker"])
        coupler = unwrap(angle(sub(C0, B0), sub(C, B), k) - th, prev["coupler"])  # relative to the crank that carries it
        keys.append({"crank": r(th, 2), "rocker": r(rocker), "coupler": r(coupler)})
    ro, co = [kv["rocker"] for kv in keys], [kv["coupler"] for kv in keys]
    joints = [
        {"name": "crank", "type": "revolute", "parts": parts(a.crank), "origin": A, "axis": k, "min": a.min, "max": a.max},
        {"name": "rocker", "type": "revolute", "parts": parts(a.rocker), "origin": D, "axis": k,
         "min": span(ro, 5)[0], "max": span(ro, 5)[1], "note": "follows the crank (closed loop, see animation)"},
        {"name": "coupler", "type": "revolute", "parts": parts(a.coupler), "parent": "crank", "origin": B0, "axis": k,
         "min": span(co, 5)[0], "max": span(co, 5)[1], "note": "follows the crank (closed loop, see animation)"},
    ]
    write(a.out, joints, keys, "Crank rotation", a.steps)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("info").add_argument("step")
    s = sp.add_parser("slider-crank")
    s.add_argument("out")
    for n in ("center", "axis", "pin", "wrist", "slide", "crank", "slider", "rod"):
        s.add_argument("--" + n, required=True)
    s.add_argument("--steps", type=int, default=36)
    f = sp.add_parser("four-bar")
    f.add_argument("out")
    for n in ("axis", "a", "b", "c", "d", "crank", "coupler", "rocker"):
        f.add_argument("--" + n, required=True)
    f.add_argument("--min", type=float, default=0)
    f.add_argument("--max", type=float, default=360)
    f.add_argument("--steps", type=int, default=36)
    a = ap.parse_args()
    {"info": lambda: info(a.step), "slider-crank": lambda: slider_crank(a), "four-bar": lambda: four_bar(a)}[a.cmd]()


if __name__ == "__main__":
    main()

"""Design-intent checks written in the model script itself (plain Python, CadQuery stays as it is).

    import os, sys; sys.path.insert(0, os.path.expanduser("~/.CAD4Ai/lib"))
    from cadtools.expect import expect
    ...build, cq.exporters.export / assy.save(...)...
    expect("deska").size(100, 60, 5).holes(4, d=5.5, pitch=(80, 40)).mass(max=300)
    expect("hridel", "lozisko").clearance(min=0)       # no overlap (touching allowed)
    expect.no_collisions()                               # whole assembly, fastener overlaps ignored

Rules are only collected while the script runs; when it ends, they are checked on the STEP it exported
(the last .step written) and a short report is printed:  [expect] 6/7 OK / FAIL deska.holes: ...
The result is also kept for `cad4ai after`, so the hook shows it next to the diff. Sandbox runs (doctor,
optimize) skip the checks. A rule never stops the script or the export.
"""
import atexit
import json
import os
import sys

_RULES = []
_EXPORTS = []
_DONE = [False]


class _Rule:
    def __init__(self, names):
        self.names = list(names)
        self.checks = []

    def _add(self, kind, **kw):
        self.checks.append((kind, kw))
        return self

    def size(self, x=None, y=None, z=None, tol=0.05):
        """Envelope [mm] along X, Y, Z (None = do not check that axis)."""
        return self._add("size", x=x, y=y, z=z, tol=tol)

    def holes(self, n=None, d=None, tol=0.05, pitch=None, pcd=None, axis=None, through=None):
        """Number of holes of diameter d (all diameters if None); optional grid pitch (px, py), PCD, axis."""
        return self._add("holes", n=n, d=d, tol=tol, pitch=pitch, pcd=pcd, axis=axis, through=through)

    def mass(self, min=None, max=None):  # noqa: A002
        return self._add("mass", min=min, max=max)

    def volume(self, min=None, max=None):  # noqa: A002
        return self._add("volume", min=min, max=max)

    def count(self, n):
        """How many part instances match the name(s)."""
        return self._add("count", n=n)

    def at(self, x=None, y=None, z=None, tol=0.05):
        """Minimum corner of the envelope."""
        return self._add("at", x=x, y=y, z=z, tol=tol)

    def inside(self, xmin=None, ymin=None, zmin=None, xmax=None, ymax=None, zmax=None):
        """The parts stay within these limits."""
        return self._add("inside", xmin=xmin, ymin=ymin, zmin=zmin, xmax=xmax, ymax=ymax, zmax=zmax)

    def clearance(self, min=None, max=None):  # noqa: A002
        """Distance between the first name and the others (0 = touching allowed, no overlap)."""
        return self._add("clearance", min=min, max=max)

    def no_collisions(self, ignore_fasteners=True):
        return self._add("collide", ignore=ignore_fasteners)

    def valid(self):
        return self._add("valid")


def expect(*names):
    r = _Rule(names or ["*"])
    _RULES.append(r)
    return r


def _no_collisions(ignore_fasteners=True):
    return expect("*").no_collisions(ignore_fasteners)


expect.no_collisions = _no_collisions


# ---------------------------------------------------------------- remember what the script exports

def _patch():
    try:
        import cadquery as cq
        from cadquery import exporters as ex
    except Exception:  # noqa: BLE001
        return

    def rec(p):
        p = os.path.abspath(str(p))
        if p.lower().endswith((".step", ".stp")):
            _EXPORTS.append(p)

    orig = ex.export

    def export(w, fname, *a, **k):
        r = orig(w, fname, *a, **k)
        rec(fname)
        return r
    ex.export = export
    for cls, names in ((cq.Assembly, ("save", "export")), (cq.Shape, ("exportStep",))):
        for n in names:
            f = getattr(cls, n, None)
            if f is None:
                continue

            def wrap(f):
                def g(self, path, *a, **k):
                    r = f(self, path, *a, **k)
                    rec(path)
                    return r
                return g
            setattr(cls, n, wrap(f))


_patch()


# ---------------------------------------------------------------- evaluation

def _fmt(v):
    return f"{v:g}" if isinstance(v, (int, float)) else str(v)


def evaluate(step, rules):
    """Cheap rules now (only the parts they name are measured); no_collisions rules are returned as
    deferred - the hook / `cad4ai after` checks them on all cores, incrementally, with the shared cache."""
    from . import core, digest
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    model = core.load(step)
    memo = {}

    def pd(inst, detail):
        k = (inst.name, detail)
        if k not in memo:
            memo[k] = digest.part_digest(inst, detail)
        return memo[k]
    res, deferred = [], []

    def sel(names):
        try:
            return core.find(model, names)
        except SystemExit:
            return None

    for r in rules:
        label = ",".join(r.names)
        insts = sel(r.names)
        for kind, kw in r.checks:
            tag = f"{label}.{kind}"
            if insts is None:
                res.append((False, tag, f"no part named {label}"))
                continue
            if kind == "collide":
                deferred.append({"names": r.names, "ignore": kw.get("ignore", True)})
                continue
            need = kind in ("holes", "valid")
            ps = [pd(i, need) for i in insts] if kind not in ("count", "clearance") else []
            try:
                ok, msg = _check(kind, kw, insts, ps, model, BRepExtrema_DistShapeShape, core)
            except Exception as e:  # noqa: BLE001
                ok, msg = False, f"check error {type(e).__name__}: {e}"
            res.append((ok, tag, msg))
    return res, deferred


def _env(ps):
    lo = [min(p["min"][i] for p in ps) for i in range(3)]
    hi = [max(p["max"][i] for p in ps) for i in range(3)]
    return lo, hi


def _check(kind, kw, insts, ps, model, Dist, core):
    if kind == "size":
        lo, hi = _env(ps)
        got = [hi[i] - lo[i] for i in range(3)]
        bad = [f"{'XYZ'[i]} {got[i]:.2f}≠{_fmt(w)}" for i, w in enumerate((kw["x"], kw["y"], kw["z"]))
               if w is not None and abs(got[i] - w) > kw["tol"]]
        return not bad, ("; ".join(bad) if bad else f"{got[0]:.2f}x{got[1]:.2f}x{got[2]:.2f}")
    if kind == "at":
        lo, _ = _env(ps)
        bad = [f"{'XYZ'[i]} {lo[i]:.2f}≠{_fmt(w)}" for i, w in enumerate((kw["x"], kw["y"], kw["z"]))
               if w is not None and abs(lo[i] - w) > kw["tol"]]
        return not bad, "; ".join(bad) if bad else "ok"
    if kind == "inside":
        lo, hi = _env(ps)
        bad = []
        for i, a in enumerate("xyz"):
            if kw[a + "min"] is not None and lo[i] < kw[a + "min"] - 1e-6:
                bad.append(f"{a}min {lo[i]:.2f}<{_fmt(kw[a + 'min'])}")
            if kw[a + "max"] is not None and hi[i] > kw[a + "max"] + 1e-6:
                bad.append(f"{a}max {hi[i]:.2f}>{_fmt(kw[a + 'max'])}")
        return not bad, "; ".join(bad) if bad else "ok"
    if kind in ("mass", "volume"):
        key = "mass_g" if kind == "mass" else "vol"
        v = sum(p[key] for p in ps)
        ok = (kw["min"] is None or v >= kw["min"]) and (kw["max"] is None or v <= kw["max"])
        return ok, f"{v:.1f}" + (" g" if kind == "mass" else " mm3") + ("" if ok else f" (want {_fmt(kw['min'])}..{_fmt(kw['max'])})")
    if kind == "count":
        return len(insts) == kw["n"], f"{len(insts)} parts" + ("" if len(insts) == kw["n"] else f" (want {kw['n']})")
    if kind == "valid":
        bad = [p["name"] for p in ps if p.get("INVALID")]
        return not bad, ("invalid: " + ", ".join(bad)) if bad else "valid"
    if kind == "holes":
        groups = [g for p in ps for g in p.get("holes", [])]
        if kw["d"] is not None:
            groups = [g for g in groups if abs(g["d"] - kw["d"]) <= kw["tol"]]
        if kw["axis"]:
            groups = [g for g in groups if str(g["axis"]).lstrip("-") == kw["axis"].upper().lstrip("-")]
        if kw["through"] is not None:
            groups = [g for g in groups if bool(g.get("through")) == kw["through"]]
        n = sum(g["n"] for g in groups)
        probs = []
        if kw["n"] is not None and n != kw["n"]:
            allh = ", ".join(f"{g['n']}xØ{g['d']}" for p in ps for g in p.get("holes", [])) or "none"
            probs.append(f"{n} holes" + (f" Ø{_fmt(kw['d'])}" if kw["d"] else "") + f", want {kw['n']} (part has: {allh})")
        if kw["pitch"] is not None:
            want = sorted(float(x) for x in kw["pitch"])
            hit = False
            for g in groups:
                pv = [v for v in (g.get("pitch") or {}).values() if isinstance(v, (int, float))]
                if sorted(pv) == [] and len(want) == 1:
                    continue
                if len(pv) == len(want) and all(abs(a - b) <= kw["tol"] for a, b in zip(sorted(pv), want)):
                    hit = True
                elif len(want) == 1 and any(abs(v - want[0]) <= kw["tol"] for v in pv):
                    hit = True
            if not hit:
                probs.append(f"pitch {want} not found (got {[g.get('pitch') for g in groups]})")
        if kw["pcd"] is not None and not any(g.get("pcd") and abs(g["pcd"] - kw["pcd"]) <= kw["tol"] for g in groups):
            probs.append(f"PCD {_fmt(kw['pcd'])} not found (got {[g.get('pcd') for g in groups if g.get('pcd')]})")
        return not probs, "; ".join(probs) if probs else f"{n} holes"
    if kind == "clearance":
        a, others = insts[0], insts[1:]
        if not others:
            return False, "needs two part names"
        ds = []
        for b in others:
            d = Dist(a.shape, b.shape)
            v = d.Value() if d.IsDone() else float("nan")
            if v < 1e-6:
                from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
                ov = core.props(BRepAlgoAPI_Common(a.shape, b.shape).Shape())[0]
                v = -ov if ov > 1e-3 else 0.0  # negative = overlap volume
            ds.append((b.name, v))
        bad = [(n, v) for n, v in ds if (kw["min"] is not None and v < kw["min"] - 1e-6) or (kw["max"] is not None and v > kw["max"] + 1e-6)]
        txt = ", ".join(f"{n}: {'overlap ' + format(-v, '.2f') + ' mm3' if v < 0 else format(v, '.3f') + ' mm'}" for n, v in (bad or ds))
        return not bad, txt
    if kind == "collide":
        from . import collide
        c = collide.check(model_path(model), 0.0, [i.name for i in insts] if len(insts) < len(model) else None, parallel=False)
        coll = c["collisions"] + ([] if kw["ignore"] else c["fastener_overlaps"])
        return not coll, ("; ".join(f"{x['a']} x {x['b']} {x['overlap_mm3']} mm3" for x in coll[:6]) if coll else "none")
    return False, f"unknown check {kind}"


def model_path(model):
    return _CUR[0]


_CUR = [None]


def result_file(step):
    from . import core
    return os.path.join(core.CACHE, "expect", core.model_key(step) + ".json")


def _report():
    if _DONE[0] or not _RULES or os.environ.get("CAD4AI_OUT"):
        return
    _DONE[0] = True
    steps = [p for p in _EXPORTS if os.path.isfile(p)]
    if not steps:
        print("[expect] no .step exported - rules not checked", file=sys.stderr)
        return
    step = steps[-1]
    _CUR[0] = step
    from . import core
    try:
        res, deferred = evaluate(step, _RULES)
    except Exception as e:  # noqa: BLE001
        print(f"[expect] could not check: {type(e).__name__}: {e}", file=sys.stderr)
        return
    ok = sum(1 for r in res if r[0])
    lines = [f"[expect] {ok}/{len(res)} OK ({os.path.basename(step)})" +
             (f"; {len(deferred)} collision rule(s) checked by the CAD4Ai hook" if deferred else "")]
    lines += [f"  FAIL {t}: {m}" for good, t, m in res if not good]
    txt = "\n".join(lines)
    print(txt, file=sys.stderr if ok < len(res) else sys.stdout)
    p = result_file(step)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"key": core.file_key(step), "text": txt, "ok": ok, "n": len(res), "deferred": deferred}, f,
                  ensure_ascii=False)


def flush():
    """Check and reset (the viewer's warm runner calls this after every script run)."""
    try:
        _report()
    finally:
        _RULES.clear()
        _EXPORTS.clear()
        _DONE[0] = False


atexit.register(_report)

"""Parameter optimisation of a model script, all runs local and in parallel (sandbox copies).

    cad4ai optimize model.py --vary WALL=1..6 --vary RIB_H=2..12 --minimize mass
        [--subject "fem.max_disp_mm<0.2" --fem "part=Bracket fix=hole:6.6 load=zmax=0,0,-200"]
        [--subject "size.z<=40" --subject "collisions==0"] [--budget 40] [--apply]

Metrics available for --minimize / --maximize / --subject:
  mass (g), volume (mm3), size.x size.y size.z (envelope), parts, collisions (count), min_clearance,
  fem.max_disp_mm, fem.vm_p99_5_MPa, fem.safety_vs_yield_p99_5 (only when --fem is given).
1 parameter: bounded golden search; more: a parallel random + refine search (Latin hypercube, then a
shrinking box around the best). Constraint violations are penalised. Each evaluation = one script run.
"""
import math
import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from . import core, sandbox


def _metrics(step, need_coll, fem_spec):
    from . import digest, collide, fem
    d = digest.digest(step, detail=False, parallel=False)
    m = {"mass": d["mass_g"], "volume": sum(p["vol"] for p in d["parts"]), "parts": d["parts_n"],
         "size.x": d["size"][0], "size.y": d["size"][1], "size.z": d["size"][2], "invalid": len(d["invalid"])}
    if need_coll:
        c = collide.check(step, 1.0)
        m["collisions"] = len(c["collisions"])
        ds = [x["dist"] for x in c["clearance_below_limit"]]
        m["min_clearance"] = min(ds) if ds else 1.0
    if fem_spec:
        r = fem.solve(step, fem_spec["part"], fem_spec["fix"], fem_spec["load"],
                      elements=fem_spec.get("elements", 25000))
        for k in ("max_disp_mm", "vm_p99_5_MPa", "safety_vs_yield_p99_5"):
            m["fem." + k] = r[k]
    return m


def parse_fem(spec):
    """'part=Bracket fix=hole:6.6 load=zmax=0,0,-200 elements=30000' (fix/load may repeat)."""
    out = {"fix": [], "load": []}
    for tok in spec.split():
        k, v = tok.split("=", 1)
        if k in ("fix", "load"):
            out[k].append(v)
        elif k == "elements":
            out[k] = int(v)
        else:
            out[k] = v
    return out


COND = re.compile(r"^\s*([\w.]+)\s*(<=|>=|<|>|==)\s*(-?[\d.eE+-]+)\s*$")


def _penalty(m, conds):
    pen, bad = 0.0, []
    for c in conds:
        k, op, v = COND.match(c).groups()
        v = float(v)
        x = m.get(k)
        if x is None:
            raise ValueError(f"unknown metric {k}")
        ok = {"<": x < v, "<=": x <= v, ">": x > v, ">=": x >= v, "==": abs(x - v) < 1e-9}[op]
        if not ok:
            bad.append(c)
            pen += 1 + abs(x - v) / (abs(v) + 1e-9)
    return pen, bad


def optimise(script, vary, objective, sense=1, subject=(), fem_spec=None, budget=30, workers=None, apply=False,
             step_hint=None):
    workers = workers or max(2, min(8, (os.cpu_count() or 4) // 2))
    names = list(vary)
    lo = np.array([vary[n][0] for n in names], float)
    hi = np.array([vary[n][1] for n in names], float)
    metrics = [m.group(1) for m in (COND.match(c) for c in subject) if m]
    if len(metrics) != len(subject):
        bad = [c for c in subject if not COND.match(c)]
        raise ValueError(f"condition not understood: {bad} (use e.g. size.z<=40, collisions==0)")
    need_coll = any(m in ("collisions", "min_clearance") for m in metrics) or objective in ("collisions", "min_clearance")
    hist = []

    def evaluate(x):
        vals = {n: float(round(v, 4)) for n, v in zip(names, x)}
        r = sandbox.run(script, values=vals, keep=True, timeout=900)
        try:
            if not r["ok"]:
                return {"x": vals, "ok": False, "error": r["stderr"].strip().splitlines()[-1][:200] if r["stderr"] else "failed"}
            f = sandbox.main_step(r["files"], script) if not step_hint else os.path.basename(step_hint)
            if not f:
                return {"x": vals, "ok": False, "error": "script exported no STEP"}
            m = _metrics(os.path.join(r["out_dir"], f), need_coll, fem_spec)
            pen, bad = _penalty(m, subject)
            score = sense * m[objective] + pen * (abs(m[objective]) + 1) * 10
            return {"x": vals, "ok": True, "m": m, "score": score, "violates": bad}
        finally:
            shutil.rmtree(r["out_dir"], ignore_errors=True)

    def batch(X):
        with ThreadPoolExecutor(max_workers=workers) as ex:
            res = list(ex.map(evaluate, X))
        hist.extend(res)
        return res

    rng = np.random.default_rng(1)
    if len(names) == 1:
        # parallel grid then golden refine
        X = [lo + (hi - lo) * t for t in np.linspace(0, 1, max(workers, 5))]
        batch([x for x in X])
        for _ in range(max(1, (budget - len(hist)) // workers)):
            ok = [h for h in hist if h["ok"]]
            if not ok:
                break
            best = min(ok, key=lambda h: h["score"])
            xb = best["x"][names[0]]
            span = (hi[0] - lo[0]) / (len(hist) / workers + 1) ** 1.5
            a, b = max(lo[0], xb - span), min(hi[0], xb + span)
            batch([np.array([v]) for v in np.linspace(a, b, workers)])
    else:
        n0 = max(workers, min(budget // 2, 4 * len(names) + 4))
        # Latin hypercube
        cut = (np.argsort(rng.random((len(names), n0)), axis=1).T + rng.random((n0, len(names)))) / n0
        batch([lo + (hi - lo) * c for c in cut])
        box = (hi - lo) / 2
        while len(hist) < budget:
            ok = [h for h in hist if h["ok"]]
            if not ok:
                break
            best = min(ok, key=lambda h: h["score"])
            xb = np.array([best["x"][n] for n in names])
            box *= 0.6
            X = [np.clip(xb + box * (2 * rng.random(len(names)) - 1), lo, hi) for _ in range(min(workers, budget - len(hist)))]
            batch(X)
    ok = [h for h in hist if h["ok"]]
    feas = [h for h in ok if not h["violates"]]
    best = min(feas or ok, key=lambda h: h["score"]) if ok else None
    res = {"ok": bool(best), "objective": ("min " if sense > 0 else "max ") + objective, "subject": list(subject),
           "runs": len(hist), "failed_runs": len(hist) - len(ok), "feasible": bool(feas)}
    if best:
        res["best"] = {"params": best["x"], "metrics": best["m"]}
        top = sorted(feas or ok, key=lambda h: h["score"])[:5]
        res["top5"] = [{"params": h["x"], objective: h["m"][objective]} for h in top]
    if not ok:
        res["errors"] = list({h.get("error") for h in hist})[:5]
    if apply and best and feas:
        import server  # write_params keeps the script's formatting
        res["applied"] = server.write_params(script, best["x"])
    return res


def parse_vary(items):
    out = {}
    for it in items:
        m = re.match(r"^([A-Z][A-Z0-9_]*)=(-?[\d.]+)\.\.(-?[\d.]+)$", it.strip())
        if not m:
            raise ValueError(f"--vary NAME=lo..hi, got {it}")
        out[m.group(1)] = (float(m.group(2)), float(m.group(3)))
    return out

"""Script doctor: run a failing model script, find what broke and try fixes locally (many runs in parallel).

- Locates the failing line of the user's script (not CadQuery internals) and classifies the error.
- fillet / chamfer that fails: bisects the radius on that line (all cores at once) and reports the largest
  value that works, e.g. "fillet R3 fails; works up to R2.4 (k=0.80)".
- boolean / BRep_API failure: re-runs with the operation's line removed to tell whether it is the cause.
- selector that selects nothing / wrong count: says so with the line.
Nothing in the real script is changed (sandbox copies; exports are redirected).
"""
import os
import re
from concurrent.futures import ThreadPoolExecutor

from . import sandbox

CATS = [
    ("fillet", re.compile(r"\.(fillet|fillet2D)\(")),
    ("chamfer", re.compile(r"\.(chamfer|chamfer2D)\(")),
    ("shell", re.compile(r"\.shell\(")),
    ("loft", re.compile(r"\.loft\(")),
    ("sweep", re.compile(r"\.sweep\(")),
    ("boolean", re.compile(r"\.(cut|union|intersect|cutBlind|cutThruAll|fuse|__sub__|__add__)\(|\s[-+&]\s")),
    ("selector", re.compile(r"\.(faces|edges|vertices|wires|solids)\(")),
]

HINTS = {
    "fillet": "radius too big for a neighbouring face/edge or fillet over a tangent/seam edge; fillet before booleans or select fewer edges",
    "chamfer": "chamfer longer than the adjacent edge; reduce it or chamfer before the cut",
    "shell": "shell thickness bigger than the smallest radius/feature, or a face to remove that touches a fillet",
    "loft": "wires with different edge counts or orientation; use ruled=True or rebuild the profiles",
    "sweep": "profile not perpendicular to the path start or self-intersecting path (radius < profile)",
    "boolean": "coplanar/tangent faces or an invalid operand; shift one operand by 0.01 mm or check validity first",
    "selector": "the selector matched nothing or several objects; print .size() before the operation",
}


def _user_frame(stderr, script):
    """Last traceback frame inside the user's script (or its local modules)."""
    folder = os.path.dirname(os.path.abspath(script)).lower()
    frames = re.findall(r'File "([^"]+)", line (\d+)', stderr)
    for f, ln in reversed(frames):
        if os.path.abspath(f).lower().startswith(folder) and ".cad4ai_" not in f:
            return f, int(ln)
    return (frames[-1][0], int(frames[-1][1])) if frames else (None, None)


def _err_line(stderr):
    lines = [l for l in stderr.strip().splitlines() if l.strip()]
    for l in reversed(lines):
        if re.match(r"^[A-Za-z_.]+(Error|Exception|NotDone|Failure)\b|^[A-Za-z_]+: ", l.strip()):
            return l.strip()[:300]
    return lines[-1].strip()[:300] if lines else ""


def _wrap_arg(line, method):
    """'.fillet(R)' -> '.fillet(_c4_r(R))' for the first call of method on the line."""
    i = line.find("." + method + "(")
    if i < 0:
        return None
    j = i + len(method) + 2
    depth, k = 1, j
    while k < len(line) and depth:
        if line[k] in "([{":
            depth += 1
        elif line[k] in ")]}":
            depth -= 1
        k += 1
    inner = line[j:k - 1]
    # first positional argument only
    d, cut = 0, len(inner)
    for n, ch in enumerate(inner):
        if ch in "([{":
            d += 1
        elif ch in ")]}":
            d -= 1
        elif ch == "," and d == 0:
            cut = n
            break
    first, rest = inner[:cut], inner[cut:]
    if not first.strip() or "=" in first.split("(")[0]:
        return None
    return line[:j] + f"_c4_r({first})" + rest + line[k - 1:]


def _bisect_radius(script, line_no, method, workers):
    def transform(src):
        L = src.split("\n")
        w = _wrap_arg(L[line_no - 1], method)
        if w is None:
            raise ValueError("cannot wrap the radius argument")
        L[line_no - 1] = w
        return "\n".join(L)

    def trial(k):
        r = sandbox.run(script, transform=transform, env={"CAD4AI_K": repr(k)}, timeout=600)
        return k, r

    lo, hi, base_r, tried = 0.0, 1.0, None, []
    grid = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.05][:max(4, workers)]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for k, r in ex.map(trial, grid):
            tried.append((k, r["ok"]))
            if r["radii"] and base_r is None:
                base_r = r["radii"][0]
        ok = [k for k, o in tried if o]
        if not ok:
            return {"works": False, "tried_k": grid, "nominal": base_r}
        lo = max(ok)
        bad = [k for k, o in tried if not o and k > lo]
        hi = min(bad) if bad else 1.0
        # refine between lo and hi in parallel
        for _ in range(2):
            ks = [lo + (hi - lo) * i / (workers + 1) for i in range(1, workers + 1)]
            for k, r in ex.map(trial, ks):
                if r["ok"] and k > lo:
                    lo = k
            bad = [k for k in ks if k > lo]
            hi = min(bad) if bad else hi
    res = {"works": True, "k_max": round(lo, 3), "nominal": base_r}
    if base_r is not None:
        res["max_value"] = round(base_r * lo, 3)
    return res


def diagnose(script, workers=None, traceback_text=None):
    """traceback_text: the failure already seen (e.g. by the hook) - then the script is not run again
    just to see it fail; only the experiments (radius search, line removal) run."""
    workers = workers or max(2, min(10, (os.cpu_count() or 4) - 2))
    se = traceback_text if traceback_text and "Traceback" in traceback_text else None
    if se is None:
        first = sandbox.run(script, timeout=900)
        if first["ok"]:
            return {"ok": True, "status": "script runs fine", "ms": first["ms"], "exports": first["files"]}
        se = first["stderr"]
    else:
        se = se[se.rfind("Traceback"):]
    f, ln = _user_frame(se, script)
    err = _err_line(se)
    out = {"ok": False, "error": err, "file": f, "line": ln}
    src_line = ""
    if f and ln and os.path.isfile(f):
        with open(f, encoding="utf-8") as fh:
            L = fh.read().split("\n")
        src_line = L[ln - 1].strip() if 0 < ln <= len(L) else ""
        out["code"] = src_line
        out["context"] = [f"{i + 1}: {L[i]}" for i in range(max(0, ln - 4), min(len(L), ln + 1))]
    cat = next((c for c, rx in CATS if rx.search(src_line)), None)
    if "SyntaxError" in err or "IndentationError" in err:
        cat = "syntax"
    elif "NameError" in err or "AttributeError" in err or "TypeError" in err or "ImportError" in err or "ModuleNotFound" in err:
        cat = cat if cat in ("selector",) else "python"
    out["category"] = cat or "other"
    if cat in HINTS:
        out["hint"] = HINTS[cat]
    # automatic experiments (only on the main script's own line)
    same_file = f and os.path.abspath(f).lower() == os.path.abspath(script).lower()
    if cat in ("fillet", "chamfer") and same_file:
        method = re.search(r"\.(fillet2D|fillet|chamfer2D|chamfer)\(", src_line).group(1)
        try:
            out["radius_search"] = _bisect_radius(script, ln, method, workers)
            rs = out["radius_search"]
            if rs.get("works") and rs.get("max_value") is not None:
                out["fix"] = f"{method} works up to {rs['max_value']} (nominal {rs['nominal']}, factor {rs['k_max']}) on line {ln}"
            elif not rs.get("works"):
                out["fix"] = f"{method} on line {ln} fails even at 5 % of the value: wrong edges selected or geometry issue, not the size"
        except ValueError as e:
            out["radius_search"] = str(e)
    if cat in ("boolean", "fillet", "chamfer", "shell") and same_file and "fix" not in out:
        # is this line the only problem? comment it out (keep the assignment if any) and run
        def drop(src):
            L = src.split("\n")
            line = L[ln - 1]
            m = re.match(r"^(\s*)(\w+)\s*=\s*(\w+)\s*\.", line)
            L[ln - 1] = (f"{m.group(1)}{m.group(2)} = {m.group(3)}" if m else re.match(r"^\s*", line).group(0) + "pass") + "  # removed by CAD4Ai doctor"
            return "\n".join(L)
        r = sandbox.run(script, transform=drop, timeout=900)
        out["without_this_line"] = "script runs" if r["ok"] else f"still fails: {_err_line(r['stderr'])}"
    out["stderr_tail"] = "\n".join(se.strip().splitlines()[-6:])
    return out

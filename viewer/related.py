"""Which script parameters drive a part (or a clicked place), and which script lines build it.

Used by the viewer's "Show related parameters" (context menu) and by the script map sent with notes
to Claude (so Claude reads a few dozen lines instead of the whole script).

How: the part name is looked up as a string in the model script and in its local modules (imports that
are .py files next to it or in a folder it adds to sys.path): exact, else the longest literal piece of it
(e.g. "MCP2200_klavesy" for MCP2200_klavesy_1 built by f"{nm}_{i}"). From the expression that names it, a
backward slice inside the enclosing function follows the variables (assignments, for-loop targets) to the
UPPER_CASE parameters, also when read as attributes (g.SOCKET_FLANGE). Function arguments are followed to
the calls of that function; local functions called on the way add the parameters they use. Fewer hops =
more related. Numbers measured at the click (diameter, distance…) equal to a parameter value (or 2x / half)
also count.
"""
import ast
import os
import re


def _names(node, params=None):
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute) and n.attr.isupper():
            out.add(n.attr)   # g.SOCKET_FLANGE, cfg.WIDTH
    return out


def _callee(c):
    f = c.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None


def _calls(node):
    return {k for n in ast.walk(node) if isinstance(n, ast.Call) for k in [_callee(n)] if k}


def _parents(tree):
    par = {}
    for p in ast.walk(tree):
        for c in ast.iter_child_nodes(p):
            par[c] = p
    return par


class _File:
    def __init__(self, path):
        self.path = path
        with open(path, encoding="utf-8") as f:
            self.tree = ast.parse(f.read())
        self.par = _parents(self.tree)
        self.funcs = {n.name: n for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)}


def local_modules(script):
    """The model script plus the local .py modules it imports (same folder or a folder put on sys.path)."""
    here = os.path.dirname(os.path.abspath(script))
    with open(script, encoding="utf-8") as f:
        src = f.read()
    dirs = [here] + [os.path.join(here, d) for d in re.findall(r"sys\.path\.(?:insert|append)\([^)]*?[\"']([\w./\\-]+)[\"']\s*\)", src)]
    tree = ast.parse(src)
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
            mods.add(n.module.split(".")[0])
    out = [os.path.abspath(script)]
    for m in sorted(mods):
        for d in dirs:
            p = os.path.join(d, m + ".py")
            if os.path.isfile(p) and os.path.abspath(p) not in out:
                out.append(os.path.abspath(p))
                break
    return out


def _naming(n, par):
    """Is this string where a part gets its name (name=..., first item of a tuple, {"name": ...})?"""
    p = par.get(n)
    if isinstance(p, ast.keyword) and p.arg in ("name", "nm", "label"):
        return True
    if isinstance(p, ast.Tuple) and p.elts and p.elts[0] is n:
        return True
    if isinstance(p, ast.Dict):
        for k, v in zip(p.keys, p.values):
            if v is n and isinstance(k, ast.Constant) and k.value == "name":
                return True
    return False


def _str_hits(fl, part):
    hits = []
    for n in ast.walk(fl.tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and len(n.value) >= 2:
            if isinstance(fl.par.get(n), ast.JoinedStr):
                continue
            v = n.value
            k = 1.0 if _naming(n, fl.par) else 0.55   # a comparison like o["name"] == "PLAST" says less
            if v == part:
                hits.append((n, k))
            elif len(v) >= 4 and re.fullmatch(r"[\w\- .]+", v) and part.startswith(v):
                hits.append((n, k * (0.5 + 0.45 * len(v) / len(part))))
        elif isinstance(n, ast.JoinedStr):
            # f"{nm}_{i}": a pattern the name has to fit (placement loops of repeated parts)
            pat = "".join(re.escape(x.value) if isinstance(x, ast.Constant) else ".+" for x in n.values)
            lit = sum(len(x.value) for x in n.values if isinstance(x, ast.Constant))
            if lit >= 3 and re.fullmatch(pat, part):   # f"{nm}_{i}" alone fits every part: no signal
                k = 1.0 if _naming(n, fl.par) else 0.55
                hits.append((n, k * (0.6 + 0.35 * lit / len(part))))
    return hits


def _expr_scope(node, par):
    """The smallest piece that describes one part: a dict(...)/tuple/list element, else the statement."""
    cur = node
    while cur in par and not isinstance(cur, ast.stmt):
        p = par[cur]
        if isinstance(p, (ast.List, ast.Tuple, ast.Set)) and isinstance(cur, (ast.Call, ast.Tuple, ast.Dict)):
            return cur
        cur = p
    return cur


def _stmt_of(node, par):
    while node in par and not isinstance(node, ast.stmt):
        node = par[node]
    return node


def related(script, part=None, values=(), param_names=None, module_vals=None, max_hops=4):
    """-> {"params": [{"name", "score", "why"}], "lines": [{"file", "from", "to"}], "found": bool}"""
    files = [_File(p) for p in local_modules(script)]
    main = files[0]
    if param_names is None:
        param_names = {t.id for n in main.tree.body if isinstance(n, ast.Assign) for t in n.targets
                       if isinstance(t, ast.Name) and t.id.isupper()}
    params = set(param_names)
    if module_vals is None:
        module_vals = {}
        for n in main.tree.body:
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
                try:
                    module_vals[n.targets[0].id] = ast.literal_eval(n.value)
                except (ValueError, SyntaxError):
                    pass
    allfuncs = {}
    for fl in files:
        for k, v in fl.funcs.items():
            allfuncs.setdefault(k, (fl, v))

    fparams = {}

    def func_params(name, seen=()):
        if name in fparams:
            return fparams[name]
        if name not in allfuncs or name in seen:
            return set()
        fn = allfuncs[name][1]
        out = _names(fn) & params
        for c in _calls(fn) - {name}:
            out |= func_params(c, seen + (name,))
        fparams[name] = out
        return out

    score, why, lines = {}, {}, []

    def add(p, s, w):
        if s > score.get(p, 0) + 1e-9:
            score[p], why[p] = s, w

    def note_lines(fl, node):
        lines.append((fl.path, node.lineno, getattr(node, "end_lineno", node.lineno)))

    def slice_from(fl, start, fn, hit, hop0, budget):
        """Backward slice from the names in `start` inside function `fn` (or the module)."""
        body = fn if fn else fl.tree
        defs = {}
        for s in ast.walk(body):
            if isinstance(s, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                tg = s.targets if isinstance(s, ast.Assign) else [s.target]
                for t in tg:
                    for nm in _names(t):
                        defs.setdefault(nm, []).append((s, s.value))
            elif isinstance(s, (ast.For, ast.comprehension)):
                for nm in _names(s.target):
                    defs.setdefault(nm, []).append((s if isinstance(s, ast.For) else None, s.iter))
        args = [a.arg for a in fn.args.args] if fn else []
        frontier, seen = _names(start) | _calls(start), set()
        for hop in range(hop0, max_hops + 1):
            w = 0.75 ** hop
            nxt = set()
            for nm in frontier - seen:
                seen.add(nm)
                if nm in params:
                    add(nm, hit * w, "used where the part is built" if hop == 0 else f"feeds the part ({hop} step{'s' if hop > 1 else ''} back)")
                    continue
                if nm in allfuncs and nm != (fn.name if fn else None):
                    for p in func_params(nm):
                        add(p, hit * w * 0.6, f"inside {nm}()")
                    continue
                if nm in args and fn and budget > 0:
                    # argument: follow the calls of this function, the matching argument there
                    i = args.index(nm)
                    for fl2 in files:
                        for c in ast.walk(fl2.tree):
                            if isinstance(c, ast.Call) and _callee(c) == fn.name:
                                a = c.args[i] if i < len(c.args) else next((k.value for k in c.keywords if k.arg == nm), None)
                                if a is None:
                                    continue
                                st = _stmt_of(c, fl2.par)
                                if hop < 2:
                                    note_lines(fl2, st)
                                fn2 = next((p for p in [fl2.par.get(st)] if p), None)
                                while fn2 is not None and not isinstance(fn2, ast.FunctionDef):
                                    fn2 = fl2.par.get(fn2)
                                slice_from(fl2, a, fn2, hit, hop + 1, budget - 1)
                    continue
                for s, val in defs.get(nm, []):
                    nxt |= _names(val) | _calls(val)
                    if s is not None and hop < 2:
                        note_lines(fl, s)
            frontier = nxt
            if not frontier - seen:
                break

    found = False
    if part:
        hits = [(fl, n, s) for fl in files for n, s in _str_hits(fl, part)]
        best = max((s for *_, s in hits), default=0)
        for fl, node, hit in hits:
            if hit < best * 0.8:
                continue
            found = True
            scope = _expr_scope(node, fl.par)
            note_lines(fl, scope if hasattr(scope, "lineno") else _stmt_of(node, fl.par))
            fn = node
            while fn in fl.par and not isinstance(fn, ast.FunctionDef):
                fn = fl.par[fn]
            fn = fn if isinstance(fn, ast.FunctionDef) else None
            slice_from(fl, scope, fn, hit, 0, 2)
            # where the result of that function is used: the callers place, mirror or repeat the part
            seen_fn = set()
            hop = 1
            while fn is not None and fn.name not in seen_fn and hop <= 2:
                seen_fn.add(fn.name)
                nxt = None
                for fl2 in files:
                    for c in ast.walk(fl2.tree):
                        if isinstance(c, ast.Call) and _callee(c) == fn.name:
                            st = _stmt_of(c, fl2.par)
                            note_lines(fl2, st)
                            caller = st
                            while caller in fl2.par and not isinstance(caller, ast.FunctionDef):
                                caller = fl2.par[caller]
                            caller = caller if isinstance(caller, ast.FunctionDef) else None
                            # what the call's result becomes (the assigned names) feeds the placement
                            tg = st.targets if isinstance(st, ast.Assign) else []
                            outs = set().union(*(_names(t) for t in tg)) if tg else set()
                            if caller is not None:
                                uses = [u for u in ast.walk(caller) if isinstance(u, ast.stmt) and not isinstance(u, ast.FunctionDef)
                                        and u is not st and outs & _names(u)]
                                for u in uses[:6]:
                                    if hop < 2:
                                        note_lines(fl2, u)
                                    slice_from(fl2, u, caller, hit * 0.8, hop, 0)
                            slice_from(fl2, c, caller, hit * 0.8, hop, 1)
                            nxt = nxt or caller
                fn = nxt
                hop += 1
    for v in values or ():
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if abs(v) < 1e-6:
            continue
        for p in params:
            pv = module_vals.get(p)
            if isinstance(pv, bool) or not isinstance(pv, (int, float)) or abs(pv) < 1e-6:
                continue
            for k, lab in ((1, "="), (2, "= 2×"), (0.5, "= ½×")):
                if abs(v - pv * k) <= max(0.01, abs(v) * 0.002):
                    base = score.get(p, 0)
                    add(p, (0.9 if k == 1 else 0.5) + 0.5 * base, f"value {v:g} = {lab.strip('= ') or ''}{p}".replace("= ", "") + (f" · {why[p]}" if p in why else ""))
                    break
    # merge line ranges per file, keep it short
    merged = []
    for path, a, b in sorted(set(lines)):
        if merged and merged[-1]["file"] == path and a <= merged[-1]["to"] + 3:
            merged[-1]["to"] = max(merged[-1]["to"], b)
        else:
            merged.append({"file": path, "from": a, "to": b})
    out = sorted(({"name": p, "score": round(s, 3), "why": why[p]} for p, s in score.items()), key=lambda x: -x["score"])
    return {"params": out, "lines": merged[:16], "found": found}


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(related(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None,
                             [float(x) for x in sys.argv[3:]]), indent=1, ensure_ascii=False))

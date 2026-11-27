"""Static check of a CadQuery model script before it runs (AST only, milliseconds).

Catches the mistakes that otherwise cost a failed run or a wrong model:
duplicate assembly names, fillet/chamfer after booleans or on all edges, hole(5) meant for an M5 screw,
parameters without comment/unit (the viewer cannot edit them well), unused parameters, export missing or
not STEP, absolute export paths, syntax errors.
"""
import ast
import os
import re

PARAM = re.compile(r"^[A-Z][A-Z0-9_]*$")
from .std import THREAD  # noqa: E402  one thread table for std, lint and the collision check

# hole(5) typed for an M5 screw: size -> (clearance, tap drill)
NOMINAL = {int(k[1:]): (v[3], v[1]) for k, v in THREAD.items() if float(k[1:]).is_integer() and float(k[1:]) >= 3}
BOOL = {"cut", "union", "intersect", "cutBlind", "cutThruAll", "fuse"}


TAPS = {v[1]: k for k, v in THREAD.items()}
HOLE_NAME = re.compile(r"TAP|BORE|HOLE|DRILL|DIRA|VRT|_D$|^D_", re.I)   # a hole diameter, not a length
THREAD_NAME = re.compile(r"TAP|THREAD|NUT|ZAVIT|MATIC", re.I)            # ... of an internal thread


def _odd_hole(name, v):
    """Warning text when a hole parameter is not a size you can drill (4.134 instead of 4.2)."""
    if not isinstance(v, (int, float)) or isinstance(v, bool) or not HOLE_NAME.search(name) or not 1 <= v <= 40:
        return None
    if THREAD_NAME.search(name) and v not in TAPS:
        near = min(THREAD, key=lambda k: abs(THREAD[k][1] - v))
        return (f"{name} = {v:g} is not a tap drill size; an {near} internal thread is modelled at "
                f"{THREAD[near][1]:g} (tap_drill(\"{near}\"))")
    if abs(v * 10 - round(v * 10)) > 1e-6:
        return f"{name} = {v:g}: drill bits come in 0.1 mm steps ({round(v, 1):g}), or use tap_drill() / hole()"
    return None


def _chain(node):
    """Method names of a call chain a.b().c().d() -> ['b','c','d'] and the root name."""
    names = []
    while isinstance(node, (ast.Call, ast.Attribute)):
        if isinstance(node, ast.Call):
            node = node.func
            continue
        names.append(node.attr)
        node = node.value
    root = node.id if isinstance(node, ast.Name) else None
    return list(reversed(names)), root


def lint(script):
    with open(script, encoding="utf-8", errors="replace") as f:
        src = f.read()
    lines = src.split("\n")
    issues = []

    def add(ln, level, msg):
        issues.append((ln, level, msg))
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [(e.lineno or 0, "error", f"syntax: {e.msg}")]

    # parameters
    params = {}
    first_def = next((n.lineno for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))), 10 ** 9)
    for n in tree.body:
        if n.lineno > first_def:
            break  # only the parameter block at the top counts as parameters
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) \
                and PARAM.match(n.targets[0].id) and isinstance(n.value, (ast.Constant, ast.UnaryOp)):
            v = n.value
            if isinstance(v, ast.Constant) and not isinstance(v.value, (int, float)):
                continue
            params[n.targets[0].id] = n.lineno
            line = lines[n.lineno - 1]
            if "#" not in line:
                add(n.lineno, "warn", f"parameter {n.targets[0].id} has no comment (\"# what [mm] lo..hi\")")
            elif not re.search(r"\[[^\]]+\]", line.split("#", 1)[1]) and not isinstance(getattr(v, "value", None), bool):
                add(n.lineno, "info", f"parameter {n.targets[0].id}: no [unit] in its comment")
            msg = _odd_hole(n.targets[0].id, getattr(v, "value", None))
            if msg:
                add(n.lineno, "warn", msg)
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    used |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    # parameters may be read by local modules (import model as M; M.WALL), by name (globals()) or by a
    # helper module that does `from model import *`
    others = ""
    try:
        import sys
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if here not in sys.path:
            sys.path.insert(0, here)
        from related import local_modules
        mods = set(local_modules(script)[1:])
        folder = os.path.dirname(os.path.abspath(script))
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if not d.startswith((".", "__")) and d not in ("zaloha", "backup", "old")]
            mods |= {os.path.join(root, f) for f in files if f.endswith(".py")}
            if root.count(os.sep) - folder.count(os.sep) >= 2:
                dirs[:] = []
        for m in mods:
            if os.path.abspath(m) != os.path.abspath(script):
                with open(m, encoding="utf-8", errors="replace") as f:
                    others += f.read()
    except Exception:  # noqa: BLE001
        pass
    dynamic = "globals()" in src or "vars()" in src
    for p, ln in params.items():
        if p not in used and not dynamic and not re.search(rf"\b{p}\b", others):
            add(ln, "warn", f"parameter {p} is never used")

    # boolean history per variable (statement order) and chains
    had_bool = set()
    names_seen = {}
    exports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            meths, root = _chain(node)
            m = meths[-1] if meths else None
            # assembly names
            if m == "add":
                for kw in node.keywords:
                    if kw.arg == "name" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        nm = kw.value.value
                        if nm in names_seen and names_seen[nm] != node.lineno:
                            add(node.lineno, "error", f"assembly name \"{nm}\" used twice (also line {names_seen[nm]})")
                        names_seen.setdefault(nm, node.lineno)
            if m in ("export", "save", "exportStep") or (m == "export" and root == "exporters"):
                exports.append(node)
            if m == "hole" and node.args and isinstance(node.args[0], ast.Constant) and \
                    isinstance(node.args[0].value, (int, float)) and node.args[0].value in NOMINAL:
                cl, tap = NOMINAL[node.args[0].value]
                add(node.lineno, "warn", f"hole({node.args[0].value}) - an M{node.args[0].value:g} screw needs clearance {cl}; "
                    f"a tapped hole / nut thread is modelled at the tap drill {tap} (tap_drill(\"M{node.args[0].value:g}\"))")
            if m in ("fillet", "chamfer"):
                before = meths[:-1]
                if len(node.args) < 2 and not node.keywords and not any(x in ("edges", "faces") for x in before[-3:])                         and root not in ("self",):
                    add(node.lineno, "warn", f"{m}() without an edges()/faces() selector right before it - applies to ALL edges, fails often")
                if any(x in BOOL for x in before) or (root in had_bool and not any(x in ("box", "rect", "circle", "extrude") for x in before)):
                    add(node.lineno, "info", f"{m}() after a boolean on the same body - the most common failure; prefer filleting before cut/union or select few edges")
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            meths, root = _chain(node.value) if isinstance(node.value, (ast.Call, ast.Attribute)) else ([], None)
            if any(x in BOOL for x in meths):
                had_bool.add(node.targets[0].id)

    # loops adding constant names -> duplicates at run time
    for loop in [n for n in ast.walk(tree) if isinstance(n, (ast.For, ast.While))]:
        for node in ast.walk(loop):
            if isinstance(node, ast.Call) and _chain(node)[0][-1:] == ["add"]:
                for kw in node.keywords:
                    if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                        add(node.lineno, "error", f"assembly name \"{kw.value.value}\" is constant inside a loop - names must be unique (use an f-string with the index)")
    if not exports and params and "import" in src and not re.search(r"^def |^class ", src, re.M) or \
            (not exports and params and "__main__" in src):
        add(0, "warn", "no export/save call found - the viewer and checks need a .step")
    for node in exports:
        for a in list(node.args) + [k.value for k in node.keywords]:
            if isinstance(a, ast.Constant) and isinstance(a.value, str) and "." in a.value[-6:]:
                if not a.value.lower().endswith((".step", ".stp", ".json", ".svg", ".png")):
                    add(node.lineno, "warn", f"export to {a.value} - models are exported as STEP")
                if os.path.isabs(a.value):
                    add(node.lineno, "info", f"absolute export path {a.value} - relative to the script is portable")
    seen, out = set(), []
    for it in sorted(issues, key=lambda x: (x[0], x[1])):
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def text(script, show_info=False):
    iss = [i for i in lint(script) if show_info or i[1] != "info"]
    if not iss:
        return "[lint] no issues"
    b = os.path.basename(script)
    return "\n".join(f"[lint] {b}:{ln} {lvl}: {msg}" for ln, lvl, msg in iss[:25])

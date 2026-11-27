"""@cached_part: rebuild only the parts whose inputs changed (disk cache of B-rep results).

    from cadtools.cache import cached_part

    @cached_part
    def housing():          # returns a finished cq.Workplane or cq.Shape
        return cq.Workplane("XY").box(W, D, H)...

The key is the function's source, its arguments, and the values of every global it uses (parameters,
constants) and the source of every module-level function it calls, followed recursively. Change any of
those and the part is rebuilt; otherwise it is read back from ~/.CAD4Ai/cache/parts in milliseconds.
Rules: the function must return a finished part (Workplane or Shape); a Workplane comes back on the XY
plane with the same solids. Anything else (Assembly, tuples...) is not cached. CAD4AI_NOCACHE=1 turns it off.
If an input cannot be fingerprinted (e.g. a cq object passed in), the part is simply built every time.
"""
import functools
import hashlib
import inspect
import json
import os
import types

from . import core

DIR = os.path.join(core.CACHE, "parts")
_SIMPLE = (int, float, str, bool, type(None), complex, bytes)
STATS = {"hit": 0, "miss": 0, "skip": 0}


class _NoKey(Exception):
    pass


def _val(v, g, seen, depth=0):
    if depth > 6:
        raise _NoKey
    if isinstance(v, _SIMPLE):
        return repr(v)
    if isinstance(v, (list, tuple, set, frozenset)):
        items = sorted(v, key=repr) if isinstance(v, (set, frozenset)) else v
        return type(v).__name__ + "[" + ",".join(_val(x, g, seen, depth + 1) for x in items) + "]"
    if isinstance(v, dict):
        return "{" + ",".join(f"{_val(k, g, seen, depth + 1)}:{_val(x, g, seen, depth + 1)}" for k, x in sorted(v.items(), key=lambda kv: repr(kv[0]))) + "}"
    if isinstance(v, functools.partial):
        return "partial(" + _val(v.func, g, seen, depth + 1) + _val(v.args, g, seen, depth + 1) + _val(v.keywords, g, seen, depth + 1) + ")"
    if isinstance(v, types.FunctionType):
        inner = getattr(v, "__wrapped__", v)
        return _fn(inner, seen)
    if isinstance(v, types.ModuleType):
        return "module:" + v.__name__ + ":" + str(getattr(v, "__version__", ""))
    if isinstance(v, type):
        return "class:" + v.__module__ + "." + v.__qualname__
    if isinstance(v, (types.BuiltinFunctionType, types.MethodType)):
        return "builtin:" + getattr(v, "__qualname__", repr(v))
    raise _NoKey


def _names(code):
    out = set(code.co_names)
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            out |= _names(c)
    return out


def _fn(fn, seen):
    if id(fn) in seen:
        return "fn:" + fn.__qualname__
    seen.add(id(fn))
    try:
        src = inspect.getsource(fn)
    except (OSError, TypeError):
        src = fn.__code__.co_code.hex()
    parts = [src, _val(fn.__defaults__ or (), fn.__globals__, seen)]
    g = fn.__globals__
    for n in sorted(_names(fn.__code__)):
        if n in g:
            v = g[n]
            if isinstance(v, types.ModuleType):
                parts.append(f"{n}=module:{v.__name__}")
                continue
            parts.append(f"{n}={_val(v, g, seen)}")
    if fn.__closure__:
        for c in fn.__closure__:
            parts.append(_val(c.cell_contents, g, seen))
    return "fn:" + hashlib.sha1("\n".join(parts).encode()).hexdigest()


def _key(fn, args, kwargs):
    import cadquery
    seen = set()
    s = "|".join([_fn(fn, seen), _val(args, fn.__globals__, seen), _val(kwargs, fn.__globals__, seen),
                  getattr(cadquery, "__version__", "")])
    return hashlib.sha1(s.encode()).hexdigest()[:24]


def cached_part(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if os.environ.get("CAD4AI_NOCACHE") == "1":
            return fn(*args, **kwargs)
        try:
            key = _key(fn, args, kwargs)
        except _NoKey:
            STATS["skip"] += 1
            return fn(*args, **kwargs)
        import cadquery as cq
        brep, meta = os.path.join(DIR, key + ".brep"), os.path.join(DIR, key + ".json")
        if os.path.isfile(brep) and os.path.isfile(meta):
            try:
                with open(meta, encoding="utf-8") as f:
                    m = json.load(f)
                shp = cq.Shape.importBrep(brep)
                STATS["hit"] += 1
                if m["kind"] == "shape":
                    return shp
                vals = list(shp) if m.get("n", 1) > 1 and hasattr(shp, "__iter__") else [shp]
                return cq.Workplane("XY").newObject(vals)
            except Exception:  # noqa: BLE001 - a broken cache entry is just rebuilt
                pass
        res = fn(*args, **kwargs)
        STATS["miss"] += 1
        try:
            if isinstance(res, cq.Workplane):
                vals = [v for v in res.vals() if isinstance(v, cq.Shape)]
                if not vals:
                    return res
                shp = vals[0] if len(vals) == 1 else cq.Compound.makeCompound(vals)
                kind, n = "workplane", len(vals)
            elif isinstance(res, cq.Shape):
                shp, kind, n = res, "shape", 1
            else:
                return res
            os.makedirs(DIR, exist_ok=True)
            tmp = brep + ".tmp"
            shp.exportBrep(tmp)
            os.replace(tmp, brep)
            with open(meta, "w", encoding="utf-8") as f:
                json.dump({"kind": kind, "n": n, "fn": fn.__qualname__}, f)
        except Exception:  # noqa: BLE001 - caching must never break the model
            pass
        return res
    wrapper.__wrapped__ = fn
    return wrapper

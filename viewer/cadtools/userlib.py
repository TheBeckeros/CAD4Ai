"""User part families: your own library areas next to the built-in standard parts.

Each family is one Python file in ~/.CAD4Ai/library/families/<id>.py (outside the app folder, kept across
plugin updates) with:

    FAMILY = {"id": "alu30", "title": "Al profile 30x30 (own)", "aliases": "profil hlinik 30x30 item",
              "pattern": r"ALU30", "source": "where the values come from", "status": "unverified",
              "columns": ["code", "w", "slot"], "rows": [["ALU30 x500", 30, 8.2]],
              "example": "ALU30 x500"}
    def dims(code): ...   -> dict of dimensions for a code matching `pattern`
    def part(code): ...   -> cq.Workplane in the library conventions (main axis local +Z, bottom at Z=0)

std.dims() / std.part() / parts.place() find these families automatically (after the built-in ones), and
the viewer's Libraries tab lists them. `cad4ai lib new <id>` writes a skeleton to fill in.
"""
import importlib.util
import os
import re

from . import core

DIR = os.path.join(core.APP_HOME, "library", "families")
_CACHE = {"t": 0, "fams": []}


def families(reload=False):
    """Loaded user families (re-read when a file changed)."""
    try:
        files = sorted(f for f in os.listdir(DIR) if f.endswith(".py") and not f.startswith("_"))
    except OSError:
        return []
    stamp = max([os.path.getmtime(os.path.join(DIR, f)) for f in files] or [0])
    if not reload and _CACHE["t"] == stamp and _CACHE["fams"]:
        return _CACHE["fams"]
    fams = []
    for f in files:
        p = os.path.join(DIR, f)
        try:
            spec = importlib.util.spec_from_file_location(f"cad4ai_userfam_{f[:-3]}", p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            fam = dict(getattr(mod, "FAMILY", {}))
            fam.setdefault("id", f[:-3])
            fam["_mod"], fam["_file"] = mod, p
            fams.append(fam)
        except Exception as e:  # noqa: BLE001 - a broken user file must not break the library
            fams.append({"id": f[:-3], "title": f"{f} (error: {type(e).__name__}: {e})", "_file": p, "broken": True})
    _CACHE.update(t=stamp, fams=fams)
    return fams


def match(code):
    for fam in families():
        if fam.get("broken") or not fam.get("pattern"):
            continue
        if re.search(fam["pattern"], code, re.I):
            return fam
    return None


def dims(code):
    fam = match(code)
    if not fam:
        raise ValueError(f"unknown part code: {code}")
    d = dict(fam["_mod"].dims(code))
    d.setdefault("std", fam.get("title") or fam["id"])
    d.setdefault("family", fam["id"])
    return d


def part(code):
    fam = match(code)
    if not fam:
        raise ValueError(f"no geometry for {code}")
    return fam["_mod"].part(code)


TEMPLATE = '''"""{title}

Own part family of the CAD4Ai library. Fill in the table (with the source of the values) and part().
"""
import re

import cadquery as cq

FAMILY = {{
    "id": "{fid}",
    "title": "{title}",
    "aliases": "{aliases}",
    "pattern": r"{pattern}",              # codes of this family, e.g. "{pattern} x500"
    "source": "TODO: catalogue / drawing the values come from",
    "status": "unverified",               # unverified | verified (after checking against the source)
    "columns": ["size", "a", "b"],
    "rows": [],                           # one row per size, used by dims() and shown in the viewer
    "example": "{pattern} x100",
    "note": "{note}",
}}


def dims(code):
    """Dimensions for a code; length from 'x<L>' if the family has one."""
    m = re.search(r"[xX](\\d+(?:\\.\\d+)?)", code)
    L = float(m.group(1)) if m else None
    row = FAMILY["rows"][0] if FAMILY["rows"] else ["?", 10, 10]
    return {{"size": row[0], "a": row[1], "b": row[2], "L": L}}


def part(code):
    """Geometry in the library conventions: main axis = local +Z, bottom at Z=0."""
    d = dims(code)
    return cq.Workplane("XY").rect(d["a"], d["b"]).extrude(d["L"] or 100)
'''


def new_family(fid, title=None, aliases="", note=""):
    fid = re.sub(r"[^a-z0-9_]+", "_", fid.lower()).strip("_") or "family"
    os.makedirs(DIR, exist_ok=True)
    p = os.path.join(DIR, fid + ".py")
    if os.path.exists(p):
        raise FileExistsError(p)
    with open(p, "w", encoding="utf-8") as f:
        f.write(TEMPLATE.format(fid=fid, title=title or fid, aliases=aliases.replace('"', "'"),
                                pattern=fid.upper(), note=note.replace('"', "'")))
    _CACHE["t"] = 0
    return p


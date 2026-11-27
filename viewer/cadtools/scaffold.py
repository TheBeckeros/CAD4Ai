"""Routine files Claude no longer writes by hand: <model>.parts.json filled in, and a script skeleton.

parts.json: every part of the exported assembly gets an entry; only missing parts/keys are added, what is
already there (written by Claude or the user) is never changed. type from the name (screw/bearing/seal...),
standard and size from the standard-parts tables, subassembly from the assembly tree.
"""
import json
import os
import re

from . import core

TYPES = [
    ("bearing", re.compile(r"lo[zž]isk|bearing|\b(6[0-3]\d{2}|6[89]\d{2}|60[0-9]|62[0-9]|68\d|69\d)(-?2?[RZ]S?)?\b", re.I)),
    ("seal", re.compile(r"o-?ring|o-?krou|t[eě]sn|seal|gufer|gufero", re.I)),
    ("spring", re.compile(r"pru[zž]in|spring", re.I)),
    ("electrical", re.compile(r"motor|nema|konektor|connector|sensor|[cč]idlo|kabel|cable|pcb|deska_pl|led\b", re.I)),
    ("purchased", re.compile(r"profil|2020|3030|4040|4545|v-?slot|vendor|nakup", re.I)),
]


def base_name(inst_name):
    return re.sub(r"(#\d+)?(~\d+)?$", "", inst_name)


def guess(inst):
    """Only what is certain: a type when the name is a recognised standard part (screw size, bearing
    code, O-ring), its standard, and the subassembly. A wrong type is worse than none (the viewer groups
    by it and fastener overlaps are judged differently), so nothing is guessed from loose words."""
    nm = base_name(inst.name)
    d = {}
    dims = None
    try:
        from . import std
        dims = std.dims(nm)
    except Exception:  # noqa: BLE001
        dims = None
    if dims:
        s = dims.get("std") or ""
        size = dims.get("size") or dims.get("bearing") or dims.get("motor") or dims.get("profile") or ""
        L = dims.get("L")
        if s or size:
            d["standard"] = " ".join(x for x in (s, f"{size}x{L:g}" if (size and L) else str(size)) if x).strip()
        if "bearing" in dims:
            d["type"] = "bearing"
        elif s.startswith("ISO 3601"):
            d["type"] = "seal"
        elif "motor" in dims:
            d["type"] = "electrical"
        elif "profile" in dims:
            d["type"] = "purchased"
        elif s.startswith("ISO"):
            d["type"] = "fastener"
    elif core.FASTENER.search(nm) and re.search(r"(^|[^A-Za-z])M\d", nm):
        d["type"] = "fastener"  # e.g. SROUB_M4x10: a metric size in the name
    if inst.path and "/" in inst.path:
        d["subassembly"] = inst.path.split("/", 1)[1]
    return nm, d


def has_script(step):
    folder = os.path.dirname(os.path.abspath(step))
    stem = os.path.splitext(os.path.basename(step))[0]
    try:
        for n in os.listdir(folder):
            if n.endswith(".py") and not n.startswith(".cad4ai_"):
                with open(os.path.join(folder, n), encoding="utf-8", errors="replace") as f:
                    if stem in f.read():
                        return True
    except OSError:
        pass
    return False


def fill_parts_json(step, only_with_script=True):
    """-> list of added part names ([] if nothing changed)."""
    if only_with_script and not has_script(step):
        return []
    model = core.load(step)
    if len(model) < 2:
        return []
    p = os.path.splitext(step)[0].split("@", 1)[0] + ".parts.json"
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    parts = data.setdefault("parts", {})
    added = []
    for inst in model:
        nm, d = guess(inst)
        if not d:
            continue  # nothing certain to say about this part
        if nm not in parts:
            # an existing entry for a prefix (e.g. "Bolt" for Bolt_3) covers it
            if any(nm.startswith(k) for k in parts):
                continue
            parts[nm] = d
            added.append(nm)
        else:
            for k, v in d.items():
                if k not in parts[nm] and k != "type":
                    parts[nm][k] = v
    if added:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    return added


TEMPLATE = '''"""{title}

Built by CadQuery; exports {name}.step (+ {name}.parts.json is filled in by CAD4Ai).
"""
import os
import sys

import cadquery as cq

sys.path.insert(0, os.path.expanduser("~/.CAD4Ai/lib"))  # stable CAD4Ai helpers (not the versioned plugin path)
from cadtools.expect import expect  # noqa: E402  design-intent checks, run after the export
from cadtools.std import part  # noqa: E402,F401  standard parts: part("ISO 4762 M5x16")
from cadtools.cache import cached_part  # noqa: E402  @cached_part: rebuild only what changed

# --- Main ---
WIDTH = 100.0  # overall width [mm] 10..500
DEPTH = 60.0  # overall depth [mm] 10..500
THICK = 5.0  # plate thickness [mm] 1..30
HOLE = 5.5  # clearance hole M5 (cad4ai std hole M5) [mm] 3..20


@cached_part
def base():
    return (cq.Workplane("XY").box(WIDTH, DEPTH, THICK).translate((0, 0, THICK / 2))
            .faces(">Z").workplane().rect(WIDTH - 20, DEPTH - 20, forConstruction=True).vertices().hole(HOLE))


assy = cq.Assembly(name="{name}")
assy.add(base(), name="base", color=cq.Color(0.7, 0.72, 0.75))
assy.export("{name}.step")

expect("base").size(WIDTH, DEPTH, THICK).holes(4, d=HOLE)
expect.no_collisions()
'''


def new_script(path, title=None):
    if os.path.exists(path):
        raise FileExistsError(path)
    name = os.path.splitext(os.path.basename(path))[0]
    from . import install
    install.sync()
    with open(path, "w", encoding="utf-8") as f:
        f.write(TEMPLATE.format(title=title or name, name=name))
    return path

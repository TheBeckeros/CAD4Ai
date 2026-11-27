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
    nm = base_name(inst.name)
    d = {}
    if core.FASTENER.search(nm):
        d["type"] = "fastener"
    else:
        for t, rx in TYPES:
            if rx.search(nm):
                d["type"] = t
                break
        else:
            d["type"] = "custom"
    try:
        from . import std
        dims = std.dims(nm)
        s = dims.get("std") or ""
        size = dims.get("size") or dims.get("bearing") or dims.get("motor") or dims.get("profile") or ""
        L = dims.get("L")
        if s or size:
            d["standard"] = " ".join(x for x in (s, f"{size}x{L:g}" if (size and L) else str(size)) if x).strip()
    except Exception:  # noqa: BLE001
        pass
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
import sys

import cadquery as cq

sys.path.insert(0, r"{viewer}")
from cadtools.expect import expect  # noqa: E402  design-intent checks, run after the export
from cadtools.std import part, hole  # noqa: E402,F401  standard parts (ISO screws, bearings...)
from cadtools.cache import cached_part  # noqa: E402,F401  @cached_part: rebuild only what changed

# --- Main ---
WIDTH = 100.0  # overall width [mm] 10..500
DEPTH = 60.0  # overall depth [mm] 10..500
THICK = 5.0  # plate thickness [mm] 1..30
HOLE = hole("M5")["clearance"]  # clearance hole for M5 [mm]


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
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(path, "w", encoding="utf-8") as f:
        f.write(TEMPLATE.format(title=title or name, name=name, viewer=here))
    return path

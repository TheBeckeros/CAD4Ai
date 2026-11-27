"""CAD4Ai standard-part library V1: templates Claude calls instead of modelling from scratch.

    import os, sys; sys.path.insert(0, os.path.expanduser("~/.CAD4Ai/lib"))
    from cadtools.parts import part, place, bolt_joint, drill, info, find

    s = place("ISO 4762 M5x16", at=(10, 0, 8))              # head seated on Z=8, shank down -Z
    b = place("6204", at=(0, 0, 0), up=(1, 0, 0))             # bearing axis along +X, face A on the point
    j = bolt_joint("M5", grip=12, at=(20, 0, 12))             # screw + washers + nut, length chosen
    plate = j.cut(plate, "clearance")                         # clearance hole on the joint axis
    j.add_to(assy, "J1")                                      # parts named with ISO number + size

Conventions (every part, local frame):
- the part's main axis is local +Z; `up` in place() says where that axis points in the model;
- screws: head seat (underside of the head) at Z=0, head towards +Z, shank to -Z (countersunk: head top
  at Z=0); nuts, washers, bearings, pins, profiles, inserts: bottom face at Z=0, extending +Z;
- threads: external = nominal diameter, internal (nut, tapped hole, insert thread) = tap drill, so a
  screw in its thread overlaps by the expected ring (the collision check knows it);
- anchors: named points of each part (info(code)["anchors"]) - place any of them on a model point.

Values: every table carries its source and status (info(code)["source"]). Status "unverified" means typed
from general knowledge, not yet checked against the standard or a maker's catalogue: fine for layout, check
before ordering or for tight fits. "formula" = computed from the standard's definition (thread diameters).
"""
import math
import re

from . import std

# ---------------------------------------------------------------- provenance

SOURCES = {
    "thread": ("ISO 261 coarse pitch; tap drill = d - P (common practice, ISO 2306 class)", "unverified"),
    "thread_profile": ("ISO 68-1 basic profile: d2 = d - 0.6495P, D1 = d - 1.0825P, d3 = d - 1.2269P", "formula"),
    "clearance": ("ISO 273 fine / medium / coarse", "unverified"),
    "ISO 4762": ("ISO 4762 head dk max, k max, socket s, depth t min", "unverified"),
    "ISO 4017": ("ISO 4017 across flats s, head height k", "unverified"),
    "ISO 10642": ("ISO 10642 head dk, k, socket s", "unverified"),
    "ISO 7380": ("ISO 7380 head dk, k, socket s", "unverified"),
    "ISO 4029": ("ISO 4029 socket s", "unverified"),
    "ISO 4032": ("ISO 4032 across flats s, height m", "unverified"),
    "ISO 4035": ("ISO 4035 height m", "unverified"),
    "ISO 7089": ("ISO 7089 d1, d2, h", "unverified"),
    "ISO 8734": ("ISO 8734 nominal d (any length)", "unverified"),
    "DIN 985": ("DIN 985 lock nut height m (s as ISO 4032)", "unverified"),
    "ISO 15": ("ISO 15 boundary dimensions d, D, B (deep groove ball bearings)", "unverified"),
    "NEMA": ("NEMA ICS 16 flange, hole pitch, pilot, shaft (typical maker data)", "unverified"),
    "profile": ("typical 20/30/40/45 slot profile envelope (maker dependent)", "unverified"),
    "ISO 3601": ("O-ring d1 x d2 any; grooves are typical guidelines", "unverified"),
    "DIN 6885": ("DIN 6885 A key b x h, shaft / hub depths", "unverified"),
    "DIN 471": ("DIN 471 shaft groove d2, width m, ring thickness s", "unverified"),
    "DIN 472": ("DIN 472 bore groove d2, width m, ring thickness s", "unverified"),
    "insert": ("heat-set insert for 3D prints: typical maker values (they differ!)", "vendor"),
    "lengths": ("usual stock lengths of metric screws", "unverified"),
}

# usual stock lengths [mm]
LENGTHS = [3, 4, 5, 6, 8, 10, 12, 14, 16, 18, 20, 22, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 90, 100,
           110, 120, 130, 140, 150, 160, 180, 200]

# DIN 985 nylon-insert lock nut: height m (across flats as ISO 4032)
DIN985 = {"M3": 4, "M4": 5, "M5": 5, "M6": 6, "M8": 8, "M10": 10, "M12": 12, "M16": 16, "M20": 20}
# ring thickness s for DIN 471 / 472 by nominal diameter
CIRCLIP_S = {8: 0.8, 10: 1.0, 12: 1.0, 15: 1.0, 16: 1.0, 17: 1.0, 19: 1.0, 20: 1.2, 22: 1.0, 24: 1.2, 25: 1.2,
             26: 1.2, 28: 1.2, 30: 1.5, 32: 1.2, 35: 1.5, 37: 1.5, 40: 1.75, 42: 1.75, 45: 1.75, 47: 1.75,
             50: 2.0, 52: 2.0, 55: 2.0, 62: 2.0, 68: 2.5, 72: 2.5, 80: 2.5}
# heat-set insert: hole d, outer d, length (typical)
INSERT = {"M2": (3.2, 3.6, 4.0), "M2.5": (3.6, 4.0, 5.7), "M3": (4.0, 4.6, 5.7), "M4": (5.6, 6.3, 8.1),
          "M5": (6.4, 7.1, 9.5), "M6": (8.0, 8.7, 12.7)}

ALIASES = {
    "ISO 4762": "imbus inbus socket cap allen válcová hlava šroub screw din 912",
    "ISO 4017": "šestihran šestihranná hlava hex head bolt šroub screw din 933",
    "ISO 10642": "zápustný zapustny countersunk flat head šroub screw din 7991",
    "ISO 7380": "půlkulatá pulkulata button head čočková šroub screw",
    "ISO 4029": "stavěcí stavecí stavěcí červík set screw grub din 916",
    "ISO 4032": "matice nut šestihranná hex din 934",
    "ISO 4035": "nízká matice thin nut jam din 439",
    "DIN 985": "pojistná matice samojistná lock nut nylon nyloc",
    "ISO 7089": "podložka washer plochá flat din 125",
    "ISO 8734": "kolík kolik dowel pin válcový din 6325",
    "bearing": "ložisko lozisko bearing kuličkové ball 6204 608",
    "NEMA": "krokový motor stepper motor nema",
    "profile": "hliníkový profil aluminium extrusion t-slot item bosch 2020 4040",
    "O-ring": "o-kroužek o-krouzek oring těsnění seal",
    "key": "pero drážka key keyway din 6885",
    "DIN 471": "pojistný kroužek seeger hřídel shaft circlip vnější",
    "DIN 472": "pojistný kroužek seeger díra bore circlip vnitřní",
    "insert": "zalisovací matice závitová vložka heat set insert 3d tisk print",
}

EXAMPLES = {
    "ISO 4762": "ISO 4762 M5x16", "ISO 4017": "ISO 4017 M8x30", "ISO 10642": "ISO 10642 M6x20",
    "ISO 7380": "ISO 7380 M4x10", "ISO 4029": "ISO 4029 M5x8", "ISO 4032": "ISO 4032 M8", "ISO 4035": "ISO 4035 M8",
    "DIN 985": "DIN 985 M6", "ISO 7089": "ISO 7089 M8", "ISO 8734": "ISO 8734 6x20", "bearing": "6204",
    "NEMA": "NEMA17 x48", "profile": "2020x200", "O-ring": "O-ring 20x2", "key": "key 30x40 (shaft d x length)",
    "DIN 471": "DIN 471 20", "DIN 472": "DIN 472 47", "insert": "insert M3",
}


def _norm(t):
    import unicodedata
    t = unicodedata.normalize("NFKD", t.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def find(query, k=6):
    """Catalogue search (Czech or English words, a standard number or a size): -> [{family, example, source}]."""
    q = [w for w in re.split(r"[\s,;]+", _norm(query)) if w]
    size = next((w.upper() for w in q if re.fullmatch(r"m\d+(\.\d+)?", w)), None)
    out = []
    for fam, words in ALIASES.items():
        hay = _norm(fam + " " + words)
        score = sum(1 for w in q if w in hay)
        if score:
            ex = EXAMPLES[fam]
            if size and re.search(r"M\d", ex):
                ex = re.sub(r"M\d+(\.\d+)?", size, ex)
            out.append({"family": fam, "example": ex, "score": score, "status": _status(fam)})
    out.sort(key=lambda x: -x["score"])
    return out[:k]


def _status(fam):
    key = {"bearing": "ISO 15", "key": "DIN 6885", "O-ring": "ISO 3601"}.get(fam, fam)
    return SOURCES.get(key, ("", "unverified"))[1]


# ---------------------------------------------------------------- extra families (std.dims / std.part delegate here)

def extra_dims(code):
    c = code.upper().replace(" ", "")
    m = std._m(code)
    if "985" in c and m in DIN985:
        return {"std": "DIN 985", "size": m, "s": std.ISO4032[m][0], "m": DIN985[m]}
    mc = re.search(r"DIN ?(471|472)\D*(\d+)", code.upper())
    if mc:
        kind, d = mc.group(1), int(mc.group(2))
        table = std.DIN471 if kind == "471" else std.DIN472
        if d not in table:
            raise ValueError(f"DIN {kind}: no size {d} (have {sorted(table)})")
        g, w = table[d]
        return {"std": f"DIN {kind}", "d": d, "groove_d": g, "groove_w": w, "s": CIRCLIP_S.get(d, round(w - 0.1, 2)),
                "kind": "shaft" if kind == "471" else "bore"}
    if ("INSERT" in c or "VLOZK" in c or "ZALIS" in c) and m in INSERT:
        h, od, L = INSERT[m]
        return {"std": "insert", "size": m, "hole_d": h, "outer_d": od, "L": L, "thread_hole": std.THREAD[m][1],
                "note": "maker values differ: use the hole size from your insert's data sheet"}
    raise ValueError(f"unknown part code: {code}")


def extra_part(code):
    import cadquery as cq
    d = extra_dims(code)
    if d["std"] == "DIN 985":
        nom = float(d["size"][1:])
        nut = std._hexagon(cq, d["s"], d["m"]).edges("not |Z").chamfer(nom * 0.05)
        return nut.faces(">Z").workplane().hole(std.THREAD[d["size"]][1])
    if d["std"] in ("DIN 471", "DIN 472"):
        # simplified ring sitting in its groove: radial width ~ 0.1 d + 1, gap 30°
        g, s = d["groove_d"], d["s"]
        b = 0.1 * d["d"] + 1.0
        r_in, r_out = (g / 2, g / 2 + b) if d["kind"] == "shaft" else (g / 2 - b, g / 2)
        ring = cq.Workplane("XY").circle(r_out).circle(r_in).extrude(s)
        gap = cq.Workplane("XY").polyline([(0, 0), (2 * r_out, -r_out * 0.27), (2 * r_out, r_out * 0.27)]).close().extrude(s)
        return ring.cut(gap.rotate((0, 0, 0), (0, 0, 1), 90))
    if d["std"] == "insert":
        # outer knurl simplified as a cylinder of the outer diameter; inner thread = tap drill
        return (cq.Workplane("XY").circle(d["outer_d"] / 2).extrude(d["L"])
                .faces(">Z").workplane().hole(d["thread_hole"]))
    raise ValueError(f"no geometry for {code}")


# ---------------------------------------------------------------- anchors and placement

def info(code):
    """Dimensions, anchors (local frame), recommended holes, source/status and steel mass of a part."""
    d = std.dims(code)
    fam = d.get("std") or ("bearing" if "bearing" in d else "NEMA" if "motor" in d else "profile" if "profile" in d else "")
    src = SOURCES.get(fam) or ("", "unverified")
    if d.get("family"):  # own family (~/.CAD4Ai/library/families)
        from . import userlib
        uf = next((f for f in userlib.families() if f.get("id") == d["family"]), {})
        src = (uf.get("source", ""), uf.get("status", "unverified"))
    out = {"code": code, "family": fam, "dims": d, "anchors": anchors(code), "source": src[0], "status": src[1]}
    if d.get("size") in std.THREAD:
        h = std.hole(d["size"], "all")
        out["holes"] = {k: h[k] for k in ("clearance", "clearance_fine", "tap_drill", "cbore_d", "cbore_depth", "csk_d")
                        if k in h}
        P = h["pitch"]
        dn = float(d["size"][1:])
        out["thread"] = {"d": dn, "P": P, "d2": round(dn - 0.649519 * P, 3), "D1": round(dn - 1.082532 * P, 3),
                         "d3": round(dn - 1.226869 * P, 3), "status": "formula ISO 68-1"}
    return out


def anchors(code):
    d = std.dims(code)
    s = d.get("std", "")
    if s in ("ISO 4762", "ISO 4017", "ISO 7380"):
        return {"seat": (0, 0, 0), "head_top": (0, 0, d["head_h"]), "tip": (0, 0, -d["L"]), "axis": "+Z = towards the head"}
    if s == "ISO 10642":
        return {"head_top": (0, 0, 0), "seat_cone": (0, 0, -d["head_h"]), "tip": (0, 0, -d["L"]), "axis": "+Z = towards the head"}
    if s == "ISO 4029":
        return {"top": (0, 0, 0), "tip": (0, 0, -d["L"]), "axis": "+Z = socket end"}
    if s in ("ISO 4032", "ISO 4035", "DIN 985"):
        return {"bottom": (0, 0, 0), "top": (0, 0, d["m"]), "axis": "+Z"}
    if s == "ISO 7089":
        return {"bottom": (0, 0, 0), "top": (0, 0, d["h"]), "axis": "+Z"}
    if s == "ISO 8734":
        return {"bottom": (0, 0, 0), "top": (0, 0, d["L"]), "axis": "+Z"}
    if "bearing" in d:
        return {"face_a": (0, 0, 0), "face_b": (0, 0, d["B"]), "centre": (0, 0, d["B"] / 2), "axis": "+Z (bore d, outer D)"}
    if "motor" in d:
        return {"flange": (0, 0, 0), "pilot_top": (0, 0, d["pilot_h"]), "shaft_tip": (0, 0, d["pilot_h"] + 20),
                "back": (0, 0, -(d["body_L"] or 40)), "axis": "+Z = shaft"}
    if "profile" in d:
        return {"end_a": (0, 0, 0), "end_b": (0, 0, d["L"] or 100), "axis": "+Z = length"}
    if s in ("DIN 471", "DIN 472"):
        return {"bottom": (0, 0, 0), "top": (0, 0, d["s"]), "axis": "+Z"}
    if s == "insert":
        return {"bottom": (0, 0, 0), "top": (0, 0, d["L"]), "axis": "+Z = open end"}
    if s == "ISO 3601":
        return {"centre": (0, 0, 0), "axis": "+Z"}
    if d.get("family"):  # own families follow the library convention: bottom at Z=0, axis +Z
        return {"bottom": (0, 0, 0), "top": (0, 0, d.get("L") or 0), "axis": "+Z"}
    return {"origin": (0, 0, 0), "axis": "+Z"}


def _rot(v, axis, ang):
    """Rodrigues rotation of vector v about unit axis by ang [rad]."""
    ax = _unit(axis)
    c, s = math.cos(ang), math.sin(ang)
    dot = sum(a * b for a, b in zip(ax, v))
    cr = (ax[1] * v[2] - ax[2] * v[1], ax[2] * v[0] - ax[0] * v[2], ax[0] * v[1] - ax[1] * v[0])
    return tuple(v[i] * c + cr[i] * s + ax[i] * dot * (1 - c) for i in range(3))


def _unit(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return tuple(x / n for x in v)


def _frame(up):
    """Rotation (axis, angle) taking local +Z onto `up`."""
    u = _unit(up)
    dot = max(-1.0, min(1.0, u[2]))
    if dot > 1 - 1e-12:
        return None
    if dot < -1 + 1e-12:
        return (1.0, 0.0, 0.0), math.pi
    axis = (-u[1], u[0], 0.0)  # z x up
    return axis, math.acos(dot)


def place(code_or_wp, at=(0, 0, 0), up=(0, 0, 1), anchor=None, spin=0.0, code=None):
    """A standard part (code or a Workplane from part()) moved so that its `anchor` sits on `at` and its local
    +Z axis points along `up`; `spin` [deg] turns it about that axis (hexagon / slot orientation).
    Default anchor: the screw seat, otherwise the bottom / face A / origin."""
    wp = std.part(code_or_wp) if isinstance(code_or_wp, str) else code_or_wp
    code = code_or_wp if isinstance(code_or_wp, str) else code
    an = anchors(code) if code else {"origin": (0, 0, 0)}
    if anchor is None:
        anchor = next((k for k in ("seat", "head_top", "bottom", "face_a", "flange", "end_a", "centre", "origin") if k in an), "origin")
    a = an.get(anchor)
    if a is None:
        raise ValueError(f"{code}: no anchor '{anchor}' (have {[k for k in an if k != 'axis']})")
    if spin:
        wp = wp.rotate((0, 0, 0), (0, 0, 1), spin)
        a = _rot(a, (0, 0, 1), math.radians(spin))
    fr = _frame(up)
    if fr:
        axis, ang = fr
        wp = wp.rotate((0, 0, 0), axis, math.degrees(ang))
        a = _rot(a, axis, ang)
    return wp.translate(tuple(at[i] - a[i] for i in range(3)))


def drill(body, at, d, depth=None, up=(0, 0, 1)):
    """Cut a round hole of diameter d into `body` starting at point `at` and going against `up`
    (depth None = through everything). Works in any orientation, no workplane gymnastics."""
    import cadquery as cq
    if depth is None:  # through: a long cylinder both ways from the point
        cyl = cq.Workplane("XY").circle(d / 2).extrude(-2e4).translate((0, 0, 1e4))
    else:
        cyl = cq.Workplane("XY").circle(d / 2).extrude(-depth)
    return body.cut(place(cyl, at=at, up=up))


# ---------------------------------------------------------------- bolted joint template

def pick_length(need, size=None):
    for L in LENGTHS:
        if L >= need - 1e-6:
            return L
    return int(math.ceil(need / 10.0) * 10)


class Joint:
    """A bolted joint: parts already placed, holes to cut, and what was chosen (see bolt_joint)."""

    def __init__(self):
        self.parts = {}
        self.holes = {}
        self.info = {}

    def add_to(self, assy, prefix="J1", color=None):
        import cadquery as cq
        col = color or cq.Color(0.55, 0.57, 0.6)
        for role, (code, wp) in self.parts.items():
            name = f"{prefix}_{role}_" + re.sub(r"[^A-Za-z0-9.]+", "", code.replace(" ", "")).replace("ISO", "ISO")
            assy.add(wp, name=name, color=col)
        return assy

    def cut(self, body, kind="clearance", depth=None):
        """Drill the joint's hole into a part: kind clearance | tap | cbore (counterbore + clearance) | csk."""
        at, up = self.info["at"], self.info["up"]
        if kind == "clearance":
            return drill(body, at, self.holes["clearance"], depth, up)
        if kind == "tap":
            bottom = tuple(at[i] - up[i] * self.info["grip"] for i in range(3))
            return drill(body, bottom, self.holes["tap_drill"], depth if depth is not None else self.info.get("tap_depth"), up)
        if kind == "cbore":
            b = drill(body, at, self.holes["cbore_d"], self.holes["cbore_depth"], up)
            return drill(b, at, self.holes["clearance"], depth, up)
        if kind == "csk":
            import cadquery as cq
            r = self.holes["csk_d"] / 2
            cone = cq.Solid.makeCone(r, 0, r, cq.Vector(0, 0, 0), cq.Vector(0, 0, -1))
            b = body.cut(place(cq.Workplane("XY").add(cone), at=at, up=up))
            return drill(b, at, self.holes["clearance"], depth, up)
        raise ValueError(kind)

    def summary(self):
        return {"parts": {k: v[0] for k, v in self.parts.items()}, "holes": self.holes, **self.info}


def bolt_joint(size, grip, at=(0, 0, 0), up=(0, 0, 1), screw="ISO 4762", washer=True, nut="ISO 4032",
               engagement=None, material="steel", spin=0.0, thread_thickness=None):
    """Screw (+ washer) through a stack of thickness `grip` [mm] whose top face is at `at`, `up` pointing
    out of that face towards the head.
      nut="ISO 4032" | "DIN 985" | "ISO 4035": washer + nut under the stack, length = stack + nut + 2 pitches;
      nut=None: tapped hole in the last part; length = grip + engagement (default 1 d steel, 2 d alu / plastic),
      tap depth suggested = engagement + 3 pitches; thread_thickness = thickness of the tapped part: the
      screw is then chosen not to stick out of it (warning when no stock length fits).
    The screw length is rounded up to the usual stock length; returns a Joint (parts placed, .cut(), .add_to())."""
    size = std._m(size) or size
    dn = std.nominal(size)
    P = std.THREAD[size][0]
    up = _unit(up)
    j = Joint()
    h = std.hole(size, "all")
    j.holes = {k: h[k] for k in ("clearance", "clearance_fine", "tap_drill", "cbore_d", "cbore_depth", "csk_d") if k in h}
    countersunk = screw.replace(" ", "") in ("ISO10642", "DIN7991")
    wz = std.ISO7089[size][2] if (washer and not countersunk) else 0.0

    def pt(t):  # point on the axis, t along up from `at`
        return tuple(at[i] + up[i] * t for i in range(3))
    if nut:
        nd = std.dims(f"{nut} {size}")
        need = grip + wz + (std.ISO7089[size][2] if washer else 0) + nd["m"] + 2 * P
    else:
        eng = engagement if engagement is not None else dn * (1.0 if material.lower() in ("steel", "ocel", "stainless", "nerez") else 2.0)
        need = grip + wz + eng
    L = pick_length(need)
    warn = None
    if not nut and thread_thickness is not None:
        top = grip + wz + thread_thickness  # longest screw that stays inside the tapped part
        if L > top + 1e-6:
            fits = [x for x in LENGTHS if grip + wz + eng - 1e-6 <= x <= top + 1e-6]
            if fits:
                L = fits[-1]
            else:
                warn = (f"no stock length gives {eng:g} mm engagement inside {thread_thickness:g} mm: "
                        f"the tip sticks out {L - top:g} mm (or the engagement is short)")
    code = f"{screw} {size}x{L:g}"
    j.parts["SCREW"] = (code, place(code, at=pt(wz) if not countersunk else pt(0), up=up,
                                    anchor="seat" if not countersunk else "head_top", spin=spin))
    if wz:
        j.parts["WASHER"] = (f"ISO 7089 {size}", place(f"ISO 7089 {size}", at=pt(0), up=up))
    info = {"size": size, "screw": code, "L": L, "grip": grip, "at": tuple(at), "up": up, "pitch": P}
    if nut:
        t = -grip
        if washer:
            j.parts["WASHER_NUT"] = (f"ISO 7089 {size}", place(f"ISO 7089 {size}", at=pt(t), up=up, anchor="top"))
            t -= std.ISO7089[size][2]
        ncode = f"{nut} {size}"
        j.parts["NUT"] = (ncode, place(ncode, at=pt(t), up=up, anchor="top", spin=spin))
        protrusion = L - (grip + wz + (std.ISO7089[size][2] if washer else 0) + std.dims(ncode)["m"])
        info.update(nut=ncode, protrusion=round(protrusion, 2))
    else:
        actual = L - grip - wz
        if thread_thickness is not None:
            actual = min(actual, thread_thickness)
        td = actual + 3 * P
        if thread_thickness is not None:
            td = min(td, thread_thickness)
        if warn:
            info["warning"] = warn
        elif actual < eng - 1e-6:
            info["warning"] = f"engagement {actual:g} mm < recommended {eng:g} mm"
        info.update(engagement=round(actual, 2), engagement_min=round(eng, 2),
                    tap_depth=round(td, 2), tapped_hole=f"{size}: drill {h['tap_drill']} " +
                    ("through" if thread_thickness is not None and td >= thread_thickness else f"depth {round(td, 1)}"))
    j.info = info
    return j


def part(code):
    return std.part(code)

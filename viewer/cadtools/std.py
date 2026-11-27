"""Standard parts: dimension tables + CadQuery generators (simplified geometry, correct envelope/interfaces).

Use from a model script:
    import os, sys; sys.path.insert(0, os.path.expanduser("~/.CAD4Ai/lib"))
    from cadtools.std import part, hole, dims
    s = part("ISO 4762 M5x16")           # cq.Workplane, head on Z=0 looking +Z, shank along -Z
    h = hole("M5", "clearance")          # {"d": 5.5, ...}
CLI: cad4ai std "ISO 4762 M5x16" | cad4ai std hole M5 | cad4ai std list
Generated STEP files are cached in ~/.CAD4Ai/cache/std (instant the second time).
THREAD CONVENTION (simplified representation, used everywhere in CAD4Ai):
  external thread (screw, stud, threaded shaft) = cylinder of the NOMINAL diameter (M4 -> 4.0);
  internal thread (tapped hole, nut)            = hole of the TAP DRILL diameter   (M4 -> 3.3).
  So a screw in its thread overlaps the part by a thin ring on purpose; the collision check knows this
  and reports it as an expected thread engagement, not as a collision. Use tap_drill("M4") for the hole.
Values: ISO/DIN nominal dimensions (max head sizes) for metric coarse threads.
"""
import os
import re

# --- metric threads: pitch, tap drill, clearance fine/medium/coarse (ISO 273)
THREAD = {
    "M2": (0.4, 1.6, 2.2, 2.4, 2.6), "M2.5": (0.45, 2.05, 2.7, 2.9, 3.1), "M3": (0.5, 2.5, 3.2, 3.4, 3.6),
    "M4": (0.7, 3.3, 4.3, 4.5, 4.8), "M5": (0.8, 4.2, 5.3, 5.5, 5.8), "M6": (1.0, 5.0, 6.4, 6.6, 7.0),
    "M8": (1.25, 6.8, 8.4, 9.0, 10.0), "M10": (1.5, 8.5, 10.5, 11.0, 12.0), "M12": (1.75, 10.2, 13.0, 13.5, 14.5),
    "M14": (2.0, 12.0, 15.0, 15.5, 16.5), "M16": (2.0, 14.0, 17.0, 17.5, 18.5), "M20": (2.5, 17.5, 21.0, 22.0, 24.0),
    "M24": (3.0, 21.0, 25.0, 26.0, 28.0),
}
# ISO 4762 socket head cap screw: head dk, head k, hex socket s, socket depth t
ISO4762 = {"M2": (3.8, 2, 1.5, 1), "M2.5": (4.5, 2.5, 2, 1.1), "M3": (5.5, 3, 2.5, 1.3), "M4": (7, 4, 3, 2),
           "M5": (8.5, 5, 4, 2.5), "M6": (10, 6, 5, 3), "M8": (13, 8, 6, 4), "M10": (16, 10, 8, 5),
           "M12": (18, 12, 10, 6), "M14": (21, 14, 12, 7), "M16": (24, 16, 14, 8), "M20": (30, 20, 17, 10),
           "M24": (36, 24, 19, 12)}
# ISO 4017 / 4014 hex head: across flats s, head k
ISO4017 = {"M2": (4, 1.4), "M2.5": (5, 1.7), "M3": (5.5, 2), "M4": (7, 2.8), "M5": (8, 3.5), "M6": (10, 4),
           "M8": (13, 5.3), "M10": (16, 6.4), "M12": (18, 7.5), "M14": (21, 8.8), "M16": (24, 10), "M20": (30, 12.5),
           "M24": (36, 15)}
# ISO 10642 countersunk socket: head dk, k (90°), socket s
ISO10642 = {"M3": (6.72, 1.86, 2), "M4": (8.96, 2.48, 2.5), "M5": (11.2, 3.1, 3), "M6": (13.44, 3.72, 4),
            "M8": (17.92, 4.96, 5), "M10": (22.4, 6.2, 6), "M12": (26.88, 7.44, 8), "M16": (33.6, 8.8, 10),
            "M20": (40.32, 10.16, 12)}
# ISO 7380 button head: dk, k, s
ISO7380 = {"M3": (5.7, 1.65, 2), "M4": (7.6, 2.2, 2.5), "M5": (9.5, 2.75, 3), "M6": (10.5, 3.3, 4),
           "M8": (14, 4.4, 5), "M10": (17.5, 5.5, 6), "M12": (21, 6.6, 8)}
# ISO 4032 hex nut: s, m ; ISO 4035 thin nut m
ISO4032 = {"M2": (4, 1.6), "M2.5": (5, 2), "M3": (5.5, 2.4), "M4": (7, 3.2), "M5": (8, 4.7), "M6": (10, 5.2),
           "M8": (13, 6.8), "M10": (16, 8.4), "M12": (18, 10.8), "M14": (21, 12.8), "M16": (24, 14.8),
           "M20": (30, 18), "M24": (36, 21.5)}
ISO4035 = {"M3": 1.8, "M4": 2.2, "M5": 2.7, "M6": 3.2, "M8": 4, "M10": 5, "M12": 6, "M16": 8, "M20": 10, "M24": 12}
# ISO 7089 washer: d1, d2, h
ISO7089 = {"M2": (2.2, 5, 0.3), "M2.5": (2.7, 6, 0.5), "M3": (3.2, 7, 0.5), "M4": (4.3, 9, 0.8),
           "M5": (5.3, 10, 1), "M6": (6.4, 12, 1.6), "M8": (8.4, 16, 1.6), "M10": (10.5, 20, 2),
           "M12": (13, 24, 2.5), "M14": (15, 28, 2.5), "M16": (17, 30, 3), "M20": (21, 37, 3), "M24": (25, 44, 4)}
# ISO 4026/4029 set screw: socket s
SETSCREW = {"M3": 1.5, "M4": 2, "M5": 2.5, "M6": 3, "M8": 4, "M10": 5, "M12": 6}
# counterbore for ISO 4762 (DIN 974-1 row): diameter, depth
CBORE = {"M2": (4.3, 2.4), "M2.5": (5, 2.9), "M3": (6.5, 3.4), "M4": (8, 4.4), "M5": (10, 5.4), "M6": (11, 6.4),
         "M8": (15, 8.6), "M10": (18, 10.6), "M12": (20, 12.6), "M14": (24, 14.6), "M16": (26, 16.6),
         "M20": (33, 20.6), "M24": (40, 24.8)}
# ISO 2338 / 8734 dowel pins: nominal d (h8 / m6) - any length
# deep groove ball bearings: d, D, B
BEARING = {
    "623": (3, 10, 4), "624": (4, 13, 5), "625": (5, 16, 5), "626": (6, 19, 6), "627": (7, 22, 7), "608": (8, 22, 7),
    "609": (9, 24, 7), "688": (8, 16, 5), "689": (9, 17, 5), "6800": (10, 19, 5), "6801": (12, 21, 5),
    "6802": (15, 24, 5), "6803": (17, 26, 5), "6804": (20, 32, 7), "6805": (25, 37, 7), "6806": (30, 42, 7),
    "6900": (10, 22, 6), "6901": (12, 24, 6), "6902": (15, 28, 7), "6903": (17, 30, 7), "6904": (20, 37, 9),
    "6905": (25, 42, 9), "6906": (30, 47, 9),
    "6000": (10, 26, 8), "6001": (12, 28, 8), "6002": (15, 32, 9), "6003": (17, 35, 10), "6004": (20, 42, 12),
    "6005": (25, 47, 12), "6006": (30, 55, 13), "6007": (35, 62, 14), "6008": (40, 68, 15), "6009": (45, 75, 16),
    "6010": (50, 80, 16),
    "6200": (10, 30, 9), "6201": (12, 32, 10), "6202": (15, 35, 11), "6203": (17, 40, 12), "6204": (20, 47, 14),
    "6205": (25, 52, 15), "6206": (30, 62, 16), "6207": (35, 72, 17), "6208": (40, 80, 18), "6209": (45, 85, 19),
    "6210": (50, 90, 20),
    "6300": (10, 35, 11), "6301": (12, 37, 12), "6302": (15, 42, 13), "6303": (17, 47, 14), "6304": (20, 52, 15),
    "6305": (25, 62, 17), "6306": (30, 72, 19),
}
# stepper motors: flange, hole pitch, screw, pilot d x h, shaft d
NEMA = {"NEMA8": (20.3, 16, "M2", 16, 1.5, 4), "NEMA11": (28.2, 23, "M2.5", 22, 2, 5),
        "NEMA14": (35.2, 26, "M3", 22, 2, 5), "NEMA17": (42.3, 31, "M3", 22, 2, 5),
        "NEMA23": (56.4, 47.14, "Ø5.1", 38.1, 1.6, 6.35), "NEMA34": (86, 69.6, "Ø5.5", 73, 1.6, 14)}
# aluminium T-slot profiles (simplified as solid square with centre bore): size, slot width, centre bore
PROFILE = {"2020": (20, 6.2, 4.2), "2040": (20, 6.2, 4.2), "3030": (30, 8.2, 6.8), "3060": (30, 8.2, 6.8),
           "4040": (40, 8.2, 8.5), "4080": (40, 8.2, 8.5), "4545": (45, 10, 8.5)}
# ISO 2491/DIN 6885 A parallel keys by shaft range: (d_min, d_max, b, h, t1 shaft, t2 hub)
KEYS = [(6, 8, 2, 2, 1.2, 1.0), (8, 10, 3, 3, 1.8, 1.4), (10, 12, 4, 4, 2.5, 1.8), (12, 17, 5, 5, 3.0, 2.3),
        (17, 22, 6, 6, 3.5, 2.8), (22, 30, 8, 7, 4.0, 3.3), (30, 38, 10, 8, 5.0, 3.3), (38, 44, 12, 8, 5.0, 3.3),
        (44, 50, 14, 9, 5.5, 3.8), (50, 58, 16, 10, 6.0, 4.3), (58, 65, 18, 11, 7.0, 4.4), (65, 75, 20, 12, 7.5, 4.9),
        (75, 85, 22, 14, 9.0, 5.4), (85, 95, 25, 14, 9.0, 5.4)]
# DIN 471 / 472 circlips: shaft/bore d -> groove d, groove width m
DIN471 = {8: (7.6, 0.9), 10: (9.6, 1.1), 12: (11.5, 1.1), 15: (14.3, 1.1), 17: (16.2, 1.1), 20: (19, 1.3),
          25: (23.9, 1.3), 30: (28.6, 1.6), 35: (33, 1.6), 40: (37.5, 1.85), 45: (42.5, 1.85), 50: (47, 2.15)}
DIN472 = {16: (16.8, 1.1), 19: (20, 1.1), 22: (23, 1.1), 24: (25.2, 1.3), 26: (27.2, 1.3), 28: (29.4, 1.3),
          32: (33.7, 1.3), 35: (37, 1.6), 37: (39, 1.6), 40: (42.5, 1.85), 42: (44.5, 1.85), 47: (49.5, 1.85),
          52: (55, 2.15), 55: (58, 2.15), 62: (65, 2.15), 68: (71, 2.65), 72: (75, 2.65), 80: (83.5, 2.65)}


def _m(code):
    m = re.search(r"M(\d+(?:\.\d+)?)", code, re.I)
    return f"M{m.group(1)}" if m else None


def _len(code):
    m = re.search(r"[xX×](\d+(?:\.\d+)?)", code)
    return float(m.group(1)) if m else None


def tap_drill(size):
    """Hole diameter of an internal thread (tapped hole, nut) by the CAD4Ai convention: 'M4' -> 3.3."""
    return THREAD[_m(size) or size][1]


def nominal(size):
    """Diameter of an external thread (screw, stud) by the convention: 'M4' -> 4.0."""
    return float((_m(size) or size)[1:])


def hole(size, kind="clearance"):
    """size 'M5'; kind clearance|clearance-fine|clearance-coarse|tap|cbore|csk -> dims [mm]."""
    s = _m(size) or size
    if s not in THREAD:
        raise ValueError(f"unknown thread {size}")
    p, tap, cf, cm, cc = THREAD[s]
    out = {"thread": s, "pitch": p, "tap_drill": tap, "clearance_fine": cf, "clearance": cm, "clearance_coarse": cc}
    if s in CBORE:
        out["cbore_d"], out["cbore_depth"] = CBORE[s]
    if s in ISO10642:
        out["csk_d"], out["csk_angle"] = round(ISO10642[s][0] + 0.4, 2), 90
    out["min_thread_engagement"] = {"steel": round(1.0 * float(s[1:]), 1), "alu": round(2.0 * float(s[1:]), 1),
                                    "plastic_insert": "use heat-set insert"}
    return out if kind in ("all", None) else {**out, "d": {"clearance": cm, "clearance-fine": cf, "clearance-coarse": cc,
                                                           "tap": tap, "cbore": out.get("cbore_d"),
                                                           "csk": out.get("csk_d")}.get(kind, cm)}


def key_for(shaft_d):
    for lo, hi, b, h, t1, t2 in KEYS:
        if lo < shaft_d <= hi:
            return {"shaft": shaft_d, "b": b, "h": h, "t1_shaft": t1, "t2_hub": t2, "std": "DIN 6885 A"}
    raise ValueError("shaft out of 6..95 mm")


def dims(code):
    """Dimensions of a standard part from its code."""
    c = code.upper().replace(" ", "")
    m, L = _m(code), _len(code)
    if "4762" in c or "912" in c:
        dk, k, s, t = ISO4762[m]
        return {"std": "ISO 4762", "size": m, "L": L, "head_d": dk, "head_h": k, "socket": s, "socket_depth": t}
    if "4017" in c or "4014" in c or "933" in c or "931" in c:
        s, k = ISO4017[m]
        return {"std": "ISO 4017", "size": m, "L": L, "s": s, "head_h": k, "e": round(s / 0.866, 2)}
    if "10642" in c or "7991" in c:
        dk, k, s = ISO10642[m]
        return {"std": "ISO 10642", "size": m, "L": L, "head_d": dk, "head_h": k, "socket": s, "angle": 90}
    if "7380" in c:
        dk, k, s = ISO7380[m]
        return {"std": "ISO 7380", "size": m, "L": L, "head_d": dk, "head_h": k, "socket": s}
    if "4032" in c or "934" in c:
        s, mm = ISO4032[m]
        return {"std": "ISO 4032", "size": m, "s": s, "m": mm, "e": round(s / 0.866, 2)}
    if "4035" in c or "439" in c:
        return {"std": "ISO 4035", "size": m, "s": ISO4032[m][0], "m": ISO4035[m]}
    if "7089" in c or "125" in c:
        d1, d2, h = ISO7089[m]
        return {"std": "ISO 7089", "size": m, "d1": d1, "d2": d2, "h": h}
    if "4026" in c or "4027" in c or "4029" in c or "913" in c:
        return {"std": "ISO 4029", "size": m, "L": L, "socket": SETSCREW[m]}
    if "2338" in c or "8734" in c or c.startswith("PIN") or "6325" in c:
        d = float(re.search(r"(\d+(?:\.\d+)?)[xX×]", code).group(1))
        return {"std": "ISO 8734", "d": d, "L": L}
    mb = re.search(r"\b(6\d{2,3}|6[0-3]\d{2}|68\d{2}|69\d{2})\b", code)
    if mb and mb.group(1) in BEARING:
        d, D, B = BEARING[mb.group(1)]
        return {"std": "ISO 15", "bearing": mb.group(1), "d": d, "D": D, "B": B,
                "shaft_fit": "k5/j6", "housing_fit": "H7/J7", "shoulder_shaft_min": round(d + (D - d) * 0.25, 1),
                "shoulder_housing_max": round(D - (D - d) * 0.25, 1)}
    mn = re.search(r"NEMA\s?(\d+)", c)
    if mn and f"NEMA{mn.group(1)}" in NEMA:
        f, pitch, scr, pd, ph, sd = NEMA[f"NEMA{mn.group(1)}"]
        return {"motor": f"NEMA{mn.group(1)}", "flange": f, "hole_pitch": pitch, "screw": scr, "pilot_d": pd,
                "pilot_h": ph, "shaft_d": sd, "body_L": L}
    mp = re.search(r"(\d{4})", c)
    if mp and mp.group(1) in PROFILE and ("PROF" in c or "ITEM" in c or "BOSCH" in c or "VSLOT" in c or "TSLOT" in c or c[:4].isdigit()):
        a, slot, bore = PROFILE[mp.group(1)]
        w = int(mp.group(1)[:2])
        h = int(mp.group(1)[2:])
        return {"profile": mp.group(1), "w": w, "h": h, "slot": slot, "centre_bore": bore, "L": L,
                "note": "simplified envelope; slots drawn as grooves"}
    mo = re.search(r"O-?RING\s*(\d+(?:\.\d+)?)[xX×](\d+(?:\.\d+)?)", c)
    if mo:
        d1, d2 = float(mo.group(1)), float(mo.group(2))
        return {"std": "ISO 3601", "d1": d1, "d2": d2,
                "groove_static_radial": {"depth": round(d2 * 0.78, 2), "width": round(d2 * 1.35, 2)},
                "groove_axial_face": {"depth": round(d2 * 0.72, 2), "width": round(d2 * 1.45, 2)},
                "note": "groove values are typical guidelines (~20-25 % squeeze); check the seal maker's table"}
    raise ValueError(f"unknown part code: {code}")


# ---------------------------------------------------------------- geometry

def _hexagon(cq, s, h):
    return cq.Workplane("XY").polygon(6, s / 0.8660254).extrude(h)


def part(code):
    """CadQuery Workplane of a standard part. Screws: head bottom at Z=0, head +Z, shank -Z."""
    import cadquery as cq
    d = dims(code)
    std = d.get("std", "")
    if "L" in d and d.get("size"):
        nom = float(d["size"][1:])
    if std == "ISO 4762":
        head = cq.Workplane("XY").circle(d["head_d"] / 2).extrude(d["head_h"]).edges(">Z").chamfer(nom * 0.08)
        head = head.cut(_hexagon(cq, d["socket"], d["socket_depth"]).translate((0, 0, d["head_h"] - d["socket_depth"])))
        return head.union(cq.Workplane("XY").circle(nom / 2).extrude(-d["L"]).faces("<Z").chamfer(min(nom * 0.1, 0.8)))
    if std == "ISO 4017":
        head = _hexagon(cq, d["s"], d["head_h"]).edges(">Z").chamfer(nom * 0.06)
        return head.union(cq.Workplane("XY").circle(nom / 2).extrude(-d["L"]).faces("<Z").chamfer(min(nom * 0.1, 0.8)))
    if std == "ISO 10642":
        k = d["head_h"]
        head = cq.Workplane("XZ").polyline([(0, 0), (nom / 2, 0), (d["head_d"] / 2, k), (0, k)]).close().revolve(360, (0, 0, 0), (0, 1, 0))
        head = head.translate((0, 0, -k))
        head = head.cut(_hexagon(cq, d["socket"], k * 0.7).translate((0, 0, -k * 0.7)))
        return head.union(cq.Workplane("XY").workplane(offset=-k).circle(nom / 2).extrude(-(d["L"] - k)))
    if std == "ISO 7380":
        head = cq.Workplane("XY").circle(d["head_d"] / 2).extrude(d["head_h"]).edges(">Z").fillet(d["head_h"] * 0.9)
        head = head.cut(_hexagon(cq, d["socket"], d["head_h"] * 0.6).translate((0, 0, d["head_h"] * 0.4)))
        return head.union(cq.Workplane("XY").circle(nom / 2).extrude(-d["L"]))
    if std in ("ISO 4032", "ISO 4035"):
        nom = float(d["size"][1:])
        # internal thread by the convention: tap-drill hole
        return _hexagon(cq, d["s"], d["m"]).edges("not |Z").chamfer(nom * 0.05).faces(">Z").workplane().hole(THREAD[d["size"]][1])
    if std == "ISO 7089":
        return cq.Workplane("XY").circle(d["d2"] / 2).circle(d["d1"] / 2).extrude(d["h"])
    if std == "ISO 4029":
        nom = float(d["size"][1:])
        s = cq.Workplane("XY").circle(nom / 2).extrude(-d["L"]).faces("<Z").chamfer(nom * 0.15)
        return s.cut(_hexagon(cq, d["socket"], nom * 0.6).translate((0, 0, -nom * 0.6)))
    if std == "ISO 8734":
        return cq.Workplane("XY").circle(d["d"] / 2).extrude(d["L"]).edges().chamfer(min(0.3, d["d"] * 0.1))
    if "bearing" in d:
        D, dd, B = d["D"], d["d"], d["B"]
        t = (D - dd) / 2
        outer = cq.Workplane("XY").circle(D / 2).circle(D / 2 - t * 0.3).extrude(B)
        inner = cq.Workplane("XY").circle(dd / 2 + t * 0.3).circle(dd / 2).extrude(B)
        shield = cq.Workplane("XY").workplane(offset=B * 0.1).circle(D / 2 - t * 0.29).circle(dd / 2 + t * 0.29).extrude(B * 0.8)
        return outer.union(inner).union(shield).edges("%CIRCLE").chamfer(min(0.3, t * 0.08))
    if "motor" in d:
        L = d["body_L"] or 40
        body = cq.Workplane("XY").rect(d["flange"], d["flange"]).extrude(-L).edges("|Z").chamfer(d["flange"] * 0.08)
        body = body.union(cq.Workplane("XY").circle(d["pilot_d"] / 2).extrude(d["pilot_h"]))
        body = body.union(cq.Workplane("XY").circle(d["shaft_d"] / 2).extrude(d["pilot_h"] + 20))
        hp = d["hole_pitch"] / 2
        hd = float(re.sub(r"[^\d.]", "", d["screw"])) if d["screw"].startswith("Ø") else THREAD[d["screw"]][1]
        return body.faces(">Z[-2]").workplane().pushPoints([(hp, hp), (-hp, hp), (hp, -hp), (-hp, -hp)]).hole(hd, 8)
    if "profile" in d:
        L = d["L"] or 100
        w, h = d["w"], d["h"] if d["h"] > 10 else d["w"]
        a = d["w"]
        n_x, n_y = 1, max(1, int(round(h / a)))
        body = cq.Workplane("XY").rect(a * n_x, a * n_y).extrude(L)
        depth = a * 0.3
        for j in range(n_y):
            yc = -a * n_y / 2 + a * (j + 0.5)
            body = body.faces(">Z").workplane().center(0, 0).moveTo(0, yc).hole(d["centre_bore"])
            for sx in (-1, 1):
                body = body.cut(cq.Workplane("XY").center(sx * (a / 2 - depth / 2), yc).rect(depth, d["slot"]).extrude(L))
        for sy in (-1, 1):
            body = body.cut(cq.Workplane("XY").center(0, sy * (a * n_y / 2 - depth / 2)).rect(d["slot"], depth).extrude(L))
        return body
    if std == "ISO 3601":
        return cq.Workplane("XZ").center(d["d1"] / 2 + d["d2"] / 2, 0).circle(d["d2"] / 2).revolve(360, (-d["d1"] / 2 - d["d2"] / 2, 0, 0), (-d["d1"] / 2 - d["d2"] / 2, 1, 0))
    raise ValueError(f"no geometry for {code}")


def step_file(code):
    """Cached STEP of a standard part -> path."""
    from . import core
    import cadquery as cq
    safe = re.sub(r"[^A-Za-z0-9.]+", "_", code.strip())
    p = os.path.join(core.CACHE, "std", safe + ".step")
    if not os.path.isfile(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        cq.exporters.export(part(code), p)
    return p


def catalogue():
    return {"screws": ["ISO 4762 Mx L (socket cap)", "ISO 4017 Mx L (hex)", "ISO 10642 (countersunk)", "ISO 7380 (button)",
                       "ISO 4029 (set screw)"], "threads": sorted(THREAD, key=lambda s: float(s[1:])),
            "nuts": ["ISO 4032", "ISO 4035 (thin)"], "washers": ["ISO 7089"], "pins": ["ISO 8734 d x L"],
            "bearings": sorted(BEARING), "motors": sorted(NEMA), "profiles": sorted(PROFILE),
            "o-rings": "O-ring d1 x d2 (any)", "keys": "key <shaft d>", "circlips": {"DIN471 shaft": sorted(DIN471),
                                                                                    "DIN472 bore": sorted(DIN472)},
            "holes": "hole M5 [clearance|tap|cbore|csk|all]"}

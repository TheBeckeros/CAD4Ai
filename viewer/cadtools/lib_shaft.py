"""Shaft-hub elements: keys (Pera: parallel DIN 6885, Woodruff DIN 6888), retaining rings (Pojistné kroužky:
DIN 471 shaft, DIN 472 bore, DIN 6799 E-clip), seals (Těsnící kroužky: O-ring ISO 3601, radial shaft seal
DIN 3760, copper sealing washer DIN 7603). Each has counterpart tools (keyseat, hub groove, ring groove, housing
bore). Values typed from general knowledge (unverified)."""
import math

from . import famreg as F
from .famreg import Family, register

SRC = "DIN key / circlip / seal dimensions, typed from general knowledge"

# DIN 6885 A parallel keys: b x h -> t1 (shaft), t2 (hub), shaft range
KEYS = {(2, 2): (1.2, 1.0, 6, 8), (3, 3): (1.8, 1.4, 8, 10), (4, 4): (2.5, 1.8, 10, 12), (5, 5): (3.0, 2.3, 12, 17), (6, 6): (3.5, 2.8, 17, 22),
        (8, 7): (4.0, 3.3, 22, 30), (10, 8): (5.0, 3.3, 30, 38), (12, 8): (5.0, 3.3, 38, 44), (14, 9): (5.5, 3.8, 44, 50),
        (16, 10): (6.0, 4.3, 50, 58), (18, 11): (7.0, 4.4, 58, 65), (20, 12): (7.5, 4.9, 65, 75), (22, 14): (9.0, 5.4, 75, 85),
        (25, 14): (9.0, 5.4, 85, 95), (28, 16): (10.0, 6.4, 95, 110)}
# DIN 6888 Woodruff: b x h -> D, t1 shaft depth
WOODRUFF = {(2, 2.6): (7, 1.8), (2, 3.7): (10, 2.9), (3, 3.7): (10, 2.5), (3, 5): (13, 3.8), (3, 6.5): (16, 5.3), (4, 5): (13, 3.5),
            (4, 6.5): (16, 5.0), (4, 7.5): (19, 6.0), (5, 6.5): (16, 4.5), (5, 7.5): (19, 5.5), (5, 9): (22, 7.0), (6, 9): (22, 6.5),
            (6, 10): (25, 7.5), (8, 11): (28, 8.0), (10, 13): (32, 10.0)}
# DIN 471 (shaft d): groove d2, groove width m, ring s, ring radial width a (max at the lugs), lug hole d5
D471 = {3: (2.8, 0.5, 0.4, 1.9), 4: (3.8, 0.5, 0.4, 2.2), 5: (4.8, 0.7, 0.6, 2.5), 6: (5.7, 0.8, 0.7, 2.7), 7: (6.7, 0.9, 0.8, 3.1),
        8: (7.6, 0.9, 0.8, 3.2), 9: (8.6, 1.1, 1.0, 3.3), 10: (9.6, 1.1, 1.0, 3.3), 12: (11.5, 1.1, 1.0, 3.3), 14: (13.4, 1.1, 1.0, 3.5),
        15: (14.3, 1.1, 1.0, 3.6), 16: (15.2, 1.1, 1.0, 3.7), 17: (16.2, 1.1, 1.0, 3.8), 18: (17.0, 1.3, 1.2, 3.9), 20: (19.0, 1.3, 1.2, 4.0),
        22: (21.0, 1.3, 1.2, 4.2), 24: (22.9, 1.3, 1.2, 4.4), 25: (23.9, 1.3, 1.2, 4.4), 28: (26.6, 1.6, 1.5, 4.7), 30: (28.6, 1.6, 1.5, 5.0),
        32: (30.3, 1.6, 1.5, 5.2), 35: (33.0, 1.6, 1.5, 5.6), 40: (37.5, 1.85, 1.75, 6.0), 45: (42.5, 1.85, 1.75, 6.7),
        50: (47.0, 2.15, 2.0, 6.9), 55: (52.0, 2.15, 2.0, 7.2), 60: (57.0, 2.15, 2.0, 7.4), 65: (62.0, 2.65, 2.5, 7.8),
        70: (67.0, 2.65, 2.5, 8.1), 75: (72.0, 2.65, 2.5, 8.4), 80: (76.5, 2.65, 2.5, 8.6), 90: (86.5, 3.15, 3.0, 9.6), 100: (96.5, 3.15, 3.0, 10.6)}
D472 = {8: (8.4, 0.9, 0.8, 2.4), 10: (10.4, 1.1, 1.0, 3.2), 12: (12.5, 1.1, 1.0, 3.4), 14: (14.6, 1.1, 1.0, 3.7), 16: (16.8, 1.1, 1.0, 3.8),
        18: (19.0, 1.1, 1.0, 4.1), 19: (20.0, 1.1, 1.0, 4.1), 20: (21.0, 1.1, 1.0, 4.2), 22: (23.0, 1.1, 1.0, 4.2), 24: (25.2, 1.3, 1.2, 4.4),
        25: (26.2, 1.3, 1.2, 4.5), 26: (27.2, 1.3, 1.2, 4.7), 28: (29.4, 1.3, 1.2, 4.8), 30: (31.4, 1.3, 1.2, 4.8), 32: (33.7, 1.3, 1.2, 5.4),
        35: (37.0, 1.6, 1.5, 5.4), 37: (39.0, 1.6, 1.5, 5.5), 40: (42.5, 1.85, 1.75, 5.8), 42: (44.5, 1.85, 1.75, 5.9), 47: (49.5, 1.85, 1.75, 6.4),
        52: (55.0, 2.15, 2.0, 6.7), 55: (58.0, 2.15, 2.0, 6.8), 62: (65.0, 2.15, 2.0, 7.3), 68: (71.0, 2.65, 2.5, 7.8), 72: (75.0, 2.65, 2.5, 7.8),
        80: (83.5, 2.65, 2.5, 8.5), 90: (93.5, 3.15, 3.0, 8.7), 100: (103.5, 3.15, 3.0, 9.6)}
# DIN 6799 E-clip by groove d: shaft range, outer d (free), s
ECLIP = {1.2: (1.4, 2, 3, 0.3), 1.5: (2, 2.5, 4, 0.4), 1.9: (2.5, 3, 4.5, 0.5), 2.3: (3, 4, 6, 0.6), 3.2: (4, 5, 7.3, 0.6), 4: (5, 7, 9.3, 0.7),
         5: (6, 8, 11.3, 0.7), 6: (7, 9, 12.3, 0.7), 7: (8, 11, 14.3, 0.9), 8: (9, 12, 16.3, 1.0), 9: (10, 14, 18.8, 1.1),
         10: (11, 15, 20.4, 1.2), 12: (13, 18, 23.4, 1.3), 15: (16, 24, 29.4, 1.5), 19: (20, 31, 37.6, 1.75), 24: (25, 38, 44.6, 2.0)}


# ---------------------------------------------------------------- keys

def _key_parse(g, token, kw):
    form = (g.get("form") or "A").upper()
    b, h = float(g["b"]), float(g["h"])
    L = F.num(g.get("L")) or kw.get("L")
    key = (int(b) if b.is_integer() else b, int(h) if h.is_integer() else h)
    t1, t2, lo, hi = F.table(KEYS, key, "DIN 6885")
    if not L:
        raise ValueError("length missing: write e.g. DIN 6885 A 8x7x40")
    return {"form": form, "b": b, "h": h, "L": L, "t1": t1, "t2": t2, "shaft": f"{lo}..{hi}", "size": f"{b:g}x{h:g}x{L:g}", "type": "custom"}


def _key_outline(b, L, form, z0, h):
    import cadquery as cq
    if form == "A":
        return cq.Workplane("XY").workplane(offset=z0).slot2D(L, b).extrude(h)
    if form == "C":  # one end round
        w = cq.Workplane("XY").workplane(offset=z0).center(-b / 4, 0).slot2D(L - b / 2, b).extrude(h)
        return w.union(cq.Workplane("XY").workplane(offset=z0).center(L / 4, 0).rect(L / 2, b).extrude(h))
    return cq.Workplane("XY").workplane(offset=z0).rect(L, b).extrude(h)


def _key_hub(d):
    """Through hub groove: from just below the shaft surface (Z=t1) up by t2 + 0.2 mm radial clearance, 2 m long."""
    import cadquery as cq
    return cq.Workplane("XY").workplane(offset=d["t1"] - 0.5).rect(2000, d["b"]).extrude(d["t2"] + 0.7)


def _key(d):
    c = min(0.25, 0.06 * d["h"])
    k = _key_outline(d["b"], d["L"], d["form"], 0, d["h"])
    try:
        k = k.edges("|X or |Y").chamfer(c) if c > 0.1 else k
    except Exception:  # noqa: BLE001
        pass
    return F.body_color(k, F.STEEL)


register(Family("DIN 6885", "Pero těsné (podélné)", "Pera/Podélná pera", nums=["DIN 6885", "ISO 2491", "ISO 773"],
                regex=r"(?P<form>[ABC])?\s*(?P<b>\d+(?:\.\d+)?)\s*x\s*(?P<h>\d+(?:\.\d+)?)(?:\s*x\s*(?P<L>\d+(?:\.\d+)?))?",
                parse=_key_parse, build=_key, rows=[[f"{k[0]}x{k[1]}", *v] for k, v in KEYS.items()],
                columns=["b x h", "t1 shaft", "t2 hub", "shaft from", "shaft to"], example="DIN 6885 A 8x7x40",
                aliases="pero drážka těsné pero parallel key keyway feather", source=SRC, ptype="custom",
                anchors=lambda d: {"bottom": (0, 0, 0), "shaft_surface": (0, 0, d["t1"]), "top": (0, 0, d["h"]), "axis": "+Z = out of the shaft, length along X"},
                tools={"shaft": lambda d: _key_outline(d["b"], d["L"], d["form"], 0, d["h"] + 50), "hub": _key_hub},
                note="Key bottom (= keyseat bottom) at Z=0, length along X, centred. tool 'shaft' = keyseat (place it like the key and "
                     "cut the shaft), tool 'hub' = through hub groove (t2 + 0.2 radial clearance)."))


def _wr_parse(g, token, kw):
    b, h = float(g["b"]), float(g["h"])
    key = (int(b) if b.is_integer() else b, int(h) if h.is_integer() else h)
    D, t1 = F.table(WOODRUFF, key, "DIN 6888")
    return {"b": b, "h": h, "D": D, "t1": t1, "size": f"{b:g}x{h:g}", "type": "custom"}


def _woodruff(d):
    import cadquery as cq
    R = d["D"] / 2
    seg = cq.Workplane("XZ").center(0, d["h"] - R).circle(R).extrude(d["b"] / 2, both=True)
    return F.body_color(seg.intersect(cq.Workplane("XY").rect(d["D"] + 2, d["b"] + 2).extrude(d["h"])), F.STEEL)


register(Family("DIN 6888", "Woodruffovo pero", "Pera/Woodruffova pera", nums=["DIN 6888", "ISO 3912"],
                regex=r"(?P<b>\d+(?:\.\d+)?)\s*x\s*(?P<h>\d+(?:\.\d+)?)", parse=_wr_parse, build=_woodruff,
                rows=[[f"{k[0]}x{k[1]}", *v] for k, v in WOODRUFF.items()], columns=["b x h", "D", "t1 shaft"],
                example="DIN 6888 5x7.5", aliases="woodruff úsečové pero segmentové half moon key", source=SRC, ptype="custom",
                anchors=lambda d: {"bottom": (0, 0, 0), "shaft_surface": (0, 0, d["t1"]), "top": (0, 0, d["h"]), "axis": "+Z out, flat along X"},
                tools={"shaft": lambda d: __import__("cadquery").Workplane("XZ").center(0, d["h"] - d["D"] / 2).circle(d["D"] / 2 + 0.05)
                       .extrude(d["b"] / 2, both=True)},
                note="Arc bottom at Z=0 (seat bottom), flat top at Z=h, length along X."))


# ---------------------------------------------------------------- retaining rings

def circlip_geom(d0, d2, s, a, shaft=True):
    """DIN 471 / 472 ring as fitted in the groove: eccentric ring (wide at the back, narrow at the lugs), two lugs
    with holes. Ring plane Z = 0..s, centred on the axis."""
    import cadquery as cq
    if shaft:
        r_in = d2 / 2
        b_back, b_lug = 0.75 * a, 0.4 * a
        outer = cq.Workplane("XY").center(-(b_back - b_lug) / 2, 0).circle(r_in + (b_back + b_lug) / 2).extrude(s)
        ringw = outer.cut(F.ring(r_in, 0, s + 2, -1))
        lug_r = r_in + a * 0.55
    else:
        r_out = d2 / 2
        b_back, b_lug = 0.75 * a, 0.4 * a
        inner = cq.Workplane("XY").center((b_back - b_lug) / 2, 0).circle(r_out - (b_back + b_lug) / 2).extrude(s + 2).translate((0, 0, -1))
        ringw = F.ring(r_out, 0, s).cut(inner)
        lug_r = r_out - a * 0.55
    gap = 0.45 * a + 0.5
    ringw = ringw.cut(cq.Workplane("XY").center((lug_r + a) if shaft else (lug_r - a), 0).rect(2 * a + 4, gap).extrude(s + 2).translate((0, 0, -1)))
    for sgn in (1, -1):
        ang = sgn * (gap / 2 + 0.55 * a) / max(lug_r, 1)
        cx, cy = lug_r * math.cos(ang), lug_r * math.sin(ang)
        lug = cq.Workplane("XY").center(cx, cy).circle(0.55 * a).extrude(s)
        ringw = ringw.union(lug)
        ringw = ringw.cut(cq.Workplane("XY").center(cx, cy).circle(0.22 * a + 0.2).extrude(s + 2).translate((0, 0, -1)))
    if shaft:
        ringw = ringw.cut(F.ring(d2 / 2, 0, s + 2, -1))
    else:
        ringw = ringw.intersect(F.ring(d2 / 2, 0, s))
    return ringw


def _clip_family(fid, title, sub, nums, tab, shaft, example, aliases):
    def parse(g, token, kw):
        d0 = float(g["d"])
        key = int(d0) if d0.is_integer() else d0
        d2, m, s, a = F.table(tab, key, fid)
        return {"d": d0, "d2": d2, "m": m, "s": s, "a": a, "size": f"{d0:g}", "kind": "shaft" if shaft else "bore", "h": s}

    def groove(d):
        if shaft:
            return F.ring(d["d"] / 2 + 1, d["d2"] / 2, d["m"])
        return F.ring(d["d2"] / 2, d["d"] / 2 - 1, d["m"])

    register(Family(fid, title, "Pojistné kroužky/" + sub, nums=nums, regex=r"(?P<d>\d+(?:\.\d+)?)", parse=parse,
                    build=lambda d: F.body_color(circlip_geom(d["d"], d["d2"], d["s"], d["a"], shaft), F.BLACK_OX),
                    rows=[[k, *v] for k, v in tab.items()], columns=["d", "groove d2", "groove m", "ring s", "ring a"],
                    example=example, aliases=aliases, ptype="fastener", source=SRC,
                    anchors=lambda d: {"bottom": (0, 0, 0), "top": (0, 0, d["s"]), "axis": "+Z"},
                    tools={"groove": groove}, color=F.BLACK_OX,
                    note="Ring as fitted (Z = 0..s); tool 'groove' = groove of width m from Z=0 (place both at the groove face)."))


_clip_family("DIN 471", "Pojistný kroužek pro hřídele", "Vnější", ["DIN 471"], D471, True, "DIN 471 20",
             "pojistný kroužek seeger hřídel shaft circlip vnější retaining ring external")
_clip_family("DIN 472", "Pojistný kroužek pro díry", "Vnitřní", ["DIN 472"], D472, False, "DIN 472 47",
             "pojistný kroužek seeger díra bore circlip vnitřní retaining ring internal")


def _eclip_parse(g, token, kw):
    dg = float(g["d"])
    key = int(dg) if dg.is_integer() else dg
    lo, hi, D, s = F.table(ECLIP, key, "DIN 6799")
    return {"d": dg, "D": D, "s": s, "h": s, "size": f"{dg:g}", "shaft": f"{lo}..{hi}"}


def _eclip(d):
    import cadquery as cq
    dg, D, s = d["d"], d["D"], d["s"]
    w = F.ring(D / 2, dg / 2, s)
    w = w.cut(cq.Workplane("XY").center(D / 2, 0).rect(D, dg * 0.85).extrude(s + 2).translate((0, 0, -1)))
    for a in (60, 180, 300):  # three inner contact lugs: cut relief between them
        rel = cq.Workplane("XY").center(dg / 2 + 0.12 * dg, 0).circle(0.18 * dg).extrude(s + 2).translate((0, 0, -1))
        w = w.cut(rel.rotate((0, 0, 0), (0, 0, 1), a + 60))
    return F.body_color(w, F.BLACK_OX)


register(Family("DIN 6799", "Pojistná podložka (E kroužek)", "Pojistné kroužky/Vnější", nums=["DIN 6799", "ISO 1661"],
                regex=r"(?P<d>\d+(?:\.\d+)?)", parse=_eclip_parse, build=_eclip, rows=[[k, *v] for k, v in ECLIP.items()],
                columns=["groove d", "shaft from", "shaft to", "outer D", "s"], example="DIN 6799 6",
                aliases="pojistná podložka E kroužek třmenová e-clip retaining washer", source=SRC,
                anchors=lambda d: {"bottom": (0, 0, 0), "top": (0, 0, d["s"]), "axis": "+Z"}, color=F.BLACK_OX,
                tools={"groove": lambda d: F.ring(d["D"], d["d"] / 2, d["s"] + 0.1)}, note="Code = groove diameter; opening along +X."))


# ---------------------------------------------------------------- seals

def _oring_parse(g, token, kw):
    d1, d2 = float(g["d1"]), float(g["d2"])
    return {"d1": d1, "d2": d2, "size": f"{d1:g}x{d2:g}", "type": "seal",
            "groove_static_radial": {"depth": round(d2 * 0.78, 2), "width": round(d2 * 1.35, 2)},
            "groove_axial_face": {"depth": round(d2 * 0.72, 2), "width": round(d2 * 1.45, 2)}}


def _oring(d):
    import cadquery as cq
    w = cq.Workplane("XY").add(cq.Solid.makeTorus(d["d1"] / 2 + d["d2"] / 2, d["d2"] / 2, pnt=cq.Vector(0, 0, d["d2"] / 2)))
    return F.body_color(w, F.RUBBER)


register(Family("ISO 3601", "O-kroužek", "Těsnící kroužky/O-kroužky", nums=["ISO 3601", "DIN 3771"], words=["O-RING", "ORING", "O RING"],
                regex=r"(?P<d1>\d+(?:\.\d+)?)\s*x\s*(?P<d2>\d+(?:\.\d+)?)", parse=_oring_parse, build=_oring,
                rows=[["any d1 x d2"]], columns=["code"], example="O-ring 20x2", aliases="o-kroužek o-krouzek oring těsnění seal NBR",
                source="ISO 3601 any d1 x d2; grooves are typical guidelines (~20-25 % squeeze)", ptype="seal", color=F.RUBBER,
                anchors=lambda d: {"bottom": (0, 0, 0), "centre": (0, 0, d["d2"] / 2), "axis": "+Z"},
                tools={"groove_shaft": lambda d: F.ring(d["d1"] / 2 + d["d2"] * 0.78 + 0.01, d["d1"] / 2 - 0.01 + 0.0, d["d2"] * 1.35),
                       "groove_face": lambda d: F.ring(d["d1"] / 2 + d["d2"] * 1.45, d["d1"] / 2, d["d2"] * 0.72)},
                note="d1 inner x d2 section, lying on Z=0. Tools: groove_shaft (radial, on the shaft), groove_face (axial)."))


def _seal_parse(g, token, kw):
    return {"form": (g.get("form") or "A").upper(), "d": float(g["d"]), "D": float(g["D"]), "b": float(g["b"]), "type": "seal",
            "size": f"{float(g['d']):g}x{float(g['D']):g}x{float(g['b']):g}", "h": float(g["b"])}


def _seal(d):
    """DIN 3760 radial shaft seal: metal case covered with rubber, sealing lip to the shaft, garter spring."""
    import cadquery as cq
    di, Do, b = d["d"], d["D"], d["b"]
    t = (Do - di) / 2
    case = F.revolve([(Do / 2 - 0.12 * t, 0), (Do / 2, 0), (Do / 2, b), (Do / 2 - 0.28 * t, b), (Do / 2 - 0.28 * t, b - 0.15 * b),
                      (Do / 2 - 0.12 * t, b - 0.15 * b)])
    lip = F.revolve([(Do / 2 - 0.28 * t, b), (di / 2 + 0.35 * t, b), (di / 2 + 0.06 * t, 0.42 * b), (di / 2, 0.3 * b),
                     (di / 2 + 0.06 * t, 0.12 * b), (di / 2 + 0.3 * t, 0.12 * b), (di / 2 + 0.42 * t, 0.62 * b),
                     (Do / 2 - 0.28 * t, b - 0.15 * b)])
    body = case.union(lip)
    sp_r = 0.07 * t
    spring = cq.Workplane("XY").add(cq.Solid.makeTorus(di / 2 + 0.3 * t + sp_r, sp_r, pnt=cq.Vector(0, 0, 0.42 * b)))
    F.paint(spring, F.STEEL)
    return F.body_color(cq.Workplane("XY").add(cq.Compound.makeCompound([body.val(), spring.val()])), F.RUBBER)


register(Family("DIN 3760", "Hřídelové těsnění (gufero)", "Těsnící kroužky/Hřídelová těsnění", nums=["DIN 3760", "ISO 6194"],
                words=["GUFERO", "SIMMERRING"],
                regex=r"(?P<form>AS|A|B|C)?\s*(?P<d>\d+(?:\.\d+)?)\s*x\s*(?P<D>\d+(?:\.\d+)?)\s*x\s*(?P<b>\d+(?:\.\d+)?)",
                parse=_seal_parse, build=_seal, rows=[[c] for c in ("10x22x7", "12x22x7", "15x26x7", "17x28x7", "20x35x7", "25x40x7",
                                                                        "30x47x7", "35x52x7", "40x62x8", "45x62x8", "50x72x8")],
                columns=["d x D x b (any)"], example="DIN 3760 A 20x35x7", aliases="gufero hřídelové těsnění simmerring radial shaft seal",
                source="DIN 3760 any d x D x b (simplified section)", ptype="seal", color=F.RUBBER,
                anchors=lambda d: {"face": (0, 0, 0), "back": (0, 0, d["b"]), "axis": "+Z"},
                tools={"housing": lambda d: F.ring(d["D"] / 2, 0, d["b"] + 0.01).edges(">Z").chamfer(0.3)},
                note="Lip side (spring) at Z=0 faces the medium. Tool 'housing' = bore D x b."))


def _cu_parse(g, token, kw):
    return {"d1": float(g["a"]), "d2": float(g["b"]), "h": float(g["c"]), "size": f"{float(g['a']):g}x{float(g['b']):g}x{float(g['c']):g}", "type": "seal"}


register(Family("DIN 7603", "Těsnicí podložka (měď)", "Těsnící kroužky/Těsnicí podložky", nums=["DIN 7603"],
                regex=r"(?:[A-Z]\s*)?(?P<a>\d+(?:\.\d+)?)\s*x\s*(?P<b>\d+(?:\.\d+)?)\s*x\s*(?P<c>\d+(?:\.\d+)?)",
                parse=_cu_parse, build=lambda d: F.body_color(F.ring(d["d2"] / 2, d["d1"] / 2, d["h"]), F.COPPER),
                rows=[[c] for c in ("6x10x1", "8x12x1", "10x14x1", "12x16x1.5", "14x20x1.5", "16x22x1.5", "18x24x1.5", "20x26x1.5")],
                columns=["d1 x d2 x h (any)"], example="DIN 7603 A 10x14x1", aliases="těsnicí podložka měděná copper sealing washer",
                source="any d1 x d2 x h", ptype="seal", color=F.COPPER,
                anchors=lambda d: {"bottom": (0, 0, 0), "top": (0, 0, d["h"]), "axis": "+Z"}))

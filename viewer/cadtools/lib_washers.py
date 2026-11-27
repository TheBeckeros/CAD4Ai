"""Washers (Podložky): plain (normal, small, large, hardened HV), spring, toothed, serrated, tab washers, square
taper washers for U / I beams, washers for timber, bearing lock washers MB. Bottom face at Z=0, axis +Z.
Values typed from general knowledge (unverified)."""
import math

from . import famreg as F
from .famreg import Family, register

SRC = "ISO / DIN washer dimensions, typed from general knowledge"

PLAIN = {"M2": (2.2, 5, 0.3), "M2.5": (2.7, 6, 0.5), "M3": (3.2, 7, 0.5), "M4": (4.3, 9, 0.8), "M5": (5.3, 10, 1), "M6": (6.4, 12, 1.6),
         "M8": (8.4, 16, 1.6), "M10": (10.5, 20, 2), "M12": (13, 24, 2.5), "M14": (15, 28, 2.5), "M16": (17, 30, 3), "M18": (19, 34, 3),
         "M20": (21, 37, 3), "M22": (23, 39, 3), "M24": (25, 44, 4), "M27": (28, 50, 4), "M30": (31, 56, 4)}
SMALL = {"M2": (2.2, 4.5, 0.3), "M2.5": (2.7, 5, 0.5), "M3": (3.2, 6, 0.5), "M4": (4.3, 8, 0.5), "M5": (5.3, 9, 1), "M6": (6.4, 11, 1.6),
         "M8": (8.4, 15, 1.6), "M10": (10.5, 18, 1.6), "M12": (13, 20, 2), "M16": (17, 28, 2.5), "M20": (21, 34, 3), "M24": (25, 39, 4)}
LARGE = {"M3": (3.2, 9, 0.8), "M4": (4.3, 12, 1), "M5": (5.3, 15, 1.2), "M6": (6.4, 18, 1.6), "M8": (8.4, 24, 2), "M10": (10.5, 30, 2.5),
         "M12": (13, 37, 3), "M14": (15, 44, 3), "M16": (17, 50, 3), "M20": (22, 60, 4), "M24": (26, 72, 5)}
HVW = {"M12": (13, 24, 3), "M16": (17, 30, 4), "M20": (21, 37, 4), "M22": (23, 39, 4), "M24": (25, 44, 4), "M27": (28, 50, 5), "M30": (31, 56, 5)}
SPRING = {"M3": (3.1, 6.2, 0.8), "M4": (4.1, 7.6, 0.9), "M5": (5.1, 9.2, 1.2), "M6": (6.1, 11.8, 1.6), "M8": (8.2, 14.8, 2),
          "M10": (10.2, 18.1, 2.2), "M12": (12.2, 21.1, 2.5), "M14": (14.2, 24.1, 3), "M16": (16.2, 27.4, 3.5), "M20": (20.2, 33.6, 4),
          "M24": (24.5, 40, 5), "M30": (30.5, 48.2, 6)}
TOOTH = {"M3": (3.2, 6, 0.4, 6), "M4": (4.3, 8, 0.5, 8), "M5": (5.3, 10, 0.6, 8), "M6": (6.4, 11, 0.7, 9), "M8": (8.4, 15, 0.8, 10),
         "M10": (10.5, 18, 0.9, 12), "M12": (13, 20.5, 1, 12), "M16": (17, 26, 1.2, 14)}
TAB = {"M4": (4.3, 9, 0.5, 14, 5), "M5": (5.3, 10, 0.5, 16, 6), "M6": (6.4, 12.5, 0.75, 18, 7), "M8": (8.4, 17, 0.75, 20, 8),
       "M10": (10.5, 21, 0.75, 22, 10), "M12": (13, 24, 1, 28, 12), "M16": (17, 30, 1, 32, 15), "M20": (21, 37, 1, 36, 18)}
TAPER = {"M8": (9, 22, 22, 3.8), "M10": (11, 22, 22, 3.8), "M12": (13.5, 26, 30, 4.9), "M16": (17.5, 32, 36, 5.9),
         "M20": (22, 40, 44, 7), "M24": (26, 56, 56, 8.5)}
WOOD_SQ = {"M10": (11, 30, 3), "M12": (13.5, 40, 4), "M16": (17.5, 50, 5), "M20": (22, 60, 6), "M24": (26, 70, 6)}
WOOD_R = {"M8": (9, 28, 3), "M10": (11, 34, 3), "M12": (13.5, 44, 4), "M16": (17.5, 56, 5), "M20": (22, 72, 6), "M24": (26, 85, 6)}
# MB lock washer for KM nuts: bore d1, outer d2, s, inner tab width, number of outer tabs
MB = {"MB0": (10, 21, 1, 3, 11), "MB1": (12, 25, 1, 3, 11), "MB2": (15, 28, 1, 4, 13), "MB3": (17, 32, 1, 4, 13), "MB4": (20, 36, 1, 4, 13),
      "MB5": (25, 42, 1.25, 5, 13), "MB6": (30, 49, 1.25, 5, 13), "MB7": (35, 57, 1.25, 6, 15), "MB8": (40, 62, 1.25, 6, 15),
      "MB9": (45, 69, 1.25, 6, 15), "MB10": (50, 74, 1.25, 6, 15)}


def w_anchors(d):
    return {"bottom": (0, 0, 0), "top": (0, 0, d["h"]), "axis": "+Z"}


def washer_family(fid, title, sub, nums, tab, build, columns, example, aliases, note="", color=F.STEEL, h_of=None):
    def parse(g, token, kw):
        size = f"M{float(g['d']):g}"
        row = F.table(tab, size, fid)
        h = h_of(row) if h_of else row[2]
        return {"size": size, "row": row, "d": float(size[1:]), "h": h, "d1": row[0]}

    def bld(d):
        return F.body_color(build(d, d["row"]), color)

    rows = [[k, *v] for k, v in tab.items()]
    return register(Family(fid, title, "Podložky/" + sub, nums=nums, regex=r"M(?P<d>\d+(?:\.\d+)?)", parse=parse, build=bld,
                           rows=rows, columns=["size", *columns], example=example, aliases=aliases, ptype="fastener",
                           source=SRC, anchors=w_anchors, note=note))


def _plain(chamfer=False):
    def b(d, row):
        d1, d2, h = row
        d["h"] = h
        if chamfer and h >= 1:  # ISO 7090: 30 deg chamfer on the outer top edge, h/4 .. h/2
            c = 0.35 * h
            return F.revolve([(d1 / 2, 0), (d2 / 2, 0), (d2 / 2, h - c), (d2 / 2 - c / math.tan(math.radians(30)), h), (d1 / 2, h)])
        return F.ring(d2 / 2, d1 / 2, h)
    return b


SIMPLE = "Jednoduché podložky"
washer_family("ISO 7089", "Podložka plochá", SIMPLE, ["ISO 7089", "DIN 125", "CSN 021702"], PLAIN, _plain(), ["d1", "d2", "h"],
              "ISO 7089 M8", "podložka washer plochá flat")
washer_family("ISO 7090", "Podložka plochá se sražením", SIMPLE, ["ISO 7090", "DIN 125 B"], PLAIN, _plain(True), ["d1", "d2", "h"],
              "ISO 7090 M8", "podložka sražená chamfered washer")
washer_family("ISO 7092", "Podložka malá", SIMPLE, ["ISO 7092", "DIN 433"], SMALL, _plain(), ["d1", "d2", "h"], "ISO 7092 M5",
              "podložka malá small washer pro válcové hlavy")
washer_family("ISO 7093", "Podložka velká", SIMPLE, ["ISO 7093", "DIN 9021"], LARGE, _plain(), ["d1", "d2", "h"], "ISO 7093 M6",
              "podložka velká large washer karosářská")
washer_family("DIN 6916", "Podložka HV tvrzená pro ocelové konstrukce", "Jednoduché podložky - tvrzené", ["DIN 6916", "EN 14399-6"],
              HVW, _plain(), ["d1", "d2", "h"], "DIN 6916 M20", "podložka tvrzená HV konstrukční hardened washer")
washer_family("ISO 7089 HV300", "Podložka plochá tvrzená 300 HV", "Jednoduché podložky - tvrzené", ["ISO 7089 HV300", "DIN 125 HV"],
              PLAIN, _plain(), ["d1", "d2", "h"], "ISO 7089 HV300 M10", "podložka tvrzená hardened washer 300HV")


def _spring(d, row):
    """DIN 127 B split spring washer: one turn of a rectangular section, rising by ~1 s across the split."""
    import cadquery as cq
    d1, d2, s = row
    d["h"] = 2 * s
    rm = (d1 + d2) / 4
    b = (d2 - d1) / 2
    gap = math.degrees(max(0.6 * s, 0.8) / rm)
    helix = cq.Wire.makeHelix(pitch=s * 360 / (360 - gap), height=s, radius=rm)
    prof = cq.Workplane("XZ").center(rm, s / 2).rect(b, s)
    try:
        w = prof.sweep(cq.Workplane().add(helix), isFrenet=True)
        if w.val().isValid() and w.val().Volume() > 0:
            return w
    except Exception:  # noqa: BLE001
        pass
    ringw = F.ring(d2 / 2, d1 / 2, s)
    return ringw.cut(cq.Workplane("XY").center(rm, 0).rect(b + 2, 0.6 * s).extrude(s + 1).translate((0, 0, -0.5)))


washer_family("DIN 127", "Pružná podložka (pérová)", "Pružné pojistné podložky", ["DIN 127", "DIN 127 B"], SPRING, _spring, ["d1", "d2", "s"],
              "DIN 127 M8", "pérová podložka pružná pojistná spring lock washer grower", color=F.BLACK_OX, h_of=lambda r: 2 * r[2])


def _tooth(external=True, serrated=False):
    def b(d, row):
        import cadquery as cq
        d1, d2, s, n = row
        n = int(n * (1.6 if serrated else 1))
        d["h"] = s * 2.2
        rin, rout = d1 / 2, d2 / 2
        core_in, core_out = (rin, rin + 0.45 * (rout - rin)) if external else (rout - 0.45 * (rout - rin), rout)
        base = F.ring(core_out, core_in, s)
        pts = []
        for i in range(n):
            a0 = 2 * math.pi * i / n
            a1 = a0 + 2 * math.pi / n * 0.55
            r_base, r_tip = (core_out - 0.05, rout) if external else (core_in + 0.05, rin)
            pts.append([(r_base * math.cos(a0), r_base * math.sin(a0)), (r_tip * math.cos(a0 + 0.08), r_tip * math.sin(a0 + 0.08)),
                        (r_tip * math.cos(a1 - 0.04), r_tip * math.sin(a1 - 0.04)), (r_base * math.cos(a1), r_base * math.sin(a1))])
        teeth = None
        for i, p in enumerate(pts):
            t = cq.Workplane("XY").polyline(p).close().extrude(s)
            t = t.rotate(((p[1][0] + p[2][0]) / 2, (p[1][1] + p[2][1]) / 2, 0), (0, 0, 1), 0)
            ang = 2 * math.pi * (i + 0.27) / n
            t = t.rotate((0, 0, 0), (math.cos(ang), math.sin(ang), 0), -18).translate((0, 0, 0.35 * s))  # twisted tooth
            teeth = t if teeth is None else teeth.union(t)
        return base.union(teeth)
    return b


TOOTHT = "Ozubená pojistná podložka"
washer_family("DIN 6797 A", "Vějířová podložka, vnější zuby", TOOTHT, ["DIN 6797 A", "DIN 6797"], TOOTH, _tooth(True),
              ["d1", "d2", "s", "teeth"], "DIN 6797 A M6", "vějířová ozubená pojistná podložka external tooth lock washer", h_of=lambda r: 2.2 * r[2])
washer_family("DIN 6797 J", "Vějířová podložka, vnitřní zuby", TOOTHT, ["DIN 6797 J"], TOOTH, _tooth(False),
              ["d1", "d2", "s", "teeth"], "DIN 6797 J M6", "vějířová ozubená pojistná podložka internal tooth lock washer", h_of=lambda r: 2.2 * r[2])
washer_family("DIN 6798 A", "Podložka s ozubením, vnější", TOOTHT, ["DIN 6798 A", "DIN 6798"], TOOTH, _tooth(True, True),
              ["d1", "d2", "s", "teeth"], "DIN 6798 A M8", "ozubená podložka serrated lock washer vnější", h_of=lambda r: 2.2 * r[2])
washer_family("DIN 6798 J", "Podložka s ozubením, vnitřní", TOOTHT, ["DIN 6798 J"], TOOTH, _tooth(False, True),
              ["d1", "d2", "s", "teeth"], "DIN 6798 J M8", "ozubená podložka serrated lock washer vnitřní", h_of=lambda r: 2.2 * r[2])


def _tab(kind):
    def b(d, row):
        import cadquery as cq
        d1, d2, s, L, bt = row
        d["h"] = s
        w = F.ring(d2 / 2, 0, s)
        if kind in ("long", "two"):
            w = w.union(cq.Workplane("XY").center(L / 2, 0).rect(L, bt).extrude(s))
        if kind == "two":
            w = w.union(cq.Workplane("XY").center(-L / 2 * 0.75, 0).rect(L * 0.75, bt).extrude(s))
        if kind == "nose":
            w = w.union(cq.Workplane("XY").center(d2 / 2, 0).rect(0.5 * d2, 0.3 * d2).extrude(s))
        return w.cut(F.ring(d1 / 2, 0, s + 2, -1))
    return b


TABT = "Pojistná podložka s jazýčky"
washer_family("DIN 93", "Pojistný plech s dlouhým jazýčkem", TABT, ["DIN 93"], TAB, _tab("long"), ["d1", "d2", "s", "tab L", "tab b"],
              "DIN 93 M10", "pojistný plech jazýček tab washer", note="Tab flat (before bending), along +X.")
washer_family("DIN 463", "Pojistný plech se dvěma jazýčky", TABT, ["DIN 463"], TAB, _tab("two"), ["d1", "d2", "s", "tab L", "tab b"],
              "DIN 463 M10", "pojistný plech dva jazýčky double tab washer", note="Tabs flat (before bending).")
washer_family("DIN 432", "Pojistný plech s nosem", TABT, ["DIN 432"], TAB, _tab("nose"), ["d1", "d2", "s", "tab L", "tab b"],
              "DIN 432 M10", "pojistný plech nos external tab washer")


def _mb_parse(g, token, kw):
    k = "MB" + g["n"]
    d1, d2, s, tw, n = F.table(MB, k, "MB")
    return {"size": k, "d1": d1, "d2": d2, "h": s, "tw": tw, "n": n, "d": d1, "std_code": k}


def _mb(d):
    import cadquery as cq
    d1, d2, s, tw, n = d["d1"], d["d2"], d["h"], d["tw"], d["n"]
    w = F.ring(d2 / 2, d1 / 2, s)
    w = w.union(cq.Workplane("XY").center(d1 / 2 - 0.08 * d1, 0).rect(0.16 * d1 + 0.01, tw).extrude(s))  # inner tab
    for i in range(n):
        a = 360 * i / n
        slot = cq.Workplane("XY").center(d2 / 2, 0).rect(0.22 * (d2 - d1), 0.6 * math.pi * d2 / n / 2).extrude(s + 2).translate((0, 0, -1))
        w = w.cut(slot.rotate((0, 0, 0), (0, 0, 1), a + 180 / n))
    return F.body_color(w, F.STEEL)


register(Family("DIN 5406", "Pojistná podložka MB (pro KM)", "Podložky/Pojistná podložka s jazýčky", nums=["DIN 5406"], words=["MB"],
                regex=r"(?:MB)?\s*(?P<n>\d+)", parse=_mb_parse, build=_mb, rows=[[k, *v] for k, v in MB.items()],
                columns=["code", "d1", "d2", "s", "inner tab", "outer tabs"], example="MB4",
                aliases="pojistná podložka MB ložisková lock washer KM", source=SRC, anchors=w_anchors, note="Flat, tabs not bent."))


def _taper(slope):
    def b(d, row):
        import cadquery as cq
        d1, a, bb, h = row
        d["h"] = h + a / 2 * slope
        lo, hi = h - a / 2 * slope, h + a / 2 * slope
        w = (cq.Workplane("XZ").polyline([(-a / 2, 0), (a / 2, 0), (a / 2, hi), (-a / 2, lo)]).close().extrude(bb / 2, both=True))
        return w.cut(F.ring(d1 / 2, 0, hi + 2, -1))
    return b


TAPERT = "Čtyřhranné klínové"
washer_family("DIN 434", "Klínová podložka pro U profily (8 %)", TAPERT, ["DIN 434"], TAPER, _taper(0.08), ["d1", "a", "b", "h mid"],
              "DIN 434 M12", "klínová podložka U profil taper washer channel 8%", h_of=lambda r: r[3] + r[1] / 2 * 0.08)
washer_family("DIN 435", "Klínová podložka pro I profily (14 %)", TAPERT, ["DIN 435"], TAPER, _taper(0.14), ["d1", "a", "b", "h mid"],
              "DIN 435 M12", "klínová podložka I profil taper washer beam 14%", h_of=lambda r: r[3] + r[1] / 2 * 0.14)


def _wood_sq(d, row):
    d1, a, s = row
    d["h"] = s
    return F.square(a, s).cut(F.ring(d1 / 2, 0, s + 2, -1))


def _wood_r(d, row):
    d1, d2, s = row
    d["h"] = s
    return F.ring(d2 / 2, d1 / 2, s)


WOODT = "Dřevěné konstrukce"
washer_family("DIN 436", "Čtyřhranná podložka pro dřevo", WOODT, ["DIN 436"], WOOD_SQ, _wood_sq, ["d1", "a", "s"], "DIN 436 M12",
              "podložka čtyřhranná dřevo tesařská square washer timber")
washer_family("DIN 440", "Kruhová podložka pro dřevo", WOODT, ["DIN 440", "DIN 440 R"], WOOD_R, _wood_r, ["d1", "d2", "s"], "DIN 440 M12",
              "podložka kruhová dřevo tesařská round washer timber")

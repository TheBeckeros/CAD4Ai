"""Nuts (Matice): hex (normal, thin, high, fine), structural HV, self-locking (nylon insert, all-metal), cap,
square, round slotted KM, flange, wing, coupling, T-slot. Bottom face at Z=0, axis +Z. Internal thread = tap
drill bore in P/2 rings (CAD4Ai convention). Values typed from general knowledge (unverified)."""
import math

from . import famreg as F
from . import screws as S
from .famreg import Family, register

SRC = "ISO / DIN nominal nut dimensions, typed from general knowledge"

HEXN = {"M2": (4, 1.6), "M2.5": (5, 2), "M3": (5.5, 2.4), "M4": (7, 3.2), "M5": (8, 4.7), "M6": (10, 5.2), "M8": (13, 6.8),
        "M10": (16, 8.4), "M12": (18, 10.8), "M14": (21, 12.8), "M16": (24, 14.8), "M18": (27, 15.8), "M20": (30, 18),
        "M22": (34, 19.4), "M24": (36, 21.5), "M27": (41, 23.8), "M30": (46, 25.6)}
THIN = {"M3": 1.8, "M4": 2.2, "M5": 2.7, "M6": 3.2, "M8": 4, "M10": 5, "M12": 6, "M14": 7, "M16": 8, "M18": 9, "M20": 10,
        "M22": 11, "M24": 12, "M27": 13.5, "M30": 15}
HIGH = {"M5": 5.1, "M6": 5.7, "M8": 7.5, "M10": 9.3, "M12": 12, "M14": 14.1, "M16": 16.4, "M20": 20.3, "M24": 23.9, "M30": 28.6}
HVN = {"M12": (22, 10), "M16": (27, 13), "M20": (32, 16), "M22": (36, 18), "M24": (41, 20), "M27": (46, 22), "M30": (50, 24)}
NYLOC = {"M3": 4.5, "M4": 6, "M5": 6.8, "M6": 8, "M8": 9.5, "M10": 11.9, "M12": 14.9, "M14": 17, "M16": 19.1, "M20": 22.8, "M24": 27.1}
NYLOC_LOW = {"M3": 4, "M4": 5, "M5": 5, "M6": 6, "M8": 8, "M10": 10, "M12": 12, "M14": 14, "M16": 16, "M20": 20, "M24": 24}
# cap nut DIN 1587 (high): s, h total, thread depth ; DIN 917 (low): s, h, thread depth
CAP = {"M4": (7, 8, 5.4), "M5": (8, 10, 6.4), "M6": (10, 12, 7.5), "M8": (13, 15, 9.5), "M10": (17, 18, 11.5), "M12": (19, 22, 14),
       "M16": (24, 28, 18), "M20": (30, 34, 22), "M24": (36, 42, 26)}
CAP_LOW = {"M4": (7, 5.5, 3.5), "M5": (8, 6.5, 4), "M6": (10, 7.5, 5), "M8": (13, 9.5, 6.5), "M10": (17, 11.5, 8), "M12": (19, 13.5, 10),
           "M16": (24, 17, 13), "M20": (30, 22, 16)}
SQN = {"M3": (5.5, 2.4), "M4": (7, 3.2), "M5": (8, 4), "M6": (10, 5), "M8": (13, 6.5), "M10": (17, 8), "M12": (19, 10), "M16": (24, 13)}
SQN_LOW = {"M3": (5.5, 1.8), "M4": (7, 2.2), "M5": (8, 2.7), "M6": (10, 3.2), "M8": (13, 4), "M10": (17, 5), "M12": (19, 6), "M16": (24, 8)}
FLANGEN = {"M5": (8, 5, 11.8, 1.0), "M6": (10, 6, 14.2, 1.1), "M8": (13, 8, 17.9, 1.2), "M10": (15, 10, 21.8, 1.5), "M12": (18, 12, 26, 1.8),
           "M16": (24, 16, 34.5, 2.4), "M20": (30, 20, 42.8, 3.0)}
WINGN = {"M4": (20, 10.5), "M5": (26, 13), "M6": (33, 17), "M8": (39, 20), "M10": (51, 25), "M12": (65, 33.5)}
COUPLING = {"M5": (8, 15), "M6": (10, 18), "M8": (13, 24), "M10": (17, 30), "M12": (19, 36), "M16": (24, 48), "M20": (30, 60)}
# DIN 508 T-slot nut by slot width a: thread, b head width, h total, k head height, l length
TSLOT = {8: ("M6", 13, 10, 5, 13), 10: ("M8", 15, 12, 6, 15), 12: ("M10", 18, 14, 7, 18), 14: ("M12", 22, 16, 8, 22),
         18: ("M16", 28, 20, 10, 28), 22: ("M20", 35, 28, 14, 35)}
# DIN 981 KM bearing lock nut: thread d x P, outer d1, width B, slot b x h
KM = {"KM0": (10, 0.75, 18, 4, 3, 2), "KM1": (12, 1, 22, 4, 3, 2), "KM2": (15, 1, 25, 5, 4, 2), "KM3": (17, 1, 28, 5, 4, 2),
      "KM4": (20, 1, 32, 6, 4, 2), "KM5": (25, 1.5, 38, 7, 5, 2), "KM6": (30, 1.5, 45, 7, 5, 2), "KM7": (35, 1.5, 52, 8, 5, 2),
      "KM8": (40, 1.5, 58, 9, 6, 2.5), "KM9": (45, 1.5, 65, 10, 6, 2.5), "KM10": (50, 1.5, 70, 11, 6, 2.5),
      "KM11": (55, 2, 75, 11, 7, 3), "KM12": (60, 2, 80, 11, 7, 3)}
KM_THREADS = [(v[0], v[1]) for v in KM.values()]


def nut_anchors(d):
    return {"bottom": (0, 0, 0), "top": (0, 0, d["m"]), "axis": "+Z"}


def _nut_tools():
    def thread(d):
        return F.ring(d["tap"] / 2, 0, d["m"] + 2, -1)
    return {"bolt": thread}


def nut_family(fid, title, sub, nums, tab, build, columns, example, aliases, fine=False, note="", color=F.STEEL):
    def parse(g, token, kw):
        size, P, _ = F.metric(g, length=False)
        if fine and not P:
            raise ValueError(f"fine pitch missing: write e.g. {example}")
        P = F.pitch(size, P)
        row = F.table(tab, size, fid)
        m = row[1] if isinstance(row, tuple) else row          # height (s, m) / (s, h, ...) / h
        s_ = row[0] if isinstance(row, tuple) else HEXN.get(size, (None,))[0]
        return {"size": size, "d": float(size[1:]), "P": P, "tap": F.tap(size, P if fine or abs(P - F.pitch(size)) > 1e-9 else None),
                "row": row, "pitch_code": f"{size}x{P:g}", "m": m, "s": s_}

    def bld(d):
        return F.body_color(build(d, d["row"]), color)

    rows = [[k, *(v if isinstance(v, tuple) else (v,))] for k, v in tab.items()]
    if fine:
        from .std import FINE
        rows = [[fc, *(tab[fc.split("x")[0]] if isinstance(tab[fc.split("x")[0]], tuple) else (tab[fc.split("x")[0]],))]
                for fc in FINE if fc.split("x")[0] in tab]
    return register(Family(fid, title, "Matice/" + sub, nums=nums, regex=F.METRIC, parse=parse, build=bld, rows=rows,
                           columns=["size", *columns], example=example, aliases=aliases, ptype="fastener", source=SRC,
                           anchors=nut_anchors, tools=_nut_tools(), note=note))


def _hexn(m_from):
    def b(d, row):
        s, m = row if isinstance(row, tuple) else (HEXN[d["size"]][0], row)
        d["m"], d["s"] = m, s
        return S.hex_nut(d["d"], d["P"], d["tap"], s, m)
    return b


HEXT = "Šestihranná matice"
nut_family("ISO 4032", "Šestihranná matice", HEXT, ["ISO 4032", "DIN 934", "CSN 021401"], HEXN, _hexn("std"), ["s", "m"],
           "ISO 4032 M8", "matice nut šestihranná hex")
nut_family("ISO 4035", "Šestihranná matice nízká", HEXT, ["ISO 4035", "DIN 439"], THIN, _hexn("thin"), ["m"],
           "ISO 4035 M8", "nízká matice thin nut jam kontramatice")
nut_family("ISO 4033", "Šestihranná matice vysoká", HEXT, ["ISO 4033"], HIGH, _hexn("thin"), ["m"], "ISO 4033 M10",
           "vysoká matice style 2 high nut")
nut_family("ISO 8673", "Šestihranná matice, jemný závit", "Šestihranná matice - jemné stoupání", ["ISO 8673", "DIN 934 F"],
           HEXN, _hexn("std"), ["s", "m"], "ISO 8673 M10x1.25", "matice jemný závit jemné stoupání fine thread nut", fine=True)
nut_family("ISO 8675", "Šestihranná matice nízká, jemný závit", "Šestihranná matice - jemné stoupání", ["ISO 8675", "DIN 439 F"],
           THIN, _hexn("thin"), ["m"], "ISO 8675 M12x1.5", "nízká matice jemný závit fine thin nut", fine=True)
nut_family("EN 14399-4 N", "Matice HV pro ocelové konstrukce", "Šestihranná matice - konstrukční", ["EN 14399-4 N", "DIN 6915"],
           HVN, _hexn("std"), ["s", "m"], "DIN 6915 M20", "HV matice konstrukční structural nut ocelové konstrukce 10")


def _nyloc(low=False, metal=False):
    def b(d, row):
        import cadquery as cq
        s = HEXN[d["size"]][0]
        h = row
        d["m"], d["s"] = h, s
        mh = 0.72 * h if not low else 0.68 * h              # hexagon height, the rest is the collar
        body = S.chamfered_prism(cq, s, 0, mh, top=False, bottom=True)
        rc = 0.93 * s / 2
        collar = F.revolve([(0, mh - 0.01), (rc, mh - 0.01), (rc, mh + (h - mh) * 0.45), ("arc", (rc - (h - mh) * 0.2, mh + (h - mh) * 0.85),
                                                                                    (rc - (h - mh) * 0.5, h)), (0, h)])
        body = body.union(collar, clean=True)
        body = S.nut_bore(cq, body, d["d"], d["P"], d["tap"], 0, mh, csk=True)
        if metal:  # all-metal: deformed top, bore continues
            return S.nut_bore(cq, body, d["d"], d["P"], d["tap"], mh - 0.01, h, csk=False)
        # nylon insert ring in the collar (its own solid, blue), bore of the insert = tap drill
        r_in_ring = d["tap"] / 2
        r_out_ring = min(rc - (h - mh) * 0.5, d["d"] / 2 + 0.25 * d["d"])
        cavity = F.ring(r_out_ring, 0, h - mh - 0.3 * (h - mh) + 0.01, mh - 0.01)
        body = body.cut(cavity, clean=True).cut(F.ring(d["d"] * 0.52, 0, h + 1, mh), clean=True)
        insert = F.ring(r_out_ring, r_in_ring, h - mh - 0.3 * (h - mh), mh)
        F.paint(insert, F.NYLON)
        return cq.Workplane("XY").add(cq.Compound.makeCompound([body.val(), insert.val()]))
    return b


LOCKT = "Šestihranná matice - samojistná"
nut_family("ISO 7040", "Samojistná matice s plastovým kroužkem", LOCKT, ["ISO 7040", "DIN 982"], NYLOC, _nyloc(), ["h"],
           "ISO 7040 M8", "samojistná pojistná matice nylon nyloc plastový kroužek lock nut")
nut_family("DIN 985", "Samojistná matice nízká s plastovým kroužkem", LOCKT, ["DIN 985", "ISO 10511"], NYLOC_LOW, _nyloc(True), ["h"],
           "DIN 985 M8", "samojistná pojistná matice nízká nylon nyloc lock nut")
nut_family("ISO 7042", "Samojistná matice celokovová", LOCKT, ["ISO 7042", "DIN 980"], NYLOC, _nyloc(metal=True), ["h"],
           "ISO 7042 M10", "samojistná celokovová all metal lock nut stover")
nut_family("ISO 10512", "Samojistná matice s plastovým kroužkem, jemný závit", "Šestihranná matice - samojistná - jemný závit",
           ["ISO 10512"], NYLOC, _nyloc(), ["h"], "ISO 10512 M10x1.25", "samojistná nyloc jemný závit fine lock nut", fine=True)


def _cap(tab):
    def b(d, row):
        import cadquery as cq
        s, h, t = row
        d["m"], d["s"] = h, s
        mh = h - s / 2 * 0.95 if h - s / 2 * 0.95 > t * 0.8 else t * 0.85
        body = S.chamfered_prism(cq, s, 0, mh, top=False, bottom=True)
        R = 0.95 * s / 2
        zt = h
        z0 = mh - 0.01
        zc = (R * R + z0 * z0 - zt * zt) / (2 * (z0 - zt))       # sphere centre on the axis through both points
        rs = zt - zc
        am = (math.atan2(z0 - zc, R) + math.pi / 2) / 2
        dome = F.revolve([(0, z0), (R, z0), ("arc", (rs * math.cos(am), zc + rs * math.sin(am)), (0, zt))])
        body = body.union(dome, clean=True)
        # blind threaded bore depth t
        tool = S._revolve(cq, [(0, -0.5), (1.08 * d["d"] / 2 + 0.87, -0.5), (d["tap"] / 2, (1.08 * d["d"] / 2 - d["tap"] / 2) / 1.732)]
                          + S._bands(d["tap"] / 2, (1.08 * d["d"] / 2 - d["tap"] / 2) / 1.732, t, d["P"] / 2)
                          + [(0, t + d["tap"] / 2 * 0.6)])
        return body.cut(tool, clean=False)
    return b


CAPT = "Šestihranná matice - uzavřená"
nut_family("DIN 1587", "Uzavřená matice vysoká", CAPT, ["DIN 1587"], CAP, _cap(CAP), ["s", "h", "thread depth"], "DIN 1587 M8",
           "uzavřená klobouková matice cap acorn dome nut")
nut_family("DIN 917", "Uzavřená matice nízká", CAPT, ["DIN 917"], CAP_LOW, _cap(CAP_LOW), ["s", "h", "thread depth"], "DIN 917 M8",
           "uzavřená nízká klobouková matice cap nut low")
nut_family("DIN 1587 F", "Uzavřená matice, jemný závit", "Šestihranná matice - uzavřená - jemný závit", ["DIN 1587 F"], CAP, _cap(CAP),
           ["s", "h", "thread depth"], "DIN 1587 F M10x1.25", "uzavřená klobouková matice jemný závit fine cap nut", fine=True)


def _square(d, row):
    s, m = row
    d["m"], d["s"] = m, s
    return S.hex_nut(d["d"], d["P"], d["tap"], s, m, sides=4)


nut_family("DIN 557", "Čtyřhranná matice", "Čtyřhranná matice", ["DIN 557"], SQN, _square, ["s", "m"], "DIN 557 M8",
           "čtyřhranná matice square nut")
nut_family("DIN 562", "Čtyřhranná matice nízká", "Čtyřhranná matice", ["DIN 562"], SQN_LOW, _square, ["s", "m"], "DIN 562 M5",
           "čtyřhranná matice nízká thin square nut")


def _flange(d, row):
    import cadquery as cq
    s, m, dc, c = row
    d["m"], d["s"] = m, s
    fl = F.revolve([(0, 0), (dc / 2, 0), (dc / 2, c * 0.6), (dc / 2 - c, c), (0, c)])
    body = fl.union(S.chamfered_prism(cq, s, c, m, top=True, bottom=False), clean=True)
    return S.nut_bore(cq, body, d["d"], d["P"], d["tap"], 0, m)


nut_family("DIN 6923", "Matice s přírubou", "Smíšené", ["DIN 6923", "ISO 4161"], FLANGEN, _flange, ["s", "m", "dc", "c"],
           "DIN 6923 M8", "přírubová matice s límcem flange nut")


def _wing(d, row):
    import cadquery as cq
    e, h = row
    d["m"], d["s"] = h, e
    db = 1.9 * d["d"] + 3
    hb = 0.5 * h
    body = F.revolve([(0, 0), (db / 2, 0), (db / 2 * 0.8, hb), (0, hb)])
    t = 0.12 * e
    wing = (cq.Workplane("XZ").polyline([(-db / 2 * 0.6, 0), (-e / 2, h * 0.7), (-e / 2 + 0.06 * e, h), (-db / 2 * 0.5, h),
                                          (db / 2 * 0.5, h), (e / 2 - 0.06 * e, h), (e / 2, h * 0.7), (db / 2 * 0.6, 0)])
            .close().extrude(t / 2, both=True))
    body = body.union(wing, clean=True)
    return S.nut_bore(cq, body, d["d"], d["P"], d["tap"], 0, hb)


nut_family("DIN 315", "Křídlová matice", "Smíšené", ["DIN 315"], WINGN, _wing, ["e", "h"], "DIN 315 M6",
           "křídlová matice motýlek wing nut butterfly")


def _coupling(d, row):
    s, m = row
    d["m"], d["s"] = m, s
    return S.hex_nut(d["d"], d["P"], d["tap"], s, m)


nut_family("DIN 6334", "Spojovací (prodlužovací) matice", "Smíšené", ["DIN 6334"], COUPLING, _coupling, ["s", "m"], "DIN 6334 M8",
           "spojovací prodlužovací matice dlouhá coupling nut")


def _tslot_parse(g, token, kw):
    a = int(float(g["a"]))
    th, b, h, k, l = F.table(TSLOT, a, "DIN 508")
    if g.get("d") and f"M{float(g['d']):g}" != th:
        raise ValueError(f"DIN 508 slot {a}: thread {th}")
    from .std import THREAD
    return {"size": th, "d": float(th[1:]), "P": THREAD[th][0], "tap": THREAD[th][1], "a": a, "b": b, "h": h, "k": k, "l": l, "m": h}


def _tslot(d):
    import cadquery as cq
    a, b, h, k, l = d["a"], d["b"], d["h"], d["k"], d["l"]
    head = cq.Workplane("XY").rect(b, l).extrude(k).edges("|Z").chamfer(0.12 * b)
    neck = cq.Workplane("XY").workplane(offset=k).rect(a - 0.2, l).extrude(h - k)
    body = head.union(neck).edges(">Z").chamfer(0.08 * a)
    return F.body_color(S.nut_bore(cq, body, d["d"], d["P"], d["tap"], 0, h), F.STEEL)


register(Family("DIN 508", "Matice do T-drážky", "Matice/Smíšené", nums=["DIN 508"],
                regex=r"(?:M(?P<d>\d+(?:\.\d+)?)\s*x\s*)?(?P<a>\d+)", parse=_tslot_parse, build=_tslot,
                rows=[[k, *v] for k, v in TSLOT.items()], columns=["slot a", "thread", "b", "h", "k", "l"],
                example="DIN 508 M10x12", aliases="matice do T drážky t-slot nut upínací stůl", source=SRC,
                anchors=nut_anchors, note="Code: thread x slot width. Head (wide part) at the bottom, Z=0."))


def _km_parse(g, token, kw):
    k = "KM" + g["n"]
    dd, P, d1, B, sb, sh = F.table(KM, k, "KM")
    return {"size": f"M{dd:g}x{P:g}", "d": dd, "P": P, "tap": round(dd - P, 2), "d1": d1, "m": B, "sb": sb, "sh": sh, "km": k, "std_code": k}


def _km(d):
    import cadquery as cq
    d1, B = d["d1"], d["m"]
    body = cq.Workplane("XY").circle(d1 / 2).extrude(B).edges().chamfer(0.5)
    for i in range(4):
        slot = cq.Workplane("XY").center(d1 / 2, 0).rect(2 * d["sh"], d["sb"]).extrude(B + 1).translate((0, 0, -0.5))
        body = body.cut(slot.rotate((0, 0, 0), (0, 0, 1), 90 * i))
    return F.body_color(S.nut_bore(cq, body, d["d"], d["P"], d["tap"], 0, B, csk=True), F.BLACK_OX)


register(Family("DIN 981", "Válcová matice KM (pro ložiska)", "Matice/Válcová matice", nums=["DIN 981"], words=["KM"],
                regex=r"(?:KM)?\s*(?P<n>\d+)", parse=_km_parse, build=_km,
                rows=[[k, f"M{v[0]}x{v[1]:g}", v[2], v[3]] for k, v in KM.items()], columns=["code", "thread", "d1", "B"],
                example="KM4", aliases="válcová matice drážková ložisková pojistná KM lock nut bearing", source=SRC,
                anchors=nut_anchors, color=F.BLACK_OX, note="Use with an MB lock washer (DIN 5406)."))

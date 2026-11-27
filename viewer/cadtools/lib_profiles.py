"""Structural profiles (Konstrukční prvky): IPE, IPN, HEA / HEB / HEM, UPN, UPE, equal and unequal angles,
square / rectangular / round tubes, flat and round bar, aluminium slot profiles, plus custom I / U sections.
Section in the XY plane, length along +Z from 0 to L (code 'IPE 200x1500' or part('IPE 200', L=1500)).
I, H, U, tubes, bars: bounding box centred on the axis; angles: heel (outer corner) on the axis, legs along +X / +Y.
Tables EN 10365 / EN 10056-1 typed from general knowledge (unverified) with the catalogue mass per metre; the
self check compares the modelled section mass with it."""
import math

from . import famreg as F
from .famreg import Family, register

SRC = "EN 10365 / EN 10056-1 / EN 10219 section tables, typed from general knowledge"
RHO = 7.85e-6  # kg/mm3 steel

# h, b, tw, tf, r, kg/m
IPE = {80: (80, 46, 3.8, 5.2, 5, 6.0), 100: (100, 55, 4.1, 5.7, 7, 8.1), 120: (120, 64, 4.4, 6.3, 7, 10.4), 140: (140, 73, 4.7, 6.9, 7, 12.9),
       160: (160, 82, 5.0, 7.4, 9, 15.8), 180: (180, 91, 5.3, 8.0, 9, 18.8), 200: (200, 100, 5.6, 8.5, 12, 22.4), 220: (220, 110, 5.9, 9.2, 12, 26.2),
       240: (240, 120, 6.2, 9.8, 15, 30.7), 270: (270, 135, 6.6, 10.2, 15, 36.1), 300: (300, 150, 7.1, 10.7, 15, 42.2),
       330: (330, 160, 7.5, 11.5, 18, 49.1), 360: (360, 170, 8.0, 12.7, 18, 57.1), 400: (400, 180, 8.6, 13.5, 21, 66.3),
       450: (450, 190, 9.4, 14.6, 21, 77.6), 500: (500, 200, 10.2, 16.0, 21, 90.7), 550: (550, 210, 11.1, 17.2, 24, 106), 600: (600, 220, 12.0, 19.0, 24, 122)}
HEA = {100: (96, 100, 5, 8, 12, 16.7), 120: (114, 120, 5, 8, 12, 19.9), 140: (133, 140, 5.5, 8.5, 12, 24.7), 160: (152, 160, 6, 9, 15, 30.4),
       180: (171, 180, 6, 9.5, 15, 35.5), 200: (190, 200, 6.5, 10, 18, 42.3), 220: (210, 220, 7, 11, 18, 50.5), 240: (230, 240, 7.5, 12, 21, 60.3),
       260: (250, 260, 7.5, 12.5, 24, 68.2), 280: (270, 280, 8, 13, 24, 76.4), 300: (290, 300, 8.5, 14, 27, 88.3), 320: (310, 300, 9, 15.5, 27, 97.6),
       340: (330, 300, 9.5, 16.5, 27, 105), 360: (350, 300, 10, 17.5, 27, 112), 400: (390, 300, 11, 19, 27, 125), 450: (440, 300, 11.5, 21, 27, 140),
       500: (490, 300, 12, 23, 27, 155)}
HEB = {100: (100, 100, 6, 10, 12, 20.4), 120: (120, 120, 6.5, 11, 12, 26.7), 140: (140, 140, 7, 12, 12, 33.7), 160: (160, 160, 8, 13, 15, 42.6),
       180: (180, 180, 8.5, 14, 15, 51.2), 200: (200, 200, 9, 15, 18, 61.3), 220: (220, 220, 9.5, 16, 18, 71.5), 240: (240, 240, 10, 17, 21, 83.2),
       260: (260, 260, 10, 17.5, 24, 93.0), 280: (280, 280, 10.5, 18, 24, 103), 300: (300, 300, 11, 19, 27, 117), 320: (320, 300, 11.5, 20.5, 27, 127),
       340: (340, 300, 12, 21.5, 27, 134), 360: (360, 300, 12.5, 22.5, 27, 142), 400: (400, 300, 13.5, 24, 27, 155), 450: (450, 300, 14, 26, 27, 171),
       500: (500, 300, 14.5, 28, 27, 187)}
HEM = {100: (120, 106, 12, 20, 12, 41.8), 120: (140, 126, 12.5, 21, 12, 52.1), 140: (160, 146, 13, 22, 12, 63.2), 160: (180, 166, 14, 23, 15, 76.2),
       180: (200, 186, 14.5, 24, 15, 88.9), 200: (220, 206, 15, 25, 18, 103), 220: (240, 226, 15.5, 26, 18, 117), 240: (270, 248, 18, 32, 21, 157),
       260: (290, 268, 18, 32.5, 24, 172), 280: (310, 288, 18.5, 33, 24, 189), 300: (340, 310, 21, 39, 27, 238)}
# IPN: h, b, tw, tf (at b/4), r1, r2, kg/m ; flange slope 14 %
IPN = {80: (80, 42, 3.9, 5.9, 3.9, 2.3, 5.94), 100: (100, 50, 4.5, 6.8, 4.5, 2.7, 8.34), 120: (120, 58, 5.1, 7.7, 5.1, 3.1, 11.1),
       140: (140, 66, 5.7, 8.6, 5.7, 3.4, 14.3), 160: (160, 74, 6.3, 9.5, 6.3, 3.8, 17.9), 180: (180, 82, 6.9, 10.4, 6.9, 4.1, 21.9),
       200: (200, 90, 7.5, 11.3, 7.5, 4.5, 26.2), 220: (220, 98, 8.1, 12.2, 8.1, 4.9, 31.1), 240: (240, 106, 8.7, 13.1, 8.7, 5.2, 36.2),
       260: (260, 113, 9.4, 14.1, 9.4, 5.6, 41.9), 280: (280, 119, 10.1, 15.2, 10.1, 6.1, 47.9), 300: (300, 125, 10.8, 16.2, 10.8, 6.5, 54.2),
       320: (320, 131, 11.5, 17.3, 11.5, 6.9, 61.0), 340: (340, 137, 12.2, 18.3, 12.2, 7.3, 68.0), 360: (360, 143, 13.0, 19.5, 13.0, 7.8, 76.1),
       400: (400, 155, 14.4, 21.6, 14.4, 8.6, 92.4)}
# UPN: h, b, tw, tf (at b/2), r1, r2, kg/m ; flange slope 8 % (h <= 300) / 5 %
UPN = {50: (50, 38, 5, 7, 7, 3.5, 5.59), 65: (65, 42, 5.5, 7.5, 7.5, 4, 7.09), 80: (80, 45, 6, 8, 8, 4, 8.64), 100: (100, 50, 6, 8.5, 8.5, 4.5, 10.6),
       120: (120, 55, 7, 9, 9, 4.5, 13.4), 140: (140, 60, 7, 10, 10, 5, 16.0), 160: (160, 65, 7.5, 10.5, 10.5, 5.5, 18.8),
       180: (180, 70, 8, 11, 11, 5.5, 22.0), 200: (200, 75, 8.5, 11.5, 11.5, 6, 25.3), 220: (220, 80, 9, 12.5, 12.5, 6.5, 29.4),
       240: (240, 85, 9.5, 13, 13, 6.5, 33.2), 260: (260, 90, 10, 14, 14, 7, 37.9), 280: (280, 95, 10, 15, 15, 7.5, 41.8),
       300: (300, 100, 10, 16, 16, 8, 46.2), 320: (320, 100, 14, 17.5, 17.5, 8.75, 59.5), 350: (350, 100, 14, 16, 16, 8, 60.6),
       380: (380, 102, 13.5, 16, 16, 8, 63.1), 400: (400, 110, 14, 18, 18, 9, 71.8)}
UPE = {80: (80, 50, 4, 7, 10, 7.9), 100: (100, 55, 4.5, 7.5, 10, 9.82), 120: (120, 60, 5, 8, 12, 12.1), 140: (140, 65, 5, 9, 12, 14.5),
       160: (160, 70, 5.5, 9.5, 12, 17.0), 180: (180, 75, 5.5, 10.5, 12, 19.7), 200: (200, 80, 6, 11, 13, 22.8), 220: (220, 85, 6.5, 12, 13, 26.6),
       240: (240, 90, 7, 12.5, 15, 30.2), 270: (270, 95, 7.5, 13.5, 15, 35.2), 300: (300, 100, 9.5, 15, 15, 44.4)}
# equal angle a x t: r1, r2, kg/m ; unequal a x b x t: r1, r2, kg/m
LEQ = {(20, 3): (3.5, 2, 0.88), (25, 3): (3.5, 2, 1.12), (25, 4): (3.5, 2, 1.45), (30, 3): (5, 2.5, 1.36), (30, 4): (5, 2.5, 1.78),
       (35, 4): (5, 2.5, 2.09), (40, 4): (6, 3, 2.42), (40, 5): (6, 3, 2.97), (45, 4.5): (7, 3.5, 3.06), (50, 5): (7, 3.5, 3.77),
       (50, 6): (7, 3.5, 4.47), (60, 6): (8, 4, 5.42), (60, 8): (8, 4, 7.09), (70, 7): (9, 4.5, 7.38), (80, 8): (10, 5, 9.63),
       (90, 9): (11, 5.5, 12.2), (100, 10): (12, 6, 15.0), (120, 12): (13, 6.5, 21.6), (150, 15): (16, 8, 33.8), (200, 20): (18, 9, 59.9)}
LUN = {(30, 20, 3): (4, 2, 1.12), (40, 20, 4): (4, 2, 1.77), (50, 30, 5): (5, 2.5, 2.96), (60, 40, 5): (6, 3, 3.76), (60, 40, 6): (6, 3, 4.46),
       (75, 50, 6): (7, 3.5, 5.65), (80, 40, 6): (7, 3.5, 5.41), (100, 50, 8): (9, 4.5, 8.97), (100, 75, 8): (10, 5, 10.6),
       (120, 80, 10): (11, 5.5, 15.0), (150, 100, 10): (12, 6, 19.0)}


def _L(d, kw):
    L = F.num(d.get("L")) or kw.get("L") or 1000.0
    return float(L)


def p_anchors(d):
    return {"end_a": (0, 0, 0), "end_b": (0, 0, d["L"]), "centre": (0, 0, d["L"] / 2), "axis": "+Z = length"}


def _fillet_pts(cx, cy, r, a0, a1, n=1):
    """mid point of an arc of radius r around (cx, cy) between angles a0, a1 [rad]."""
    am = (a0 + a1) / 2
    return (cx + r * math.cos(am), cy + r * math.sin(am))


def i_section(h, b, tw, tf, r, slope=0.0, r2=0.0):
    """I / H section (parallel flanges, root radius r; slope > 0: tapered inner flange faces like IPN, tf at b/4)."""
    import cadquery as cq
    if slope <= 0:
        x1 = tw / 2
        y1 = h / 2 - tf
        pts = []
        wp = cq.Workplane("XY").moveTo(-b / 2, -h / 2).lineTo(b / 2, -h / 2).lineTo(b / 2, -y1).lineTo(x1 + r, -y1)
        wp = wp.threePointArc(_fillet_pts(x1 + r, -y1 + r, r, -math.pi / 2, -math.pi), (x1, -y1 + r))
        wp = wp.lineTo(x1, y1 - r).threePointArc(_fillet_pts(x1 + r, y1 - r, r, math.pi, math.pi / 2), (x1 + r, y1))
        wp = wp.lineTo(b / 2, y1).lineTo(b / 2, h / 2).lineTo(-b / 2, h / 2).lineTo(-b / 2, y1).lineTo(-x1 - r, y1)
        wp = wp.threePointArc(_fillet_pts(-x1 - r, y1 - r, r, math.pi / 2, 0), (-x1, y1 - r))
        wp = wp.lineTo(-x1, -y1 + r).threePointArc(_fillet_pts(-x1 - r, -y1 + r, r, 0, -math.pi / 2), (-x1 - r, -y1))
        wp = wp.lineTo(-b / 2, -y1).close()
        return wp
    # tapered flanges: inner face line through (b/4, h/2 - tf) with slope; tip thickness, root by r (simplified: chamfer-like
    # straight taper, root and tip radii approximated by short arcs)
    xq = b / 4
    def yin(x):  # inner flange face y (upper flange) at x
        return h / 2 - tf - (xq - x) * slope
    x_tip = b / 2
    y_tip = yin(x_tip) - 0.0
    x_root = tw / 2
    y_root = yin(x_root)
    rr = r
    wp = cq.Workplane("XY").moveTo(-b / 2, h / 2).lineTo(b / 2, h / 2).lineTo(b / 2, y_tip + r2 * 0.3)
    wp = wp.lineTo(x_root + rr, yin(x_root + rr)).threePointArc((x_root + rr * 0.3, yin(x_root + rr * 0.3) - rr * 0.3), (x_root, y_root - rr))
    wp = wp.lineTo(x_root, -(y_root - rr)).threePointArc((x_root + rr * 0.3, -(yin(x_root + rr * 0.3) - rr * 0.3)), (x_root + rr, -yin(x_root + rr)))
    wp = wp.lineTo(b / 2, -(y_tip + r2 * 0.3)).lineTo(b / 2, -h / 2).lineTo(-b / 2, -h / 2).lineTo(-b / 2, -(y_tip + r2 * 0.3))
    wp = wp.lineTo(-(x_root + rr), -yin(x_root + rr)).threePointArc((-(x_root + rr * 0.3), -(yin(x_root + rr * 0.3) - rr * 0.3)), (-x_root, -(y_root - rr)))
    wp = wp.lineTo(-x_root, y_root - rr).threePointArc((-(x_root + rr * 0.3), yin(x_root + rr * 0.3) - rr * 0.3), (-(x_root + rr), yin(x_root + rr)))
    wp = wp.lineTo(-b / 2, y_tip + r2 * 0.3).close()
    return wp


def u_section(h, b, tw, tf, r, slope=0.0):
    """Channel: web on the left (x = -b/2), flanges to +X; tapered inner flange faces when slope > 0 (tf at b/2)."""
    import cadquery as cq
    x0 = -b / 2
    xw = x0 + tw
    xm = x0 + b / 2
    def yin(x):
        return h / 2 - tf - (xm - x) * slope
    rr = r
    wp = cq.Workplane("XY").moveTo(x0, -h / 2).lineTo(b / 2, -h / 2).lineTo(b / 2, -yin(b / 2))
    wp = wp.lineTo(xw + rr, -yin(xw + rr)).threePointArc((xw + rr * 0.29, -(yin(xw + rr * 0.29) - rr * 0.29)), (xw, -(yin(xw) - rr)))
    wp = wp.lineTo(xw, yin(xw) - rr).threePointArc((xw + rr * 0.29, yin(xw + rr * 0.29) - rr * 0.29), (xw + rr, yin(xw + rr)))
    wp = wp.lineTo(b / 2, yin(b / 2)).lineTo(b / 2, h / 2).lineTo(x0, h / 2).close()
    return wp


def l_section(a, b, t, r1, r2):
    """Angle: heel at the origin, legs along +X (a) and +Y (b), root radius r1, toe radius r2."""
    import cadquery as cq
    c = math.sqrt(0.5)
    wp = cq.Workplane("XY").moveTo(0, 0).lineTo(a, 0).lineTo(a, t - r2)
    wp = wp.threePointArc((a - r2 + r2 * c, t - r2 + r2 * c), (a - r2, t))
    wp = wp.lineTo(t + r1, t).threePointArc((t + r1 - r1 * c, t + r1 - r1 * c), (t, t + r1))
    wp = wp.lineTo(t, b - r2).threePointArc((t - r2 + r2 * c, b - r2 + r2 * c), (t - r2, b))
    wp = wp.lineTo(0, b).close()
    return wp


def _extrude(section, L):
    return section.extrude(L)


def _mass_ref(d):
    return d.get("kgm")


def prof_family(fid, title, sub, tab, words, section, columns, example, aliases, keyfmt=str, note="", color=F.STRUCT, kind="I"):
    def parse(g, token, kw):
        key = int(float(g["n"]))
        row = F.table(tab, key, fid)
        d = {"n": key, "row": row, "L": _L(g, kw), "size": f"{fid} {key}", "profile": f"{fid} {key}", "kgm": row[-1], "type": "purchased"}
        return d

    def build(d):
        w = _extrude(section(d["row"]), d["L"])
        return F.body_color(w, color)

    rows = [[keyfmt(k), *v] for k, v in tab.items()]
    return register(Family(fid, title, "Konstrukční prvky/" + sub, words=words,
                           regex=r"(?P<n>\d+)(?:\s*x\s*(?P<L>\d+(?:\.\d+)?))?", parse=parse, build=build, rows=rows,
                           columns=["size", *columns], example=example, aliases=aliases, ptype="purchased", source=SRC,
                           anchors=p_anchors, note=note or "Section centred, length along +Z. Code: <size>x<length> or part(code, L=...).",
                           mass_ref=_mass_ref))


prof_family("IPE", "Profil IPE", "Profil IPE", IPE, ["IPE"], lambda r: i_section(*r[:5]), ["h", "b", "tw", "tf", "r", "kg/m"],
            "IPE 200x1500", "nosník I profil ipe beam evropský")
prof_family("HEA", "Profil HEA (HE A)", "Profil HE", HEA, ["HEA", "HE A", "IPBL"], lambda r: i_section(*r[:5]), ["h", "b", "tw", "tf", "r", "kg/m"],
            "HEA 200x2000", "nosník H profil HEA hea širokopřírubový wide flange")
prof_family("HEB", "Profil HEB (HE B)", "Profil HE", HEB, ["HEB", "HE B", "IPB"], lambda r: i_section(*r[:5]), ["h", "b", "tw", "tf", "r", "kg/m"],
            "HEB 200x2000", "nosník H profil HEB heb širokopřírubový wide flange")
prof_family("HEM", "Profil HEM (HE M)", "Profil HE", HEM, ["HEM", "HE M", "IPBV"], lambda r: i_section(*r[:5]), ["h", "b", "tw", "tf", "r", "kg/m"],
            "HEM 200x2000", "nosník H profil HEM hem zesílený")
prof_family("IPN", "Profil IPN (I, úkosové příruby)", "Profil IPN", IPN, ["IPN", "INP"],
            lambda r: i_section(r[0], r[1], r[2], r[3], r[4], slope=0.14, r2=r[5]), ["h", "b", "tw", "tf", "r1", "r2", "kg/m"],
            "IPN 200x1500", "nosník I profil normální úkosový ipn")
prof_family("UPN", "Profil UPN (U, úkosové příruby)", "Profil UPN", UPN, ["UPN", "UNP", "U"],
            lambda r: u_section(r[0], r[1], r[2], r[3], r[4], slope=0.08 if r[0] <= 300 else 0.05), ["h", "b", "tw", "tf", "r1", "r2", "kg/m"],
            "UPN 100x1000", "U profil úkosový channel upn", note="Web at x = -b/2, flanges towards +X, bounding box centred.")
prof_family("UPE", "Profil UPE (U, rovnoběžné příruby)", "Profil U", UPE, ["UPE"], lambda r: u_section(*r[:5]), ["h", "b", "tw", "tf", "r", "kg/m"],
            "UPE 120x1000", "U profil rovnoběžné příruby channel parallel upe", note="Web at x = -b/2, flanges towards +X.")


def _leq_parse(g, token, kw):
    a, t = float(g["a"]), float(g["t"])
    key =(int(a) if a.is_integer() else a, int(t) if t.is_integer() else t)
    r1, r2, kgm = F.table(LEQ, key, "L")
    return {"a": a, "b": a, "t": t, "r1": r1, "r2": r2, "kgm": kgm, "L": _L(g, kw), "size": f"L {a:g}x{t:g}", "profile": f"L {a:g}x{t:g}",
            "type": "purchased"}


def _lun_parse(g, token, kw):
    a, b, t = float(g["a"]), float(g["b"]), float(g["t"])
    key = tuple(int(x) if x.is_integer() else x for x in (a, b, t))
    if a == b:
        r1, r2, kgm = F.table(LEQ, (key[0], key[2]), "L")
    else:
        r1, r2, kgm = F.table(LUN, key, "L")
    return {"a": a, "b": b, "t": t, "r1": r1, "r2": r2, "kgm": kgm, "L": _L(g, kw), "size": f"L {a:g}x{b:g}x{t:g}",
            "profile": f"L {a:g}x{b:g}x{t:g}", "type": "purchased"}


def _angle(d):
    return F.body_color(l_section(d["a"], d["b"], d["t"], d["r1"], d["r2"]).extrude(d["L"]), F.STRUCT)


register(Family("L unequal", "Úhelník L nerovnoramenný", "Konstrukční prvky/Úhelník L", words=["L"],
                regex=r"(?P<a>\d+(?:\.\d+)?)\s*x\s*(?P<b>\d+(?:\.\d+)?)\s*x\s*(?P<t>\d+(?:\.\d+)?)(?:\s*x\s*(?P<L>\d+(?:\.\d+)?))?\s*$",
                parse=_lun_parse, build=_angle, rows=[[f"{k[0]}x{k[1]}x{k[2]}", *v] for k, v in LUN.items()],
                columns=["a x b x t", "r1", "r2", "kg/m"], example="L 60x40x6x1000", aliases="úhelník nerovnoramenný unequal angle L profil",
                source=SRC, ptype="purchased", anchors=p_anchors, color=F.STRUCT, mass_ref=_mass_ref,
                note="Heel on the axis, leg a along +X, leg b along +Y, length along +Z."))
register(Family("L", "Úhelník L rovnoramenný", "Konstrukční prvky/Úhelník L", words=["L"],
                regex=r"(?P<a>\d+(?:\.\d+)?)\s*x\s*(?P<t>\d+(?:\.\d+)?)(?:\s*x\s*(?P<L>\d+(?:\.\d+)?))?\s*$",
                parse=_leq_parse, build=_angle, rows=[[f"{k[0]}x{k[1]}", *v] for k, v in LEQ.items()],
                columns=["a x t", "r1", "r2", "kg/m"], example="L 50x5x1000", aliases="úhelník rovnoramenný equal angle L profil",
                source=SRC, ptype="purchased", anchors=p_anchors, color=F.STRUCT, mass_ref=_mass_ref,
                note="Heel on the axis, legs along +X and +Y, length along +Z. Code: L a x t x length."))


def _tube_parse(kind):
    def p(g, token, kw):
        if kind == "SHS":
            B = H = float(g["a"])
            t = float(g["b"])
            L = F.num(g.get("c"))
            if g.get("d"):  # 'SHS 40x40x3x1000'
                H, t, L = float(g["b"]), float(g["c"]), F.num(g.get("d"))
        else:
            B, H, t, L = float(g["a"]), float(g["b"]), float(g["c"]), F.num(g.get("d"))
        L = float(L or kw.get("L") or 1000)
        ro = 2 * t if t <= 6 else 2.5 * t
        area = B * H - (B - 2 * t) * (H - 2 * t) - (4 - math.pi) * (ro ** 2 - max(ro - t, 0) ** 2)
        return {"B": B, "H": H, "t": t, "L": L, "ro": ro, "kgm": round(area * RHO * 1000, 2), "size": f"{kind} {B:g}x{H:g}x{t:g}",
                "profile": f"{kind} {B:g}x{H:g}x{t:g}", "type": "purchased"}
    return p


def _tube(d):
    import cadquery as cq
    B, H, t, ro = d["B"], d["H"], d["t"], d["ro"]
    ri = max(ro - t, 0.01)
    outer = cq.Workplane("XY").sketch().rect(B, H).vertices().fillet(ro).finalize().extrude(d["L"])
    inner = cq.Workplane("XY").sketch().rect(B - 2 * t, H - 2 * t).vertices().fillet(ri).finalize().extrude(d["L"] + 2).translate((0, 0, -1))
    return F.body_color(outer.cut(inner), F.STRUCT)


TUBES = "Uzavřené profily"
NUM = r"(?P<a>\d+(?:\.\d+)?)\s*x\s*(?P<b>\d+(?:\.\d+)?)\s*x\s*(?P<c>\d+(?:\.\d+)?)(?:\s*x\s*(?P<d>\d+(?:\.\d+)?))?"
register(Family("RHS", "Jekl obdélníkový (RHS)", "Konstrukční prvky/" + TUBES, words=["RHS", "JEKL", "TR4HR"], regex=NUM, parse=_tube_parse("RHS"),
                build=_tube, rows=[["B x H x t (any)"]], columns=["code"], example="RHS 60x40x3x1000",
                aliases="jekl obdélníkový uzavřený profil rectangular hollow section tube", source="EN 10219 cold formed, ro = 2t (t<=6) / 2.5t",
                ptype="purchased", anchors=p_anchors, color=F.STRUCT, mass_ref=_mass_ref))
register(Family("SHS", "Jekl čtvercový (SHS)", "Konstrukční prvky/" + TUBES, words=["SHS", "TR4HR"],
                regex=r"(?P<a>\d+(?:\.\d+)?)\s*x\s*(?P<b>\d+(?:\.\d+)?)(?:\s*x\s*(?P<c>\d+(?:\.\d+)?))?(?:\s*x\s*(?P<d>\d+(?:\.\d+)?))?",
                parse=_tube_parse("SHS"), build=_tube, rows=[["a x t (any)"]], columns=["code"], example="SHS 40x3x1000",
                aliases="jekl čtvercový uzavřený profil square hollow section tube", source="EN 10219 cold formed, ro = 2t (t<=6) / 2.5t",
                ptype="purchased", anchors=p_anchors, color=F.STRUCT, mass_ref=_mass_ref, note="SHS a x t x L (or a x a x t x L)."))


def _chs_parse(g, token, kw):
    D, t = float(g["a"]), float(g["b"])
    L = float(F.num(g.get("c")) or kw.get("L") or 1000)
    area = math.pi / 4 * (D * D - (D - 2 * t) ** 2)
    return {"D": D, "t": t, "L": L, "kgm": round(area * RHO * 1000, 2), "size": f"CHS {D:g}x{t:g}", "profile": f"CHS {D:g}x{t:g}", "type": "purchased"}


register(Family("CHS", "Trubka kruhová (CHS)", "Konstrukční prvky/" + TUBES, words=["CHS", "TR", "TRUBKA"],
                regex=r"(?P<a>\d+(?:\.\d+)?)\s*x\s*(?P<b>\d+(?:\.\d+)?)(?:\s*x\s*(?P<c>\d+(?:\.\d+)?))?", parse=_chs_parse,
                build=lambda d: F.body_color(F.ring(d["D"] / 2, d["D"] / 2 - d["t"], d["L"]), F.STRUCT), rows=[["D x t (any)"]],
                columns=["code"], example="CHS 48.3x3.2x1000", aliases="trubka kruhová circular hollow section pipe tube",
                source="EN 10219 / 10210 any D x t", ptype="purchased", anchors=p_anchors, color=F.STRUCT, mass_ref=_mass_ref))


def _flat_parse(g, token, kw):
    b, t = float(g["a"]), float(g["b"])
    L = float(F.num(g.get("c")) or kw.get("L") or 1000)
    return {"b": b, "t": t, "L": L, "kgm": round(b * t * RHO * 1000, 2), "size": f"FL {b:g}x{t:g}", "profile": f"FL {b:g}x{t:g}", "type": "purchased"}


register(Family("FL", "Pásovina (plochá tyč)", "Konstrukční prvky/Tyče", words=["FL", "PLO", "FLAT"],
                regex=r"(?P<a>\d+(?:\.\d+)?)\s*x\s*(?P<b>\d+(?:\.\d+)?)(?:\s*x\s*(?P<c>\d+(?:\.\d+)?))?", parse=_flat_parse,
                build=lambda d: F.body_color(__import__("cadquery").Workplane("XY").rect(d["b"], d["t"]).extrude(d["L"]), F.STRUCT),
                rows=[["b x t (any)"]], columns=["code"], example="FL 40x10x500", aliases="pásovina plochá tyč flat bar",
                source="EN 10058 any b x t", ptype="purchased", anchors=p_anchors, color=F.STRUCT, mass_ref=_mass_ref,
                note="Width b along X, thickness along Y."))


def _round_parse(g, token, kw):
    D = float(g["a"])
    L = float(F.num(g.get("b")) or kw.get("L") or 1000)
    return {"D": D, "L": L, "kgm": round(math.pi / 4 * D * D * RHO * 1000, 2), "size": f"KR {D:g}", "profile": f"KR {D:g}", "type": "purchased"}


register(Family("KR", "Kruhová tyč", "Konstrukční prvky/Tyče", words=["KR", "RD", "TYC"], regex=r"(?P<a>\d+(?:\.\d+)?)(?:\s*x\s*(?P<b>\d+(?:\.\d+)?))?",
                parse=_round_parse, build=lambda d: F.body_color(F.ring(d["D"] / 2, 0, d["L"]), F.STRUCT), rows=[["D (any)"]],
                columns=["code"], example="KR 20x500", aliases="kruhová tyč kulatina round bar", source="EN 10060 any D",
                ptype="purchased", anchors=p_anchors, color=F.STRUCT, mass_ref=_mass_ref))


# ---------------------------------------------------------------- custom sections (any size)

def _custom_i_parse(g, token, kw):
    vals = [float(x) for x in (g["a"], g["b"], g["c"], g["e"])]
    h, b, tw, tf = vals
    r = F.num(g.get("r"), 0.0)
    L = float(kw.get("L") or 1000)
    return {"h": h, "b": b, "tw": tw, "tf": tf, "r": r, "L": L, "size": f"I {h:g}x{b:g}x{tw:g}x{tf:g}", "profile": "I custom", "type": "purchased"}


register(Family("I custom", "Vlastní I profil (h x b x tw x tf [x r])", "Konstrukční prvky/Vlastní", words=["ICUSTOM", "I-PROFIL"],
                regex=r"(?P<a>[\d.]+)\s*x\s*(?P<b>[\d.]+)\s*x\s*(?P<c>[\d.]+)\s*x\s*(?P<e>[\d.]+)(?:\s*x\s*(?P<r>[\d.]+))?",
                parse=_custom_i_parse, build=lambda d: F.body_color(i_section(d["h"], d["b"], d["tw"], d["tf"], max(d["r"], 0.01)).extrude(d["L"]), F.STRUCT),
                rows=[["h x b x tw x tf x r"]], columns=["code"], example="ICUSTOM 200x100x6x9x10",
                aliases="vlastní I profil HD HL HP HX W M S DIL IPEA IPEO IPER IPEV custom beam", source="any section (for profiles without a table)",
                ptype="purchased", anchors=p_anchors, color=F.STRUCT,
                note="For HD / HL / HP / HX / W / M / IPEA / IPEO / IPER / IPEV ... sizes: take h, b, tw, tf, r from the maker's table."))


# aluminium slot profiles (existing simplified envelope, kept in std.part)
def _alu_parse(g, token, kw):
    from .std import PROFILE
    code = g["n"]
    a, slot, bore = F.table(PROFILE, code, "alu profile")
    L = float(F.num(g.get("L")) or kw.get("L") or 1000)
    return {"code": code, "L": L, "profile": code, "size": code, "type": "purchased"}


def _alu(d):
    from .std import part
    return F.body_color(part(f"{d['code']}x{d['L']:g}"), F.ALU)


register(Family("ALU", "Hliníkový drážkový profil", "Konstrukční prvky/Hliníkové profily", words=["ALU", "ITEM", "BOSCH", "VSLOT", "TSLOT"],
                regex=r"(?P<n>\d{4})(?:\s*x\s*(?P<L>\d+(?:\.\d+)?))?", parse=_alu_parse, build=_alu,
                rows=[["2020"], ["2040"], ["3030"], ["3060"], ["4040"], ["4080"], ["4545"]], columns=["profile"], example="ALU 4040x500",
                aliases="hliníkový profil drážkový aluminium extrusion t-slot item bosch", source="typical slot profile envelope (maker dependent)",
                ptype="purchased", anchors=p_anchors, color=F.ALU, note="Simplified section with slots; also plain '2020x200'."))

"""Transmissions (Převody): involute spur / helical gears, racks, chain sprockets (ISO 606 / ANSI).

    part("GEAR m2 z30 b20 d12")             # spur gear, module 2, 30 teeth, face width 20, bore 12
    part("GEAR m2 z30 b20 d12 beta15 x0.2")  # helical 15 deg, profile shift 0.2
    part("RACK m2 b20 L200")
    part("SPROCKET 08B-1 z17 d15")
    gear_pair(m=2, z1=20, z2=40, b=20)      # both gears placed in mesh + centre distance

Gear: real involute flanks (base circle, profile shift x, addendum 1 m, dedendum 1.25 m, root arc), pressure angle 20 deg.
Face A at Z=0, width b up to +Z, axis Z; tooth 0 centred on +X. Sprocket: ISO 606 pitch diameter, roller seating
circle ri and seating angle (straight flanks - simplified tooth form)."""
import math
import re

from . import famreg as F
from .famreg import Family, register

# chain: pitch p, roller d1, inner width b1
CHAIN = {"05B": (8.0, 5.0, 3.0), "06B": (9.525, 6.35, 5.72), "08B": (12.7, 8.51, 7.75), "10B": (15.875, 10.16, 9.65), "12B": (19.05, 12.07, 11.68),
         "16B": (25.4, 15.88, 17.02), "20B": (31.75, 19.05, 19.56), "24B": (38.1, 25.4, 25.4),
         "25": (6.35, 3.3, 3.18), "35": (9.525, 5.08, 4.77), "40": (12.7, 7.92, 7.85), "50": (15.875, 10.16, 9.4), "60": (19.05, 11.91, 12.57),
         "80": (25.4, 15.88, 15.75), "100": (31.75, 19.05, 18.9)}


def inv(a):
    return math.tan(a) - a


def gear_outline(m, z, x=0.0, alpha=20.0, n_flank=7, internal=False):
    """Closed 2D gear outline (cq.Workplane, XY) with involute flanks as splines."""
    import cadquery as cq
    a = math.radians(alpha)
    r = m * z / 2
    rb = r * math.cos(a)
    ra = r + m * (1 + x)
    rf = r - m * (1.25 - x)
    s = m * (math.pi / 2 + 2 * x * math.tan(a))       # tooth thickness on the pitch circle
    psi = s / (2 * r)                                 # half tooth angle at the pitch circle
    def theta(rho):                                   # half tooth angle at radius rho (involute part)
        ar = math.acos(min(1.0, rb / rho))
        return psi + inv(a) - inv(ar)
    r0 = max(rb, rf)
    rads = [r0 + (ra - r0) * (i / (n_flank - 1)) ** 1.2 for i in range(n_flank)]
    pitch = 2 * math.pi / z

    def pol(rr, ang):
        return (rr * math.cos(ang), rr * math.sin(ang))
    wp = None
    for k in range(z):
        c = k * pitch
        right = [pol(rr, c - theta(rr)) for rr in rads]          # from root to tip
        left = [pol(rr, c + theta(rr)) for rr in reversed(rads)]  # from tip to root
        t_tip = theta(ra)
        if wp is None:
            start = pol(rf, c - theta(r0)) if rf < rb else right[0]
            wp = cq.Workplane("XY").moveTo(*start)
            if rf < rb:
                wp = wp.lineTo(*right[0])
        elif rf < rb:  # current point is already on the root circle below this flank
            wp = wp.lineTo(*right[0])
        wp = wp.spline(right[1:], includeCurrent=True)
        wp = wp.threePointArc(pol(ra, c), left[0])
        wp = wp.spline(left[1:], includeCurrent=True)
        end_ang = c + theta(r0)
        if rf < rb:
            wp = wp.lineTo(*pol(rf, end_ang))
        nxt = (k + 1) * pitch - theta(r0)
        wp = wp.threePointArc(pol(rf, (end_ang + nxt) / 2), pol(rf, nxt))
    return wp.close(), {"d": 2 * r, "da": 2 * ra, "df": 2 * rf, "db": 2 * rb}


def _gear_parse(g, token, kw):
    m = float(g["m"])
    z = int(g["z"])
    b = float(g.get("b") or kw.get("b") or 10 * m)
    bore = F.num(g.get("bore")) or kw.get("bore") or 0.0
    beta = F.num(g.get("beta")) or kw.get("beta") or 0.0
    x = F.num(g.get("x")) or kw.get("x") or 0.0
    if z < 6:
        raise ValueError("at least 6 teeth")
    mt = m / math.cos(math.radians(beta))
    dims = {"m": m, "z": z, "b": b, "bore": bore, "beta": beta, "x": x, "alpha": 20.0, "d": round(mt * z, 3),
            "da": round(mt * z + 2 * m * (1 + x), 3), "df": round(mt * z - 2 * m * (1.25 - x), 3), "size": f"m{m:g} z{z}", "type": "custom",
            "hub_d": kw.get("hub_d"), "hub_l": kw.get("hub_l"), "keyway": kw.get("keyway")}
    if z < 17 and x == 0:
        dims["warning"] = f"z={z} < 17 undercuts without profile shift (x >= {round((17 - z) / 17, 2)})"
    return dims


def _gear(d):
    import cadquery as cq
    m, z, b, beta, x = d["m"], d["z"], d["b"], d["beta"], d["x"]
    mt = m / math.cos(math.radians(beta))
    outline, _ = gear_outline(mt, z, x * m / mt, d["alpha"])
    if beta:
        twist = math.degrees(b * math.tan(math.radians(beta)) / (mt * z / 2))
        body = outline.twistExtrude(b, twist)
    else:
        body = outline.extrude(b)
    if d.get("hub_d") and d.get("hub_l"):
        body = body.union(F.ring(d["hub_d"] / 2, 0, d["hub_l"], b))
    top = b + (d.get("hub_l") or 0 if d.get("hub_d") else 0)
    if d["bore"]:
        body = body.cut(F.ring(d["bore"] / 2, 0, top + 2, -1))
        if d.get("keyway"):  # 'keyway': True -> DIN 6885 hub groove for the bore
            from .lib_shaft import KEYS
            for (kb, kh), (t1, t2, lo, hi) in KEYS.items():
                if lo < d["bore"] <= hi:
                    body = body.cut(cq.Workplane("XY").center(d["bore"] / 2, 0).rect(2 * t2 + 0.4, kb).extrude(top + 2).translate((0, 0, -1)))
                    break
    return F.body_color(body, F.STEEL)


def g_anchors(d):
    return {"face_a": (0, 0, 0), "face_b": (0, 0, d["b"]), "centre": (0, 0, d["b"] / 2), "axis": "+Z; tooth 0 on +X"}


register(Family("GEAR", "Ozubené kolo čelní (evolventní)", "Převody/Ozubená kola", words=["GEAR", "OZUBENE KOLO", "KOLO"],
                regex=r"M\s*(?P<m>[\d.]+)\s*Z\s*(?P<z>\d+)(?:\s*B\s*(?P<b>[\d.]+))?(?:\s*D\s*(?P<bore>[\d.]+))?(?:\s*BETA\s*(?P<beta>-?[\d.]+))?(?:\s*X\s*(?P<x>-?[\d.]+))?",
                parse=_gear_parse, build=_gear, rows=[["m z b d beta x (any)"]], columns=["code"], example="GEAR m2 z30 b20 d12",
                aliases="ozubené kolo čelní šikmé evolventa spur helical gear pastorek pinion", source="involute ISO 53 basic rack, alpha 20 deg",
                ptype="custom", anchors=g_anchors,
                note="Keyword arguments: hub_d, hub_l (hub on face B), keyway=True (hub groove for the bore). beta = helix angle."))


def _rack_parse(g, token, kw):
    m = float(g["m"])
    b = float(g.get("b") or kw.get("b") or 10 * m)
    L = float(g.get("L") or kw.get("L") or 100)
    h = float(g.get("h") or kw.get("h") or max(2.25 * m + 3 * m, 6 * m))
    return {"m": m, "b": b, "L": L, "h": h, "size": f"m{m:g} L{L:g}", "type": "custom"}


def _rack(d):
    import cadquery as cq
    m, b, L, h = d["m"], d["b"], d["L"], d["h"]
    p = math.pi * m
    a = math.radians(20)
    n = int(L / p) + 1
    top = h            # pitch line at h - m ; tips at h
    pl = h - m
    pts = [(0, 0), (L, 0), (L, pl - 1.25 * m)]
    x = L
    # teeth from right to left: trapezoids around the pitch line
    for i in range(n, -1, -1):
        xc = i * p
        half_tip = p / 4 - m * math.tan(a)
        half_root = p / 4 + 1.25 * m * math.tan(a)
        for xx, yy in ((xc + half_root, pl - 1.25 * m), (xc + half_tip, top), (xc - half_tip, top), (xc - half_root, pl - 1.25 * m)):
            pts.append((min(max(xx, 0), L), yy))
    pts.append((0, pl - 1.25 * m))
    clean = [pts[0]]
    for q in pts[1:]:
        if abs(q[0] - clean[-1][0]) > 1e-6 or abs(q[1] - clean[-1][1]) > 1e-6:
            clean.append(q)
    prof = cq.Workplane("XZ").polyline(clean).close()
    return F.body_color(prof.extrude(-b), F.STEEL)


register(Family("RACK", "Ozubený hřeben", "Převody/Ozubená kola", words=["RACK", "HREBEN"],
                regex=r"M\s*(?P<m>[\d.]+)(?:\s*B\s*(?P<b>[\d.]+))?(?:\s*L\s*(?P<L>[\d.]+))?(?:\s*H\s*(?P<h>[\d.]+))?",
                parse=_rack_parse, build=_rack, rows=[["m b L h (any)"]], columns=["code"], example="RACK m2 b20 L200",
                aliases="ozubený hřeben rack", source="ISO 53 basic rack, alpha 20 deg", ptype="custom",
                anchors=lambda d: {"origin": (0, 0, 0), "pitch_line": (0, 0, d["h"] - d["m"]), "axis": "length +X, teeth up +Z, width +Y"},
                note="Length along +X, teeth up (+Z), pitch line at Z = h - m, width b along +Y. First tooth centred at X=0."))


def _spr_parse(g, token, kw):
    ch = g["chain"].upper().replace(" ", "")
    strands = int(g.get("n") or 1)
    p, d1, b1 = F.table(CHAIN, ch, "chain")
    z = int(g["z"])
    bore = F.num(g.get("bore")) or kw.get("bore") or 0.0
    dp = p / math.sin(math.pi / z)
    return {"chain": ch, "strands": strands, "p": p, "d1": d1, "b1": b1, "z": z, "bore": bore, "dp": round(dp, 3),
            "df": round(dp - d1, 3), "da": round(dp + 1.25 * p - d1 - 0.5 * (1.25 * p - p * (1 - 1.6 / z)), 3),
            "bf": round((0.93 if p <= 12.7 else 0.95) * b1, 2), "size": f"{ch}-{strands} z{z}", "type": "custom"}


def _sprocket(d):
    import cadquery as cq
    p, d1, z = d["p"], d["d1"], d["z"]
    dp, da, bf = d["dp"], d["da"], d["bf"]
    ri = 0.505 * d1 + 0.069 * d1 ** (1 / 3)
    alpha = math.radians(140 - 90 / z)                   # roller seating angle
    disc = cq.Workplane("XY").circle(da / 2).extrude(bf)
    for k in range(z):
        ang = 2 * math.pi * k / z + math.pi / z
        cx, cy = dp / 2 * math.cos(ang), dp / 2 * math.sin(ang)
        seat = cq.Workplane("XY").center(cx, cy).circle(ri).extrude(bf + 2).translate((0, 0, -1))
        # straight flanks tangent to the seat circle, opening outwards by phi from the radial direction
        ux, uy = math.cos(ang), math.sin(ang)
        vx, vy = -uy, ux
        phi = (math.pi - alpha) / 2
        L = da
        poly = [(cx, cy)]
        for sgn in (-1, 1):
            nx, ny = -math.sin(phi) * ux + sgn * math.cos(phi) * vx, -math.sin(phi) * uy + sgn * math.cos(phi) * vy
            tx, ty = cx + ri * nx, cy + ri * ny
            dx, dy = math.cos(phi) * ux + sgn * math.sin(phi) * vx, math.cos(phi) * uy + sgn * math.sin(phi) * vy
            poly += [(tx, ty), (tx + L * dx, ty + L * dy)] if sgn < 0 else [(tx + L * dx, ty + L * dy), (tx, ty)]
        gap = cq.Workplane("XY").polyline(poly).close().extrude(bf + 2).translate((0, 0, -1))
        disc = disc.cut(seat).cut(gap)
    # tooth side chamfers (simplified): small 45 deg on both faces at the tip
    c = min(0.1 * p, 0.3 * bf)
    tipcut = F.revolve([(da / 2 - c * 1.6, -0.01), (da / 2 + 1, -0.01), (da / 2 + 1, c + 1)]).union(
        F.revolve([(da / 2 - c * 1.6, bf + 0.01), (da / 2 + 1, bf + 0.01), (da / 2 + 1, bf - c - 1)]))
    disc = disc.cut(tipcut)
    if d["bore"]:
        disc = disc.cut(F.ring(d["bore"] / 2, 0, bf + 2, -1))
    if d["strands"] > 1:
        pt = d.get("pt") or (1.13 * d["b1"] + 0.5 * d1)   # transverse pitch (approx.)
        one = disc
        for i in range(1, d["strands"]):
            disc = disc.union(one.translate((0, 0, i * pt)))
        core_r = d["df"] / 2 - 0.35 * p                     # hub joining the strands below the tooth gaps
        disc = disc.union(F.ring(core_r, d["bore"] / 2 if d["bore"] else 0, (d["strands"] - 1) * pt + bf))
    return F.body_color(disc, F.STEEL)


register(Family("SPROCKET", "Řetězové kolo", "Převody/Řetězová kola", words=["SPROCKET", "RETEZOVE KOLO", "RETEZKA"],
                regex=r"(?P<chain>\d{2,3}B?|\d{2,3})(?:\s*-\s*(?P<n>[123]))?\s*Z\s*(?P<z>\d+)(?:\s*D\s*(?P<bore>[\d.]+))?",
                parse=_spr_parse, build=_sprocket, rows=[[k, *v] for k, v in CHAIN.items()], columns=["chain", "pitch p", "roller d1", "inner width b1"],
                example="SPROCKET 08B-1 z17 d15", aliases="řetězové kolo řetězka sprocket chain ISO 606 ANSI",
                source="ISO 606 pitch diameter, seating radius and angle; flanks simplified", ptype="custom",
                anchors=lambda d: {"face_a": (0, 0, 0), "face_b": (0, 0, d["bf"]), "axis": "+Z"},
                note="Tooth width bf from Z=0. Seating circle ri = 0.505 d1 + 0.069 d1^(1/3), seating angle 140 - 90/z."))


# ---------------------------------------------------------------- helpers

def centre_distance(m, z1, z2, beta=0.0):
    mt = m / math.cos(math.radians(beta))
    return mt * (z1 + z2) / 2


def gear_pair(m, z1, z2, b, bore1=0.0, bore2=0.0, beta=0.0, at=(0, 0, 0)):
    """Two gears in mesh: gear 1 at `at`, gear 2 on +X at the centre distance, rotated so the teeth mesh.
    Returns {"gear1": wp, "gear2": wp, "a": centre distance, "codes": [...]}. Helical: gear 2 gets the opposite hand."""
    from .std import part
    a = centre_distance(m, z1, z2, beta)
    c1 = f"GEAR m{m:g} z{z1} b{b:g}" + (f" d{bore1:g}" if bore1 else "") + (f" beta{beta:g}" if beta else "")
    c2 = f"GEAR m{m:g} z{z2} b{b:g}" + (f" d{bore2:g}" if bore2 else "") + (f" beta{-beta:g}" if beta else "")
    g1 = part(c1).translate(at)
    # gear 1 has a tooth on +X; gear 2 must present a gap towards -X: half a pitch turn if z2 is even
    rot = 180.0 / z2 if z2 % 2 == 0 else 0.0
    rot += 180.0
    g2 = part(c2).rotate((0, 0, 0), (0, 0, 1), rot).translate((at[0] + a, at[1], at[2]))
    return {"gear1": g1, "gear2": g2, "a": round(a, 4), "codes": [c1, c2]}

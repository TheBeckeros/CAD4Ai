"""Bearings (Ložiska): ball - deep groove 60/62/63/618/619/6xx, angular contact 72/73 B, self-aligning 12/22,
thrust 511/512; roller - cylindrical NU/NJ/N 2/3/22, tapered 302/303/322, needle drawn cup HK.
Boundary dimensions ISO 15 / ISO 355 / ISO 104 typed from general knowledge (unverified); inside (rings, balls,
rollers, seals) is representative, not a maker's drawing. Face A at Z=0, width up to +Z, axis Z.
Suffix -2RS / -2RS1 / -RS: rubber seals (dark), -2Z / -ZZ / -Z: steel shields; none: open with rolling elements."""
import math
import re

from . import famreg as F
from .famreg import Family, register

SRC = "ISO 15 / 355 / 104 boundary dimensions, typed from general knowledge; internal geometry representative"

D60 = {10: (26, 8), 12: (28, 8), 15: (32, 9), 17: (35, 10), 20: (42, 12), 25: (47, 12), 30: (55, 13), 35: (62, 14), 40: (68, 15), 45: (75, 16),
       50: (80, 16), 55: (90, 18), 60: (95, 18), 65: (100, 18), 70: (110, 20), 75: (115, 20), 80: (125, 22), 85: (130, 22), 90: (140, 24),
       95: (145, 24), 100: (150, 24)}
D62 = {10: (30, 9), 12: (32, 10), 15: (35, 11), 17: (40, 12), 20: (47, 14), 25: (52, 15), 30: (62, 16), 35: (72, 17), 40: (80, 18), 45: (85, 19),
       50: (90, 20), 55: (100, 21), 60: (110, 22), 65: (120, 23), 70: (125, 24), 75: (130, 25), 80: (140, 26), 85: (150, 28), 90: (160, 30),
       95: (170, 32), 100: (180, 34)}
D63 = {10: (35, 11), 12: (37, 12), 15: (42, 13), 17: (47, 14), 20: (52, 15), 25: (62, 17), 30: (72, 19), 35: (80, 21), 40: (90, 23), 45: (100, 25),
       50: (110, 27), 55: (120, 29), 60: (130, 31), 65: (140, 33), 70: (150, 35), 75: (160, 37), 80: (170, 39), 85: (180, 41), 90: (190, 43),
       95: (200, 45), 100: (215, 47)}
D618 = {10: (19, 5), 12: (21, 5), 15: (24, 5), 17: (26, 5), 20: (32, 7), 25: (37, 7), 30: (42, 7), 35: (47, 7), 40: (52, 7), 45: (58, 7), 50: (65, 7)}
D619 = {10: (22, 6), 12: (24, 6), 15: (28, 7), 17: (30, 7), 20: (37, 9), 25: (42, 9), 30: (47, 9), 35: (55, 10), 40: (62, 12), 45: (68, 12), 50: (72, 12)}
B22 = {10: 14, 12: 14, 15: 14, 17: 16, 20: 18, 25: 18, 30: 20, 35: 23, 40: 23, 45: 23, 50: 23, 55: 25, 60: 28, 65: 31, 70: 31, 75: 31, 80: 33}
MINI = {"623": (3, 10, 4), "624": (4, 13, 5), "625": (5, 16, 5), "626": (6, 19, 6), "627": (7, 22, 7), "628": (8, 24, 8), "629": (9, 26, 8),
        "608": (8, 22, 7), "609": (9, 24, 7), "607": (7, 19, 6), "606": (6, 17, 6), "605": (5, 14, 5), "604": (4, 12, 4),
        "688": (8, 16, 5), "689": (9, 17, 5), "686": (6, 13, 5), "685": (5, 11, 5), "684": (4, 9, 4), "695": (5, 13, 4), "696": (6, 15, 5),
        "697": (7, 17, 5), "698": (8, 19, 6), "699": (9, 20, 6)}
T511 = {10: (24, 9), 12: (26, 9), 15: (28, 9), 17: (30, 9), 20: (35, 10), 25: (42, 11), 30: (47, 11), 35: (52, 12), 40: (60, 13), 45: (65, 14),
        50: (70, 14), 55: (78, 16), 60: (85, 17)}
T512 = {10: (26, 11), 12: (28, 11), 15: (32, 12), 17: (35, 12), 20: (40, 14), 25: (47, 15), 30: (52, 16), 35: (62, 18), 40: (68, 19), 45: (73, 20),
        50: (78, 22), 55: (90, 25), 60: (95, 26)}
# tapered: d -> D, T, B (cone), C (cup) for 302xx / 303xx / 322xx
TAP302 = {15: (42, 14.25, 13, 11), 17: (40, 13.25, 12, 11), 20: (47, 15.25, 14, 12), 25: (52, 16.25, 15, 13), 30: (62, 17.25, 16, 14),
          35: (72, 18.25, 17, 15), 40: (80, 19.75, 18, 16), 45: (85, 20.75, 19, 16), 50: (90, 21.75, 20, 17), 55: (100, 22.75, 21, 18),
          60: (110, 23.75, 22, 19)}
TAP303 = {15: (42, 14.25, 13, 11), 17: (47, 15.25, 14, 12), 20: (52, 16.25, 15, 13), 25: (62, 18.25, 17, 15), 30: (72, 20.75, 19, 16),
          35: (80, 22.75, 21, 18), 40: (90, 25.25, 23, 20), 45: (100, 27.25, 25, 22), 50: (110, 29.25, 27, 23)}
TAP322 = {20: (47, 19.25, 18, 15), 25: (52, 19.25, 18, 16), 30: (62, 21.25, 20, 17), 35: (72, 24.25, 23, 19), 40: (80, 24.75, 23, 19),
          45: (85, 24.75, 23, 19), 50: (90, 24.75, 23, 19)}
HK = {"HK0306": (3, 6.5, 6), "HK0408": (4, 8, 8), "HK0509": (5, 9, 9), "HK0608": (6, 10, 8), "HK0709": (7, 11, 9), "HK0808": (8, 12, 8),
      "HK0810": (8, 12, 10), "HK1010": (10, 14, 10), "HK1012": (10, 14, 12), "HK1212": (12, 18, 12), "HK1412": (14, 20, 12),
      "HK1512": (15, 21, 12), "HK1612": (16, 22, 12), "HK1812": (18, 24, 12), "HK2016": (20, 26, 16), "HK2520": (25, 32, 20),
      "HK3020": (30, 37, 20), "HK3520": (35, 42, 20), "HK4020": (40, 47, 20)}
SERIES = {"60": D60, "62": D62, "63": D63, "618": D618, "619": D619}
SEAL = re.compile(r"-?\s*(2RS1?|2RSR|2RSH|RS1?|2Z|ZZ|Z|2RZ|RZ|NR|N)?\s*(C3|C4|P5|P6)?\s*$", re.I)


def bore(code2):
    n = int(code2)
    return {0: 10, 1: 12, 2: 15, 3: 17}.get(n, 5 * n)


def _chamfer(D, d):
    t = (D - d) / 2
    return round(min(max(0.15, 0.06 * t), 2.0), 2)


def b_anchors(d):
    return {"face_a": (0, 0, 0), "face_b": (0, 0, d["B"]), "centre": (0, 0, d["B"] / 2), "axis": "+Z (bore d, outer D)"}


def _b_tools():
    return {"shaft_seat": lambda d: F.ring(d["d"] / 2 + 0.01, 0, d["B"] + 0.02, -0.01),
            "housing_seat": lambda d: F.ring(d["D"] / 2 + 0.01, 0, d["B"] + 0.02, -0.01)}


def _ringsec(r_in, r_out, z0, z1, c, groove=None):
    """Ring of revolution between radii, chamfered corners c; groove = (radius_centre_x, z, r) torus race to cut."""
    import cadquery as cq
    w = F.revolve([(r_in + c, z0), (r_out - c, z0), (r_out, z0 + c), (r_out, z1 - c), (r_out - c, z1), (r_in + c, z1), (r_in, z1 - c), (r_in, z0 + c)])
    if groove:
        x, z, r = groove
        w = w.cut(cq.Workplane("XY").add(cq.Solid.makeTorus(x, r, pnt=cq.Vector(0, 0, z))))
    return w


def _balls(dm, z, Dw, n):
    import cadquery as cq
    sol = [cq.Solid.makeSphere(Dw / 2, cq.Vector(dm / 2 * math.cos(2 * math.pi * i / n), dm / 2 * math.sin(2 * math.pi * i / n), z),
                               angleDegrees1=-90, angleDegrees2=90) for i in range(n)]
    return sol


def _cage(elements, bands):
    """Rolling elements fused with their cage into ONE solid (as in a real bearing, and so the viewer shows one
    part, not dozens). bands: [(r_mid, half_width, z0, h)] rings of revolution placed inside the elements."""
    import cadquery as cq
    w = None
    for r_mid, hw, z0, h in bands:
        b = F.ring(r_mid + hw, r_mid - hw, h, z0)
        w = b if w is None else w.union(b)
    for e in elements:
        w = w.union(cq.Workplane("XY").add(e))
    F.paint(w, F.DARK_STEEL)
    return w.val()


def ball_bearing(d, D, B, seal="", rows=1, angular=False, self_align=False):
    import cadquery as cq
    t = (D - d) / 2
    c = _chamfer(D, d)
    dm = (D + d) / 2
    Dw = 0.32 * t * (1.0 if rows == 1 else 0.85)
    gr = 0.52 * Dw
    zs = [B / 2] if rows == 1 else [B * 0.3, B * 0.7]
    r_or_in = dm / 2 + 0.28 * Dw + 0.0     # outer ring bore (land)
    r_ir_out = dm / 2 - 0.28 * Dw
    outer = _ringsec(r_or_in, D / 2, 0, B, c)
    inner = _ringsec(d / 2, r_ir_out, 0, B, c)
    for z in zs:
        if not self_align:
            outer = outer.cut(cq.Workplane("XY").add(cq.Solid.makeTorus(dm / 2, gr, pnt=cq.Vector(0, 0, z))))
        inner = inner.cut(cq.Workplane("XY").add(cq.Solid.makeTorus(dm / 2, gr, pnt=cq.Vector(0, 0, z))))
    if self_align:  # spherical outer raceway
        R = (math.hypot(dm / 2 + Dw / 2, (zs[-1] - zs[0]) / 2) if rows == 2 else dm / 2 + Dw / 2) + 0.04 * Dw
        outer = outer.cut(cq.Workplane("XY").add(cq.Solid.makeSphere(R, cq.Vector(0, 0, B / 2), angleDegrees1=-90, angleDegrees2=90)))
    if angular:  # lowered outer shoulder on face B side
        outer = outer.cut(F.ring(dm / 2 + 0.5 * Dw, 0, B / 2, B / 2 + 0.01))
    parts = [outer.val(), inner.val()]
    s = (seal or "").upper()
    if s:
        rubber = "RS" in s
        th = min(0.8, 0.12 * B)
        for zf in (0.25 * c, B - 0.25 * c - th) if s.startswith("2") or s in ("ZZ",) else (B - 0.25 * c - th,):
            disc = F.ring(r_or_in, r_ir_out + 0.2, th, zf)   # sits in the outer ring bore (touching), clear of the inner ring
            F.paint(disc, F.RUBBER if rubber else F.DARK_STEEL)
            parts.append(disc.val())
    else:
        n = max(6, int(math.pi * dm / (Dw * 1.45)))
        balls = [b_ for z in zs for b_ in _balls(dm, z, Dw, n)]
        parts.append(_cage(balls, [(dm / 2, 0.17 * Dw, zs[0] - 0.19 * Dw, zs[-1] - zs[0] + 0.38 * Dw)]))
    return cq.Workplane("XY").add(cq.Compound.makeCompound(parts))


def thrust_bearing(d, D, H):
    import cadquery as cq
    hw = 0.28 * H
    Dw = H - 2 * hw + 0.6 * hw
    dm = (D + d) / 2
    shaft_w = F.ring(D / 2 - 0.02 * D, d / 2, hw, H - hw)
    house_w = F.ring(D / 2, d / 2 + 0.03 * D + 0.2, hw, 0)
    tor_lo = cq.Workplane("XY").add(cq.Solid.makeTorus(dm / 2, 0.52 * Dw, pnt=cq.Vector(0, 0, H / 2)))
    shaft_w, house_w = shaft_w.cut(tor_lo), house_w.cut(tor_lo)
    n = max(6, int(math.pi * dm / (Dw * 1.5)))
    parts = [house_w.val(), shaft_w.val(), _cage(_balls(dm, H / 2, Dw, n), [(dm / 2, 0.17 * Dw, H / 2 - 0.19 * Dw, 0.38 * Dw)])]
    return cq.Workplane("XY").add(cq.Compound.makeCompound(parts))


def roller_bearing(d, D, B, kind="NU"):
    import cadquery as cq
    t = (D - d) / 2
    c = _chamfer(D, d)
    Dw = 0.36 * t
    dm = (D + d) / 2
    Lw = 0.62 * B
    r_or = dm / 2 + Dw / 2
    r_ir = dm / 2 - Dw / 2
    rib = 0.25 * Dw
    outer = _ringsec(r_or if kind == "N" else r_or - rib, D / 2, 0, B, c)
    if kind != "N":  # NU / NJ: ribs on the outer ring, raceway between
        outer = outer.cut(F.ring(r_or + 0.01, 0, Lw + 0.2, (B - Lw) / 2 - 0.1))
    inner = _ringsec(d / 2, r_ir if kind != "N" else r_ir + rib, 0, B, c)
    if kind == "N":
        inner = inner.cut(F.ring(r_ir + rib + 1, r_ir - 0.01, Lw + 0.2, (B - Lw) / 2 - 0.1).cut(F.ring(r_ir - 0.01, 0, B, 0)))
    if kind == "NJ":
        inner = inner.union(F.ring(r_ir + rib, r_ir - 0.01, (B - Lw) / 2 - 0.1, 0))
    n = max(8, int(math.pi * dm / (Dw * 1.3)))
    rollers = [cq.Solid.makeCylinder(Dw / 2, Lw, cq.Vector(dm / 2 * math.cos(2 * math.pi * i / n), dm / 2 * math.sin(2 * math.pi * i / n), (B - Lw) / 2))
               for i in range(n)]
    z0 = (B - Lw) / 2
    cage = _cage(rollers, [(dm / 2, 0.22 * Dw, z0, 0.12 * Lw), (dm / 2, 0.22 * Dw, z0 + 0.88 * Lw, 0.12 * Lw)])
    return cq.Workplane("XY").add(cq.Compound.makeCompound([outer.val(), inner.val(), cage]))


def tapered_bearing(d, D, T, Bc, Cc):
    """Tapered roller bearing: cone (inner ring, large end + back rib at Z=0, width B), cup (outer ring, width C at
    the Z=T end), rollers inclined by 12 deg in a cage. Both raceways are offset from the roller axes by the roller
    radius, so nothing overlaps (simplified: cylindrical rollers between parallel cones)."""
    import cadquery as cq
    a = math.radians(12)
    ta, ca = math.tan(a), math.cos(a)
    t = (D - d) / 2
    rm, zc = (D + d) / 4, T / 2
    rho = 0.18 * t
    cl = 0.03 * rho
    Lw = 0.7 * Cc

    def r_ax(z):                       # roller axis radius at height z (narrows towards +Z)
        return rm - (z - zc) * ta
    def r_cup(z):
        return r_ax(z) + rho / ca + cl
    def r_cone(z):
        return r_ax(z) - rho / ca - cl
    z0c = T - Cc
    cup = F.revolve([(D / 2, z0c), (D / 2, T), (r_cup(T), T), (r_cup(z0c), z0c)])
    sz = zc - Lw / 2 * ca                                     # lower end centre height of a roller
    z_rib = max(0.1 * Bc, sz - rho * math.sin(a) - 0.2)
    rib_r = r_cone(0) + 0.6 * rho
    cone = F.revolve([(d / 2, 0), (rib_r, 0), (rib_r, z_rib), (r_cone(z_rib), z_rib), (r_cone(Bc), Bc), (d / 2, Bc)])
    n = max(8, int(2 * math.pi * rm / (2 * rho * 1.25)))
    rollers = []
    for i in range(n):
        cyl = cq.Solid.makeCylinder(rho, Lw, cq.Vector(0, 0, -Lw / 2), cq.Vector(0, 0, 1))
        cyl = cyl.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 1, 0), -math.degrees(a)).translate(cq.Vector(rm, 0, zc))
        rollers.append(cyl.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), 360.0 * i / n))
    h = 0.1 * Lw
    z_lo, z_hi = zc - 0.38 * Lw * ca, zc + 0.38 * Lw * ca     # cage rings near the roller ends, inside the rollers
    bands = [(r_ax(z_lo), 0.35 * rho, z_lo - h / 2, h), (r_ax(z_hi), 0.35 * rho, z_hi - h / 2, h)]
    return cq.Workplane("XY").add(cq.Compound.makeCompound([cup.val(), cone.val(), _cage(rollers, bands)]))


def needle_cup(d, D, C):
    import cadquery as cq
    tc = max(0.3, 0.1 * (D - d))
    Dw = (D - d) / 2 - tc
    Lw = C - 2 * tc - 0.4
    cup = F.revolve([(D / 2 - tc, 0), (D / 2, 0), (D / 2, C), (d / 2 + Dw * 0.5, C), (d / 2 + Dw * 0.5, C - tc), (D / 2 - tc, C - tc)])
    cup = cup.union(F.ring(D / 2, d / 2 + Dw * 0.5, tc, 0))
    dm = d + Dw
    n = max(8, int(math.pi * dm / (Dw * 1.12)))
    needles = [cq.Solid.makeCylinder(Dw / 2 * 0.98, Lw, cq.Vector(dm / 2 * math.cos(2 * math.pi * i / n), dm / 2 * math.sin(2 * math.pi * i / n), tc + 0.2))
               for i in range(n)]
    z0 = tc + 0.2
    cage = _cage(needles, [(dm / 2, 0.2 * Dw, z0, 0.12 * Lw), (dm / 2, 0.2 * Dw, z0 + 0.88 * Lw, 0.12 * Lw)])
    return cq.Workplane("XY").add(cq.Compound.makeCompound([cup.val(), cage]))


# ---------------------------------------------------------------- families

def _seal_of(rest):
    m = SEAL.match(rest or "")
    return (m.group(1) or "").upper() if m else ""


def _deep_parse(g, token, kw):
    code = g["code"]
    seal = _seal_of(g.get("rest"))
    if code in MINI:
        d, D, B = MINI[code]
    else:
        for pre in ("618", "619", "60", "62", "63"):
            if code.startswith(pre) and len(code) == len(pre) + 2:
                dd = bore(code[len(pre):])
                D, B = F.table(SERIES[pre], dd, pre + "xx")
                d = dd
                break
        else:
            return None
    return {"bearing": code, "d": d, "D": D, "B": B, "seal": seal, "size": code + (f"-{seal}" if seal else ""), "type": "bearing",
            "shaft_fit": "k5/j6", "housing_fit": "H7/J7", "shoulder_shaft_min": round(d + (D - d) * 0.25, 1),
            "shoulder_housing_max": round(D - (D - d) * 0.25, 1)}


BALLT = "Ložiska/Kuličková ložiska"
_ROWS = [[f"{p}{c:02d}" if c > 3 else f"{p}{c:02d}", bore(f"{c:02d}"), *SERIES[p][bore(f'{c:02d}')]]
         for p in ("60", "62", "63") for c in range(0, 21) if bore(f"{c:02d}") in SERIES[p]]
class _BearingFamily(Family):
    """Bearing codes have no standard prefix: match the whole code against a pattern."""

    def __init__(self, fid, pattern, **kw):
        super().__init__(fid, **kw)
        self.pat = re.compile(pattern, re.I)
        self.head = None

    def match(self, code, kw):
        m = self.pat.search(code)
        if not m:
            return None
        d = self.parse(m.groupdict(), m.group(0), kw)
        if d is None:
            return None
        d.setdefault("std", self.id)
        d.setdefault("type", self.ptype)
        d["family"] = self.id
        d.setdefault("std_code", d.get("size"))
        return d


def _deep(d):
    return F.body_color(ball_bearing(d["d"], d["D"], d["B"], d["seal"]), F.STEEL)


register(_BearingFamily("ISO 15 deep groove", r"(?<![A-Z0-9.])(?P<code>6[0-3]\d{2}|618\d{2}|619\d{2}|6[0-9]{2})(?![0-9])(?P<rest>[\s\-A-Z0-9]*)$",
                        title="Kuličkové ložisko jednořadé", path=BALLT, parse=_deep_parse, build=_deep,
                        rows=_ROWS + [[k, *v] for k, v in MINI.items()], columns=["code", "d", "D", "B"], example="6204-2RS",
                        aliases="ložisko lozisko kuličkové jednořadé deep groove ball bearing 608 6204 2RS ZZ", source=SRC, ptype="bearing",
                        anchors=b_anchors, tools=_b_tools(),
                        note="Suffix -2RS rubber seals, -2Z / ZZ shields, none = open (balls visible). Shaft k5/j6, housing H7/J7."))


def _series_parse(series_tab, B_override=None, kind="ac"):
    def p(g, token, kw):
        code = g["code"]
        dd = bore(code[-2:])
        D, B = F.table(series_tab, dd, code[:-2] + "xx")
        if B_override:
            B = F.table(B_override, dd, code[:-2] + "xx")
        return {"bearing": code + (g.get("suffix") or ""), "d": dd, "D": D, "B": B, "seal": _seal_of(g.get("rest")), "size": code, "type": "bearing"}
    return p


register(_BearingFamily("ISO 15 angular contact", r"(?<![A-Z0-9.])(?P<code>7[23]\d{2})(?P<suffix>\s*-?\s*B[A-Z]*)?(?![0-9])(?P<rest>[\s\-A-Z0-9]*)$",
                        title="Kuličkové ložisko s kosoúhlým stykem", path=BALLT, parse=_series_parse(D62),
                        build=lambda d: F.body_color(ball_bearing(d["d"], d["D"], d["B"], "", angular=True), F.STEEL),
                        rows=[[f"72{c:02d} B", *D62[bore(f'{c:02d}')]] for c in range(0, 13)], columns=["code", "D", "B"], example="7205 B",
                        aliases="kosoúhlé ložisko angular contact ball bearing 40°", source=SRC, ptype="bearing", anchors=b_anchors, tools=_b_tools(),
                        note="72xx: dimensions as 62xx, 73xx as 63xx (73xx uses the 62 table here - check). Lowered outer shoulder on face B."))
register(_BearingFamily("ISO 15 self-aligning", r"(?<![A-Z0-9.])(?<!N\s)(?<!U\s)(?<!J\s)(?<!P\s)(?P<code>1[23]\d{2}|2[23]\d{2})(?![0-9])(?P<rest>[\s\-A-Z0-9]*)$",
                        title="Kuličkové ložisko naklápěcí (dvouřadé)", path=BALLT,
                        parse=lambda g, t, kw: (_series_parse(D62, B22 if g["code"].startswith("22") else None)(g, t, kw)
                                                if g["code"][:2] in ("12", "22") else _series_parse(D63)(g, t, kw)),
                        build=lambda d: F.body_color(ball_bearing(d["d"], d["D"], d["B"], d["seal"], rows=2, self_align=True), F.STEEL),
                        rows=[[f"12{c:02d}", *D62[bore(f'{c:02d}')]] for c in range(0, 13)] + [[f"22{c:02d}", D62[bore(f'{c:02d}')][0], B22[bore(f'{c:02d}')]]
                                                                                          for c in range(0, 13) if bore(f"{c:02d}") in B22],
                        columns=["code", "D", "B"], example="1205", aliases="naklápěcí dvouřadé ložisko self-aligning ball bearing", source=SRC,
                        ptype="bearing", anchors=b_anchors, tools=_b_tools()))


def _thrust_parse(g, token, kw):
    code = g["code"]
    dd = bore(code[-2:])
    D, H = F.table(T511 if code.startswith("511") else T512, dd, code[:3] + "xx")
    return {"bearing": code, "d": dd, "D": D, "B": H, "H": H, "size": code, "type": "bearing"}


register(_BearingFamily("ISO 104 thrust ball", r"(?<![A-Z0-9.])(?P<code>51[12]\d{2})(?![0-9])", title="Axiální kuličkové ložisko", path=BALLT,
                        parse=_thrust_parse, build=lambda d: F.body_color(thrust_bearing(d["d"], d["D"], d["H"]), F.STEEL),
                        rows=[[f"511{c:02d}", bore(f'{c:02d}'), *T511[bore(f'{c:02d}')]] for c in range(0, 13)]
                        + [[f"512{c:02d}", bore(f'{c:02d}'), *T512[bore(f'{c:02d}')]] for c in range(0, 13)],
                        columns=["code", "d", "D", "H"], example="51105", aliases="axiální ložisko thrust ball bearing", source=SRC,
                        ptype="bearing", anchors=lambda d: {"bottom": (0, 0, 0), "top": (0, 0, d["H"]), "axis": "+Z"}, tools=_b_tools(),
                        note="Housing washer at Z=0 (bore d+), shaft washer on top (bore d)."))

ROLLT = "Ložiska/Válečková ložiska"


def _cyl_parse(g, token, kw):
    kind, ser, c2 = g["kind"].upper(), g["ser"], g["c2"]
    dd = bore(c2)
    if ser == "2":
        D, B = F.table(D62, dd, "NU2xx")
    elif ser == "3":
        D, B = F.table(D63, dd, "NU3xx")
    else:
        D = F.table(D62, dd, "NU22xx")[0]
        B = F.table(B22, dd, "NU22xx")
    return {"bearing": f"{kind}{ser}{c2}", "kind": kind, "d": dd, "D": D, "B": B, "size": f"{kind}{ser}{c2}", "type": "bearing"}


register(_BearingFamily("ISO 15 cylindrical roller", r"(?<![A-Z0-9.])(?P<kind>NUP|NU|NJ|N)\s*(?P<ser>22|2|3)(?P<c2>\d{2})(?![0-9])",
                        title="Válečkové ložisko NU / NJ / N", path=ROLLT, parse=_cyl_parse,
                        build=lambda d: F.body_color(roller_bearing(d["d"], d["D"], d["B"], "NJ" if d["kind"] in ("NJ", "NUP") else d["kind"]), F.STEEL),
                        rows=[[f"NU2{c:02d}", bore(f'{c:02d}'), *D62[bore(f'{c:02d}')]] for c in range(4, 21)]
                        + [[f"NU3{c:02d}", bore(f'{c:02d}'), *D63[bore(f'{c:02d}')]] for c in range(4, 21)],
                        columns=["code", "d", "D", "B"], example="NU 206", aliases="válečkové ložisko cylindrical roller bearing NU NJ N",
                        source=SRC, ptype="bearing", anchors=b_anchors, tools=_b_tools()))


def _tap_parse(g, token, kw):
    code = g["code"]
    tab = {"302": TAP302, "303": TAP303, "322": TAP322}[code[:3]]
    dd = bore(code[3:])
    D, T, Bc, Cc = F.table(tab, dd, code[:3] + "xx")
    return {"bearing": code, "d": dd, "D": D, "B": T, "T": T, "Bc": Bc, "Cc": Cc, "size": code, "type": "bearing"}


register(_BearingFamily("ISO 355 tapered roller", r"(?<![A-Z0-9.])(?P<code>30[23]\d{2}|322\d{2})(?![0-9])", title="Kuželíkové ložisko", path=ROLLT,
                        parse=_tap_parse, build=lambda d: F.body_color(tapered_bearing(d["d"], d["D"], d["T"], d["Bc"], d["Cc"]), F.STEEL),
                        rows=[[f"302{c:02d}", bore(f'{c:02d}'), *TAP302[bore(f'{c:02d}')]] for c in range(3, 13) if bore(f'{c:02d}') in TAP302]
                        + [[f"303{c:02d}", bore(f'{c:02d}'), *TAP303[bore(f'{c:02d}')]] for c in range(3, 11) if bore(f'{c:02d}') in TAP303]
                        + [[f"322{c:02d}", bore(f'{c:02d}'), *TAP322[bore(f'{c:02d}')]] for c in range(4, 11) if bore(f'{c:02d}') in TAP322],
                        columns=["code", "d", "D", "T", "B", "C"], example="30205",
                        aliases="kuželíkové ložisko tapered roller bearing cone cup", source=SRC, ptype="bearing",
                        anchors=lambda d: {"face_a": (0, 0, 0), "back": (0, 0, d["T"]), "axis": "+Z"}, tools=_b_tools(),
                        note="Cone (inner ring) back face at Z=0, cup at the Z=T end."))
register(_BearingFamily("HK needle", r"(?<![A-Z0-9.])(?P<code>HK\s*\d{4})(?![0-9])", title="Jehlové pouzdro HK", path=ROLLT,
                        parse=lambda g, t, kw: {"bearing": g["code"].replace(" ", ""), "d": F.table(HK, g["code"].replace(" ", "").upper(), "HK")[0],
                                                "D": HK[g["code"].replace(" ", "").upper()][1], "B": HK[g["code"].replace(" ", "").upper()][2],
                                                "size": g["code"].replace(" ", "").upper(), "type": "bearing"},
                        build=lambda d: F.body_color(needle_cup(d["d"], d["D"], d["B"]), F.STEEL),
                        rows=[[k, *v] for k, v in HK.items()], columns=["code", "Fw", "D", "C"], example="HK2016",
                        aliases="jehlové pouzdro jehličkové ložisko needle drawn cup HK", source=SRC, ptype="bearing", anchors=b_anchors,
                        tools={"housing_seat": lambda d: F.ring(d["D"] / 2, 0, d["B"] + 0.02, -0.01)},
                        note="d = shaft (inscribed) diameter Fw. Closed end at Z=0."))

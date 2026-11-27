"""Pins (Čepy): cylindrical, hardened, internal thread, taper, spring (slotted), grooved, rivets (solid, blind),
clevis pins, split pins, clevis forks. Axis +Z, bottom end at Z=0 unless noted. Values typed from general
knowledge (unverified)."""
import math

from . import famreg as F
from .famreg import Family, register

SRC = "ISO / DIN pin dimensions, typed from general knowledge"
DX = r"(?:[A-Z]\s+)?(?P<d>\d+(?:\.\d+)?)\s*(?:[a-z]\d+)?\s*x\s*(?P<L>\d+(?:\.\d+)?)"   # '6m6x20', 'B 8x30'

# spring pins: wall s heavy (ISO 8752) / light (ISO 13337)
SPRING_S = {1: (0.2, 0.2), 1.5: (0.3, 0.3), 2: (0.4, 0.2), 2.5: (0.5, 0.25), 3: (0.6, 0.3), 4: (0.8, 0.5), 5: (1.0, 0.5), 6: (1.2, 0.75),
            8: (1.6, 0.75), 10: (2.0, 1.0), 12: (2.5, 1.0), 13: (2.5, 1.25), 16: (3.0, 1.5), 20: (4.0, 2.0)}
# internal thread of ISO 8735 by d: thread, depth
PIN_THREAD = {6: ("M4", 6), 8: ("M5", 8), 10: ("M6", 10), 12: ("M6", 12), 16: ("M8", 16), 20: ("M10", 18), 25: ("M16", 24)}
# rivets: ISO 1051 / DIN 660 round head dk, k ; DIN 661 countersunk dk
RIVET = {2: (3.5, 1.2), 2.5: (4.4, 1.5), 3: (5.3, 1.8), 4: (7, 2.4), 5: (8.8, 3), 6: (10.5, 3.6), 8: (14, 4.8), 10: (17.5, 6)}
RIVET_CSK = {2: 3.5, 2.5: 4.4, 3: 5.3, 4: 7, 5: 8.8, 6: 10.5, 8: 14, 10: 17.5}
BLIND = {2.4: (5, 0.8, 1.45), 3.2: (6.5, 1.1, 1.9), 4: (8, 1.3, 2.4), 4.8: (9.5, 1.5, 2.9), 5: (10, 1.6, 3.1), 6.4: (13, 2, 3.7)}
# clevis pin ISO 2341: head dk, k, split pin hole d_sp
CLEVIS = {3: (5, 1, 0.8), 4: (6, 1, 1), 5: (8, 1.6, 1.2), 6: (10, 2, 1.6), 8: (14, 3, 2), 10: (18, 4, 3.2), 12: (20, 4, 3.2),
          14: (22, 4, 4), 16: (25, 4.5, 4), 20: (30, 5, 5), 24: (36, 6, 6.3)}
# clevis fork DIN 71752 by thread: slot b, pin d, total l1, body w, fork length g
FORK = {"M4": (4, 4, 21, 8, 8), "M5": (5, 5, 26, 10, 10), "M6": (6, 6, 31, 12, 12), "M8": (8, 8, 42, 16, 16),
        "M10": (10, 10, 52, 20, 20), "M12": (12, 12, 62, 24, 24), "M14": (14, 14, 72, 27, 28), "M16": (16, 16, 83, 32, 32)}


def _dl(g, kw, fid, example):
    d = float(g["d"])
    L = F.num(g.get("L")) or kw.get("L")
    if not L:
        raise ValueError(f"length missing: write e.g. {example}")
    return d, L


def pin_family(fid, title, sub, nums, build, example, aliases, extra=None, rows=None, columns=None, note="", color=F.STEEL,
               anchors=None, tools=None):
    def parse(g, token, kw):
        d, L = _dl(g, kw, fid, example)
        out = {"d": d, "L": L, "size": f"{d:g}x{L:g}"}
        if extra:
            out.update(extra(d, L))
        return out

    def a(d):
        return {"bottom": (0, 0, 0), "top": (0, 0, d["L"]), "centre": (0, 0, d["L"] / 2), "axis": "+Z"}

    def hole(d):
        return F.ring(d["d"] / 2, 0, d["L"] + 2, -1)

    return register(Family(fid, title, "Čepy/" + sub, nums=nums, regex=DX, parse=parse,
                           build=lambda d: F.body_color(build(d), color), rows=rows or [], columns=columns or [], example=example,
                           aliases=aliases, ptype="fastener", source=SRC, anchors=anchors or a, note=note,
                           tools=tools or {"hole": hole}))


def _cyl(end_a="chamfer", end_b="chamfer"):
    def b(d):
        r, L = d["d"] / 2, d["L"]
        c = min(0.15 * d["d"], 0.8)
        segs = [(0, 0)]
        if end_a == "round":
            R = d["d"]
            h = R - math.sqrt(R * R - r * r)
            segs += [("arc", (r * 0.6, h - (R - math.sqrt(R * R - (r * 0.6) ** 2))), (r, h))]
        else:
            segs += [(r - c, 0), (r, c)]
        segs += [(r, L - c), (r - c, L), (0, L)]
        return F.revolve(segs)
    return b


CYL = "Válcové"
pin_family("ISO 2338", "Válcový kolík", CYL, ["ISO 2338", "DIN 7", "CSN 022150"], _cyl(), "ISO 2338 6m6x20",
           "kolík válcový dowel pin cylindrical")
pin_family("ISO 8734", "Válcový kolík kalený", CYL, ["ISO 8734", "DIN 6325"], _cyl("round"), "ISO 8734 6x20",
           "kolík kalený dowel pin hardened m6", note="Rounded end at Z=0, chamfered end at Z=L.")


def _cyl_thread(d):
    import cadquery as cq
    from . import screws as S
    from .std import THREAD
    body = _cyl()(d)
    th, depth = PIN_THREAD.get(int(d["d"]), (None, 0))
    if not th:
        return body
    P, tp = THREAD[th][:2]
    tool = S._revolve(cq, [(0, d["L"] + 1), (tp / 2 + 0.4, d["L"] + 1), (tp / 2, d["L"] - 0.2)]
                      + S._bands(tp / 2, d["L"] - 0.2, d["L"] - depth, P / 2) + [(0, d["L"] - depth - tp / 2 * 0.6)])
    return body.cut(tool, clean=False)


pin_family("ISO 8735", "Válcový kolík kalený s vnitřním závitem", CYL, ["ISO 8735", "DIN 7979"], _cyl_thread, "ISO 8735 10x40",
           "kolík s vnitřním závitem vytahovací internal thread dowel", rows=[[k, *v] for k, v in PIN_THREAD.items()],
           columns=["d", "thread", "depth"], note="Thread at the Z=L end.")


def _taper(d):
    r, L = d["d"] / 2, d["L"]
    R = r + L / 50 / 2
    c = min(0.1 * d["d"], 0.6)
    return F.revolve([(0, 0), (r - c, 0), (r, c), (R, L - c), (R - c, L), (0, L)])


pin_family("ISO 2339", "Kuželový kolík 1:50", "Kuželové", ["ISO 2339", "DIN 1"], _taper, "ISO 2339 6x40",
           "kolík kuželový taper pin 1:50", note="d = small end at Z=0.")


def _spring(light=False):
    def b(d):
        import cadquery as cq
        dd, L = d["d"], d["L"]
        s = SPRING_S.get(dd, (0.2 * dd, 0.1 * dd))[1 if light else 0]
        c = min(0.15 * dd, 1.0, 0.8 * s)
        tube =F.revolve([(dd / 2 - s, 0), (dd / 2 - c, 0), (dd / 2, c), (dd / 2, L - c), (dd / 2 - c, L), (dd / 2 - s, L)])
        gap = 0.2 * dd
        return tube.cut(cq.Workplane("XY").center(dd / 2, 0).rect(dd, gap).extrude(L + 2).translate((0, 0, -1)))
    return b


SPR = "Pružný"
pin_family("ISO 8752", "Pružný kolík (těžký)", SPR, ["ISO 8752", "DIN 1481"], _spring(), "ISO 8752 6x30",
           "pružný kolík trubkový spring pin slotted roll pin heavy", rows=[[k, v[0]] for k, v in SPRING_S.items()], columns=["d", "s"])
pin_family("ISO 13337", "Pružný kolík (lehký)", SPR, ["ISO 13337", "DIN 7346"], _spring(True), "ISO 13337 6x30",
           "pružný kolík lehký spring pin light", rows=[[k, v[1]] for k, v in SPRING_S.items()], columns=["d", "s"])


def _grooved(d):
    import cadquery as cq
    dd, L = d["d"], d["L"]
    body = _cyl()(d)
    w, dep = 0.22 * dd, 0.06 * dd + 0.05
    for i in range(3):
        g = cq.Workplane("XY").center(dd / 2, 0).rect(2 * dep, w).extrude(L - 0.6 * dd).translate((0, 0, 0.3 * dd))
        body = body.cut(g.rotate((0, 0, 0), (0, 0, 1), 120 * i))
    return body


pin_family("ISO 8740", "Rýhovaný kolík", "Rýhované", ["ISO 8740", "DIN 1473"], _grooved, "ISO 8740 6x30",
           "rýhovaný kolík grooved pin", note="Three grooves along the full length (simplified).")


def _rivet(csk=False):
    def b(d):
        dd, L = d["d"], d["L"]
        r = dd / 2
        if csk:
            dk = RIVET_CSK.get(dd, 1.75 * dd)
            k = (dk - dd) / 2 / math.tan(math.radians(45))
            return F.revolve([(0, -L), (r - 0.1 * dd, -L), (r, -L + 0.1 * dd), (r, -k), (dk / 2, 0), (0, 0)])
        dk, k = RIVET.get(dd, (1.75 * dd, 0.6 * dd))
        R = (dk * dk / 4 + k * k) / (2 * k)
        zc = k - R
        am = math.atan2(-zc, dk / 2) / 2 + math.pi / 4
        return F.revolve([(0, -L), (r - 0.1 * dd, -L), (r, -L + 0.1 * dd), (r, 0), (dk / 2, 0),
                          ("arc", (R * math.cos(am), zc + R * math.sin(am)), (0, k))])
    return b


def _rivet_anchor(d):
    return {"seat": (0, 0, 0), "tip": (0, 0, -d["L"]), "axis": "+Z = head"}


RIV = "Nýty"
pin_family("ISO 1051", "Nýt s půlkulovou hlavou", RIV, ["ISO 1051", "DIN 660", "DIN 124"], _rivet(), "DIN 660 5x20",
           "nýt plný půlkulatá hlava solid rivet round head", rows=[[k, *v] for k, v in RIVET.items()], columns=["d", "dk", "k"],
           anchors=_rivet_anchor, note="Head seat at Z=0, shank to -Z (L = shank under the head).")
pin_family("DIN 661", "Nýt se zápustnou hlavou", RIV, ["DIN 661", "DIN 302"], _rivet(True), "DIN 661 4x16",
           "nýt zápustný countersunk solid rivet", anchors=lambda d: {"head_top": (0, 0, 0), "tip": (0, 0, -d["L"]), "axis": "+Z"},
           note="Head top at Z=0, L includes the head.")


def _blind(d):
    import cadquery as cq
    dd, L = d["d"], d["L"]
    dk, k, dm = BLIND.get(dd, (2 * dd, 0.32 * dd, 0.6 * dd))
    body = F.revolve([(dm / 2, -L), (dd / 2, -L), (dd / 2, 0), (dk / 2, 0), (dk / 2 - 0.3 * k, k), (dm / 2, k)])
    mandrel = F.revolve([(0, -L - 0.8), (dm / 2 * 1.35, -L - 0.8), (dm / 2 * 1.35, -L - 0.2), (dm / 2, -L), (dm / 2, k + 25),
                         (dm / 2 - 0.3, k + 25.3), (0, k + 25.3)])
    F.paint(mandrel, F.DARK_STEEL)
    return cq.Workplane("XY").add(cq.Compound.makeCompound([body.val(), mandrel.val()]))


pin_family("ISO 15977", "Trhací nýt (s trnem)", RIV, ["ISO 15977", "DIN 7337"], _blind, "ISO 15977 4x10",
           "trhací nýt pop blind rivet", rows=[[k, *v] for k, v in BLIND.items()], columns=["d", "dk", "k", "mandrel d"],
           color=F.ALU, anchors=_rivet_anchor, note="Aluminium body + steel mandrel (before setting). Flange seat at Z=0.")


def _clevis(with_hole=True):
    def b(d):
        import cadquery as cq
        dd, L = d["d"], d["L"]
        dk, k, dsp = CLEVIS.get(dd, (1.6 * dd, 0.3 * dd, 0.2 * dd))
        c = min(0.15 * dd, 1)
        body = F.revolve([(0, -L), (dd / 2 - c, -L), (dd / 2, -L + c), (dd / 2, 0), (dk / 2, 0), (dk / 2, k - 0.3 * k), (dk / 2 - 0.3 * k, k), (0, k)])
        if with_hole:
            le = 1.6 * dsp + 0.5
            body = body.cut(cq.Workplane("YZ").workplane(offset=-dd).center(0, -L + le).circle(dsp / 2).extrude(2 * dd))
        return body
    return b


VID = "Vidlice"
pin_family("ISO 2341 B", "Čep s hlavou a otvorem pro závlačku", VID, ["ISO 2341 B", "DIN 1444 B"], _clevis(True), "ISO 2341 B 8x30",
           "čep s hlavou závlačka clevis pin split pin hole", rows=[[k, *v] for k, v in CLEVIS.items()], columns=["d", "dk", "k", "split pin d"],
           anchors=lambda d: {"seat": (0, 0, 0), "tip": (0, 0, -d["L"]), "axis": "+Z = head"}, note="Head seat at Z=0, shank to -Z.")
pin_family("ISO 2341 A", "Čep s hlavou bez otvoru", VID, ["ISO 2341 A", "DIN 1444 A"], _clevis(False), "ISO 2341 A 8x30",
           "čep s hlavou clevis pin", anchors=lambda d: {"seat": (0, 0, 0), "tip": (0, 0, -d["L"]), "axis": "+Z = head"})


def _split_pin(d):
    """ISO 1234 split pin: two half-round legs (one longer) and an eye, in the XZ plane, legs to -Z."""
    import cadquery as cq
    dd, L = d["d"], d["L"]
    w = 0.9 * dd           # wire: half-round of width w each leg -> total ~ 2 x w/2
    rleg = w / 2
    legs = None
    for side, extra in ((-1, 0.0), (1, 0.15 * L)):
        semi = cq.Workplane("XY").center(side * 0.02, 0).moveTo(0, -rleg).threePointArc((side * rleg, 0), (0, rleg)).close()
        leg = semi.extrude(-(L + extra))
        legs = leg if legs is None else legs.union(leg)
    re_ = 0.9 * dd + rleg
    eye = cq.Workplane("XY").add(cq.Solid.makeTorus(re_ - rleg, rleg, pnt=cq.Vector(0, 0, re_ - rleg * 0.2), dir=cq.Vector(0, 1, 0)))
    return legs.union(eye)


pin_family("ISO 1234", "Závlačka", VID, ["ISO 1234", "DIN 94"], _split_pin, "ISO 1234 2x16", "závlačka split pin cotter pin",
           anchors=lambda d: {"eye": (0, 0, 0), "tip": (0, 0, -d["L"]), "axis": "+Z = eye"}, note="d = nominal (hole) size; eye at Z=0, legs to -Z.")


def _fork_parse(g, token, kw):
    size = f"M{float(g['d']):g}"
    b, dp, l1, w, gl = F.table(FORK, size, "DIN 71752")
    from .std import THREAD
    return {"size": size, "d": float(size[1:]), "P": THREAD[size][0], "tap": THREAD[size][1], "b": b, "pin_d": dp, "l1": l1, "w": w, "g": gl,
            "L": l1}


def _fork(d):
    import cadquery as cq
    from . import screws as S
    b, dp, l1, w, gl = d["b"], d["pin_d"], d["l1"], d["w"], d["g"]
    body = cq.Workplane("XY").rect(w, w).extrude(l1).edges("|Z").fillet(0.15 * w)
    body = body.union(cq.Workplane("XZ").center(0, l1).circle(w / 2).extrude(w / 2, both=True)).intersect(
        cq.Workplane("XY").rect(w, w).extrude(l1 + w / 2).edges("|Z").fillet(0.15 * w))
    body = body.cut(cq.Workplane("XY").workplane(offset=l1 - gl).rect(w + 2, b).extrude(gl + w))
    body = body.cut(cq.Workplane("XZ").center(0, l1).circle(dp / 2).extrude(w, both=True))
    depth = 1.5 * d["d"] + 2
    tool = S._revolve(cq, [(0, -1), (d["d"] * 0.54 + 0.6, -1), (d["tap"] / 2, 0.3)] + S._bands(d["tap"] / 2, 0.3, depth, d["P"] / 2)
                      + [(0, depth + d["tap"] / 2 * 0.6)])
    return F.body_color(body.cut(tool, clean=False), F.STEEL)


register(Family("DIN 71752", "Vidlice (vidlicový kloub)", "Čepy/Vidlice", nums=["DIN 71752", "ISO 8140"], regex=r"G?\s*M?(?P<d>\d+(?:\.\d+)?)",
                parse=_fork_parse, build=_fork, rows=[[k, *v] for k, v in FORK.items()], columns=["thread", "slot b", "pin d", "l1", "w", "g"],
                example="DIN 71752 M8", aliases="vidlice vidlicový kloub clevis fork rod end", source=SRC,
                anchors=lambda d: {"thread_end": (0, 0, 0), "pin_axis": (0, 0, d["l1"]), "axis": "+Z = fork"},
                note="Threaded end at Z=0, pin axis along Y at Z=l1."))

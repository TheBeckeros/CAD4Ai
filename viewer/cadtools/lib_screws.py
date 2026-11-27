"""Screws (Šrouby): hex, socket, slotted, cross, hexalobular, square, wing, eye, shoulder, set screws, studs,
self-tapping. Values: ISO / DIN nominal dimensions typed from general knowledge (status unverified) - fine for
design, check the maker's data for tight fits."""
from . import famreg as F
from . import screws as S
from .famreg import Family, register

SRC = "ISO / DIN nominal head dimensions (max), typed from general knowledge"

# hex head: s, k (ISO 4017 / 4014 / 8765 / 8676)
HEX = {"M2": (4, 1.4), "M2.5": (5, 1.7), "M3": (5.5, 2), "M4": (7, 2.8), "M5": (8, 3.5), "M6": (10, 4), "M8": (13, 5.3),
       "M10": (16, 6.4), "M12": (18, 7.5), "M14": (21, 8.8), "M16": (24, 10), "M18": (27, 11.5), "M20": (30, 12.5),
       "M22": (34, 14), "M24": (36, 15), "M27": (41, 17), "M30": (46, 18.7)}
# socket head cap ISO 4762: dk, k, s, t
SOCK = {"M2": (3.8, 2, 1.5, 1), "M2.5": (4.5, 2.5, 2, 1.1), "M3": (5.5, 3, 2.5, 1.3), "M4": (7, 4, 3, 2), "M5": (8.5, 5, 4, 2.5),
        "M6": (10, 6, 5, 3), "M8": (13, 8, 6, 4), "M10": (16, 10, 8, 5), "M12": (18, 12, 10, 6), "M14": (21, 14, 12, 7),
        "M16": (24, 16, 14, 8), "M20": (30, 20, 17, 10), "M24": (36, 24, 19, 12), "M30": (45, 30, 22, 15.5)}
# DIN 7984 low head socket: dk, k, s, t
LOWSOCK = {"M3": (5.5, 2, 2, 1.5), "M4": (7, 2.8, 2.5, 2.3), "M5": (8.5, 3.5, 3, 2.7), "M6": (10, 4, 4, 3),
           "M8": (13, 5, 5, 3.8), "M10": (16, 6, 7, 4.5), "M12": (18, 7, 8, 5), "M16": (24, 9, 12, 6.8), "M20": (30, 11, 14, 8.6)}
# ISO 10642 countersunk socket: dk (theoretical), k, s, t
CSKS = {"M3": (6.72, 1.86, 2, 1.1), "M4": (8.96, 2.48, 2.5, 1.5), "M5": (11.2, 3.1, 3, 1.9), "M6": (13.44, 3.72, 4, 2.2),
        "M8": (17.92, 4.96, 5, 3.0), "M10": (22.4, 6.2, 6, 3.6), "M12": (26.88, 7.44, 8, 4.3), "M16": (33.6, 8.8, 10, 4.8),
        "M20": (40.32, 10.16, 12, 5.6)}
# ISO 7380 button: dk, k, s, t
BUTTON = {"M3": (5.7, 1.65, 2, 1.04), "M4": (7.6, 2.2, 2.5, 1.3), "M5": (9.5, 2.75, 3, 1.56), "M6": (10.5, 3.3, 4, 2.08),
          "M8": (14, 4.4, 5, 2.6), "M10": (17.5, 5.5, 6, 3.12), "M12": (21, 6.6, 8, 4.16), "M16": (28, 8.8, 10, 5.2)}
# slotted cheese ISO 1207 / pan ISO 1580 / countersunk ISO 2009: dk, k, n, t
CHEESE = {"M2": (3.8, 1.3, 0.5, 0.6), "M2.5": (4.5, 1.6, 0.6, 0.7), "M3": (5.5, 2, 0.8, 0.85), "M4": (7, 2.6, 1.2, 1.1),
          "M5": (8.5, 3.3, 1.2, 1.3), "M6": (10, 3.9, 1.6, 1.6), "M8": (13, 5, 2, 2), "M10": (16, 6, 2.5, 2.4)}
PAN = {"M2": (4, 1.3, 0.5, 0.5), "M2.5": (5, 1.5, 0.6, 0.6), "M3": (5.6, 1.8, 0.8, 0.7), "M4": (8, 2.4, 1.2, 1),
       "M5": (9.5, 3, 1.2, 1.2), "M6": (12, 3.6, 1.6, 1.4), "M8": (16, 4.8, 2, 1.9), "M10": (20, 6, 2.5, 2.4)}
CSK = {"M2": (3.8, 1.2, 0.5, 0.5), "M2.5": (4.7, 1.5, 0.6, 0.6), "M3": (5.5, 1.65, 0.8, 0.6), "M4": (8.4, 2.7, 1.2, 1),
       "M5": (9.3, 2.7, 1.2, 1.1), "M6": (11.3, 3.3, 1.6, 1.2), "M8": (15.8, 4.65, 2, 1.8), "M10": (18.3, 5, 2.5, 2)}
RAISE_F = {"M2": 0.5, "M2.5": 0.6, "M3": 0.75, "M4": 1, "M5": 1.25, "M6": 1.5, "M8": 2, "M10": 2.3}
# cross recess: ISO 7045 pan dk, k, PH ; ISO 7046 countersunk PH (head as ISO 2009)
PAN_CROSS = {"M2": (4, 1.6, 1), "M2.5": (5, 2.1, 1), "M3": (5.6, 2.4, 1), "M4": (8, 3.1, 2), "M5": (9.5, 3.7, 2),
             "M6": (12, 4.6, 3), "M8": (16, 6, 4), "M10": (20, 7.5, 4)}
CSK_PH = {"M2": 0, "M2.5": 1, "M3": 1, "M4": 2, "M5": 2, "M6": 3, "M8": 4, "M10": 4}
# hexalobular: ISO 14580 cheese dk, k, T ; ISO 14583 pan dk, k, T ; ISO 14581 countersunk T
TX_CHEESE = {"M2": (3.8, 1.55, 6), "M2.5": (4.5, 1.85, 8), "M3": (5.5, 2.4, 10), "M4": (7, 3.1, 20), "M5": (8.5, 3.65, 25),
             "M6": (10, 4.4, 30), "M8": (13, 5.8, 45), "M10": (16, 6.9, 50)}
TX_PAN = {"M2": (4, 1.6, 6), "M2.5": (5, 2.1, 8), "M3": (5.6, 2.4, 10), "M4": (8, 3.1, 20), "M5": (9.5, 3.7, 25),
          "M6": (12, 4.6, 30), "M8": (16, 6, 45), "M10": (20, 7.5, 50)}
TX_CSK = {"M2": 6, "M2.5": 8, "M3": 10, "M4": 20, "M5": 25, "M6": 30, "M8": 40, "M10": 50}
# ISO 4162 / DIN 6921 flange hex: s, k, dc, c
FLANGE = {"M5": (8, 5.4, 11.8, 1.0), "M6": (10, 6.6, 14.2, 1.1), "M8": (13, 8.1, 17.9, 1.2), "M10": (15, 9.2, 21.8, 1.5),
          "M12": (18, 11.5, 26, 1.8), "M14": (21, 12.8, 29.9, 2.1), "M16": (24, 14.7, 34.5, 2.4), "M20": (30, 18.2, 42.8, 3.0)}
# EN 14399-4 HV structural bolt: s, k, dw, c, b
HV = {"M12": (22, 8, 19.9, 0.8, 23), "M16": (27, 10, 24.9, 0.8, 28), "M20": (32, 13, 29.5, 0.8, 33), "M22": (36, 14, 33.3, 0.8, 34),
      "M24": (41, 15, 38.0, 0.8, 39), "M27": (46, 17, 42.8, 0.8, 41), "M30": (50, 19, 46.6, 0.8, 44)}
# DIN 478 square head with collar: s, k, dc, c ; DIN 479 square head set screw (dog point): s, k
SQUARE = {"M5": (8, 3.5, 10, 1), "M6": (10, 4, 13, 1.2), "M8": (13, 5.5, 16, 1.5), "M10": (17, 7, 20, 2), "M12": (19, 8, 24, 2.5),
          "M16": (24, 10, 30, 3), "M20": (30, 13, 36, 4)}
SQUARE_SET = {"M5": (5, 5), "M6": (6, 6), "M8": (8, 7), "M10": (10, 8), "M12": (12, 10), "M16": (16, 12), "M20": (20, 14)}
# DIN 316 wing screw: e (span), h (height)
WING = {"M4": (20, 10.5), "M5": (26, 13), "M6": (33, 17), "M8": (39, 20), "M10": (51, 25), "M12": (65, 33.5)}
# DIN 580 eye bolt: d1 ring outer, d2 ring section, d4 collar, h total above seat, k collar, l thread length
EYE = {"M8": (36, 8, 20, 36, 6, 13), "M10": (45, 10, 25, 45, 8, 17), "M12": (54, 12, 30, 53, 10, 20.5),
       "M16": (63, 14, 35, 62, 12, 27), "M20": (72, 16, 40, 71, 14, 30), "M24": (90, 20, 50, 90, 18, 36)}
# ISO 7379 shoulder screw by shoulder ds: thread, l2 thread length, dk, k, s
SHOULDER = {6: ("M5", 9.5, 10, 4.5, 3), 8: ("M6", 11, 13, 5.5, 4), 10: ("M8", 13, 16, 7, 5), 12: ("M10", 16, 18, 8, 6),
            16: ("M12", 18, 24, 10, 8), 20: ("M16", 22, 30, 14, 10)}
# set screws: hex socket s (ISO 4026-4029), slot n, t (ISO 4766 / 7434-7436), dog point dp, z (ISO 4028 / 7435)
SET_S = {"M2": 0.9, "M2.5": 1.3, "M3": 1.5, "M4": 2, "M5": 2.5, "M6": 3, "M8": 4, "M10": 5, "M12": 6, "M16": 8, "M20": 10}
SET_SLOT = {"M2": (0.25, 0.84), "M2.5": (0.4, 0.95), "M3": (0.4, 1.05), "M4": (0.6, 1.42), "M5": (0.8, 1.63), "M6": (1, 2),
            "M8": (1.2, 2.5), "M10": (1.6, 3), "M12": (2, 3.6)}
DOG = {"M3": (2, 1.5), "M4": (2.5, 2), "M5": (3.5, 2.5), "M6": (4, 3), "M8": (5.5, 4), "M10": (7, 5), "M12": (8.5, 6),
       "M16": (12, 8), "M20": (15, 10)}
# self-tapping: ISO 7049 pan cross dk, k, PH ; ISO 7050 countersunk cross dk, k, PH ; ISO 1479 hex s, k
ST_PAN = {"ST2.2": (4, 1.6, 0), "ST2.9": (5.6, 2.4, 1), "ST3.5": (7, 2.6, 2), "ST3.9": (7.5, 2.8, 2), "ST4.2": (8, 3.1, 2),
          "ST4.8": (9.5, 3.5, 2), "ST5.5": (11, 3.8, 3), "ST6.3": (12, 4.2, 3)}
ST_CSK = {"ST2.2": (3.8, 1.1, 0), "ST2.9": (5.5, 1.7, 1), "ST3.5": (6.8, 2.35, 2), "ST3.9": (7.5, 2.6, 2), "ST4.2": (8.1, 2.6, 2),
          "ST4.8": (9.5, 3, 2), "ST5.5": (10.8, 3.4, 3), "ST6.3": (12.4, 3.8, 3)}
ST_HEX = {"ST2.2": (3.2, 1.6), "ST2.9": (5, 2), "ST3.5": (5.5, 2.4), "ST4.2": (7, 2.8), "ST4.8": (8, 3.2), "ST5.5": (8, 3.5), "ST6.3": (10, 4.2)}


# ---------------------------------------------------------------- shared parse / anchors / tools

def _need_L(L, code):
    if not L:
        raise ValueError(f"length missing: write e.g. {code}")
    return L


def headed_anchors(d):
    k = d.get("k", 0)
    if d.get("csk"):
        return {"head_top": (0, 0, d.get("f", 0)), "seat_cone": (0, 0, -k), "tip": (0, 0, -d["L"]), "axis": "+Z = towards the head"}
    return {"seat": (0, 0, 0), "head_top": (0, 0, k), "tip": (0, 0, -d["L"]), "axis": "+Z = towards the head"}


def _hole_tools():
    def clear(d):
        from .std import THREAD
        dc = THREAD[d["size"]][3] if d.get("size") in THREAD else d["d"] + 0.5
        return F.ring(dc / 2, 0, d["L"] + 2, -d["L"] - 1)

    def tapped(d):
        return F.ring(d["tap"] / 2, 0, d["L"] + 2 * d["P"] + 1, -d["L"] - 2 * d["P"])

    def cbore(d):
        from .std import CBORE
        cb = CBORE.get(d.get("size"), (d.get("dk", 2 * d["d"]) + 1, d.get("k", d["d"]) + 0.4))
        return clear(d).union(F.ring(cb[0] / 2, 0, cb[1] + 0.01, -0.01).translate((0, 0, d.get("k", 0) - cb[1] + 0.4)))
    return {"clearance": clear, "tap": tapped, "cbore": cbore}


def _csk_tools():
    t = _hole_tools()

    def csk(d):
        r = d["dk"] / 2 + 0.2
        cone = F.revolve([(0, -r), (r, 0), (r, 1), (0, 1)])
        return t["clearance"](d).union(cone)
    return {"clearance": t["clearance"], "tap": t["tap"], "csk": csk}


def _head(row, size, csk, headless):
    """(k, dk) known before building, for anchors and tools."""
    if headless:
        return 0.0, None
    if isinstance(row, tuple):
        return row[1], row[0]
    if csk and size in CSK:
        return CSK[size][1], CSK[size][0]
    return 0.0, None


def screw_family(fid, title, sub, nums, tab, build, columns, example, aliases, fine=False, csk=False,
                 note="", words=(), size_kind="metric", headless=False):
    """Register a screw family: tab[size] -> row; build(d, row) -> Workplane; d has size, d (nominal), P, tap, L."""

    def parse(g, token, kw):
        if size_kind == "st":
            size = "ST" + g["d"]
            L = F.num(g.get("a")) or kw.get("L")
            row = F.table(tab, size, fid)
            dd = float(g["d"])
            k, dk = _head(row, size, csk, headless)
            return {"size": size, "d": dd, "P": S.ST_PITCH[size], "tap": round(dd * 0.75, 1), "L": _need_L(L, example),
                    "row": row, "csk": csk, "k": k, "dk": dk}
        size, P, L = F.metric(g, length=True)
        if fine and not P:
            raise ValueError(f"fine pitch missing: write e.g. {example}")
        if not fine and P:
            raise ValueError(f"{fid} is a coarse thread family (fine pitch: see the fine-thread family)")
        L = L or kw.get("L")
        row = F.table(tab, size, fid)
        dd = float(size[1:])
        P = F.pitch(size, P)
        k, dk = _head(row, size, csk, headless)
        return {"size": size, "d": dd, "P": P, "tap": F.tap(size, P if fine else None), "L": _need_L(L, example),
                "row": row, "csk": csk, "pitch_code": f"{size}x{P:g}" if fine else size, "k": k, "dk": dk}

    def bld(d):
        w = build(d, d["row"])
        return F.body_color(w, F.STEEL)

    def anchors(d):
        a = headed_anchors(d)
        return a

    rx = (r"(?P<d>\d+(?:\.\d+)?)\s*(?:x\s*(?P<a>\d+(?:\.\d+)?))?" if size_kind == "st" else F.METRIC)
    if size_kind == "st":
        rx = r"ST\s*" + rx
    rows = [[k, *(v if isinstance(v, tuple) else (v,))] for k, v in tab.items()]
    if fine:
        from .std import FINE
        rows = [[fc, *(tab[fc.split("x")[0]] if isinstance(tab[fc.split("x")[0]], tuple) else (tab[fc.split("x")[0]],))]
                for fc in FINE if fc.split("x")[0] in tab]
    return register(Family(fid, title, "Šrouby/" + sub, nums=nums, regex=rx, parse=parse, build=bld, rows=rows,
                           columns=["size", *columns], example=example, aliases=aliases, ptype="fastener",
                           source=SRC, anchors=anchors, tools=_csk_tools() if csk else _hole_tools(), note=note,
                           words=words))


def _rf(d):
    return S.UNDERHEAD_R.get(d["size"], 0.1 * d["d"])


def _b(std_name, d, k=0.0):
    return S.thread_length(std_name, d["d"], d["L"], k)


def _set_k(d, k):
    d["k"] = k


# ---------------------------------------------------------------- hex head

def _hex(form):
    def b(d, row):
        s, k = row
        dw, c = S.HEX_WASHER.get(d["size"], (0.9 * s, 0.1 * d["d"]))
        d["k"] = k
        return S.headed(d["d"], d["P"], d["L"], "hex", _b(form, d), rf=_rf(d), s=s, k=k, dw=dw, c=c)
    return b


HEXT = "Šrouby se šestihrannou hlavou"
screw_family("ISO 4017", "Šestihranný šroub, celý závit", HEXT, ["ISO 4017", "DIN 933", "CSN 021103"], HEX, _hex("ISO 4017"),
             ["s", "k"], "ISO 4017 M8x30", "šestihran šestihranná hlava hex head bolt šroub screw celozávitový")
screw_family("ISO 4014", "Šestihranný šroub, částečný závit", HEXT, ["ISO 4014", "DIN 931", "CSN 021101"], HEX, _hex("ISO 4014"),
             ["s", "k"], "ISO 4014 M10x60", "šestihran šestihranná hlava hex bolt šroub screw dřík částečný závit")
screw_family("ISO 8765", "Šestihranný šroub, jemný závit, částečný", "Šrouby se šestihrannou hlavou - jemný závit",
             ["ISO 8765", "DIN 960"], HEX, _hex("ISO 8765"), ["s", "k"], "ISO 8765 M10x1.25x60",
             "šestihran jemný závit jemné stoupání fine thread hex bolt", fine=True)
screw_family("ISO 8676", "Šestihranný šroub, jemný závit, celý", "Šrouby se šestihrannou hlavou - jemný závit",
             ["ISO 8676", "DIN 961"], HEX, _hex("ISO 8676"), ["s", "k"], "ISO 8676 M12x1.5x40",
             "šestihran jemný závit jemné stoupání fine thread hex screw celozávitový", fine=True)


def _hv(d, row):
    s, k, dw, c, bb = row
    d["k"] = k
    b = bb if d["L"] - bb >= 0.5 * d["d"] else None
    return S.headed(d["d"], d["P"], d["L"], "hex", b, rf=_rf(d), s=s, k=k, dw=dw, c=c)


screw_family("EN 14399-4", "Šroub HV pro ocelové konstrukce", "Šrouby se šestihrannou hlavou - konstrukční",
             ["EN 14399-4", "DIN 6914"], HV, _hv, ["s", "k", "dw", "c", "b"], "EN 14399-4 M20x80",
             "HV předpjatý konstrukční šroub ocelové konstrukce structural bolt velký šestihran 10.9")


def _flange(d, row):
    s, k, dc, c = row
    d["k"] = k
    return S.headed(d["d"], d["P"], d["L"], "flange", S.thread_length("ISO 4162p", d["d"], d["L"]), rf=_rf(d), s=s, k=k, dc=dc, c=c)


screw_family("ISO 4162", "Šestihranný šroub s přírubou", "Smíšené", ["ISO 4162", "DIN 6921", "ISO 15071"], FLANGE, _flange,
             ["s", "k", "dc", "c"], "ISO 4162 M8x25", "příruba přírubový šestihran flange bolt límec")


# ---------------------------------------------------------------- socket

def _sock(form, tab_t=None):
    def b(d, row):
        dk, k, s, t = row
        d["k"], d["dk"] = k, dk
        return S.headed(d["d"], d["P"], d["L"], "socket", _b(form, d), rf=_rf(d), dk=dk, k=k, drive="socket", s=s, t=t)
    return b


SOCKT = "Šrouby s šestihranným vnitřním vybráním"
screw_family("ISO 4762", "Imbus, válcová hlava", SOCKT, ["ISO 4762", "DIN 912", "CSN 021143"], SOCK, _sock("ISO 4762"),
             ["dk", "k", "s", "t"], "ISO 4762 M5x16", "imbus inbus socket cap allen válcová hlava šroub screw")
screw_family("DIN 7984", "Imbus, nízká válcová hlava", SOCKT, ["DIN 7984", "DIN 6912"], LOWSOCK, _sock("DIN 7984"),
             ["dk", "k", "s", "t"], "DIN 7984 M6x20", "imbus nízká hlava low head socket cap")


def _csks(d, row):
    dk, k, s, t = row
    d.update(k=k, dk=dk)
    return S.headed(d["d"], d["P"], d["L"], "csk", _b("ISO 10642", d, k), dk=dk, k=k, drive="socket", s=s, t=t)


screw_family("ISO 10642", "Imbus, zápustná hlava", SOCKT, ["ISO 10642", "DIN 7991"], CSKS, _csks, ["dk", "k", "s", "t"],
             "ISO 10642 M6x20", "zápustný zapustny countersunk flat head imbus", csk=True, note="Head top at Z=0, L includes the head.")


def _button(d, row):
    dk, k, s, t = row
    d.update(k=k, dk=dk)
    return S.headed(d["d"], d["P"], d["L"], "button", None, rf=_rf(d), dk=dk, k=k, drive="socket", s=s, t=t)


screw_family("ISO 7380", "Imbus, půlkulatá hlava", SOCKT, ["ISO 7380"], BUTTON, _button, ["dk", "k", "s", "t"],
             "ISO 7380 M4x10", "půlkulatá pulkulata čočková button head imbus")


def _shoulder_parse(g, token, kw):
    ds = int(float(g["ds"]))
    ls = F.num(g.get("ls")) or kw.get("L")
    th, l2, dk, k, s = F.table(SHOULDER, ds, "ISO 7379")
    from .std import THREAD
    return {"size": th, "d": float(th[1:]), "P": THREAD[th][0], "tap": THREAD[th][1], "ds": ds, "ls": _need_L(ls, "ISO 7379 10x40"),
            "L": ls + l2, "l2": l2, "dk": dk, "k": k, "s": s}


register(Family("ISO 7379", "Lícovaný šroub (osazený)", "Šrouby/Smíšené", nums=["ISO 7379"],
                regex=r"(?P<ds>\d+)\s*x\s*(?P<ls>\d+(?:\.\d+)?)", parse=_shoulder_parse,
                build=lambda d: F.body_color(S.headed(d["d"], d["P"], d["ls"] + d["l2"], "shoulder", rf=0.4, dk=d["dk"], k=d["k"],
                                                      ds=d["ds"], ls=d["ls"], l2=d["l2"], s=d["s"]), F.STEEL),
                rows=[[k, *v] for k, v in SHOULDER.items()], columns=["shoulder d", "thread", "l2", "dk", "k", "s"],
                example="ISO 7379 10x40", aliases="lícovaný osazený šroub shoulder screw stripper bolt", source=SRC,
                anchors=lambda d: {"seat": (0, 0, 0), "head_top": (0, 0, d["k"]), "shoulder_end": (0, 0, -d["ls"]),
                                   "tip": (0, 0, -d["ls"] - d["l2"]), "axis": "+Z = towards the head"},
                note="Code: shoulder d x shoulder length."))


# ---------------------------------------------------------------- slotted, cross, hexalobular

def _slot(head, tab, raised=False):
    def b(d, row):
        dk, k, n, t = row
        d.update(k=k, dk=dk)
        if head == "csk":
            f = RAISE_F.get(d["size"], 0.2 * k) if raised else 0
            d["f"] = f
            return S.headed(d["d"], d["P"], d["L"], "raised_csk" if raised else "csk", None, dk=dk, k=k, f=f,
                            drive="slot", n=n, t=t + f)
        return S.headed(d["d"], d["P"], d["L"], head, None, rf=_rf(d), dk=dk, k=k, drive="slot", n=n, t=t)
    return b


SLOTT = "Šrouby s drážkou"
screw_family("ISO 1207", "Válcová hlava s drážkou", SLOTT, ["ISO 1207", "DIN 84"], CHEESE, _slot("cheese", CHEESE),
             ["dk", "k", "n", "t"], "ISO 1207 M4x10", "drážka plochý šroubovák válcová hlava slotted cheese head")
screw_family("ISO 1580", "Čočková hlava s drážkou", SLOTT, ["ISO 1580", "DIN 85"], PAN, _slot("pan", PAN),
             ["dk", "k", "n", "t"], "ISO 1580 M4x10", "drážka čočková plochá hlava slotted pan head")
screw_family("ISO 2009", "Zápustná hlava s drážkou", SLOTT, ["ISO 2009", "DIN 963"], CSK, _slot("csk", CSK),
             ["dk", "k", "n", "t"], "ISO 2009 M4x10", "drážka zápustná slotted countersunk", csk=True)
screw_family("ISO 2010", "Čočkovitá zápustná hlava s drážkou", SLOTT, ["ISO 2010", "DIN 964"], CSK, _slot("csk", CSK, True),
             ["dk", "k", "n", "t"], "ISO 2010 M4x10", "drážka čočkovitá zápustná raised countersunk", csk=True)


def _cross_pan(d, row):
    dk, k, ph = row
    d.update(k=k, dk=dk)
    return S.headed(d["d"], d["P"], d["L"], "pan", None, rf=_rf(d), dk=dk, k=k, drive="cross", ph=ph)


def _cross_csk(d, row):
    dk, k = CSK[d["size"]][:2]
    d.update(k=k, dk=dk)
    return S.headed(d["d"], d["P"], d["L"], "csk", None, dk=dk, k=k, drive="cross", ph=row)


CROSST = "Šrouby křížové se zápustnou hlavou"
screw_family("ISO 7046", "Zápustná hlava, křížová drážka", CROSST, ["ISO 7046", "DIN 965"], CSK_PH, _cross_csk, ["PH"],
             "ISO 7046 M4x12", "křížový křížová drážka phillips zápustný countersunk", csk=True)
screw_family("ISO 7045", "Čočková hlava, křížová drážka", CROSST, ["ISO 7045", "DIN 7985"], PAN_CROSS, _cross_pan,
             ["dk", "k", "PH"], "ISO 7045 M4x10", "křížový křížová drážka phillips čočková pan head")


def _tx(head, tab):
    def b(d, row):
        if head == "csk":
            dk, k = CSK[d["size"]][:2]
            d.update(k=k, dk=dk)
            return S.headed(d["d"], d["P"], d["L"], "csk", None, dk=dk, k=k, drive="torx", tx=row, t=0.55 * k)
        dk, k, tx = row
        d.update(k=k, dk=dk)
        return S.headed(d["d"], d["P"], d["L"], head, None, rf=_rf(d), dk=dk, k=k, drive="torx", tx=tx, t=0.5 * k)
    return b


screw_family("ISO 14580", "Válcová hlava Torx", "Smíšené", ["ISO 14580"], TX_CHEESE, _tx("cheese", TX_CHEESE), ["dk", "k", "T"],
             "ISO 14580 M5x12", "torx hvězda hexalobular válcová cheese")
screw_family("ISO 14583", "Čočková hlava Torx", "Smíšené", ["ISO 14583"], TX_PAN, _tx("pan", TX_PAN), ["dk", "k", "T"],
             "ISO 14583 M4x10", "torx hvězda hexalobular čočková pan")
screw_family("ISO 14581", "Zápustná hlava Torx", "Smíšené", ["ISO 14581"], TX_CSK, _tx("csk", TX_CSK), ["T"],
             "ISO 14581 M5x16", "torx hvězda hexalobular zápustná countersunk", csk=True)


# ---------------------------------------------------------------- square, wing, eye

def _sq(d, row):
    s, k, dc, c = row
    d["k"] = k
    return S.headed(d["d"], d["P"], d["L"], "square", S.thread_length("ISO 4014", d["d"], d["L"]), rf=_rf(d), s=s, k=k, dc=dc, c=c)


screw_family("DIN 478", "Šroub s čtyřhrannou hlavou a nákružkem", "Šroub s čtyřhrannou hlavou", ["DIN 478"], SQUARE, _sq,
             ["s", "k", "dc", "c"], "DIN 478 M10x40", "čtyřhran čtyřhranná hlava square head bolt")


def _sq_set(d, row):
    s, k = row
    d["k"] = k
    dp, z = DOG.get(d["size"], (0.6 * d["d"], 0.5 * d["d"]))
    return S.headed(d["d"], d["P"], d["L"], "square", None, tip="dog", rf=_rf(d), s=s, k=k, dp=dp, z_len=z)


screw_family("DIN 479", "Stavěcí šroub s čtyřhrannou hlavou, čep", "Stavěcí šroub - s čtyřhrannou hlavou", ["DIN 479"], SQUARE_SET,
             _sq_set, ["s", "k"], "DIN 479 M10x30", "stavěcí čtyřhran čtyřhranná hlava square head set screw čípek")


def _wing(d, row):
    e, h = row
    d["k"] = h
    return S.headed(d["d"], d["P"], d["L"], "wing", None, rf=_rf(d), e=e, h=h)


screw_family("DIN 316", "Šroub s křídlovou hlavou", "Šroub s křídlovou hlavou", ["DIN 316"], WING, _wing, ["e", "h"],
             "DIN 316 M6x20", "křídlový šroub křídlová hlava wing screw thumb")


def _eye_parse(g, token, kw):
    size, P, L = F.metric(g, length=True)
    d1, d2, d4, h, k, l = F.table(EYE, size, "DIN 580")
    return {"size": size, "d": float(size[1:]), "P": F.pitch(size), "tap": F.tap(size), "L": L or l,
            "d1": d1, "d2": d2, "d4": d4, "h": h, "k": h}


register(Family("DIN 580", "Závěsný šroub (oko)", "Šrouby/Smíšené", nums=["DIN 580"], regex=F.METRIC, parse=_eye_parse,
                build=lambda d: F.body_color(S.headed(d["d"], d["P"], d["L"], "eye", None, rf=0.5, d1=d["d1"], d2=d["d2"], d4=d["d4"],
                                                      h=d["h"], k=d["d4"] * 0.3), F.STEEL),
                rows=[[k, *v] for k, v in EYE.items()], columns=["size", "d1 ring", "d2 section", "d4 collar", "h", "k", "thread l"],
                example="DIN 580 M12", aliases="závěsné oko očnicový šroub eye bolt lifting", source=SRC,
                anchors=lambda d: {"seat": (0, 0, 0), "top": (0, 0, d["h"]), "tip": (0, 0, -d["L"]), "axis": "+Z = ring"},
                tools=_hole_tools()))


# ---------------------------------------------------------------- set screws

def _set(point, drive_kind):
    def b(d, row):
        d["k"] = 0
        if drive_kind == "socket":
            kw = {"s": row}
        else:
            kw = {"n": row[0], "t": row[1]}
        if point == "dog":
            kw["dp"], kw["z_len"] = DOG.get(d["size"], (0.6 * d["d"], 0.5 * d["d"]))
        return S.set_screw(d["d"], d["P"], d["L"], point, drive_kind, **kw)
    return b


SETT = "Stavěcí šrouby - s vnitřním vybráním"
for fid, nums, point, title, al in [
        ("ISO 4026", ["ISO 4026", "DIN 913"], "flat", "Stavěcí šroub, imbus, plochý konec", "plochý konec flat point"),
        ("ISO 4027", ["ISO 4027", "DIN 914"], "cone", "Stavěcí šroub, imbus, kuželový hrot", "hrot kužel cone point"),
        ("ISO 4028", ["ISO 4028", "DIN 915"], "dog", "Stavěcí šroub, imbus, čípek", "čípek čep dog point"),
        ("ISO 4029", ["ISO 4029", "DIN 916"], "cup", "Stavěcí šroub, imbus, důlek", "důlek miska cup point")]:
    screw_family(fid, title, SETT, nums, SET_S, _set(point, "socket"), ["s"], f"{fid} M6x10",
                 "stavěcí stavecí červík set screw grub imbus " + al, note="Drive end at Z=0, body to -Z.", headless=True)
SLOTSETT = "Stavěcí šrouby - s drážkou"
for fid, nums, point, title, al in [
        ("ISO 4766", ["ISO 4766", "DIN 551"], "flat", "Stavěcí šroub s drážkou, plochý konec", "plochý konec flat"),
        ("ISO 7434", ["ISO 7434", "DIN 553"], "cone", "Stavěcí šroub s drážkou, hrot", "hrot kužel cone"),
        ("ISO 7435", ["ISO 7435", "DIN 417"], "dog", "Stavěcí šroub s drážkou, čípek", "čípek dog"),
        ("ISO 7436", ["ISO 7436", "DIN 438"], "cup", "Stavěcí šroub s drážkou, důlek", "důlek cup")]:
    screw_family(fid, title, SLOTSETT, nums, SET_SLOT, _set(point, "slot"), ["n", "t"], f"{fid} M5x8",
                 "stavěcí červík drážka slotted set screw " + al, note="Slot end at Z=0, body to -Z.", headless=True)


# ---------------------------------------------------------------- studs and rods

def _stud_family(fid, nums, title, factor, sub):
    def parse(g, token, kw):
        size, P, L = F.metric(g, length=True)
        fine = bool(P)
        P = F.pitch(size, P)
        L = _need_L(L or kw.get("L"), f"{fid} M10x40")
        dd = float(size[1:])
        bm = factor * dd
        b = 2 * dd + 6 if L <= 125 else 2 * dd + 12
        return {"size": size, "d": dd, "P": P, "tap": F.tap(size, P if fine else None), "L": L, "bm": bm,
                "b": None if L - b < 0.5 * dd else b}

    register(Family(fid, title, "Šrouby/" + sub, nums=nums, regex=F.METRIC, parse=parse,
                    build=lambda d: F.body_color(S.stud(d["d"], d["P"], d["L"], d["bm"], d["b"]), F.STEEL),
                    rows=[[k, round(factor * float(k[1:]), 1)] for k in HEX if k not in ("M2", "M2.5")], columns=["size", "bm (metal end)"],
                    example=f"{fid} M10x40", aliases="závrtný šroub svorník bez hlavy stud " + ("jemný " if False else ""),
                    source="DIN stud ends bm = k d, nut end thread b = 2d+6", note="Metal end bm to -Z from Z=0, nut end L to +Z. Fine thread: M10x1.25x40.",
                    anchors=lambda d: {"face": (0, 0, 0), "metal_end": (0, 0, -d["bm"]), "nut_end": (0, 0, d["L"]), "axis": "+Z = nut end"},
                    tools={"tap": lambda d: F.ring(d["tap"] / 2, 0, d["bm"] + 3 * d["P"], -d["bm"] - 3 * d["P"])}))


_stud_family("DIN 938", ["DIN 938"], "Závrtný šroub, konec 1d (ocel)", 1.0, "Závrtný šroub (bez hlavy)")
_stud_family("DIN 939", ["DIN 939"], "Závrtný šroub, konec 1,25d (litina)", 1.25, "Závrtný šroub (bez hlavy)")
_stud_family("DIN 835", ["DIN 835"], "Závrtný šroub, konec 2d (hliník)", 2.0, "Závrtný šroub (bez hlavy)")
_stud_family("DIN 940", ["DIN 940"], "Závrtný šroub, konec 2,5d (lehké slitiny)", 2.5, "Závrtný šroub (bez hlavy)")


def _rod_parse(g, token, kw):
    size, P, L = F.metric(g, length=True)
    fine = bool(P)
    P = F.pitch(size, P)
    L = _need_L(L or kw.get("L"), "DIN 976 M10x1000")
    return {"size": size, "d": float(size[1:]), "P": P, "tap": F.tap(size, P if fine else None), "L": L}


register(Family("DIN 976", "Závitová tyč", "Šrouby/Závrtný šroub (bez hlavy)", nums=["DIN 976", "DIN 975"], regex=F.METRIC,
                parse=_rod_parse, build=lambda d: F.body_color(S.stud(d["d"], d["P"], d["L"], 0.0, None), F.STEEL),
                rows=[[k] for k in HEX], columns=["size"], example="DIN 976 M10x200",
                aliases="závitová tyč svorník threaded rod stud bolt", source="any length", note="From Z=0 to Z=L.",
                anchors=lambda d: {"bottom": (0, 0, 0), "top": (0, 0, d["L"]), "axis": "+Z"}))


# ---------------------------------------------------------------- self-tapping

def _st(head):
    def b(d, row):
        if head == "pan":
            dk, k, ph = row
            d.update(k=k, dk=dk)
            return S.headed(d["d"], d["P"], d["L"], "pan", None, tip="point", rf=0.1, dk=dk, k=k, drive="cross", ph=ph)
        if head == "csk":
            dk, k, ph = row
            d.update(k=k, dk=dk)
            return S.headed(d["d"], d["P"], d["L"], "csk", None, tip="point", dk=dk, k=k, drive="cross", ph=ph)
        s, k = row
        d["k"] = k
        return S.headed(d["d"], d["P"], d["L"], "hex", None, tip="point", rf=0.1, s=s, k=k, dw=0.9 * s, c=0.3)
    return b


ST_T = "Samořezné šrouby"
screw_family("ISO 7049", "Samořezný šroub, čočková hlava, křížová drážka", ST_T, ["ISO 7049", "DIN 7981"], ST_PAN, _st("pan"),
             ["dk", "k", "PH"], "ISO 7049 ST4.2x16", "samořezný do plechu self tapping sheet metal křížový čočková", size_kind="st",
             note="Pointed tip (form C). Pilot hole in sheet ~ 0.75 d.")
screw_family("ISO 7050", "Samořezný šroub, zápustná hlava, křížová drážka", ST_T, ["ISO 7050", "DIN 7982"], ST_CSK, _st("csk"),
             ["dk", "k", "PH"], "ISO 7050 ST4.2x16", "samořezný do plechu self tapping zápustný křížový", size_kind="st", csk=True)
screw_family("ISO 1479", "Samořezný šroub, šestihranná hlava", ST_T, ["ISO 1479", "DIN 7976"], ST_HEX, _st("hex"),
             ["s", "k"], "ISO 1479 ST4.8x19", "samořezný šestihran self tapping hex", size_kind="st")

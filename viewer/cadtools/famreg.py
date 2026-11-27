"""Registry of standard-part families: one code -> dimensions, geometry, anchors, counterpart tools, colours.

    from cadtools.std import part, tool, apply_colors       # (part / place also in cadtools.parts)
    s = part("DIN 933 M8x30")          # any registered code, ISO / DIN / EN synonyms, '_' or no spaces work too
    p = part("IPE 200", L=1500)        # keyword arguments go to the family (length, teeth, ...)
    k = tool("DIN 6885 A 8x7x40", "shaft")   # counterpart: keyseat volume in the part's own frame
    apply_colors(assy)                 # body / thread / seal colours, right before assy.export()

A family = id, tree path (Czech, as in CAD libraries), standard numbers that select it, a regex for the
size part of the code, parse() -> dims dict, build(dims) -> cq.Workplane, anchors(dims), tools{kind: fn(dims)},
a table (columns + rows) for the viewer, an example, aliases for search, value source and status.

Colours travel with the geometry: build functions call paint(shape, rgb) on solids or faces; apply_colors finds
them again in any placed / rotated copy by a transform-invariant signature (surface type + area, solid volume),
and every library part without its own colour gets its family colour. Thread rings are found by geometry
(screws.thread_faces).
"""
import math
import re
import unicodedata

FAMILIES = {}          # id -> Family
_ORDER = []            # registration order (tree order)
_LOADED = False
STEEL = (0.70, 0.69, 0.67)
DARK_STEEL = (0.42, 0.43, 0.45)
STRUCT = (0.52, 0.53, 0.55)
BRASS = (0.80, 0.65, 0.30)
COPPER = (0.78, 0.47, 0.30)
RUBBER = (0.12, 0.12, 0.13)
NYLON = (0.30, 0.45, 0.85)
ALU = (0.80, 0.81, 0.83)
BLACK_OX = (0.22, 0.22, 0.24)

PREFIX = r"(?:ISO|DIN|EN|CSN|ČSN|SN)?[\s\-]*"


class Family:
    def __init__(self, fid, title, path, nums=(), regex=None, parse=None, build=None, rows=None, columns=None,
                 example="", aliases="", ptype="fastener", source="", status="unverified", anchors=None,
                 tools=None, color=STEEL, note="", words=(), mass_ref=None):
        self.id, self.title, self.path = fid, title, path
        self.nums = list(nums)            # standard numbers / leading words that select the family
        self.words = list(words)          # keywords that select it without a standard prefix (IPE, KM, GEAR)
        self.regex = re.compile(regex, re.I) if regex else None
        self.parse, self.build = parse, build
        self.rows, self.columns = rows or [], columns or []
        self.example, self.aliases, self.ptype = example, aliases, ptype
        self.source, self.status, self.note = source, status, note
        self.anchor_fn, self.tools, self.color = anchors, tools or {}, color
        self.mass_ref = mass_ref          # fn(dims) -> reference mass [kg] or kg/m for the self check
        head = []
        for n in sorted(self.nums, key=len, reverse=True):  # longest first; "DIN 933": prefix required, any spacing ("DIN933", "DIN_933", "DIN-933")
            head.append(re.escape(n).replace(r"\ ", r"[\s\-]*").replace(r"\-", r"[\s\-]*") + r"(?![0-9])")
        for w in self.words:  # "IPE", "KM": not followed by a letter ("IPE200", "KM4" fine; "IPEA" is another word)
            head.append(re.escape(w).replace(r"\ ", r"[\s\-]*") + r"(?![A-Z])")
        self.head = re.compile(r"(?<![A-Z0-9.])(?:" + "|".join(head) + r")", re.I) if head else None

    def match(self, code, kw):
        m = self.head.search(code) if self.head else None
        if not m:
            return None
        rest = code[m.end():].strip(" _-/")
        token = code[m.start():m.end()]
        sm = self.regex.match(rest) if self.regex else None
        if self.regex and not sm:
            return None
        g = sm.groupdict() if sm else {}
        d = self.parse(g, token, kw) if self.parse else dict(g)
        if d is None:
            return None
        d.setdefault("std", self.id)
        d.setdefault("type", self.ptype)
        d["family"] = self.id
        d.setdefault("std_code", std_code(self.id, d))
        return d

    def anchors(self, d):
        return self.anchor_fn(d) if self.anchor_fn else {"origin": (0, 0, 0), "axis": "+Z"}


def std_code(fid, d):
    """Canonical code of a part for parts.json 'standard' (ISO 4017 M8x30, IPE 200x1500, 6204-2RS, KM4 ...)."""
    sz = str(d.get("pitch_code") or d.get("size") or "")
    L = d.get("L")
    if d.get("profile"):
        return f"{d['profile']}x{L:g}" if L else str(d["profile"])
    if d.get("bearing") or sz.startswith(("KM", "MB", "HK")) or fid in sz:
        return sz
    code = f"{fid} {sz}".strip()
    if L and re.fullmatch(r"(M|ST)[\d.]+(x[\d.]+)?", sz):   # screws / studs: size (+ fine pitch) x length
        code += f"x{L:g}"
    return code


def register(fam):
    FAMILIES[fam.id] = fam
    _ORDER.append(fam.id)
    return fam


def load():
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    from . import lib_screws, lib_nuts, lib_washers, lib_pins, lib_shaft, lib_profiles, lib_bearings, lib_gears  # noqa: F401


def norm(code):
    c = str(code).replace("_", " ").replace("×", "x").replace(",", ".")
    c = re.sub(r"\s+", " ", c).strip()
    return c


def lookup(code, kw=None):
    """(family, dims) for a code, or (None, None)."""
    load()
    c = norm(code)
    kw = kw or {}
    best = None
    for fid in _ORDER:
        f = FAMILIES[fid]
        try:
            d = f.match(c, kw)
        except (KeyError, ValueError) as e:
            if best is None:
                best = (f, e)
            continue
        if d is not None:
            return f, d
    if best is not None:
        raise ValueError(f"{best[0].id}: {best[1]}")
    return None, None


# ---------------------------------------------------------------- size parsing helpers

def num(x, default=None):
    return float(x) if x not in (None, "") else default


METRIC = r"M(?P<d>\d+(?:\.\d+)?)(?:\s*x\s*(?P<a>\d+(?:\.\d+)?))?(?:\s*x\s*(?P<b>\d+(?:\.\d+)?))?"


def metric(g, length=True):
    """'M10x1.25x40' -> size, fine pitch, L. length=False: a single x value is the pitch (nuts)."""
    size = f"M{float(g['d']):g}"
    a, b = num(g.get("a")), num(g.get("b"))
    P, L = None, None
    if b is not None:
        P, L = a, b
    elif a is not None:
        if length:
            L = a
        else:
            P = a
    return size, P, L


def pitch(size, P=None):
    from .std import THREAD, FINE
    if P:
        if f"{size}x{P:g}" not in FINE and size in THREAD and abs(THREAD[size][0] - P) > 1e-9:
            raise ValueError(f"unknown fine thread {size}x{P:g} (have {', '.join(k for k in FINE if k.startswith(size + 'x')) or 'none'})")
        return P
    if size not in THREAD:
        raise ValueError(f"unknown thread {size}")
    return THREAD[size][0]


def tap(size, P=None):
    from .std import tap_drill
    return tap_drill(f"{size}x{P:g}" if P else size)


def table(t, key, what):
    if key not in t:
        raise ValueError(f"{what}: no size {key} (have {', '.join(str(k) for k in t)})")
    return t[key]


def sizes_sorted(keys):
    def k(s):
        m = re.search(r"\d+(?:\.\d+)?", str(s))
        return (float(m.group(0)) if m else 0, str(s))
    return sorted(keys, key=k)


# ---------------------------------------------------------------- colours that follow the geometry

_PAINT = {}   # signature -> rgb


def _sig(shape):
    import cadquery as cq
    if isinstance(shape, cq.Solid):
        return ("S", round(shape.Volume(), 3), round(shape.Area(), 3))
    if isinstance(shape, cq.Face):
        return ("F", shape.geomType(), round(shape.Area(), 4), len(shape.Edges()))
    return None


def paint(shapes, rgb):
    """Remember a colour for solids / faces of a library part (found again after place / rotate)."""
    import cadquery as cq
    if isinstance(shapes, cq.Workplane):
        shapes = shapes.vals()
    if not isinstance(shapes, (list, tuple)):
        shapes = [shapes]
    for s in shapes:
        for x in ([s] if isinstance(s, (cq.Solid, cq.Face)) else s.Solids() or s.Faces()):
            k = _sig(x)
            if k:
                _PAINT[k] = tuple(rgb)


_BODY = {}    # solid signature -> family colour (default body colour of a library part)


def body_color(wp, rgb):
    import cadquery as cq
    for s in (wp.vals() if isinstance(wp, cq.Workplane) else [wp]):
        for so in (s.Solids() if hasattr(s, "Solids") else []):
            _BODY[_sig(so)] = tuple(rgb)
    return wp


def apply_colors(assy):
    """Body colour of library parts, painted faces / solids (seals, inserts...) and dark thread rings for every
    part of a cq.Assembly. Call right before assy.export(). Returns the number of coloured sub-shapes."""
    import cadquery as cq
    from .screws import thread_faces, THREAD_DARK
    n = 0
    for _, node in assy.traverse():
        if node.obj is None:
            continue
        shapes = node.obj.vals() if isinstance(node.obj, cq.Workplane) else [node.obj]
        shapes = [s for s in shapes if isinstance(s, cq.Shape)]
        solids = [so for s in shapes for so in s.Solids()]
        if node.color is None:
            for so in solids:
                c = _BODY.get(_sig(so))
                if c:
                    node.color = cq.Color(*c)
                    break
        subs = []
        if _PAINT:
            for so in solids:
                c = _PAINT.get(_sig(so))
                if c:
                    subs += [(f, c) for f in so.Faces()]
                    continue
                for f in so.Faces():
                    c = _PAINT.get(_sig(f))
                    if c:
                        subs.append((f, c))
        done = {id(f) for f, _ in subs}
        rings = [f for s in shapes for f in thread_faces(s)]
        if rings and node.color is None:
            node.color = cq.Color(*STEEL)
        subs += [(f, THREAD_DARK) for f in rings if id(f) not in done]
        for f, c in subs:
            node.addSubshape(f, color=cq.Color(*c))
        n += len(subs)
    return n


# ---------------------------------------------------------------- search and tree

def _n(t):
    t = unicodedata.normalize("NFKD", str(t).lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def find(query, k=8):
    """Families matching Czech / English words, a standard number or a size -> [{family, title, path, example}]."""
    load()
    q = [w for w in re.split(r"[\s,;/]+", _n(query)) if w]
    size = next((w.upper() for w in q if re.fullmatch(r"m\d+(\.\d+)?", w)), None)
    out = []
    for fid in _ORDER:
        f = FAMILIES[fid]
        hay = _n(" ".join([f.id, f.title, f.path, f.aliases, " ".join(f.nums), " ".join(f.words)]))
        score = sum(2 if re.search(r"(^|\W)" + re.escape(w) + r"($|\W)", hay) else 1 for w in q if w in hay)
        if not score or (size and q and len(q) == 1):
            continue
        ex = f.example
        if size and re.search(r"M\d", ex):
            ex = re.sub(r"M\d+(\.\d+)?", size, ex, count=1)
        out.append({"family": f.id, "title": f.title, "path": f.path, "example": ex, "score": score,
                    "status": f.status})
    out.sort(key=lambda x: -x["score"])
    return out[:k]


def row_code(f, row):
    """A code that opens this table row in 3D (checked by parsing), or None."""
    k = row[0] if row else None
    cands = []
    ex = f.example
    if isinstance(k, str) and re.fullmatch(r"M[\d.]+x[\d.]+", k):     # fine thread row
        cands.append(re.sub(r"M[\d.]+x[\d.]+", k, ex, count=1))
    if isinstance(k, str) and re.fullmatch(r"M\d+(\.\d+)?", k):
        cands.append(re.sub(r"M\d+(\.\d+)?", k, ex, count=1))
    elif isinstance(k, str) and k.startswith("ST"):
        cands.append(re.sub(r"ST[\d.]+", k, ex, count=1))
    elif isinstance(k, (int, float)) and f.words:
        cands += [f"{f.words[0]} {k:g}x1000", f"{f.id} {k:g}"]
    elif isinstance(k, (int, float)):
        cands += [re.sub(r"(?<=\s)[\d.]+(?=x|$)", f"{k:g}", ex, count=1), f"{f.nums[0] if f.nums else f.id} {k:g}"]
    elif isinstance(k, str):
        cands += [k, f"{f.words[0]} {k}" if f.words else k, f"{f.nums[0]} {k}" if f.nums else k,
                  re.sub(r"\d+(\.\d+)?x\d+(\.\d+)?(x\d+(\.\d+)?)?", k, ex, count=1),
                  re.sub(r"\d+(\.\d+)?x\d+(\.\d+)?", k, ex, count=1)]
    for c in cands:
        try:
            fam, _ = lookup(c)
        except (ValueError, KeyError):
            continue
        if fam is f:
            return c
    return None


def tree():
    """Families grouped by path for the viewer: [{id, title, path, example, columns, rows, ...}]."""
    load()
    out = []
    for fid in _ORDER:
        f = FAMILIES[fid]
        out.append({"id": f.id, "title": f.title, "path": f.path, "columns": f.columns, "rows": f.rows,
                    "codes": [row_code(f, r) for r in f.rows], "example": f.example, "source": f.source, "status": f.status,
                    "note": f.note, "aliases": " ".join([f.aliases] + f.nums + f.words), "tools": sorted(f.tools),
                    "origin": "built-in"})
    return out


# ---------------------------------------------------------------- common geometry helpers

def revolve(segs, clean=True):
    """Solid of revolution about Z from an XZ half-plane profile: [(x, z) | ("arc", mid, end)]."""
    import cadquery as cq
    wp = cq.Workplane("XZ").moveTo(*segs[0])
    for s in segs[1:]:
        wp = wp.threePointArc(s[1], s[2]) if s[0] == "arc" else wp.lineTo(*s)
    return wp.close().revolve(360, (0, 0, 0), (0, 1, 0), clean=clean)


def ring(r_out, r_in, h, z0=0.0):
    import cadquery as cq
    w = cq.Workplane("XY").workplane(offset=z0).circle(r_out)
    if r_in > 0:
        w = w.circle(r_in)
    return w.extrude(h)


def hexagon(s, h, z0=0.0):
    import cadquery as cq
    return cq.Workplane("XY").workplane(offset=z0).polygon(6, s / math.cos(math.pi / 6)).extrude(h)


def square(a, h, z0=0.0):
    import cadquery as cq
    return cq.Workplane("XY").workplane(offset=z0).rect(a, a).extrude(h)

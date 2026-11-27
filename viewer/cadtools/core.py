"""Shared core of the CAD4Ai tools: read a STEP into named, placed part instances; cache results on disk.

Every tool works on `Model` = list of `Inst` (unique name, solid placed in the assembly, the shape key
shared by instances of one part, parts.json info). Results that are expensive to compute are cached by
(file path, mtime, size, tool, args) under ~/.CAD4Ai/cache, so a second call is instant.
"""
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_HOME = os.environ.get("CAD4AI_HOME") or os.path.join(os.path.expanduser("~"), ".CAD4Ai")
CACHE = os.path.join(APP_HOME, "cache")
FASTENER = __import__("re").compile(
    r"(^|[^A-Za-z])M\d+(\.\d+)?x\d+|ISO ?(4762|4017|4014|4032|7089|7380|10642|4026|4027|4028|4029)|DIN ?(912|933|931|934|125|7991|7984|985|6325|471|472)|"
    r"UNI ?\d{4}|screw|bolt|nut|washer|šroub|matice|podlo[žz]ka|kolík|rivet|nýt", 2)


def _tools_version():
    """Cache key part that changes whenever the tools' code changes."""
    d = os.path.dirname(os.path.abspath(__file__))
    return str(max(os.path.getmtime(os.path.join(d, f)) for f in os.listdir(d) if f.endswith(".py")))


TOOLS_VERSION = _tools_version()

# density [g/cm3] by material name (lower-case substring match); default steel
DENSITY = {
    "s235": 7.85, "s355": 7.85, "11 3": 7.85, "ocel": 7.85, "steel": 7.85, "c45": 7.85, "42crmo4": 7.85,
    "nerez": 7.9, "1.4301": 7.9, "1.4404": 7.95, "aisi": 7.9, "stainless": 7.9,
    "al": 2.70, "hlin": 2.70, "6061": 2.70, "6082": 2.70, "7075": 2.81, "5754": 2.67,
    "mosaz": 8.5, "brass": 8.5, "bronz": 8.8, "měď": 8.96, "copper": 8.96, "cu": 8.96,
    "litina": 7.2, "cast iron": 7.2, "titan": 4.43, "ti": 4.43,
    "pla": 1.24, "petg": 1.27, "abs": 1.04, "asa": 1.07, "pa12": 1.01, "pa6": 1.14, "nylon": 1.14,
    "pom": 1.41, "pe": 0.95, "pp": 0.91, "pc": 1.2, "ptfe": 2.2, "pmma": 1.18, "tpu": 1.21,
    "dřevo": 0.6, "wood": 0.6, "pryž": 1.3, "rubber": 1.3,
}
# E [MPa], nu, yield [MPa]
MECH = {
    "steel": (210000, 0.30, 235), "s355": (210000, 0.30, 355), "c45": (210000, 0.30, 430),
    "stainless": (195000, 0.30, 210), "al": (69000, 0.33, 240), "7075": (71700, 0.33, 500),
    "brass": (100000, 0.34, 200), "titan": (114000, 0.34, 830), "pla": (3500, 0.36, 50),
    "petg": (2100, 0.38, 45), "abs": (2200, 0.35, 40), "pa12": (1700, 0.4, 45), "pom": (2900, 0.37, 60),
    "pc": (2400, 0.37, 60), "asa": (2000, 0.35, 45),
}


def density_of(material):
    m = (material or "").lower()
    best = None
    for k, d in DENSITY.items():
        if k in m and (best is None or len(k) > len(best[0])):
            best = (k, d)
    return best[1] if best else 7.85


def mech_of(material):
    m = (material or "steel").lower()
    alias = {"s235": "steel", "ocel": "steel", "11 3": "steel", "nerez": "stainless", "1.4301": "stainless",
             "hlin": "al", "6061": "al", "6082": "al", "mosaz": "brass", "ti": "titan"}
    for k in sorted(list(MECH) + list(alias), key=len, reverse=True):
        if k in m:
            return MECH[alias.get(k, k)]
    return MECH["steel"]


# ---------------------------------------------------------------- output

def emit(obj):
    """One compact JSON document on stdout (what Claude reads)."""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")


def r(v, n=2):
    if isinstance(v, (list, tuple)):
        return [r(x, n) for x in v]
    if isinstance(v, float):
        x = round(v, n)
        return 0.0 if x == 0 else x
    return v


# ---------------------------------------------------------------- cache

def file_key(path):
    st = os.stat(path)
    return f"{os.path.abspath(path).lower()}|{st.st_mtime_ns}|{st.st_size}"


def cache_path(path, tool, args=""):
    h = hashlib.sha1(f"{TOOLS_VERSION}|{file_key(path)}|{tool}|{args}".encode()).hexdigest()[:20]
    return os.path.join(CACHE, tool, h + ".json")


def cached(path, tool, args, fn):
    """Result of fn() for this exact file version, computed once. A lock file makes a second process that
    asks for the same thing at the same time (hook, viewer, script) wait for the first and reuse its result
    instead of computing it twice."""
    cp = cache_path(path, tool, args)

    def read():
        try:
            with open(cp, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None
    res = read()
    if res is not None:
        return res
    os.makedirs(os.path.dirname(cp), exist_ok=True)
    lock = cp + ".lock"
    fd = None
    for _ in range(3600):  # up to ~15 min behind another process doing the same work
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lock) > 900:  # stale lock of a crashed process
                    os.remove(lock)
                    continue
            except OSError:
                continue
            time.sleep(0.25)
            res = read()
            if res is not None:
                return res
    try:
        res = read()
        if res is not None:
            return res
        t0 = time.time()
        res = fn()
        if isinstance(res, dict):
            res.setdefault("seconds", round(time.time() - t0, 1))
        tmp = cp + f".{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False)
        os.replace(tmp, cp)
        return res
    finally:
        if fd is not None:
            os.close(fd)
            try:
                os.remove(lock)
            except OSError:
                pass


def prune_cache(max_mb=2000, max_days=60):
    """Delete cache files older than max_days, then the oldest until the cache is under max_mb.
    The search index and standard parts are kept (rebuilt only on request)."""
    keep = {"index", "std", "hook"}
    files = []
    for root, dirs, fs in os.walk(CACHE):
        rel = os.path.relpath(root, CACHE).split(os.sep)[0]
        if rel in keep:
            continue
        for f in fs:
            p = os.path.join(root, f)
            try:
                st = os.stat(p)
                files.append((st.st_atime if st.st_atime > st.st_mtime else st.st_mtime, st.st_size, p))
            except OSError:
                pass
    cutoff = time.time() - max_days * 86400
    total = sum(f[1] for f in files)
    removed = 0
    for t, size, p in sorted(files):
        if t < cutoff or total > max_mb * 1e6:
            try:
                os.remove(p)
                total -= size
                removed += 1
            except OSError:
                pass
    return removed


def model_key(path):
    """Stable key of a model across versions (same as the history folder idea): its absolute path."""
    base = os.path.abspath(path).lower()
    return hashlib.sha1(base.encode()).hexdigest()[:16]


def out_dir(path, sub):
    d = os.path.join(CACHE, sub, model_key(path))
    os.makedirs(d, exist_ok=True)
    return d


# ---------------------------------------------------------------- STEP reading

GENERIC = __import__("re").compile(r"^(NAUO\d*|Open CASCADE STEP translator.*|SOLID|Body|)$", 2)


METRIC = __import__("re").compile(r"(?:^|[^A-Za-z])M\d|ISO ?\d{4}|DIN ?\d{3}")
FLEX = __import__("re").compile(r"kabel|cable|lank|wire|vodi[cč]|p[aá]sek|strap|hadic|hose|(?<![a-z])lano|(?<![a-z])rope|tkanic|[sš]ňůr", 2)


class Inst:
    __slots__ = ("name", "shape", "key", "info", "path", "owner")

    def __init__(self, name, shape, key, info, path, owner=None):
        self.name, self.shape, self.key, self.info, self.path = name, shape, key, info, path
        self.owner = owner or name  # one STEP instance; its solids share the owner

    @property
    def type(self):
        t = (self.info or {}).get("type", "")
        if not t and FASTENER.search(self.name or "") and METRIC.search(self.name or ""):
            return "fastener"  # a fastener word AND a metric size (SROUB_M4x10), not just "bolt_plate"
        return t

    @property
    def flexible(self):
        """Cables, wires, straps, hoses: modelled crossing/clamped, overlaps with them are expected."""
        return bool(FLEX.search(self.name or ""))

    @property
    def material(self):
        return (self.info or {}).get("material", "")


def parts_info(step):
    base = os.path.splitext(step)[0]
    for cand in (base + ".parts.json", base.split("@", 1)[0] + ".parts.json"):
        try:
            with open(cand, encoding="utf-8") as f:
                return (json.load(f) or {}).get("parts", {}) or {}
        except (OSError, ValueError):
            continue
    return {}


def _info_for(info, name):
    if name in info:
        return info[name]
    # instance names like "Bolt_3" -> "Bolt"; longest matching prefix wins
    best = None
    for k in info:
        if name.startswith(k) and (best is None or len(k) > len(best)):
            best = k
    return info[best] if best else {}


_LOADED = {}


def load(step):
    """STEP -> list[Inst] of solid instances in their assembly position (memoised per file version, so
    several tools in one process read a big STEP once)."""
    k = file_key(step) if os.path.isfile(step) else step
    if k in _LOADED:
        return _LOADED[k]
    res = _load(step)
    _LOADED.clear()  # keep only the latest model (memory)
    _LOADED[k] = res
    return res


def _load(step):
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TDocStd import TDocStd_Document
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.TDF import TDF_Label, TDF_LabelSequence
    from OCP.TDataStd import TDataStd_Name
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_SOLID

    if step.lower().endswith(".stl"):
        raise ValueError("STL has no B-rep; the tools need a STEP")
    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    rd = STEPCAFControl_Reader()
    rd.SetNameMode(True)
    if rd.ReadFile(step) != IFSelect_RetDone or not rd.Transfer(doc):
        raise RuntimeError(f"cannot read STEP {step}")
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    info = parts_info(step)

    def name(lab):
        a = TDataStd_Name()
        return a.Get().ToExtString() if lab.FindAttribute(TDataStd_Name.GetID_s(), a) else ""

    out, used = [], {}

    def add(nm, shp, key, path):
        exp = TopExp_Explorer(shp, TopAbs_SOLID)
        solids = []
        while exp.More():
            solids.append(exp.Current())
            exp.Next()
        if not solids:
            return
        base = nm
        if base in used:
            used[base] += 1
            base = f"{nm}~{used[nm]}"
        else:
            used[base] = 1
        for i, s in enumerate(solids):
            n = base if len(solids) == 1 else f"{base}#{i + 1}"
            out.append(Inst(n, s, f"{key}:{i}", _info_for(info, nm), path, base))

    def walk(lab, loc, path):
        ref = lab
        if st.IsReference_s(lab):
            ref = TDF_Label()
            st.GetReferredShape_s(lab, ref)
            loc = loc.Multiplied(st.GetLocation_s(lab))
        nm = name(lab)
        if not nm or GENERIC.match(nm):
            nm = name(ref)
        if not nm or GENERIC.match(nm):
            nm = os.path.splitext(os.path.basename(step))[0] if not path else f"part{len(out) + 1}"
        if st.IsAssembly_s(ref):
            seq = TDF_LabelSequence()
            st.GetComponents_s(ref, seq)
            for i in range(1, seq.Length() + 1):
                walk(seq.Value(i), loc, path + [nm])
            return
        shp = st.GetShape_s(ref)
        if not loc.IsIdentity():
            shp = shp.Moved(loc)
        add(nm, shp, str(ref.Tag()), "/".join(path))

    roots = TDF_LabelSequence()
    st.GetFreeShapes(roots)
    for i in range(1, roots.Length() + 1):
        walk(roots.Value(i), TopLoc_Location(), [])
    return out


def find(model, names):
    """Instances matching names (exact, else case-insensitive substring); '*' = all."""
    if not names or names == ["*"]:
        return list(model)
    res = []
    for n in names:
        ex = [i for i in model if i.name == n]
        if not ex:
            ex = [i for i in model if n.lower() in i.name.lower()]
        if not ex:
            raise SystemExit(json.dumps({"ok": False, "error": f"no part '{n}'",
                                         "parts": [i.name for i in model][:60]}, ensure_ascii=False))
        res += [e for e in ex if e not in res]
    return res


# ---------------------------------------------------------------- geometry helpers

def bbox(shape, tight=True):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    b = Bnd_Box()
    (BRepBndLib.AddOptimal_s(shape, b, False, False) if tight else BRepBndLib.Add_s(shape, b, True))
    if b.IsVoid():
        return None
    x0, y0, z0, x1, y1, z1 = b.Get()
    return [x0, y0, z0, x1, y1, z1]


def props(shape):
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, g)
    c = g.CentreOfMass()
    a = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, a)
    return abs(g.Mass()), a.Mass(), [c.X(), c.Y(), c.Z()]


def faces(shape):
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopoDS import TopoDS
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        yield TopoDS.Face_s(exp.Current())
        exp.Next()


def mesh(shape, tol=None):
    """Triangulate -> (verts Nx3, tris Mx3) numpy arrays (outward oriented)."""
    import numpy as np
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopAbs import TopAbs_REVERSED
    if tol is None:
        b = bbox(shape, False) or [0, 0, 0, 1, 1, 1]
        tol = max(0.01, 0.002 * max(b[3] - b[0], b[4] - b[1], b[5] - b[2]))
    BRepMesh_IncrementalMesh(shape, tol, False, 0.35, True)
    V, T, off = [], [], 0
    for f in faces(shape):
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(f, loc)
        if tri is None:
            continue
        trsf = loc.Transformation()
        n = tri.NbNodes()
        for i in range(1, n + 1):
            p = tri.Node(i).Transformed(trsf)
            V.append((p.X(), p.Y(), p.Z()))
        rev = f.Orientation() == TopAbs_REVERSED
        for i in range(1, tri.NbTriangles() + 1):
            a, b_, c = tri.Triangle(i).Get()
            T.append((off + a - 1, off + c - 1, off + b_ - 1) if rev else (off + a - 1, off + b_ - 1, off + c - 1))
        off += n
    return np.array(V, float).reshape(-1, 3), np.array(T, int).reshape(-1, 3)


def pool(n=None):
    from concurrent.futures import ProcessPoolExecutor
    return ProcessPoolExecutor(max_workers=n or max(1, (os.cpu_count() or 2) - 1))

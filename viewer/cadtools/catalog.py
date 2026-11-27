"""Everything the plugin contains, as data for the viewer's Settings tabs (Libraries, Rules, Tools,
Skills & hooks, Data). Read-only overview; the viewer calls actions (open a part, accept a candidate,
trim the cache...) through the server."""
import json
import os
import re

from . import core, parts, std

ROOT = os.path.dirname(core.HERE)  # plugin / app folder


# ---------------------------------------------------------------- libraries

def _fam(fid, title, columns, rows, example, source_key, note=""):
    src = parts.SOURCES.get(source_key, ("", "unverified"))
    return {"id": fid, "title": title, "columns": columns, "rows": rows, "example": example,
            "source": src[0], "status": src[1], "note": note, "aliases": parts.ALIASES.get(fid, "")}


def libraries():
    sizes = sorted(std.THREAD, key=lambda s: float(s[1:]))
    fams = [
        _fam("thread", "Metric threads (holes)", ["size", "pitch", "tap drill", "clearance fine", "clearance", "clearance coarse", "cbore d", "cbore depth"],
             [[s, *std.THREAD[s][:1], std.THREAD[s][1], *std.THREAD[s][2:], *std.CBORE.get(s, ("", ""))] for s in sizes],
             "M5", "thread", "Convention: screw = nominal diameter, tapped hole / nut = tap drill. d2, D1, d3 by the ISO 68-1 formula in `std info`."),
        _fam("ISO 4762", "Socket head cap screws", ["size", "head d", "head h", "socket", "socket depth"],
             [[k, *v] for k, v in std.ISO4762.items()], "ISO 4762 M5x16", "ISO 4762", "Code: ISO 4762 M<d>x<L>; head seat at Z=0, shank to -Z."),
        _fam("ISO 4017", "Hex head screws", ["size", "across flats", "head h"], [[k, *v] for k, v in std.ISO4017.items()],
             "ISO 4017 M8x30", "ISO 4017"),
        _fam("ISO 10642", "Countersunk socket screws", ["size", "head d", "head h", "socket"], [[k, *v] for k, v in std.ISO10642.items()],
             "ISO 10642 M6x20", "ISO 10642", "Head top at Z=0, L includes the head."),
        _fam("ISO 7380", "Button head screws", ["size", "head d", "head h", "socket"], [[k, *v] for k, v in std.ISO7380.items()],
             "ISO 7380 M4x10", "ISO 7380"),
        _fam("ISO 4029", "Set screws (cup point)", ["size", "socket"], [[k, v] for k, v in std.SETSCREW.items()], "ISO 4029 M5x8", "ISO 4029"),
        _fam("ISO 4032", "Hex nuts", ["size", "across flats", "height"], [[k, *v] for k, v in std.ISO4032.items()], "ISO 4032 M8", "ISO 4032",
             "Hole = tap drill (thread convention)."),
        _fam("ISO 4035", "Thin hex nuts", ["size", "height"], [[k, v] for k, v in std.ISO4035.items()], "ISO 4035 M8", "ISO 4035"),
        _fam("DIN 985", "Nylon insert lock nuts", ["size", "height"], [[k, v] for k, v in parts.DIN985.items()], "DIN 985 M6", "DIN 985"),
        _fam("ISO 7089", "Plain washers", ["size", "d1", "d2", "h"], [[k, *v] for k, v in std.ISO7089.items()], "ISO 7089 M8", "ISO 7089"),
        _fam("ISO 8734", "Dowel pins", ["code"], [["ISO 8734 <d>x<L> (any)"]], "ISO 8734 6x20", "ISO 8734"),
        _fam("bearing", "Deep groove ball bearings", ["code", "d", "D", "B"], [[k, *v] for k, v in sorted(std.BEARING.items(), key=lambda kv: (kv[1][0], kv[1][1]))],
             "6204", "ISO 15", "Code = bearing number. Shaft k5/j6, housing H7/J7 (typical recommendation)."),
        _fam("NEMA", "Stepper motors", ["code", "flange", "hole pitch", "screw", "pilot d", "pilot h", "shaft d"],
             [[k, *v] for k, v in std.NEMA.items()], "NEMA17 x48", "NEMA", "Code: NEMA<size> x<body length>."),
        _fam("profile", "Aluminium slot profiles", ["code", "size", "slot", "centre bore"], [[k, *v] for k, v in std.PROFILE.items()],
             "2020x200", "profile", "Code: <profile>x<length>. Simplified section."),
        _fam("O-ring", "O-rings", ["code"], [["O-ring <d1>x<d2> (any)"]], "O-ring 20x2", "ISO 3601", "Groove sizes are typical guidelines."),
        _fam("key", "Parallel keys", ["shaft from", "shaft to", "b", "h", "t1 shaft", "t2 hub"], [list(r) for r in std.KEYS],
             "key 30", "DIN 6885", "`cad4ai std key <shaft d>`."),
        _fam("DIN 471", "Circlips for shafts", ["shaft d", "groove d", "groove w", "ring s"],
             [[k, *v, parts.CIRCLIP_S.get(k, "")] for k, v in std.DIN471.items()], "DIN 471 20", "DIN 471"),
        _fam("DIN 472", "Circlips for bores", ["bore d", "groove d", "groove w", "ring s"],
             [[k, *v, parts.CIRCLIP_S.get(k, "")] for k, v in std.DIN472.items()], "DIN 472 47", "DIN 472"),
        _fam("insert", "Heat-set inserts (3D print)", ["size", "hole d", "outer d", "length"], [[k, *v] for k, v in parts.INSERT.items()],
             "insert M3", "insert", "Makers differ: take the hole size from your insert's data sheet."),
    ]
    keep = {"thread", "NEMA", "insert"}       # legacy tables not (yet) in the registry
    fams = [f for f in fams if f["id"] in keep]
    paths = {"thread": "Závity a díry", "NEMA": "Elektro/Krokové motory", "insert": "Konstrukční prvky/Zalisovací vložky"}
    for f in fams:
        f["origin"] = "built-in"
        f["path"] = paths.get(f["id"], "Ostatní")
    from . import famreg
    fams = famreg.tree() + fams
    from . import userlib
    for uf in userlib.families(True):
        fams.append({"id": uf.get("id"), "title": uf.get("title", uf.get("id")), "path": "Vlastní/" + str(uf.get("title", uf.get("id"))),
                     "columns": uf.get("columns", []),
                     "rows": uf.get("rows", []), "example": uf.get("example", ""), "source": uf.get("source", ""),
                     "status": uf.get("status", "unverified"), "note": uf.get("note", ""), "aliases": uf.get("aliases", ""),
                     "origin": "user", "file": uf.get("_file"), "broken": uf.get("broken", False)})
    return fams


# ---------------------------------------------------------------- rules

RULES = [
    {"group": "Threads", "title": "Thread representation", "level": "convention",
     "text": "External thread (screw, stud) = cylinder of the nominal diameter (M4 → 4.0). Internal thread (tapped hole, nut, insert) = hole of the tap drill (M4 → 3.3).",
     "where": "cadtools/std.py, parts.py; library nuts; tap_drill()"},
    {"group": "Threads", "title": "Thread engagement is not a collision", "level": "check",
     "text": "Overlap of a screw with its thread is accepted when it is at most the ring between the nominal and tap-drill diameters over the engaged length (+15 %). More = real collision (hole missing or smaller than the tap drill).",
     "where": "cadtools/collide.py"},
    {"group": "Threads", "title": "Screw length and engagement", "level": "default",
     "text": "bolt_joint picks the stock length: through bolt = stack + washers + nut + 2 pitches; into a thread = grip + engagement (1 d steel, 2 d aluminium/plastic); tap depth = engagement + 3 pitches.",
     "where": "cadtools/parts.py bolt_joint"},
    {"group": "Holes", "title": "Clearance holes", "level": "default",
     "text": "ISO 273 medium series by default (M4 4.5, M5 5.5, M6 6.6, M8 9). Fine and coarse in `std hole`.",
     "where": "cadtools/std.py THREAD"},
    {"group": "Collisions", "title": "What is not a collision", "level": "check",
     "text": "Solids of one STEP part overlapping each other (listed as a modelling note), cables / wires / straps / hoses (expected contacts), thread engagements. Touching faces are listed apart.",
     "where": "cadtools/collide.py"},
    {"group": "Collisions", "title": "Incremental check", "level": "info",
     "text": "Pairs of unchanged parts reuse the previous result (fingerprint: volume, area, box, centre of mass).",
     "where": "cadtools/collide.py"},
    {"group": "Library", "title": "Part placement", "level": "convention",
     "text": "Every library part has its main axis on local +Z; screws: head seat at Z=0, shank to -Z (countersunk: head top at Z=0); other parts: bottom at Z=0. place(code, at, up, anchor, spin).",
     "where": "cadtools/parts.py"},
    {"group": "Library", "title": "Value status", "level": "info",
     "text": "Each table carries its source and status: unverified (typed from general knowledge), vendor (maker values differ), formula (computed from the standard's definition), verified (checked by a person).",
     "where": "cadtools/parts.py SOURCES"},
    {"group": "Scripts", "title": "Parameters", "level": "mandatory",
     "text": "Sizes as UPPER_CASE parameters at the top, one per line, plain number with a comment: NAME = 5.5  # what [mm] lo..hi, grouped under # --- Group --- lines. Computed values are not editable in the viewer.",
     "where": "cadtools/params.py (viewer, sandbox, guard), lint"},
    {"group": "Scripts", "title": "Helper imports", "level": "mandatory",
     "text": "Model scripts import helpers via sys.path.insert(0, os.path.expanduser(\"~/.CAD4Ai/lib\")) - never the versioned plugin folder.",
     "where": "cadtools/install.py"},
    {"group": "Scripts", "title": "Lint warnings", "level": "check",
     "text": "Duplicate assembly names, constant names in loops, fillet/chamfer without an edge selector, hole(5) typed for M5, parameters without comment / unit, unused parameters, no STEP export.",
     "where": "cadtools/lint.py (hook after writing a script)"},
    {"group": "Scripts", "title": "Design intent", "level": "check",
     "text": "expect(...).size / holes / mass / clearance / count / inside run at the end of the script on the exported STEP; no_collisions() is checked by the hook after the export.",
     "where": "cadtools/expect.py"},
    {"group": "Scripts", "title": "Unexpected changes", "level": "check",
     "text": "After a parameter-only edit, a changed part that none of the changed parameters drive is reported.",
     "where": "cadtools/guard.py"},
    {"group": "Export", "title": "STEP only", "level": "mandatory",
     "text": "Models are exported as STEP (other formats only on request, via the viewer's Export menu). Variants as name@label.step.",
     "where": "plugin instructions"},
    {"group": "Data", "title": "Clean app folder", "level": "mandatory",
     "text": "The app / plugin folder holds no project data: session data aimed there goes to ~/.CAD4Ai/sessions, no __pycache__, leftovers moved at server start.",
     "where": "viewer/server.py safe_data_dir, clean_app_folder"},
    {"group": "Data", "title": "parts.json", "level": "default",
     "text": "Missing entries are added after each export, only when certain (recognised standard part); existing entries are never changed.",
     "where": "cadtools/scaffold.py"},
    {"group": "Library", "title": "Library candidates", "level": "info",
     "text": "Parts named like a family the library lacks (profiles, rails, springs, hinges...), custom shapes repeated 8x in a model or used in 2 models are suggested once as a new library family.",
     "where": "cadtools/libscan.py"},
]


# ---------------------------------------------------------------- tools, skills, hooks

def tools():
    import importlib.util
    spec = importlib.util.spec_from_file_location("cad4ai_cli_doc", os.path.join(core.HERE, "cad4ai.py"))
    src = open(spec.origin, encoding="utf-8").read()
    doc = re.search(r'"""(.*?)"""', src, re.S).group(1)
    out = []
    for line in doc.splitlines():
        m = re.match(r"\s+cad4ai (\S+)\s+(.*?)\s{2,}(.*)$", line)
        if m:
            out.append({"cmd": m.group(1), "args": m.group(2).strip(), "what": m.group(3).strip()})
        else:
            m = re.match(r"\s+cad4ai (\S+)\s+(.*)$", line)
            if m:
                out.append({"cmd": m.group(1), "args": "", "what": m.group(2).strip()})
    return out


def skills():
    out = []
    sd = os.path.join(ROOT, "skills")
    for n in sorted(os.listdir(sd)) if os.path.isdir(sd) else []:
        p = os.path.join(sd, n, "SKILL.md")
        if not os.path.isfile(p):
            continue
        txt = open(p, encoding="utf-8").read()
        m = re.search(r"^description:\s*(.+)$", txt, re.M)
        body = txt.split("---", 2)[-1].strip()
        out.append({"name": n, "description": m.group(1).strip() if m else "", "body": body[:6000],
                    "scripts": sorted(os.listdir(os.path.join(sd, n, "scripts"))) if os.path.isdir(os.path.join(sd, n, "scripts")) else []})
    return out


HOOK_TEXT = {
    "start": "Session start: syncs ~/.CAD4Ai/lib, daily index/cache jobs; in CAD folders one line telling Claude where the tools are.",
    "pre": "Before Read: blocks reading .step/.stl/... as text (huge, useless tokens).",
    "post": "After a command: failing CadQuery script → doctor result; changed .step → diff, validity, expect, collisions, unexpected changes, parts.json, library candidates.",
    "edit": "After writing a CadQuery script: lint warnings only.",
}


def hooks():
    try:
        with open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return []
    out = []
    for ev, items in (d.get("hooks") or {}).items():
        for it in items:
            for h in it.get("hooks", []):
                mode = h.get("command", "").rsplit(" ", 1)[-1]
                out.append({"event": ev, "matcher": it.get("matcher", "*"), "mode": mode, "what": HOOK_TEXT.get(mode, ""),
                            "timeout": h.get("timeout")})
    return out


# ---------------------------------------------------------------- data

def _size(p):
    total, n = 0, 0
    for root, _d, files in os.walk(p):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
                n += 1
            except OSError:
                pass
    return total, n


def data():
    home = core.APP_HOME
    rows = []
    for name, what in (("cache", "results of the local tools (digests, collisions, FEM, views...) - trimmed to 2 GB / 60 days"),
                       ("history", "versions of every model (older STEPs gzip-compressed)"),
                       ("lib", "stable copy of the helpers for model scripts"),
                       ("library", "your own part families and library candidates"),
                       ("sessions", "notes of chats opened in the app folder itself")):
        size, n = _size(os.path.join(home, name))
        rows.append({"name": name, "path": os.path.join(home, name), "mb": round(size / 1e6, 1), "files": n, "what": what})
    return {"home": home, "folders": rows, "app_folder": ROOT}


def overview():
    from . import libscan
    return {"libraries": libraries(), "rules": RULES, "tools": tools(), "skills": skills(), "hooks": hooks(),
            "data": data(), "candidates": libscan.listing(("new", "suggested", "accepted", "dismissed")),
            "version": _version()}


def _version():
    try:
        with open(os.path.join(ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            return json.load(f).get("version")
    except (OSError, ValueError):
        return None
